.pragma library

// browserGlass daemon logic: pure functions, no QML object, no I/O. The
// daemon (BrowserGlassDaemon.qml) and the uninstall sweep
// (components/UninstallSweep.qml) call them; the QML tests import this file
// directly. Every function returns new values and never mutates its
// arguments.
//
// ---------------------------------------------------------------------------
// What the daemon shares with the settings page and the bar widget
// ---------------------------------------------------------------------------
// PluginGlobalVar names (PluginService.getGlobalVar("browserGlass", name)):
//   glassActive    bool     glass is on (status.glass.active, or the last
//                           sync's "glass" until a status arrives)
//   restartNeeded  bool     a running browser must restart to show the
//                           current files (status.restart_needed); while it
//                           is true the daemon polls `status --json` every
//                           POLL_INTERVAL_MS
//   status         object   the last `status --json` document (contract
//                           spec "status"), null before the first one
//   lastSync       object   the last successful `sync` line (contract spec
//                           "sync"), null before the first one
//   sites          array    `sites --json` ([{name, domains}]), loaded once
//                           at start; null until loaded
//   lastError      string   the last error ("" when the last sync and status
//                           succeeded)
//   syncing        bool     a sync is scheduled or running
// Daemon functions (PluginService.pluginDaemonInstances["browserGlass"],
// also reachable with `dms ipc call browserGlass ...`):
//   requestSync(reason)  refreshStatus()  loadSites()  toggleGlass()
//   excludeClipboard()   copyReport()
//
// ---------------------------------------------------------------------------
// pluginData keys (what the settings page stores) -> sync --settings JSON
// ---------------------------------------------------------------------------
//   glassEnabled     bool, default true (bar widget switch)
//   opacityOverride  bool, default false
//   opacity          SliderSetting int percent (0..100), default 85 -> /100
//   siteTheme        "follow" | "dark" | "none", default "follow"
//   pagesTransparent bool, default true (v0 key, master switch for pages)
//   genericStyle     bool, default true
//   excludedSites    [{domain}] (v0 key, ListSettingWithInput) -> excluded[]
//   disabledStyles   [name] (or [{name}]) -> disabledStyles[]
//   newTabGlass, readerOpaque, privateGlass   bool, defaults true
//   blur <- SettingsData.blurEnabled, isLight <- SessionData.isLightMode

var PLUGIN_ID = "browserGlass";

// Identical to browserglass.py STDIN_BOOTSTRAP: runs the script text read
// from stdin, so the uninstaller needs no file (one argv string is capped
// at 128 KiB and the script is larger).
var STDIN_BOOTSTRAP = "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))";

// browserglass.py EXIT_KEPT: `uninstall --if-gone` found plugin.json back
// after its grace period (an update or a reinstall) and did nothing.
var EXIT_KEPT = 3;

var SYNC_DEBOUNCE_MS = 800;
var POLL_INTERVAL_MS = 10000;
var BUSY_RETRY_MS = 2000;
var MAX_BUSY_RETRIES = 3;
// Failed status reads in a row before the restart poll stops
var MAX_STATUS_FAILURES = 3;
// A Qt coarse timer may fire up to 5% early: a request this close to the
// end of the debounce may find the sync already launched.
var DEBOUNCE_SAFETY = 0.9;

var WARN_RULE_HELD = "niri_rule_held";
var WARN_RULE_STALE = "niri_rule_stale";
// Warning codes worth a toast (once per code and profile per session);
// the others only show in the status block.
var TOAST_WARNINGS = ["zen_transparency_mod", "read_only", "write_failed", "read_failed",
    "data_unavailable", "state_corrupt", "state_unavailable", "backup_failed", "fork_failed"];

var DEFAULTS = {
    "glassEnabled": true,
    "opacityOverride": false,
    "opacity": 85,
    "siteTheme": "follow",
    "pagesTransparent": true,
    "genericStyle": true,
    "newTabGlass": true,
    "readerOpaque": true,
    "privateGlass": true
};
var SITE_THEMES = ["follow", "dark", "none"];
var BOOL_KEYS = ["glassEnabled", "opacityOverride", "pagesTransparent", "genericStyle",
    "newTabGlass", "readerOpaque", "privateGlass"];

// ---------------------------------------------------------------------------
// Settings and command lines
// ---------------------------------------------------------------------------

function _bool(value, fallback) {
    if (typeof value === "boolean")
        return value;
    if (value === 0 || value === 1)
        return value === 1;
    if (typeof value === "string") {
        var v = value.trim().toLowerCase();
        if (v === "true" || v === "1" || v === "yes" || v === "on")
            return true;
        if (v === "false" || v === "0" || v === "no" || v === "off")
            return false;
    }
    return fallback;
}

// SliderSetting stores an int percent: an integer is a percent (85 -> 0.85),
// a fraction in [0, 1] is kept (0.85). Clamped to [0, 1], 2 decimals.
function opacityFraction(value) {
    var n = typeof value === "string" ? Number(value.trim()) : value;
    if (typeof n !== "number" || !isFinite(n))
        n = DEFAULTS.opacity;
    var f = (Number.isInteger(n) || n > 1) ? n / 100 : n;
    f = Math.min(1, Math.max(0, f));
    return Math.round(f * 100) / 100;
}

function _items(list, field) {
    if (!Array.isArray(list))
        return [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
        var item = list[i];
        var text = (item !== null && typeof item === "object") ? item[field] : item;
        if (typeof text !== "string")
            continue;
        text = text.trim();
        if (text && out.indexOf(text) < 0)
            out.push(text);
    }
    return out;
}

// The --settings object for `sync` (contract spec "settings"), every key
// present. pluginData may be null or partial.
function buildSettings(pluginData, blurEnabled, isLightMode) {
    var d = pluginData || {};
    var s = {
        "blur": blurEnabled !== false,
        "isLight": isLightMode === true
    };
    for (var i = 0; i < BOOL_KEYS.length; i++) {
        var key = BOOL_KEYS[i];
        s[key] = _bool(d[key], DEFAULTS[key]);
    }
    s.opacity = opacityFraction(d.opacity === undefined || d.opacity === null ? DEFAULTS.opacity : d.opacity);
    var theme = typeof d.siteTheme === "string" ? d.siteTheme.trim().toLowerCase() : "";
    s.siteTheme = SITE_THEMES.indexOf(theme) >= 0 ? theme : DEFAULTS.siteTheme;
    s.excluded = _items(d.excludedSites, "domain");
    s.disabledStyles = _items(d.disabledStyles, "name");
    // Key order of the contract (stable JSON text, comparable between syncs)
    var ordered = {};
    var order = ["blur", "isLight", "glassEnabled", "opacityOverride", "opacity", "siteTheme",
        "pagesTransparent", "genericStyle", "excluded", "disabledStyles", "newTabGlass",
        "readerOpaque", "privateGlass"];
    for (var j = 0; j < order.length; j++)
        ordered[order[j]] = s[order[j]];
    return ordered;
}

function settingsJson(pluginData, blurEnabled, isLightMode) {
    return JSON.stringify(buildSettings(pluginData, blurEnabled, isLightMode));
}

function _dir(pluginDir) {
    return String(pluginDir || "").replace(/\/+$/, "");
}
function scriptPath(pluginDir) {
    return _dir(pluginDir) + "/browserglass.py";
}
function dataDir(pluginDir) {
    return _dir(pluginDir) + "/data";
}
function manifestPath(pluginDir) {
    return _dir(pluginDir) + "/plugin.json";
}

// --if-plugin: the script refuses ("plugin_gone:") when plugin.json is gone,
// so a sync started just before the folder was deleted writes nothing back
// after the uninstall sweep.
function syncArgv(pluginDir, settingsText) {
    return ["python3", "-I", scriptPath(pluginDir), "sync", "--data", dataDir(pluginDir),
        "--settings", settingsText, "--if-plugin", manifestPath(pluginDir)];
}
function statusArgv(pluginDir) {
    return ["python3", "-I", scriptPath(pluginDir), "status", "--json"];
}
function sitesArgv(pluginDir) {
    return ["python3", "-I", scriptPath(pluginDir), "sites", "--json", "--data", dataDir(pluginDir)];
}
function reportArgv(pluginDir) {
    return ["python3", "-I", scriptPath(pluginDir), "report"];
}
function uninstallArgv(pluginDir) {
    return ["python3", "-I", scriptPath(pluginDir), "uninstall"];
}
// The deleted-folder uninstaller: the script text goes on its stdin. It
// waits a grace period, then does nothing (EXIT_KEPT) if plugin.json is back.
function sweepArgv(pluginDir) {
    return ["python3", "-I", "-c", STDIN_BOOTSTRAP, "uninstall", "--if-gone", manifestPath(pluginDir)];
}

// ---------------------------------------------------------------------------
// Output parsing
// ---------------------------------------------------------------------------

// The last non-empty line of `text` parsed as JSON, or null
function parseJsonLine(text) {
    var lines = String(text || "").split("\n");
    for (var i = lines.length - 1; i >= 0; i--) {
        var line = lines[i].trim();
        if (!line)
            continue;
        try {
            return JSON.parse(line);
        } catch (e) {
            return null;
        }
    }
    return null;
}

// The whole of `text` parsed as JSON (status is one line, but tolerate a
// pretty-printed document), or null
function parseJson(text) {
    var t = String(text || "").trim();
    if (!t)
        return null;
    try {
        return JSON.parse(t);
    } catch (e) {
        return parseJsonLine(t);
    }
}

function _isObject(v) {
    return v !== null && typeof v === "object" && !Array.isArray(v);
}

// The error text of a failed command: its {"error"} line, else the exit code
function errorText(stdout, exitCode) {
    var doc = parseJsonLine(stdout);
    if (_isObject(doc) && typeof doc.error === "string" && doc.error)
        return doc.error;
    if (exitCode === 124)
        return "timed out";
    return "exit code " + exitCode;
}

// The state lock was held by another browserGlass command: worth a retry
function isBusyError(message) {
    return /state lock/.test(String(message || ""));
}

// sync --if-plugin refused: the plugin folder is gone or being removed (the
// sweep handles it), so this is not an error worth a toast
function isPluginGoneError(message) {
    return /^plugin_gone:/.test(String(message || ""));
}

// {ok, result, error}: result is the sync line (contract spec "sync")
function parseSync(stdout, exitCode) {
    if (exitCode !== 0)
        return {"ok": false, "result": null, "error": errorText(stdout, exitCode)};
    var doc = parseJsonLine(stdout);
    if (!_isObject(doc) || typeof doc.glass !== "boolean")
        return {"ok": false, "result": null, "error": "unreadable sync output"};
    var r = {
        "glass": doc.glass,
        "opacity": typeof doc.opacity === "number" ? doc.opacity : 0,
        "reason": typeof doc.reason === "string" ? doc.reason : "",
        "first_run": doc.first_run === true,
        "changed": Array.isArray(doc.changed) ? doc.changed : [],
        "running_changed": Array.isArray(doc.running_changed) ? doc.running_changed : [],
        "niri_changed": doc.niri_changed === true,
        "warnings": Array.isArray(doc.warnings) ? doc.warnings.filter(_isObject) : []
    };
    return {"ok": true, "result": r, "error": ""};
}

function _hasWarning(status, code) {
    var list = (status && Array.isArray(status.warnings)) ? status.warnings : [];
    for (var i = 0; i < list.length; i++) {
        if (list[i] && list[i].code === code)
            return true;
    }
    return false;
}

// {ok, status, error, glassActive, restartNeeded, stale, held}
//   stale  status reports niri_rule_stale: the daemon must run sync
//   held   a running browser still holds the niri rule (niri_rule_held)
function parseStatus(stdout, exitCode) {
    var bad = {"ok": false, "status": null, "error": "", "glassActive": false,
        "restartNeeded": false, "stale": false, "held": false};
    if (exitCode !== 0) {
        bad.error = errorText(stdout, exitCode);
        return bad;
    }
    var doc = parseJson(stdout);
    if (!_isObject(doc) || !_isObject(doc.glass)) {
        bad.error = "unreadable status output";
        return bad;
    }
    if (!Array.isArray(doc.warnings))
        doc.warnings = [];
    if (!Array.isArray(doc.browsers))
        doc.browsers = [];
    return {
        "ok": true,
        "status": doc,
        "error": "",
        "glassActive": doc.glass.active === true,
        "restartNeeded": doc.restart_needed === true,
        "stale": _hasWarning(doc, WARN_RULE_STALE),
        "held": _hasWarning(doc, WARN_RULE_HELD)
    };
}

// {ok, sites, error}: sites is [{name, domains}]
function parseSites(stdout, exitCode) {
    if (exitCode !== 0)
        return {"ok": false, "sites": null, "error": errorText(stdout, exitCode)};
    var doc = parseJson(stdout);
    if (!Array.isArray(doc))
        return {"ok": false, "sites": null, "error": "unreadable sites output"};
    var out = [];
    for (var i = 0; i < doc.length; i++) {
        var s = doc[i];
        if (_isObject(s) && typeof s.name === "string")
            out.push({"name": s.name, "domains": Array.isArray(s.domains) ? s.domains : []});
    }
    return {"ok": true, "sites": out, "error": ""};
}

// Why glass is off, as a source string for I18n.trFor (reason codes of the
// contract)
function reasonText(reason) {
    switch (reason) {
    case "active":
        return "Glass is on";
    case "blur_disabled":
        return "DMS blur is off";
    case "opaque":
        return "Window opacity is 100%";
    case "toggled_off":
        return "Glass is turned off";
    case "forced_off":
        return "Glass is forced off";
    default:
        return "Glass is off";
    }
}

// What a warning code (status contract) means, as a source string for
// I18n.trFor (the status block and the warning toasts; the CLI's own
// message, technical and in English, goes in the toast details)
function warningText(code) {
    switch (code) {
    case "zen_transparency_mod":
        return "Zen transparency mod detected: it may stack with Browser Glass";
    case "read_only":
        return "A browser file is read-only: it was left unchanged";
    case "write_failed":
        return "A file could not be written";
    case "read_failed":
        return "A browser profile was skipped: a file could not be read";
    case "data_unavailable":
        return "The site styles could not be read";
    case "site_style_invalid":
        return "A site style was skipped: it is not valid";
    case "state_corrupt":
        return "The plugin's saved state was unusable: it starts afresh";
    case "state_unavailable":
        return "The plugin's saved state could not be used";
    case "backup_failed":
        return "A browser profile was skipped: no backup could be taken";
    case "backup_kept":
        return "A browser file was edited since its backup: the original was kept";
    case "fork_failed":
        return "The clean-up after the browser closes could not start";
    case "profile_missing":
        return "A browser profile folder was not found";
    case "dangling_link":
        return "A browser file is a broken link: it was left unchanged";
    case "niri_rule_held":
        return "The niri rule stays until the running browsers restart";
    case "niri_rule_stale":
        return "The niri rule is out of date";
    default:
        return "Browser Glass warning";
    }
}

// The warnings of a status worth showing: niri_rule_stale is the daemon's
// cue to sync again, not news; dropHeld also leaves out niri_rule_held
// (the popout's count)
function statusWarnings(status, dropHeld) {
    var list = status && Array.isArray(status.warnings) ? status.warnings : [];
    return list.filter(function (w) {
        return _isObject(w) && w.code !== WARN_RULE_STALE && !(dropHeld && w.code === WARN_RULE_HELD);
    });
}

// Browser family codes (status contract) as product names
var FAMILY_NAMES = {
    "firefox": "Firefox",
    "librewolf": "LibreWolf",
    "zen": "Zen",
    "floorp": "Floorp",
    "waterfox": "Waterfox"
};

function familyName(family) {
    var code = String(family || "");
    return Object.prototype.hasOwnProperty.call(FAMILY_NAMES, code) ? FAMILY_NAMES[code] : (code || "?");
}

// The product names of a list of status browsers, each once, in order
function familyNames(browsers) {
    var out = [];
    var list = Array.isArray(browsers) ? browsers : [];
    for (var i = 0; i < list.length; i++) {
        if (!_isObject(list[i]) || !list[i].family)
            continue;
        var name = familyName(list[i].family);
        if (out.indexOf(name) < 0)
            out.push(name);
    }
    return out;
}

// ---------------------------------------------------------------------------
// Sync debounce bookkeeping
// ---------------------------------------------------------------------------
// One sync at a time (browserglass.py holds a lock: a second one would fail).
// Proc.runCommand restarts its debounce on every call with the same id, so
// requests in the debounce window collapse into one launch carrying the last
// command. Once the sync may have launched, a new request is remembered
// (dirty) and runs after it.
//   phase  "idle" | "scheduled" (runCommand called, callback not yet back)
//   scheduledAt  time of the last runCommand call (ms)
//   dirty  a request came while the sync may be running
//   reasons  what asked for the pending sync
//   busyRetries  consecutive "state lock held" failures

function newSyncBook() {
    return {"phase": "idle", "scheduledAt": 0, "dirty": false, "reasons": [], "busyRetries": 0};
}

function _copyBook(book) {
    var b = book || newSyncBook();
    return {
        "phase": b.phase || "idle",
        "scheduledAt": b.scheduledAt || 0,
        "dirty": b.dirty === true,
        "reasons": Array.isArray(b.reasons) ? b.reasons.slice() : [],
        "busyRetries": b.busyRetries || 0
    };
}

// A sync is asked for. {book, schedule}: schedule true means call
// Proc.runCommand now (first request, or one still inside the debounce
// window, which restarts it with fresh settings).
function syncRequest(book, reason, now, debounceMs) {
    var b = _copyBook(book);
    var wait = typeof debounceMs === "number" ? debounceMs : SYNC_DEBOUNCE_MS;
    if (reason && b.reasons.indexOf(reason) < 0)
        b.reasons.push(reason);
    // A fresh request gets its own lock retries
    b.busyRetries = 0;
    var since = now - b.scheduledAt;
    // The wall clock went back: the sync may be running, do not restart it
    if (since < 0)
        since = wait;
    if (b.phase === "scheduled" && since >= wait * DEBOUNCE_SAFETY) {
        b.dirty = true;
        return {"book": b, "schedule": false};
    }
    b.phase = "scheduled";
    b.scheduledAt = now;
    return {"book": b, "schedule": true};
}

// The sync callback came back. busy: it failed on the state lock.
// {book, schedule, retry}: schedule true means run another sync now (a
// request came meanwhile, or a lock retry); retry true when it is a lock
// retry (the daemon uses BUSY_RETRY_MS as its debounce).
function syncFinished(book, now, busy) {
    var b = _copyBook(book);
    b.phase = "idle";
    var retry = false;
    if (busy && b.busyRetries < MAX_BUSY_RETRIES) {
        b.busyRetries += 1;
        retry = true;
    } else if (!busy) {
        b.busyRetries = 0;
    }
    if (b.dirty || retry) {
        var wasDirty = b.dirty;
        b.dirty = false;
        b.phase = "scheduled";
        b.scheduledAt = now;
        return {"book": b, "schedule": true, "retry": retry && !wasDirty};
    }
    b.reasons = [];
    return {"book": b, "schedule": false, "retry": false};
}

// ---------------------------------------------------------------------------
// Toasts and follow-ups
// ---------------------------------------------------------------------------
// A toast is {level: "info" | "warning" | "error", text, details[, detailsTr]};
// text is a source string the daemon passes to I18n.trFor; details is shown
// as is (an error text, a domain), unless detailsTr is true: then it is a
// source string too (reasonText()'s).
// ctx (daemon memory, one session):
//   lastErrorShown   the error text last toasted ("" after a success)
//   restartShown     the restart toast was shown in this restart episode
//   warningsShown    ["code/profile", ...] already toasted
//   staleResync      a sync was run for niri_rule_stale in this episode

function newToastContext() {
    return {"lastErrorShown": "", "restartShown": false, "warningsShown": [], "staleResync": false};
}

function _copyCtx(ctx) {
    var c = ctx || newToastContext();
    return {
        "lastErrorShown": c.lastErrorShown || "",
        "restartShown": c.restartShown === true,
        "warningsShown": Array.isArray(c.warningsShown) ? c.warningsShown.slice() : [],
        "staleResync": c.staleResync === true
    };
}

function _warningToasts(warnings, c, toasts) {
    for (var i = 0; i < warnings.length; i++) {
        var w = warnings[i];
        if (!w || TOAST_WARNINGS.indexOf(w.code) < 0)
            continue;
        var key = w.code + "/" + (w.profile || "");
        if (c.warningsShown.indexOf(key) >= 0)
            continue;
        c.warningsShown.push(key);
        // The text is warningText()'s (translated by the daemon); the CLI's
        // message is shown as is
        toasts.push({
            "level": "warning",
            "text": warningText(w.code),
            "details": typeof w.message === "string" ? w.message : ""
        });
    }
}

// The toasts for one sync outcome (parseSync()'s value). {toasts, ctx}
//   error         once per distinct error text (busy retries stay silent)
//   first run     "set up" (glass on: restart the browser; off: why)
//   restart       a running browser's files changed (running_changed), once
//                 per restart episode
//   warnings      TOAST_WARNINGS, once per code and profile
function syncToasts(outcome, ctx, retrying) {
    var c = _copyCtx(ctx);
    var toasts = [];
    if (!outcome || !outcome.ok) {
        var message = outcome ? outcome.error : "unknown error";
        if (!retrying && message !== c.lastErrorShown && !isPluginGoneError(message)) {
            c.lastErrorShown = message;
            toasts.push({"level": "error", "text": "Browser Glass sync failed", "details": message});
        }
        return {"toasts": toasts, "ctx": c};
    }
    c.lastErrorShown = "";
    var r = outcome.result;
    if (r.first_run) {
        if (r.glass)
            toasts.push({"level": "info", "text": "Browser Glass is set up: restart your browser to see the glass", "details": ""});
        else
            toasts.push({"level": "info", "text": "Browser Glass is set up, but glass is off", "details": reasonText(r.reason), "detailsTr": true});
        if (r.running_changed.length > 0)
            c.restartShown = true;
    } else if (r.running_changed.length > 0 && !c.restartShown) {
        c.restartShown = true;
        toasts.push({"level": "info", "text": "Restart your browser to apply Browser Glass", "details": ""});
    }
    _warningToasts(r.warnings, c, toasts);
    return {"toasts": toasts, "ctx": c};
}

// What to do with a status (parseStatus()'s value). {poll, resync, toasts, ctx}
//   poll    keep polling status every POLL_INTERVAL_MS (restart_needed)
//   resync  run sync now: the niri rule is stale (once per stale episode,
//           so a sync that cannot drop it does not loop)
function statusDecision(parsed, ctx) {
    var c = _copyCtx(ctx);
    var toasts = [];
    if (!parsed || !parsed.ok)
        return {"poll": false, "resync": false, "toasts": toasts, "ctx": c};
    if (!parsed.restartNeeded)
        c.restartShown = false;
    var resync = false;
    if (parsed.stale) {
        if (!c.staleResync) {
            c.staleResync = true;
            resync = true;
        }
    } else {
        c.staleResync = false;
    }
    _warningToasts(parsed.status.warnings, c, toasts);
    return {"poll": parsed.restartNeeded, "resync": resync, "toasts": toasts, "ctx": c};
}

// ---------------------------------------------------------------------------
// Clipboard exclusion
// ---------------------------------------------------------------------------

// The host of a URL or bare host in `text` ("" when it holds none): scheme,
// user info, port, path and a leading "www." dropped, lowercase. Only
// http(s) URLs and bare hosts count (no about:, file:...). A backslash ends
// the host, as a slash does (browsers read one so); the host keeps only
// letters, digits, dots and hyphens (non-ASCII letters included, for
// internationalised names), each label starting and ending with neither.
function hostFromText(text) {
    var t = String(text || "").trim();
    if (!t || /\s/.test(t))
        return "";
    var m = /^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$/.exec(t);
    if (m) {
        var scheme = m[1].toLowerCase();
        if (scheme !== "http" && scheme !== "https") {
            // "example.com:8080/x" has no scheme, only a port
            if (!/^\d/.test(m[2]))
                return "";
        } else {
            if (m[2].indexOf("//") !== 0)
                return "";
            t = m[2].slice(2);
        }
    }
    t = t.split(/[\/\\?#]/)[0];
    var at = t.lastIndexOf("@");
    if (at >= 0)
        t = t.slice(at + 1);
    t = t.replace(/:\d*$/, "").replace(/\.$/, "").toLowerCase();
    if (t.indexOf("www.") === 0)
        t = t.slice(4);
    if (t.indexOf(".") < 0 || !/^[a-z0-9.\-\u0080-\uffff]+$/.test(t))
        return "";
    var labels = t.split(".");
    for (var i = 0; i < labels.length; i++) {
        if (!labels[i] || /^-|-$/.test(labels[i]))
            return "";
    }
    return t;
}

// Adds the clipboard's host to the excludedSites list (pluginData shape
// [{domain}]). {ok, domain, list, reason}: reason "added", "already" (the
// host or a parent domain is listed: exclusions cover subdomains) or
// "invalid"; list is the new list (unchanged unless added).
function excludeFromClipboard(text, excludedSites) {
    var list = Array.isArray(excludedSites) ? excludedSites.slice() : [];
    var host = hostFromText(text);
    if (!host)
        return {"ok": false, "domain": "", "list": list, "reason": "invalid"};
    var current = _items(list, "domain").map(function (d) {
        var low = String(d).trim().toLowerCase().replace(/\.$/, "");
        return low.indexOf("www.") === 0 ? low.slice(4) : low;
    });
    for (var i = 0; i < current.length; i++) {
        var d = current[i];
        if (d && (host === d || host.slice(-(d.length + 1)) === "." + d))
            return {"ok": true, "domain": host, "list": list, "reason": "already"};
    }
    list.push({"domain": host});
    return {"ok": true, "domain": host, "list": list, "reason": "added"};
}

// ---------------------------------------------------------------------------
// Teardown
// ---------------------------------------------------------------------------

// What to do when the daemon is destroyed. "sweep": plugin.json is gone (the
// folder may have been deleted): after a grace period, uninstall from the
// script text kept in memory and drop the plugin_settings.json entry. "uninstall": the plugin was disabled
// (enabled === false): run the script's uninstall. "none": the shell quits
// or reloads the plugin.
function teardownAction(enabledSetting, manifestPresent, haveScriptText) {
    if (!manifestPresent)
        return haveScriptText ? "sweep" : "none";
    return enabledSetting === false ? "uninstall" : "none";
}

// pluginSettings without the plugin's entry, or null when it has none
function withoutPlugin(pluginSettings, pluginId) {
    if (!_isObject(pluginSettings) || !Object.prototype.hasOwnProperty.call(pluginSettings, pluginId))
        return null;
    var next = JSON.parse(JSON.stringify(pluginSettings));
    delete next[pluginId];
    return next;
}

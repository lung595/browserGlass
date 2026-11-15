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
//   lookupSite()  siteFor()  glassCommand(cmd)  launcherAction(a)
//   (the launcher's, components/launcher.js)
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
//   liveControl      bool, default true (companion add-on, live exclusions)
//   darkPages        bool, default true (companion add-on darkens light pages)
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
// syncToasts()'s restart toast text (isRestartToast())
var RESTART_TEXT = "Restart your browser to apply Browser Glass";
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
    "privateGlass": true,
    "liveControl": true,
    "darkPages": true
};
var SITE_THEMES = ["follow", "dark", "none"];
var BOOL_KEYS = ["glassEnabled", "opacityOverride", "pagesTransparent", "genericStyle",
    "newTabGlass", "readerOpaque", "privateGlass", "liveControl", "darkPages"];

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
        "readerOpaque", "privateGlass", "liveControl", "darkPages"];
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

// Where the daemon writes the --settings JSON for the next sync, which
// reads it and deletes it (`sync --settings-file`): the excluded sites never
// go in an argv, which every local user can read in /proc/PID/cmdline.
// $XDG_RUNTIME_DIR is the user's own folder (mode 700). "" without an
// absolute runtime folder: the JSON goes in the argv then (--settings).
// Same name as browserglass.py SYNC_SETTINGS_NAME: uninstall removes a file
// no sync read.
var SETTINGS_FILE_NAME = "browserGlass-sync-settings.json";
function settingsFilePath(runtimeDir) {
    var dir = String(runtimeDir || "").replace(/\/+$/, "");
    return dir.charAt(0) === "/" ? dir + "/" + SETTINGS_FILE_NAME : "";
}

// --settings-file FILE (settingsFilePath()), or --settings with the JSON
// when there is no file. --if-plugin: the script refuses ("plugin_gone:")
// when plugin.json is gone or plugin_settings.json has the plugin disabled,
// so a sync started just before the folder was deleted, or the plugin
// disabled, writes nothing back after the uninstall. --plugin-dir: where
// the companion add-on and the native host wrapper come from (live control).
function syncArgv(pluginDir, settingsText, settingsFile) {
    var input = settingsFile ? ["--settings-file", settingsFile] : ["--settings", settingsText];
    return ["python3", "-I", scriptPath(pluginDir), "sync", "--data", dataDir(pluginDir)].concat(input,
        ["--if-plugin", manifestPath(pluginDir), "--plugin-dir", _dir(pluginDir)]);
}
// The site a niri window shows (w: {id, pid, app_id}). The title never goes
// in the argv (every local user can read it in /proc/PID/cmdline): the
// script asks niri for the title of window --window-id. The "--opt=value"
// form keeps an app-id that starts with "-" a value.
function activeSiteArgv(pluginDir, w) {
    var win = w || {};
    var id = parseInt(win.id, 10);
    return ["python3", "-I", scriptPath(pluginDir), "active-site", "--json",
        "--pid=" + (parseInt(win.pid, 10) || 0), "--app-id=" + String(win.app_id || ""),
        "--window-id=" + (isNaN(id) ? -1 : id), "--data", dataDir(pluginDir)];
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
// sweep handles it), or the plugin is disabled (its uninstall runs), so this
// is not an error worth a toast
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
    var live = _isObject(doc.live) ? doc.live : {};
    var r = {
        "glass": doc.glass,
        "opacity": typeof doc.opacity === "number" ? doc.opacity : 0,
        "reason": typeof doc.reason === "string" ? doc.reason : "",
        "first_run": doc.first_run === true,
        "changed": Array.isArray(doc.changed) ? doc.changed : [],
        "running_changed": Array.isArray(doc.running_changed) ? doc.running_changed : [],
        "niri_changed": doc.niri_changed === true,
        "warnings": Array.isArray(doc.warnings) ? doc.warnings.filter(_isObject) : [],
        "live": {"hosts": _count(live.hosts), "acked": _count(live.acked)},
        "companion": Array.isArray(doc.companion) ? doc.companion.filter(_isObject) : []
    };
    return {"ok": true, "result": r, "error": ""};
}

function _count(v) {
    return typeof v === "number" && v > 0 ? Math.floor(v) : 0;
}

// The active-site answers (contract spec "active_site")
var SITE_ERRORS = ["no_browser", "private", "not_web", "no_session", "ambiguous", "unsupported", "outdated"];

// {host, domain, source, age} or {error}: one of SITE_ERRORS, or "failed"
// (the command failed or answered something else)
function parseActiveSite(stdout, exitCode) {
    if (exitCode !== 0)
        return {"error": "failed"};
    var doc = parseJsonLine(stdout);
    if (!_isObject(doc))
        return {"error": "failed"};
    if (typeof doc.error === "string")
        return {"error": SITE_ERRORS.indexOf(doc.error) >= 0 ? doc.error : "failed"};
    if (typeof doc.host !== "string" || !doc.host || typeof doc.domain !== "string" || !doc.domain)
        return {"error": "failed"};
    return {
        "host": doc.host,
        "domain": doc.domain,
        "source": doc.source === "companion" ? "companion" : "session",
        "age": typeof doc.age === "number" ? doc.age : null
    };
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
    case "signed_xpi_unusable":
        return "The signed companion add-on could not be used: the unsigned one is used instead";
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
//   urgent  the pending (dirty) sync must run without debounce (a launcher
//           command, syncRequestNow())

function newSyncBook() {
    return {"phase": "idle", "scheduledAt": 0, "dirty": false, "reasons": [], "busyRetries": 0, "urgent": false};
}

function _copyBook(book) {
    var b = book || newSyncBook();
    return {
        "phase": b.phase || "idle",
        "scheduledAt": b.scheduledAt || 0,
        "dirty": b.dirty === true,
        "reasons": Array.isArray(b.reasons) ? b.reasons.slice() : [],
        "busyRetries": b.busyRetries || 0,
        "urgent": b.urgent === true
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

// A sync is asked for at once (a launcher command: no debounce). {book,
// schedule}: schedule true means call Proc.runCommand now with no wait
// (nothing launched yet: a pending debounced request is restarted); else the
// sync may be running and an urgent one follows it.
function syncRequestNow(book, reason, now) {
    var b = _copyBook(book);
    if (reason && b.reasons.indexOf(reason) < 0)
        b.reasons.push(reason);
    b.busyRetries = 0;
    var since = now - b.scheduledAt;
    if (since < 0)
        since = SYNC_DEBOUNCE_MS;
    if (b.phase === "scheduled" && since >= SYNC_DEBOUNCE_MS * DEBOUNCE_SAFETY) {
        b.dirty = true;
        b.urgent = true;
        return {"book": b, "schedule": false};
    }
    b.phase = "scheduled";
    // It launches at once: a later request must count it as running
    b.scheduledAt = now - SYNC_DEBOUNCE_MS;
    return {"book": b, "schedule": true};
}

// The sync callback came back. busy: it failed on the state lock.
// {book, schedule, retry, urgent}: schedule true means run another sync now
// (a request came meanwhile, or a lock retry); retry true when it is a lock
// retry (the daemon uses BUSY_RETRY_MS as its debounce); urgent true when
// the request that came is a launcher command's (no debounce).
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
        var urgent = wasDirty && b.urgent;
        b.dirty = false;
        b.urgent = false;
        b.phase = "scheduled";
        b.scheduledAt = urgent ? now - SYNC_DEBOUNCE_MS : now;
        return {"book": b, "schedule": true, "retry": retry && !wasDirty, "urgent": urgent};
    }
    b.reasons = [];
    b.urgent = false;
    return {"book": b, "schedule": false, "retry": false, "urgent": false};
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

// True for syncToasts()'s restart toast (a launcher command's own toast
// replaces it)
function isRestartToast(toast) {
    return _isObject(toast) && toast.text === RESTART_TEXT;
}

// The status line of live control (status.companion.state)
function liveStatusText(state) {
    switch (state) {
    case "connected":
        return "Live control: connected";
    case "waiting_restart":
        return "Live control: waiting for a browser restart";
    case "outdated":
        return "Live control: restart the browser once more";
    case "unavailable":
        return "Live control: not available for these browsers; changes apply at the next restart";
    case "disabled":
        return "Live control: the add-on is disabled in the browser; enable it in about:addons";
    case "removed":
        return "Live control: the add-on was removed in the browser; turn Live control off and on to add it back";
    default:
        return "Live control: off";
    }
}

// True when a profile the last sync (parseSync()'s result) left
// pending_restart is installed (or disabled) in `status` (parseStatus()'s
// status): the browser registered the add-on since, and one sync records
// it, so a removal in about:addons that follows is not read as the
// browser's signing refusal. That sync says installed or disabled: it does
// not repeat.
function companionLoaded(lastSync, status) {
    if (!_isObject(lastSync) || !Array.isArray(lastSync.companion) || !_isObject(status) || !Array.isArray(status.browsers))
        return false;
    var pending = {};
    lastSync.companion.forEach(function (c) {
        if (_isObject(c) && c.state === "pending_restart" && typeof c.profile === "string")
            pending[c.profile] = true;
    });
    return status.browsers.some(function (b) {
        return _isObject(b) && Array.isArray(b.profiles) && b.profiles.some(function (p) {
            return _isObject(p) && (p.companion === "installed" || p.companion === "disabled") && pending[p.id] === true;
        });
    });
}

// True when the --settings texts `before` and `after` (settingsJson())
// differ in liveControl; false when either cannot be read
function liveControlChanged(before, after) {
    var a = parseJson(before);
    var b = parseJson(after);
    return _isObject(a) && _isObject(b) && a.liveControl !== b.liveControl;
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

var _IDEOGRAPHIC_DOTS = /[。．｡]/g;
var _DOMAIN_LABEL = /^[a-z0-9-]{1,63}$/;
var _NON_ASCII = /[^\x00-\x7f]/;

// The code points of `text`, or null when it holds a lone surrogate (the
// engine's Array.from() splits a string in UTF-16 units)
function _codePoints(text) {
    var out = [];
    for (var i = 0; i < text.length; i++) {
        var c = text.charCodeAt(i);
        if (c >= 0xd800 && c <= 0xdbff) {
            var low = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
            if (low < 0xdc00 || low > 0xdfff)
                return null;
            out.push((c - 0xd800) * 0x400 + (low - 0xdc00) + 0x10000);
            i++;
        } else if (c >= 0xdc00 && c <= 0xdfff) {
            return null;
        } else {
            out.push(c);
        }
    }
    return out;
}

function _punyDigit(d) {
    return String.fromCharCode(d < 26 ? 97 + d : 22 + d);
}

function _punyAdapt(delta, points, first) {
    var d = first ? Math.floor(delta / 700) : Math.floor(delta / 2);
    d += Math.floor(d / points);
    var k = 0;
    while (d > 455) {
        d = Math.floor(d / 35);
        k += 36;
    }
    return k + Math.floor(36 * d / (d + 38));
}

// RFC 3492 Punycode of one label (Python's "punycode" codec), "" for a
// label with a lone surrogate
function _punycode(label) {
    var cps = _codePoints(label);
    if (cps === null)
        return "";
    var out = "";
    for (var i = 0; i < cps.length; i++) {
        if (cps[i] < 128)
            out += String.fromCharCode(cps[i]);
    }
    var b = out.length;
    var h = b;
    if (b > 0)
        out += "-";
    var n = 128, delta = 0, bias = 72;
    while (h < cps.length) {
        var m = 0x110000;
        for (var j = 0; j < cps.length; j++) {
            if (cps[j] >= n && cps[j] < m)
                m = cps[j];
        }
        delta += (m - n) * (h + 1);
        n = m;
        for (var x = 0; x < cps.length; x++) {
            if (cps[x] < n)
                delta++;
            if (cps[x] !== n)
                continue;
            var q = delta;
            for (var k = 36; ; k += 36) {
                var t = k <= bias ? 1 : (k >= bias + 26 ? 26 : k - bias);
                if (q < t)
                    break;
                out += _punyDigit(t + (q - t) % (36 - t));
                q = Math.floor((q - t) / (36 - t));
            }
            out += _punyDigit(q);
            bias = _punyAdapt(delta, h + 1, h === b);
            delta = 0;
            h++;
        }
        delta++;
        n++;
    }
    return out;
}

// A domain as the exclusion list compares it, the way browserglass.py
// normalize_domain() reads an excludedSites entry: the bare host of a domain
// or URL ("https://user@Sub.Example.com:8080/path?q" -> "sub.example.com"),
// without a leading "*." or the dots around it, lowercase, an
// internationalised name in its "xn--" form; "" when it is no usable host
// (Python's None). A leading "www." is kept, as Python keeps it:
// "www.example.com" covers that host only, and the registrable domain
// "www.gov.uk" must never turn into the public suffix "gov.uk".
function normDomain(text) {
    if (typeof text !== "string")
        return "";
    var host = text.trim();
    var scheme = host.indexOf("://");
    if (scheme >= 0)
        host = host.slice(scheme + 3);
    host = host.split(/[\/?#]/)[0];
    host = host.slice(host.lastIndexOf("@") + 1);
    if (host.charAt(0) === "[")
        return "";
    host = host.normalize("NFKC").toLowerCase().normalize("NFC").replace(_IDEOGRAPHIC_DOTS, ".");
    host = host.split(":")[0].replace(/^\.+|\.+$/g, "");
    while (host.indexOf("*.") === 0)
        host = host.slice(2);
    if (_NON_ASCII.test(host)) {
        var labels = host.split(".");
        for (var i = 0; i < labels.length; i++) {
            if (!_NON_ASCII.test(labels[i]))
                continue;
            var code = _punycode(labels[i]);
            if (!code)
                return "";
            labels[i] = "xn--" + code;
        }
        host = labels.join(".");
    }
    if (!host || host.length > 253)
        return "";
    var parts = host.split(".");
    for (var p = 0; p < parts.length; p++) {
        if (!_DOMAIN_LABEL.test(parts[p]))
            return "";
    }
    return host;
}

// Second-level labels that ccTLDs commonly sell under ("co.uk", "gov.au")
var _SUFFIX_LABELS = ["ac", "co", "com", "edu", "go", "gob", "gouv", "gov", "govt", "ltd",
    "mil", "ne", "net", "nhs", "nic", "or", "org", "plc", "police", "sch"];

// No Public Suffix List here: a single label, or "gov.uk"-like names, are
// treated as public suffixes
function _looksLikeSuffix(host) {
    var labels = host.split(".");
    if (labels.length < 2)
        return true;
    return labels.length === 2 && /^[a-z]{2}$/.test(labels[1]) && _SUFFIX_LABELS.indexOf(labels[0]) >= 0;
}

// The host of a URL or bare host in `text` ("" when it holds none): scheme,
// user info, port, path and a leading "www." dropped (kept when what
// remains looks like a public suffix: "www.gov.uk"), lowercase. Only
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
    if (t.indexOf("www.") === 0 && !_looksLikeSuffix(t.slice(4)))
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
    var h = normDomain(host);
    if (!h)
        return {"ok": false, "domain": "", "list": list, "reason": "invalid"};
    // Stored entries are compared the way the backend reads them
    // (normDomain keeps "www."): "www.x.com" covers that host and its
    // subdomains, not x.com, so only the exact entry or a parent domain makes
    // the copied host "already" listed. The copied host itself loses its
    // "www." (hostFromText) on purpose: the bare domain covers www. and every
    // other subdomain.
    var current = _items(list, "domain").map(normDomain);
    for (var i = 0; i < current.length; i++) {
        var d = current[i];
        if (d && (h === d || h.slice(-(d.length + 1)) === "." + d))
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

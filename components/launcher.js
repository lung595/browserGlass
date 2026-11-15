.pragma library
.import "logic.js" as Logic

// browserGlass launcher logic: pure functions, no QML object, no I/O.
// BrowserGlassLauncher.qml builds its items with them, and the daemon
// (BrowserGlassDaemon.qml launcherAction) decides with them what a command
// saves and which toasts it shows. The QML tests import this file directly.
// Every function returns new values and never mutates its arguments.
//
// The launcher runs without a trigger (the daemon saves noTrigger: true):
// DMS hands getItems() the raw query, and the plugin answers only when the
// first word is exactly "glass" or "gs", or in DMS's plugin view (the Browse
// entry of Browser Glass, the Plugins tab: fromPluginView()), where the bare
// words are the commands and "" lists them.
//
//   glass | gs              the five commands
//   gs on | off             glass on or off (setting glassEnabled)
//   gs blist | fix          exclude the current site (registrable domain)
//   gs unblist              put it back under glass
//   gs list [filter]        the excluded sites; Enter removes one
// A command word may be cut short: "gs b" is blist, "gs o" on and off.
//
// Texts are source strings for I18n.trFor (launcherText()); an item or a
// toast with a textArg/nameArg/commentArg/detailsArg fills "%1" with it.
//
// Item (what getItems() returns, DMS launcher shape plus bg* fields):
//   {id, name, comment, icon, keywords, _preScored, nameTr, nameArg,
//    commentArg, bgCmd, bgSite}
//   bgCmd   "on" | "off" | "blist" | "unblist" | "list" | "list-remove" | "none"
//   bgSite  the current site the item showed ({host, domain, source, age}),
//           null until it is known, or while it is provisional (the item
//           then runs by name and the daemon asks for the site again)
// Site (browserglass.py active-site --json, logic.js parseActiveSite()):
//   {host, domain, source: "companion" | "session", age: seconds | null}
//   or {error: SITE_ERRORS code, or "failed"}; the daemon's siteFor(true)
//   adds provisional: true to an older answer it shows while it asks again
// Action (launcherAction(a)): {kind: "on" | "off" | "blist" | "unblist" |
//   "list-remove", domain, host, source, age, error}

var PLUGIN_ID = "browserGlass";

// How long a current-site answer is reused, and how long an action waits
// for one before it gives up (ms)
var SITE_CACHE_MS = 3000;
var SITE_WAIT_MS = 2000;
// A site read from the session file older than this is mentioned (s)
var SESSION_AGE_NOTE_S = 10;
// What the launcher reopens on after a site is removed from the list
var LIST_QUERY = "glass list";
// DMS shows at most this many items of a plugin for a typed query
// (DLauncherV2 Controller _pluginQueryItems maxPerPlugin): a longer list
// shows one less and an item that tells how to reach the rest
var LIST_MAX = 10;

var COMMANDS = [
    {"cmd": "on", "alias": "", "icon": "material:blur_on"},
    {"cmd": "off", "alias": "", "icon": "material:blur_off"},
    {"cmd": "blist", "alias": "fix", "icon": "material:block"},
    {"cmd": "unblist", "alias": "", "icon": "material:undo"},
    {"cmd": "list", "alias": "", "icon": "material:list"}
];

// active-site error codes (contract spec "active_site")
var SITE_ERRORS = ["no_browser", "private", "not_web", "no_session", "ambiguous", "unsupported", "outdated"];

function _isObject(v) {
    return v !== null && typeof v === "object" && !Array.isArray(v);
}

// The source strings of the launcher, its toasts and refusals
function launcherText(key) {
    switch (key) {
    case "on":
        return "Glass on";
    case "off":
        return "Glass off";
    case "onNotShown":
        return "Glass on, but not shown";
    case "isOn":
        return "Glass is on";
    case "isOff":
        return "Glass is off";
    case "blist":
        return "Exclude the current site";
    case "unblist":
        return "Put the current site back under glass";
    case "list":
        return "Excluded sites";
    case "finding":
        return "Finding the current site…";
    case "withSubdomains":
        return "%1 — with its subdomains";
    case "isExcluded":
        return "%1 is excluded";
    case "alreadyExcluded":
        return "%1 is already excluded";
    case "notExcluded":
        return "%1 is not excluded";
    case "count0":
        return "No excluded sites";
    case "count1":
        return "Excluded: 1 site";
    case "countN":
        return "Excluded: %1 sites";
    case "removeHint":
        return "Enter: remove from the list";
    case "listMore":
        return "%1 more: type gs list <filter>";
    case "excluded":
        return "%1 excluded";
    case "excludedRestart":
        return "%1 excluded — applies after a restart";
    case "included":
        return "%1 back under glass";
    case "includedRestart":
        return "%1 back under glass — applies after a restart";
    case "sessionAge":
        return "from the session saved %1 ago";
    case "no_browser":
        return "No browser in the foreground";
    case "private":
        return "Private window: site not detected";
    case "not_web":
        return "Not a web page";
    case "no_session":
        return "Browser session unreadable";
    case "ambiguous":
        return "Current tab uncertain";
    case "unsupported":
        return "Address not supported";
    case "outdated":
        return "Restart the browser once more";
    case "retry":
        return "try again in a few seconds";
    default:
        return "Current site not found";
    }
}

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

// {word, rest} when the first word of `text` is "glass" or "gs" (any case),
// else null: "gsettings", "glassy", "gsx", "list" and "" are not ours.
// word is the command word, lowercase ("" when there is none); rest is the
// text after it.
function parseQuery(text) {
    var m = /^\s*(?:glass|gs)(?:\s+([\s\S]*))?$/i.exec(String(text === undefined || text === null ? "" : text));
    if (!m)
        return null;
    var after = (m[1] || "").trim();
    var cut = after.search(/\s/);
    var word = (cut < 0 ? after : after.slice(0, cut)).toLowerCase();
    var rest = cut < 0 ? "" : after.slice(cut).trim();
    return {"word": word, "rest": rest};
}

// The commands a word stands for: all for "", else those whose name or
// alias starts with it ("o" -> on, off; "f" -> blist)
function matchCommands(word) {
    var w = String(word || "").toLowerCase();
    return COMMANDS.filter(function (c) {
        return !w || c.cmd.indexOf(w) === 0 || (c.alias !== "" && c.alias.indexOf(w) === 0);
    });
}

// The one command a word names, for the IPC (`glass "blist"`): an exact
// name or alias, or a prefix only one command has; "" otherwise
function commandOf(word) {
    var w = String(word || "").trim().toLowerCase();
    if (!w)
        return "";
    for (var i = 0; i < COMMANDS.length; i++) {
        if (COMMANDS[i].cmd === w || COMMANDS[i].alias === w)
            return COMMANDS[i].cmd;
    }
    var found = matchCommands(w);
    return found.length === 1 ? found[0].cmd : "";
}

// True when the query lists the excluded sites ("gs list ...")
function isListQuery(q) {
    return q !== null && q !== undefined && q.word === "list";
}

// True when the items of `q` show the current site (blist or unblist)
function needsSite(q) {
    if (!q || isListQuery(q))
        return false;
    return matchCommands(q.word).some(function (c) {
        return c.cmd === "blist" || c.cmd === "unblist";
    });
}

// ---------------------------------------------------------------------------
// Excluded sites
// ---------------------------------------------------------------------------

// Shared with the clipboard exclusion (logic.js)
function normDomain(text) {
    return Logic.normDomain(text);
}

// The domain of one excludedSites entry ({domain} or a bare string), "" when
// it has none
function entryDomain(entry) {
    var text = _isObject(entry) ? entry.domain : entry;
    return typeof text === "string" ? normDomain(text) : "";
}

// The excluded domains, normalised, each once, in order
function excludedDomains(excludedSites) {
    var list = Array.isArray(excludedSites) ? excludedSites : [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
        var d = entryDomain(list[i]);
        if (d && out.indexOf(d) < 0)
            out.push(d);
    }
    return out;
}

// An exclusion covers its domain and every subdomain
function covers(entry, host) {
    var e = normDomain(entry);
    var h = normDomain(host);
    return e !== "" && h !== "" && (h === e || h.slice(-(e.length + 1)) === "." + e);
}

function _covered(domains, host) {
    return domains.some(function (d) {
        return covers(d, host);
    });
}

// The excluded domains that cover `host`, in list order
function _covering(domains, host) {
    return domains.filter(function (d) {
        return covers(d, host);
    });
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------

function _item(id, cmd, name, comment, icon, rank) {
    return {
        "id": "browserGlass:" + id,
        "name": name,
        "comment": comment,
        "icon": icon,
        "keywords": [],
        "_preScored": 1000 - rank,
        "nameTr": true,
        "nameArg": "",
        "commentArg": "",
        "bgCmd": cmd,
        "bgSite": null
    };
}

function _siteOk(site) {
    return _isObject(site) && typeof site.error !== "string" && typeof site.domain === "string" && site.domain !== "";
}

// The command items for `cmds` (matchCommands()). state:
//   site          the current site (null: not known yet)
//   excludedSites the pluginData list
//   glassEnabled  the glassEnabled setting
function commandItems(cmds, state) {
    var s = state || {};
    var domains = excludedDomains(s.excludedSites);
    var site = s.site === undefined ? null : s.site;
    var list = Array.isArray(cmds) ? cmds : [];
    var out = [];
    for (var i = 0; i < list.length; i++) {
        var c = list[i];
        var item = _item(c.cmd, c.cmd, launcherText(c.cmd), "", c.icon, i);
        item.keywords = c.alias ? [c.cmd, c.alias] : [c.cmd];
        if (c.cmd === "on" || c.cmd === "off") {
            item.comment = launcherText(s.glassEnabled === false ? "isOff" : "isOn");
        } else if (c.cmd === "list") {
            item.comment = launcherText(domains.length === 0 ? "count0" : (domains.length === 1 ? "count1" : "countN"));
            item.commentArg = domains.length > 1 ? String(domains.length) : "";
        } else if (site === null) {
            item.comment = launcherText("finding");
        } else if (!_siteOk(site)) {
            item.comment = launcherText(_isObject(site) ? site.error : "failed");
        } else {
            // unblist names the exclusions it removes, as its toast does (a
            // host-only entry is not the registrable domain)
            var listed = _covering(domains, site.host || site.domain);
            item.commentArg = site.domain;
            if (c.cmd === "blist") {
                item.comment = launcherText(_covered(domains, site.domain) ? "alreadyExcluded" : "withSubdomains");
            } else {
                item.comment = launcherText(listed.length > 0 ? "isExcluded" : "notExcluded");
                if (listed.length > 0)
                    item.commentArg = listed.join(", ");
            }
            if (site.provisional !== true)
                item.bgSite = {"host": site.host || site.domain, "domain": site.domain, "source": site.source || "", "age": typeof site.age === "number" ? site.age : null};
        }
        out.push(item);
    }
    return out;
}

// The items of "gs list [filter]": one per excluded site whose domain holds
// the filter (Enter removes it), or one item that does nothing when the
// list is empty. Past LIST_MAX, the first LIST_MAX - 1 and an item that
// does nothing: "N more: type gs list <filter>" (DMS shows at most LIST_MAX
// items of a plugin in its global search). `all`: every site, for DMS's
// plugin view, which shows them all.
function listItems(filter, excludedSites, all) {
    var domains = excludedDomains(excludedSites);
    if (domains.length === 0) {
        var empty = _item("list-empty", "none", launcherText("count0"), "", "material:info", 0);
        return [empty];
    }
    var f = String(filter || "").trim().toLowerCase();
    var shown = domains.filter(function (d) {
        return !f || d.indexOf(f) >= 0;
    });
    var count = shown.length > LIST_MAX && all !== true ? LIST_MAX - 1 : shown.length;
    var out = [];
    for (var i = 0; i < count; i++) {
        var item = _item("list:" + shown[i], "list-remove", shown[i], launcherText("removeHint"), "material:undo", i);
        item.nameTr = false;
        item.keywords = [shown[i]];
        item.bgSite = {"host": shown[i], "domain": shown[i], "source": "list", "age": null};
        out.push(item);
    }
    if (count < shown.length) {
        var more = _item("list-more", "none", launcherText("listMore"), "", "material:more_horiz", count);
        more.nameArg = String(shown.length - count);
        out.push(more);
    }
    return out;
}

// True when DMS's launcher asks from its plugin view: the Browse entry of
// Browser Glass (the view filtered to it) or the Plugins tab, where a query
// is typed for the plugins only. `stack` is the call stack text (new
// Error().stack) of getItems(): a call of the launcher's performSearch(),
// not of its plugin phase (the global search and the home page, which also
// asks with "") nor of its refresh of plugin results. DMS gives getItems()
// nothing else that tells them apart. An unknown stack is no plugin view.
function fromPluginView(stack) {
    var s = typeof stack === "string" ? stack : "";
    if (!/(^|\n)performSearch@[^\n]*Controller\.qml:/.test(s))
        return false;
    return !/(^|\n)(_performPluginPhase|_pluginQueryItems|_refreshPluginResults)@/.test(s);
}

// The query of a raw launcher text: "glass ..." or "gs ...", or, in the
// plugin view (fromPluginView()), the bare command words too ("" lists the
// commands, "on", "list x"); null when it is not ours
function queryFor(text, pluginView) {
    var q = parseQuery(text);
    if (q !== null || pluginView !== true)
        return q;
    var bare = String(text === undefined || text === null ? "" : text);
    return parseQuery("glass " + bare.replace(/^\s+/, ""));
}

// Every item for a raw launcher query ([] when it is not ours)
function itemsFor(text, state, pluginView) {
    var q = queryFor(text, pluginView);
    if (q === null)
        return [];
    var s = state || {};
    if (isListQuery(q))
        return listItems(q.rest, s.excludedSites, pluginView === true);
    return commandItems(matchCommands(q.word), s);
}

// ---------------------------------------------------------------------------
// Actions and toasts
// ---------------------------------------------------------------------------
// A toast is {level, text, textArg, details, detailsTr, detailsArg}: text
// (and details when detailsTr) are source strings; the args fill "%1".

function _toast(level, key, arg) {
    var text = launcherText(key);
    return {"level": level, "text": text, "textArg": arg === undefined ? "" : String(arg), "details": "", "detailsTr": false, "detailsArg": ""};
}

// The warning for a site that could not be told (an active-site error)
function refusalToast(error) {
    var code = SITE_ERRORS.indexOf(error) >= 0 ? error : "failed";
    var t = _toast("warning", code);
    if (code === "failed") {
        var hint = launcherText("retry");
        t.details = hint;
        t.detailsTr = true;
    }
    return t;
}

// What an action does, from the current excludedSites:
//   {save: null | {key, value}, toasts: [now], pending: null | {kind,
//    domain, source, age, on}, reopen}
// save is written to the plugin data (then a sync runs at once); pending is
// the toast to resolve once that sync is done (toastFor()); reopen asks to
// show "glass list" again.
function planAction(a, excludedSites) {
    var plan = {"save": null, "toasts": [], "pending": null, "reopen": false};
    var act = _isObject(a) ? a : {};
    var list = Array.isArray(excludedSites) ? excludedSites.slice() : [];
    var domains = excludedDomains(list);
    var kind = act.kind;
    if (kind === "on" || kind === "off") {
        plan.save = {"key": "glassEnabled", "value": kind === "on"};
        plan.pending = {"kind": "glass", "on": kind === "on", "domain": "", "source": "", "age": null};
        return plan;
    }
    if (kind !== "blist" && kind !== "unblist" && kind !== "list-remove") {
        plan.toasts.push(refusalToast("failed"));
        return plan;
    }
    if (typeof act.error === "string" && act.error) {
        plan.toasts.push(refusalToast(act.error));
        return plan;
    }
    var domain = normDomain(act.domain);
    if (!domain) {
        plan.toasts.push(refusalToast("failed"));
        return plan;
    }
    var source = typeof act.source === "string" ? act.source : "";
    var age = typeof act.age === "number" ? act.age : null;
    if (kind === "blist") {
        if (_covered(domains, domain)) {
            plan.toasts.push(_toast("info", "alreadyExcluded", domain));
            return plan;
        }
        plan.save = {"key": "excludedSites", "value": list.concat([{"domain": domain}])};
        plan.pending = {"kind": "exclude", "domain": domain, "source": source, "age": age};
        return plan;
    }
    var host = kind === "unblist" ? normDomain(act.host || domain) : domain;
    var kept = list.filter(function (e) {
        var d = entryDomain(e);
        return kind === "unblist" ? !covers(d, host) : d !== domain;
    });
    plan.reopen = kind === "list-remove";
    if (kept.length === list.length) {
        plan.toasts.push(_toast("info", "notExcluded", domain));
        return plan;
    }
    // The toast names the exclusions removed, not the registrable domain
    var removed = kind === "unblist" ? _covering(domains, host).join(", ") : domain;
    plan.save = {"key": "excludedSites", "value": kept};
    plan.pending = {"kind": "include", "domain": removed, "source": source, "age": age};
    return plan;
}

// The toast for a pending action once its sync is done (parseSync()'s
// outcome), or null (a failed sync shows its own error toast). It applied
// live when the add-on of a browser acknowledged the new list, the site came
// from the add-on (or the list) and live control is on. "gs on" while the
// sync says glass is still off (DMS blur off, opacity 100%...) warns why.
function toastFor(pending, outcome, liveControl) {
    if (!_isObject(pending) || !outcome || !outcome.ok)
        return null;
    if (pending.kind === "glass") {
        var r = _isObject(outcome.result) ? outcome.result : {};
        if (pending.on && r.glass === false) {
            var w = _toast("warning", "onNotShown");
            w.details = Logic.reasonText(r.reason);
            w.detailsTr = true;
            return w;
        }
        return _toast("info", pending.on ? "on" : "off");
    }
    var live = outcome.result && _isObject(outcome.result.live) ? outcome.result.live : {};
    var applied = liveControl !== false && (live.acked || 0) > 0 && (pending.source === "companion" || pending.source === "list");
    var key = pending.kind === "exclude" ? (applied ? "excluded" : "excludedRestart") : (applied ? "included" : "includedRestart");
    var t = _toast("info", key, pending.domain);
    if (pending.source === "session" && typeof pending.age === "number" && pending.age > SESSION_AGE_NOTE_S) {
        var note = launcherText("sessionAge");
        t.details = note;
        t.detailsTr = true;
        t.detailsArg = Math.round(pending.age) + " s";
    }
    return t;
}

// True for a resolved site action toast (of toastFor()) that says itself a
// restart is needed: the sync's generic restart toast is left out then. A
// live one keeps it, as another change may still need the restart.
function replacesRestartToast(toast) {
    return _isObject(toast) && (toast.text === launcherText("excludedRestart") || toast.text === launcherText("includedRestart"));
}

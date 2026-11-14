import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import "components/logic.js" as Logic
import "components/keeper.js" as Keeper

// BrowserGlassDaemon.qml: what it runs (Proc records the argv instead of
// running it, and answers with the contract fixtures), when, and what it
// shows. Covers the sync debounce, the --settings text, the toasts, status
// polling while a browser must restart, the niri_rule_stale resync, the IPC
// commands and the teardown (disable -> uninstall, deleted folder -> sweep).
Item {
    id: root

    Harness {
        id: t
        timeoutMs: 60000
    }

    readonly property string dir: "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass"
    readonly property string manifest: dir + "/plugin.json"
    readonly property string scriptPath: dir + "/browserglass.py"
    readonly property string rulesPath: "/tmp/fakehome/.config/niri/dms/windowrules.kdl"
    readonly property string colorsPath: "/tmp/fakehome/.cache/dms/dms-colors.json"
    readonly property string syncId: "browserGlass.sync"
    readonly property string statusId: "browserGlass.status"
    readonly property string sitesId: "browserGlass.sites"
    readonly property string reportId: "browserGlass.report"
    readonly property string pasteId: "browserGlass.paste"
    readonly property string busyText: "another browserGlass command holds the state lock; try again"

    property string script: ""
    property var fx: ({})
    property var d: null
    // State carried from one step to the next
    property int mark: 0

    Component {
        id: daemonComponent
        BrowserGlassDaemon {
            pluginId: "browserGlass"
            pluginService: PluginService
        }
    }

    // A clean shell, then a daemon. manual: nothing launches until
    // Proc.flush() (otherwise Proc's debounce timers run, as in DMS)
    function fresh(manual) {
        Proc.reset();
        Proc.autoRun = !manual;
        ProcessLog.reset();
        ToastService.reset();
        Quickshell.reset();
        PluginService.reset();
        SettingsData.reset();
        SessionData.isLightMode = false;
        SettingsData.pluginSettings = {
            "browserGlass": {
                "enabled": true
            }
        };
        FileViewLog.reset();
        FileViewLog.put(root.manifest, "{\"id\": \"browserGlass\"}\n");
        FileViewLog.put(root.scriptPath, root.script);
        FileViewLog.put(root.rulesPath, "window-rule {\n    opacity 0.9\n}\n");
        FileViewLog.put(root.colorsPath, "{}\n");
        PluginService.pluginPaths = {
            "browserGlass": root.dir + "/"
        };
        Proc.setResult(root.syncId, root.fx.sync, 0);
        Proc.setResult(root.statusId, root.fx.status, 0);
        Proc.setResult(root.sitesId, root.fx.sites, 0);
        root.d = daemonComponent.createObject(root);
        return root.d;
    }

    function settingsOf(command) {
        return JSON.parse(command[command.indexOf("--settings") + 1]);
    }
    function syncs() {
        return Proc.commandsFor(root.syncId);
    }
    function syncCalls() {
        return Proc.calls.filter(c => c.id === root.syncId);
    }
    // Every shared-variable write (each one notifies every reader)
    property int gvWrites: 0
    Connections {
        target: PluginService
        function onGlobalVarChanged(pluginId, varName) {
            root.gvWrites++;
        }
    }

    function gv(name) {
        const vars = PluginService.globalVars.browserGlass || {};
        return vars[name];
    }
    function defaults(changes) {
        return Object.assign(JSON.parse(root.fx.settings), changes || {});
    }
    // The status fixture with other warnings and restart_needed
    function statusWith(restartNeeded, warnings) {
        const s = JSON.parse(root.fx.status);
        s.restart_needed = restartNeeded;
        s.warnings = warnings;
        return JSON.stringify(s, null, 2);
    }
    function stale() {
        return [{
                "code": "niri_rule_stale",
                "message": "The niri rule is stale."
            }];
    }
    function save(key, value) {
        PluginService.savePluginData("browserGlass", key, value);
    }

    Component.onCompleted: {
        root.script = t.readFile("browserglass.py");
        root.fx = {
            "sync": t.readFile("contract/sync.json"),
            "noop": t.readFile("contract/sync-noop.json"),
            "status": t.readFile("contract/status.json"),
            "sites": t.readFile("contract/sites.json"),
            "error": t.readFile("contract/error.json"),
            "settings": t.readFile("contract/settings-default.json")
        };
        t.steps([
            // --- Debounce, with Proc's own timers ------------------------------
            {
                "run": () => {
                    t.ok("fixtures read", root.script.length > 0 && root.fx.sync && root.fx.status && root.fx.settings);
                    root.fresh(false);
                    t.check("the plugin folder comes from PluginService", root.d.pluginDir, root.dir);
                    t.check("a start sync is asked for with the 800 ms debounce", root.syncCalls().map(c => [c.debounceMs, c.timeoutMs]), [[800, 60000]]);
                    t.check("syncing is shared", root.gv("syncing"), true);
                    // Several changes while it waits
                    root.save("opacity", 60);
                    SettingsData.blurEnabled = false;
                }
            },
            {
                "wait": 150,
                "run": () => {
                    SessionData.isLightMode = true;
                    root.save("opacity", 70);
                    FileViewLog.change(root.rulesPath, "window-rule {\n    opacity 0.8\n}\n");
                }
            },
            {
                "wait": 150,
                "run": () => {
                    FileViewLog.change(root.colorsPath, "{\"dark\": {}}\n");
                    t.check("nothing ran yet", root.syncs().length, 0);
                    t.ok("each change restarted the one pending sync", root.syncCalls().length >= 5);
                }
            },
            {
                "wait": 1300,
                "run": () => {
                    t.check("several rapid changes -> one sync", root.syncs().length, 1);
                    const s = root.settingsOf(root.syncs()[0]);
                    t.check("it carries the last settings", s, root.defaults({
                        "blur": false,
                        "isLight": true,
                        "opacity": 0.7
                    }));
                    t.check("argv", root.syncs()[0], Logic.syncArgv(root.dir, JSON.stringify(s)));
                    t.check("then one status", Proc.commandsFor(root.statusId), [Logic.statusArgv(root.dir)]);
                    t.check("and the sites list once", Proc.commandsFor(root.sitesId), [Logic.sitesArgv(root.dir)]);
                    t.check("sites are shared", root.gv("sites"), JSON.parse(root.fx.sites).map(x => ({
                                "name": x.name,
                                "domains": x.domains
                            })));
                    t.check("syncing is over", root.gv("syncing"), false);
                    // A change after the sync ran: a sync of its own
                    root.save("siteTheme", "dark");
                }
            },
            {
                "wait": 1100,
                "run": () => {
                    t.check("a later change -> a second sync", root.syncs().length, 2);
                    t.check("with that change", root.settingsOf(root.syncs()[1]).siteTheme, "dark");
                    root.d.destroy();
                }
            },
            // --- Settings JSON ----------------------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    t.check("the start sync ran", root.syncs().length, 1);
                    const first = root.syncs()[0];
                    t.check("no setting yet: the contract defaults", root.settingsOf(first), JSON.parse(root.fx.settings));
                    t.check("keys in the contract's order", Object.keys(root.settingsOf(first)), Object.keys(JSON.parse(root.fx.settings)));
                    t.ok("--settings is compact JSON", first[first.indexOf("--settings") + 1].indexOf("\n") < 0);
                    Proc.flush();
                    root.mark = Proc.calls.length;
                    // SliderSetting saves its default (85) on load: same text, no sync
                    root.save("opacity", 85);
                    t.check("saving the default opacity runs nothing", Proc.calls.length, root.mark);
                    SettingsData.blurEnabled = true;
                    t.check("nor does an unchanged blur", Proc.calls.length, root.mark);
                    // The slider's percent becomes a 0..1 fraction
                    const seen = [];
                    for (const pct of [0, 1, 50, 100]) {
                        root.save("opacity", pct);
                        Proc.flush();
                        seen.push(root.settingsOf(Proc.lastCommand(root.syncId)).opacity);
                        Proc.flush();
                    }
                    t.check("percent slider -> 0..1 opacity", seen, [0, 0.01, 0.5, 1]);
                    root.save("opacityOverride", true);
                    root.save("excludedSites", [
                        {
                            "domain": " example.com "
                        },
                        {
                            "domain": "example.com"
                        },
                        {
                            "domain": "news.example.org"
                        }
                    ]);
                    root.save("disabledStyles", [
                        {
                            "name": "github.com"
                        }
                    ]);
                    root.save("newTabGlass", false);
                    SessionData.isLightMode = true;
                    Proc.flush();
                    t.check("lists, flags and mode reach --settings", root.settingsOf(Proc.lastCommand(root.syncId)), root.defaults({
                        "isLight": true,
                        "opacityOverride": true,
                        "opacity": 1,
                        "excluded": ["example.com", "news.example.org"],
                        "disabledStyles": ["github.com"],
                        "newTabGlass": false
                    }));
                    t.check("the enabled flag is not a sync setting", "enabled" in root.settingsOf(Proc.lastCommand(root.syncId)), false);
                    Proc.flush();
                    root.d.destroy();
                }
            },
            // --- Toasts and shared state -----------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    t.check("first run: the set-up toast, then the Zen warning", ToastService.log.map(x => [x.level, x.message]), [["info", "Browser Glass is set up: restart your browser to see the glass"], ["warning", "Zen transparency mod detected: it may stack with Browser Glass"]]);
                    t.check("toasts carry the plugin's category", ToastService.log.map(x => x.category), ["browserGlass", "browserGlass"]);
                    t.check("lastSync is shared", root.gv("lastSync"), Logic.parseSync(root.fx.sync, 0).result);
                    t.check("glassActive is shared", root.gv("glassActive"), true);
                    Proc.flush();
                    t.check("the same warning in status: no second toast", ToastService.log.length, 2);
                    t.check("status is shared", root.gv("status"), JSON.parse(root.fx.status));
                    t.check("restartNeeded is shared", [root.gv("restartNeeded"), root.d.restartNeeded], [true, true]);
                    t.check("no error", root.gv("lastError") ?? "", "");

                    // A sync that changes nothing: no toast
                    Proc.setResult(root.syncId, root.fx.noop, 0);
                    root.d.requestSync("test");
                    Proc.flush();
                    Proc.flush();
                    t.check("a no-op sync shows nothing", ToastService.log.length, 2);

                    // A failure: one toast per distinct error
                    Proc.setResult(root.syncId, root.fx.error, 2);
                    root.d.requestSync("test");
                    Proc.flush();
                    t.check("an error toast with the error text", ToastService.log.slice(2).map(x => [x.level, x.message, x.details]), [["error", "Browser Glass sync failed", "invalid --settings: expected a JSON object"]]);
                    t.check("lastError is shared", root.gv("lastError"), "invalid --settings: expected a JSON object");
                    Proc.flush();
                    root.d.requestSync("test");
                    Proc.flush();
                    Proc.flush();
                    t.check("the same error again: no second toast", ToastService.log.length, 3);

                    // The state lock: silent retries on a 2 s debounce, then one toast
                    Proc.setResult(root.syncId, JSON.stringify({
                        "error": root.busyText
                    }), 1);
                    root.mark = root.syncCalls().length;
                    root.d.requestSync("test");
                    Proc.flush();
                    Proc.flush();
                    Proc.flush();
                    t.check("busy: three retries, silent", ToastService.log.length, 3);
                    t.check("on the 2 s retry debounce", root.syncCalls().slice(root.mark + 1).map(c => c.debounceMs), [2000, 2000, 2000]);
                    Proc.flush();
                    t.check("still busy after them: one error toast", ToastService.log.slice(3).map(x => [x.level, x.details]), [["error", root.busyText]]);
                    t.check("and no more retries", Proc.isPending(root.syncId), false);

                    // Back to normal: the error clears
                    Proc.setResult(root.syncId, root.fx.noop, 0);
                    root.d.requestSync("test");
                    Proc.flush();
                    Proc.flush();
                    t.check("a good sync clears lastError", root.gv("lastError"), "");
                    t.check("and shows nothing", ToastService.log.length, 4);
                    root.d.destroy();
                }
            },
            // Translated toasts: the text always, the details only when they
            // are a source string (a reason), never an error text
            {
                "run": () => {
                    I18n.registerPluginTranslations("browserGlass", {
                        "Browser Glass is set up, but glass is off": {
                            "Browser Glass is set up, but glass is off": "Browser Glass est installé, mais le verre est éteint"
                        },
                        "DMS blur is off": {
                            "DMS blur is off": "Le flou DMS est désactivé"
                        },
                        "Browser Glass sync failed": {
                            "Browser Glass sync failed": "Échec de la synchronisation"
                        },
                        "invalid --settings: expected a JSON object": {
                            "invalid --settings: expected a JSON object": "NOT TRANSLATED"
                        }
                    });
                    root.fresh(true);
                    const doc = JSON.parse(root.fx.sync);
                    doc.glass = false;
                    doc.reason = "blur_disabled";
                    doc.warnings = [];
                    Proc.setResult(root.syncId, JSON.stringify(doc), 0);
                    Proc.flush();
                    t.check("first run with glass off: text and reason translated", ToastService.log.map(x => [x.level, x.message, x.details]), [["info", "Browser Glass est installé, mais le verre est éteint", "Le flou DMS est désactivé"]]);
                    Proc.flush();
                    Proc.setResult(root.syncId, root.fx.error, 2);
                    root.d.requestSync("test");
                    Proc.flush();
                    t.check("an error text stays as the CLI wrote it", ToastService.log.slice(-1).map(x => [x.message, x.details]), [["Échec de la synchronisation", "invalid --settings: expected a JSON object"]]);
                    I18n.unregisterPluginTranslations("browserGlass");
                    Proc.flush();
                    root.d.destroy();
                }
            },
            // --- Status polling ----------------------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.setResult(root.statusId, root.statusWith(false, []), 0);
                    Proc.flush();
                    Proc.flush();
                    t.check("no restart needed: no polling", root.d.polling, false);
                    // Something changed while a browser runs: status says restart
                    Proc.setResult(root.statusId, root.statusWith(true, []), 0);
                    root.d.requestSync("test");
                    Proc.flush();
                    Proc.flush();
                    t.check("restart_needed true: polling starts", root.d.polling, true);
                    t.check("no status pending yet", Proc.isPending(root.statusId), false);
                    root.mark = Proc.commandsFor(root.statusId).length;
                }
            },
            {
                "wait": Logic.POLL_INTERVAL_MS + 400,
                "run": () => {
                    t.check("a status is asked for every 10 s", Proc.isPending(root.statusId), true);
                    t.check("with the status argv", Proc.calls[Proc.calls.length - 1].command, Logic.statusArgv(root.dir));
                    t.check("nothing else", Proc.pendingIds(), [root.statusId]);
                    // The browser restarted
                    Proc.setResult(root.statusId, root.statusWith(false, []), 0);
                    Proc.flush();
                    t.check("restart_needed false: polling STOPS", root.d.polling, false);
                    t.check("restartNeeded is shared", root.gv("restartNeeded"), false);
                    root.mark = Proc.calls.length;
                }
            },
            {
                "wait": Logic.POLL_INTERVAL_MS + 400,
                "run": () => {
                    t.check("no status asked for once stopped", Proc.calls.length, root.mark);
                    t.check("nothing pending", Proc.pendingIds(), []);
                    // The same status again: no shared variable is rewritten
                    root.mark = root.gvWrites;
                    root.d.statusDone(root.statusWith(false, []), 0);
                    t.check("an unchanged status writes no shared variable", root.gvWrites, root.mark);
                    // A status that keeps failing while a restart is needed
                    root.d.statusDone(root.statusWith(true, []), 0);
                    t.check("polling again", root.d.polling, true);
                    root.d.statusDone("", 1);
                    root.d.statusDone("", 1);
                    t.check("two failures: still polling", root.d.polling, true);
                    root.d.statusDone("", 1);
                    t.check("MAX_STATUS_FAILURES failures in a row: polling stops", [root.d.polling, root.gv("restartNeeded")], [false, false]);
                    t.check("and the error is shared", root.gv("lastError") !== "", true);
                    root.d.statusDone(root.statusWith(true, []), 0);
                    root.d.statusDone("", 1);
                    t.check("a good status resets the count", root.d.polling, true);
                    root.d.destroy();
                }
            },
            // --- niri_rule_stale --------------------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.setResult(root.syncId, root.fx.noop, 0);
                    Proc.setResult(root.statusId, root.statusWith(false, root.stale()), 0);
                    Proc.flush();
                    t.check("one sync at start", root.syncs().length, 1);
                    Proc.flush();
                    t.check("a stale niri rule asks for a sync", Proc.isPending(root.syncId), true);
                    t.check("for that reason", root.d.book.reasons, ["niri_rule_stale"]);
                    Proc.flush();
                    t.check("the resync ran", root.syncs().length, 2);
                    Proc.flush();
                    t.check("still stale after it: no loop", Proc.isPending(root.syncId), false);
                    t.check("still two syncs", root.syncs().length, 2);
                    // The rule got fresh, then stale again: one more sync
                    Proc.setResult(root.statusId, root.statusWith(false, []), 0);
                    root.d.refreshStatus();
                    Proc.flush();
                    Proc.setResult(root.statusId, root.statusWith(false, root.stale()), 0);
                    root.d.refreshStatus();
                    Proc.flush();
                    t.check("a new stale episode: a sync again", Proc.isPending(root.syncId), true);
                    Proc.flush();
                    Proc.flush();
                    t.check("three syncs in all", root.syncs().length, 3);
                    t.check("no toast for it", ToastService.log.length, 0);
                    root.d.destroy();
                }
            },
            // --- IPC ----------------------------------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    t.check("status before any: an error object", JSON.parse(IpcRegistry.call("browserGlass", "status")), {
                        "error": "no status yet"
                    });
                    t.check("and it asks for one", Proc.isPending(root.statusId), true);
                    Proc.flush();
                    Proc.flush();
                    t.check("status: the last status as JSON", JSON.parse(IpcRegistry.call("browserGlass", "status")), JSON.parse(root.fx.status));
                    Proc.flush();

                    root.mark = root.syncs().length;
                    t.check("sync answers OK", IpcRegistry.call("browserGlass", "sync"), "OK");
                    Proc.flush();
                    t.check("and runs one sync", root.syncs().length, root.mark + 1);
                    t.check("with the sync argv", Proc.lastCommand(root.syncId), Logic.syncArgv(root.dir, Logic.settingsJson({}, true, false)));
                    Proc.flush();

                    t.check("toggle turns glass off", IpcRegistry.call("browserGlass", "toggle"), "glass off");
                    t.check("saved in the plugin settings", PluginService.saves[PluginService.saves.length - 1], ["browserGlass", "glassEnabled", false]);
                    Proc.flush();
                    t.check("and synced", root.settingsOf(Proc.lastCommand(root.syncId)).glassEnabled, false);
                    Proc.flush();
                    t.check("toggle again turns it on", IpcRegistry.call("browserGlass", "toggle"), "glass on");
                    Proc.flush();
                    t.check("and synced", root.settingsOf(Proc.lastCommand(root.syncId)).glassEnabled, true);
                    Proc.flush();

                    // PluginService.togglePlugin() calls the daemon's toggle()
                    t.check("toggle() turns glass off", root.d.toggle(), false);
                    t.check("saved like the IPC toggle", PluginService.saves[PluginService.saves.length - 1], ["browserGlass", "glassEnabled", false]);
                    Proc.flush();
                    Proc.flush();
                    t.check("toggle() again turns it on", root.d.toggle(), true);
                    Proc.flush();
                    Proc.flush();

                    // The settings page's status read: none while a sync is pending
                    root.d.requestSync("test");
                    t.check("a sync pending: no status read", root.d.refreshStatusIfIdle(), false);
                    Proc.flush();
                    Proc.flush();
                    root.mark = Proc.calls.filter(c => c.id === root.statusId).length;
                    t.check("idle: a status read", root.d.refreshStatusIfIdle(), true);
                    Proc.flush();
                    t.check("that runs one", Proc.calls.filter(c => c.id === root.statusId).length, root.mark + 1);

                    Proc.setResult(root.pasteId, "https://www.Example.com/some/page?q=1\n", 0);
                    t.check("excludeClipboard answers OK", IpcRegistry.call("browserGlass", "excludeClipboard"), "OK");
                    Proc.flush();
                    t.check("it reads the clipboard with dms cl paste", Proc.commandsFor(root.pasteId), [["dms", "cl", "paste"]]);
                    t.check("the host is saved", SettingsData.getPluginSetting("browserGlass", "excludedSites", []), [
                        {
                            "domain": "example.com"
                        }
                    ]);
                    t.check("one info toast naming it", ToastService.log.slice(-1).map(x => [x.level, x.message, x.details]), [["info", "Site excluded from glass", "example.com"]]);
                    Proc.flush();
                    t.check("and synced", root.settingsOf(Proc.lastCommand(root.syncId)).excluded, ["example.com"]);
                    Proc.flush();
                    IpcRegistry.call("browserGlass", "excludeClipboard");
                    Proc.flush();
                    t.check("again: already excluded", ToastService.log.slice(-1).map(x => [x.level, x.message]), [["info", "Site already excluded"]]);
                    t.check("not saved twice", SettingsData.getPluginSetting("browserGlass", "excludedSites", []).length, 1);
                    Proc.setResult(root.pasteId, "just some words", 0);
                    IpcRegistry.call("browserGlass", "excludeClipboard");
                    Proc.flush();
                    t.check("no address on the clipboard: a warning", ToastService.log.slice(-1).map(x => x.level), ["warning"]);
                    Proc.setResult(root.pasteId, "https://example.net/", 1);
                    IpcRegistry.call("browserGlass", "excludeClipboard");
                    Proc.flush();
                    t.check("a failed paste is not read", ToastService.log.slice(-1).map(x => x.level), ["warning"]);

                    Proc.setResult(root.reportId, "browserGlass report\nversion 1.0.0\n", 0);
                    t.check("report answers OK", IpcRegistry.call("browserGlass", "report"), "OK");
                    Proc.flush();
                    t.check("it runs the report argv", Proc.commandsFor(root.reportId), [Logic.reportArgv(root.dir)]);
                    t.check("and copies it with dms cl copy", Quickshell.detached, [["dms", "cl", "copy", "--", "browserGlass report\nversion 1.0.0\n"]]);
                    t.check("one info toast", ToastService.log.slice(-1).map(x => [x.level, x.message]), [["info", "Report copied to the clipboard"]]);
                    Proc.setResult(root.reportId, JSON.stringify({
                        "error": "boom"
                    }), 1);
                    IpcRegistry.call("browserGlass", "report");
                    Proc.flush();
                    t.check("a failed report: an error toast, nothing copied", [ToastService.log.slice(-1).map(x => [x.level, x.details]), Quickshell.detached.length], [[["error", "boom"]], 1]);
                    t.check("no call ever leaves the plugin folder or dms", Proc.launched.every(l => l.command[0] === "dms" || l.command[2].indexOf(root.dir + "/") === 0), true);
                    root.d.destroy();
                }
            },
            // --- Teardown ------------------------------------------------------------
            {
                "run": () => {
                    t.check("IPC handler gone with the daemon", IpcRegistry.call("browserGlass", "sync"), null);
                    // Shell reload or quit: enabled stays true
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    root.d.requestSync("pending at unload");
                    ToastService.reset();
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    t.check("every command id is released", Proc.released.slice().sort(), [root.pasteId, root.reportId, root.sitesId, root.statusId, root.syncId].sort());
                    t.check("a pending sync never runs after unload", [Proc.flush(), Proc.isPending(root.syncId)], [0, false]);
                    t.check("reload/quit: no uninstall", Quickshell.detached, []);
                    t.check("no sweep either", ProcessLog.runs.length, 0);
                    t.check("no toast", ToastService.log.length, 0);

                    // Disabled by the user: DMS sets enabled false, then unloads
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    ToastService.reset();
                    SettingsData.setPluginSetting("browserGlass", "enabled", false);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    t.check("disabled: onDestruction runs uninstall, detached", Quickshell.detached, [Logic.uninstallArgv(root.dir)]);
                    t.check("argv", Quickshell.detached[0], ["python3", "-I", root.scriptPath, "uninstall"]);
                    t.check("not the stdin sweep", ProcessLog.runs.length, 0);
                    t.check("one info toast", ToastService.log.map(x => [x.level, x.message]), [["info", "Browser Glass disabled: restoring the browsers"]]);
                    t.ok("the settings entry stays (DMS owns it)", SettingsData.pluginSettings.browserGlass !== undefined);

                    // The folder was deleted: the sweep uninstalls, not the daemon
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    ToastService.reset();
                    SettingsData.setPluginSetting("browserGlass", "enabled", false);
                    FileViewLog.remove(root.manifest);
                    FileViewLog.remove(root.scriptPath);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    t.check("deleted folder: no detached uninstall (the script is gone)", Quickshell.detached, []);
                    t.check("the sweep ran once", ProcessLog.runs.map(r => r.command), [Logic.sweepArgv(root.dir)]);
                    t.ok("with the script on stdin", ProcessLog.runs.length === 1 && ProcessLog.runs[0].stdin === root.script);
                    t.ok("the settings entry stays while it runs", SettingsData.pluginSettings.browserGlass !== undefined);
                    t.check("no toast yet", ToastService.log.length, 0);
                    const live = ProcessLog.alive().filter(p => p.running);
                    t.check("the sweep's process outlives the daemon", live.length, 1);
                    // Its creation context died with the plugin (the real
                    // Process is C++): raise the signal the real one would
                    for (const p of live)
                        p.exited(0, 0);
                }
            },
            {
                "wait": 50,
                "run": () => {
                    t.check("and goes once it exits", [ProcessLog.alive().length, Keeper.count()], [0, 0]);
                    t.check("then the settings entry is dropped", SettingsData.pluginSettings.browserGlass, undefined);
                    t.check("and one toast", ToastService.log.map(x => x.message), ["Browser Glass removed: browsers restored"]);
                    PluginService.pluginPaths = {};
                    Proc.reset();
                }
            }
        ]);
    }
}

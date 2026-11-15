import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import "components/logic.js" as Logic
import "components/keeper.js" as Keeper
import "components/launcher.js" as Launcher

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
    readonly property string runDir: "/tmp/fakehome/run"
    readonly property string runFile: runDir + "/browserGlass-sync-settings.json"
    readonly property string syncId: "browserGlass.sync"
    readonly property string statusId: "browserGlass.status"
    readonly property string sitesId: "browserGlass.sites"
    readonly property string reportId: "browserGlass.report"
    readonly property string pasteId: "browserGlass.paste"
    readonly property string siteId: "browserGlass.site"
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

    // The launcher as DMS loads it and DMS's launcher controller (call stacks)
    Component {
        id: launcherComponent
        BrowserGlassLauncher {
            pluginService: PluginService
        }
    }
    Component {
        id: controllerComponent
        Controller {}
    }

    // A clean shell, then a daemon. manual: nothing launches until
    // Proc.flush() (otherwise Proc's debounce timers run, as in DMS)
    function fresh(manual) {
        Proc.reset();
        Proc.autoRun = !manual;
        ProcessLog.reset();
        ToastService.reset();
        Quickshell.reset();
        Quickshell.environment = {
            "HOME": "/tmp/fakehome",
            "USER": "alice",
            "XDG_RUNTIME_DIR": root.runDir
        };
        PluginService.reset();
        PopoutService.reset();
        NiriService.reset();
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

    // The settings a launched sync read: its --settings-file as it was at
    // launch (or the --settings argument when there is no runtime dir)
    function settingsOf(command) {
        const at = command.indexOf("--settings");
        if (at >= 0)
            return JSON.parse(command[at + 1]);
        const l = Proc.launched.filter(x => x.command === command)[0];
        return l && typeof l.settingsFile === "string" ? JSON.parse(l.settingsFile) : null;
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
    // The sync fixture without its first run, with these live counts and
    // running_changed (what makes the restart toast)
    function syncWith(acked, runningChanged) {
        const s = JSON.parse(root.fx.noop);
        s.live = {
            "hosts": 1,
            "acked": acked
        };
        s.running_changed = runningChanged;
        return JSON.stringify(s);
    }
    function toasts() {
        return ToastService.log.map(x => [x.level, x.message]);
    }
    function browserWindow(title) {
        return [{
                "id": 3,
                "app_id": "firefox",
                "title": title,
                "pid": 4242,
                "is_focused": true
            }];
    }

    Component.onCompleted: {
        root.script = t.readFile("browserglass.py");
        root.fx = {
            "sync": t.readFile("contract/sync.json"),
            "noop": t.readFile("contract/sync-noop.json"),
            "status": t.readFile("contract/status.json"),
            "sites": t.readFile("contract/sites.json"),
            "error": t.readFile("contract/error.json"),
            "companion": t.readFile("contract/sync-companion.json"),
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
                    t.check("argv", root.syncs()[0], Logic.syncArgv(root.dir, JSON.stringify(s), root.runFile));
                    t.check("the settings file is read at launch, then gone", [Proc.launched.filter(l => l.id === root.syncId)[0].settingsFile, FileViewLog.has(root.runFile)], [JSON.stringify(s), false]);
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
                    t.check("with the sync argv", Proc.lastCommand(root.syncId), Logic.syncArgv(root.dir, Logic.settingsJson({}, true, false), root.runFile));
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
            // --- Launcher: noTrigger -------------------------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    t.check("noTrigger saved at start", PluginService.saves.filter(x => x[1] === "noTrigger"), [["browserGlass", "noTrigger", true]]);
                    t.check("and one start sync only", root.syncCalls().length, 1);
                    Proc.flush();
                    Proc.flush();
                    t.check("noTrigger is no sync input: still one sync", root.syncs().length, 1);
                    t.ok("noTrigger stays out of --settings", !("noTrigger" in root.settingsOf(root.syncs()[0])));
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    // A shell reload keeps the saved value (and a user's own)
                    PluginService.saves = [];
                    SettingsData.setPluginSetting("browserGlass", "noTrigger", false);
                    root.d = daemonComponent.createObject(root);
                    t.check("saved only once", PluginService.saves.filter(x => x[1] === "noTrigger"), []);
                    t.check("the user's value kept", SettingsData.getPluginSetting("browserGlass", "noTrigger", null), false);
                    root.d.destroy();
                }
            },
            // --- Sync: settings file, argv fallback, a failing result ---------------
            {
                "run": () => {
                    Quickshell.environment = {
                        "HOME": "/tmp/fakehome",
                        "USER": "alice"
                    };
                    Proc.reset();
                    Proc.autoRun = false;
                    FileViewLog.reset();
                    FileViewLog.put(root.manifest, "{\"id\": \"browserGlass\"}\n");
                    FileViewLog.put(root.scriptPath, root.script);
                    Proc.setResult(root.syncId, root.fx.sync, 0);
                    root.d = daemonComponent.createObject(root);
                    Proc.flush();
                    const argv = root.syncs()[0];
                    t.check("no runtime dir: the settings in argv", [argv.indexOf("--settings-file"), argv[argv.indexOf("--settings") + 1]], [-1, root.d.lastSettingsText]);
                    t.check("and no file written", FileViewLog.writes.filter(w => w[0].indexOf("sync-settings") >= 0), []);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    // Same settings again (a colours change, an IPC sync): the
                    // file the last sync deleted is written again
                    root.mark = Proc.launched.length;
                    root.d.requestSync("colors");
                    Proc.flush();
                    const again = Proc.launched.slice(root.mark).filter(l => l.id === root.syncId);
                    t.check("the same settings twice: the second sync reads its file", [again.length, again.length ? again[0].settingsFile : null], [1, root.d.lastSettingsText]);
                    // A failed write: this launch passes the settings in argv
                    FileViewLog.failing = [root.runFile];
                    root.d.requestSync("colors");
                    Proc.flush();
                    const argv = Proc.lastCommand(root.syncId);
                    t.check("the file cannot be written: the settings in argv", [argv.indexOf("--settings-file"), argv[argv.indexOf("--settings") + 1]], [-1, root.d.lastSettingsText]);
                    FileViewLog.failing = [];
                    root.d.requestSync("colors");
                    Proc.flush();
                    t.check("and the file again once it can be", Proc.lastCommand(root.syncId).indexOf("--settings-file") >= 0, true);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    // syncDone throws (a broken pending list): no warning, idle
                    root.d.pendingToasts = {
                        get length() {
                            throw new Error("boom");
                        }
                    };
                    root.d.requestSync("test");
                    Proc.flush();
                    t.check("a throwing result handler leaves the sync idle", [root.d.book, root.gv("syncing")], [Logic.newSyncBook(), false]);
                    root.d.pendingToasts = [];
                    root.mark = root.syncs().length;
                    root.d.requestSync("test");
                    Proc.flush();
                    t.check("and the next request syncs", root.syncs().length, root.mark + 1);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    ToastService.reset();
                    // A failed sync shows its error once
                    Proc.setResult(root.syncId, root.fx.error, 2);
                    root.d.requestSync("test");
                    Proc.flush();
                    t.check("a failed sync: its error toast", root.toasts(), [["error", "Browser Glass sync failed"]]);
                    // A launcher action whose sync fails the same way: saved,
                    // not applied, and said so once
                    ToastService.reset();
                    root.d.launcherAction({
                        "kind": "blist",
                        "host": "mail.proton.me",
                        "domain": "proton.me",
                        "source": "companion"
                    });
                    t.check("the action is saved", root.d.pluginData.excludedSites, [{
                            "domain": "proton.me"
                        }]);
                    Proc.flush();
                    t.check("the same error again after a launcher action: one error toast", ToastService.log.map(x => [x.level, x.message, x.details]), [["error", "Browser Glass sync failed", "invalid --settings: expected a JSON object"]]);
                    t.check("and nothing waits", root.d.pendingToasts, []);
                    // A new error: syncToasts() shows it, no second toast
                    ToastService.reset();
                    Proc.setResult(root.syncId, JSON.stringify({
                        "error": "another error"
                    }), 1);
                    root.d.launcherAction({
                        "kind": "off"
                    });
                    Proc.flush();
                    t.check("a new error after a launcher action: still one error toast", ToastService.log.map(x => [x.level, x.details]), [["error", "another error"]]);
                    root.d.destroy();
                }
            },
            // --- Live control and the companion add-on ------------------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    // Live control off then on, quicker than the debounce: two
                    // syncs, the first with it off
                    root.mark = root.syncCalls().length;
                    root.save("liveControl", false);
                    root.save("liveControl", true);
                    t.check("liveControl changes sync without the debounce", root.syncCalls().slice(root.mark).map(c => c.debounceMs), [0]);
                    root.mark = root.syncs().length;
                    Proc.flush();
                    Proc.flush();
                    Proc.flush();
                    t.check("one sync with it off, then one with it on", root.syncs().slice(root.mark).map(c => root.settingsOf(c).liveControl), [false, true]);
                    // Another setting keeps the debounce
                    root.mark = root.syncCalls().length;
                    root.save("opacity", 60);
                    t.check("other settings keep the debounce", root.syncCalls().slice(root.mark).map(c => c.debounceMs), [800]);
                    root.d.destroy();
                }
            },
            {
                "run": () => {
                    root.fresh(true);
                    // The sync left a profile pending_restart; the status finds
                    // it installed (the browser loaded it): one sync records it
                    Proc.setResult(root.syncId, root.fx.companion, 0);
                    Proc.flush();
                    t.check("the sync's companion states are shared", root.gv("lastSync").companion, JSON.parse(root.fx.companion).companion);
                    Proc.flush();
                    t.check("a pending add-on found loaded: a sync is asked for", Proc.isPending(root.syncId), true);
                    Proc.flush();
                    Proc.flush();
                    t.check("once: the same outcome asks for no more", [root.syncs().length, Proc.pendingIds()], [2, []]);
                    root.d.destroy();
                }
            },
            // --- Launcher: actions, sync at once, toast after it ----------------------
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    ToastService.reset();
                    // The restart toast is shown once per episode: start one
                    root.d.toastCtx = Logic.newToastContext();
                    NiriService.windows = root.browserWindow("Proton Mail");
                    Proc.setResult(root.siteId, t.readFile("contract/active-site-companion.json"), 0);
                    t.check("the site is unknown first", root.d.siteFor(), null);
                    t.check("an active-site lookup starts", Proc.isPending(root.siteId), true);
                    t.check("asked once while it runs", [root.d.siteFor(), Proc.calls.filter(c => c.id === root.siteId).length], [null, 1]);
                    Proc.flush();
                    t.check("for the focused window", Proc.lastCommand(root.siteId), Logic.activeSiteArgv(root.dir, NiriService.windows[0]));
                    t.check("by its window id, never its title", [Proc.lastCommand(root.siteId).indexOf("--window-id=3") >= 0, Proc.lastCommand(root.siteId).join(" ").indexOf("Proton Mail")], [true, -1]);
                    t.check("the launcher is asked to update", PluginService.launcherUpdates, ["browserGlass"]);
                    t.check("then the site is known", root.d.siteFor().domain, "proton.me");
                    t.check("and reused: no new lookup", Proc.isPending(root.siteId), false);

                    // blist, applied live
                    Proc.setResult(root.syncId, root.syncWith(1, ["0f1e2d3c4b5a"]), 0);
                    root.mark = root.syncs().length;
                    t.check("blist runs", root.d.glassCommand("blist"), true);
                    t.check("the domain is saved", root.d.pluginData.excludedSites, [{
                            "domain": "proton.me"
                        }]);
                    t.check("the sync is asked for with no debounce", root.syncCalls().slice(-1)[0].debounceMs, 0);
                    t.check("no toast before the sync", ToastService.log.length, 0);
                    Proc.flush();
                    t.check("one sync, with the new list", [root.syncs().length, root.settingsOf(Proc.lastCommand(root.syncId)).excluded], [root.mark + 1, ["proton.me"]]);
                    // Other local users can read every argv (/proc/PID/cmdline)
                    t.check("no excluded domain in any argv", Proc.calls.filter(c => /proton\.me|example\.com/.test(c.command.join("\n"))).length, 0);
                    // Applied live, but another change of the same sync (an
                    // opacity edit) still needs a restart: both toasts
                    t.check("live: its toast, and the restart toast another change needs", root.toasts(), [["info", Logic.RESTART_TEXT], ["info", "proton.me excluded"]]);
                    Proc.flush();

                    // Already covered: no save, no sync
                    ToastService.reset();
                    PluginService.saves = [];
                    root.mark = root.syncCalls().length;
                    root.d.glassCommand("fix");
                    root.d.launcherAction({
                        "kind": "blist",
                        "host": "mail.proton.me",
                        "domain": "proton.me",
                        "source": "companion"
                    });
                    t.check("already excluded: a toast each, no save", [root.toasts(), PluginService.saves.length], [[["info", "proton.me is already excluded"], ["info", "proton.me is already excluded"]], 0]);
                    t.check("and no sync", root.syncCalls().length, root.mark);

                    // unblist, not live (no add-on acknowledged)
                    ToastService.reset();
                    root.d.toastCtx = Logic.newToastContext();
                    Proc.setResult(root.syncId, root.syncWith(0, ["0f1e2d3c4b5a"]), 0);
                    t.check("unblist runs", IpcRegistry.call("browserGlass", "includeCurrent"), "OK");
                    t.check("the entry is dropped", root.d.pluginData.excludedSites, []);
                    Proc.flush();
                    t.check("not live: after a restart, no generic restart toast", root.toasts(), [["info", "proton.me back under glass — applies after a restart"]]);
                    Proc.flush();
                    t.check("unblist of a site not excluded", [root.d.glassCommand("unblist"), root.toasts().slice(-1)[0]], [true, ["info", "proton.me is not excluded"]]);

                    // A site from the session file, older than 10 s
                    ToastService.reset();
                    NiriService.windows = root.browserWindow("GitHub");
                    Proc.setResult(root.siteId, JSON.stringify({
                        "host": "user.github.io",
                        "domain": "user.github.io",
                        "source": "session",
                        "age": 42
                    }), 0);
                    Proc.setResult(root.syncId, root.syncWith(1, []), 0);
                    t.check("excludeCurrent waits for the site", [IpcRegistry.call("browserGlass", "excludeCurrent"), Proc.isPending(root.siteId), root.d.siteWaiters.length], ["OK", true, 1]);
                    Proc.flush();
                    t.check("then saves it", root.d.pluginData.excludedSites, [{
                            "domain": "user.github.io"
                        }]);
                    Proc.flush();
                    t.check("session: never live, its age mentioned", ToastService.log.map(x => [x.message, x.details]), [["user.github.io excluded — applies after a restart", "from the session saved 42 s ago"]]);
                    Proc.flush();

                    // list-remove: live (the list names the domain), then the list again
                    ToastService.reset();
                    root.d.launcherAction({
                        "kind": "list-remove",
                        "domain": "user.github.io",
                        "source": "list"
                    });
                    t.check("list-remove drops the entry", root.d.pluginData.excludedSites, []);
                    Proc.flush();
                    t.check("and toasts once synced", root.toasts(), [["info", "user.github.io back under glass"]]);
                    Proc.flush();
                }
            },
            {
                "run": () => {
                    t.check("the launcher reopens on the list", PopoutService.launcherQueries, ["glass list"]);

                    // Glass on and off by IPC: the toast after the sync
                    ToastService.reset();
                    Proc.setResult(root.syncId, root.syncWith(0, []), 0);
                    t.check("glass off", IpcRegistry.call("browserGlass", "glass", "off"), "OK");
                    t.check("saved", PluginService.saves.slice(-1)[0], ["browserGlass", "glassEnabled", false]);
                    Proc.flush();
                    t.check("Glass off toast", root.toasts(), [["info", "Glass off"]]);
                    Proc.flush();
                    t.check("an unknown command", IpcRegistry.call("browserGlass", "glass", "nope"), "unknown command: nope");
                    t.check("glass list by IPC", IpcRegistry.call("browserGlass", "glass", "list"), "OK");

                    // A request while a sync may run: an urgent one follows it
                    root.d.requestSync("windowrules");
                    root.d.book = Object.assign({}, root.d.book, {
                        "scheduledAt": Date.now() - 5000
                    });
                    root.d.launcherAction({
                        "kind": "on"
                    });
                    t.check("no restart of a sync that may run", root.syncCalls().slice(-1)[0].debounceMs, 800);
                    Proc.flush();
                    t.check("the follow-up has no debounce", root.syncCalls().slice(-1)[0].debounceMs, 0);
                    t.check("no toast before the sync that saw the change", ToastService.log.filter(x => x.message === "Glass on").length, 0);
                    Proc.flush();
                    t.check("then Glass on", root.toasts().slice(-1)[0], ["info", "Glass on"]);
                    Proc.flush();

                    // Refusals: warnings
                    ToastService.reset();
                    NiriService.windows = [];
                    root.d.glassCommand("blist");
                    t.check("no window: a warning", root.toasts(), [["warning", "No browser in the foreground"]]);
                    NiriService.windows = [{
                            "id": 8,
                            "app_id": "firefox",
                            "title": "Private Browsing",
                            "pid": 4243,
                            "is_focused": false
                        }];
                    NiriService.lastFocusedWindowId = 8;
                    Proc.setResult(root.siteId, t.readFile("contract/active-site-private.json"), 0);
                    root.d.glassCommand("blist");
                    Proc.flush();
                    t.check("the last focused window is asked", Proc.lastCommand(root.siteId).indexOf("--pid=4243") >= 0, true);
                    t.check("private: a warning", root.toasts().slice(-1)[0], ["warning", "Private window: site not detected"]);
                    t.check("nothing saved", root.d.pluginData.excludedSites, []);
                    // No answer within 2 s
                    ToastService.reset();
                    NiriService.windows = root.browserWindow("Slow");
                    root.d.glassCommand("blist");
                    t.ok("the wait is armed", root.d.siteWaiters.length === 1);
                }
            },
            {
                "wait": 2200,
                "run": () => {
                    t.check("no answer: a warning with a hint", ToastService.log.map(x => [x.level, x.message, x.details]), [["warning", "Current site not found", "try again in a few seconds"]]);
                    t.check("the wait is over", root.d.siteWaiters.length, 0);
                    Proc.flush();
                    t.check("a late answer acts on nothing", ToastService.log.length, 1);
                    root.d.destroy();
                }
            },
            // --- Launcher: the Browse view of Browser Glass (empty query) ---------
            // DMS keeps the first items of this view: it ignores
            // requestLauncherUpdate there (Controller.qml onRequestLauncherUpdate
            // returns on an empty query when no trigger matched)
            {
                "run": () => {
                    root.fresh(true);
                    Proc.flush();
                    Proc.flush();
                    const instances = {};
                    instances["browserGlass"] = root.d;
                    PluginService.pluginDaemonInstances = instances;
                    const launcher = launcherComponent.createObject(root);
                    const c = controllerComponent.createObject(root);
                    const blist = () => c.performSearch(launcher, "").filter(i => i.bgCmd === "blist")[0];
                    NiriService.windows = root.browserWindow("Proton Mail");
                    Proc.setResult(root.siteId, t.readFile("contract/active-site-companion.json"), 0);
                    t.check("first Browse view, nothing known: no site yet", [blist().comment, blist().bgSite], ["Finding the current site…", null]);
                    t.check("a lookup runs", Proc.isPending(root.siteId), true);
                    Proc.flush();
                    t.check("its answer asks for an update", PluginService.launcherUpdates, ["browserGlass"]);
                    t.check("the Browse view entered again names the site", [blist().comment, blist().bgSite.domain], ["proton.me — with its subdomains", "proton.me"]);

                    // Older than SITE_CACHE_MS: shown while a new lookup runs
                    root.d.siteInfo = Object.assign({}, root.d.siteInfo, {
                        "at": Date.now() - Launcher.SITE_CACHE_MS - 1000
                    });
                    const old = blist();
                    t.check("an older answer for the same window: its domain, provisional", [old.comment, old.bgSite], ["proton.me — with its subdomains", null]);
                    t.check("and a new lookup runs", Proc.isPending(root.siteId), true);
                    t.check("an action never takes it", root.d.siteFor(), null);
                    // Enter on it: by name, so the action waits for the new answer
                    Proc.setResult(root.syncId, root.syncWith(1, []), 0);
                    launcher.executeItem(old);
                    t.check("the action waits for the new answer", [root.d.siteWaiters.length, (root.d.pluginData.excludedSites || []).length], [1, 0]);
                    Proc.flush();
                    t.check("then acts on it", root.d.pluginData.excludedSites, [{
                            "domain": "proton.me"
                        }]);
                    Proc.flush();
                    Proc.flush();
                    NiriService.windows = root.browserWindow("Another tab");
                    t.check("another title: no older answer shown", blist().comment, "Finding the current site…");
                    Proc.flush();
                    PluginService.pluginDaemonInstances = {};
                    c.destroy();
                    launcher.destroy();
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
                    t.check("every command id is released", Proc.released.slice().sort(), [root.pasteId, root.reportId, root.siteId, root.sitesId, root.statusId, root.syncId].sort());
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

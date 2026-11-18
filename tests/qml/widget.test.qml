import QtQuick
import Quickshell.Io
import qs.Common
import qs.Services
import "components/logic.js" as Logic

// BrowserGlassWidget.qml: the bar pill (blur_on / blur_off, the restart
// dot) and the popout (status, glass switch, "Exclude copied URL", "Open
// settings"). The daemon's shared variables are set through PluginService,
// as BrowserGlassDaemon.qml publishes them; "Exclude copied URL" runs the
// real daemon, whose clipboard read Proc records.
Item {
    id: root

    width: 400
    height: 800

    Harness {
        id: t
    }

    readonly property string dir: "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass"
    readonly property string pasteId: "browserGlass.paste"

    property var fx: ({})
    property var w: null
    property var d: null
    property var pill: null
    property var vpill: null
    property var pop: null

    Item {
        id: holder
        width: 360
        height: 700
    }

    Component {
        id: widgetComponent
        BrowserGlassWidget {
            pluginId: "browserGlass"
            pluginService: PluginService
        }
    }

    Component {
        id: daemonComponent
        BrowserGlassDaemon {
            pluginId: "browserGlass"
            pluginService: PluginService
        }
    }

    // A clean shell and a widget (no daemon yet)
    function fresh() {
        for (const item of [root.pop, root.pill, root.vpill, root.w]) {
            if (item)
                item.destroy();
        }
        Proc.reset();
        Proc.autoRun = false;
        ToastService.reset();
        PopoutService.reset();
        PluginService.reset();
        PluginService.pluginDaemonInstances = {};
        I18n.unregisterPluginTranslations("browserGlass");
        SettingsData.reset();
        SettingsData.pluginSettings = {
            "browserGlass": {
                "enabled": true
            }
        };
        root.w = widgetComponent.createObject(root);
        root.pill = root.w.horizontalBarPill.createObject(holder);
        root.vpill = root.w.verticalBarPill.createObject(holder);
        root.pop = root.w.popoutContent.createObject(holder, {
            "width": holder.width
        });
    }

    // A real daemon, registered as DMS does (PluginService.pluginDaemonInstances)
    function startDaemon() {
        FileViewLog.reset();
        FileViewLog.put(root.dir + "/plugin.json", "{\"id\": \"browserGlass\"}\n");
        FileViewLog.put(root.dir + "/browserglass.py", "# script\n");
        PluginService.pluginPaths = {
            "browserGlass": root.dir + "/"
        };
        Proc.setResult("browserGlass.sync", root.fx.sync, 0);
        Proc.setResult("browserGlass.status", root.fx.status, 0);
        Proc.setResult("browserGlass.sites", root.fx.sites, 0);
        root.d = daemonComponent.createObject(root);
        PluginService.pluginDaemonInstances = {
            "browserGlass": root.d
        };
    }

    function find(item, name) {
        if (!item)
            return null;
        if (item.objectName === name)
            return item;
        const kids = item.children || [];
        for (let i = 0; i < kids.length; i++) {
            const hit = root.find(kids[i], name);
            if (hit)
                return hit;
        }
        return null;
    }
    function set(name, value) {
        PluginService.setGlobalVar("browserGlass", name, value);
    }
    function popText(name) {
        const item = root.find(root.pop, name);
        return item ? item.text : null;
    }
    function rowValue(name) {
        const item = root.find(root.pop, name);
        return item ? item.value : null;
    }
    function statusWith(changes) {
        return Object.assign(JSON.parse(root.fx.status), changes);
    }

    Component.onCompleted: {
        root.fx = {
            "sync": t.readFile("contract/sync.json"),
            "status": t.readFile("contract/status.json"),
            "sites": t.readFile("contract/sites.json")
        };
        t.steps([
            // --- Pill ----------------------------------------------------------
            {
                "run": () => {
                    t.ok("fixtures read", root.fx.sync && root.fx.status && root.fx.sites);
                    root.fresh();
                    const icon = root.find(root.pill, "glassIcon");
                    const badge = root.find(root.pill, "restartBadge");
                    t.ok("the pill has an icon and a badge", icon !== null && badge !== null);
                    t.check("no status yet: blur_off", icon.name, "blur_off");
                    t.check("the widget's iconName agrees", root.w.iconName, "blur_off");
                    t.check("no badge", [badge.visible, root.pill.showBadge], [false, false]);
                    t.check("the pill is one bar icon wide", [root.pill.implicitWidth, root.pill.implicitHeight], [root.w.iconSize, root.w.iconSize]);
                    t.check("the icon has the bar icon size", icon.size, root.w.iconSize);

                    root.set("glassActive", true);
                    t.check("glass active: blur_on", icon.name, "blur_on");
                    t.check("in the primary colour", String(icon.color), String(Theme.primary));
                    t.check("the vertical pill too", root.find(root.vpill, "glassIcon").name, "blur_on");
                    t.check("still no badge", badge.visible, false);

                    root.set("restartNeeded", true);
                    t.check("restart needed: the badge shows", [badge.visible, root.pill.showBadge], [true, true]);
                    t.check("on the vertical pill too", root.find(root.vpill, "restartBadge").visible, true);
                    t.check("the icon stays blur_on", icon.name, "blur_on");

                    root.set("restartNeeded", false);
                    t.check("restart done: the badge goes", badge.visible, false);

                    root.set("glassActive", false);
                    t.check("glass inactive: blur_off", icon.name, "blur_off");
                    t.check("in the plain text colour", String(icon.color), String(Theme.surfaceText));
                    root.set("restartNeeded", true);
                    t.check("glass off with a restart pending: blur_off and the badge", [icon.name, badge.visible], ["blur_off", true]);

                    root.set("glassActive", "true");
                    root.set("restartNeeded", 1);
                    t.check("only true counts", [icon.name, badge.visible], ["blur_off", false]);
                    t.check("the pill wrote nothing", PluginService.saves, []);
                }
            },
            // --- Popout: status ------------------------------------------------
            {
                "run": () => {
                    root.fresh();
                    t.ok("the popout is built", root.pop !== null);
                    t.check("its header", root.pop.headerText, "Browser Glass");
                    t.check("no status yet: said so", root.pop.detailsText, "No status yet");
                    t.check("no opacity yet", root.rowValue("opacityRow"), "—");
                    t.check("no browsers yet", root.rowValue("browsersRow"), "—");
                    t.check("nothing pending, no error, no warning", ["syncingText", "restartNotice", "errorText", "warningsText"].map(n => root.find(root.pop, n).visible), [false, false, false, false]);
                    t.check("the glass switch is on by default", root.find(root.pop, "glassToggle").checked, true);
                    t.ok("the popout has a height", root.pop.implicitHeight > 0);

                    root.set("glassActive", true);
                    t.check("before a status, the shared glassActive tells", root.pop.detailsText, "Glass is on");

                    root.set("status", JSON.parse(root.fx.status));
                    root.set("restartNeeded", true);
                    t.check("the status reason", root.pop.detailsText, "Glass is on");
                    t.check("the opacity and where it comes from", root.rowValue("opacityRow"), "85%, from DMS");
                    t.check("the browsers found, each family once", root.rowValue("browsersRow"), "Firefox, LibreWolf, Zen");
                    t.check("the restart notice", root.find(root.pop, "restartNotice").visible, true);
                    t.check("names the browser to restart", root.popText("restartText"), "Restart Firefox to see the change");
                    t.check("the Zen warning is counted", [root.find(root.pop, "warningsText").visible, root.popText("warningsText")], [true, "1 warning, details in the settings"]);
                    t.check("Live control connected: no invite", root.find(root.pop, "liveInvite").visible, false);
                    const off = JSON.parse(root.fx.status);
                    off.companion = {
                        "enabled": false,
                        "state": "off",
                        "hosts": 0,
                        "manifest": false
                    };
                    root.set("status", off);
                    t.check("Live control off: the popout says what it adds", [root.find(root.pop, "liveInvite").visible, root.popText("liveInvite").indexOf("Turn it on in the settings") >= 0], [true, true]);
                    root.set("status", JSON.parse(root.fx.status));

                    const s = root.statusWith({
                        "glass": {
                            "active": false,
                            "reason": "blur_disabled",
                            "opacity": 0.7,
                            "opacity_source": "override",
                            "surface": "#101418",
                            "mode": "dark"
                        },
                        "browsers": [],
                        "warnings": [
                            {
                                "code": "niri_rule_held",
                                "message": "held",
                                "family": null,
                                "profile": null
                            },
                            {
                                "code": "read_only",
                                "message": "a",
                                "family": "firefox",
                                "profile": "x"
                            },
                            {
                                "code": "write_failed",
                                "message": "b",
                                "family": "firefox",
                                "profile": "y"
                            }
                        ]
                    });
                    root.set("status", s);
                    t.check("why glass is off", root.pop.detailsText, "DMS blur is off");
                    t.check("a browser override", root.rowValue("opacityRow"), "70%, browser override");
                    t.check("no browser found", root.rowValue("browsersRow"), "None found");
                    t.check("no family to name: the generic restart text", root.popText("restartText"), "Restart the browser to see the change");
                    t.check("the niri rule codes are not counted", root.popText("warningsText"), "2 warnings, details in the settings");

                    s.glass = Object.assign({}, s.glass, {
                        "reason": "toggled_off",
                        "opacity_source": "forced"
                    });
                    s.warnings = [s.warnings[0]];
                    // A new document, as the daemon publishes each status
                    root.set("status", JSON.parse(JSON.stringify(s)));
                    t.check("turned off", root.pop.detailsText, "Glass is turned off");
                    t.check("a forced opacity", root.rowValue("opacityRow"), "70%, forced");
                    t.check("only niri rule codes: no warning line", root.find(root.pop, "warningsText").visible, false);

                    root.set("restartNeeded", false);
                    t.check("restart done: the notice goes", root.find(root.pop, "restartNotice").visible, false);
                    root.set("syncing", true);
                    t.check("a sync running shows", root.find(root.pop, "syncingText").visible, true);
                    root.set("syncing", false);
                    root.set("lastError", "python3 not found");
                    t.check("the last error, as is", [root.find(root.pop, "errorText").visible, root.popText("errorText")], [true, "python3 not found"]);
                    root.set("lastError", "");
                    t.check("no error: hidden", root.find(root.pop, "errorText").visible, false);
                    t.check("the popout wrote nothing", PluginService.saves, []);
                }
            },
            // --- Popout: glass switch ------------------------------------------
            {
                "run": () => {
                    root.fresh();
                    const toggle = root.find(root.pop, "glassToggle");
                    t.tap(toggle);
                    t.check("off: glassEnabled false is saved", PluginService.saves, [["browserGlass", "glassEnabled", false]]);
                    t.check("in the plugin settings", SettingsData.getPluginSetting("browserGlass", "glassEnabled", null), false);
                    t.check("the widget reads it back", [root.w.glassEnabled, toggle.checked], [false, false]);
                    t.tap(toggle);
                    t.check("on again: true is saved", PluginService.saves.slice(-1), [["browserGlass", "glassEnabled", true]]);
                    t.check("the switch follows", toggle.checked, true);
                    t.check("one save per tap, nothing else", PluginService.saves.map(s => s[1]), ["glassEnabled", "glassEnabled"]);
                    PluginService.savePluginData("browserGlass", "glassEnabled", "off");
                    t.check("a stored string is read as logic.js reads it", toggle.checked, false);
                    t.check("the switch is not glass being on", root.w.glassActive, false);
                    t.check("no command runs", Proc.calls, []);
                }
            },
            // --- Popout: Exclude copied URL ------------------------------------
            {
                "run": () => {
                    root.fresh();
                    const button = root.find(root.pop, "excludeButton");
                    t.check("no daemon: the button is off", button.enabled, false);
                    t.check("and the action does nothing", root.w.excludeClipboard(), false);
                    t.check("no command", Proc.calls, []);

                    root.startDaemon();
                    t.check("with the daemon: on", button.enabled, true);
                    Proc.flush();
                    Proc.reset();
                    Proc.autoRun = false;
                    ToastService.reset();
                    Proc.setResult(root.pasteId, "https://www.Example.com/some/page?q=1\n", 0);
                    t.press(button);
                    t.check("it asks the daemon, which reads the clipboard", Proc.calls.filter(c => c.id === root.pasteId).map(c => c.command), [["dms", "cl", "paste"]]);
                    Proc.flush();
                    t.check("the host is saved", SettingsData.getPluginSetting("browserGlass", "excludedSites", []), [
                        {
                            "domain": "example.com"
                        }
                    ]);
                    t.check("the daemon's toast names it", ToastService.log.filter(x => x.message === "Site excluded from glass").map(x => x.details), ["example.com"]);
                    // Gone while the manifest is still there: no sweep
                    root.d.destroy();
                    root.d = null;
                    PluginService.pluginDaemonInstances = {};
                    t.check("daemon gone: the button is off again", button.enabled, false);
                }
            },
            // --- Popout: Open settings -----------------------------------------
            {
                "wait": 50,
                "run": () => {
                    root.fresh();
                    root.w.triggerPopout();
                    t.check("the pill opens the popout", root.w._testPopoutOpen, true);
                    t.press(root.find(root.pop, "settingsButton"));
                    t.check("the plugin's settings tab is asked for", PopoutService.opened, ["plugin:browserGlass"]);
                    t.check("the popout closes", root.w._testPopoutOpen, false);
                    t.check("nothing saved", PluginService.saves, []);
                }
            },
            // --- Translations --------------------------------------------------
            {
                "run": () => {
                    root.fresh();
                    I18n.registerPluginTranslations("browserGlass", {
                        "Open settings": {
                            "Open settings": "Ouvrir les réglages"
                        },
                        "Glass is off": {
                            "Glass is off": "Le verre est coupé"
                        },
                        "%1%, from DMS": {
                            "%1%, from DMS": "%1\u00a0%, selon DMS"
                        }
                    });
                    root.set("status", JSON.parse(root.fx.status));
                    root.set("status", root.statusWith({
                        "glass": Object.assign({}, JSON.parse(root.fx.status).glass, {
                            "active": false,
                            "reason": "unknown"
                        })
                    }));
                    t.check("button labels go through trFor", root.find(root.pop, "settingsButton").text, "Ouvrir les réglages");
                    t.check("the reason too", root.pop.detailsText, "Le verre est coupé");
                    t.check("and the placeholders", root.rowValue("opacityRow"), "85\u00a0%, selon DMS");
                    t.check("untranslated text stays English", root.find(root.pop, "excludeButton").text, "Exclude copied URL");
                    t.check("PLUGIN_ID is the widget's id", Logic.PLUGIN_ID, root.w.pluginId);
                }
            },
            {
                "run": () => {
                    for (const item of [root.pop, root.pill, root.vpill, root.w])
                        item.destroy();
                    root.w = null;
                }
            }
        ]);
    }
}

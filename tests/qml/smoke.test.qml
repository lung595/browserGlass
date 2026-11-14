import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Widgets
import qs.DCommon.Widgets
import qs.Modules.Plugins

// Proves the QML test plumbing: every stand-in loads, records what the code
// does with it and answers what a test feeds it. Run with tests/qml/run.sh.
Item {
    id: root
    width: 400
    height: 600

    Harness {
        id: t
    }

    // --- PluginComponent + PluginGlobalVar (a daemon's root) -------------
    PluginComponent {
        id: daemon
        pluginId: "smokePlugin"
        pluginService: PluginService
        popoutContent: Component {
            Item {}
        }
        horizontalBarPill: Component {
            DIcon {
                name: daemon.pluginData.glassEnabled === false ? "blur_off" : "blur_on"
            }
        }

        PluginGlobalVar {
            id: status
            varName: "status"
            defaultValue: "unknown"
        }

        IpcHandler {
            target: "smokePlugin"
            function ping(word: string): string {
                return "pong " + word;
            }
        }
    }

    // --- PluginSettings + setting widgets ---------------------------------
    PluginSettings {
        id: settings
        pluginId: "smokeSettings"
        pluginService: PluginService
        width: 400

        ToggleSetting {
            id: toggle
            settingKey: "flag"
            label: "Flag"
            defaultValue: true
        }
        SelectionSetting {
            id: select
            settingKey: "theme"
            label: "Theme"
            options: [
                {
                    "label": "Follow",
                    "value": "follow"
                },
                {
                    "label": "Dark",
                    "value": "dark"
                }
            ]
            defaultValue: "follow"
        }
        SliderSetting {
            id: slider
            settingKey: "opacity"
            label: "Opacity"
            defaultValue: 80
        }
        StringSetting {
            id: str
            settingKey: "name"
            label: "Name"
        }
        ListSettingWithInput {
            id: list
            settingKey: "excludedSites"
            label: "Excluded"
            fields: [
                {
                    "id": "domain",
                    "label": "Domain",
                    "required": true
                }
            ]
        }
    }

    // --- FileView ----------------------------------------------------------
    property int kdlLoads: 0
    property int kdlChanges: 0
    property int missingFailures: 0
    FileView {
        id: kdl
        path: "/tmp/fakehome/.config/niri/dms/windowrules.kdl"
        watchChanges: true
        onLoaded: root.kdlLoads++
        onFileChanged: root.kdlChanges++
    }
    FileView {
        id: missing
        onLoadFailed: root.missingFailures++
    }

    // --- Widgets -------------------------------------------------------------
    property int buttonClicks: 0
    property var toggled: []
    Column {
        StyledText {
            id: text
            text: I18n.trFor("smokePlugin", "Hello")
        }
        StyledRect {
            width: 10
            height: 10
        }
        DButton {
            id: button
            text: "Go"
            onClicked: root.buttonClicks++
        }
        DToggle {
            id: dToggle
            onToggled: checked => root.toggled = root.toggled.concat([checked])
        }
        DTextField {
            id: field
            placeholderText: "domain"
        }
    }

    property var procAnswers: []
    property var ownedAnswers: []

    Component.onCompleted: {
        // FileView seeds before the views' first load (next event loop turn)
        FileViewLog.put(kdl.path, "window-rule {\n    opacity 0.9\n}\n");
        t.steps([
            {
                "run": () => {
                    // Quickshell
                    t.check("Quickshell.env HOME is made up", Quickshell.env("HOME"), "/tmp/fakehome");
                    t.check("Quickshell.env unknown is null", Quickshell.env("NOPE"), null);
                    Quickshell.execDetached(["python3", "-I", "-c", "pass", "uninstall"]);
                    t.check("execDetached is recorded", Quickshell.detached, [["python3", "-I", "-c", "pass", "uninstall"]]);

                    // Proc, manual mode: debounce collapses, flush launches
                    Proc.autoRun = false;
                    Proc.setResult("bg.sync", '{"glass":true}', 0);
                    for (const n of [1, 2, 3])
                        Proc.runCommand("bg.sync", ["python3", "-I", "browserglass.py", "sync", String(n)], (out, code) => root.procAnswers = root.procAnswers.concat([[out, code]]), 800);
                    t.check("three requests recorded", Proc.calls.length, 3);
                    t.check("debounce kept", Proc.calls[0].debounceMs, 800);
                    t.ok("still pending", Proc.isPending("bg.sync"));
                    t.check("nothing launched before flush", Proc.launched.length, 0);
                    t.check("flush launches one", Proc.flush(), 1);
                    t.check("the last command wins", Proc.lastCommand("bg.sync"), ["python3", "-I", "browserglass.py", "sync", "3"]);
                    t.check("the callback got the canned result", root.procAnswers, [['{"glass":true}', 0]]);
                    Proc.results = {
                        "bg.status": (cmd, id) => ({
                                "output": cmd.join(" "),
                                "exitCode": 3
                            })
                    };
                    Proc.runCommand("bg.status", ["status", "--json"], (out, code) => root.procAnswers = root.procAnswers.concat([[out, code]]));
                    Proc.flush();
                    t.check("a result function sees the command", root.procAnswers[1], ["status --json", 3]);
                    Proc.runCommand("bg.gone", ["x"], () => t.ok("released command never runs", false));
                    Proc.release("bg.gone");
                    t.check("release recorded", Proc.released, ["bg.gone"]);
                    t.check("release cancels", Proc.flush(), 0);
                    Proc.runCommand(null, ["anon"], null);
                    t.ok("a null id gets a random one", Proc.pendingIds()[0].indexOf("random-") === 0);
                    Proc.reset();
                    t.check("reset clears", [Proc.calls.length, Proc.launched.length, Proc.pendingIds().length, Proc.autoRun], [0, 0, 0, true]);
                    // Proc, timer mode: two quick requests, one launch after the debounce
                    Proc.runCommand("bg.timed", ["a"], null, 40);
                    Proc.runCommand("bg.timed", ["b"], null, 40);
                }
            },
            {
                "wait": 150,
                "run": () => {
                    t.check("timer mode launched once, last command", Proc.commandsFor("bg.timed"), [["b"]]);

                    // FileView
                    t.check("seeded file loaded", root.kdlLoads, 1);
                    t.ok("text() reads the store", kdl.text().indexOf("opacity 0.9") > 0);
                    FileViewLog.change(kdl.path, "window-rule {\n    opacity 0.7\n}\n");
                    t.check("an outside edit raises fileChanged", root.kdlChanges, 1);
                    t.ok("and the new text is read", kdl.text().indexOf("opacity 0.7") > 0);
                    missing.path = "/tmp/fakehome/nope.txt";
                    missing.content = undefined;
                    kdl.setText("written");
                    t.check("setText is recorded", FileViewLog.writes, [[kdl.path, "written"]]);
                    missing.content = "fake";
                    t.check("content overrides the store", missing.text(), "fake");

                    // ToastService
                    ToastService.showInfo("Browser Glass", "Restart");
                    ToastService.showError("Browser Glass", "Sync failed");
                    ToastService.showWarning("Browser Glass", "Zen");
                    t.check("toast levels", ToastService.log.map(x => x.level), ["info", "error", "warning"]);
                    t.check("toast message and details", [ToastService.log[1].message, ToastService.log[1].details], ["Browser Glass", "Sync failed"]);
                    t.check("ofLevel", ToastService.ofLevel("warning").length, 1);

                    // PluginService + PluginComponent + PluginGlobalVar
                    t.check("pluginData starts empty", daemon.pluginData, {});
                    PluginService.savePluginData("smokePlugin", "glassEnabled", false);
                    t.check("savePluginData reaches pluginData", daemon.pluginData.glassEnabled, false);
                    t.check("and SettingsData", SettingsData.getPluginSetting("smokePlugin", "glassEnabled", true), false);
                    t.check("loadPluginData", PluginService.loadPluginData("smokePlugin", "glassEnabled", true), false);
                    t.check("loadPluginData default", PluginService.loadPluginData("smokePlugin", "nope", 7), 7);
                    const pill = daemon.horizontalBarPill.createObject(root);
                    t.check("a pill built from the component sees pluginData", pill.name, "blur_off");
                    pill.destroy();
                    t.check("PluginGlobalVar default", status.value, "unknown");
                    status.set("active");
                    t.check("PluginGlobalVar set", PluginService.getGlobalVar("smokePlugin", "status", null), "active");
                    t.check("PluginGlobalVar value follows", status.value, "active");
                    daemon.triggerPopout();
                    t.check("triggerPopout opens", daemon._testPopoutOpen, true);
                    daemon.closePopout();
                    t.check("closePopout closes", daemon._testPopoutOpen, false);

                    // IpcHandler
                    t.check("IPC call", IpcRegistry.call("smokePlugin", "ping", "x"), "pong x");
                    t.check("IPC unknown target", IpcRegistry.call("nobody", "ping"), null);

                    // SessionData / SettingsData / I18n / PopoutService / Theme
                    t.check("isLightMode default", SessionData.isLightMode, false);
                    t.check("blurEnabled default", SettingsData.blurEnabled, true);
                    t.check("trFor returns the source", text.text, "Hello");
                    I18n.registerPluginTranslations("smokePlugin", {
                        "Hello": {
                            "Hello": "Bonjour"
                        }
                    });
                    t.check("trFor with a table", I18n.trFor("smokePlugin", "Hello"), "Bonjour");
                    t.check("the binding follows the table", text.text, "Bonjour");
                    PopoutService.openSettingsWithTab("plugin:browserGlass");
                    t.check("openSettingsWithTab recorded", PopoutService.opened, ["plugin:browserGlass"]);
                    t.ok("Theme has a surface colour", Theme.surface !== undefined);
                    t.check("Paths.strip", Paths.strip(Paths.config), "/tmp/fakehome/.config/dms");

                    // Widgets
                    t.press(button);
                    t.tap(dToggle);
                    field.text = "example.com";
                    t.check("DButton press", root.buttonClicks, 1);
                    t.check("DToggle tap", root.toggled, [true]);
                    t.check("DToggle keeps its bound state", dToggle.checked, false);
                    button.enabled = false;
                    t.press(button);
                    t.check("a disabled DButton ignores a press", root.buttonClicks, 1);
                    t.check("DTextField text", field.text, "example.com");

                    // Settings widgets: loaded (Toggle and String wait one turn)
                    t.check("settings: toggle loaded its default", toggle.value, true);
                    t.check("settings: selection default", select.value, "follow");
                    t.check("settings: slider default", slider.value, 80);
                    PluginService.saves = [];
                    toggle.value = false;
                    select.choose("Dark");
                    slider.value = 55;
                    str.text = "bob";
                    str.commit();
                    t.check("list submit refuses an empty required field", list.submit([" "]), false);
                    t.check("list submit adds", list.submit([" example.com "]), true);
                    t.check("every change is saved", PluginService.saves, [["smokeSettings", "flag", false], ["smokeSettings", "theme", "dark"], ["smokeSettings", "opacity", 55], ["smokeSettings", "name", "bob"], ["smokeSettings", "excludedSites", [
                                    {
                                        "domain": "example.com"
                                    }
                                ]]]);
                    t.check("and lands in SettingsData", SettingsData.pluginSettings.smokeSettings.theme, "dark");

                    // Stubs keep DMS's semantics
                    SettingsData.setPluginSetting("smokeCopy", "excluded", ["a.com"]);
                    const copy = SettingsData.getPluginSettingsForPlugin("smokeCopy");
                    copy.excluded.push("b.com");
                    t.check("the store is a deep copy", SettingsData.getPluginSetting("smokeCopy", "excluded", []), ["a.com"]);
                    t.check("getPluginPath unknown is empty", PluginService.getPluginPath("nobody"), "");
                    kdl.setText("\u00e9");
                    t.check("FileView data() is UTF-8", Array.from(new Uint8Array(kdl.data())), [195, 169]);
                    root.ownedAnswers = [];
                    const live = Qt.createQmlObject("import QtQuick; QtObject {}", root);
                    const dead = Qt.createQmlObject("import QtQuick; QtObject {}", root);
                    Proc.runCommand("bg.live", ["live"], () => root.ownedAnswers = root.ownedAnswers.concat(["live"]), 40, 1000, live);
                    Proc.runCommand("bg.dead", ["dead"], () => root.ownedAnswers = root.ownedAnswers.concat(["dead"]), 40, 1000, dead);
                    dead.destroy();
                }
            },
            {
                "wait": 150,
                "run": () => {
                    t.check("a live owner's command runs", Proc.commandsFor("bg.live"), [["live"]]);
                    t.check("a dead owner's command never runs", Proc.commandsFor("bg.dead"), []);
                    t.check("nor its callback", root.ownedAnswers, ["live"]);
                    t.check("and is released", Proc.released, ["bg.dead"]);
                }
            }
        ]);
    }
}

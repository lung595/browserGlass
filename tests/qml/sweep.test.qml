import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import "components"
import "components/logic.js" as Logic
import "components/keeper.js" as Keeper

// components/UninstallSweep.qml: the deleted-folder uninstaller. It keeps
// browserglass.py's text from load time and, once plugin.json is gone,
// starts `python3 -I -c STDIN_BOOTSTRAP uninstall --if-gone <plugin.json>`
// with that text on stdin (never in argv). The script waits its grace
// period and exits EXIT_KEPT when plugin.json is back (an update); else,
// once it exits, the plugin's plugin_settings.json entry is dropped.
Item {
    id: root

    Harness {
        id: t
    }

    readonly property string dir: "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass"
    readonly property string manifest: dir + "/plugin.json"
    readonly property string scriptPath: dir + "/browserglass.py"
    property string script: ""
    property var sweep: null

    Component {
        id: sweepComponent
        UninstallSweep {
            pluginId: "browserGlass"
        }
    }

    function fresh() {
        ProcessLog.reset();
        ToastService.reset();
        Quickshell.reset();
        SettingsData.reset();
        SettingsData.pluginSettings = {
            "browserGlass": {
                "enabled": true,
                "opacity": 70
            },
            "otherPlugin": {
                "enabled": true
            }
        };
        FileViewLog.reset();
        FileViewLog.put(root.scriptPath, root.script);
        FileViewLog.put(root.manifest, "{\"id\": \"browserGlass\"}\n");
        PluginService.pluginPaths = {
            "browserGlass": root.dir + "/"
        };
        root.sweep = sweepComponent.createObject(root);
    }

    // The sweep's process: its creation context died with the plugin, so its
    // QML methods can no longer run (the real Process is C++): raise the
    // signal itself, as the real one would
    function exitLive(code) {
        const live = ProcessLog.alive().filter(p => p.running);
        for (const p of live)
            p.exited(code, 0);
        return live.length;
    }

    function deleteFolder() {
        root.fresh();
        FileViewLog.remove(root.manifest);
        FileViewLog.remove(root.scriptPath);
        root.sweep.destroy();
    }

    // No argv string may carry the script (MAX_ARG_STRLEN is 128 KiB)
    function argvClean(command) {
        return command.every(a => a.length < 1000 && a.indexOf("def main") < 0);
    }

    Component.onCompleted: {
        root.script = t.readFile("browserglass.py");
        t.steps([
            {
                "run": () => {
                    t.ok("the real script is over the 128 KiB argv cap", root.script.length > 131072);
                    // 1. Shell reload / quit / disable: the folder stays, nothing runs
                    root.fresh();
                    t.check("the folder is captured from PluginService", [root.sweep.pluginDir, root.sweep.manifest], [root.dir, root.manifest]);
                    t.ok("the script text is kept in memory", root.sweep.script === root.script);
                    t.ok("nothing runs at load", ProcessLog.runs.length === 0);
                    root.sweep.destroy();
                }
            },
            {
                "run": () => {
                    t.check("plugin.json still there: no process", ProcessLog.runs.length, 0);
                    t.check("no detached command", Quickshell.detached, []);
                    t.ok("the settings entry stays", SettingsData.pluginSettings.browserGlass !== undefined);
                    t.check("no toast", ToastService.log.length, 0);

                    // 2. The folder was deleted: plugin.json gone at unload
                    root.fresh();
                    FileViewLog.remove(root.manifest);
                    FileViewLog.remove(root.scriptPath);
                    root.sweep.destroy();
                }
            },
            {
                "run": () => {
                    t.check("one process ran", ProcessLog.runs.length, 1);
                    const run = ProcessLog.runs[0];
                    t.check("argv is python3 -I -c <bootstrap> uninstall --if-gone <plugin.json>", run.command, ["python3", "-I", "-c", Logic.STDIN_BOOTSTRAP, "uninstall", "--if-gone", root.manifest]);
                    t.ok("the bootstrap is the script's own constant", root.script.indexOf("\nSTDIN_BOOTSTRAP = " + JSON.stringify(run.command[3]) + "\n") >= 0);
                    t.ok("the script text is NOT in argv", root.argvClean(run.command));
                    t.ok("the script text went to stdin, whole", run.stdin === root.script);
                    t.ok("stdin was closed (python reads to EOF)", run.stdinClosed);
                    t.check("not a detached launch (it needs stdin)", run.detached, false);
                    t.check("nothing was dropped", ProcessLog.dropped, []);
                    t.check("no execDetached either", Quickshell.detached, []);
                    t.ok("the settings entry stays while the grace period runs", SettingsData.pluginSettings.browserGlass !== undefined);
                    t.check("nothing written yet", SettingsData.pluginSettingsWrites.length, 0);
                    t.check("no toast yet", ToastService.log.length, 0);
                    t.check("the process outlives the plugin", ProcessLog.alive().filter(p => p.running).length, 1);
                    t.check("keeper.js holds it from the garbage collector", Keeper.count(), 1);
                    root.exitLive(0);
                }
            },
            {
                "wait": 50,
                "run": () => {
                    t.check("and goes once it exits", ProcessLog.alive().length, 0);
                    t.check("and the keeper lets go", Keeper.count(), 0);
                    t.check("exit 0: the plugin's settings entry is dropped, the others kept", SettingsData.pluginSettings, {
                        "otherPlugin": {
                            "enabled": true
                        }
                    });
                    t.check("and plugin_settings.json is written", SettingsData.pluginSettingsWrites.map(x => JSON.parse(x)), [
                        {
                            "otherPlugin": {
                                "enabled": true
                            }
                        }
                    ]);
                    t.check("one info toast", ToastService.log.map(x => [x.level, x.message]), [["info", "Browser Glass removed: browsers restored"]]);

                    // 2b. An update or reinstall: plugin.json was back after the grace
                    root.deleteFolder();
                }
            },
            {
                "run": () => {
                    t.check("the sweep started", ProcessLog.runs.length, 1);
                    t.check("EXIT_KEPT", root.exitLive(Logic.EXIT_KEPT), 1);
                }
            },
            {
                "wait": 50,
                "run": () => {
                    t.check("kept: the settings entry stays", SettingsData.pluginSettings.browserGlass, {
                        "enabled": true,
                        "opacity": 70
                    });
                    t.check("nothing written", SettingsData.pluginSettingsWrites.length, 0);
                    t.check("no toast", ToastService.log.length, 0);
                    t.check("the keeper lets go", Keeper.count(), 0);

                    // 2c. The uninstall itself failed: the plugin is still gone
                    root.deleteFolder();
                }
            },
            {
                "run": () => {
                    t.check("one more sweep", root.exitLive(1), 1);
                }
            },
            {
                "wait": 50,
                "run": () => {
                    t.check("failed: the entry is dropped all the same", SettingsData.pluginSettings.browserGlass, undefined);
                    t.check("one error toast with the exit code", ToastService.log.map(x => [x.level, x.message, x.details]), [["error", "Browser Glass removed, but restoring the browsers failed", "exit code 1"]]);
                    t.check("the keeper lets go", Keeper.count(), 0);

                    // 3. Folder deleted, but the script could not be read at load
                    ProcessLog.reset();
                    FileViewLog.reset();
                    FileViewLog.put(root.manifest, "{}");
                    SettingsData.pluginSettings = {
                        "browserGlass": {
                            "enabled": true
                        }
                    };
                    PluginService.pluginPaths = {
                        "browserGlass": root.dir
                    };
                    root.sweep = sweepComponent.createObject(root);
                    t.check("no script text", root.sweep.script, "");
                    FileViewLog.remove(root.manifest);
                    root.sweep.destroy();
                }
            },
            {
                "run": () => {
                    t.check("no script: nothing runs", ProcessLog.runs.length, 0);
                    t.ok("the entry stays (nothing was uninstalled)", SettingsData.pluginSettings.browserGlass !== undefined);
                    PluginService.pluginPaths = {};
                }
            }
        ]);
    }
}

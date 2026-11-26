.pragma library
.import "logic.js" as Logic

// Starts a process that outlives the plugin: UninstallSweep.qml runs the
// uninstaller while the plugin is being destroyed, after its folder is gone.
// - The Process comes from a component this library compiles while the
//   folder still exists (prepare(), at load): at teardown no file can be read.
// - It is created here, outside the plugin's QML context, so it keeps working
//   once that context is torn down, and without a parent, so nothing of the
//   plugin takes it along.
// - A parentless object belongs to the JavaScript engine, whose garbage
//   collector would destroy it (killing its child) once nothing refers to it:
//   `held` refers to it (a library lives as long as the engine) until it exits.
// - What happens once it exits runs here too: the plugin's QML context (its
//   handlers, its ids) is gone by then. The caller hands over the shell's
//   singletons it needs (`after`).

var held = [];
var runner = null;

// Compiles SweepProcess.qml; true when it is ready
function prepare() {
    if (!runner)
        runner = Qt.createComponent("SweepProcess.qml");
    return runner !== null && runner.status === 1; // Component.Ready
}

// Starts `command`, writes `text` to its stdin and closes it. Once it exits,
// `onExit(exitCode)` runs (when given) and the process is dropped. The
// process object, or null when it could not be made.
function spawnWithStdin(command, text, onExit) {
    if (!prepare())
        return null;
    var proc = runner.createObject(null, {
        "command": command,
        "stdinEnabled": true
    });
    if (!proc)
        return null;
    held.push(proc);
    proc.exited.connect(function (exitCode) {
        var i = held.indexOf(proc);
        if (i >= 0)
            held.splice(i, 1);
        proc.destroy();
        if (typeof onExit === "function")
            onExit(exitCode);
    });
    proc.running = true;
    proc.write(text);
    // Closes stdin once the text is written: python reads to EOF
    proc.stdinEnabled = false;
    return proc;
}

// What the sweep does once its uninstaller exited. Logic.EXIT_KEPT:
// plugin.json came back during the grace period (an update, a reinstall),
// nothing changes. Otherwise the plugin is gone and a toast tells how the
// uninstall went. Its plugin_settings.json entry is dropped only once the
// uninstall succeeded: after a failure (a busy state lock...) the browsers
// are still glassed, and a reinstall needs those settings to restore them.
//   after: {settings: SettingsData, toasts: ToastService, pluginId,
//           doneText, failedText (already translated)}
// plugin_settings.json: DMS keeps a removed plugin's entry, and writes its
// whole map back on every save, so the entry goes through SettingsData (an
// edit of the file itself would be overwritten).
function afterSweep(exitCode, after) {
    if (exitCode === Logic.EXIT_KEPT || !after)
        return "kept";
    var settings = exitCode === 0 ? after.settings : null;
    var next = settings ? Logic.withoutPlugin(settings.pluginSettings, after.pluginId) : null;
    if (next !== null) {
        settings.pluginSettings = next;
        // DMS's writer (looked up by name: older shells may lack it)
        var save = settings["savePluginSettings"];
        if (typeof save === "function")
            save.call(settings);
    }
    if (after.toasts) {
        if (exitCode === 0)
            after.toasts.showInfo(after.doneText, "", "", after.pluginId);
        else
            after.toasts.showError(after.failedText, "exit code " + exitCode, "", after.pluginId);
    }
    return exitCode === 0 ? "removed" : "failed";
}

// The sweep: `command` with the script `text` on stdin, then afterSweep()
function sweep(command, text, after) {
    return spawnWithStdin(command, text, function (exitCode) {
        afterSweep(exitCode, after);
    });
}

function count() {
    return held.length;
}

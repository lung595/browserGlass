import QtQuick
import Quickshell.Io
import qs.Common
import qs.Services
import "logic.js" as Logic
import "keeper.js" as Keeper

// Deleting the plugin folder leaves nothing behind. DMS removes the folder,
// then unloads the plugin: when the daemon (and this sweep with it) is
// destroyed, the sweep checks whether its own plugin.json is gone. Disabling,
// reloading or quitting the shell keep the folder, so nothing happens then
// (disabling is the daemon's own uninstall).
// The folder no longer exists at that point, so browserglass.py is read when
// the plugin loads and kept in memory. Its text is written to the stdin of
// `python3 -I -c STDIN_BOOTSTRAP uninstall --if-gone <plugin.json>`: never
// in argv (one argument is capped at 128 KiB and the script is larger).
// A missing plugin.json is not trusted at once: an update or a reinstall
// replaces the folder, so the script first waits a grace period
// ($BG_SWEEP_GRACE, 4 s) and does nothing (EXIT_KEPT) if plugin.json is back.
// components/keeper.js starts that process so that it outlives the plugin,
// and, once it exits, drops the plugin's plugin_settings.json entry (unless
// it was kept) and shows the toast.
// At rest this costs one string: no timer, no process.
Item {
    id: sweep

    required property string pluginId

    // Captured while the plugin is loaded: DMS forgets its path on unload
    property string pluginDir: ""
    property string manifest: ""
    property string script: ""
    // True once the sweep ran (tests read it)
    property bool swept: false

    visible: false
    width: 0
    height: 0

    FileView {
        id: source
        blockLoading: true
        printErrors: false
    }

    FileView {
        id: probe
        blockLoading: true
        printErrors: false
    }

    function capture() {
        // DMS's path for the plugin, else this file's own folder's parent
        const fromService = PluginService.getPluginPath(sweep.pluginId);
        const dir = String(fromService || Paths.strip(Qt.resolvedUrl(".."))).replace(/\/+$/, "");
        if (!dir)
            return;
        sweep.pluginDir = dir;
        sweep.manifest = Logic.manifestPath(dir);
        source.path = Logic.scriptPath(dir);
        source.reload();
        sweep.script = source.text();
        Keeper.prepare();
    }

    // A cheap first look (an empty or unreadable plugin.json counts as
    // missing): the script checks again, for real, after its grace period
    function manifestPresent() {
        if (!sweep.manifest)
            return true;
        probe.path = sweep.manifest;
        probe.reload();
        return probe.text() !== "";
    }

    function run() {
        if (!sweep.script)
            return false;
        // keeper.js starts it outside this plugin's lifetime and finishes
        // the job once it exits (this object is gone by then)
        const proc = Keeper.sweep(Logic.sweepArgv(sweep.pluginDir), sweep.script, {
            "settings": SettingsData,
            "toasts": ToastService,
            "pluginId": sweep.pluginId,
            "doneText": I18n.trFor("browserGlass", "Browser Glass removed: browsers restored"),
            "failedText": I18n.trFor("browserGlass", "Browser Glass removed, but restoring the browsers failed")
        });
        if (!proc)
            return false;
        sweep.swept = true;
        return true;
    }

    Component.onCompleted: capture()

    Component.onDestruction: {
        if (manifestPresent())
            return;
        run();
    }
}

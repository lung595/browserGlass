import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "components"
import "components/logic.js" as Logic

// Keeps the browsers' glass in step with DMS: runs `browserglass.py sync`
// (debounced, one at a time) when the plugin settings, DMS blur, the light
// or dark mode, the niri window rules or the DMS colours change. Shares the
// outcome with the settings page and the bar widget through PluginGlobalVar
// (names in components/logic.js), polls `status` only while a browser must
// restart, and shows the toasts logic.js decides.
// Disabling the plugin runs `uninstall`; deleting its folder runs it from
// the script text kept in memory (components/UninstallSweep.qml).
// `dms ipc call browserGlass sync | status | toggle | excludeClipboard | report`
PluginComponent {
    id: root

    readonly property string syncId: "browserGlass.sync"
    readonly property string statusId: "browserGlass.status"
    readonly property string sitesId: "browserGlass.sites"
    readonly property string reportId: "browserGlass.report"
    readonly property string pasteId: "browserGlass.paste"
    readonly property var procIds: [syncId, statusId, sitesId, reportId, pasteId]

    // Captured at load: DMS forgets a plugin's path once it is unloaded
    property string pluginDir: ""
    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")
    readonly property string cacheHome: Quickshell.env("XDG_CACHE_HOME") || (home + "/.cache")

    // Sync bookkeeping (logic.js), toast memory, the settings of the last
    // launched sync
    property var book: Logic.newSyncBook()
    property var toastCtx: Logic.newToastContext()
    property string lastSettingsText: ""
    property string syncError: ""
    property string statusError: ""
    // Failed status reads in a row (the restart poll stops at
    // Logic.MAX_STATUS_FAILURES)
    property int statusFailures: 0
    property bool started: false

    readonly property bool restartNeeded: restartNeededVar.value === true
    readonly property bool polling: pollTimer.running

    PluginGlobalVar {
        id: glassActiveVar
        varName: "glassActive"
        defaultValue: false
    }
    PluginGlobalVar {
        id: restartNeededVar
        varName: "restartNeeded"
        defaultValue: false
    }
    PluginGlobalVar {
        id: statusVar
        varName: "status"
        defaultValue: null
    }
    PluginGlobalVar {
        id: lastSyncVar
        varName: "lastSync"
        defaultValue: null
    }
    PluginGlobalVar {
        id: sitesVar
        varName: "sites"
        defaultValue: null
    }
    PluginGlobalVar {
        id: lastErrorVar
        varName: "lastError"
        defaultValue: ""
    }
    PluginGlobalVar {
        id: syncingVar
        varName: "syncing"
        defaultValue: false
    }

    UninstallSweep {
        id: sweep
        pluginId: root.pluginId
    }

    // --- Sync ----------------------------------------------------------------

    function currentSettingsText() {
        return Logic.settingsJson(root.pluginData, SettingsData.blurEnabled, SessionData.isLightMode);
    }

    // A shared variable is written only when its value changes: every write
    // notifies the settings page and each bar widget
    function publish(variable, value) {
        if (JSON.stringify(variable.value) !== JSON.stringify(value))
            variable.set(value);
    }

    // Asks for a sync; requests close together collapse into one
    function requestSync(reason) {
        if (!root.pluginDir)
            return false;
        const r = Logic.syncRequest(root.book, reason || "request", Date.now(), Logic.SYNC_DEBOUNCE_MS);
        root.book = r.book;
        root.publish(syncingVar, true);
        if (r.schedule)
            root.launchSync(Logic.SYNC_DEBOUNCE_MS);
        return true;
    }

    // A settings input changed: sync only when the --settings text differs
    // (SliderSetting saves its default on load, for one)
    function settingsChanged(reason) {
        if (!root.started)
            return;
        if (root.currentSettingsText() === root.lastSettingsText)
            return;
        root.requestSync(reason);
    }

    function launchSync(waitMs) {
        const text = root.currentSettingsText();
        root.lastSettingsText = text;
        Proc.runCommand(root.syncId, Logic.syncArgv(root.pluginDir, text), (stdout, exitCode) => root.syncDone(stdout, exitCode), waitMs, 60000, root);
    }

    function syncDone(stdout, exitCode) {
        const outcome = Logic.parseSync(stdout, exitCode);
        const busy = !outcome.ok && Logic.isBusyError(outcome.error);
        const f = Logic.syncFinished(root.book, Date.now(), busy);
        root.book = f.book;
        const t = Logic.syncToasts(outcome, root.toastCtx, f.schedule);
        root.toastCtx = t.ctx;
        root.showToasts(t.toasts);
        if (outcome.ok) {
            root.syncError = "";
            root.publish(lastSyncVar, outcome.result);
            root.publish(glassActiveVar, outcome.result.glass);
        } else if (!f.schedule) {
            root.syncError = outcome.error;
        }
        root.publishError();
        if (f.schedule) {
            root.launchSync(f.retry ? Logic.BUSY_RETRY_MS : Logic.SYNC_DEBOUNCE_MS);
            return;
        }
        root.publish(syncingVar, false);
        root.refreshStatus();
    }

    // --- Status and sites ----------------------------------------------------

    // A status read unless a sync is pending (its end reads one anyway)
    function refreshStatusIfIdle() {
        if (root.book.phase !== "idle")
            return false;
        return root.refreshStatus();
    }

    function refreshStatus() {
        if (!root.pluginDir)
            return false;
        Proc.runCommand(root.statusId, Logic.statusArgv(root.pluginDir), (stdout, exitCode) => root.statusDone(stdout, exitCode), 0, 15000, root);
        return true;
    }

    function statusDone(stdout, exitCode) {
        const parsed = Logic.parseStatus(stdout, exitCode);
        if (!parsed.ok) {
            root.statusError = parsed.error;
            root.publishError();
            // The poll must not run forever on a status that keeps failing
            root.statusFailures++;
            if (root.statusFailures >= Logic.MAX_STATUS_FAILURES)
                root.publish(restartNeededVar, false);
            return;
        }
        root.statusFailures = 0;
        root.statusError = "";
        root.publishError();
        root.publish(statusVar, parsed.status);
        root.publish(glassActiveVar, parsed.glassActive);
        root.publish(restartNeededVar, parsed.restartNeeded);
        const d = Logic.statusDecision(parsed, root.toastCtx);
        root.toastCtx = d.ctx;
        root.showToasts(d.toasts);
        if (d.resync)
            root.requestSync(Logic.WARN_RULE_STALE);
    }

    function loadSites() {
        if (!root.pluginDir)
            return false;
        Proc.runCommand(root.sitesId, Logic.sitesArgv(root.pluginDir), (stdout, exitCode) => {
            const parsed = Logic.parseSites(stdout, exitCode);
            if (parsed.ok)
                root.publish(sitesVar, parsed.sites);
        }, 0, 15000, root);
        return true;
    }

    function publishError() {
        root.publish(lastErrorVar, root.syncError || root.statusError);
    }

    // --- Actions (bar widget, settings page, IPC) ----------------------------

    function savePluginData(key, value) {
        const service = root.pluginService || PluginService;
        service.savePluginData(Logic.PLUGIN_ID, key, value);
    }

    // Turns glass on or off (not an uninstall); returns the new state
    function toggleGlass() {
        const next = !Logic.buildSettings(root.pluginData, SettingsData.blurEnabled, SessionData.isLightMode).glassEnabled;
        root.savePluginData("glassEnabled", next);
        return next;
    }

    // Excludes the host of the URL on the clipboard
    function excludeClipboard() {
        Proc.runCommand(root.pasteId, [Proc.dmsBin, "cl", "paste"], (stdout, exitCode) => {
            const r = Logic.excludeFromClipboard(exitCode === 0 ? stdout : "", root.pluginData.excludedSites);
            if (r.reason === "added") {
                root.savePluginData("excludedSites", r.list);
                root.toast("info", "Site excluded from glass", r.domain);
            } else if (r.reason === "already") {
                root.toast("info", "Site already excluded", r.domain);
            } else {
                root.toast("warning", "The clipboard holds no web address", "");
            }
        }, 0, 5000, root);
        return true;
    }

    // What PluginService.togglePlugin() calls (the same as the IPC toggle)
    function toggle() {
        return root.toggleGlass();
    }

    // Copies the anonymous report to the clipboard
    function copyReport() {
        if (!root.pluginDir)
            return false;
        Proc.runCommand(root.reportId, Logic.reportArgv(root.pluginDir), (stdout, exitCode) => {
            if (exitCode !== 0) {
                root.toast("error", "Could not build the report", Logic.errorText(stdout, exitCode));
                return;
            }
            // "--": the text is never read as an option
            Quickshell.execDetached([Proc.dmsBin, "cl", "copy", "--", stdout]);
            root.toast("info", "Report copied to the clipboard", "");
        }, 0, 15000, root);
        return true;
    }

    // --- Toasts --------------------------------------------------------------

    // `text` is translated; `details` (error text, a domain) is shown as is,
    // unless detailsTr is true: then it is a source string too
    function toast(level, text, details, detailsTr) {
        const message = I18n.trFor("browserGlass", text);
        const more = details ? (detailsTr === true ? I18n.trFor("browserGlass", String(details)) : String(details)) : "";
        if (level === "error")
            ToastService.showError(message, more, "", Logic.PLUGIN_ID);
        else if (level === "warning")
            ToastService.showWarning(message, more, "", Logic.PLUGIN_ID);
        else
            ToastService.showInfo(message, more, "", Logic.PLUGIN_ID);
    }

    function showToasts(list) {
        for (let i = 0; i < list.length; i++)
            root.toast(list[i].level, list[i].text, list[i].details, list[i].detailsTr === true);
    }

    // --- Triggers ------------------------------------------------------------

    onPluginDataChanged: settingsChanged("settings")

    Connections {
        target: SettingsData
        function onBlurEnabledChanged() {
            root.settingsChanged("blur");
        }
    }

    Connections {
        target: SessionData
        function onIsLightModeChanged() {
            root.settingsChanged("mode");
        }
    }

    // The global window opacity lives in DMS's niri rules
    FileView {
        id: windowRules
        path: root.configHome + "/niri/dms/windowrules.kdl"
        watchChanges: true
        printErrors: false
        onFileChanged: {
            reload();
            root.requestSync("windowrules");
        }
    }

    // The Material You colours (glass tint)
    FileView {
        id: colors
        path: root.cacheHome + "/dms/dms-colors.json"
        watchChanges: true
        printErrors: false
        onFileChanged: {
            reload();
            root.requestSync("colors");
        }
    }

    // Only while a running browser must restart: tells when it did
    Timer {
        id: pollTimer
        interval: Logic.POLL_INTERVAL_MS
        repeat: true
        running: root.restartNeeded && root.pluginDir !== ""
        onTriggered: root.refreshStatusIfIdle()
    }

    IpcHandler {
        target: "browserGlass"

        function sync(): string {
            return root.requestSync("ipc") ? "OK" : "plugin folder unknown";
        }
        // The last status (JSON); asks for a fresh one
        function status(): string {
            root.refreshStatus();
            const s = statusVar.value;
            return s ? JSON.stringify(s) : JSON.stringify({
                "error": "no status yet"
            });
        }
        function toggle(): string {
            return root.toggleGlass() ? "glass on" : "glass off";
        }
        function excludeClipboard(): string {
            root.excludeClipboard();
            return "OK";
        }
        function report(): string {
            return root.copyReport() ? "OK" : "plugin folder unknown";
        }
    }

    Component.onCompleted: {
        // A previous daemon (shell reload, re-enable) may have left these
        // mid-way: nothing of it runs any more
        root.publish(syncingVar, false);
        root.publish(lastErrorVar, "");
        const dir = PluginService.getPluginPath(root.pluginId) || Paths.strip(Qt.resolvedUrl("."));
        root.pluginDir = String(dir).replace(/\/+$/, "");
        root.requestSync("start");
        root.loadSites();
        root.started = true;
    }

    Component.onDestruction: {
        for (let i = 0; i < root.procIds.length; i++)
            Proc.release(root.procIds[i]);
        // "enabled" turns false only when the user disables the plugin, not
        // when the shell quits or reloads it; a deleted folder is the sweep's
        const enabled = SettingsData.getPluginSetting(Logic.PLUGIN_ID, "enabled", true);
        const action = Logic.teardownAction(enabled, sweep.manifestPresent(), true);
        if (action !== "uninstall" || !root.pluginDir)
            return;
        // The script waits up to 2 minutes for a running sync to finish
        Quickshell.execDetached(Logic.uninstallArgv(root.pluginDir));
        root.toast("info", "Browser Glass disabled: restoring the browsers", "");
    }
}

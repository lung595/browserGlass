import QtQuick
import Quickshell
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "components"
import "components/logic.js" as Logic
import "components/launcher.js" as Launcher

// Keeps the browsers' glass in step with DMS: runs `browserglass.py sync`
// (debounced, one at a time) when the plugin settings, DMS blur, the light
// or dark mode, the niri window rules or the DMS colours change. Shares the
// outcome with the settings page and the bar widget through PluginGlobalVar
// (names in components/logic.js), polls `status` only while a browser must
// restart, and shows the toasts logic.js decides.
// Disabling the plugin runs `uninstall`; deleting its folder runs it from
// the script text kept in memory (components/UninstallSweep.qml).
// The launcher's glass commands (BrowserGlassLauncher.qml) run here too:
// launcherAction() saves, syncs at once and toasts once the sync is done.
// `dms ipc call browserGlass sync | status | toggle | excludeClipboard |
// report | excludeCurrent | includeCurrent | glass <cmd>`
PluginComponent {
    id: root

    readonly property string syncId: "browserGlass.sync"
    readonly property string statusId: "browserGlass.status"
    readonly property string sitesId: "browserGlass.sites"
    readonly property string reportId: "browserGlass.report"
    readonly property string pasteId: "browserGlass.paste"
    readonly property string siteId: "browserGlass.site"
    readonly property var procIds: [syncId, statusId, sitesId, reportId, pasteId, siteId]

    // Captured at load: DMS forgets a plugin's path once it is unloaded
    property string pluginDir: ""
    readonly property string home: Quickshell.env("HOME") || ""
    readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")
    readonly property string cacheHome: Quickshell.env("XDG_CACHE_HOME") || (home + "/.cache")
    // The --settings JSON of the next sync goes there, never in the argv
    // ("" without a runtime folder: the argv then)
    readonly property string settingsFile: Logic.settingsFilePath(Quickshell.env("XDG_RUNTIME_DIR"))
    // Set by the settings file's saveFailed (synchronous, blockWrites)
    property bool settingsWriteFailed: false

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
    // The lastSync (JSON) whose pending add-on a status found loaded: the
    // sync that records it is asked for once (statusDone())
    property string companionResyncOf: ""

    // The launcher's current site: the last active-site answer ({key, at,
    // result}, key naming the niri window), the window key of the lookup in
    // flight and when it started, what waits for it (functions taking the
    // site) and the toasts of launcher actions waiting for their sync
    // (launcher.js toastFor())
    property var siteInfo: null
    property string siteLookupKey: ""
    property real siteLookupAt: 0
    property var siteWaiters: []
    property var pendingToasts: []

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

    // Asks for a sync without debounce (a launcher command)
    function syncNow(reason) {
        if (!root.pluginDir)
            return false;
        const r = Logic.syncRequestNow(root.book, reason || "launcher", Date.now());
        root.book = r.book;
        root.publish(syncingVar, true);
        if (r.schedule)
            root.launchSync(0);
        return true;
    }

    // A settings input changed: sync only when the --settings text differs
    // (SliderSetting saves its default on load, for one). Live control turned
    // off or on syncs at once: off then on within the debounce would be one
    // sync with it on, and only a sync with it off lets the add-on of a
    // profile where it was removed in the browser be placed again
    function settingsChanged(reason) {
        if (!root.started)
            return;
        const text = root.currentSettingsText();
        if (text === root.lastSettingsText)
            return;
        if (Logic.liveControlChanged(root.lastSettingsText, text))
            root.syncNow(reason);
        else
            root.requestSync(reason);
    }

    // The settings go in a file the sync reads and deletes (the excluded
    // sites stay out of /proc/PID/cmdline). Written at once (blockWrites):
    // a later call within the debounce rewrites it, and the one launch that
    // follows reads the last text. FileView skips a text equal to the one it
    // last wrote (the sync deleted that file since): it is emptied first, so
    // every launch writes. A failed write (either one) falls back to
    // --settings.
    function launchSync(waitMs) {
        const text = root.currentSettingsText();
        root.lastSettingsText = text;
        let file = root.settingsFile;
        if (file) {
            root.settingsWriteFailed = false;
            settingsFileView.setText("");
            settingsFileView.setText(text);
            if (root.settingsWriteFailed)
                file = "";
        }
        Proc.runCommand(root.syncId, Logic.syncArgv(root.pluginDir, text, file), (stdout, exitCode) => root.syncDoneSafe(stdout, exitCode), waitMs, 60000, root);
    }

    // Proc logs the command of a callback that throws: nothing may get out.
    // A failure leaves the bookkeeping idle, so the next request syncs.
    function syncDoneSafe(stdout, exitCode) {
        try {
            root.syncDone(stdout, exitCode);
        } catch (e) {
            try {
                root.book = Logic.newSyncBook();
                root.publish(syncingVar, false);
            } catch (e2) {}
        }
    }

    function syncDone(stdout, exitCode) {
        const outcome = Logic.parseSync(stdout, exitCode);
        const busy = !outcome.ok && Logic.isBusyError(outcome.error);
        const f = Logic.syncFinished(root.book, Date.now(), busy);
        root.book = f.book;
        const t = Logic.syncToasts(outcome, root.toastCtx, f.schedule);
        root.toastCtx = t.ctx;
        root.showToasts(f.schedule ? t.toasts : root.withPendingToasts(t.toasts, outcome));
        if (outcome.ok) {
            root.syncError = "";
            root.publish(lastSyncVar, outcome.result);
            root.publish(glassActiveVar, outcome.result.glass);
        } else if (!f.schedule) {
            root.syncError = outcome.error;
        }
        root.publishError();
        if (f.schedule) {
            root.launchSync(f.retry ? Logic.BUSY_RETRY_MS : (f.urgent ? 0 : Logic.SYNC_DEBOUNCE_MS));
            return;
        }
        root.publish(syncingVar, false);
        root.refreshStatus();
    }

    // The toasts of a finished sync with the launcher's waiting ones: a site
    // action's "applies after a restart" toast says it itself, so the
    // generic restart toast is left out then (kept when the action applied
    // live and another change still needs a restart). A failed sync shows
    // its error once even when syncToasts() left out a repeated one: the
    // action was saved but not applied
    function withPendingToasts(toasts, outcome) {
        const pending = root.pendingToasts;
        if (pending.length === 0)
            return toasts;
        root.pendingToasts = [];
        if (!outcome.ok) {
            if (Logic.isPluginGoneError(outcome.error) || toasts.some(x => x.level === "error"))
                return toasts;
            return toasts.concat([{
                    "level": "error",
                    "text": "Browser Glass sync failed",
                    "details": outcome.error
                }]);
        }
        const live = Logic.buildSettings(root.pluginData, SettingsData.blurEnabled, SessionData.isLightMode).liveControl;
        let list = toasts;
        const resolved = [];
        for (let i = 0; i < pending.length; i++) {
            const t = Launcher.toastFor(pending[i], outcome, live);
            if (!t)
                continue;
            resolved.push(t);
            if (Launcher.replacesRestartToast(t))
                list = list.filter(x => !Logic.isRestartToast(x));
        }
        return list.concat(resolved);
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
        else if (Logic.companionLoaded(lastSyncVar.value, parsed.status)) {
            // Once per sync outcome: a sync that fails leaves it shared
            const of = JSON.stringify(lastSyncVar.value);
            if (of !== root.companionResyncOf) {
                root.companionResyncOf = of;
                root.requestSync("companion");
            }
        }
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

    // What PluginService.togglePlugin() calls (the same as the IPC toggle),
    // through BrowserGlassLauncher.toggle(): DMS picks the launcher instance
    // first
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

    // --- Launcher (BrowserGlassLauncher.qml, IPC) ----------------------------

    // The niri window the launcher acts on: the focused one, else the last
    // focused (the launcher may hold the focus)
    function referenceWindow() {
        const list = NiriService.windows || [];
        const focused = list.find(w => w && w.is_focused);
        if (focused)
            return focused;
        return list.find(w => w && w.id === NiriService.lastFocusedWindowId) || null;
    }

    function windowKey(w) {
        return [w.id, w.pid, w.app_id, w.title].join("\n");
    }

    // The current site for the launcher's items: the answer for the
    // reference window when it is recent, else null (a lookup starts and the
    // launcher is asked to update once it is back). provisional (the
    // launcher's items): an older answer for the same window (same id, pid,
    // app-id and title) instead of null, marked provisional: true, while the
    // lookup runs. DMS's plugin view with an empty query (the Browse entry
    // of Browser Glass) never asks for its items again on
    // requestLauncherUpdate (DLauncherV2 Controller onRequestLauncherUpdate
    // returns on an empty query when no trigger matched), so its first
    // answer is what it shows: this answer makes it name the site whenever
    // one for the same window is kept (otherwise "Finding the current
    // site…", and Enter waits for the lookup). An action never runs on a
    // provisional answer.
    function siteFor(provisional) {
        const w = root.referenceWindow();
        if (!w)
            return {
                "error": "no_browser"
            };
        const key = root.windowKey(w);
        const info = root.siteInfo;
        if (info && info.key === key && Date.now() - info.at < Launcher.SITE_CACHE_MS)
            return info.result;
        root.lookupSite(w, key);
        if (provisional === true && info && info.key === key && info.result)
            return Object.assign({}, info.result, {
                "provisional": true
            });
        return null;
    }

    function lookupSite(w, key) {
        if (!root.pluginDir) {
            root.siteDone(key, {
                "error": "failed"
            });
            return false;
        }
        // One lookup at a time: Proc hands a running command's output to the
        // callback of the last runCommand with its id. The timeout ends it;
        // the margin covers a callback that never came.
        if (root.siteLookupKey !== "" && Date.now() - root.siteLookupAt < 2 * Launcher.SITE_WAIT_MS)
            return true;
        root.siteLookupKey = key;
        root.siteLookupAt = Date.now();
        // Proc logs the command of a callback that throws, so nothing may
        // get out of this one (the argv holds the window id, never the title)
        Proc.runCommand(root.siteId, Logic.activeSiteArgv(root.pluginDir, w), (stdout, exitCode) => root.siteDoneSafe(key, stdout, exitCode), 0, Launcher.SITE_WAIT_MS, root);
        return true;
    }

    function siteDoneSafe(key, stdout, exitCode) {
        try {
            root.siteDone(key, Logic.parseActiveSite(stdout, exitCode));
        } catch (e) {
            try {
                root.siteDone(key, {
                    "error": "failed"
                });
            } catch (e2) {}
        }
    }

    function siteDone(key, result) {
        root.siteInfo = {
            "key": key,
            "at": Date.now(),
            "result": result
        };
        if (root.siteLookupKey === key)
            root.siteLookupKey = "";
        // The window changed meanwhile: what waits wants the new one's site
        const w = root.referenceWindow();
        if (root.siteWaiters.length > 0 && w && root.windowKey(w) !== key)
            root.lookupSite(w, root.windowKey(w));
        else
            root.resolveSiteWaiters(result);
        (root.pluginService || PluginService).requestLauncherUpdate(Logic.PLUGIN_ID);
    }

    function resolveSiteWaiters(result) {
        siteWait.stop();
        const waiters = root.siteWaiters;
        root.siteWaiters = [];
        for (let i = 0; i < waiters.length; i++)
            waiters[i](result);
    }

    // Calls fn(site) with the current site, at once when it is known, else
    // when the lookup is back (at most Launcher.SITE_WAIT_MS: then "failed")
    function withSite(fn) {
        const site = root.siteFor();
        if (site !== null) {
            fn(site);
            return;
        }
        root.siteWaiters = root.siteWaiters.concat([fn]);
        if (!siteWait.running)
            siteWait.start();
    }

    // A glass command by name ("on", "off", "blist" or "fix", "unblist",
    // "list"), as the launcher's items and the IPC give it; false when the
    // name is unknown
    function glassCommand(cmd) {
        const c = Launcher.commandOf(cmd);
        if (c === "on" || c === "off") {
            root.launcherAction({
                "kind": c
            });
        } else if (c === "blist" || c === "unblist") {
            root.withSite(site => root.launcherAction(Object.assign({}, site, {
                "kind": c
            })));
        } else if (c === "list") {
            root.reopenList();
        } else {
            return false;
        }
        return true;
    }

    // Runs a launcher action (launcher.js planAction(): {kind, domain, host,
    // source, age, error}): its toasts now, its save with a sync at once, its
    // toast once that sync is done
    function launcherAction(a) {
        const plan = Launcher.planAction(a, root.pluginData.excludedSites);
        root.showToasts(plan.toasts);
        if (plan.save) {
            if (plan.pending)
                root.pendingToasts = root.pendingToasts.concat([plan.pending]);
            root.savePluginData(plan.save.key, plan.save.value);
            root.syncNow("launcher");
        }
        if (plan.reopen)
            root.reopenList();
        return plan.save !== null;
    }

    // Shows "glass list" again, once the launcher that ran the item closed
    function reopenList() {
        Qt.callLater(() => PopoutService.openDankLauncherV2WithQuery(Launcher.LIST_QUERY, false));
    }

    // Only while an action waits for the current site
    Timer {
        id: siteWait
        interval: Launcher.SITE_WAIT_MS
        repeat: false
        onTriggered: root.resolveSiteWaiters({
            "error": "failed"
        })
    }

    // --- Toasts --------------------------------------------------------------

    // `text` is translated; `details` (error text, a domain) is shown as is,
    // unless detailsTr is true: then it is a source string too. textArg and
    // detailsArg fill their text's "%1".
    function toast(level, text, details, detailsTr, textArg, detailsArg) {
        let message = I18n.trFor("browserGlass", text);
        if (textArg)
            message = message.arg(textArg);
        let more = details ? (detailsTr === true ? I18n.trFor("browserGlass", String(details)) : String(details)) : "";
        if (more && detailsArg)
            more = more.arg(detailsArg);
        if (level === "error")
            ToastService.showError(message, more, "", Logic.PLUGIN_ID);
        else if (level === "warning")
            ToastService.showWarning(message, more, "", Logic.PLUGIN_ID);
        else
            ToastService.showInfo(message, more, "", Logic.PLUGIN_ID);
    }

    function showToasts(list) {
        for (let i = 0; i < list.length; i++)
            root.toast(list[i].level, list[i].text, list[i].details, list[i].detailsTr === true, list[i].textArg || "", list[i].detailsArg || "");
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

    // The settings of the next sync (launchSync()): written only, never read
    // or watched
    FileView {
        id: settingsFileView
        path: root.settingsFile
        preload: false
        blockWrites: true
        printErrors: false
        onSaveFailed: root.settingsWriteFailed = true
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
        // The launcher's commands, for keybindings
        function excludeCurrent(): string {
            root.glassCommand("blist");
            return "OK";
        }
        function includeCurrent(): string {
            root.glassCommand("unblist");
            return "OK";
        }
        function glass(cmd: string): string {
            return root.glassCommand(cmd) ? "OK" : "unknown command: " + cmd;
        }
    }

    Component.onCompleted: {
        // A previous daemon (shell reload, re-enable) may have left these
        // mid-way: nothing of it runs any more
        root.publish(syncingVar, false);
        root.publish(lastErrorVar, "");
        const dir = PluginService.getPluginPath(root.pluginId) || Paths.strip(Qt.resolvedUrl("."));
        root.pluginDir = String(dir).replace(/\/+$/, "");
        // The launcher answers without a trigger ("glass ..." or "gs ...");
        // saved once, so a user's choice stays (noTrigger is no sync input)
        const service = root.pluginService || PluginService;
        if (service.loadPluginData(Logic.PLUGIN_ID, "noTrigger", null) === null)
            service.savePluginData(Logic.PLUGIN_ID, "noTrigger", true);
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

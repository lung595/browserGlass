import QtQuick
import qs.Common
import qs.Services
import "components/logic.js" as Logic
import "components/launcher.js" as Launcher

// The launcher's glass commands: "glass" or "gs", then on, off, blist (fix),
// unblist or list (components/launcher.js). DMS asks for items with the raw
// query (the daemon saves noTrigger: true) and runs the one picked; the
// daemon does the work (launcherAction()) and knows the current site
// (siteFor(): it asks for an update once an answer is back, which DMS's
// Browse view with an empty query ignores; meanwhile an older answer for the
// same window is shown, provisional).
Item {
    id: root

    property var pluginService: null
    property string pluginId: "browserGlass"
    property string trigger: "glass"

    signal itemsChanged

    readonly property var service: root.pluginService || PluginService

    function daemon() {
        const d = root.service.pluginDaemonInstances ? root.service.pluginDaemonInstances[Logic.PLUGIN_ID] : null;
        return d || null;
    }

    function setting(key, fallback) {
        return root.service.loadPluginData(Logic.PLUGIN_ID, key, fallback);
    }

    function tr(text, arg) {
        const t = I18n.trFor("browserGlass", text);
        return arg ? t.arg(arg) : t;
    }

    function getItems(query) {
        // The plugin view (Browse entry, Plugins tab) also takes the bare
        // command words and lists every site: only the call stack tells it
        // from the global search
        const parsed = Launcher.parseQuery(query);
        const view = (parsed === null || Launcher.isListQuery(parsed)) && Launcher.fromPluginView(new Error().stack);
        const q = Launcher.queryFor(query, view);
        if (q === null)
            return [];
        const d = root.daemon();
        const state = {
            "site": Launcher.needsSite(q) && d ? d.siteFor(true) : null,
            "excludedSites": root.setting("excludedSites", []),
            "glassEnabled": root.setting("glassEnabled", true) !== false
        };
        const items = Launcher.itemsFor(query, state, view);
        return items.map(it => Object.assign({}, it, {
                "name": it.nameTr ? root.tr(it.name, it.nameArg) : it.name,
                "comment": it.comment ? root.tr(it.comment, it.commentArg) : ""
            }));
    }

    // What PluginService.togglePlugin() calls (dms ipc call plugins toggle
    // browserGlass): with a launcher component it picks this instance over
    // the daemon, so this forwards to the daemon's toggle()
    function toggle() {
        const d = root.daemon();
        return d ? d.toggle() : false;
    }

    function executeItem(item) {
        const d = root.daemon();
        if (!item || !d)
            return;
        if (item.bgSite)
            d.launcherAction(Object.assign({}, item.bgSite, {
                "kind": item.bgCmd
            }));
        else if (item.bgCmd !== "none")
            d.glassCommand(item.bgCmd);
    }
}

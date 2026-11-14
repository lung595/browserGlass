pragma ComponentBehavior: Bound
import QtQuick
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "components"
import "components/logic.js" as Logic

// Bar widget: the glass state as an icon (blur_on / blur_off), with a dot
// while a running browser must restart. Its popout shows the status and
// offers the glass switch (pluginData "glassEnabled": not an uninstall),
// "Exclude copied URL" (the daemon's excludeClipboard) and the settings.
// Every value comes from the daemon's PluginGlobalVar (components/logic.js).
PluginComponent {
    id: root

    // Direct children: PluginGlobalVar reads its parent's pluginId
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
        id: lastErrorVar
        varName: "lastError"
        defaultValue: ""
    }
    PluginGlobalVar {
        id: syncingVar
        varName: "syncing"
        defaultValue: false
    }

    readonly property bool glassActive: glassActiveVar.value === true
    readonly property bool restartNeeded: restartNeededVar.value === true
    readonly property var status: statusVar.value ?? null
    readonly property string lastError: typeof lastErrorVar.value === "string" ? lastErrorVar.value : ""
    readonly property bool syncing: syncingVar.value === true
    // The user's switch (what the toggle shows), not whether glass is on
    readonly property bool glassEnabled: Logic.buildSettings(root.pluginData, true, false).glassEnabled
    readonly property string iconName: root.glassActive ? "blur_on" : "blur_off"
    readonly property var daemon: PluginService.pluginDaemonInstances[Logic.PLUGIN_ID] ?? null
    readonly property bool daemonAvailable: root.daemon !== null && typeof root.daemon.excludeClipboard === "function"

    // Glass on or off; the daemon syncs on the pluginData change
    function setGlassEnabled(on) {
        const service = root.pluginService || PluginService;
        service.savePluginData(Logic.PLUGIN_ID, "glassEnabled", on === true);
    }

    // The daemon reads the clipboard and saves the host (toasts included)
    function excludeClipboard() {
        if (!root.daemonAvailable)
            return false;
        root.daemon.excludeClipboard();
        return true;
    }

    function openSettings() {
        root.closePopout();
        PopoutService.openSettingsWithTab("plugin:" + Logic.PLUGIN_ID);
    }

    horizontalBarPill: Component {
        WidgetPill {
            widget: root
        }
    }

    verticalBarPill: Component {
        WidgetPill {
            widget: root
        }
    }

    popoutContent: Component {
        GlassPopout {
            widget: root
        }
    }

    popoutWidth: 360
}

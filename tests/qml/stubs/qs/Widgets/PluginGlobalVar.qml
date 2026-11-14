import QtQuick
import qs.Services

// DMS's PluginGlobalVar, as it is (minus the logger): a value shared by every
// component of a plugin, keyed by the parent's pluginId
Item {
    id: root

    required property string varName
    property var defaultValue: undefined

    readonly property var value: {
        const pid = parent?.pluginId ?? "";
        if (!pid || !PluginService.globalVars[pid])
            return defaultValue;
        return PluginService.globalVars[pid][varName] ?? defaultValue;
    }

    function set(newValue) {
        const pid = parent?.pluginId ?? "";
        if (pid)
            PluginService.setGlobalVar(pid, varName, newValue);
        else
            console.warn("PluginGlobalVar: cannot set", varName, "- no pluginId from parent");
    }

    visible: false
    width: 0
    height: 0
}

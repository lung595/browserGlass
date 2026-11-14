import QtQuick
import qs.Common
import qs.Widgets

// Stand-in for DMS's PluginSettings, same logic as the real one: the setting
// widgets find it up their parent chain and load and save through
// pluginService (PluginService in a test), so PluginService.saves and
// SettingsData.pluginSettings show what the page wrote. Items declared in it
// are moved into its column, as in DMS.
Item {
    id: root

    required property string pluginId
    property var pluginService: null
    default property list<QtObject> content

    signal settingChanged

    property var variants: []

    implicitHeight: settingsColumn.implicitHeight
    height: implicitHeight

    readonly property bool hasPermission: {
        if (!pluginService?.availablePlugins || !pluginId)
            return true;
        const plugin = pluginService.availablePlugins[pluginId];
        if (!plugin)
            return true;
        const permissions = Array.isArray(plugin.permissions) ? plugin.permissions : [];
        return permissions.indexOf("settings_write") !== -1;
    }

    onPluginServiceChanged: {
        if (pluginService)
            reloadChildValues();
    }

    onContentChanged: {
        for (let i = 0; i < content.length; i++) {
            const item = content[i];
            if (item instanceof Item)
                item.parent = settingsColumn;
        }
    }

    Connections {
        target: root.pluginService
        enabled: root.pluginService !== null
        function onPluginDataChanged(changedPluginId) {
            if (changedPluginId === root.pluginId)
                root.reloadChildValues();
        }
    }

    function reloadChildValues() {
        for (let i = 0; i < content.length; i++) {
            const child = content[i];
            if (child.loadValue)
                child.loadValue();
        }
    }
    function saveValue(key, value) {
        if (!pluginService)
            return;
        if (!hasPermission) {
            console.warn("Plugin", pluginId, "does not have settings_write permission");
            return;
        }
        pluginService.savePluginData(pluginId, key, value);
        settingChanged();
    }
    function loadValue(key, defaultValue) {
        if (pluginService && pluginService.loadPluginData)
            return pluginService.loadPluginData(pluginId, key, defaultValue);
        return defaultValue;
    }
    function saveState(key, value) {
        if (pluginService && pluginService.savePluginState)
            pluginService.savePluginState(pluginId, key, value);
    }
    function loadState(key, defaultValue) {
        if (pluginService && pluginService.loadPluginState)
            return pluginService.loadPluginState(pluginId, key, defaultValue);
        return defaultValue;
    }

    Column {
        id: settingsColumn
        width: parent.width
        spacing: Theme.spacingM
    }
}

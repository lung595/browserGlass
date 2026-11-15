pragma Singleton
import QtQuick

// The DMS settings the plugin reads, and DMS's per-plugin settings store
// (pluginSettings: plugin id -> {key: value}), which PluginService writes.
QtObject {
    id: root

    property bool blurEnabled: true
    property bool syncModeWithPortal: true
    property bool reduceMotion: false
    property var barConfigs: []
    property string pluginSettingsPath: "/tmp/fakehome/.config/dms/plugin_settings.json"
    property var pluginSettings: ({})
    // Every savePluginSettings(): the JSON text DMS would write to
    // plugin_settings.json
    property var pluginSettingsWrites: []

    // Deep copies (JSON), as DMS stores and hands out JSON round-trips: a
    // component mutating its pluginData (e.g. excluded.push()) never changes
    // the store behind DMS's back.
    function _copy(value) {
        return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    }
    function getPluginSetting(pluginId, key, defaultValue) {
        const p = pluginSettings[pluginId];
        if (!p || p[key] === undefined)
            return defaultValue;
        return _copy(p[key]);
    }
    function setPluginSetting(pluginId, key, value) {
        const next = Object.assign({}, pluginSettings);
        next[pluginId] = Object.assign({}, next[pluginId] || {});
        next[pluginId][key] = _copy(value);
        pluginSettings = next;
    }
    function getPluginSettingsForPlugin(pluginId) {
        return _copy(pluginSettings[pluginId] || {});
    }
    // DMS writes its whole map to plugin_settings.json
    function savePluginSettings() {
        pluginSettingsWrites = pluginSettingsWrites.concat([JSON.stringify(pluginSettings, null, 2)]);
    }
    function reset() {
        blurEnabled = true;
        syncModeWithPortal = true;
        pluginSettings = {};
        pluginSettingsWrites = [];
    }
}

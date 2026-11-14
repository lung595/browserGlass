pragma Singleton
import QtQuick
import qs.Common

// Stand-in for DMS's PluginService, with the real signatures: plugin data
// goes to SettingsData's store (as in DMS) and raises pluginDataChanged;
// global variables (what PluginGlobalVar reads) live in globalVars.
// saves records every savePluginData: [[pluginId, key, value], ...].
QtObject {
    signal pluginDataChanged(string pluginId)
    signal globalVarChanged(string pluginId, string varName)
    signal pluginLoaded(string pluginId)
    signal pluginUnloaded(string pluginId)

    property var globalVars: ({})
    // Plugin id -> manifest; PluginSettings reads its permissions
    property var availablePlugins: ({})
    property var pluginDaemonInstances: ({})
    // Plugin id -> folder, what getPluginPath() answers
    property var pluginPaths: ({})
    property var pluginStates: ({})
    property var saves: []

    function savePluginData(pluginId, key, value) {
        SettingsData.setPluginSetting(pluginId, key, value);
        saves = saves.concat([[pluginId, key, value]]);
        pluginDataChanged(pluginId);
        return true;
    }
    function loadPluginData(pluginId, key, defaultValue) {
        return SettingsData.getPluginSetting(pluginId, key, defaultValue);
    }
    function getGlobalVar(pluginId, varName, defaultValue) {
        if (globalVars[pluginId] && varName in globalVars[pluginId])
            return globalVars[pluginId][varName];
        return defaultValue;
    }
    function setGlobalVar(pluginId, varName, value) {
        const next = Object.assign({}, globalVars);
        next[pluginId] = Object.assign({}, next[pluginId] || {});
        next[pluginId][varName] = value;
        globalVars = next;
        globalVarChanged(pluginId, varName);
    }
    function getPluginVariants(pluginId) {
        return [];
    }
    function getPluginPath(pluginId) {
        return pluginPaths[pluginId] || "";  // real DMS answers "" for an unknown id
    }
    function isPluginLoaded(pluginId) {
        return pluginDaemonInstances[pluginId] !== undefined;
    }
    function loadPluginState(pluginId, key, defaultValue) {
        const s = pluginStates[pluginId];
        return s && s[key] !== undefined ? s[key] : defaultValue;
    }
    function savePluginState(pluginId, key, value) {
        const next = Object.assign({}, pluginStates);
        next[pluginId] = Object.assign({}, next[pluginId] || {});
        next[pluginId][key] = value;
        pluginStates = next;
    }
    function reset() {
        globalVars = {};
        pluginStates = {};
        saves = [];
    }
}

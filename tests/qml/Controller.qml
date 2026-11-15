import QtQuick

// Stand-in for DMS's launcher controller (Modals/DLauncherV2/Controller.qml):
// the same file and function names, so a plugin's getItems() sees the call
// stack it sees in DMS. performSearch() is the plugin view (the Browse entry
// of one plugin, the Plugins tab); _performPluginPhase() the global search
// and the home page; _pluginQueryItems() a typed global query.
QtObject {
    function performSearch(launcher, query) {
        return launcher.getItems(query);
    }
    function _performPluginPhase(launcher, query) {
        return launcher.getItems(query);
    }
    function _pluginQueryItems(launcher, query) {
        return launcher.getItems(query);
    }
}

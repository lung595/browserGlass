pragma Singleton
import QtQuick

// Stand-in for DMS's PopoutService: records the settings tabs asked for.
// opened: ["plugin:browserGlass", ...]; launcherQueries: the launcher
// reopened with a query (openDankLauncherV2WithQuery), ["glass list", ...]
QtObject {
    property var opened: []
    property var launcherQueries: []

    function openSettingsWithTab(tabName, returnOrigin, reopen) {
        opened = opened.concat([tabName]);
    }
    function openSettings() {
        opened = opened.concat([""]);
    }
    function openDankLauncherV2WithQuery(query, triggerUsesOverlayLayer) {
        launcherQueries = launcherQueries.concat([query]);
    }
    function reset() {
        opened = [];
        launcherQueries = [];
    }
}

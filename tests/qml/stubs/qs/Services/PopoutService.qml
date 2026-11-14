pragma Singleton
import QtQuick

// Stand-in for DMS's PopoutService: records the settings tabs asked for.
// opened: ["plugin:browserGlass", ...]
QtObject {
    property var opened: []

    function openSettingsWithTab(tabName, returnOrigin, reopen) {
        opened = opened.concat([tabName]);
    }
    function openSettings() {
        opened = opened.concat([""]);
    }
    function reset() {
        opened = [];
    }
}

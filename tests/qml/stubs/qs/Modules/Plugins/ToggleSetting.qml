import QtQuick
import qs.Common
import qs.Widgets
import "SettingsUtils.js" as Utils

// DMS's ToggleSetting logic: loads on the next turn of the event loop, then
// saves every change of `value` (a test flips it by assigning value)
Item {
    id: root

    required property string settingKey
    required property string label
    property string description: ""
    property bool defaultValue: false
    property bool value: defaultValue
    property bool isInitialized: false

    width: parent ? parent.width : 0
    height: 48

    function loadValue() {
        const settings = Utils.findSettings(root.parent);
        if (settings && settings.pluginService) {
            value = settings.loadValue(settingKey, defaultValue);
            isInitialized = true;
        }
    }
    Component.onCompleted: Qt.callLater(loadValue)
    onValueChanged: {
        if (!isInitialized)
            return;
        const settings = Utils.findSettings(root.parent);
        if (settings)
            settings.saveValue(settingKey, value);
    }

    StyledText {
        text: root.label
    }
}

import QtQuick
import qs.Common
import qs.Widgets
import "SettingsUtils.js" as Utils

// DMS's StringSetting logic: loads on the next turn of the event loop and
// saves on commit() (focus loss or Enter in DMS). A test types by setting
// `text`, then calls commit().
Item {
    id: root

    required property string settingKey
    required property string label
    property string description: ""
    property string placeholder: ""
    property string defaultValue: ""
    property string value: defaultValue
    property string text: ""
    property bool isInitialized: false

    width: parent ? parent.width : 0
    height: 48

    function loadValue() {
        const settings = Utils.findSettings(root.parent);
        if (settings && settings.pluginService) {
            const loaded = settings.loadValue(settingKey, defaultValue);
            value = loaded;
            text = loaded;
            isInitialized = true;
        }
    }
    Component.onCompleted: Qt.callLater(loadValue)
    function commit() {
        if (!isInitialized || text === value)
            return;
        value = text;
        const settings = Utils.findSettings(root.parent);
        if (settings)
            settings.saveValue(settingKey, value);
    }

    StyledText {
        text: root.label + ": " + (root.text || root.placeholder)
    }
}

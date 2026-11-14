import QtQuick
import qs.Common
import qs.Widgets
import "SettingsUtils.js" as Utils

// DMS's ListSetting logic: loads `items` when built, saves every later change
Column {
    id: root

    required property string settingKey
    required property string label
    property string description: ""
    property var defaultValue: []
    property var items: defaultValue
    property Component delegate: null
    property bool isLoading: false
    property bool _loaded: false

    width: parent ? parent.width : 0

    function loadValue() {
        const settings = Utils.findSettings(root.parent);
        if (settings) {
            isLoading = true;
            items = settings.loadValue(settingKey, defaultValue);
            isLoading = false;
        }
        _loaded = true;
    }
    Component.onCompleted: loadValue()
    onItemsChanged: {
        if (isLoading || !_loaded)
            return;
        const settings = Utils.findSettings(root.parent);
        if (settings)
            settings.saveValue(settingKey, items);
    }
    function addItem(item) {
        items = items.concat([item]);
    }
    function removeItem(index) {
        const next = items.slice();
        next.splice(index, 1);
        items = next;
    }

    StyledText {
        text: root.label + " (" + root.items.length + ")"
    }
}

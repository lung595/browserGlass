import QtQuick
import qs.Common
import qs.Widgets
import "SettingsUtils.js" as Utils

// DMS's SelectionSetting logic: loads when built and saves every change of
// `value`, including the load itself (as DMS does)
Item {
    id: root

    required property string settingKey
    required property string label
    property string description: ""
    required property var options
    property string defaultValue: ""
    property string value: defaultValue

    width: parent ? parent.width : 0
    height: 48

    readonly property var optionLabels: options.map(o => o.label || o)
    readonly property var valueToLabel: {
        const map = {};
        for (const o of options) {
            if (typeof o === "object")
                map[o.value] = o.label;
            else
                map[o] = o;
        }
        return map;
    }
    readonly property var labelToValue: {
        const map = {};
        for (const o of options) {
            if (typeof o === "object")
                map[o.label] = o.value;
            else
                map[o] = o;
        }
        return map;
    }
    // Test helper: what picking the option labelled `label` does
    function choose(label) {
        value = labelToValue[label] !== undefined ? labelToValue[label] : label;
    }

    function loadValue() {
        const settings = Utils.findSettings(root.parent);
        if (settings && settings.pluginService)
            value = settings.loadValue(settingKey, defaultValue);
    }
    Component.onCompleted: loadValue()
    onValueChanged: {
        const settings = Utils.findSettings(root.parent);
        if (settings)
            settings.saveValue(settingKey, value);
    }

    StyledText {
        text: root.label + ": " + (root.valueToLabel[root.value] || root.value)
    }
}

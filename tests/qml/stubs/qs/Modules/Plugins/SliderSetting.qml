import QtQuick
import qs.Common
import qs.Widgets
import "SettingsUtils.js" as Utils

// DMS's SliderSetting logic: loads when built, saves every change of `value`
Item {
    id: root

    required property string settingKey
    required property string label
    property string description: ""
    property int defaultValue: 0
    property int value: defaultValue
    property int minimum: 0
    property int maximum: 100
    property string startIcon: ""
    property string endIcon: ""
    property string unit: ""

    width: parent ? parent.width : 0
    height: 48

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
        text: root.label + ": " + root.value + root.unit
    }
}

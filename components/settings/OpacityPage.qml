import QtQuick
import qs.Common
import qs.Widgets
import qs.Modules.Plugins

// How see-through the browsers are: the DMS opacity, or one of their own.
CategoryPage {
    id: page
    category: "opacity"

    required property var settings
    // The slider shows only with the override on (the settings page hides it from the search too)
    readonly property bool override: overrideToggle.value

    StyledText {
        objectName: "dmsOpacity"
        visible: page.shown("dmsOpacity")
        width: parent.width
        text: page.settings.dmsOpacityText()
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeMedium
        color: Theme.surfaceText
    }

    ToggleSetting {
        id: overrideToggle
        objectName: "opacityOverride"
        visible: page.shown("opacityOverride")
        settingKey: "opacityOverride"
        label: page.label("opacityOverride")
        description: page.help("opacityOverride")
        defaultValue: false
    }

    SliderSetting {
        objectName: "opacity"
        visible: overrideToggle.value && page.shown("opacity")
        settingKey: "opacity"
        label: page.label("opacity")
        description: page.help("opacity")
        defaultValue: 85
        minimum: 20
        maximum: 100
        unit: "%"
    }
}

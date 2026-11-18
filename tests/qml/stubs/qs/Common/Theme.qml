pragma Singleton
import QtQuick

// The DMS theme values the plugin's pages read, with the shell's dark defaults
QtObject {
    property bool isLightMode: false
    property color primary: "#C5E66A"
    property color primaryText: "#1B2600"
    property color primaryContainer: "#3A4D00"
    property color secondary: "#BFCBAD"
    property color tertiary: "#9FD3C7"
    property color error: "#FFB4AB"
    property color success: "#4CAF50"
    property color warning: "#FF9800"
    property color info: "#2196F3"
    property color errorText: "#690005"
    property color background: "#12140E"
    property color surface: "#12140E"
    property color surfaceVariant: "#45483C"
    property color surfaceContainer: "#1E201A"
    property color surfaceContainerHigh: "#282B24"
    property color surfaceContainerHighest: "#33362E"
    property color outline: "#909284"
    property color outlineVariant: "#45483C"
    property color surfaceText: "#E4E3DB"
    property color surfaceVariantText: "#C6C8B8"
    property real fontSizeSmall: 12
    property real fontSizeMedium: 14
    property real fontSizeLarge: 16
    property real fontSizeXLarge: 20
    property int fontWeightMedium: Font.Medium
    property int fontWeightBold: Font.Bold
    property real spacingXXS: 2
    property real spacingXS: 4
    property real spacingS: 8
    property real spacingM: 12
    property real spacingL: 16
    property real spacingXL: 24
    property real cornerRadius: 12
    property real cornerRadiusS: 8
    property real cornerRadiusFull: 9999
    property real buttonHeightXXS: 28
    property real outlineWidth: 1
    property string monoFontFamily: "monospace"
    property real iconSizeSmall: 16
    property real iconSizeMedium: 20
    property real iconSize: 24
    property real iconSizeLarge: 32
    function withAlpha(c, a) {
        return Qt.rgba(c.r, c.g, c.b, a);
    }
    function barIconSize(barThickness, offset, maximize, scale) {
        return Math.round((barThickness - 18 + (offset === undefined ? 0 : offset)) * (scale || 1));
    }
    function barTextSize(barThickness, scale, maximize) {
        return Math.round(fontSizeMedium * (scale || 1));
    }
}

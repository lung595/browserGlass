import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// A section title of the settings page (DMS has no section component): an
// icon, the title and an optional line under it, after a divider.
Column {
    id: header

    property string title: ""
    property string subtitle: ""
    property string iconName: ""
    property bool first: false

    width: parent ? parent.width : 0
    spacing: Theme.spacingXS
    topPadding: first ? 0 : Theme.spacingM

    Rectangle {
        visible: !header.first
        width: parent.width
        height: 1
        color: Theme.outline
        opacity: 0.3
    }

    Row {
        spacing: Theme.spacingS
        topPadding: header.first ? 0 : Theme.spacingS

        DIcon {
            visible: header.iconName !== ""
            name: header.iconName
            size: Theme.iconSize
            color: Theme.primary
            anchors.verticalCenter: parent.verticalCenter
        }

        StyledText {
            text: header.title
            font.pixelSize: Theme.fontSizeXLarge
            font.weight: Theme.fontWeightBold
            color: Theme.surfaceText
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    StyledText {
        visible: header.subtitle !== ""
        width: parent.width
        text: header.subtitle
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
        wrapMode: Text.WordWrap
    }
}

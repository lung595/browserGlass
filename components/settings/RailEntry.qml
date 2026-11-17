import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// One category of the rail. The open one sits behind a pane of glass (a
// see-through tint of the primary colour, a lit top edge); the others are
// bare. While a search filters, no pane shows, the categories with a match
// carry their count and the others fade. Only the opacity changes, and only
// for a moment.
Item {
    id: entry

    required property var view
    required property var modelData

    readonly property bool on: !view.filtering && view.current === modelData.id
    readonly property int badge: view.counts[modelData.id] || 0
    readonly property bool dim: view.filtering && badge === 0
    readonly property bool reduceMotion: SettingsData.reduceMotion

    objectName: "rail:" + modelData.id
    opacity: dim ? 0.38 : 1
    activeFocusOnTab: true

    Accessible.role: Accessible.PageTab
    Accessible.name: dim ? I18n.trFor("browserGlass", "%1, no match").arg(modelData.name) : modelData.name
    Accessible.selected: on
    Accessible.onPressAction: entry.choose()

    function choose() {
        entry.view.pick(modelData.id);
    }

    // 100 ms, then nothing runs; with Reduce motion it just cuts
    Behavior on opacity {
        enabled: !entry.reduceMotion
        NumberAnimation {
            duration: 100
            easing.type: Easing.OutCubic
        }
    }

    Keys.onReturnPressed: choose()
    Keys.onEnterPressed: choose()
    Keys.onSpacePressed: choose()

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        id: tap
        onTapped: entry.choose()
    }

    // The row: a pane of glass when open, a faint veil on hover or press
    Rectangle {
        id: pane
        anchors.fill: parent
        anchors.topMargin: 2
        anchors.bottomMargin: 2
        radius: Theme.cornerRadius
        color: entry.on ? Theme.withAlpha(Theme.primary, 0.14) : tap.pressed ? Theme.withAlpha(Theme.surfaceText, 0.10) : hover.hovered ? Theme.withAlpha(Theme.surfaceText, 0.05) : "transparent"
        border.width: entry.on || entry.activeFocus ? (entry.activeFocus ? 2 : 1) : 0
        border.color: entry.activeFocus ? Theme.primary : Theme.withAlpha(Theme.primary, 0.35)

        // The lit edge of the glass
        Rectangle {
            visible: entry.on
            x: parent.radius
            y: 1
            width: parent.width - parent.radius * 2
            height: 1
            color: Theme.withAlpha(Theme.surfaceText, 0.18)
        }
    }

    DIcon {
        id: icon
        x: entry.view.compact ? (entry.width - size) / 2 : 14
        anchors.verticalCenter: parent.verticalCenter
        name: entry.modelData.icon
        size: 20
        color: entry.on ? Theme.primary : Theme.surfaceText
    }

    StyledText {
        objectName: "railName"
        visible: !entry.view.compact
        anchors.left: icon.right
        anchors.leftMargin: Theme.spacingS + 2
        anchors.right: count.visible ? count.left : parent.right
        anchors.rightMargin: Theme.spacingS
        anchors.verticalCenter: parent.verticalCenter
        text: entry.modelData.name
        elide: Text.ElideRight
        wrapMode: Text.NoWrap
        font.pixelSize: Theme.fontSizeMedium
        font.weight: entry.on ? Font.DemiBold : Font.Normal
        color: entry.on ? Theme.primary : Theme.surfaceText
    }

    // Matches in this category: at the row's end, or on the icon's corner
    // when the rail is narrow
    Rectangle {
        id: count
        objectName: "railCount"
        visible: entry.view.filtering && entry.badge > 0
        x: entry.view.compact ? icon.x + icon.width - 8 : entry.width - width - Theme.spacingS
        y: entry.view.compact ? 4 : (entry.height - height) / 2
        width: Math.max(18, countText.implicitWidth + 8)
        height: 18
        radius: 9
        color: Theme.primary
        border.width: entry.view.compact ? 2 : 0
        border.color: Theme.surface
        StyledText {
            id: countText
            anchors.centerIn: parent
            text: entry.badge
            font.pixelSize: Theme.fontSizeSmall
            font.features: {
                "tnum": 1
            }
            font.weight: Font.DemiBold
            color: Theme.primaryText
        }
    }

    // A narrow rail shows icons only: the name appears beside it on hover or focus
    Rectangle {
        objectName: "railTip"
        visible: entry.view.compact && (hover.hovered || entry.activeFocus)
        z: 10
        x: entry.width + Theme.spacingXS
        anchors.verticalCenter: parent.verticalCenter
        width: tipText.implicitWidth + Theme.spacingS * 2
        height: 28
        radius: 8
        color: Theme.surfaceContainerHigh
        border.width: 1
        border.color: Theme.outline
        StyledText {
            id: tipText
            anchors.centerIn: parent
            text: entry.modelData.name
            wrapMode: Text.NoWrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceText
        }
    }
}

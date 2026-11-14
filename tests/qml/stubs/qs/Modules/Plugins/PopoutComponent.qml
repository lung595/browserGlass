import QtQuick
import qs.Common
import qs.DCommon.Widgets

// Stand-in for DMS's PopoutComponent (a plugin popout's header, details and
// content column), with the same properties. closePopout is the function
// DMS's PluginPopout injects; nothing injects it in a test.
Column {
    id: root

    property string headerText: ""
    property string detailsText: ""
    property bool showCloseButton: false
    property var closePopout: null
    property var parentPopout: null
    property alias headerActions: headerActionsLoader.sourceComponent

    readonly property int headerHeight: popoutHeader.visible ? popoutHeader.height : 0
    readonly property int detailsHeight: popoutDetails.visible ? popoutDetails.implicitHeight : 0

    spacing: 0

    Item {
        id: popoutHeader
        width: parent.width
        height: 40
        visible: root.headerText.length > 0

        Text {
            objectName: "popoutHeaderText"
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: root.headerText
            font.pixelSize: Theme.fontSizeLarge + 4
            color: Theme.surfaceText
        }

        Loader {
            id: headerActionsLoader
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Text {
        id: popoutDetails
        objectName: "popoutDetailsText"
        width: parent.width
        text: root.detailsText
        font.pixelSize: Theme.fontSizeMedium
        color: Theme.surfaceVariantText
        visible: root.detailsText.length > 0
        wrapMode: Text.WordWrap
    }
}

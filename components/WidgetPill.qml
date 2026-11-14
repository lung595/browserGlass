import QtQuick
import qs.Common
import qs.DCommon.Widgets

// The bar pill's content (horizontal and vertical bars alike): blur_on while
// glass is on, blur_off otherwise, and a dot while a running browser must
// restart to show the current files.
Item {
    id: pill

    // The BrowserGlassWidget it belongs to
    required property var widget

    readonly property int iconSize: pill.widget ? pill.widget.iconSize : 16
    readonly property bool showBadge: pill.widget ? pill.widget.restartNeeded === true : false

    implicitWidth: pill.iconSize
    implicitHeight: pill.iconSize

    DIcon {
        id: icon
        objectName: "glassIcon"
        anchors.centerIn: parent
        name: pill.widget ? pill.widget.iconName : "blur_off"
        size: pill.iconSize
        color: pill.widget && pill.widget.glassActive ? Theme.primary : Theme.surfaceText
    }

    Rectangle {
        objectName: "restartBadge"
        width: Math.max(4, Math.round(pill.iconSize / 4))
        height: width
        radius: width / 2
        color: Theme.warning
        anchors.right: icon.right
        anchors.top: icon.top
        visible: pill.showBadge
    }
}

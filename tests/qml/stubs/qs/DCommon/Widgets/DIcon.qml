import QtQuick

// Stand-in for DMS's DIcon (qs.DCommon.Widgets): the icon's name as text (no
// icon font offscreen), with only the properties the plugin sets
Item {
    id: icon
    property string name: ""
    property real size: 24
    property color color: "white"
    width: size
    height: size
    Text {
        anchors.centerIn: parent
        text: icon.name
        color: icon.color
        font.pixelSize: Math.max(1, icon.size / 3)
    }
}

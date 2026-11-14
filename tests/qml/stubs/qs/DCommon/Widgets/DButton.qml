import QtQuick

// Stand-in for DMS's DButton (qs.DCommon.Widgets), with only the properties
// the plugin sets. A test presses it with Harness.press().
Item {
    id: button
    property string text: ""
    property string iconName: ""
    property string variant: "filled"

    signal clicked

    implicitWidth: Math.max(64, label.implicitWidth + 24)
    implicitHeight: 36
    Text {
        id: label
        anchors.centerIn: parent
        text: button.text
        color: "white"
    }
}

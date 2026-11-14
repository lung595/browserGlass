import QtQuick

// Stand-in for DMS's DTextField (qs.DCommon.Widgets): a plain text input
// with only the properties the plugin sets
Item {
    id: field
    property alias text: input.text
    property string placeholderText: ""
    property string leftIconName: ""
    property bool showClearButton: false

    implicitWidth: 200
    implicitHeight: 40
    TextInput {
        id: input
        anchors.fill: parent
        color: "white"
    }
}

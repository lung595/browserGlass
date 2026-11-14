import QtQuick

// Stand-in for DMS's DToggle (qs.DCommon.Widgets): its state and signals,
// with only the properties the plugin sets. As in DMS, a tap does not change
// `checked`: it emits clicked and toggled(!checked), and the owner binds
// `checked`. A test taps it with Harness.tap().
Item {
    property bool checked: false
    property string text: ""
    property string description: ""

    signal clicked
    signal toggled(bool checked)

    width: 52
    height: 30
}

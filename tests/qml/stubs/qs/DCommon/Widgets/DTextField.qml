import QtQuick

// Stand-in for DMS's DTextField (qs.DCommon.Widgets): a plain text input
// with only the properties, signals and functions the plugin uses. It keeps
// to the API DMS 2.0.0 already had (no `inputFocused`, that came later)
Item {
    id: field
    property alias text: input.text
    property alias maximumLength: input.maximumLength
    property string placeholderText: ""
    property string leftIconName: ""
    property bool showClearButton: false
    property Component trailingContent: null

    signal textEdited
    signal accepted
    signal focusStateChanged(bool hasFocus)

    function forceActiveFocus() {
        input.forceActiveFocus();
    }
    function setFocus(value) {
        input.focus = value;
    }
    function selectAll() {
        input.selectAll();
    }

    implicitWidth: 200
    implicitHeight: 40
    TextInput {
        id: input
        anchors.fill: parent
        color: "white"
        onTextChanged: field.textEdited()
        onAccepted: field.accepted()
        onActiveFocusChanged: field.focusStateChanged(activeFocus)
    }
    Loader {
        anchors.right: parent.right
        active: field.trailingContent !== null
        sourceComponent: field.trailingContent
    }
}

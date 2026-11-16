import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// The search field on top of the settings page. It only edits `view.query`:
// the page filters itself from there. Esc clears, a second Esc leaves the
// field, Enter opens the best match.
Rectangle {
    id: field

    required property var view

    // The second Esc: the field lets go and the page takes the keys back
    signal released

    readonly property bool typed: view.query !== ""
    readonly property string text: input.text
    readonly property bool fieldFocus: input.activeFocus
    readonly property string hintText: typed ? I18n.trFor("browserGlass", "Esc clears") : view.compact ? "/" : I18n.trFor("browserGlass", "Ctrl+F or /")

    function focusField() {
        input.forceActiveFocus();
        input.selectAll();
    }

    // Gives the keys back to the page (the page's focus would hand them
    // straight back to the field otherwise)
    function dropFocus() {
        input.focus = false;
    }

    // Esc in the field: clears what is typed, or lets the field go
    function clearOrRelease() {
        if (input.text !== "")
            input.text = "";
        else
            field.released();
    }

    // 44 px tall: a touch target, like the rail's rows
    height: 44
    radius: height / 2
    color: Theme.surfaceContainerHigh
    // At rest the outline is the boundary of the field; typing or keyboard
    // focus: 2 px primary
    border.width: typed || input.activeFocus ? 2 : 1
    border.color: typed || input.activeFocus ? Theme.primary : hover.hovered ? Theme.withAlpha(Theme.surfaceText, 0.5) : Theme.outline

    HoverHandler {
        id: hover
        cursorShape: Qt.IBeamCursor
    }

    DIcon {
        id: lens
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        name: "search"
        size: 20
        color: field.typed ? Theme.primary : Theme.surfaceVariantText
    }

    TextInput {
        id: input
        objectName: "searchInput"
        anchors.left: lens.right
        anchors.leftMargin: Theme.spacingS
        anchors.right: hint.left
        anchors.rightMargin: Theme.spacingS
        anchors.verticalCenter: parent.verticalCenter
        clip: true
        font.pixelSize: Theme.fontSizeMedium
        color: Theme.surfaceText
        selectionColor: Theme.primary
        selectedTextColor: Theme.primaryText
        // Long queries are cut: a search of 30 settings never needs more
        maximumLength: 80
        Accessible.role: Accessible.EditableText
        Accessible.name: I18n.trFor("browserGlass", "Search settings")
        onTextChanged: field.view.query = text
        onAccepted: field.view.openFirst()
        Keys.onEscapePressed: field.clearOrRelease()

        // The view clears the query too (Enter, a click on the rail): typing
        // breaks a `text:` binding, so the field follows by hand
        Connections {
            target: field.view
            function onQueryChanged() {
                if (input.text !== field.view.query)
                    input.text = field.view.query;
            }
        }

        StyledText {
            objectName: "searchPlaceholder"
            anchors.verticalCenter: parent.verticalCenter
            visible: input.text === "" && !input.preeditText
            text: I18n.trFor("browserGlass", "Search settings")
            font.pixelSize: Theme.fontSizeMedium
            color: Theme.surfaceVariantText
        }
    }

    // The key hint says what will happen: idle it says how to come here,
    // typing it says how to get out
    Rectangle {
        id: hint
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        width: hintLabel.implicitWidth + 16
        height: 24
        radius: 12
        color: Theme.withAlpha(Theme.surfaceText, 0.07)
        StyledText {
            id: hintLabel
            objectName: "searchHint"
            anchors.centerIn: parent
            text: field.hintText
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
        }
    }
}

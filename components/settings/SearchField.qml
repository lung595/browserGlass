import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// The search field on top of the settings page: DMS's own text field. It
// only edits `view.query`: the page filters itself from there. Esc clears, a
// second Esc leaves the field, Enter opens the best match.
Item {
    id: field

    required property var view

    // The second Esc: the field lets go and the page takes the keys back
    signal released

    readonly property bool typed: view.query !== ""
    readonly property string text: input.text
    // Set from the field's focus signal: DMS 2.0.0 has no `inputFocused` yet
    property bool fieldFocus: false
    readonly property string hintText: typed ? I18n.trFor("browserGlass", "Esc clears") : view.compact ? "/" : I18n.trFor("browserGlass", "Ctrl+F or /")

    function focusField() {
        input.forceActiveFocus();
        input.selectAll();
    }

    // Gives the keys back to the page (the page's focus would hand them
    // straight back to the field otherwise)
    function dropFocus() {
        input.setFocus(false);
    }

    // Esc in the field: clears what is typed, or lets the field go
    function clearOrRelease() {
        if (input.text !== "")
            input.text = "";
        else
            field.released();
    }

    implicitHeight: input.implicitHeight
    height: implicitHeight

    DTextField {
        id: input
        objectName: "searchInput"
        anchors.left: parent.left
        anchors.right: parent.right
        placeholderText: I18n.trFor("browserGlass", "Search settings")
        leftIconName: "search"
        // Long queries are cut: a search of 30 settings never needs more
        maximumLength: 80
        Accessible.name: I18n.trFor("browserGlass", "Search settings")
        onTextEdited: field.view.query = text
        onAccepted: field.view.openFirst()
        onFocusStateChanged: hasFocus => field.fieldFocus = hasFocus
        Keys.onEscapePressed: field.clearOrRelease()

        // The key hint says what will happen: idle it says how to come here,
        // typing it says how to get out
        trailingContent: Component {
            Rectangle {
                width: hintLabel.implicitWidth + Theme.spacingL
                height: Theme.iconSize
                radius: Theme.cornerRadiusFull
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

        // The view clears the query too (Enter, a click on the rail): typing
        // breaks a `text:` binding, so the field follows by hand
        Connections {
            target: field.view
            function onQueryChanged() {
                if (input.text !== field.view.query)
                    input.text = field.view.query;
            }
        }
    }
}

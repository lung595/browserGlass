import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// What the content shows when a search matches nothing: one line to say so,
// one to say what to try. The rail stays usable.
Column {
    id: none

    required property string query

    objectName: "noResults"
    spacing: Theme.spacingS
    topPadding: Theme.spacingXL

    DIcon {
        anchors.horizontalCenter: parent.horizontalCenter
        name: "search_off"
        size: Theme.iconSizeLarge
        color: Theme.surfaceVariantText
    }
    StyledText {
        objectName: "noResultsText"
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
        text: I18n.trFor("browserGlass", "Nothing matches “%1”").arg(none.query.trim())
        font.pixelSize: Theme.fontSizeMedium
        font.weight: Font.Medium
        color: Theme.surfaceText
    }
    StyledText {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: I18n.trFor("browserGlass", "Try one word: opacity, dark, exclude, uninstall")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }
}

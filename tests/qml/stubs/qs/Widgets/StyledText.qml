import QtQuick

// Mirrors DMS's StyledText defaults (wrap, elide, vertical centering)
Text {
    font.pixelSize: 14
    color: "white"
    textFormat: Text.PlainText
    wrapMode: Text.WordWrap
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
}

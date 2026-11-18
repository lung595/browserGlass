import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// What Browser Glass writes, and how to remove it by hand: three rows, each
// a title or a note over its text or command.
CategoryPage {
    id: page
    category: "files"

    required property var settings

    Item {
        objectName: "filesWritten"
        visible: page.shown("filesWritten")
        width: parent.width
        height: filesColumn.implicitHeight

        Column {
            id: filesColumn
            width: parent.width
            spacing: Theme.spacingXS

            StyledText {
                width: parent.width
                text: page.label("filesWritten")
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.fontWeightMedium
                color: Theme.surfaceText
            }

            StyledText {
                objectName: "filesWrittenList"
                width: parent.width
                text: page.help("filesWritten")
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }
        }
    }

    Item {
        objectName: "uninstall"
        visible: page.shown("uninstall")
        width: parent.width
        height: uninstallColumn.implicitHeight

        Column {
            id: uninstallColumn
            width: parent.width
            spacing: Theme.spacingS

            StyledText {
                width: parent.width
                text: page.label("uninstall")
                font.pixelSize: Theme.fontSizeLarge
                font.weight: Theme.fontWeightMedium
                color: Theme.surfaceText
            }

            StyledText {
                width: parent.width
                text: page.help("uninstall")
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }

            StyledRect {
                width: parent.width
                height: uninstallText.implicitHeight + Theme.spacingS * 2
                radius: Theme.cornerRadius
                color: Theme.surfaceContainerHigh

                StyledText {
                    id: uninstallText
                    objectName: "uninstallCommand"
                    anchors.fill: parent
                    anchors.margins: Theme.spacingS
                    text: page.settings.uninstallCommand
                    font.family: Theme.monoFontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.surfaceText
                    wrapMode: Text.WrapAnywhere
                }
            }

            DButton {
                objectName: "copyUninstall"
                text: I18n.trFor("browserGlass", "Copy command")
                iconName: "content_copy"
                variant: "text"
                onClicked: page.settings.copyText(page.settings.uninstallCommand)
            }
        }
    }

    Item {
        objectName: "stdinUninstall"
        visible: page.shown("stdinUninstall")
        width: parent.width
        height: stdinColumn.implicitHeight

        Column {
            id: stdinColumn
            width: parent.width
            spacing: Theme.spacingS

            StyledText {
                width: parent.width
                text: page.label("stdinUninstall")
                wrapMode: Text.WordWrap
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }

            StyledRect {
                width: parent.width
                height: stdinText.implicitHeight + Theme.spacingS * 2
                radius: Theme.cornerRadius
                color: Theme.surfaceContainerHigh

                StyledText {
                    id: stdinText
                    objectName: "stdinUninstallCommand"
                    anchors.fill: parent
                    anchors.margins: Theme.spacingS
                    text: page.settings.stdinUninstallCommand
                    font.family: Theme.monoFontFamily
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.surfaceText
                    wrapMode: Text.WrapAnywhere
                }
            }
        }
    }
}

import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets

// The notes worth knowing, the guide and the bug reports.
CategoryPage {
    id: page
    category: "help"

    required property var settings

    StyledText {
        objectName: "zenWarning"
        visible: page.shown("zenWarning") && (page.settings.zenWarning || page.settings.zenFound)
        width: parent.width
        text: page.label("zenWarning")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        font.weight: page.settings.zenWarning ? Theme.fontWeightMedium : Font.Normal
        color: page.settings.zenWarning ? Theme.warning : Theme.surfaceVariantText
    }

    StyledText {
        objectName: "restartNote"
        visible: page.shown("restartNote")
        width: parent.width
        text: page.label("restartNote")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    Flow {
        visible: page.shown("openReadme") || page.shown("openGuide") || page.shown("openIssues")
        width: parent.width
        spacing: Theme.spacingS

        DButton {
            objectName: "openReadme"
            visible: page.shown("openReadme")
            text: page.label("openReadme")
            iconName: "open_in_new"
            variant: "text"
            onClicked: page.settings.openUrl(page.settings.readmeUrl)
        }

        DButton {
            objectName: "openGuide"
            visible: page.shown("openGuide")
            text: page.label("openGuide")
            iconName: "open_in_new"
            variant: "text"
            onClicked: page.settings.openUrl(page.settings.guideUrl)
        }

        DButton {
            objectName: "openIssues"
            visible: page.shown("openIssues")
            text: page.label("openIssues")
            iconName: "open_in_new"
            variant: "text"
            onClicked: page.settings.openUrl(page.settings.issuesUrl)
        }
    }
}

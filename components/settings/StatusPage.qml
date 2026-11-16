import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets
import ".."

// Whether the glass is on and why, the report and a fresh sync. The plugin's
// one-line description opens the page while nothing is searched.
CategoryPage {
    id: page
    category: "status"

    required property var settings

    StyledText {
        objectName: "about"
        visible: !page.view.filtering
        width: parent.width
        text: I18n.trFor("browserGlass", "Gives Firefox-family browsers (Firefox, LibreWolf, Zen, Floorp, Waterfox) the DMS glass under niri. Opacity and colours follow DMS; video, images and text stay opaque. Restart the browser after a change.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    StatusBlock {
        objectName: "statusBlock"
        visible: page.shown("statusBlock")
    }

    DButton {
        objectName: "turnGlassOn"
        visible: page.shown("turnGlassOn") && page.settings.glass !== null && page.settings.glass.reason === "toggled_off"
        text: page.label("turnGlassOn")
        iconName: "blur_on"
        onClicked: page.settings.service.savePluginData(page.settings.pluginId, "glassEnabled", true)
    }

    // A warning, not a setting: it shows with whatever this page shows
    StyledText {
        objectName: "noDaemon"
        visible: page.settings.daemon === null
        width: parent.width
        text: I18n.trFor("browserGlass", "The Browser Glass daemon is not running: enable the plugin to apply the glass.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.warning
    }

    Flow {
        visible: page.shown("copyReport") || page.shown("resync")
        width: parent.width
        spacing: Theme.spacingS

        DButton {
            objectName: "copyReport"
            visible: page.shown("copyReport")
            text: page.label("copyReport")
            iconName: "content_copy"
            enabled: page.settings.daemon !== null
            onClicked: page.settings.daemon.copyReport()
        }

        DButton {
            objectName: "resync"
            visible: page.shown("resync")
            text: page.label("resync")
            iconName: "sync"
            variant: "tonal"
            enabled: page.settings.daemon !== null
            onClicked: page.settings.daemon.requestSync("settings")
        }
    }

    StyledText {
        objectName: "reportNote"
        visible: page.shown("copyReport")
        width: parent.width
        text: page.help("copyReport")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }
}

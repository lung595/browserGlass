pragma ComponentBehavior: Bound
import QtQuick
import qs.Common
import qs.Widgets
import qs.DCommon.Widgets
import qs.Modules.Plugins
import "logic.js" as Logic

// The bar widget's popout: the detailed status (why glass is on or off, the
// opacity, the browsers found, a pending restart, errors and warnings), the
// glass switch, "Exclude copied URL" and "Open settings". The actions are
// the widget's (BrowserGlassWidget.qml).
PopoutComponent {
    id: popout

    // The BrowserGlassWidget it belongs to
    required property var widget

    readonly property var status: popout.widget ? popout.widget.status : null
    readonly property var glass: popout.status && popout.status.glass ? popout.status.glass : null
    readonly property var browsers: popout.status && Array.isArray(popout.status.browsers) ? popout.status.browsers : []
    // Warnings worth telling (the niri rule codes are the daemon's business)
    readonly property var warnings: Logic.statusWarnings(popout.status, true)
    readonly property bool liveOff: popout.status !== null && popout.status.companion !== null && typeof popout.status.companion === "object" && popout.status.companion.state === "off"

    readonly property string reasonText: {
        if (popout.glass)
            return I18n.trFor("browserGlass", Logic.reasonText(popout.glass.reason));
        if (popout.widget && popout.widget.glassActive)
            return I18n.trFor("browserGlass", "Glass is on");
        return I18n.trFor("browserGlass", "No status yet");
    }
    readonly property string opacityText: {
        if (!popout.glass || typeof popout.glass.opacity !== "number")
            return "—";
        const percent = Math.round(popout.glass.opacity * 100);
        switch (popout.glass.opacity_source) {
        case "override":
            return I18n.trFor("browserGlass", "%1%, browser override").arg(percent);
        case "forced":
            return I18n.trFor("browserGlass", "%1%, forced").arg(percent);
        default:
            return I18n.trFor("browserGlass", "%1%, from DMS").arg(percent);
        }
    }
    readonly property string browsersText: {
        const names = Logic.familyNames(popout.browsers.filter(b => b && Array.isArray(b.profiles) && b.profiles.length > 0));
        if (!popout.status)
            return "—";
        return names.length ? names.join(", ") : I18n.trFor("browserGlass", "None found");
    }
    readonly property string restartText: {
        const names = Logic.familyNames(popout.browsers.filter(b => b && b.restart_needed === true));
        if (!names.length)
            return I18n.trFor("browserGlass", "Restart the browser to see the change");
        return I18n.trFor("browserGlass", "Restart %1 to see the change").arg(names.join(", "));
    }
    readonly property string warningsText: popout.warnings.length === 1 ? I18n.trFor("browserGlass", "1 warning, details in the settings") : I18n.trFor("browserGlass", "%1 warnings, details in the settings").arg(popout.warnings.length)

    headerText: I18n.trFor("browserGlass", "Browser Glass")
    detailsText: popout.reasonText

    component InfoRow: Item {
        id: row
        property string label: ""
        property string value: ""
        width: parent ? parent.width : 0
        implicitHeight: Math.max(rowLabel.implicitHeight, rowValue.implicitHeight)

        StyledText {
            id: rowLabel
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, row.width / 2)
            text: row.label
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
            wrapMode: Text.NoWrap
        }
        StyledText {
            id: rowValue
            anchors.right: parent.right
            anchors.left: rowLabel.right
            anchors.leftMargin: Theme.spacingS
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: Text.AlignRight
            text: row.value
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceText
            wrapMode: Text.NoWrap
        }
    }

    Column {
        width: parent.width
        spacing: Theme.spacingS
        topPadding: Theme.spacingS

        InfoRow {
            objectName: "opacityRow"
            label: I18n.trFor("browserGlass", "Opacity")
            value: popout.opacityText
        }

        InfoRow {
            objectName: "browsersRow"
            label: I18n.trFor("browserGlass", "Browsers")
            value: popout.browsersText
        }

        StyledText {
            objectName: "syncingText"
            width: parent.width
            visible: popout.widget ? popout.widget.syncing === true : false
            text: I18n.trFor("browserGlass", "Applying the change…")
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
        }

        Row {
            objectName: "restartNotice"
            width: parent.width
            spacing: Theme.spacingS
            visible: popout.widget ? popout.widget.restartNeeded === true : false

            DIcon {
                id: restartIcon
                name: "restart_alt"
                size: Theme.iconSizeSmall
                color: Theme.warning
                anchors.verticalCenter: parent.verticalCenter
            }
            StyledText {
                objectName: "restartText"
                width: parent.width - restartIcon.width - parent.spacing
                text: popout.restartText
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceText
            }
        }

        StyledText {
            objectName: "errorText"
            width: parent.width
            visible: text.length > 0
            text: popout.widget ? popout.widget.lastError : ""
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.error
        }

        // Live control off (the default): the pages get the basic glass
        // only; it is opt-in, so the popout says what it would add
        StyledText {
            objectName: "liveInvite"
            width: parent.width
            visible: popout.liveOff
            text: I18n.trFor("browserGlass", "Live control is off: the pages get the basic glass. Turn it on in the settings for site dark themes, veiled bars and sharp text.")
            wrapMode: Text.WordWrap
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
        }

        StyledText {
            objectName: "warningsText"
            width: parent.width
            visible: popout.warnings.length > 0
            text: popout.warningsText
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.warning
        }

        DToggle {
            objectName: "glassToggle"
            width: parent.width
            text: I18n.trFor("browserGlass", "Glass")
            description: I18n.trFor("browserGlass", "Off: the browsers follow the DMS window opacity again; the plugin stays installed")
            checked: popout.widget ? popout.widget.glassEnabled : true
            onToggled: on => popout.widget.setGlassEnabled(on)
        }

        Flow {
            width: parent.width
            spacing: Theme.spacingS

            DButton {
                objectName: "excludeButton"
                text: I18n.trFor("browserGlass", "Exclude copied URL")
                iconName: "link_off"
                enabled: popout.widget ? popout.widget.daemonAvailable : false
                onClicked: popout.widget.excludeClipboard()
            }
            DButton {
                objectName: "settingsButton"
                text: I18n.trFor("browserGlass", "Open settings")
                iconName: "settings"
                onClicked: popout.widget.openSettings()
            }
        }
    }
}

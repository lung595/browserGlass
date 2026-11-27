pragma ComponentBehavior: Bound
import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.DCommon.Widgets
import "logic.js" as Logic

// The glass state as the daemon last saw it: on or off and why, restart
// needed, opacity and tint, the niri rule, the browsers found and the
// warnings. It only reads what BrowserGlassDaemon.qml shares through its
// PluginGlobalVar values (names in logic.js) and runs nothing itself. Used by
// the settings page.
Column {
    id: block

    // The daemon's shared values; a user may bind its own instead
    readonly property var vars: PluginService.globalVars[Logic.PLUGIN_ID] || ({})
    property var status: vars.status || null
    property var lastSync: vars.lastSync || null
    property bool glassActive: vars.glassActive === true
    property bool restartNeeded: vars.restartNeeded === true
    property bool syncing: vars.syncing === true
    property string lastError: typeof vars.lastError === "string" ? vars.lastError : ""

    readonly property var glass: status && status.glass ? status.glass : null
    readonly property string reason: glass ? String(glass.reason || "") : (lastSync ? String(lastSync.reason || "") : "")
    readonly property bool known: status !== null || lastSync !== null
    readonly property var browsers: status ? block.listOf(status.browsers) : []
    readonly property var warnings: Logic.statusWarnings(status, false)

    width: parent ? parent.width : 0
    spacing: Theme.spacingS

    // A real array from a list value. The Repeater hands each delegate a
    // converted copy of its model entry (modelData), in which a nested list
    // such as browser.profiles is array-like but not an Array.
    function listOf(value) {
        if (Array.isArray(value))
            return value;
        if (value && typeof value === "object" && typeof value.length === "number")
            return Array.prototype.slice.call(value);
        return [];
    }

    function percent(fraction) {
        const n = Number(fraction);
        return isFinite(n) ? Math.round(n * 100) : 0;
    }

    function headline() {
        if (!block.known)
            return I18n.trFor("browserGlass", "No status yet");
        if (block.glassActive)
            return I18n.trFor("browserGlass", "Glass is on");
        return I18n.trFor("browserGlass", Logic.reasonText(block.reason));
    }

    function opacityLine() {
        if (!block.glass)
            return "";
        const value = block.percent(block.glass.opacity);
        if (block.glass.opacity_source === "override")
            return I18n.trFor("browserGlass", "Opacity %1%, set by the override").arg(value);
        if (block.glass.opacity_source === "forced")
            return I18n.trFor("browserGlass", "Opacity %1%, forced").arg(value);
        return I18n.trFor("browserGlass", "Opacity %1%, from the DMS window rules").arg(value);
    }

    function tintLine() {
        if (!block.glass)
            return "";
        const surface = String(block.glass.surface || "");
        return block.glass.mode === "light" ? I18n.trFor("browserGlass", "Tint %1, light mode").arg(surface) : I18n.trFor("browserGlass", "Tint %1, dark mode").arg(surface);
    }

    function niriLine() {
        const niri = block.status && block.status.niri ? block.status.niri : null;
        if (!niri)
            return "";
        if (!niri.config)
            return I18n.trFor("browserGlass", "niri config.kdl not found");
        if (niri.rule && !niri.include)
            return I18n.trFor("browserGlass", "niri rule written, but config.kdl does not include it");
        return niri.rule ? I18n.trFor("browserGlass", "niri rule in place") : I18n.trFor("browserGlass", "No niri rule");
    }

    function browserName(browser) {
        const name = Logic.familyName(browser.family);
        if (browser.variant === "flatpak")
            return name + " (Flatpak)";
        if (browser.variant === "snap")
            return name + " (Snap)";
        return name;
    }

    function browserLine(browser) {
        const profiles = block.listOf(browser.profiles);
        const parts = [profiles.length === 1 ? I18n.trFor("browserGlass", "1 profile") : I18n.trFor("browserGlass", "%1 profiles").arg(profiles.length)];
        const running = profiles.filter(p => p && p.running).length;
        if (running > 0)
            parts.push(I18n.trFor("browserGlass", "%1 running").arg(running));
        const bare = profiles.filter(p => p && p.applied === false).length;
        if (bare > 0)
            parts.push(I18n.trFor("browserGlass", "%1 without glass").arg(bare));
        if (browser.restart_needed)
            parts.push(I18n.trFor("browserGlass", "restart needed"));
        return block.browserName(browser) + ": " + parts.join(", ");
    }

    // What the warning means (translated), with the browser it is about
    function warningText(warning) {
        const text = I18n.trFor("browserGlass", Logic.warningText(warning.code));
        return warning.family ? Logic.familyName(warning.family) + ": " + text : text;
    }

    // Live control (status.companion), "" before a status that has it
    function liveLine() {
        const companion = block.status && block.status.companion && typeof block.status.companion === "object" ? block.status.companion : null;
        if (!companion)
            return "";
        return I18n.trFor("browserGlass", Logic.liveStatusText(String(companion.state || "")));
    }

    Row {
        width: parent.width
        spacing: Theme.spacingS

        DIcon {
            id: stateIcon
            objectName: "statusIcon"
            name: block.glassActive ? "blur_on" : "blur_off"
            size: Theme.iconSize
            color: block.glassActive ? Theme.primary : Theme.surfaceVariantText
            anchors.verticalCenter: parent.verticalCenter
        }

        StyledText {
            objectName: "statusHeadline"
            width: parent.width - stateIcon.width - Theme.spacingS
            text: block.headline()
            font.pixelSize: Theme.fontSizeLarge
            font.weight: Theme.fontWeightMedium
            color: Theme.surfaceText
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    StyledText {
        objectName: "statusSyncing"
        visible: block.syncing
        width: parent.width
        text: I18n.trFor("browserGlass", "Applying the settings…")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    StyledText {
        objectName: "statusRestart"
        visible: block.restartNeeded
        width: parent.width
        text: I18n.trFor("browserGlass", "Restart the browser to see the change")
        font.pixelSize: Theme.fontSizeMedium
        font.weight: Theme.fontWeightMedium
        color: Theme.warning
    }

    StyledText {
        objectName: "statusOpacity"
        visible: text !== ""
        width: parent.width
        text: block.opacityLine()
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    Row {
        visible: block.glass !== null
        spacing: Theme.spacingS

        Rectangle {
            width: Theme.iconSizeSmall
            height: Theme.iconSizeSmall
            radius: width / 2
            color: block.glass && /^#[0-9a-fA-F]{6}$/.test(String(block.glass.surface)) ? block.glass.surface : "transparent"
            border.width: 1
            border.color: Theme.outline
            anchors.verticalCenter: parent.verticalCenter
        }

        StyledText {
            objectName: "statusTint"
            text: block.tintLine()
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceVariantText
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    StyledText {
        objectName: "statusNiri"
        visible: text !== ""
        width: parent.width
        text: block.niriLine()
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    StyledText {
        objectName: "statusLive"
        visible: text !== ""
        width: parent.width
        text: block.liveLine()
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    StyledText {
        objectName: "statusNoBrowser"
        visible: block.status !== null && block.browsers.length === 0
        width: parent.width
        text: I18n.trFor("browserGlass", "No Firefox-family browser found")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    Column {
        objectName: "statusBrowsers"
        visible: block.browsers.length > 0
        width: parent.width
        spacing: Theme.spacingXS

        StyledText {
            text: I18n.trFor("browserGlass", "Browsers")
            font.pixelSize: Theme.fontSizeMedium
            font.weight: Theme.fontWeightMedium
            color: Theme.surfaceText
        }

        Repeater {
            model: block.browsers

            StyledText {
                required property var modelData
                objectName: "statusBrowser"
                width: parent.width
                text: block.browserLine(modelData)
                font.pixelSize: Theme.fontSizeSmall
                color: modelData.restart_needed ? Theme.warning : Theme.surfaceVariantText
            }
        }
    }

    Repeater {
        objectName: "warningList"
        model: block.warnings

        StyledText {
            required property var modelData
            objectName: "statusWarning"
            width: block.width
            text: block.warningText(modelData)
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.warning
        }
    }

    StyledText {
        objectName: "statusError"
        visible: block.lastError !== ""
        width: parent.width
        text: I18n.trFor("browserGlass", "Last error: %1").arg(block.lastError)
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.error
    }
}

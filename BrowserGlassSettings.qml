import QtQuick
import Quickshell
import qs.Common
import qs.Services
import qs.Widgets
import qs.DCommon.Widgets
import qs.Modules.Plugins
import "components"
import "components/logic.js" as Logic

// The settings page, in four sections: Status, Appearance, Sites, Advanced
// & help. The setting widgets save into the plugin data (keys listed at the
// top of components/logic.js), which the daemon turns into `sync
// --settings`. Everything shown about the browsers comes from the daemon's
// shared values (PluginGlobalVar names in logic.js), and the buttons call
// the daemon's own functions: this page runs no browserglass.py command.
// The setting widgets stay direct children of PluginSettings, so they all
// reload when something else (the bar widget, the daemon) changes the data.
PluginSettings {
    id: root
    pluginId: "browserGlass"

    readonly property var service: root.pluginService || PluginService
    readonly property var vars: service.globalVars[Logic.PLUGIN_ID] || ({})
    readonly property var daemon: service.pluginDaemonInstances ? (service.pluginDaemonInstances[Logic.PLUGIN_ID] || null) : null
    readonly property var status: vars.status || null
    readonly property var glass: status && status.glass ? status.glass : null
    readonly property bool zenWarning: Logic.statusWarnings(status, false).some(w => w.code === "zen_transparency_mod")
    // A Zen browser was found: the note on Zen Mods concerns it
    readonly property bool zenFound: status && Array.isArray(status.browsers) ? status.browsers.some(b => b && b.family === "zen") : false
    readonly property string pluginDir: String(service.getPluginPath(Logic.PLUGIN_ID) || Paths.strip(Qt.resolvedUrl("."))).replace(/\/+$/, "")
    readonly property string home: String(Quickshell.env("HOME") || "").replace(/\/+$/, "")

    readonly property string repoUrl: "https://github.com/lung595/browserGlass"
    readonly property string readmeUrl: repoUrl + "#readme"
    readonly property string guideUrl: repoUrl + "/blob/main/docs/GUIDE.md"
    readonly property string issuesUrl: repoUrl + "/issues"

    // How a link opens (a test replaces it)
    property var openUrl: url => Qt.openUrlExternally(url)

    // The DMS window opacity, as status last read it
    function dmsOpacityText() {
        if (!root.glass)
            return I18n.trFor("browserGlass", "DMS window opacity: not known yet");
        const value = Math.round(Number(root.glass.opacity) * 100);
        if (root.glass.opacity_source === "dms")
            return I18n.trFor("browserGlass", "DMS window opacity: %1% (the first global window rule)").arg(value);
        if (typeof root.glass.dms_opacity !== "number")
            return I18n.trFor("browserGlass", "DMS window opacity: replaced, the glass uses %1%").arg(value);
        return I18n.trFor("browserGlass", "DMS window opacity: %1%, the glass uses %2%").arg(Math.round(root.glass.dms_opacity * 100)).arg(value);
    }

    // A path as a shell word: ~/... when it is plain, else single-quoted
    function shellPath(path) {
        const p = String(path);
        if (root.home && (p === root.home || p.indexOf(root.home + "/") === 0)) {
            const rest = p.slice(root.home.length);
            if (/^[A-Za-z0-9._\/-]*$/.test(rest))
                return "~" + rest;
        }
        if (/^[A-Za-z0-9._\/-]+$/.test(p))
            return p;
        return "'" + p.replace(/'/g, "'\\''") + "'";
    }

    readonly property string uninstallCommand: "python3 -I " + shellPath(Logic.scriptPath(pluginDir)) + " uninstall"
    readonly property string stdinUninstallCommand: "python3 -I -c \"" + Logic.STDIN_BOOTSTRAP + "\" uninstall < browserglass.py"

    function copyText(text) {
        // "--": the text is never read as an option
        Quickshell.execDetached([Proc.dmsBin, "cl", "copy", "--", text]);
        ToastService.showInfo(I18n.trFor("browserGlass", "Command copied to the clipboard"), "", "", Logic.PLUGIN_ID);
    }

    Component.onCompleted: {
        // A fresh look for the status block, and the site list if the
        // daemon could not load it at start
        if (!root.daemon)
            return;
        root.daemon.refreshStatusIfIdle();
        if (!Array.isArray(root.vars.sites))
            root.daemon.loadSites();
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "Gives Firefox-family browsers (Firefox, LibreWolf, Zen, Floorp, Waterfox) the DMS glass under niri. Opacity and colours follow DMS; video, images and text stay opaque. Restart the browser after a change.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    // --- Status ---------------------------------------------------------------

    SettingsHeader {
        objectName: "sectionStatus"
        first: true
        iconName: "info"
        title: I18n.trFor("browserGlass", "Status")
    }

    StatusBlock {
        objectName: "statusBlock"
    }

    DButton {
        objectName: "turnGlassOn"
        visible: root.glass !== null && root.glass.reason === "toggled_off"
        text: I18n.trFor("browserGlass", "Turn glass on")
        iconName: "blur_on"
        onClicked: root.service.savePluginData(Logic.PLUGIN_ID, "glassEnabled", true)
    }

    StyledText {
        objectName: "noDaemon"
        visible: root.daemon === null
        width: parent.width
        text: I18n.trFor("browserGlass", "The Browser Glass daemon is not running: enable the plugin to apply the glass.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.warning
    }

    Flow {
        width: parent.width
        spacing: Theme.spacingS

        DButton {
            objectName: "copyReport"
            text: I18n.trFor("browserGlass", "Copy report")
            iconName: "content_copy"
            enabled: root.daemon !== null
            onClicked: root.daemon.copyReport()
        }

        DButton {
            objectName: "resync"
            text: I18n.trFor("browserGlass", "Re-sync")
            iconName: "sync"
            variant: "tonal"
            enabled: root.daemon !== null
            onClicked: root.daemon.requestSync("settings")
        }
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "The report holds no path, profile name or address: paste it in a bug report.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    // --- Appearance -----------------------------------------------------------

    SettingsHeader {
        objectName: "sectionAppearance"
        iconName: "palette"
        title: I18n.trFor("browserGlass", "Appearance")
    }

    StyledText {
        objectName: "dmsOpacity"
        width: parent.width
        text: root.dmsOpacityText()
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeMedium
        color: Theme.surfaceText
    }

    ToggleSetting {
        id: overrideToggle
        objectName: "opacityOverride"
        settingKey: "opacityOverride"
        label: I18n.trFor("browserGlass", "Override")
        description: I18n.trFor("browserGlass", "Use an opacity of your own for the browsers instead of the DMS one.")
        defaultValue: false
    }

    SliderSetting {
        objectName: "opacity"
        visible: overrideToggle.value
        settingKey: "opacity"
        label: I18n.trFor("browserGlass", "Browser opacity")
        description: I18n.trFor("browserGlass", "100% turns the glass off.")
        defaultValue: 85
        minimum: 20
        maximum: 100
        unit: "%"
    }

    SelectionSetting {
        objectName: "siteTheme"
        settingKey: "siteTheme"
        label: I18n.trFor("browserGlass", "Site theme")
        description: I18n.trFor("browserGlass", "The light or dark scheme websites are asked for.")
        options: [
            {
                "label": I18n.trFor("browserGlass", "Follow DMS"),
                "value": "follow"
            },
            {
                "label": I18n.trFor("browserGlass", "Always dark"),
                "value": "dark"
            },
            {
                "label": I18n.trFor("browserGlass", "Leave as is"),
                "value": "none"
            }
        ]
        defaultValue: "follow"
    }

    // The browser follows the system light/dark scheme live; DMS writes its
    // mode there only with "Sync with portal" on.
    StyledText {
        objectName: "portalHint"
        visible: !SettingsData.syncModeWithPortal
        width: parent.width
        text: I18n.trFor("browserGlass", "To switch the browser between light and dark along with DMS, without a restart, turn on Settings → Theme → Portal & terminals → Sync with portal.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.warning
    }

    ToggleSetting {
        objectName: "pagesTransparent"
        settingKey: "pagesTransparent"
        label: I18n.trFor("browserGlass", "Glass web pages")
        description: I18n.trFor("browserGlass", "Off: only the browser's own interface (tabs, address bar) is glass.")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "newTabGlass"
        settingKey: "newTabGlass"
        label: I18n.trFor("browserGlass", "Glass new tab")
        description: I18n.trFor("browserGlass", "The new tab, home and private browsing pages.")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "readerOpaque"
        settingKey: "readerOpaque"
        label: I18n.trFor("browserGlass", "Opaque reader view and PDF")
        description: I18n.trFor("browserGlass", "Keeps reader view and the PDF viewer solid, for reading.")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "privateGlass"
        settingKey: "privateGlass"
        label: I18n.trFor("browserGlass", "Glass private windows")
        description: I18n.trFor("browserGlass", "Off: private windows keep a solid background.")
        defaultValue: true
    }

    // --- Sites ----------------------------------------------------------------

    SettingsHeader {
        objectName: "sectionSites"
        iconName: "language"
        title: I18n.trFor("browserGlass", "Sites")
    }

    ToggleSetting {
        objectName: "genericStyle"
        settingKey: "genericStyle"
        label: I18n.trFor("browserGlass", "Generic style for other sites")
        description: I18n.trFor("browserGlass", "Sites without a dedicated style get a see-through background too.")
        defaultValue: true
    }

    ToggleSetting {
        objectName: "darkPages"
        settingKey: "darkPages"
        label: I18n.trFor("browserGlass", "Dark pages")
        description: I18n.trFor("browserGlass", "Under a dark theme, the companion add-on turns light pages dark with the bundled Dark Reader engine, and their background becomes glass. Needs Live control.")
        defaultValue: true
    }

    ListSettingWithInput {
        objectName: "excludedSites"
        settingKey: "excludedSites"
        label: I18n.trFor("browserGlass", "Excluded sites")
        description: I18n.trFor("browserGlass", "These sites keep their normal background (a light site hard to read on glass, say). Subdomains included.")
        defaultValue: []
        fields: [
            {
                "id": "domain",
                "label": I18n.trFor("browserGlass", "Domain"),
                "placeholder": "example.com",
                "width": 260,
                "required": true
            }
        ]
    }

    DButton {
        objectName: "excludeClipboard"
        text: I18n.trFor("browserGlass", "Exclude copied URL")
        iconName: "content_paste"
        variant: "tonal"
        enabled: root.daemon !== null
        onClicked: root.daemon.excludeClipboard()
    }

    SiteList {
        objectName: "siteList"
        settingKey: "disabledStyles"
        sites: Array.isArray(root.vars.sites) ? root.vars.sites : null
    }

    // --- Advanced & help ------------------------------------------------------

    SettingsHeader {
        objectName: "sectionAdvanced"
        iconName: "help"
        title: I18n.trFor("browserGlass", "Advanced & help")
    }

    ToggleSetting {
        objectName: "liveControl"
        settingKey: "liveControl"
        label: I18n.trFor("browserGlass", "Live control")
        description: I18n.trFor("browserGlass", "Installs Browser Glass's small companion add-on in each browser profile, so that the launcher's glass commands apply at once instead of at the next browser restart. To load it, Browser Glass sets xpinstall.signatures.required to false and lets add-ons placed in the profile folder load without a prompt. Firefox release builds refuse unsigned add-ons: there, changes apply at the next restart. Uninstalling Browser Glass removes the add-on and puts these settings back.")
        defaultValue: true
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "Files written")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Theme.fontWeightMedium
        color: Theme.surfaceText
    }

    StyledText {
        objectName: "filesWritten"
        width: parent.width
        text: [
            "• " + I18n.trFor("browserGlass", "In each browser profile: chrome/dms-glass-*.css, one @import line in userChrome.css and userContent.css, a marked block in user.js, and the cleanup of prefs.js."),
            "• " + I18n.trFor("browserGlass", "~/.config/niri/dms-browser-glass.kdl, and its include line in ~/.config/niri/config.kdl."),
            "• " + I18n.trFor("browserGlass", "~/.local/state/dms/browserGlass/: state, one backup of the files it edits, the original preference values."),
            "• " + I18n.trFor("browserGlass", "With Live control: the companion add-on in each profile's extensions/ folder, ~/.mozilla/native-messaging-hosts/browserglass.json, the helper's native-host script in the state folder, and while a browser runs, a socket and two small files in $XDG_RUNTIME_DIR/browserGlass/."),
            "• " + I18n.trFor("browserGlass", "Before each sync: its settings, in $XDG_RUNTIME_DIR/browserGlass-sync-settings.json, deleted once read.")
        ].join("\n")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "Uninstall")
        font.pixelSize: Theme.fontSizeLarge
        font.weight: Theme.fontWeightMedium
        color: Theme.surfaceText
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "Disabling or removing the plugin removes all of it and restores the browsers' files and preferences; the browsers can stay open. To do it by hand, disable the plugin first, then run:")
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
            text: root.uninstallCommand
            font.family: "monospace"
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
        onClicked: root.copyText(root.uninstallCommand)
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "The script needs no other file: from a copy of browserglass.py alone (the plugin folder already gone), run:")
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
            text: root.stdinUninstallCommand
            font.family: "monospace"
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.surfaceText
            wrapMode: Text.WrapAnywhere
        }
    }

    StyledText {
        objectName: "zenWarning"
        visible: root.zenWarning || root.zenFound
        width: parent.width
        text: I18n.trFor("browserGlass", "Zen: its own transparency mods (Zen Mods) stack with Browser Glass and make the window too see-through. Keep only one of the two.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        font.weight: root.zenWarning ? Theme.fontWeightMedium : Font.Normal
        color: root.zenWarning ? Theme.warning : Theme.surfaceVariantText
    }

    StyledText {
        width: parent.width
        text: I18n.trFor("browserGlass", "The browser must restart to show a change. The niri rule applies to every window of these browsers, other profiles included.")
        wrapMode: Text.WordWrap
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.surfaceVariantText
    }

    Flow {
        width: parent.width
        spacing: Theme.spacingS

        DButton {
            objectName: "openReadme"
            text: I18n.trFor("browserGlass", "Documentation")
            iconName: "open_in_new"
            variant: "text"
            onClicked: root.openUrl(root.readmeUrl)
        }

        DButton {
            objectName: "openGuide"
            text: I18n.trFor("browserGlass", "Guide")
            iconName: "open_in_new"
            variant: "text"
            onClicked: root.openUrl(root.guideUrl)
        }

        DButton {
            objectName: "openIssues"
            text: I18n.trFor("browserGlass", "Report a problem")
            iconName: "open_in_new"
            variant: "text"
            onClicked: root.openUrl(root.issuesUrl)
        }
    }
}

import QtQuick
import Quickshell
import qs.Common
import qs.Services
import qs.Widgets
import qs.DCommon.Widgets
import qs.Modules.Plugins
import "components"
import "components/settings"
import "components/logic.js" as Logic

// The settings page: a search field on top, the categories on the left, one
// category at a time on the right (components/settings/). Typing turns the
// page into the answer (only the matching settings, editable in place); Esc
// gives the page back. The setting widgets save into the plugin data (keys
// listed at the top of components/logic.js), which the daemon turns into
// `sync --settings`. Everything shown about the browsers comes from the
// daemon's shared values (PluginGlobalVar names in logic.js), and the buttons
// call the daemon's own functions: this page runs no browserglass.py command.
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

    // Below this width the rail keeps its icons only
    readonly property int narrowWidth: 400
    // The page's state (open category, query, matches), for the tests too
    readonly property alias view: view

    FocusScope {
        id: shell
        objectName: "settingsShell"
        width: parent ? parent.width : 0
        implicitHeight: column.implicitHeight
        height: implicitHeight

        // PluginSettings reloads its direct children only when something
        // else changes the data (the bar widget, the daemon's "Exclude copied
        // URL"): the setting widgets now sit in the pages, so this passes it on
        function loadValue() {
            const walk = item => {
                for (const child of item.children) {
                    if (child.settingKey !== undefined && typeof child.loadValue === "function")
                        child.loadValue();
                    else
                        walk(child);
                }
            };
            walk(shell);
        }

        SettingsView {
            id: view
            compact: shell.width < root.narrowWidth
            // The rows the page hides right now: a search does not show them
            // (the slider shows its override switch instead)
            hidden: ({
                    "opacity": !opacityPage.override,
                    "portalHint": SettingsData.syncModeWithPortal,
                    "turnGlassOn": !(root.glass !== null && root.glass.reason === "toggled_off"),
                    "zenWarning": !(root.zenWarning || root.zenFound)
                })
        }

        // Ctrl+F reaches the field from anywhere in the window; "/" only
        // arrives here when no text field has taken it, so a slash typed into
        // a field still works
        Shortcut {
            id: ctrlF
            sequence: "Ctrl+F"
            enabled: shell.visible
            onActivated: search.focusField()
        }
        readonly property var shortcut: ctrlF
        // Esc while a search filters gives the page back; otherwise it goes
        // on to the settings window (which may close)
        function handleKey(event) {
            if (event.text === "/" && !(event.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                search.focusField();
                event.accepted = true;
            } else if (event.key === Qt.Key_Escape && view.filtering) {
                view.query = "";
                event.accepted = true;
            }
        }
        Keys.onPressed: event => shell.handleKey(event)
        // The page takes the keys ("/", Esc), the field included
        function takeKeys() {
            search.dropFocus();
            shell.forceActiveFocus();
        }
        // A click on the page gives it the keys ("/", Esc); the controls keep their own clicks
        TapHandler {
            gesturePolicy: TapHandler.ReleaseWithinBounds
            grabPermissions: PointerHandler.ApprovesTakeOverByAnything
            onTapped: (eventPoint, button) => {
                // A tap in the search field leaves it its focus
                if (!search.contains(search.mapFromItem(shell, eventPoint.position)))
                    shell.takeKeys();
            }
        }

        Column {
            id: column
            width: parent.width
            spacing: Theme.spacingM

            SearchField {
                id: search
                objectName: "searchField"
                width: parent.width
                view: view
                onReleased: shell.takeKeys()
            }

            Row {
                width: parent.width
                spacing: Theme.spacingM

                CategoryRail {
                    id: rail
                    objectName: "rail"
                    // Above the content, so a narrow rail's tooltips overlap it
                    z: 1
                    view: view
                }

                Item {
                    width: parent.width - rail.width - Theme.spacingM
                    height: Math.max(pages.implicitHeight, none.visible ? none.implicitHeight : 0)

                    NoResults {
                        id: none
                        width: parent.width
                        visible: view.filtering && !view.hasResults
                        query: view.query
                    }

                    // Every page is built once; only the open one (or those with a match) shows
                    Column {
                        id: pages
                        width: parent.width
                        spacing: Theme.spacingL

                        StatusPage {
                            view: view
                            settings: root
                        }
                        OpacityPage {
                            id: opacityPage
                            view: view
                            settings: root
                        }
                        PagesPage {
                            view: view
                        }
                        SitesPage {
                            view: view
                            settings: root
                        }
                        LivePage {
                            view: view
                            settings: root
                        }
                        FilesPage {
                            view: view
                            settings: root
                        }
                        HelpPage {
                            view: view
                            settings: root
                        }
                    }
                }
            }
        }
    }
}

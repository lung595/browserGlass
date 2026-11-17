import QtQuick
import qs.Common

// What the settings page shows, as data: the categories of the rail and one
// entry per row of the pages, with the words a user may type for it that its
// label does not say (`keywords`; the label and the help are searched too).
// The pages read `label` and `help` from here, so a search never matches a
// line the page does not show, and both are translated (I18n.trFor), so the
// search works in the language on screen. The keywords stay in English, with
// a few French ones and the translated option names.
//
// `id` is the objectName of the row (the settings key for a setting), and
// `category` the page it sits in. `anchor` names the row a setting depends
// on: the search shows them together (SettingsView.js). Kept in step with
// the pages by tests/qml/settings.test.qml: it fails when a page has a row
// the index lacks, or the index names a row no page has.
QtObject {
    function _entry(id, category, label, help, keywords, anchor) {
        return {
            "id": id,
            "category": category,
            "label": label,
            "help": help,
            "keywords": keywords,
            "anchor": anchor || ""
        };
    }

    // In the order of the rail: the id that entries name in `category`, the
    // Material icon, the name and the one-line help of the page title
    readonly property var categories: [
        {
            "id": "status",
            "icon": "blur_on",
            "name": I18n.trFor("browserGlass", "Status"),
            "help": I18n.trFor("browserGlass", "Whether the glass is on, and why")
        },
        {
            "id": "opacity",
            "icon": "opacity",
            "name": I18n.trFor("browserGlass", "Opacity"),
            "help": I18n.trFor("browserGlass", "How see-through the browsers are")
        },
        {
            "id": "pages",
            "icon": "web",
            "name": I18n.trFor("browserGlass", "Pages"),
            "help": I18n.trFor("browserGlass", "Which pages are glass, light or dark")
        },
        {
            "id": "sites",
            "icon": "language",
            "name": I18n.trFor("browserGlass", "Sites"),
            "help": I18n.trFor("browserGlass", "Exclusions and the styles of known sites")
        },
        {
            "id": "live",
            "icon": "bolt",
            "name": I18n.trFor("browserGlass", "Live control"),
            "help": I18n.trFor("browserGlass", "Changes at once, without a restart")
        },
        {
            "id": "files",
            "icon": "folder_open",
            "name": I18n.trFor("browserGlass", "Files & uninstall"),
            "help": I18n.trFor("browserGlass", "What Browser Glass writes, and how to remove it")
        },
        {
            "id": "help",
            "icon": "help",
            "name": I18n.trFor("browserGlass", "Help"),
            "help": I18n.trFor("browserGlass", "Notes, the guide and bug reports")
        }
    ]

    readonly property var entries: [
        // --- status ----------------------------------------------------------
        _entry("statusBlock", "status", I18n.trFor("browserGlass", "Status"), "", ["glass", "on", "off", "state", "opacity", "tint", "colour", "color", "niri", "browsers", "profiles", "warnings", "restart", "running", "état", "verre"]),
        _entry("turnGlassOn", "status", I18n.trFor("browserGlass", "Turn glass on"), "", ["enable", "switch", "toggle", "activate", "activer"]),
        _entry("copyReport", "status", I18n.trFor("browserGlass", "Copy report"), I18n.trFor("browserGlass", "The report holds no path, profile name or address: paste it in a bug report."), ["bug", "issue", "diagnostic", "debug", "anonymous", "privacy", "clipboard", "rapport"]),
        _entry("resync", "status", I18n.trFor("browserGlass", "Re-sync"), "", ["sync", "write", "again", "refresh", "apply", "reapply", "resynchroniser"]),

        // --- opacity ---------------------------------------------------------
        _entry("dmsOpacity", "opacity", I18n.trFor("browserGlass", "DMS window opacity"), "", ["window rule", "read only", "transparency", "alpha", "see-through", "transparence"]),
        _entry("opacityOverride", "opacity", I18n.trFor("browserGlass", "Override"), I18n.trFor("browserGlass", "Use an opacity of your own for the browsers instead of the DMS one."), ["custom", "own", "manual", "transparency", "alpha", "forcer", "remplacer"]),
        _entry("opacity", "opacity", I18n.trFor("browserGlass", "Browser opacity"), I18n.trFor("browserGlass", "100% turns the glass off."), ["slider", "percent", "transparency", "alpha", "value", "transparence"], "opacityOverride"),

        // --- pages -----------------------------------------------------------
        _entry("siteTheme", "pages", I18n.trFor("browserGlass", "Site theme"), I18n.trFor("browserGlass", "The light or dark scheme websites are asked for."), ["mode", "colour scheme", "color scheme", "prefers-color-scheme", "sombre", "clair", "thème", I18n.trFor("browserGlass", "Follow DMS"), I18n.trFor("browserGlass", "Always dark"), I18n.trFor("browserGlass", "Leave as is")]),
        _entry("portalHint", "pages", I18n.trFor("browserGlass", "To switch the browser between light and dark along with DMS, without a restart, turn on Settings → Theme → Portal & terminals → Sync with portal."), "", ["portal", "live", "mode", "xdg"]),
        _entry("darkPages", "pages", I18n.trFor("browserGlass", "Dark pages"), I18n.trFor("browserGlass", "Under a dark theme, the companion add-on turns light pages dark with the bundled Dark Reader engine, and their background becomes glass. Needs Live control."), ["darkreader", "night", "dark mode", "invert", "sombre", "nuit"]),
        _entry("pagesTransparent", "pages", I18n.trFor("browserGlass", "Glass web pages"), I18n.trFor("browserGlass", "Off: only the browser's own interface (tabs, address bar) is glass."), ["content", "websites", "transparent", "see-through", "transparence"]),
        _entry("newTabGlass", "pages", I18n.trFor("browserGlass", "Glass new tab"), I18n.trFor("browserGlass", "The new tab, home and private browsing pages."), ["newtab", "start page", "about:home", "onglet"]),
        _entry("readerOpaque", "pages", I18n.trFor("browserGlass", "Opaque reader view and PDF"), I18n.trFor("browserGlass", "Keeps reader view and the PDF viewer solid, for reading."), ["reader mode", "solid", "lecture"]),
        _entry("privateGlass", "pages", I18n.trFor("browserGlass", "Glass private windows"), I18n.trFor("browserGlass", "Off: private windows keep a solid background."), ["incognito", "private browsing", "privé", "privée"]),

        // --- sites -----------------------------------------------------------
        _entry("genericStyle", "sites", I18n.trFor("browserGlass", "Generic style for other sites"), I18n.trFor("browserGlass", "Sites without a dedicated style get a see-through background too."), ["default", "fallback", "générique"]),
        _entry("excludedSites", "sites", I18n.trFor("browserGlass", "Excluded sites"), I18n.trFor("browserGlass", "These sites keep their normal background (a light site hard to read on glass, say). Subdomains included."), ["exclude", "exception", "blocklist", "blacklist", "domain", "opaque", "exclure"]),
        _entry("excludeClipboard", "sites", I18n.trFor("browserGlass", "Exclude copied URL"), "", ["clipboard", "paste", "copy", "address", "link", "presse-papiers"]),
        _entry("siteList", "sites", I18n.trFor("browserGlass", "Dedicated site styles"), I18n.trFor("browserGlass", "Styles from my-internet that make known sites glass-friendly. Switch one off and that site keeps only the plain see-through page background: the generic style does not take its place."), ["css", "disable", "youtube", "github", "wikipedia", "reddit"]),

        // --- live control ----------------------------------------------------
        _entry("liveControl", "live", I18n.trFor("browserGlass", "Live control"), I18n.trFor("browserGlass", "Installs Browser Glass's small companion add-on in each browser profile, so that the launcher's glass commands apply at once instead of at the next browser restart. To load it, Browser Glass lets add-ons placed in the profile folder load without a prompt and, unless the add-on is signed by Mozilla, sets xpinstall.signatures.required to false. Firefox release builds refuse unsigned add-ons: there, changes apply at the next restart. Uninstalling Browser Glass removes the add-on and puts these settings back."), ["addon", "extension", "instant", "xpi", "native messaging", "signature", "launcher", "module", "direct"]),

        // --- files & uninstall -----------------------------------------------
        _entry("filesWritten", "files", I18n.trFor("browserGlass", "Files written"), ["• " + I18n.trFor("browserGlass", "In each browser profile: chrome/dms-glass-*.css, one @import line in userChrome.css and userContent.css, a marked block in user.js, and the cleanup of prefs.js."), "• " + I18n.trFor("browserGlass", "~/.config/niri/dms-browser-glass.kdl, and its include line in ~/.config/niri/config.kdl."), "• " + I18n.trFor("browserGlass", "~/.local/state/dms/browserGlass/: state, one backup of the files it edits, the original preference values."), "• " + I18n.trFor("browserGlass", "With Live control: the companion add-on in each profile's extensions/ folder, ~/.mozilla/native-messaging-hosts/browserglass.json, the helper's native-host script in the state folder, and while a browser runs, a socket and two small files in $XDG_RUNTIME_DIR/browserGlass/."), "• " + I18n.trFor("browserGlass", "Before each sync: its settings, in $XDG_RUNTIME_DIR/browserGlass-sync-settings.json, deleted once read.")].join("\n"), ["paths", "folders", "privacy", "backup", "fichiers"]),
        _entry("uninstall", "files", I18n.trFor("browserGlass", "Uninstall"), I18n.trFor("browserGlass", "Disabling or removing the plugin removes all of it and restores the browsers' files and preferences; the browsers can stay open. To do it by hand, disable the plugin first, then run:"), ["remove", "delete", "restore", "command", "copy", "désinstaller", "supprimer"]),
        _entry("stdinUninstall", "files", I18n.trFor("browserGlass", "The script needs no other file: from a copy of browserglass.py alone (the plugin folder already gone), run:"), "", ["uninstall", "remove", "stdin", "command", "désinstaller"]),

        // --- help ------------------------------------------------------------
        _entry("zenWarning", "help", I18n.trFor("browserGlass", "Zen: its own transparency mods (Zen Mods) stack with Browser Glass and make the window too see-through. Keep only one of the two."), "", ["zen mods", "transparency", "warning"]),
        _entry("restartNote", "help", I18n.trFor("browserGlass", "The browser must restart to show a change. The niri rule applies to every window of these browsers, other profiles included."), "", ["restart", "reload", "window rule", "redémarrer"]),
        _entry("openReadme", "help", I18n.trFor("browserGlass", "Documentation"), "", ["readme", "docs", "manual", "help", "website", "link", "aide"]),
        _entry("openGuide", "help", I18n.trFor("browserGlass", "Guide"), "", ["user guide", "tutorial", "how", "help", "docs", "link", "aide"]),
        _entry("openIssues", "help", I18n.trFor("browserGlass", "Report a problem"), "", ["bug", "issue", "github", "support", "link", "problème"])
    ]
}

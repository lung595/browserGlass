import QtQuick
import Quickshell
import qs.Common
import qs.Services
import "components/logic.js" as Logic

// BrowserGlassSettings.qml: the key each control saves (and what
// logic.js's sync settings make of it, the int percent of the slider
// included), the reload when something else changes the data, the site list
// search and switches, the status block, the buttons calling the daemon's
// own functions (a fake daemon records them), the uninstall commands, the
// links and the French catalog.
Item {
    id: root

    width: 640
    height: 900

    Harness {
        id: t
    }

    readonly property string pid: "browserGlass"
    readonly property string dir: "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass"

    property var page: null
    property var daemon: null
    property var opened: []

    Component {
        id: pageComponent
        BrowserGlassSettings {
            width: 600
        }
    }

    // Records what the settings page asks of the daemon
    Component {
        id: daemonComponent
        QtObject {
            property var calls: []
            function record(call) {
                calls = calls.concat([call]);
            }
            function requestSync(reason) {
                record(["requestSync", reason]);
            }
            function refreshStatus() {
                record(["refreshStatus"]);
            }
            function refreshStatusIfIdle() {
                record(["refreshStatusIfIdle"]);
            }
            function loadSites() {
                record(["loadSites"]);
            }
            function excludeClipboard() {
                record(["excludeClipboard"]);
            }
            function copyReport() {
                record(["copyReport"]);
            }
            function toggleGlass() {
                record(["toggleGlass"]);
            }
        }
    }

    function json(path) {
        return JSON.parse(t.readFile(path));
    }

    // A clean shell, the daemon's shared values from the contract fixtures,
    // and a new page (with a daemon unless withDaemon is false)
    function fresh(withDaemon, vars) {
        if (root.page)
            root.page.destroy();
        if (root.daemon)
            root.daemon.destroy();
        root.page = null;
        root.daemon = null;
        root.opened = [];
        Proc.reset();
        ToastService.reset();
        Quickshell.reset();
        PluginService.reset();
        I18n.unregisterPluginTranslations(root.pid);
        SettingsData.reset();
        SettingsData.pluginSettings = {
            "browserGlass": {
                "enabled": true
            }
        };
        const shared = vars !== undefined ? vars : {
            "status": json("contract/status.json"),
            "sites": json("contract/sites.json"),
            "glassActive": true,
            "restartNeeded": true
        };
        const g = {};
        g[root.pid] = shared;
        PluginService.globalVars = g;
        const paths = {};
        paths[root.pid] = root.dir;
        PluginService.pluginPaths = paths;
        const instances = {};
        if (withDaemon !== false) {
            root.daemon = daemonComponent.createObject(root);
            instances[root.pid] = root.daemon;
        }
        PluginService.pluginDaemonInstances = instances;
        root.page = pageComponent.createObject(root, {
            "pluginService": PluginService
        });
        root.page.openUrl = url => {
            root.opened = root.opened.concat([url]);
        };
    }

    function find(item, name) {
        if (!item)
            return null;
        if (item.objectName === name)
            return item;
        const kids = item.children || [];
        for (let i = 0; i < kids.length; i++) {
            const hit = find(kids[i], name);
            if (hit)
                return hit;
        }
        return null;
    }
    function findAll(item, prefix, out) {
        if (!item)
            return out;
        if (String(item.objectName).indexOf(prefix) === 0)
            out.push(item);
        const kids = item.children || [];
        for (let i = 0; i < kids.length; i++)
            findAll(kids[i], prefix, out);
        return out;
    }
    function control(name) {
        const item = find(root.page, name);
        if (!item)
            print("FAIL no item named " + name);
        return item;
    }
    function lastSave() {
        const s = PluginService.saves;
        return s.length ? s[s.length - 1] : null;
    }
    function savesOf(key) {
        return PluginService.saves.filter(s => s[1] === key);
    }
    function synced() {
        return Logic.buildSettings(SettingsData.getPluginSettingsForPlugin(root.pid), true, false);
    }
    // The pages on screen, by category
    function shownPages() {
        return findAll(root.page, "page:", []).filter(p => p.visible).map(p => p.category);
    }
    function openCategory(id) {
        root.page.view.open(id);
    }
    function siteNames() {
        return control("siteList").filtered.map(s => s.name);
    }
    function setGlass(glass, warnings) {
        const status = json("contract/status.json");
        Object.assign(status.glass, glass);
        if (warnings !== undefined)
            status.warnings = warnings;
        PluginService.setGlobalVar(root.pid, "status", status);
        PluginService.setGlobalVar(root.pid, "glassActive", status.glass.active === true);
    }

    Component.onCompleted: t.steps([
        {
            "run": () => fresh(true)
        },
        {
            // ToggleSetting loads on the next turn of the event loop
            "wait": 30,
            "run": () => {
                t.check("opened: a status refresh unless a sync is pending, the sites already there", root.daemon.calls, [["refreshStatusIfIdle"]]);
                t.check("the categories of the rail, in order", root.page.view.categories.map(c => [c.id, c.name]), [["status", "Status"], ["opacity", "Opacity"], ["pages", "Pages"], ["sites", "Sites"], ["live", "Live control"], ["files", "Files & uninstall"], ["help", "Help"]]);
                t.check("one rail entry each", findAll(control("rail"), "rail:", []).map(i => i.objectName), ["rail:status", "rail:opacity", "rail:pages", "rail:sites", "rail:live", "rail:files", "rail:help"]);
                t.check("it opens on the status, one page at a time", shownPages(), ["status"]);
                t.check("defaults shown", ["opacityOverride", "pagesTransparent", "newTabGlass", "readerOpaque", "privateGlass", "genericStyle"].map(n => control(n).value), [false, true, true, true, true, true]);
                t.check("slider default (int percent)", control("opacity").value, 85);
                t.check("site theme default", control("siteTheme").value, "follow");
                t.ok("slider hidden while the override is off", !control("opacity").visible);
                t.check("DMS opacity read-only line", control("dmsOpacity").text, "DMS window opacity: 85% (the first global window rule)");
                t.check("the live control toggle, off by default", [control("liveControl").label, control("liveControl").value], ["Live control", false]);
                t.ok("it says what it changes", control("liveControl").description.indexOf("xpinstall.signatures.required") >= 0);
                t.check("the dark pages toggle, on by default", [control("darkPages").label, control("darkPages").value], ["Dark pages", true]);
                t.ok("it names the engine it bundles", control("darkPages").description.indexOf("Dark Reader") >= 0);
                t.ok("files written lists the native manifest", control("filesWrittenList").text.indexOf("native-messaging-hosts/browserglass.json") >= 0);
                t.check("a live control line only with a status that has it", control("statusLive").visible, json("contract/status.json").companion !== undefined);
                PluginService.saves = [];
                control("liveControl").value = true;
                t.check("the toggle saves liveControl", lastSave(), [root.pid, "liveControl", true]);
                t.check("which reaches the sync settings", synced().liveControl, true);
                const status = json("contract/status.json");
                status.companion = {
                    "enabled": true,
                    "state": "waiting_restart",
                    "hosts": 0,
                    "manifest": true
                };
                PluginService.setGlobalVar(root.pid, "status", status);
                t.check("the live control status line", [control("statusLive").visible, control("statusLive").text], [true, "Live control: waiting for a browser restart"]);
                control("liveControl").value = true;
                PluginService.saves = [];
            }
        },
        {
            "run": () => {
                openCategory("opacity");
                t.check("a category of the rail opens its page alone", shownPages(), ["opacity"]);
                control("opacityOverride").value = true;
                t.check("override saves opacityOverride", lastSave(), [root.pid, "opacityOverride", true]);
                t.ok("slider shown with the override", control("opacity").visible);
                control("opacity").value = 70;
                t.check("slider saves an int percent", lastSave(), [root.pid, "opacity", 70]);
                t.ok("stored as an integer", Number.isInteger(SettingsData.getPluginSetting(root.pid, "opacity", null)));
                const s = synced();
                t.check("sync settings: opacity fraction", s.opacity, 0.7);
                t.check("sync settings: override on", s.opacityOverride, true);
                control("opacity").value = 100;
                t.check("100% is 1.0", synced().opacity, 1);
            }
        },
        {
            "run": () => {
                for (const key of ["pagesTransparent", "newTabGlass", "readerOpaque", "privateGlass", "genericStyle"]) {
                    control(key).value = false;
                    t.check(key + " saves its key", lastSave(), [root.pid, key, false]);
                    t.check(key + " reaches the sync settings", synced()[key], false);
                }
                control("siteTheme").choose("Always dark");
                t.check("site theme saves its value, not its label", lastSave(), [root.pid, "siteTheme", "dark"]);
                t.check("site theme in the sync settings", synced().siteTheme, "dark");
                control("siteTheme").choose("Leave as is");
                t.check("leave as is", synced().siteTheme, "none");
            }
        },
        {
            "run": () => {
                const list = control("excludedSites");
                t.check("exclusion field", list.fields.map(f => [f.id, f.required]), [["domain", true]]);
                t.ok("an empty domain adds nothing", !list.submit(["  "]));
                t.ok("a domain adds a row", list.submit(["example.org"]));
                t.check("excludedSites saves {domain} rows", lastSave(), [root.pid, "excludedSites", [{
                                "domain": "example.org"
                            }]]);
                t.check("excluded in the sync settings", synced().excluded, ["example.org"]);
                // Something else (the daemon's "Exclude copied URL") writes the data
                PluginService.savePluginData(root.pid, "excludedSites", [{
                        "domain": "example.org"
                    }, {
                        "domain": "news.example"
                    }]);
                t.check("the list reloads", list.items.map(i => i.domain), ["example.org", "news.example"]);
                PluginService.savePluginData(root.pid, "opacityOverride", false);
                t.check("the override toggle reloads", control("opacityOverride").value, false);
                t.ok("and the slider hides again", !control("opacity").visible);
                t.check("the reload kept the other values", [control("opacity").value, control("siteTheme").value, control("genericStyle").value], [100, "none", false]);
            }
        },
        {
            "run": () => {
                openCategory("sites");
                const list = control("siteList");
                t.check("all sites", siteNames(), ["github.com", "+wikipedia.org", "-google.com", "youtube.com"]);
                t.check("count line", control("siteCount").text, "4 of 4 styles shown, 0 switched off");
                list.query = "wiki";
                t.check("search by name", siteNames(), ["+wikipedia.org"]);
                list.query = "GITHUB";
                t.check("case-insensitive", siteNames(), ["github.com"]);
                list.query = "youtube-nocookie";
                t.check("search by domain", siteNames(), ["youtube.com"]);
                list.query = "google wiki";
                t.check("every word must match", siteNames(), []);
                t.ok("no-match line", control("siteEmpty").visible);
                list.query = "  ";
                t.check("blank query: all", siteNames().length, 4);
                t.ok("no-match line hidden", !control("siteEmpty").visible);
                t.check("prefix not shown", [list.displayName("+wikipedia.org"), list.displayName("-google.com"), list.displayName("github.com")], ["wikipedia.org", "google.com", "github.com"]);
            }
        },
        {
            // The ListView lays its delegates out on the next frame
            "wait": 50,
            "run": () => {
                const toggle = control("siteToggle:github.com");
                t.ok("a switch per visible site", toggle !== null);
                if (!toggle)
                    return;
                t.ok("on by default", toggle.checked);
                PluginService.saves = [];
                t.tap(toggle);
                t.check("switching off saves disabledStyles", lastSave(), [root.pid, "disabledStyles", ["github.com"]]);
                t.check("disabled in the sync settings", synced().disabledStyles, ["github.com"]);
                t.ok("the switch shows it", !toggle.checked);
                t.check("count line", control("siteCount").text, "4 of 4 styles shown, 1 switched off");
                t.tap(toggle);
                t.check("switching back on", lastSave(), [root.pid, "disabledStyles", []]);
                t.check("one save per tap", savesOf("disabledStyles").length, 2);
                // Written elsewhere ({name} objects are read too)
                PluginService.savePluginData(root.pid, "disabledStyles", [{
                        "name": "youtube.com"
                    }]);
                t.check("the list reloads", control("siteList").disabled, ["youtube.com"]);
                t.ok("and its switch", !control("siteToggle:youtube.com").checked);
            }
        },
        {
            "run": () => {
                const many = [];
                for (let i = 0; i < 660; i++)
                    many.push({
                        "name": "site" + i + ".example",
                        "domains": ["site" + i + ".example"]
                    });
                PluginService.setGlobalVar(root.pid, "sites", many);
            }
        },
        {
            "wait": 50,
            "run": () => {
                t.check("660 styles", control("siteList").total, 660);
                const made = findAll(control("siteView"), "siteToggle:", []).length;
                t.ok("only the visible rows exist (" + made + ")", made > 0 && made < 40);
                control("siteList").query = "site65";
                t.check("search in a long list", siteNames(), ["site65.example", "site650.example", "site651.example", "site652.example", "site653.example", "site654.example", "site655.example", "site656.example", "site657.example", "site658.example", "site659.example"]);
            }
        },
        {
            "run": () => {
                openCategory("status");
                t.check("headline", control("statusHeadline").text, "Glass is on");
                t.check("restart line", [control("statusRestart").visible, control("statusRestart").text], [true, "Restart the browser to see the change"]);
                t.ok("no turn-on button while glass is on", !control("turnGlassOn").visible);
                t.check("opacity line", control("statusOpacity").text, "Opacity 85%, from the DMS window rules");
                t.ok("browsers listed", control("statusBrowsers").visible);
                t.check("one line per browser, with its profile count", findAll(control("statusBrowsers"), "statusBrowser", []).filter(i => i.objectName === "statusBrowser").map(i => i.text), ["Firefox: 2 profiles, 1 running, restart needed", "Firefox (Snap): 1 profile", "LibreWolf (Flatpak): 1 profile, 1 without glass", "Zen: 1 profile"]);
                // Lists that are array-like but not Arrays (what a converted
                // QVariantList looks like from JS): still counted
                const likeList = items => {
                    const o = {
                        "length": items.length
                    };
                    items.forEach((v, k) => o[k] = v);
                    return o;
                };
                const listLike = json("contract/status.json");
                listLike.browsers = likeList([Object.assign(listLike.browsers[0], {
                        "profiles": likeList(listLike.browsers[0].profiles)
                    })]);
                PluginService.setGlobalVar(root.pid, "status", listLike);
                t.check("array-like browser and profile lists", findAll(control("statusBrowsers"), "statusBrowser", []).filter(i => i.objectName === "statusBrowser").map(i => i.text), ["Firefox: 2 profiles, 1 running, restart needed"]);
                PluginService.setGlobalVar(root.pid, "status", json("contract/status.json"));
                openCategory("help");
                t.ok("a Zen browser found: the Zen Mods note shows", control("zenWarning").visible);
                openCategory("status");
                setGlass({
                    "active": false,
                    "reason": "blur_disabled"
                });
                t.check("why the glass is off", control("statusHeadline").text, "DMS blur is off");
                setGlass({
                    "opacity": 0.7,
                    "opacity_source": "override"
                }, [{
                        "code": "zen_transparency_mod",
                        "message": "x",
                        "family": "zen",
                        "profile": "p"
                    }]);
                t.check("DMS opacity while overridden: both values", control("dmsOpacity").text, "DMS window opacity: 85%, the glass uses 70%");
                t.ok("Zen warning raised", root.page.zenWarning);
                t.check("override opacity line", control("statusOpacity").text, "Opacity 70%, set by the override");
                t.check("the warning says what it means, for which browser", findAll(control("statusBlock"), "statusWarning", []).map(i => i.text), ["Zen: Zen transparency mod detected: it may stack with Browser Glass"]);
                setGlass({
                    "opacity": 0.7,
                    "opacity_source": "override",
                    "dms_opacity": undefined
                });
                t.check("a status without dms_opacity", control("dmsOpacity").text, "DMS window opacity: replaced, the glass uses 70%");
                const noZen = json("contract/status.json");
                noZen.browsers = noZen.browsers.filter(b => b.family !== "zen");
                noZen.warnings = [];
                PluginService.setGlobalVar(root.pid, "status", noZen);
                openCategory("help");
                t.ok("no Zen browser, no warning: no Zen Mods note", !control("zenWarning").visible);
                noZen.warnings = [{
                        "code": "zen_transparency_mod",
                        "message": "x",
                        "family": "zen",
                        "profile": "p"
                    }];
                PluginService.setGlobalVar(root.pid, "status", JSON.parse(JSON.stringify(noZen)));
                t.ok("the Zen warning alone shows it", control("zenWarning").visible);
                openCategory("pages");
                t.ok("Sync with portal on: no portal hint", !control("portalHint").visible);
                SettingsData.syncModeWithPortal = false;
                t.ok("Sync with portal off: the portal hint shows", control("portalHint").visible);
                SettingsData.syncModeWithPortal = true;
                openCategory("status");
                setGlass({
                    "active": false,
                    "reason": "toggled_off"
                });
                t.ok("glass turned off: the turn-on button", control("turnGlassOn").visible);
                PluginService.saves = [];
                t.press(control("turnGlassOn"));
                t.check("it saves glassEnabled", lastSave(), [root.pid, "glassEnabled", true]);
                setGlass({
                    "active": false,
                    "reason": "blur_disabled"
                });
                t.ok("off for another reason: no button", !control("turnGlassOn").visible);
                setGlass({});
            }
        },
        {
            "run": () => {
                t.press(control("copyReport"));
                t.press(control("resync"));
                t.press(control("excludeClipboard"));
                t.check("the buttons call the daemon", root.daemon.calls.slice(1), [["copyReport"], ["requestSync", "settings"], ["excludeClipboard"]]);
                t.check("no command run by the page", Proc.calls.length, 0);
                t.check("button labels", [control("copyReport").text, control("resync").text, control("excludeClipboard").text], ["Copy report", "Re-sync", "Exclude copied URL"]);
            }
        },
        {
            "run": () => {
                const cmd = root.page.uninstallCommand;
                t.check("uninstall command", cmd, "python3 -I ~/.config/DankMaterialShell/plugins/browserGlass/browserglass.py uninstall");
                t.check("shown", control("uninstallCommand").text, cmd);
                t.press(control("copyUninstall"));
                t.check("copied through dms cl copy", Quickshell.detached, [["dms", "cl", "copy", "--", cmd]]);
                t.check("toast", ToastService.log.map(x => x.message), ["Command copied to the clipboard"]);
                t.check("stdin uninstall", root.page.stdinUninstallCommand, "python3 -I -c \"" + Logic.STDIN_BOOTSTRAP + "\" uninstall < browserglass.py");
                const paths = {};
                paths[root.pid] = "/opt/my plugins/browserGlass/";
                PluginService.pluginPaths = paths;
                t.check("a path with a space is quoted", root.page.uninstallCommand, "python3 -I '/opt/my plugins/browserGlass/browserglass.py' uninstall");
                t.press(control("openReadme"));
                t.press(control("openGuide"));
                t.press(control("openIssues"));
                t.check("doc links", root.opened, ["https://github.com/lung595/browserGlass#readme", "https://github.com/lung595/browserGlass/blob/main/docs/GUIDE.md", "https://github.com/lung595/browserGlass/issues"]);
            }
        },
        {
            "run": () => {
                I18n.registerPluginTranslations(root.pid, json("translations/fr.json"));
                t.check("French page title", find(control("page:status"), "pageTitle").text, "État");
                t.check("French rail", root.page.view.categories.map(c => c.name), ["État", "Opacité", "Pages", "Sites", "Contrôle en direct", "Fichiers et désinstallation", "Aide"]);
                t.check("French button", control("copyReport").text, "Copier le rapport");
                t.check("French status", control("statusHeadline").text, "Le verre est actif");
                t.check("French warning sentence", findAll(control("statusBlock"), "statusWarning", []).map(i => i.text), ["Zen: Mod de transparence Zen détecté : il peut se cumuler avec Browser Glass"]);
                t.check("French percent, with a no-break space", control("statusOpacity").text, "Opacité 85\u00a0%, selon les règles de fenêtre DMS");
                t.check("French count line", control("siteCount").text.indexOf("styles affichés sur 660") >= 0, true);
                I18n.unregisterPluginTranslations(root.pid);
                t.check("back to English", root.page.view.categories[0].name, "Status");
            }
        },
        {
            // The search index and the pages say the same rows
            "run": () => {
                const view = root.page.view;
                const missing = view.index.entries.filter(e => !find(control("page:" + e.category), e.id)).map(e => e.category + "/" + e.id);
                t.check("every entry of the index is a row of its page", missing, []);
                const indexed = {};
                view.index.entries.forEach(e => indexed[e.id] = true);
                const settings = [];
                const walk = item => {
                    for (const child of item.children) {
                        if (child.settingKey !== undefined)
                            settings.push(child.objectName);
                        else
                            walk(child);
                    }
                };
                walk(control("settingsShell"));
                t.check("every setting is indexed", settings.filter(n => !indexed[n]), []);
                t.check("all the settings are there", settings.slice().sort(), ["darkPages", "excludedSites", "genericStyle", "liveControl", "newTabGlass", "opacity", "opacityOverride", "pagesTransparent", "privateGlass", "readerOpaque", "siteList", "siteTheme"]);
                t.check("the labels come from the index", [control("opacityOverride").label, control("siteList").label, control("openGuide").text], ["Override", "Dedicated site styles", "Guide"]);
            }
        },
        {
            "run": () => {
                const view = root.page.view;
                openCategory("status");
                t.check("the field, idle", [control("searchInput").placeholderText, control("searchHint").text], ["Search settings", "Ctrl+F or /"]);
                control("searchInput").text = "dark";
                t.check("typing sets the query", view.query, "dark");
                t.ok("and filters", view.filtering);
                t.check("only the pages with a match show", shownPages(), ["pages"]);
                t.check("only the matching rows", ["siteTheme", "darkPages", "pagesTransparent", "newTabGlass", "readerOpaque", "privateGlass"].map(n => control(n).visible), [true, true, false, false, false, false]);
                t.ok("the page keeps its title", find(control("page:pages"), "pageTitle").visible);
                t.check("the hint says how to get out", control("searchHint").text, "Esc clears");
                t.check("counts on the rail", findAll(control("rail"), "railCount", []).filter(i => i.visible).map(i => i.parent.objectName + " " + i.children[0].text), ["rail:pages 2"]);
                t.check("the categories without a match fade", ["rail:status", "rail:pages", "rail:help"].map(n => control(n).dim), [true, false, true]);
                t.check("and say so", control("rail:status").Accessible.name, "Status, no match");
                // Edited in place, while filtered
                PluginService.saves = [];
                control("darkPages").value = false;
                t.check("a match is editable in place", lastSave(), [root.pid, "darkPages", false]);
                control("darkPages").value = true;
                control("searchInput").text = "exclude";
                t.check("matches in another page", [shownPages(), view.counts], [["sites"], {
                            "sites": 2
                        }]);
                t.ok("the site list hidden: it does not match", !control("siteList").visible);
                t.press(control("excludeClipboard"));
                t.check("the matched button works", root.daemon.calls[root.daemon.calls.length - 1], ["excludeClipboard"]);
                control("searchInput").text = "opacity";
                t.check("a search across pages", shownPages(), ["status", "opacity"]);
                t.ok("no intro paragraph in a search", !control("about").visible);
                control("searchInput").text = "slider";
                t.check("the slider hidden (override off): its override switch shows instead", [control("opacityOverride").visible, control("opacity").visible, view.counts], [true, false, {
                            "opacity": 1
                        }]);
                control("opacityOverride").value = true;
                t.check("override on: the slider matches, with its switch", [view.hits.opacity === true, view.hits.opacityOverride === true, control("opacity").visible, control("opacityOverride").visible], [true, true, true, true]);
                control("opacityOverride").value = false;
                control("searchInput").text = "zzzz";
                t.ok("no results", control("noResults").visible);
                t.check("it says what was typed", control("noResultsText").text, "Nothing matches “zzzz”");
                t.check("no page shows", shownPages(), []);
                t.ok("every category fades", findAll(control("rail"), "rail:", []).every(i => i.dim));
                // Esc in the field: clears; a second one lets the page take the keys
                const field = control("searchField");
                field.clearOrRelease();
                t.check("Esc in the field clears", [view.query, view.filtering, control("searchInput").text], ["", false, ""]);
                t.ok("no results gone", !control("noResults").visible);
                t.check("the page is back", shownPages(), ["status"]);
                let released = 0;
                const onReleased = () => released++;
                field.released.connect(onReleased);
                field.clearOrRelease();
                field.released.disconnect(onReleased);
                t.check("a second Esc lets the field go", released, 1);
                // Esc on the page while filtering gives the page back; otherwise it goes on
                const shell = control("settingsShell");
                control("searchInput").text = "uninstall";
                const esc = {
                    "key": Qt.Key_Escape,
                    "text": "",
                    "modifiers": 0,
                    "accepted": false
                };
                shell.handleKey(esc);
                t.check("Esc on the page clears the search", [esc.accepted, view.query], [true, ""]);
                esc.accepted = false;
                shell.handleKey(esc);
                t.ok("not filtering: Esc goes on to the window", !esc.accepted);
                const slash = {
                    "key": Qt.Key_Slash,
                    "text": "/",
                    "modifiers": 0,
                    "accepted": false
                };
                shell.handleKey(slash);
                t.ok("/ is taken by the page", slash.accepted);
                t.ok("and focuses the field", control("searchField").fieldFocus);
                slash.accepted = false;
                slash.modifiers = Qt.ControlModifier;
                shell.handleKey(slash);
                t.ok("Ctrl+/ is left alone", !slash.accepted);
                shell.takeKeys();
                t.ok("the page has the keys back", !control("searchField").fieldFocus);
                t.check("Ctrl+F", shell.shortcut.sequence, "Ctrl+F");
                shell.shortcut.activated();
                t.ok("focuses the field", control("searchField").fieldFocus);
                // Enter opens the best match, on its page, out of the search
                control("searchInput").text = "uninstall";
                control("searchInput").accepted();
                t.check("Enter opens the best match", [view.query, view.current, view.litKey, shownPages()], ["", "files", "uninstall", ["files"]]);
                // A click on the rail while filtering opens that category at its match
                control("searchInput").text = "restart";
                t.check("restart: three pages", shownPages(), ["status", "live", "help"]);
                control("rail:help").choose();
                t.check("a rail click while filtering opens that category, lit", [view.query, view.current, view.litKey], ["", "help", "restartNote"]);
                control("rail:opacity").choose();
                t.check("and while browsing just opens", [view.current, shownPages()], ["opacity", ["opacity"]]);
                view.open("pages", "darkPages");
            }
        },
        {
            // The frame lands in the row once the page is laid out
            "wait": 30,
            "run": () => {
                const frame = find(control("page:pages"), "litFrame");
                const row = control("darkPages");
                const at = row.mapToItem(frame.parent, 0, 0);
                t.check("the opened row is framed", [frame.row.objectName, frame.opacity > 0], ["darkPages", true]);
                t.ok("around it", frame.x <= at.x && frame.y <= at.y && frame.x + frame.width >= at.x + row.width && frame.y + frame.height >= at.y + row.height && frame.height < row.height + 20);
            }
        },
        {
            "run": () => {
                // Translated: the search reads the strings on screen
                I18n.registerPluginTranslations(root.pid, json("translations/fr.json"));
                const view = root.page.view;
                control("searchInput").text = "sombre";
                t.check("French search", shownPages(), ["pages"]);
                control("searchInput").text = "desinstallation";
                t.ok("French, without the accents", view.hits.uninstall === true);
                control("searchInput").text = "zzzz";
                t.check("French no results", control("noResultsText").text, "Rien ne correspond à « zzzz »");
                t.check("French hint", control("searchHint").text, "Échap efface");
                control("searchInput").text = "";
                t.check("French placeholder", control("searchInput").placeholderText, "Rechercher dans les réglages");
                I18n.unregisterPluginTranslations(root.pid);
            }
        },
        {
            "run": () => {
                // A narrow page: icons only
                const view = root.page.view;
                t.check("wide: names on the rail", [view.compact, control("rail").width, control("railName").visible], [false, 176, true]);
                root.page.width = 360;
                t.check("narrow: icons only", [view.compact, control("rail").width, control("railName").visible, find(control("page:pages"), "pageHelp").visible], [true, 48, false, false]);
                t.check("narrow hint", control("searchHint").text, "/");
                root.page.width = 600;
                t.ok("wide again", !view.compact);
            }
        },
        {
            "run": () => fresh(false, {})
        },
        {
            "wait": 30,
            "run": () => {
                t.ok("no daemon: said so", control("noDaemon").visible);
                t.check("no daemon: buttons off", ["copyReport", "resync", "excludeClipboard"].map(n => control(n).enabled), [false, false, false]);
                t.press(control("resync"));
                t.check("no status yet", control("statusHeadline").text, "No status yet");
                t.check("DMS opacity unknown", control("dmsOpacity").text, "DMS window opacity: not known yet");
                t.check("sites loading", control("siteCount").text, "Loading the site styles…");
                t.check("settings still saved without a daemon", (control("genericStyle").value = false, lastSave()), [root.pid, "genericStyle", false]);
            }
        },
        {
            // A daemon without the sites yet: the page asks for them
            "run": () => fresh(true, {
                    "glassActive": false
                })
        },
        {
            "wait": 30,
            "run": () => {
                t.check("sites asked for", root.daemon.calls, [["refreshStatusIfIdle"], ["loadSites"]]);
                t.ok("daemon there", !control("noDaemon").visible);
                root.page.destroy();
                root.page = null;
            }
        }
    ])
}

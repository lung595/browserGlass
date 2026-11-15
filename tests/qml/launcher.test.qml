import QtQuick
import qs.Common
import qs.Services
import "components/logic.js" as Logic
import "components/launcher.js" as Launcher

// BrowserGlassLauncher.qml and components/launcher.js: which queries are
// ours, the items for each command (ids, ranks, comments for the current
// site, as active-site answers it), the empty list, the plan of each action
// (what it saves, its toasts) and the toast once its sync is done. A fake
// daemon records what the launcher asks of it; Controller.qml calls
// getItems() as DMS's launcher does (plugin view, global search).
Item {
    id: root

    Harness {
        id: t
    }

    readonly property string pid: "browserGlass"

    property var launcher: null
    property var daemon: null

    Component {
        id: controller
        Controller {}
    }

    Component {
        id: launcherComponent
        BrowserGlassLauncher {
            pluginService: PluginService
        }
    }

    // What the launcher asks of the daemon; site: what siteFor() answers
    Component {
        id: daemonComponent
        QtObject {
            property var calls: []
            property var site: null
            property bool glassOn: true
            function toggle() {
                glassOn = !glassOn;
                return true;
            }
            property var lastProvisional: null
            function siteFor(provisional) {
                calls = calls.concat([["siteFor"]]);
                lastProvisional = provisional;
                return site;
            }
            function launcherAction(a) {
                calls = calls.concat([["launcherAction", a]]);
            }
            function glassCommand(cmd) {
                calls = calls.concat([["glassCommand", cmd]]);
            }
        }
    }

    function fixture(name) {
        return Logic.parseActiveSite(t.readFile("contract/active-site-" + name + ".json"), 0);
    }

    function fresh(excluded) {
        PluginService.reset();
        SettingsData.reset();
        SettingsData.pluginSettings = {
            "browserGlass": {
                "enabled": true,
                "excludedSites": excluded || []
            }
        };
        if (root.daemon)
            root.daemon.destroy();
        root.daemon = daemonComponent.createObject(root);
        const instances = {};
        instances[root.pid] = root.daemon;
        PluginService.pluginDaemonInstances = instances;
        if (!root.launcher)
            root.launcher = launcherComponent.createObject(root);
    }

    function items(query) {
        return root.launcher.getItems(query);
    }
    function cmds(query) {
        return items(query).map(i => i.bgCmd);
    }

    Component.onCompleted: t.steps([
        {
            "run": () => {
                root.fresh([]);
                // --- The manifest -------------------------------------------
                const manifest = JSON.parse(t.readFile("plugin.json"));
                t.check("plugin.json: the launcher component", manifest.components.launcher, "./BrowserGlassLauncher.qml");
                t.ok("plugin.json: the launcher capability", manifest.capabilities.indexOf("launcher") >= 0);
                t.check("plugin.json: the trigger", manifest.trigger, "glass");
                t.check("the launcher's own trigger and id", [root.launcher.trigger, root.launcher.pluginId], ["glass", "browserGlass"]);
                t.check("the same error codes as logic.js", Launcher.SITE_ERRORS, Logic.SITE_ERRORS);

                // --- PluginService.togglePlugin (dms ipc call plugins toggle) --
                // DMS picks the launcher instance first, then needs toggle()
                const picked = root.launcher || PluginService.pluginDaemonInstances[root.pid];
                t.check("togglePlugin finds a toggle()", typeof picked.toggle, "function");
                t.check("it flips the daemon's glass, twice", [picked.toggle(), root.daemon.glassOn, picked.toggle(), root.daemon.glassOn], [true, false, true, true]);
                PluginService.pluginDaemonInstances = {};
                t.check("no daemon: false", root.launcher.toggle(), false);
                root.fresh([]);

                // --- Queries ------------------------------------------------
                t.check("not ours", ["", "g", "gsettings", "glassy", "gsx", "list", "firefox", " gl", "glass-on"].map(q => items(q).length), [0, 0, 0, 0, 0, 0, 0, 0, 0]);
                t.check("not ours: null", [null, undefined].map(q => Launcher.parseQuery(q)), [null, null]);
                t.check("gs: the five commands", cmds("gs"), ["on", "off", "blist", "unblist", "list"]);
                t.check("glass: the same", cmds("glass"), ["on", "off", "blist", "unblist", "list"]);
                t.check("a trailing space", cmds("gs "), ["on", "off", "blist", "unblist", "list"]);
                t.check("any case: GS Fix is blist", cmds("GS Fix"), ["blist"]);
                t.check("prefixes", ["gs b", "gs f", "gs u", "gs l", "gs o", "gs on", "glass of", "gs unb"].map(cmds), [["blist"], ["blist"], ["unblist"], ["list"], ["on", "off"], ["on"], ["off"], ["unblist"]]);
                t.check("an unknown word: nothing", cmds("gs zzz"), []);
                t.check("parseQuery", Launcher.parseQuery("  Glass  LIST  proton me "), {
                    "word": "list",
                    "rest": "proton me"
                });
                t.check("commandOf", ["on", "FIX", "blist", "unb", "l", "o", "", "nope"].map(Launcher.commandOf), ["on", "blist", "blist", "unblist", "list", "", "", ""]);

                // --- Items ----------------------------------------------------
                const all = items("gs");
                t.check("unique ids", new Set(all.map(i => i.id)).size, 5);
                t.check("ids", all.map(i => i.id), ["browserGlass:on", "browserGlass:off", "browserGlass:blist", "browserGlass:unblist", "browserGlass:list"]);
                t.check("_preScored keeps the order", all.map(i => i._preScored), [1000, 999, 998, 997, 996]);
                t.check("icons", all.map(i => i.icon), ["material:blur_on", "material:blur_off", "material:block", "material:undo", "material:list"]);
                t.check("keywords: name and alias", all[2].keywords, ["blist", "fix"]);
                t.check("names", all.map(i => i.name), ["Glass on", "Glass off", "Exclude the current site", "Put the current site back under glass", "Excluded sites"]);
                t.check("glass state and list count", [all[0].comment, all[4].comment], ["Glass is on", "No excluded sites"]);
                t.check("the site is still unknown", [all[2].comment, all[2].bgSite], ["Finding the current site…", null]);
                t.check("the daemon was asked for it", root.daemon.calls.filter(c => c[0] === "siteFor").length > 0, true);
                root.daemon.calls = [];
                items("gs on");
                items("gs list");
                t.check("no site asked for on, off or list", root.daemon.calls, []);
                SettingsData.setPluginSetting(root.pid, "glassEnabled", false);
                t.check("glass off shown", items("gs on")[0].comment, "Glass is off");
            }
        },
        {
            "run": () => {
                // --- The current site (active-site answers) --------------------
                root.fresh([{
                        "domain": "github.io"
                    }, "example.org"]);
                root.daemon.site = fixture("companion");
                let list = items("gs");
                t.check("companion: the domain and its subdomains", list[2].comment, "proton.me — with its subdomains");
                t.check("not excluded yet", list[3].comment, "proton.me is not excluded");
                t.check("the item carries the site", list[2].bgSite, {
                    "host": "account.proton.me",
                    "domain": "proton.me",
                    "source": "companion",
                    "age": null
                });
                t.check("list count", list[4].comment, "Excluded: 2 sites");
                root.daemon.site = Object.assign({}, fixture("companion"), {
                    "provisional": true
                });
                list = items("gs");
                t.check("provisional: the domain shown, no site to act on (Enter runs by name)", [list[2].comment, list[2].bgSite, list[3].bgSite], ["proton.me — with its subdomains", null, null]);
                t.check("the launcher asks for a provisional answer", root.daemon.lastProvisional, true);
                root.daemon.site = fixture("session");
                list = items("gs");
                t.check("session: covered by github.io, unblist names that entry", [list[2].comment, list[3].comment], ["user.github.io is already excluded", "github.io is excluded"]);
                root.fresh(["https://account.proton.me/login"]);
                root.daemon.site = fixture("companion");
                list = items("gs");
                t.check("host-only exclusion: unblist names the host, not the domain", [list[2].comment, list[3].comment], ["proton.me — with its subdomains", "account.proton.me is excluded"]);
                root.fresh(["proton.me"]);
                root.daemon.site = fixture("companion");
                list = items("gs");
                t.check("domain exclusion: unblist names the domain", list[3].comment, "proton.me is excluded");
                root.fresh(["proton.me", "account.proton.me"]);
                root.daemon.site = fixture("companion");
                list = items("gs");
                t.check("two covering exclusions: unblist names both, as its toast", list[3].comment, "proton.me, account.proton.me is excluded");
                root.fresh([{
                        "domain": "github.io"
                    }, "example.org"]);
                for (const code of Logic.SITE_ERRORS) {
                    root.daemon.site = fixture(code);
                    const it = items("gs b")[0];
                    t.check("error " + code + ": the refusal shown, no site to act on", [it.comment === Launcher.launcherText(code), it.bgSite], [true, null]);
                }
                root.daemon.site = fixture("private");
                t.check("private window", items("gs fix")[0].comment, "Private window: site not detected");
                root.daemon.site = {
                    "error": "failed"
                };
                t.check("failed lookup", items("gs b")[0].comment, "Current site not found");

                // --- Running items ------------------------------------------------
                root.daemon.site = fixture("companion");
                root.daemon.calls = [];
                root.launcher.executeItem(items("gs b")[0]);
                t.check("blist with the site shown", root.daemon.calls.filter(c => c[0] !== "siteFor"), [["launcherAction", {
                                "host": "account.proton.me",
                                "domain": "proton.me",
                                "source": "companion",
                                "age": null,
                                "kind": "blist"
                            }]]);
                root.daemon.site = null;
                root.daemon.calls = [];
                root.launcher.executeItem(items("gs unblist")[0]);
                root.launcher.executeItem(items("gs off")[0]);
                root.launcher.executeItem(items("gs list")[0]);
                t.check("no site yet, off: by name (the daemon waits for the site)", root.daemon.calls.filter(c => c[0] !== "siteFor"), [["glassCommand", "unblist"], ["glassCommand", "off"], ["launcherAction", {
                                "host": "github.io",
                                "domain": "github.io",
                                "source": "list",
                                "age": null,
                                "kind": "list-remove"
                            }]]);
            }
        },
        {
            "run": () => {
                // --- The list ---------------------------------------------------------
                root.fresh([{
                        "domain": "proton.me"
                    }, {
                        "domain": "WWW.GitHub.com."
                    }, {
                        "domain": "proton.me"
                    }, {
                        "nodomain": 1
                    }]);
                let list = items("gs list");
                t.check("one row per excluded site, normalised (www. kept, as sync applies it), once", list.map(i => i.name), ["proton.me", "www.github.com"]);
                t.check("rows remove", list.map(i => [i.bgCmd, i.comment, i.id]), [["list-remove", "Enter: remove from the list", "browserGlass:list:proton.me"], ["list-remove", "Enter: remove from the list", "browserGlass:list:www.github.com"]]);
                t.check("rows ranked", list.map(i => i._preScored), [1000, 999]);
                t.check("a filter", items("glass list git").map(i => i.name), ["www.github.com"]);
                t.check("a filter matching nothing", items("gs list zzz"), []);
                t.check("one site: singular", Launcher.commandItems(Launcher.matchCommands("list"), {
                    "excludedSites": ["a.org"]
                })[0].comment, "Excluded: 1 site");
                root.fresh([]);
                list = items("gs list");
                t.check("empty list: one item that does nothing", list.map(i => [i.name, i.bgCmd, i.bgSite]), [["No excluded sites", "none", null]]);
                root.daemon.calls = [];
                root.launcher.executeItem(list[0]);
                t.check("running it asks nothing", root.daemon.calls, []);

                // --- French -----------------------------------------------------------
                I18n.registerPluginTranslations(root.pid, JSON.parse(t.readFile("translations/fr.json")));
                root.daemon.site = fixture("companion");
                list = items("gs");
                t.check("French names and comments", [list[0].name, list[2].name, list[2].comment, list[4].comment], ["Verre activé", "Exclure le site courant", "proton.me — avec ses sous-domaines", "Aucun site exclu"]);
                I18n.unregisterPluginTranslations(root.pid);
            }
        },
        {
            "run": () => {
                // --- Domains, as browserglass.py normalize_domain() reads them ---
                const vectors = [["https://www.YouTube.com/", "www.youtube.com"], ["*.youtube.com", "youtube.com"], ["bücher.de", "xn--bcher-kva.de"], ["BÜCHER.de.", "xn--bcher-kva.de"], ["faß.de", "xn--fa-hia.de"], ["https://user:pw@Sub.Example.com:8080/path?q#f", "sub.example.com"], ["..example.org", "example.org"], ["*.*.x.org", "x.org"], ["münchen.bücher.de", "xn--mnchen-3ya.xn--bcher-kva.de"], ["ｅｘａｍｐｌｅ。ｃｏｍ", "example.com"], ["日本語。jp", "xn--wgv71a119e.jp"], ["президент.рф", "xn--d1abbgf6aiiy.xn--p1ai"], ["[::1]", ""], ["bad host", ""], ["a_b.com", ""], ["", ""], ["http://", ""], ["a".repeat(64) + ".com", ""], ["例え.テスト", "xn--r8jz45g.xn--zckzah"], ["ab--c.ü", "ab--c.xn--tda"], ["www.gov.uk", "www.gov.uk"], ["x.com/path", "x.com"], ["mañana.com", "xn--maana-pta.com"], ["ǅ.com", "xn--d-toa.com"], ["😀.com", "xn--e28h.com"]];
                t.check("normDomain matches normalize_domain", vectors.map(v => Launcher.normDomain(v[0])), vectors.map(v => v[1]));
                t.check("an entry: {domain} or a string; nothing else", [Launcher.entryDomain({
                        "domain": "*.YouTube.com"
                    }), Launcher.entryDomain("https://www.youtube.com/watch?v=1"), Launcher.entryDomain(null), Launcher.entryDomain(7)], ["youtube.com", "www.youtube.com", "", ""]);
                const shaped = ["https://www.youtube.com/", {
                        "domain": "*.example.com"
                    }, "x.org"];
                const yt = {
                    "kind": "blist",
                    "host": "www.youtube.com",
                    "domain": "www.youtube.com",
                    "source": "companion"
                };
                let p = Launcher.planAction(yt, shaped);
                t.check("blist: a URL entry covers its host, no duplicate", [p.save, p.toasts.map(x => [x.text, x.textArg])], [null, [["%1 is already excluded", "www.youtube.com"]]]);
                p = Launcher.planAction(Object.assign({}, yt, {
                    "host": "mail.example.com",
                    "domain": "example.com"
                }), shaped);
                t.check("blist: a *. entry covers the domain", p.save, null);
                p = Launcher.planAction(Object.assign({}, yt, {
                    "kind": "unblist"
                }), shaped);
                t.check("unblist removes a URL entry", p.save.value, [{
                        "domain": "*.example.com"
                    }, "x.org"]);
                p = Launcher.planAction(Object.assign({}, yt, {
                    "kind": "unblist",
                    "host": "a.example.com",
                    "domain": "example.com"
                }), shaped);
                t.check("unblist removes a *. entry", p.save.value, ["https://www.youtube.com/", "x.org"]);
                p = Launcher.planAction({
                    "kind": "list-remove",
                    "domain": "example.com",
                    "source": "list"
                }, shaped);
                t.check("list-remove of a *. entry", p.save.value, ["https://www.youtube.com/", "x.org"]);
                t.check("list shows the normalised names, each once", Launcher.listItems("", shaped.concat(["WWW.YouTube.com"])).map(i => i.name), ["www.youtube.com", "example.com", "x.org"]);

                // --- gs list past DMS's 10 items per plugin -------------------
                const many = [];
                for (let i = 0; i < 15; i++)
                    many.push("site" + (i < 10 ? "0" : "") + i + ".org");
                let list = Launcher.listItems("", many);
                t.check("15 sites: 9 and one 'more' item", [list.length, list.slice(0, 9).every(i => i.bgCmd === "list-remove"), list[9].bgCmd, list[9].bgSite, list[9].name, list[9].nameArg], [10, true, "none", null, "%1 more: type gs list <filter>", "6"]);
                t.check("it ranks last", list[9]._preScored < list[8]._preScored, true);
                t.check("10 sites: all shown", Launcher.listItems("", many.slice(0, 10)).map(i => i.bgCmd).indexOf("none"), -1);
                t.check("a filter narrows it", Launcher.listItems("site1", many).map(i => i.name), ["site10.org", "site11.org", "site12.org", "site13.org", "site14.org"]);
                t.check("translated", JSON.parse(t.readFile("translations/fr.json"))[Launcher.launcherText("listMore")] !== undefined, true);

                // --- The plugin view: bare command words -----------------------
                const dms = "performSearch@file:///usr/share/quickshell/dms/Modals/DLauncherV2/Controller.qml:1436\n";
                t.check("fromPluginView", [Launcher.fromPluginView("getItems@file:///p/BrowserGlassLauncher.qml:40\n" + dms), Launcher.fromPluginView("getItems@x:1\n_performPluginPhase@file:///d/Controller.qml:900\n" + dms), Launcher.fromPluginView("getItems@x:1\n_refreshPluginResults@file:///d/Controller.qml:9\n"), Launcher.fromPluginView("performSearch@file:///other/Thing.qml:3\n"), Launcher.fromPluginView(undefined)], [true, false, false, false, false]);
                t.check("queryFor: bare words in the plugin view only", [Launcher.queryFor("on", true).word, Launcher.queryFor("", true).word, Launcher.queryFor(" list x", true).rest, Launcher.queryFor("on", false), Launcher.queryFor("", false), Launcher.queryFor("gs off", true).word], ["on", "", "x", null, null, "off"]);
                root.fresh(["a.org"]);
                const c = controller.createObject(root);
                t.check("Browse view, empty query: the commands", c.performSearch(root.launcher, "").map(i => i.bgCmd), ["on", "off", "blist", "unblist", "list"]);
                t.check("Browse view: bare words", [c.performSearch(root.launcher, "on").map(i => i.bgCmd), c.performSearch(root.launcher, "list").map(i => i.name), c.performSearch(root.launcher, "gs of").map(i => i.bgCmd)], [["on"], ["a.org"], ["off"]]);
                t.check("global empty query (home page): nothing", [c._performPluginPhase(root.launcher, "").length, c._performPluginPhase(root.launcher, "on").length], [0, 0]);
                t.check("a typed global query: prefix only", [c._pluginQueryItems(root.launcher, "on").length, c._pluginQueryItems(root.launcher, "gs on").map(i => i.bgCmd)], [0, ["on"]]);
                t.check("called directly: prefix only", [items("").length, items("on").length], [0, 0]);
                // DMS caps a plugin at 10 items in the global search only
                root.fresh(many);
                t.check("plugin view, 15 sites: all 15", [c.performSearch(root.launcher, "list").length, c.performSearch(root.launcher, "gs list").filter(i => i.bgCmd === "list-remove").length], [15, 15]);
                t.check("global search, 15 sites: 9 and 'more'", c._pluginQueryItems(root.launcher, "gs list").map(i => i.bgCmd).filter(x => x === "none").length, 1);
                c.destroy();
            }
        },
        {
            "run": () => {
                // --- Plans: what an action saves and toasts -------------------------
                const site = {
                    "kind": "blist",
                    "host": "account.proton.me",
                    "domain": "proton.me",
                    "source": "companion",
                    "age": null
                };
                let p = Launcher.planAction(site, []);
                t.check("blist saves the domain", p.save, {
                    "key": "excludedSites",
                    "value": [{
                            "domain": "proton.me"
                        }]
                });
                t.check("and waits for its sync", [p.toasts, p.pending.kind, p.pending.domain, p.reopen], [[], "exclude", "proton.me", false]);
                const kept = [{
                        "domain": "x.org"
                    }];
                Launcher.planAction(site, kept);
                t.check("the list given is not mutated", kept, [{
                        "domain": "x.org"
                    }]);
                p = Launcher.planAction(site, ["Proton.me."]);
                t.check("already covered: no save, one toast", [p.save, p.toasts.map(x => [x.level, x.text, x.textArg])], [null, [["info", "%1 is already excluded", "proton.me"]]]);
                p = Launcher.planAction(site, ["www.proton.me"]);
                t.check("a www. entry covers that host only, as sync applies it", p.save.value, ["www.proton.me", {
                        "domain": "proton.me"
                    }]);
                p = Launcher.planAction(Object.assign({}, site, {
                    "host": "www.gov.uk",
                    "domain": "www.gov.uk"
                }), []);
                t.check("blist of www.gov.uk saves www.gov.uk, never the public suffix gov.uk", [p.save.value, p.pending.domain], [[{
                            "domain": "www.gov.uk"
                        }], "www.gov.uk"]);
                p = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist",
                    "host": "example.com",
                    "domain": "example.com"
                }), [{
                        "domain": "www.example.com"
                    }]);
                t.check("unblist: a www. entry does not cover the bare domain", p.save, null);
                p = Launcher.planAction(Object.assign({}, site, {
                    "domain": "user.github.io"
                }), [{
                        "domain": "github.io"
                    }]);
                t.check("covered by a parent domain", p.save, null);
                p = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist"
                }), [{
                        "domain": "proton.me"
                    }, {
                        "domain": "account.proton.me"
                    }, {
                        "domain": "x.org"
                    }]);
                t.check("unblist drops every covering entry", p.save.value, [{
                        "domain": "x.org"
                    }]);
                t.check("and waits for its sync, naming the entries removed", [p.pending.kind, p.pending.domain], ["include", "proton.me, account.proton.me"]);
                p = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist"
                }), ["https://account.proton.me/", "x.org"]);
                t.check("unblist of a host-only exclusion names the host", [p.save.value, p.pending.domain], [["x.org"], "account.proton.me"]);
                t.check("its toast too", Launcher.toastFor(p.pending, Logic.parseSync('{"glass":true,"live":{"hosts":1,"acked":1}}', 0), true).textArg, "account.proton.me");
                p = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist"
                }), ["proton.me"]);
                t.check("unblist of a domain exclusion names the domain", p.pending.domain, "proton.me");
                p = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist"
                }), [{
                        "domain": "mail.proton.me"
                    }]);
                t.check("unblist of a site not excluded", [p.save, p.toasts.map(x => x.text)], [null, ["%1 is not excluded"]]);
                p = Launcher.planAction({
                    "kind": "list-remove",
                    "domain": "proton.me",
                    "source": "list"
                }, [{
                        "domain": "proton.me"
                    }, {
                        "domain": "mail.proton.me"
                    }]);
                t.check("list-remove drops that entry only, then reopens the list", [p.save.value, p.reopen], [[{
                            "domain": "mail.proton.me"
                        }], true]);
                t.check("on and off", [Launcher.planAction({
                        "kind": "on"
                    }, []).save, Launcher.planAction({
                        "kind": "off"
                    }, []).save], [{
                        "key": "glassEnabled",
                        "value": true
                    }, {
                        "key": "glassEnabled",
                        "value": false
                    }]);
                // Refusals: warnings, no save
                const refusals = Logic.SITE_ERRORS.concat(["failed", "new_code"]).map(code => Launcher.planAction(Object.assign({
                        "kind": "blist"
                    }, fixture(code === "failed" || code === "new_code" ? "private" : code), code === "failed" || code === "new_code" ? {
                        "error": code
                    } : {}), []));
                t.check("refusals: no save", refusals.every(r => r.save === null && r.pending === null), true);
                t.check("refusals: one warning each", refusals.map(r => r.toasts.map(x => x.level)), Logic.SITE_ERRORS.concat(["failed", "new_code"]).map(() => ["warning"]));
                t.check("refusal texts", refusals.map(r => r.toasts[0].text), ["No browser in the foreground", "Private window: site not detected", "Not a web page", "Browser session unreadable", "Current tab uncertain", "Address not supported", "Restart the browser once more", "Current site not found", "Current site not found"]);
                t.check("a failure says to try again", [refusals[7].toasts[0].details, refusals[7].toasts[0].detailsTr], ["try again in a few seconds", true]);

                // --- The toast once the sync is done --------------------------------
                const live = Logic.parseSync('{"glass":true,"live":{"hosts":1,"acked":1}}', 0);
                const notLive = Logic.parseSync('{"glass":true,"live":{"hosts":1,"acked":0}}', 0);
                const ex = Launcher.planAction(site, []).pending;
                t.check("live: excluded", Launcher.toastFor(ex, live, true).text, "%1 excluded");
                t.check("live control off: after a restart", Launcher.toastFor(ex, live, false).text, "%1 excluded — applies after a restart");
                t.check("no add-on acknowledged: after a restart", Launcher.toastFor(ex, notLive, true).text, "%1 excluded — applies after a restart");
                t.check("a failed sync: no toast (its error shows)", Launcher.toastFor(ex, Logic.parseSync("", 1), true), null);
                const sess = Launcher.planAction(Object.assign({}, site, {
                    "source": "session",
                    "age": 42.4
                }), []).pending;
                const st = Launcher.toastFor(sess, live, true);
                t.check("session: never live, its age mentioned", [st.text, st.details, st.detailsTr, st.detailsArg], ["%1 excluded — applies after a restart", "from the session saved %1 ago", true, "42 s"]);
                const fresh = Launcher.toastFor(Launcher.planAction(Object.assign({}, site, {
                    "source": "session",
                    "age": 3.4
                }), []).pending, live, true);
                t.check("a recent session: no mention", fresh.details, "");
                const inc = Launcher.planAction(Object.assign({}, site, {
                    "kind": "unblist"
                }), ["proton.me"]).pending;
                t.check("unblist toasts", [Launcher.toastFor(inc, live, true).text, Launcher.toastFor(inc, notLive, true).text], ["%1 back under glass", "%1 back under glass — applies after a restart"]);
                const rm = Launcher.planAction({
                    "kind": "list-remove",
                    "domain": "proton.me",
                    "source": "list"
                }, ["proton.me"]).pending;
                t.check("list-remove applies live too", Launcher.toastFor(rm, live, true).text, "%1 back under glass");
                t.check("glass on and off", [Launcher.toastFor(Launcher.planAction({
                        "kind": "on"
                    }, []).pending, notLive, true).text, Launcher.toastFor(Launcher.planAction({
                        "kind": "off"
                    }, []).pending, notLive, true).text], ["Glass on", "Glass off"]);
                const blurOff = Logic.parseSync('{"glass":false,"reason":"blur_disabled","live":{"hosts":0,"acked":0}}', 0);
                const onBlocked = Launcher.toastFor(Launcher.planAction({
                    "kind": "on"
                }, []).pending, blurOff, true);
                t.check("glass on while the sync says glass is off: a warning saying why", [onBlocked.level, onBlocked.text, onBlocked.details, onBlocked.detailsTr], ["warning", "Glass on, but not shown", "DMS blur is off", true]);
                t.check("glass off while glass is off: the plain toast", Launcher.toastFor(Launcher.planAction({
                    "kind": "off"
                }, []).pending, blurOff, true).text, "Glass off");
                t.check("the warning is translated", Object.keys(JSON.parse(t.readFile("translations/fr.json"))).indexOf("Glass on, but not shown") >= 0, true);
                t.check("a site action after a restart replaces the restart toast; live, or glass on/off, does not", [Launcher.replacesRestartToast(Launcher.toastFor(ex, notLive, true)), Launcher.replacesRestartToast(Launcher.toastFor(inc, notLive, true)), Launcher.replacesRestartToast(Launcher.toastFor(ex, live, true)), Launcher.replacesRestartToast(Launcher.toastFor(inc, live, true)), Launcher.replacesRestartToast(Launcher.toastFor(Launcher.planAction({
                        "kind": "on"
                    }, []).pending, notLive, true)), Launcher.replacesRestartToast(null)], [true, true, false, false, false, false]);
                t.check("every launcher text is translated", Object.keys(JSON.parse(t.readFile("translations/fr.json"))).indexOf(Launcher.launcherText("excludedRestart")) >= 0, true);
                root.launcher.destroy();
                root.daemon.destroy();
            }
        }
    ])
}

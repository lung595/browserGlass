import QtQuick
import "components/logic.js" as Logic

// components/logic.js on its own: settings JSON, command lines, output
// parsing, the sync debounce bookkeeping, toast and status decisions, the
// clipboard exclusion and the teardown choice.
Item {
    id: root

    Harness {
        id: t
    }

    function fixture(name) {
        return JSON.parse(t.readFile("contract/" + name));
    }

    Component.onCompleted: {
        t.steps([
            {
                "run": () => {
                    // --- Settings JSON -------------------------------------------
                    const defaults = root.fixture("settings-default.json");
                    t.check("no pluginData gives the contract's defaults", Logic.buildSettings({}, true, false), defaults);
                    t.check("null pluginData too", Logic.buildSettings(null, true, false), defaults);
                    t.check("every contract key, in the contract's order", Object.keys(Logic.buildSettings({}, true, false)), Object.keys(defaults));
                    t.check("settingsJson is the same object as text", JSON.parse(Logic.settingsJson({}, true, false)), defaults);
                    t.check("settingsJson is stable text", Logic.settingsJson({
                        "opacity": 70
                    }, true, false), Logic.settingsJson({
                        "opacity": 70
                    }, true, false));
                    const s = Logic.buildSettings({
                        "glassEnabled": false,
                        "opacityOverride": true,
                        "opacity": 70,
                        "siteTheme": "dark",
                        "pagesTransparent": false,
                        "genericStyle": false,
                        "excludedSites": [
                            {
                                "domain": " github.com "
                            },
                            {
                                "domain": ""
                            },
                            {
                                "domain": "github.com"
                            },
                            {
                                "nope": 1
                            },
                            "example.org"
                        ],
                        "disabledStyles": ["youtube.com", {
                                "name": "wikipedia.org"
                            }, 7],
                        "newTabGlass": false,
                        "readerOpaque": false,
                        "privateGlass": false,
                        "liveControl": false,
                        "darkPages": false
                    }, false, true);
                    t.check("every key is mapped", s, {
                        "blur": false,
                        "isLight": true,
                        "glassEnabled": false,
                        "opacityOverride": true,
                        "opacity": 0.7,
                        "siteTheme": "dark",
                        "pagesTransparent": false,
                        "genericStyle": false,
                        "excluded": ["github.com", "example.org"],
                        "disabledStyles": ["youtube.com", "wikipedia.org"],
                        "newTabGlass": false,
                        "readerOpaque": false,
                        "privateGlass": false,
                        "liveControl": false,
                        "darkPages": false
                    });
                    t.check("blur and isLight come from DMS, not pluginData", [Logic.buildSettings({
                            "blur": false,
                            "isLight": true
                        }, true, false).blur, Logic.buildSettings({
                            "isLight": true
                        }, true, false).isLight], [true, false]);
                    t.check("an unknown siteTheme falls back to follow", Logic.buildSettings({
                        "siteTheme": "sepia"
                    }, true, false).siteTheme, "follow");
                    t.check("siteTheme none is kept", Logic.buildSettings({
                        "siteTheme": "none"
                    }, true, false).siteTheme, "none");
                    t.check("string booleans", Logic.buildSettings({
                        "glassEnabled": "false",
                        "privateGlass": "garbage"
                    }, true, false).glassEnabled, false);
                    t.check("an unreadable boolean keeps its default", Logic.buildSettings({
                        "privateGlass": "garbage"
                    }, true, false).privateGlass, true);
                    const before = {
                        "excludedSites": [
                            {
                                "domain": " a.com "
                            }
                        ]
                    };
                    Logic.buildSettings(before, true, false);
                    t.check("pluginData is not mutated", before.excludedSites[0].domain, " a.com ");

                    // --- Percent slider -> 0..1 opacity ----------------------------
                    t.check("percent slider", [0, 1, 50, 70, 85, 100].map(Logic.opacityFraction), [0, 0.01, 0.5, 0.7, 0.85, 1]);
                    t.check("a fraction is kept", [0.85, 0.5, 0.333].map(Logic.opacityFraction), [0.85, 0.5, 0.33]);
                    t.check("out of range is clamped", [-20, 250].map(Logic.opacityFraction), [0, 1]);
                    t.check("garbage gives the default", [NaN, "x", null, undefined].map(Logic.opacityFraction), [0.85, 0.85, 0.85, 0.85]);
                    t.check("a numeric string", Logic.opacityFraction(" 60 "), 0.6);
                    t.check("the slider value reaches --settings", Logic.buildSettings({
                        "opacity": 55
                    }, true, false).opacity, 0.55);
                    t.check("the default slider percent is the contract's opacity", Logic.opacityFraction(Logic.DEFAULTS.opacity), defaults.opacity);

                    // --- Command lines -------------------------------------------
                    const dir = "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass/";
                    const base = "/tmp/fakehome/.config/DankMaterialShell/plugins/browserGlass";
                    t.check("sync argv", Logic.syncArgv(dir, "{}"), ["python3", "-I", base + "/browserglass.py", "sync", "--data", base + "/data", "--settings", "{}", "--if-plugin", base + "/plugin.json", "--plugin-dir", base]);
                    t.check("sync argv with a settings file: no settings in it", Logic.syncArgv(dir, "{\"excluded\":[\"a.com\"]}", "/run/user/1000/f.json"), ["python3", "-I", base + "/browserglass.py", "sync", "--data", base + "/data", "--settings-file", "/run/user/1000/f.json", "--if-plugin", base + "/plugin.json", "--plugin-dir", base]);
                    t.check("the settings file goes in the runtime dir", [Logic.settingsFilePath("/run/user/1000/"), Logic.settingsFilePath("/run/user/1000")], ["/run/user/1000/browserGlass-sync-settings.json", "/run/user/1000/browserGlass-sync-settings.json"]);
                    t.check("no (or a relative) runtime dir: no file", [Logic.settingsFilePath(""), Logic.settingsFilePath(null), Logic.settingsFilePath("run")], ["", "", ""]);
                    t.check("active-site argv", Logic.activeSiteArgv(base, {
                        "id": 7,
                        "pid": 4242,
                        "app_id": "firefox",
                        "title": "-x Proton"
                    }), ["python3", "-I", base + "/browserglass.py", "active-site", "--json", "--pid=4242", "--app-id=firefox", "--window-id=7", "--data", base + "/data"]);
                    t.check("active-site argv without an id", Logic.activeSiteArgv(base, {
                        "pid": "12",
                        "app_id": "zen"
                    }).slice(5, 8), ["--pid=12", "--app-id=zen", "--window-id=-1"]);
                    t.check("the title never goes in the argv", Logic.activeSiteArgv(base, {
                        "id": 7,
                        "pid": 4242,
                        "app_id": "firefox",
                        "title": "Inbox (3) - Secret"
                    }).join(" ").indexOf("Secret"), -1);
                    t.ok("the script knows --window-id", t.readFile("browserglass.py").indexOf('add_argument("--window-id"') >= 0);
                    t.ok("the script knows active-site", t.readFile("browserglass.py").indexOf('"active-site"') >= 0);
                    t.ok("the script knows --if-plugin", t.readFile("browserglass.py").indexOf('p.add_argument("--if-plugin"') >= 0);
                    t.ok("the script knows --plugin-dir", t.readFile("browserglass.py").indexOf('p.add_argument("--plugin-dir"') >= 0);
                    t.check("status argv", Logic.statusArgv(base), ["python3", "-I", base + "/browserglass.py", "status", "--json"]);
                    t.check("sites argv", Logic.sitesArgv(base), ["python3", "-I", base + "/browserglass.py", "sites", "--json", "--data", base + "/data"]);
                    t.check("report argv", Logic.reportArgv(base), ["python3", "-I", base + "/browserglass.py", "report"]);
                    t.check("uninstall argv", Logic.uninstallArgv(base), ["python3", "-I", base + "/browserglass.py", "uninstall"]);
                    t.check("manifest path", Logic.manifestPath(base + "//"), base + "/plugin.json");
                    t.check("sweep argv", Logic.sweepArgv(base), ["python3", "-I", "-c", Logic.STDIN_BOOTSTRAP, "uninstall", "--if-gone", base + "/plugin.json"]);
                    t.ok("EXIT_KEPT is the script's own code", t.readFile("browserglass.py").indexOf("\nEXIT_KEPT = " + Logic.EXIT_KEPT + "  #") >= 0);
                    const script = t.readFile("browserglass.py");
                    t.ok("browserglass.py is readable from the test copy", script.length > 100000);
                    t.ok("STDIN_BOOTSTRAP is the script's own constant", script.indexOf("\nSTDIN_BOOTSTRAP = " + JSON.stringify(Logic.STDIN_BOOTSTRAP) + "\n") >= 0);
                    t.ok("the bootstrap reads stdin, not a file", Logic.STDIN_BOOTSTRAP.indexOf("sys.stdin.read()") > 0 && Logic.STDIN_BOOTSTRAP.length < 200);
                    t.check("the plugin id", Logic.PLUGIN_ID, "browserGlass");
                    t.check("constants of the plan", [Logic.SYNC_DEBOUNCE_MS, Logic.POLL_INTERVAL_MS], [800, 10000]);

                    // --- Parsing ---------------------------------------------------
                    const syncText = t.readFile("contract/sync.json");
                    const sync = Logic.parseSync("noise\n" + syncText + "\n\n", 0);
                    t.check("parseSync reads the contract line", [sync.ok, sync.result.glass, sync.result.first_run, sync.result.running_changed, sync.result.warnings.length], [true, true, true, ["0f1e2d3c4b5a"], 1]);
                    t.check("parseSync on a failure gives the error line", Logic.parseSync(t.readFile("contract/error.json"), 2), {
                        "ok": false,
                        "result": null,
                        "error": "invalid --settings: expected a JSON object"
                    });
                    t.check("parseSync without an error line gives the exit code", Logic.parseSync("Traceback...", 1).error, "exit code 1");
                    t.check("a timeout", Logic.parseSync("", 124).error, "timed out");
                    t.check("parseSync on garbage", [Logic.parseSync("{nope", 0).ok, Logic.parseSync("", 0).ok, Logic.parseSync('{"glass":"yes"}', 0).ok], [false, false, false]);
                    t.check("parseSync without live gives zeros", Logic.parseSync('{"glass":true}', 0).result.live, {
                        "hosts": 0,
                        "acked": 0
                    });
                    t.check("parseSync reads live", Logic.parseSync('{"glass":true,"live":{"hosts":2,"acked":1}}', 0).result.live, {
                        "hosts": 2,
                        "acked": 1
                    });
                    t.check("parseSync ignores a bad live", Logic.parseSync('{"glass":true,"live":{"hosts":"2","acked":-1}}', 0).result.live, {
                        "hosts": 0,
                        "acked": 0
                    });
                    const withCompanion = Logic.parseSync(t.readFile("contract/sync-companion.json"), 0).result;
                    t.check("parseSync keeps the companion states", withCompanion.companion.map(c => c.state).slice(0, 2), ["pending_restart", "installed"]);
                    t.check("parseSync without them gives none", [sync.result.companion, Logic.parseSync('{"glass":true,"companion":[1,null,{"profile":"p"}]}', 0).result.companion], [[], [{
                                    "profile": "p"
                                }]]);
                    // A pending add-on found loaded by a status
                    const statusDoc = JSON.parse(t.readFile("contract/status.json"));
                    t.check("companionLoaded: pending in the sync, installed in the status", Logic.companionLoaded(withCompanion, statusDoc), true);
                    t.check("companionLoaded: nothing pending, or not installed yet", [Logic.companionLoaded(sync.result, statusDoc), Logic.companionLoaded({
                                    "companion": [{
                                            "profile": "0f1e2d3c4b5a",
                                            "state": "pending_restart"
                                        }]
                                }, statusDoc)], [false, false]);
                    t.check("companionLoaded: unreadable input", [Logic.companionLoaded(null, statusDoc), Logic.companionLoaded(withCompanion, null), Logic.companionLoaded(withCompanion, {
                                    "browsers": [null, {
                                            "profiles": [null]
                                        }]
                                })], [false, false, false]);
                    t.check("liveControlChanged", [Logic.liveControlChanged('{"liveControl":true}', '{"liveControl":false}'), Logic.liveControlChanged('{"liveControl":true,"opacity":1}', '{"liveControl":true}'), Logic.liveControlChanged("", '{"liveControl":true}')], [true, false, false]);
                    // active-site answers (contract fixtures, one per outcome)
                    t.check("parseActiveSite: companion", Logic.parseActiveSite(t.readFile("contract/active-site-companion.json"), 0), {
                        "host": "account.proton.me",
                        "domain": "proton.me",
                        "source": "companion",
                        "age": null
                    });
                    t.check("parseActiveSite: session", Logic.parseActiveSite(t.readFile("contract/active-site-session.json"), 0), {
                        "host": "user.github.io",
                        "domain": "user.github.io",
                        "source": "session",
                        "age": 3.4
                    });
                    t.check("parseActiveSite: each error code", Logic.SITE_ERRORS.map(code => Logic.parseActiveSite(t.readFile("contract/active-site-" + code + ".json"), 0).error), Logic.SITE_ERRORS);
                    t.check("parseActiveSite: a failure", [Logic.parseActiveSite("", 1).error, Logic.parseActiveSite("{nope", 0).error, Logic.parseActiveSite('{"error":"new_code"}', 0).error, Logic.parseActiveSite('{"host":"a.b"}', 0).error], ["failed", "failed", "failed", "failed"]);
                    const noop = Logic.parseSync(t.readFile("contract/sync-noop.json"), 0);
                    t.check("the noop fixture", [noop.ok, noop.result.changed, noop.result.first_run], [true, [], false]);
                    t.ok("the busy error is recognised", Logic.isBusyError("another browserGlass command holds the state lock; try again"));
                    t.ok("other errors are not busy", !Logic.isBusyError("invalid --settings: expected a JSON object"));

                    const st = Logic.parseStatus(t.readFile("contract/status.json"), 0);
                    t.check("parseStatus on the pretty fixture", [st.ok, st.glassActive, st.restartNeeded, st.stale, st.held, st.status.browsers.length], [true, true, true, false, false, 4]);
                    const stale = Logic.parseStatus(JSON.stringify({
                        "glass": {
                            "active": false
                        },
                        "restart_needed": false,
                        "warnings": [
                            {
                                "code": "niri_rule_stale",
                                "message": "x"
                            }
                        ]
                    }), 0);
                    t.check("niri_rule_stale is seen", [stale.ok, stale.stale, stale.held, stale.restartNeeded], [true, true, false, false]);
                    const held = Logic.parseStatus('{"glass":{"active":false},"restart_needed":true,"warnings":[{"code":"niri_rule_held"}]}', 0);
                    t.check("niri_rule_held is seen", [held.held, held.restartNeeded, held.status.browsers], [true, true, []]);
                    t.check("parseStatus failure", [Logic.parseStatus("", 1).ok, Logic.parseStatus("[]", 0).ok, Logic.parseStatus("{}", 0).error], [false, false, "unreadable status output"]);

                    const sites = Logic.parseSites(t.readFile("contract/sites.json"), 0);
                    t.ok("parseSites reads the fixture", sites.ok && sites.sites.length > 0 && typeof sites.sites[0].name === "string" && Array.isArray(sites.sites[0].domains));
                    t.check("parseSites drops bad entries", Logic.parseSites('[{"name":"a.com"},{"x":1},"b",{"name":"c.com","domains":["c.com"]}]', 0).sites, [
                        {
                            "name": "a.com",
                            "domains": []
                        },
                        {
                            "name": "c.com",
                            "domains": ["c.com"]
                        }
                    ]);
                    t.check("parseSites failure", [Logic.parseSites("{}", 0).ok, Logic.parseSites("", 3).error], [false, "exit code 3"]);
                    t.check("reason texts", ["active", "blur_disabled", "opaque", "toggled_off", "forced_off", "?"].map(Logic.reasonText).every(x => typeof x === "string" && x.length > 0), true);

                    // --- Debounce bookkeeping ----------------------------------------
                    let b = Logic.newSyncBook();
                    let r = Logic.syncRequest(b, "start", 1000, 800);
                    t.check("first request schedules", [r.schedule, r.book.phase, r.book.reasons], [true, "scheduled", ["start"]]);
                    t.check("the book given is not mutated", b.phase, "idle");
                    r = Logic.syncRequest(r.book, "pluginData", 1100, 800);
                    t.check("a request inside the window reschedules (restarts the debounce)", [r.schedule, r.book.scheduledAt, r.book.dirty, r.book.reasons], [true, 1100, false, ["start", "pluginData"]]);
                    r = Logic.syncRequest(r.book, "pluginData", 1150, 800);
                    t.check("a repeated reason is listed once", r.book.reasons, ["start", "pluginData"]);
                    r = Logic.syncRequest(r.book, "blur", 1150 + 800, 800);
                    t.check("a request after the window marks dirty, no new launch", [r.schedule, r.book.dirty, r.book.phase], [false, true, "scheduled"]);
                    let f = Logic.syncFinished(r.book, 3000, false);
                    t.check("a dirty book runs once more after the sync", [f.schedule, f.retry, f.book.phase, f.book.dirty, f.book.scheduledAt], [true, false, "scheduled", false, 3000]);
                    f = Logic.syncFinished(f.book, 4000, false);
                    t.check("then goes idle", [f.schedule, f.book.phase, f.book.reasons], [false, "idle", []]);
                    // Busy retries
                    let book = Logic.syncRequest(Logic.newSyncBook(), "x", 0, 800).book;
                    const retries = [];
                    for (let i = 0; i < 5; i++) {
                        const out = Logic.syncFinished(book, 10 * i, true);
                        retries.push([out.schedule, out.retry]);
                        book = out.book;
                    }
                    t.check("a busy failure retries MAX_BUSY_RETRIES times, then stops", retries, [[true, true], [true, true], [true, true], [false, false], [false, false]]);
                    t.check("MAX_BUSY_RETRIES", Logic.MAX_BUSY_RETRIES, 3);
                    f = Logic.syncFinished(book, 100, false);
                    t.check("a success resets the retry count", f.book.busyRetries, 0);
                    book.busyRetries = 3;
                    t.check("a new request resets the retry count", Logic.syncRequest(book, "ipc", 200, 800).book.busyRetries, 0);
                    // The wall clock went back while a sync was scheduled
                    r = Logic.syncRequest(Logic.newSyncBook(), "x", 5000, 800);
                    r = Logic.syncRequest(r.book, "y", 1000, 800);
                    t.check("a negative delta counts as launched: dirty, no restart", [r.schedule, r.book.dirty, r.book.scheduledAt], [false, true, 5000]);
                    // A launcher command: no debounce
                    r = Logic.syncRequestNow(Logic.newSyncBook(), "launcher", 5000);
                    t.check("an idle book launches at once", [r.schedule, r.book.phase, r.book.urgent], [true, "scheduled", false]);
                    t.check("a later request counts it as launched", Logic.syncRequest(r.book, "settings", 5000, 800).schedule, false);
                    r = Logic.syncRequest(Logic.newSyncBook(), "settings", 5000, 800);
                    r = Logic.syncRequestNow(r.book, "launcher", 5100);
                    t.check("a pending debounced request is restarted with no wait", [r.schedule, r.book.reasons], [true, ["settings", "launcher"]]);
                    r = Logic.syncRequest(Logic.newSyncBook(), "settings", 5000, 800);
                    r = Logic.syncRequestNow(r.book, "launcher", 5000 + 800);
                    t.check("a sync that may run: an urgent one follows", [r.schedule, r.book.dirty, r.book.urgent], [false, true, true]);
                    f = Logic.syncFinished(r.book, 7000, false);
                    t.check("the follow-up is urgent", [f.schedule, f.urgent, f.retry, f.book.urgent], [true, true, false, false]);
                    t.check("then nothing more", Logic.syncFinished(f.book, 7100, false).schedule, false);
                    r = Logic.syncRequest(Logic.newSyncBook(), "a", 0, 800);
                    r = Logic.syncRequest(r.book, "b", 900, 800);
                    t.check("a debounced follow-up is not urgent", Logic.syncFinished(r.book, 1000, false).urgent, false);

                    // --- Toasts ---------------------------------------------------------
                    t.ok("the restart toast is recognised", Logic.isRestartToast(Logic.syncToasts(Logic.parseSync('{"glass":true,"running_changed":["p"]}', 0), Logic.newToastContext()).toasts[0]));
                    t.ok("other toasts are not", !Logic.isRestartToast({
                        "text": "Browser Glass sync failed"
                    }) && !Logic.isRestartToast(null));
                    t.check("live status lines", ["connected", "waiting_restart", "outdated", "unavailable", "removed", "off", "?"].map(Logic.liveStatusText).map(x => x.indexOf("Live control: ") === 0), [true, true, true, true, true, true, true]);
                    t.ok("each live state has its own line", new Set(["connected", "waiting_restart", "outdated", "unavailable", "removed", "off"].map(Logic.liveStatusText)).size === 6);
                    let ctx = Logic.newToastContext();
                    let out = Logic.syncToasts(Logic.parseSync(t.readFile("contract/sync.json"), 0), ctx);
                    t.check("first run: set-up toast + the zen warning", out.toasts.map(x => x.level), ["info", "warning"]);
                    t.ok("first run with glass on asks for a restart", /restart/i.test(out.toasts[0].text));
                    t.ok("the first run counts as the restart toast", out.ctx.restartShown);
                    t.check("the warning toast carries the message", out.toasts[1].details, "Zen transparency mod detected; it may stack with browserGlass.");
                    const firstCtx = out.ctx;
                    const later = Logic.parseSync(JSON.stringify({
                        "glass": true,
                        "opacity": 0.85,
                        "reason": "active",
                        "first_run": false,
                        "changed": ["a"],
                        "running_changed": ["a"],
                        "niri_changed": false,
                        "warnings": [
                            {
                                "code": "zen_transparency_mod",
                                "message": "m",
                                "family": "zen",
                                "profile": "13579bdf0246"
                            }
                        ]
                    }), 0);
                    t.check("no second restart toast, no repeated warning in the same episode", Logic.syncToasts(later, firstCtx).toasts, []);
                    out = Logic.syncToasts(later, Logic.newToastContext());
                    t.check("a running browser's files changed: restart toast", out.toasts.map(x => [x.level, /restart/i.test(x.text)]), [["info", true], ["warning", false]]);
                    const notRunning = Logic.parseSync('{"glass":true,"opacity":0.85,"reason":"active","first_run":false,"changed":["a"],"running_changed":[],"niri_changed":true,"warnings":[]}', 0);
                    t.check("files changed but no browser running: no toast", Logic.syncToasts(notRunning, Logic.newToastContext()).toasts, []);
                    const offFirst = Logic.parseSync('{"glass":false,"opacity":1,"reason":"blur_disabled","first_run":true,"changed":[],"running_changed":[],"niri_changed":false,"warnings":[]}', 0);
                    out = Logic.syncToasts(offFirst, Logic.newToastContext());
                    t.check("first run with glass off says why", [out.toasts.length, out.toasts[0].level, out.toasts[0].details], [1, "info", Logic.reasonText("blur_disabled")]);
                    t.check("that reason is a source string to translate", out.toasts[0].detailsTr, true);
                    const fail = Logic.parseSync('{"error":"boom"}', 2);
                    out = Logic.syncToasts(fail, Logic.newToastContext());
                    t.check("an error toast", [out.toasts.length, out.toasts[0].level, out.toasts[0].details], [1, "error", "boom"]);
                    t.check("the same error again stays silent", Logic.syncToasts(fail, out.ctx).toasts, []);
                    const gone = Logic.parseSync('{"error":"plugin_gone: the plugin folder (--if-plugin) is gone or being removed; nothing was written"}', 1);
                    t.ok("the plugin_gone error is recognised", Logic.isPluginGoneError(gone.error) && !Logic.isPluginGoneError("invalid --settings: plugin_gone:"));
                    t.check("a plugin_gone refusal stays silent", Logic.syncToasts(gone, Logic.newToastContext()).toasts, []);
                    t.check("a busy retry stays silent", Logic.syncToasts(Logic.parseSync('{"error":"another browserGlass command holds the state lock; try again"}', 2), Logic.newToastContext(), true).toasts, []);
                    const afterOk = Logic.syncToasts(notRunning, out.ctx).ctx;
                    t.check("a success clears the shown error", afterOk.lastErrorShown, "");
                    t.check("so the error toasts again", Logic.syncToasts(fail, afterOk).toasts.length, 1);
                    const otherWarn = Logic.parseSync('{"glass":true,"opacity":0.85,"reason":"active","first_run":false,"changed":[],"running_changed":[],"niri_changed":false,"warnings":[{"code":"site_style_invalid","message":"x"},{"code":"read_only","message":"user.js is read-only","profile":"p1"},{"code":"read_only","message":"again","profile":"p2"}]}', 0);
                    const warnToasts = Logic.syncToasts(otherWarn, Logic.newToastContext()).toasts;
                    t.check("only the listed warning codes toast, once per profile", warnToasts.map(x => x.details), ["user.js is read-only", "again"]);
                    t.check("each says what its code means; the CLI message stays as is", warnToasts.map(x => [x.text, x.detailsTr === true]), [[Logic.warningText("read_only"), false], [Logic.warningText("read_only"), false]]);
                    t.check("every toast code has its own sentence", Logic.TOAST_WARNINGS.filter(c => Logic.warningText(c) === Logic.warningText("unknown_code")), []);
                    t.check("an unknown code: the generic sentence", Logic.warningText("unknown_code"), "Browser Glass warning");
                    t.check("shown warnings drop the stale rule (and held, when asked)", [Logic.statusWarnings({
                                "warnings": [{
                                        "code": "niri_rule_stale"
                                    }, {
                                        "code": "niri_rule_held"
                                    }, null, {
                                        "code": "read_only"
                                    }]
                            }, false).map(w => w.code), Logic.statusWarnings({
                                "warnings": [{
                                        "code": "niri_rule_held"
                                    }, {
                                        "code": "read_only"
                                    }]
                            }, true).map(w => w.code), Logic.statusWarnings(null, false)], [["niri_rule_held", "read_only"], ["read_only"], []]);
                    t.check("family names", [Logic.familyName("librewolf"), Logic.familyName("newfox"), Logic.familyName(""), Logic.familyName("constructor")], ["LibreWolf", "newfox", "?", "constructor"]);
                    t.check("family names, each once", Logic.familyNames([{
                                "family": "zen"
                            }, {
                                "family": "firefox"
                            }, {
                                "family": "zen"
                            }, null, {}]), ["Zen", "Firefox"]);
                    t.check("a null outcome is an error", Logic.syncToasts(null, null).toasts.map(x => x.level), ["error"]);

                    // --- Status decisions ------------------------------------------------
                    const needs = Logic.parseStatus('{"glass":{"active":true},"restart_needed":true,"warnings":[]}', 0);
                    const fine = Logic.parseStatus('{"glass":{"active":true},"restart_needed":false,"warnings":[]}', 0);
                    let d = Logic.statusDecision(needs, firstCtx);
                    t.check("restart_needed true: poll", [d.poll, d.resync], [true, false]);
                    t.ok("the restart episode goes on", d.ctx.restartShown);
                    d = Logic.statusDecision(fine, d.ctx);
                    t.check("restart_needed false: stop polling", [d.poll, d.resync], [false, false]);
                    t.ok("and the restart episode ends", !d.ctx.restartShown);
                    t.check("a failed status stops polling", Logic.statusDecision(Logic.parseStatus("", 1), d.ctx).poll, false);
                    d = Logic.statusDecision(stale, Logic.newToastContext());
                    t.check("niri_rule_stale: resync, no poll", [d.poll, d.resync], [false, true]);
                    const again = Logic.statusDecision(stale, d.ctx);
                    t.check("only once per stale episode", again.resync, false);
                    const cleared = Logic.statusDecision(fine, again.ctx);
                    t.check("a status without it ends the episode", Logic.statusDecision(stale, cleared.ctx).resync, true);
                    d = Logic.statusDecision(st, Logic.newToastContext());
                    t.check("status warnings toast once", [d.toasts.length, Logic.statusDecision(st, d.ctx).toasts.length], [1, 0]);
                    t.check("held keeps polling", Logic.statusDecision(held, Logic.newToastContext()).poll, true);

                    // --- Clipboard exclusion ---------------------------------------------
                    const hosts = ["https://www.Example.com/path?q=1#x", "http://user:pw@sub.example.org:8080/", "example.net", "example.com:8080/x", "about:newtab", "file:///etc/passwd", "", "two words.com", "localhost", "https:/bad.com", "javascript:alert(1)", "https://[::1]/", "https://a..b.com"];
                    t.check("hostFromText", hosts.map(Logic.hostFromText), ["example.com", "sub.example.org", "example.net", "example.com", "", "", "", "", "", "", "", "", ""]);
                    const odd = ["https://evil.example\\@good.example/", "https://a_b.example/", "https://x.example;y/", "https://-x.example/", "https://x-.example/", "https://Bücher.Example/", "https://a\"b.example/", "https://x.example%2f/", "https://xn--bcher-kva.example/"];
                    t.check("hostFromText: a backslash ends the host; only letters, digits, dots, hyphens", odd.map(Logic.hostFromText), ["evil.example", "", "", "", "", "bücher.example", "", "", "xn--bcher-kva.example"]);
                    const list = [
                        {
                            "domain": "github.com"
                        }
                    ];
                    let e = Logic.excludeFromClipboard("https://news.example.com/a", list);
                    t.check("adds the copied host", [e.ok, e.reason, e.domain, e.list], [true, "added", "news.example.com", [
                            {
                                "domain": "github.com"
                            },
                            {
                                "domain": "news.example.com"
                            }
                        ]]);
                    t.check("the list given is not mutated", list.length, 1);
                    e = Logic.excludeFromClipboard("https://www.GitHub.com/x", list);
                    t.check("already excluded", [e.ok, e.reason, e.list.length], [true, "already", 1]);
                    e = Logic.excludeFromClipboard("https://docs.github.com/en", list);
                    t.check("a parent domain listed: already excluded (subdomains included)", [e.reason, e.domain, e.list.length], ["already", "docs.github.com", 1]);
                    e = Logic.excludeFromClipboard("https://notgithub.com/", [{
                            "domain": "www.GitHub.com."
                        }]);
                    t.check("only a real parent domain counts", e.reason, "added");
                    e = Logic.excludeFromClipboard("https://github.com/", [{
                            "domain": "www.GitHub.com."
                        }]);
                    t.check("a listed www. host does not cover the bare domain", [e.reason, e.domain, e.list.length], ["added", "github.com", 2]);
                    e = Logic.excludeFromClipboard("https://example.org/", [{
                            "domain": "www.example.org"
                        }]);
                    t.check("www.example.org listed, example.org copied: added", e.reason, "added");
                    e = Logic.excludeFromClipboard("https://www.example.org/", [{
                            "domain": "example.org"
                        }]);
                    t.check("example.org listed, www.example.org copied: already", e.reason, "already");
                    t.check("www. is kept when dropping it would leave a public suffix", ["https://www.gov.uk/", "https://www.example.org/", "https://www.bbc.co.uk/", "https://www.co.jp/", "https://www.example.co/"].map(Logic.hostFromText), ["www.gov.uk", "example.org", "bbc.co.uk", "www.co.jp", "example.co"]);
                    e = Logic.excludeFromClipboard("https://www.gov.uk/", []);
                    t.check("www.gov.uk copied: saved as is, not the suffix", [e.reason, e.domain], ["added", "www.gov.uk"]);
                    e = Logic.excludeFromClipboard("https://example.com/", [{
                            "domain": "*.example.com"
                        }]);
                    t.check("*.example.com listed, example.com copied: already", e.reason, "already");
                    e = Logic.excludeFromClipboard("https://example.com/a", [{
                            "domain": "https://Example.com/"
                        }]);
                    t.check("a URL listed covers its host", e.reason, "already");
                    e = Logic.excludeFromClipboard("https://Bücher.example/", [{
                            "domain": "xn--bcher-kva.example"
                        }]);
                    t.check("an IDN listed in punycode, copied in Unicode: already", e.reason, "already");
                    e = Logic.excludeFromClipboard("https://xn--bcher-kva.example/", [{
                            "domain": "bücher.example"
                        }]);
                    t.check("an IDN listed in Unicode, copied in punycode: already", e.reason, "already");
                    t.check("normDomain is shared", Logic.normDomain("https://user@Sub.Example.com:8080/p"), "sub.example.com");
                    e = Logic.excludeFromClipboard("not a url", undefined);
                    t.check("invalid clipboard", [e.ok, e.reason, e.list], [false, "invalid", []]);

                    // --- Teardown --------------------------------------------------------
                    t.check("teardown choices", [Logic.teardownAction(false, true, true), Logic.teardownAction(true, true, true), Logic.teardownAction(undefined, true, true), Logic.teardownAction(false, false, true), Logic.teardownAction(true, false, true), Logic.teardownAction(false, false, false)], ["uninstall", "none", "none", "sweep", "sweep", "none"]);
                    const store = {
                        "browserGlass": {
                            "enabled": false
                        },
                        "other": {
                            "x": 1
                        }
                    };
                    t.check("withoutPlugin drops only that entry", Logic.withoutPlugin(store, "browserGlass"), {
                        "other": {
                            "x": 1
                        }
                    });
                    t.check("withoutPlugin leaves its argument alone", Object.keys(store).length, 2);
                    t.check("withoutPlugin without the entry", [Logic.withoutPlugin({
                            "other": {}
                        }, "browserGlass"), Logic.withoutPlugin(null, "browserGlass")], [null, null]);
                }
            }
        ]);
    }
}

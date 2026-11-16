"""End-to-end: each site's own dark mode (extension/theme.js). Under a
dark theme the add-on sets the value a site reads to pick its theme (a
localStorage key, a cookie of a recipe) before the page's scripts run, and
puts the prior value back under a light theme or once the site is
excluded. In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 30 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_theme.py' -v

The add-on of extension/ is installed as a temporary add-on, from a copy
with two test scripts added: a background script that applies a list sent
by the page (applyList, as a list from the helper; there is no helper
here), and a content script that relays it from window.postMessage. So the
registration of the theme payload, theme.js and content.js are the real
ones. Local pages on made-up .test hosts, one host per case (each its own
localStorage). Checked:
  - a page that reads localStorage.theme ("light") in an inline <head>
    script boots dark, with neither Dark Reader nor the dark marks; a light
    theme puts "light" back live and drops the record; the next load boots
    light;
  - a value the user already set to "dark": no record, left as is under a
    light theme;
  - the user (or the site) sets it back to "light" after the write:
    declined, never written again;
  - a page that forces "light" on every load: written once at most;
  - a page that has the key but no dark theme: the value goes back, the
    record says failed, and Dark Reader darkens it; the next load writes
    nothing;
  - theme="classic", theme='{"a":1}', themeColor="light" are left alone,
    and an absent key is never created;
  - an excluded host: the value goes back live, and nothing is written on
    the next load;
  - a recipe cookie the server renders from: exactly one reload, then the
    server's dark page; the next load is not reloaded;
  - a late write (darken turned on while the page is open): Dark Reader on
    this load, not marked failed, the next load boots dark;
  - a composite cookie read by an inline <head> script (MediaWiki's
    clientprefs, "a-clientpref-1%2Cskin-theme-clientpref-day"): the day
    theme is swapped in place and the other prefs kept, an absent cookie is
    created, and a light theme puts the day theme back;
  - a localStorage recipe whose `from` holds null (npm's npm-color-mode,
    light when absent): the key is created dark before the page reads it,
    and removed again under a light theme;
  - a localStorage key with "/" read by a script at the end of <body>
    (RTS's rts/feature/darkmode, "none" when absent): created dark, the
    page judged dark, removed under a light theme;
  - a cookie named with a leading dot that the server renders from
    (Galaxus's .themeshade): one reload, then dark, removed under a light
    theme; the same cookie already set HttpOnly by the server (unseen by
    scripts, the write refused): one reload at most, then failed and Dark
    Reader, never reloaded again;
  - the bundled recipes of the French state's design system (DSFR:
    service-public.gouv.fr, www.info.gouv.fr, impots.gouv.fr) on a page
    built like theirs:
    the server marks <html data-fr-scheme="light">, a script at the end of
    <body> reads localStorage.scheme over it and writes the scheme it
    applies back. A first visit is created dark (no Dark Reader), removed
    under a light theme; the "light" the page then stores itself is
    written dark and put back; "system" (dark under a dark system) is left
    alone;
  - the bundled recipe of the Home Assistant demo on a page built like it:
    localStorage.demo_theme holds JSON, {"theme":"default","dark":false}
    when absent, and without a dark key the page follows the system live.
    A first visit is created '{"theme":"default"}' (dark, no Dark Reader)
    and removed under a light theme; the stored light JSON is written and
    put back;
  - the bundled recipe of Proton's account pages on a page built like
    them: localStorage.theme holds a number ("2" light, "1" dark, "0" the
    system), light when absent. A first visit is created "1" (dark, no
    Dark Reader) and removed under a light theme; a stored "2" is written
    "1" and put back; "0" (dark under a dark system) is left alone.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
EXT = os.path.join(tone.REPO, "extension")
HOSTS = ("ls.test", "user.test", "back.test", "force.test", "ignore.test", "odd.test",
         "absent.test", "excl.test", "cookie.test", "late.test", "wiki.test", "wiki2.test", "create.test",
         "slash.test", "shade.test", "hidden.test", "dsfr.test", "dsfr2.test", "dsfr3.test", "ha.test",
         "proton.test")
RECORD = "browserGlass.theme"

TEXT = "<p>" + "Some readable text on a page with its own theme menu. " * 8 + "</p>"
STYLE = """<style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
html.night, html.night body {background:rgb(17,17,17); color:rgb(230,230,230)}
</style>"""
# Reads localStorage.theme before the first paint, as theme menus do.
LS_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><script>
window.__boot = localStorage.getItem("theme");
if (window.__boot === "dark") document.documentElement.classList.add("night");
</script>""" + STYLE + "</head><body>" + TEXT + "</body></html>")
# The same, then writes its default back on every load.
FORCE_PAGE = LS_PAGE.replace("</script>", 'localStorage.setItem("theme", "light");\n</script>', 1)
# Has the key, but no dark theme at all.
IGNORE_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><script>
window.__boot = localStorage.getItem("theme");
</script>""" + STYLE + "</head><body>" + TEXT + "</body></html>")

# Reads a list of client prefs from a cookie before the first paint, as
# MediaWiki does (comma-separated, %2C in the cookie).
WIKI_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><script>
var m = document.cookie.match(/(?:^|; )wikiprefs=([^;]*)/);
window.__boot = m ? decodeURIComponent(m[1]) : null;
if (window.__boot && window.__boot.indexOf("skin-theme-clientpref-night") >= 0)
  document.documentElement.classList.add("night");
</script>""" + STYLE + "</head><body>" + TEXT + "</body></html>")
WIKI_RECIPES = [
    {"store": "cookie", "key": "wikiprefs", "op": "set", "from": [None], "to": "skin-theme-clientpref-night",
     "verified": "2026-11-15", "note": "test fixture"},
    {"store": "cookie", "key": "wikiprefs", "op": "swap", "from": ["skin-theme-clientpref-day"],
     "to": "skin-theme-clientpref-night", "verified": "2026-11-15", "note": "test fixture"},
]

# Reads a key with "/" in a script at the end of <body>, as RTS does.
SLASH_KEY = "site/feature/darkmode"
SLASH_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
body[data-dark-mode=dark] {background:rgb(17,17,17); color:rgb(230,230,230)}
</style></head><body>""" + TEXT + """<script>
window.__boot = localStorage.getItem("site/feature/darkmode");
document.body.setAttribute("data-dark-mode", window.__boot || "none");
</script></body></html>""")
SLASH_RECIPE = {"store": "local", "key": SLASH_KEY, "op": "set", "from": [None, "none"], "to": "dark",
                "verified": "2026-11-16", "note": "test fixture"}

# The French state's design system (DSFR): the server marks the light
# scheme on <html>; a script at the end of <body> reads localStorage.scheme
# (light, dark, system) over it and stores the scheme it applies.
DSFR_PAGE = ("""<!doctype html><html data-fr-scheme="light"><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
html[data-fr-theme=dark], html[data-fr-theme=dark] body {background:rgb(22,22,22); color:rgb(206,206,206)}
</style></head><body>""" + TEXT + """<script>
var r = document.documentElement, s = localStorage.getItem("scheme");
window.__boot = s;
if (["light", "dark", "system"].indexOf(s) < 0) s = r.getAttribute("data-fr-scheme");
localStorage.setItem("scheme", s);
r.setAttribute("data-fr-scheme", s);
r.setAttribute("data-fr-theme", s === "system"
  ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : s);
</script></body></html>""")

# The Home Assistant demo: localStorage.demo_theme holds JSON (light when
# absent); without a "dark" key the theme follows the system, live.
HA_LIGHT = '{"theme":"default","dark":false}'
HA_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><script>
var t = localStorage.getItem("demo_theme"), o;
window.__boot = t;
try { o = t ? JSON.parse(t) : {theme: "default", dark: false}; } catch (e) { o = {theme: "default", dark: false}; }
var mq = matchMedia("(prefers-color-scheme: dark)");
function paint() {
  document.documentElement.classList.toggle("night", o.dark === undefined ? mq.matches : o.dark === true);
}
paint();
mq.addEventListener("change", paint);
</script>""" + STYLE + "</head><body>" + TEXT + "</body></html>")

# Proton's account pages: localStorage.theme holds a number, "2" light,
# "1" dark, "0" Auto (the system, live); light when absent.
PROTON_PAGE = ("""<!doctype html><html><head><meta charset="utf-8"><script>
var t = localStorage.getItem("theme");
window.__boot = t;
var mq = matchMedia("(prefers-color-scheme: dark)");
function paint() {
  document.documentElement.classList.toggle("night", t === "1" || t === "0" && mq.matches);
}
paint();
mq.addEventListener("change", paint);
</script>""" + STYLE + "</head><body>" + TEXT + "</body></html>")


def bundled(host):
    """The recipes data/themes.json ships for `host` (none: [])."""
    with open(os.path.join(tone.REPO, "data", bg.THEMES_FILE), encoding="utf-8") as f:
        return json.load(f)["sites"].get(host, [])


TEST_FEED = """// test only: a list sent by the page (test-relay.js), applied as one
// from the helper
browser.runtime.onConnect.addListener((p) => {
  if (p.name !== "bg-test")
    return;
  p.onMessage.addListener((m) => {
    const c = JSON.parse(m.list);
    enqueue(() => applyList(cleanList(c.domains), c.darken === true, cleanThemes(c.themes), null, null))
      .then(() => p.postMessage({n: m.n}));
  });
});
"""
# A port, not runtime.sendMessage: the Dark Reader build wraps that one in
# the content scripts' sandbox.
TEST_RELAY = """let bgTestPort = null;
window.addEventListener("message", (e) => {
  if (e.source !== window || !e.data || typeof e.data.bgTestList !== "string")
    return;
  if (!bgTestPort) {
    bgTestPort = browser.runtime.connect({name: "bg-test"});
    bgTestPort.onMessage.addListener((m) =>
      document.documentElement.setAttribute("data-browserglass-test-ack", String(m.n)));
  }
  bgTestPort.postMessage({list: e.data.bgTestList, n: e.data.n});
});
"""

STATE = ("const r = document.documentElement;"
         "return {boot: window.__boot === undefined ? 'unset' : window.__boot,"
         " theme: localStorage.getItem('theme'), record: JSON.parse(localStorage.getItem(arguments[0])),"
         " darkreader: !!document.querySelector('style.darkreader'),"
         " marks: r.classList.contains('dark') || r.hasAttribute('data-theme'),"
         " mark: r.getAttribute('data-browserglass-theme'), tone: r.getAttribute(arguments[1]),"
         " night: r.classList.contains('night'), cookie: document.cookie};")


def themes_doc(sites=None):
    with open(os.path.join(tone.REPO, "data", bg.THEMES_FILE), encoding="utf-8") as f:
        doc = json.load(f)
    doc["sites"] = sites or {}
    return bg.themes_clean(doc)


COOKIE_RECIPE = {"store": "cookie", "key": "mode", "op": "set", "from": [None, "light"], "to": "dark",
                 "reload": True, "verified": "2026-11-15", "note": "test fixture"}

# The server renders its theme from ".shade" (/g.html); /hide.html sets
# it HttpOnly, as Galaxus does once a visitor picks a theme.
SHADE_RECIPE = {"store": "cookie", "key": ".shade", "op": "set", "from": [None, "light"], "to": "dark",
                "reload": True, "verified": "2026-11-16", "note": "test fixture"}

CREATE_RECIPE = {"store": "local", "key": "theme", "op": "set", "from": [None, "light"], "to": "dark",
                 "verified": "2026-11-15", "note": "test fixture"}


class Server:
    """Pages of the cases; /c.html and /g.html render their theme from the
    "mode" and ".shade" cookies (counted per load); /hide.html sets
    ".shade=light" HttpOnly."""

    def __init__(self):
        self.hits = []
        hits = self.hits

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                cookie = self.headers.get("Cookie") or ""
                extra = []
                if path in ("/c.html", "/g.html"):
                    hits.append(cookie)
                    night = ("mode=dark" if path == "/c.html" else ".shade=dark") \
                        in cookie.replace(" ", "").split(";")
                    body = ('<!doctype html><html class="%s"><head><meta charset="utf-8">'
                            % ("night" if night else "")) + STYLE + "</head><body>" + TEXT + "</body></html>"
                else:
                    if path == "/hide.html":
                        extra.append(("Set-Cookie", ".shade=light; HttpOnly; Path=/"))
                    body = {"/ls.html": LS_PAGE, "/force.html": FORCE_PAGE, "/hide.html": LS_PAGE,
                            "/ignore.html": IGNORE_PAGE, "/w.html": WIKI_PAGE,
                            "/rts.html": SLASH_PAGE, "/dsfr.html": DSFR_PAGE,
                            "/ha.html": HA_PAGE, "/proton.html": PROTON_PAGE}.get(path)
                    if body is None:
                        self.send_error(404)
                        return
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                for k, v in extra:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, host, path="/ls.html"):
        return "http://%s:%d%s" % (host, self.port, path)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_extension(root):
    """A copy of extension/ with the test feed and relay."""
    ext = os.path.join(root, "ext")
    shutil.copytree(EXT, ext)
    with open(os.path.join(ext, "test-feed.js"), "w", encoding="utf-8") as f:
        f.write(TEST_FEED)
    with open(os.path.join(ext, "test-relay.js"), "w", encoding="utf-8") as f:
        f.write(TEST_RELAY)
    path = os.path.join(ext, "manifest.json")
    with open(path, encoding="utf-8") as f:
        man = json.load(f)
    man["background"]["scripts"].append("test-feed.js")
    man["content_scripts"].append({"matches": ["http://*/*"], "js": ["test-relay.js"],
                                   "run_at": "document_start"})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(man, f)
    return ext


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ThemeE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()

    def test_theme(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    # ---- helpers ------------------------------------------------------------

    def feed(self, b, domains=(), darken=True, sites=None):
        """Sends a list to the add-on through the open page, as the helper
        would, and waits until it is applied."""
        self.n += 1
        cfg = {"domains": list(domains), "darken": darken, "themes": themes_doc(sites)}
        b.js("window.postMessage({bgTestList: arguments[0], n: arguments[1]}, '*');", json.dumps(cfg), self.n)
        self.assertTrue(b.wait_for("return document.documentElement.getAttribute("
                                   "'data-browserglass-test-ack') === String(arguments[0]);",
                                   mn.WAIT_TIMEOUT, self.n), "list %d not applied" % self.n)

    def state(self, b):
        return b.js(STATE, RECORD, tone.TONE)

    def load(self, b, url):
        b.navigate(url)
        b.wait_for("return document.readyState === 'complete';")
        return self.state(b)

    def settled(self, b, extra=""):
        """Waits past the add-on's judgment of a written theme (1.4 s after
        load) and returns the state."""
        b.js("return new Promise((resolve) => setTimeout(resolve, 2200));")
        return self.state(b)

    def preset(self, b, url, values, darken=True):
        """Opens `url`, sends the list (before the values: a list sent once
        they are there makes a late write on this open page) and sets its
        localStorage; the next load is the first one with these values."""
        self.load(b, url)
        self.feed(b, darken=darken)
        b.js("localStorage.clear(); for (const [k, v] of Object.entries(arguments[0]))"
             " localStorage.setItem(k, v);", values)

    # ---- the cases ----------------------------------------------------------

    def check(self, binary):
        srv = Server()
        self.addCleanup(srv.stop)
        root = tempfile.mkdtemp(prefix="bg-e2e-theme-")
        self.addCleanup(shutil.rmtree, root, True)
        ext = test_extension(root)
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(HOSTS)))
        self.n = 0
        with mn.Browser(content_css=dk.stylesheet(True), prefs=prefs, firefox=binary) as b:
            b.send("Addon:Install", {"path": ext, "temporary": True})
            tone.set_scheme(b, True)

            # 1. boots dark natively; a light theme restores live
            url = srv.url("ls.test")
            self.preset(b, url, {"theme": "light"})
            s = self.load(b, url)
            self.assertEqual(s["boot"], "dark", s)
            self.assertTrue(s["night"], s)
            self.assertEqual(s["record"]["keys"], {"local:theme": {"prior": "light", "wrote": "dark"}})
            self.assertEqual(s["mark"], "wrote")
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertFalse(s["marks"], s)
            self.assertEqual(s["tone"], "dark")
            self.assertNotIn("failed", s["record"])
            s = self.load(b, url)  # kept on the next load
            self.assertEqual((s["boot"], s["mark"]), ("dark", "kept"), s)
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('theme') === 'light'"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["record"]), ("light", None), s)
            tone.set_scheme(b, True)

            # 2. the user's own "dark": no record, kept under light
            url = srv.url("user.test")
            self.preset(b, url, {"theme": "dark"})
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["record"], s["mark"]), ("dark", None, None), s)
            tone.set_scheme(b, False)
            s = self.load(b, url)
            self.assertEqual((s["theme"], s["record"]), ("dark", None), s)
            tone.set_scheme(b, True)

            # 3. set back to light after the write: declined, never again
            url = srv.url("back.test")
            self.preset(b, url, {"theme": "light"})
            self.assertEqual(self.load(b, url)["boot"], "dark")
            b.js("localStorage.setItem('theme', 'light');")
            for _ in range(2):
                s = self.load(b, url)
                self.assertEqual(s["boot"], "light", s)
                self.assertEqual(s["record"]["declined"], ["local:theme"], s)
                self.assertEqual(s["record"]["keys"], {}, s)
            self.assertTrue(b.wait_for(dk.DARKENED), "declined page not darkened by Dark Reader")

            # 4. a site that forces light on every load: one write at most
            url = srv.url("force.test", "/force.html")
            self.preset(b, url, {"theme": "light"})
            boots = [self.load(b, url)["boot"] for _ in range(3)]
            self.assertEqual(boots, ["dark", "light", "light"])
            s = self.state(b)
            self.assertEqual(s["record"]["declined"], ["local:theme"], s)

            # 5. the key but no dark theme: failed, values back, Dark Reader
            url = srv.url("ignore.test", "/ignore.html")
            self.preset(b, url, {"theme": "light"})
            s = self.load(b, url)
            self.assertEqual(s["boot"], "dark", s)
            s = self.settled(b)
            self.assertEqual(s["theme"], "light", s)
            self.assertEqual(s["record"]["failed"], themes_doc()["rev"], s)
            self.assertEqual(s["record"]["keys"], {}, s)
            self.assertIsNone(s["mark"], s)
            self.assertTrue(b.wait_for(dk.DARKENED), "failed page not darkened by Dark Reader")
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["theme"]), ("light", "light"), s)

            # 6. values that are not a light theme, and an absent key
            url = srv.url("odd.test")
            for values in ({"theme": "classic"}, {"theme": '{"a":1}'}, {"themeColor": "light"}):
                self.preset(b, url, values)
                self.load(b, url)
                got = b.js("const o = {}; for (let i = 0; i < localStorage.length; i++)"
                           " { const k = localStorage.key(i); o[k] = localStorage.getItem(k); } return o;")
                self.assertEqual(got, values)
            url = srv.url("absent.test")
            self.preset(b, url, {})
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["theme"], s["record"]), (None, None, None), s)

            # 7. excluded: the value goes back live, no write after
            url = srv.url("excl.test")
            self.preset(b, url, {"theme": "light"})
            self.assertEqual(self.load(b, url)["boot"], "dark")
            self.feed(b, domains=["excl.test"])
            s = self.state(b)
            self.assertEqual((s["theme"], s["record"]), ("light", None), s)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["record"]), ("light", None), s)

            # 8. a cookie the server renders from: one reload, then dark
            url = srv.url("cookie.test", "/c.html")
            self.load(b, srv.url("absent.test"))  # sent from elsewhere: no late write
            self.feed(b, sites={"cookie.test": [COOKIE_RECIPE]})
            del srv.hits[:]
            s = self.load(b, url)
            self.assertEqual(len(srv.hits), 2, srv.hits)
            self.assertEqual(srv.hits[1], "mode=dark")
            self.assertTrue(s["night"], s)
            self.assertEqual(s["record"]["keys"]["cookie:mode"], {"prior": None, "wrote": "dark", "path": "/"})
            del srv.hits[:]
            s = self.load(b, url)
            self.assertEqual(len(srv.hits), 1, srv.hits)
            self.assertEqual(s["mark"], "kept")
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.cookie.includes('mode=');"), self.state(b))
            tone.set_scheme(b, True)
            self.feed(b)  # back to the bundled recipes

            # 9. a late write: Dark Reader now, native from the next load
            url = srv.url("late.test")
            self.preset(b, url, {"theme": "light"}, darken=False)
            self.load(b, url)
            self.feed(b)
            s = self.settled(b)
            self.assertEqual(s["theme"], "dark", s)
            self.assertEqual(s["record"]["keys"], {"local:theme": {"prior": "light", "wrote": "dark"}})
            self.assertNotIn("failed", s["record"])
            self.assertTrue(b.wait_for(dk.DARKENED), "late page not darkened by Dark Reader")
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["darkreader"]), ("dark", False), s)
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertNotIn("failed", s["record"])

            # 10. a composite cookie: swapped in place, created when absent
            sites = {"wiki.test": WIKI_RECIPES, "wiki2.test": WIKI_RECIPES}
            prefs_day = "vector-feature-limited-width-clientpref-0%2Cskin-theme-clientpref-day"
            url = srv.url("wiki.test", "/w.html")
            self.load(b, url)
            # the cookie first: sent on an open page with no cookie, the
            # list would create it at once (a late write)
            b.js("document.cookie = 'wikiprefs=' + arguments[0] + '; path=/';", prefs_day)
            self.feed(b, sites=sites)
            s = self.load(b, url)
            self.assertEqual(s["boot"], "vector-feature-limited-width-clientpref-0,skin-theme-clientpref-night", s)
            self.assertTrue(s["night"], s)
            self.assertEqual(s["record"]["keys"]["cookie:wikiprefs"],
                             {"swap": True, "prior": "skin-theme-clientpref-day",
                              "wrote": "skin-theme-clientpref-night", "path": "/"})
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertNotIn("failed", s["record"])
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return document.cookie.includes(arguments[0]);",
                                       mn.WAIT_TIMEOUT, "wikiprefs=" + prefs_day), self.state(b))
            tone.set_scheme(b, True)
            url = srv.url("wiki2.test", "/w.html")
            self.load(b, url)
            self.feed(b, sites=sites)
            s = self.load(b, url)
            self.assertEqual(s["boot"], "skin-theme-clientpref-night", s)
            self.assertTrue(s["night"], s)
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.cookie.includes('wikiprefs=');"), self.state(b))
            tone.set_scheme(b, True)
            self.feed(b)

            # 11. a localStorage recipe that creates the key
            url = srv.url("create.test")
            self.preset(b, url, {})
            self.feed(b, sites={"create.test": [CREATE_RECIPE]})
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["theme"]), ("dark", "dark"), s)
            self.assertEqual(s["record"]["keys"], {"local:theme": {"prior": None, "wrote": "dark"}})
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('theme') === null;"), self.state(b))
            tone.set_scheme(b, True)
            self.feed(b)

            # 12. a key with "/" read at the end of <body>: created, judged dark
            url = srv.url("slash.test", "/rts.html")
            self.preset(b, url, {})
            self.feed(b, sites={"slash.test": [SLASH_RECIPE]})
            s = self.load(b, url)
            self.assertEqual(s["boot"], "dark", s)
            self.assertEqual(b.js("return document.body.getAttribute('data-dark-mode');"), "dark")
            self.assertEqual(s["record"]["keys"], {"local:" + SLASH_KEY: {"prior": None, "wrote": "dark"}})
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertNotIn("failed", s["record"])
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem(arguments[0]) === null"
                                       " && localStorage.getItem(arguments[1]) === null;",
                                       mn.WAIT_TIMEOUT, SLASH_KEY, RECORD), self.state(b))
            tone.set_scheme(b, True)
            self.feed(b)

            # 13. a cookie named with a dot, rendered by the server: one
            # reload, then dark; removed under a light theme
            url = srv.url("shade.test", "/g.html")
            self.load(b, srv.url("absent.test"))
            self.feed(b, sites={"shade.test": [SHADE_RECIPE]})
            del srv.hits[:]
            s = self.load(b, url)
            self.assertEqual(srv.hits, ["", ".shade=dark"])
            self.assertTrue(s["night"], s)
            self.assertEqual(s["record"]["keys"]["cookie:.shade"], {"prior": None, "wrote": "dark", "path": "/"})
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.cookie.includes('.shade=')"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            tone.set_scheme(b, True)

            # 14. the same cookie already set HttpOnly by the server: unseen
            # by scripts, and Firefox refuses the write but shows it to the
            # page's own scripts: one reload, the page stays light, failed,
            # Dark Reader; never reloaded again
            self.load(b, srv.url("hidden.test", "/hide.html"))  # no recipe yet
            self.load(b, srv.url("absent.test"))
            self.feed(b, sites={"hidden.test": [SHADE_RECIPE]})
            url = srv.url("hidden.test", "/g.html")
            del srv.hits[:]
            s = self.load(b, url)
            self.assertEqual(srv.hits, [".shade=light", ".shade=light"])
            s = self.settled(b)
            self.assertFalse(s["night"], s)
            self.assertEqual((s["record"]["keys"], s["record"]["failed"]),
                             ({}, themes_doc({"hidden.test": [SHADE_RECIPE]})["rev"]), s)
            self.assertTrue(b.wait_for(dk.DARKENED), "refused cookie: page not darkened by Dark Reader")
            for _ in range(2):
                del srv.hits[:]
                s = self.load(b, url)
                self.assertEqual(srv.hits, [".shade=light"])
                self.assertFalse(s["night"], s)
            self.feed(b)

            # 15. DSFR (service-public.gouv.fr, www.info.gouv.fr,
            # impots.gouv.fr), the bundled recipes: a first visit created
            # dark, no Dark Reader
            dsfr = ("return [localStorage.getItem('scheme'),"
                    " document.documentElement.getAttribute('data-fr-theme')];")
            sites = {"dsfr.test": bundled("service-public.gouv.fr"),
                     "dsfr2.test": bundled("www.info.gouv.fr"),
                     "dsfr3.test": bundled("impots.gouv.fr")}
            self.load(b, srv.url("absent.test"))
            self.feed(b, sites=sites)
            for host in sites:
                url = srv.url(host, "/dsfr.html")
                s = self.load(b, url)
                self.assertEqual((s["boot"], b.js(dsfr)), ("dark", ["dark", "dark"]), (host, s))
                self.assertEqual(s["record"]["keys"], {"local:scheme": {"prior": None, "wrote": "dark"}})
                s = self.settled(b)
                self.assertFalse(s["darkreader"], s)
                self.assertNotIn("failed", s["record"])
            # removed under a light theme; the page then stores "light"
            # itself, which is written dark and put back
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('scheme') === null"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            s = self.load(b, url)
            self.assertEqual((s["boot"], b.js(dsfr), s["record"]), (None, ["light", "light"], None), s)
            tone.set_scheme(b, True)
            s = self.load(b, url)
            self.assertEqual((s["boot"], b.js(dsfr)), ("dark", ["dark", "dark"]), s)
            self.assertEqual(s["record"]["keys"], {"local:scheme": {"prior": "light", "wrote": "dark"}})
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('scheme') === 'light'"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            tone.set_scheme(b, True)
            # "system", dark under a dark system by the page itself: left alone
            self.load(b, srv.url("absent.test"))
            self.feed(b)  # no recipe while preset opens the page
            self.preset(b, url, {"scheme": "system"})
            self.feed(b, sites=sites)
            s = self.load(b, url)
            self.assertEqual((s["boot"], b.js(dsfr), s["record"]), ("system", ["system", "dark"], None), s)
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.feed(b)

            # 16. the Home Assistant demo, the bundled recipe: a JSON value,
            # created on a first visit, then the stored light JSON
            auto = '{"theme":"default"}'
            ha = "return localStorage.getItem('demo_theme');"
            url = srv.url("ha.test", "/ha.html")
            self.load(b, srv.url("absent.test"))
            self.feed(b, sites={"ha.test": bundled("demo.home-assistant.io")})
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"]), (auto, True), s)
            self.assertEqual(s["record"]["keys"], {"local:demo_theme": {"prior": None, "wrote": auto}})
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertNotIn("failed", s["record"])
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('demo_theme') === null"
                                       " && localStorage.getItem(arguments[0]) === null"
                                       " && !document.documentElement.classList.contains('night');",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            b.js("localStorage.setItem('demo_theme', arguments[0]);", HA_LIGHT)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"], s["record"]), (HA_LIGHT, False, None), s)
            tone.set_scheme(b, True)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"]), (auto, True), s)
            self.assertEqual(s["record"]["keys"], {"local:demo_theme": {"prior": HA_LIGHT, "wrote": auto}})
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('demo_theme') === arguments[1]"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD, HA_LIGHT), self.state(b))
            tone.set_scheme(b, True)
            self.feed(b)

            # 17. Proton's account pages, the bundled recipe: a numeric
            # value, created on a first visit, then the stored light "2"
            url = srv.url("proton.test", "/proton.html")
            sites = {"proton.test": bundled("account.proton.me")}
            self.load(b, srv.url("absent.test"))
            self.feed(b, sites=sites)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"]), ("1", True), s)
            self.assertEqual(s["record"]["keys"], {"local:theme": {"prior": None, "wrote": "1"}})
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.assertNotIn("failed", s["record"])
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('theme') === null"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            b.js("localStorage.setItem('theme', '2');")
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"], s["record"]), ("2", False, None), s)
            tone.set_scheme(b, True)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"]), ("1", True), s)
            self.assertEqual(s["record"]["keys"], {"local:theme": {"prior": "2", "wrote": "1"}})
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return localStorage.getItem('theme') === '2'"
                                       " && localStorage.getItem(arguments[0]) === null;",
                                       mn.WAIT_TIMEOUT, RECORD), self.state(b))
            tone.set_scheme(b, True)
            # "0" (Auto), dark under a dark system by the page itself: left alone
            self.load(b, srv.url("absent.test"))
            self.feed(b)  # no recipe while preset opens the page
            self.preset(b, url, {"theme": "0"})
            self.feed(b, sites=sites)
            s = self.load(b, url)
            self.assertEqual((s["boot"], s["night"], s["record"]), ("0", True, None), s)
            s = self.settled(b)
            self.assertFalse(s["darkreader"], s)
            self.feed(b)


if __name__ == "__main__":
    unittest.main()

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
    created, and a light theme puts the day theme back.
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
         "absent.test", "excl.test", "cookie.test", "late.test", "wiki.test", "wiki2.test")
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


class Server:
    """Pages of the cases; /c.html renders its theme from the "mode" cookie
    (counted per load)."""

    def __init__(self):
        self.hits = []
        hits = self.hits

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                cookie = self.headers.get("Cookie") or ""
                if path == "/c.html":
                    hits.append(cookie)
                    night = "mode=dark" in cookie.replace(" ", "").split(";")
                    body = ('<!doctype html><html class="%s"><head><meta charset="utf-8">'
                            % ("night" if night else "")) + STYLE + "</head><body>" + TEXT + "</body></html>"
                else:
                    body = {"/ls.html": LS_PAGE, "/force.html": FORCE_PAGE,
                            "/ignore.html": IGNORE_PAGE, "/w.html": WIKI_PAGE}.get(path)
                    if body is None:
                        self.send_error(404)
                        return
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
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


if __name__ == "__main__":
    unittest.main()

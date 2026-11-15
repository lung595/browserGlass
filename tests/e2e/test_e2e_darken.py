"""End-to-end: dark pages (darkPages). Under a dark theme the companion
add-on turns a light page dark with its Dark Reader engine
(extension/vendor/darkreader.js), and the large elements that paint the
page's background become glass. In a real headless Firefox (and LibreWolf
with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 10 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_darken.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers and stylesheets as test_e2e_tone.py; Dark Reader and
content.js run in the page with a stand-in `browser`. Checked:
  - a light page under a dark theme: darkened (light text), html and body
    see-through, the full-page wrapper marked as canvas and see-through, a
    small card dark but opaque, not marked; the fetch Dark Reader gets
    returns a stylesheet, and refuses another type or a missing file;
  - a light theme gives the page its own colours back (no Dark Reader
    style, tone light), the wrapper, its lowest layer, still glass; a dark
    theme darkens it again;
  - left alone: a page that declares a dark version, an excluded page, and
    any page with darkPages off, and a page that sets the darkening colours
    itself under a light theme;
  - a page with its own dark theme behind a class (a "dark" class on
    <html>, its text colour animated) gets it instead of Dark Reader, and
    gives it back under a light theme; a page without one is left with no
    such mark once darkened.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
CANVAS, OFF = bg.ATTR_CANVAS, bg.ATTR_OFF
EXT = os.path.join(tone.REPO, "extension")

TEXT = "<p>" + "Some readable dark text on a light page. " * 8 + "</p>"
WRAPPED_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#wrap {background:rgb(255,255,255); min-height:100vh}
#card {background:rgb(240,240,240); width:200px; height:100px}
</style></head><body><div id="wrap">""" + TEXT + """<div id="card">Card</div></div></body></html>"""

# A light page with its own dark theme, on a "dark" class of <html>; the
# text colour is animated, as theme switches often are.
NATIVE_PAGE = """<!doctype html><html class="app"><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20); transition: color 2s}
html.dark, html.dark body {background:rgb(17,17,17); color:rgb(230,230,230)}
</style></head><body>""" + TEXT + """</body></html>"""
CLASSES = "return document.documentElement.className;"

# Dark Reader as a module (its UMD wrapper fills `exports`), then content.js
# with it and a stand-in WebExtension API (the stored exclusion list). The
# fetch method content.js hands Dark Reader is kept as window.bgFetch.
RUN = ("const exp = {}; (new Function('exports', 'module', arguments[1]))(exp, {exports: exp});"
       "const setFetch = exp.setFetchMethod;"
       "exp.setFetchMethod = (f) => { window.bgFetch = f; setFetch(f); };"
       "const stub = {storage: {local: {get: () => Promise.resolve({excluded: arguments[2]})}},"
       "  runtime: {onMessage: {addListener() {}}}};"
       "(new Function('browser', 'DarkReader', arguments[0]))(stub, exp);")
DARKENED = "return !!document.querySelector('style.darkreader');"
FETCHED = ("return window.bgFetch(arguments[0]).then((r) => r.text(), () => 'refused');")

# A light page that sets the darkening colours itself.
SPOOF_PAGE = WRAPPED_PAGE.replace(
    "</style>", ":root {--browserglass-darken-bg: #000; --browserglass-darken-fg: #fff}</style>")
MARKED = "return document.getElementById(arguments[0]).hasAttribute(arguments[1]);"


def stylesheet(dark_pages):
    sites = bg.Sites({}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True, darkPages=dark_pages)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


def read(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class DarkenE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = read("content.js")
        cls.darkreader_js = read("vendor/darkreader.js")

    def test_darken(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_darken(binary)
                self.check_left_alone(binary)
                self.check_native(binary)

    def run_content(self, b, excluded=()):
        b.js(RUN, self.content_js, self.darkreader_js, list(excluded))

    def bg_of(self, b, element_id):
        return b.js("return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;",
                    element_id)

    def check_darken(self, binary):
        routes = {"/w.html": ("text/html; charset=utf-8", WRAPPED_PAGE.encode("utf-8")),
                  "/s.css": ("text/css; charset=utf-8", b"p {}"),
                  "/s.json": ("application/json", b"{}")}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            # Dark Reader's fetch hands over stylesheets only
            self.assertEqual(b.js(FETCHED, srv.url("/s.css", "light.test")), "p {}")
            self.assertEqual(b.js(FETCHED, srv.url("/s.json", "light.test")), "refused")
            self.assertEqual(b.js(FETCHED, srv.url("/none.css", "light.test")), "refused")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS), "wrapper not marked")
            # its own dark theme was tried first, and taken back
            self.assertEqual(b.js(CLASSES), "")
            self.assertIsNone(b.js("return document.documentElement.getAttribute('data-theme');"))
            self.assertEqual(b.js("return document.documentElement.getAttribute(arguments[0]);",
                                  tone.TONE), "dark")
            text, html, body = tone.colors(b)
            self.assertGreater(tone.luminance(tone.rgba(text)), 0.179, text)
            self.assertEqual((html, body), ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            self.assertEqual(self.bg_of(b, "wrap"), "rgba(0, 0, 0, 0)")
            card = tone.rgba(self.bg_of(b, "card"))
            self.assertEqual(card[3], 1.0)
            self.assertLess(tone.luminance(card), 0.05, card)
            self.assertFalse(b.js(MARKED, "card", CANVAS))
            self.assertGreaterEqual(tone.contrast(text, self.bg_of(b, "card")), 4.5)
            # a light theme: the page's own colours, the wrapper (its lowest
            # layer) still glass, the card white again
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && document.documentElement.getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "still darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))
            self.assertEqual(self.bg_of(b, "wrap"), "rgba(0, 0, 0, 0)")
            self.assertEqual(self.bg_of(b, "card"), "rgb(240, 240, 240)")
            # dark again
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened again")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))

    def check_native(self, binary):
        routes = {"/n.html": ("text/html; charset=utf-8", NATIVE_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/n.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "own dark theme not on")
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertFalse(b.js(DARKENED), "Dark Reader used over the page's own dark theme")
            self.assertIn("dark", b.js(CLASSES).split())
            self.assertIn("app", b.js(CLASSES).split())
            text = tone.colors(b)[0]
            self.assertGreater(tone.luminance(tone.rgba(text)), 0.179, text)
            # a light theme takes it back, the page's own class kept
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return document.documentElement.className === 'app'"
                                       " && document.documentElement.getAttribute('data-theme') === null;"),
                            "own dark theme not taken back")
            # dark again: tried again
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for("return document.documentElement.classList.contains('dark');"),
                            "own dark theme not tried again")
            self.assertFalse(b.js(DARKENED))

    def left_alone(self, b, why):
        # content.js decides once the list is there and the page loaded:
        # both are by the time LIVE is set
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, tone.LIVE), why)
        b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
        self.assertFalse(b.js(DARKENED), why)

    def check_left_alone(self, binary):
        routes = {"/w.html": ("text/html; charset=utf-8", WRAPPED_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", tone.DARK_PAGE.encode("utf-8")),
                  "/s.html": ("text/html; charset=utf-8", SPOOF_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/d.html", "dark.test"))
            self.run_content(b)
            self.left_alone(b, "a page with a dark version")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, ["light.test"])
            self.left_alone(b, "an excluded page")
            self.assertTrue(b.js("return document.documentElement.hasAttribute(arguments[0]);", OFF))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b)
            self.left_alone(b, "darkPages off")
            # the page's own darkening colours, under a light theme
            tone.set_scheme(b, False)
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b)
            self.left_alone(b, "colours set by the page, light theme")


if __name__ == "__main__":
    unittest.main()

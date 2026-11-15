"""End-to-end: dark pages (darkPages). Under a dark theme the companion
add-on turns a light page dark with its Dark Reader engine
(extension/vendor/darkreader.js), and the large elements that paint the
page's background become glass. In a real headless Firefox (and LibreWolf
with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 10 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_darken.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers and stylesheets as test_e2e_tone.py; Dark Reader and
content.js run in the page with a stand-in `browser`, whose storage holds
the list and the helper's darken flag (the darkPages setting, sent with
the list). Checked:
  - a light page under a dark theme: darkened (light text), html and body
    see-through, the full-page wrapper marked as canvas and see-through, a
    small card dark but opaque, not marked; the fetch Dark Reader gets
    returns a stylesheet, and refuses another type or a missing file;
    grey text stays grey (the text colour's tint is muted); a frame keeps
    its colour scheme (not Dark Reader's dark one);
  - a light theme gives the page its own colours back (no Dark Reader
    style, tone light), the wrapper, its lowest layer, still glass; a dark
    theme darkens it again; the helper turning darken off live (a message)
    gives the page back at once;
  - left alone: a page that declares a dark version, an excluded page, and
    any page with darkPages off, a page under the style file's colours
    while the helper says darken false, and a page that sets the darkening
    colours itself, under a light theme and under a dark one (darken
    false: the colours alone never darken);
  - a page with its own dark theme behind a class (a "dark" class on
    <html>, its text colour animated) gets it instead of Dark Reader, and
    gives it back under a light theme; a page without one is left with no
    such mark once darkened;
  - a site style of data/sites/ on a darkened page: Stack Overflow's
    filled buttons and search field (the real Stacks var() fallback chains,
    which Dark Reader maps to the page's white) keep a fill of their own
    under a dark theme, and the site's own colours under a light one.
"""

import json
import os
import shutil
import sys
import tempfile
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
.meta {color:rgb(130,130,130)}
</style></head><body><div id="wrap">""" + TEXT + """<p id="grey" class="meta">120 points by someone</p>
<div id="card">Card</div><iframe id="frame" src="about:blank" width="20" height="20"></iframe></div></body></html>"""

# A light page with its own dark theme, on a "dark" class of <html>; the
# text colour is animated, as theme switches often are.
NATIVE_PAGE = """<!doctype html><html class="app"><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20); transition: color 2s}
html.dark, html.dark body {background:rgb(17,17,17); color:rgb(230,230,230)}
</style></head><body>""" + TEXT + """</body></html>"""
CLASSES = "return document.documentElement.className;"

# Dark Reader as a module (its UMD wrapper fills `exports`), then content.js
# with it and a stand-in WebExtension API (the stored exclusion list and
# darken flag, arguments[3]: left out, as test_e2e_layers.py does, none is
# stored, which is false). The fetch method content.js hands Dark Reader is
# kept as window.bgFetch, its message listener as window.bgMessage.
RUN = ("const exp = {}; (new Function('exports', 'module', arguments[1]))(exp, {exports: exp});"
       "const setFetch = exp.setFetchMethod;"
       "exp.setFetchMethod = (f) => { window.bgFetch = f; setFetch(f); };"
       "const stored = {excluded: arguments[2]};"
       "if (arguments[3] !== undefined) stored.darken = arguments[3];"
       "const stub = {storage: {local: {get: () => Promise.resolve(stored)}},"
       "  runtime: {onMessage: {addListener(f) { window.bgMessage = f; }}}};"
       "(new Function('browser', 'DarkReader', arguments[0]))(stub, exp);")
# The helper's list as background.js forwards it to the page.
MESSAGE = "window.bgMessage({type: 'excluded', domains: arguments[0], darken: arguments[1]});"
DARKENED = "return !!document.querySelector('style.darkreader');"
FETCHED = ("return window.bgFetch(arguments[0]).then((r) => r.text(), () => 'refused');")

# A light page that sets the darkening colours itself.
SPOOF_PAGE = WRAPPED_PAGE.replace(
    "</style>", ":root {--browserglass-darken-bg: #000; --browserglass-darken-fg: #fff}</style>")
MARKED = "return document.getElementById(arguments[0]).hasAttribute(arguments[1]);"


# A Stacks page as Stack Overflow serves it signed out (no dark theme):
# filled buttons and a search field painted from the Stacks variables,
# with their chains of var() fallbacks.
STACKS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
:root {--white: hsl(0,0%,100%); --blue-400: hsl(210,77%,46%); --black-300: hsl(210,8%,75%);
  --theme-secondary-400: var(--blue-400)}
.s-btn {--_bu-filled-bg: var(--theme-button-primary-background-color, var(--theme-secondary-400));
  display:inline-block; padding:8px; color:#fff; border:1px solid transparent}
.s-btn.s-btn__filled {background-color:var(--_bu-filled-bg)}
.s-input {--_in-bg: var(--white); --_in-bc: var(--black-300);
  background-color:var(--_in-bg); border:1px solid var(--_in-bc); width:300px}
#wrap {background:rgb(255,255,255); min-height:100vh}
</style></head><body class="unified-theme"><div id="wrap">""" + TEXT + """
<a id="ask" class="s-btn s-btn__filled" href="#">Ask Question</a>
<input id="search" class="s-input" placeholder="Search"></div></body></html>"""
STACKS = "stackoverflow.com.css"
STACKS_HOST = "stackoverflow.test"


def stacks_sites():
    """The bundled Stack Overflow style and its site fix, under a .test
    host."""
    data = os.path.join(tone.REPO, "data")
    with open(os.path.join(data, "styles.json"), encoding="utf-8") as f:
        style = json.load(f)["website"][STACKS]
    with open(os.path.join(data, bg.SITES_OWN_DIR, STACKS), encoding="utf-8") as f:
        fix = f.read()
    tmp = tempfile.mkdtemp()
    try:
        name = STACKS_HOST + ".css"
        with open(os.path.join(tmp, "styles.json"), "w", encoding="utf-8") as f:
            json.dump({"website": {name: style}}, f)
        os.mkdir(os.path.join(tmp, bg.SITES_OWN_DIR))
        with open(os.path.join(tmp, bg.SITES_OWN_DIR, name), "w", encoding="utf-8") as f:
            f.write(fix)
        return bg.sites_load(tmp)
    finally:
        shutil.rmtree(tmp)


def stylesheet(dark_pages, sites=None):
    sites = sites or bg.Sites({}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True, darkPages=dark_pages)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


SCHEME = "return getComputedStyle(document.getElementById(arguments[0])).colorScheme;"


def saturation(rgba):
    """The HSL saturation of an (r, g, b, a) colour."""
    hi, lo = max(rgba[:3]) / 255, min(rgba[:3]) / 255
    light = (hi + lo) / 2
    return 0.0 if hi == lo else (hi - lo) / (1 - abs(2 * light - 1))


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
                self.check_stacks(binary)

    def run_content(self, b, excluded=(), darken=True):
        """content.js with the stored list `excluded` and darken flag
        `darken` (None: none stored)."""
        if darken is None:
            b.js(RUN, self.content_js, self.darkreader_js, list(excluded))
        else:
            b.js(RUN, self.content_js, self.darkreader_js, list(excluded), darken)

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
            # grey text stays grey: Dark Reader gives it the hue and
            # saturation of the text colour, whose near-white (#f7f9ff) has
            # a saturation of 100%
            grey = tone.rgba(b.js("return getComputedStyle(document.getElementById('grey')).color;"))
            self.assertLessEqual(saturation(grey), 0.15, grey)
            # a frame keeps its colour scheme (Dark Reader makes every one
            # dark: a light page from another site gets an opaque backdrop),
            # one added later too
            self.assertEqual(b.js(SCHEME, "frame"), "normal")
            b.js("const f = document.createElement('iframe'); f.id = 'late'; document.body.append(f);")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('late')).colorScheme"
                                       " === 'normal';"), "a frame added later turned dark")
            # a light theme: the page's own colours, the wrapper (its lowest
            # layer) still glass, the card white again
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && document.documentElement.getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "still darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))
            self.assertEqual(self.bg_of(b, "wrap"), "rgba(0, 0, 0, 0)")
            self.assertEqual(self.bg_of(b, "card"), "rgb(240, 240, 240)")
            # the frames' own style given back
            self.assertIsNone(b.js("return document.getElementById('frame').style.colorScheme || null;"))
            # dark again
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened again")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))
            # the helper turns darken off live: the page is given back at
            # once, the style file's colours still there; and on again
            b.js(MESSAGE, [], False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && document.documentElement.getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "still darkened with darken off")
            b.js(MESSAGE, [], True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened with darken back on")

    def check_stacks(self, binary):
        # Dark Reader maps the filled buttons and the search field to the
        # page's white, which the bundled style makes transparent; the site
        # fix gives them a fill back
        routes = {"/so.html": ("text/html; charset=utf-8", STACKS_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS) + [STACKS_HOST]))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, stacks_sites()), prefs=prefs, firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/so.html", STACKS_HOST))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE))
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertEqual(self.bg_of(b, "ask"), "rgb(23, 102, 181)")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('ask')).color;"),
                             "rgb(255, 255, 255)")
            self.assertEqual(self.bg_of(b, "search"), "rgba(255, 255, 255, 0.08)")
            # light: the site's own colours
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader');"))
            self.assertEqual(self.bg_of(b, "ask"), "rgb(27, 117, 208)", "the site's own blue")

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
            # the style file's colours, but the helper says no (darkPages
            # turned off, the browser not restarted), or says nothing
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "darken false")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=None)
            self.left_alone(b, "no darken stored")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken="true")
            self.left_alone(b, "darken not a boolean")
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "darkPages off")
            # the page's own darkening colours with darkPages off (darken
            # false): under a dark theme, then a light one
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "colours set by the page, darken false")
            tone.set_scheme(b, False)
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b)
            self.left_alone(b, "colours set by the page, light theme")


if __name__ == "__main__":
    unittest.main()

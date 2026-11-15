"""End-to-end: light pages under a dark theme (and dark pages under a light
one), in a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 10 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_tone.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Throwaway browsers only (fake HOME, generated profile, 127.0.0.1 page
server, black-hole proxy); no browserglass.py subprocess: the stylesheets
come from its render functions.

One made-up site style, light.test.css, mapped to dark.test, makes html and
body transparent (as most site styles do, with !important). Two pages:
light.test (dark text on its own light background, no dark version
declared) and dark.test (light text on a dark background). Checked:
  - under a dark theme, without the add-on's tone attribute, the style
    leaves the light page alone (it paints its own background: readable);
  - with data-browserglass-tone="light" (set by Marionette, liveControl
    on), the light page gets the light tint (the light DMS surface at
    SITES_TONE_OPACITY) and the style; without liveControl the attribute
    changes nothing;
  - the dark page is glass (transparent) under a dark theme, and gets the
    dark tint under a light theme with data-browserglass-tone="dark";
  - in each case the text has a contrast of at least 4.5 against its
    effective background (the page's, or the tint over black and over
    white, the worst of the two);
  - the add-on's content.js (run in the page with a stand-in `browser`)
    measures the tone of both pages, again when the page switches its theme
    (a class on <html>) and when the colour scheme changes; text coloured
    in oklch() or color(display-p3) too; a page whose body keeps the default
    black and whose text shown is white through classes (YouTube) is dark;
  - a site style that makes the text white (white.test.css) on a light
    page: under a dark theme the tone is that of the text shown, "dark"
    (the site style applies once the tone is set), so the page is glass
    and the white text readable on the dark tint;
  - the generic style (example.com.css) on plain.test, a light page with a
    shadow root: under a dark theme, without the tone, it leaves the shadow
    content alone (as in v1.0), with or without liveControl; under a light
    theme it applies there.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "py"))

import marionette as mn  # noqa: E402
from fakehome import load_script  # noqa: E402

bg = load_script()

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None
LIBREWOLF = mn.find_librewolf() if E2E else None

TONE, LIVE = bg.ATTR_TONE, bg.ATTR_LIVE
# The colour scheme of the pages: 0 dark, 1 light (live)
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
HOSTS = ("light.test", "dark.test", "white.test", "plain.test")
LIGHT_BG, LIGHT_TEXT = "rgb(250, 250, 250)", "rgb(20, 20, 20)"
DARK_BG, DARK_TEXT = "rgb(18, 18, 18)", "rgb(235, 235, 235)"

# A light page with dark text (no dark version declared); with class
# "night" on <html> (the page's own theme switch) or under a dark colour
# scheme when it has class "auto", light text on a dark background.
LIGHT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(250,250,250)} body{color:rgb(20,20,20);margin:0}
html.night{background:rgb(18,18,18)} html.night body{color:rgb(235,235,235)}
@media (prefers-color-scheme: dark) {
  html.auto{background:rgb(18,18,18)} html.auto body{color:rgb(235,235,235)}
}
</style></head><body><p>Readable text</p></body></html>"""
DARK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><style>
html{background:rgb(18,18,18)} body{color:rgb(235,235,235);margin:0}
</style></head><body><p>Readable text</p></body></html>"""
SITE_CSS = "html, body { background: transparent !important; }\n"
WHITE_CSS = SITE_CSS + "body { color: #fff !important; }\n"
GENERIC_CSS = "section { background: transparent !important; }\n"
WHITE = "rgb(255, 255, 255)"
SHADOW_BG = "rgb(238, 238, 238)"
# Text in oklch() (dark), or with class "p3" in color(display-p3) (light,
# on a dark background).
OKLCH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(250,250,250)} body{color:oklch(0.21 0.034 264.665);margin:0}
html.p3{background:rgb(18,18,18)} html.p3 body{color:color(display-p3 0.92 0.92 0.92)}
</style></head><body><p>Readable text</p></body></html>"""
# YouTube's dark theme: the body keeps the default (black) text colour, the
# text shown is white through classes; a hidden block of dark text must not
# count.
CLASSES_PAGE = """<!doctype html><html dark><head><meta charset="utf-8"><style>
html{background:rgb(15,15,15)} body{margin:0} .t{color:rgb(241,241,241)}
</style></head><body><div class="t"><h1>Video title</h1><p>Channel name</p></div>
<div style="display:none">""" + "Hidden dark text " * 50 + """</div></body></html>"""
# A light page with a web component: a light section in a shadow root.
SHADOW_PAGE = LIGHT_PAGE.replace("<p>Readable text</p>", """<p>Readable text</p><div id="host"></div>
<script>document.getElementById("host").attachShadow({mode: "open"}).innerHTML =
'<section style="background:rgb(238,238,238)">In a shadow tree</section>';</script>""")
SHADOW_BG_JS = ("return getComputedStyle(document.getElementById('host').shadowRoot"
                ".querySelector('section')).backgroundColor;")

# Run content.js in the page: a stand-in for the WebExtension API (an empty
# stored exclusion list, no messages).
RUN_CONTENT = ("const stub = {storage: {local: {get: () => Promise.resolve({excluded: []})}},"
               "  runtime: {onMessage: {addListener() {}}}};"
               "(new Function('browser', arguments[0]))(stub);")


def browsers():
    """[(name, binary)] of the browsers to run."""
    out = [("firefox", FIREFOX)]
    if LIBREWOLF:
        out.append(("librewolf", LIBREWOLF))
    return out


def stylesheet(live):
    sites = bg.Sites({"light.test.css": {"glass": SITE_CSS}, "white.test.css": {"glass": WHITE_CSS},
                      bg.SITES_GENERIC_KEY: {"glass": GENERIC_CSS}},
                     {"light.test.css": ["dark.test"]})
    values = bg.settings_from_json("{}")
    values.update(liveControl=live)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


def browser_prefs():
    prefs = mn.test_host_prefs(list(HOSTS))
    # LibreWolf's defaults: no HTTPS upgrade of the test server, real colour scheme
    prefs.update({"dom.security.https_only_mode": False,
                  "privacy.resistFingerprinting": False,
                  PREF_SCHEME: 0})
    return prefs


def set_scheme(b, dark):
    b.chrome_js("Services.prefs.setIntPref(arguments[0], arguments[1]);", PREF_SCHEME, 0 if dark else 1)
    if not b.wait_for("return matchMedia('(prefers-color-scheme: dark)').matches === arguments[0];",
                      mn.WAIT_TIMEOUT, dark):
        raise AssertionError("the colour scheme did not switch to %s" % ("dark" if dark else "light"))


def set_tone(b, tone):
    b.js("const root = document.documentElement;"
         "if (arguments[0] === null) { root.removeAttribute(arguments[1]); root.removeAttribute(arguments[2]); }"
         "else { root.setAttribute(arguments[1], arguments[0]); root.setAttribute(arguments[2], ''); }",
         tone, TONE, LIVE)


def colors(b):
    """(text colour of the body, background of html, background of body)."""
    return (b.css("body", "color")["color"], b.css("html", "background-color")["background-color"],
            b.css("body", "background-color")["background-color"])


def rgba(text):
    """(r, g, b, a) of a computed rgb()/rgba() value."""
    inside = text[text.index("(") + 1:text.index(")")]
    parts = [float(p) for p in inside.split(",")]
    return tuple(parts) if len(parts) == 4 else tuple(parts) + (1.0,)


def luminance(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b_ = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b_)


def contrast(text, background):
    """The worst contrast of `text` on `background` (computed values),
    composited over black and over white (what is behind the glass)."""
    fg = rgba(text)
    bgc = rgba(background)
    out = []
    for under in (0.0, 255.0):
        eff = [bgc[3] * c + (1 - bgc[3]) * under for c in bgc[:3]]
        hi, lo = sorted((luminance(fg), luminance(eff)), reverse=True)
        out.append((hi + 0.05) / (lo + 0.05))
    return min(out)


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ToneE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.gated = stylesheet(True)
        cls.original = stylesheet(False)
        assert TONE in cls.gated and TONE not in cls.original
        with open(os.path.join(REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()
        a = bg.format_number(bg.SITES_TONE_OPACITY)
        cls.tint = {mode: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, mode) + (a,))
                    for mode in bg.MODES}

    def test_tone(self):
        for name, binary in browsers():
            with self.subTest(browser=name):
                self.check_styles(binary)
                self.check_content_js(binary)
                self.check_shadow(binary)

    def check_shadow(self, binary):
        routes = {"/s.html": ("text/html; charset=utf-8", SHADOW_PAGE.encode("utf-8"))}
        for css in (self.gated, self.original):
            with mn.TestServer(routes) as srv, \
                    mn.Browser(content_css=css, prefs=browser_prefs(), firefox=binary) as b:
                b.navigate(srv.url("/s.html", "plain.test"))
                set_scheme(b, True)
                self.assertEqual(b.js(SHADOW_BG_JS), SHADOW_BG)
                set_scheme(b, False)
                self.assertEqual(b.js(SHADOW_BG_JS), "rgba(0, 0, 0, 0)")

    def readable(self, text, background):
        self.assertGreaterEqual(contrast(text, background), 4.5, (text, background))

    def check_styles(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.gated, prefs=browser_prefs(), firefox=binary) as b:
            b.navigate(srv.url("/p.html", "light.test"))
            set_scheme(b, True)
            # no tone (no add-on yet): the light page keeps its own background
            text, html, body = colors(b)
            self.assertEqual((text, html), (LIGHT_TEXT, LIGHT_BG))
            self.readable(text, html)
            # tone measured light: the light tint, the site style applies
            set_tone(b, "light")
            text, html, body = colors(b)
            self.assertEqual(html, self.tint["light"])
            self.assertEqual(body, "rgba(0, 0, 0, 0)")
            self.readable(text, html)
            # a page declaring its dark version never gets the light tint,
            # even measured light (a single-page app measured too early)
            b.js("document.documentElement.setAttribute('dark', '');")
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            b.js("document.documentElement.removeAttribute('dark');")
            self.assertEqual(colors(b)[1], self.tint["light"])
            # under a light theme the light page is glass, untinted
            set_scheme(b, False)
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            # the dark page: glass under a dark theme, the dark tint under a
            # light one once measured dark
            b.navigate(srv.url("/d.html", "dark.test"))
            set_scheme(b, True)
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            set_tone(b, "dark")
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            set_scheme(b, False)
            text, html, body = colors(b)
            self.assertEqual((text, html), (DARK_TEXT, self.tint["dark"]))
            self.readable(text, html)
            set_tone(b, None)
            text, html, body = colors(b)
            self.assertEqual(html, "rgba(0, 0, 0, 0)")
        # without liveControl the attribute changes nothing
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.original, prefs=browser_prefs(), firefox=binary) as b:
            b.navigate(srv.url("/p.html", "light.test"))
            set_scheme(b, True)
            set_tone(b, "light")
            self.assertEqual(colors(b)[:2], (LIGHT_TEXT, LIGHT_BG))

    def tone_is(self, b, tone):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, TONE, tone):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute("
                                                "arguments[0]);", TONE), tone))

    def check_content_js(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8")),
                  "/o.html": ("text/html; charset=utf-8", OKLCH_PAGE.encode("utf-8")),
                  "/c.html": ("text/html; charset=utf-8", CLASSES_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.gated, prefs=browser_prefs(), firefox=binary) as b:
            set_scheme(b, True)
            b.navigate(srv.url("/p.html", "light.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            self.assertTrue(b.js("return document.documentElement.hasAttribute(arguments[0]);", LIVE))
            self.assertEqual(colors(b)[1], self.tint["light"])
            # the page switches its own theme: a class on <html>
            b.js("document.documentElement.classList.add('night');")
            self.tone_is(b, "dark")
            text, html, body = colors(b)
            self.assertEqual((text, html), (DARK_TEXT, "rgba(0, 0, 0, 0)"))
            # a page following the colour scheme
            b.js("document.documentElement.className = 'auto';")
            self.tone_is(b, "dark")
            set_scheme(b, False)
            self.tone_is(b, "light")
            set_scheme(b, True)
            self.tone_is(b, "dark")
            b.navigate(srv.url("/d.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            # colours in other colour spaces
            b.navigate(srv.url("/o.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            b.js("document.documentElement.classList.add('p3');")
            self.tone_is(b, "dark")
            # the body's colour unset, the text shown white through classes
            b.navigate(srv.url("/c.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            # a site style making the text white: the tone of the text shown
            b.navigate(srv.url("/p.html", "white.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            text, html, body = colors(b)
            self.assertEqual((text, html), (WHITE, "rgba(0, 0, 0, 0)"))
            self.readable(text, "rgb(%d, %d, %d)" % bg.surface_rgb(None, "dark"))


if __name__ == "__main__":
    unittest.main()

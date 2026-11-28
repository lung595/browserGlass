"""End-to-end: a light-only page whose white text on photos, black cards
and brand sections outweighs its dark text, under the light theme. In a
real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_lightbody.py' -v

Two pages, each a white body with dark text (no dark version declared):
  - /shop.html on plain.test (the generic style, clearing sections and
    headers as the bundled one does): a hero of white lines over a photo,
    a white headline in a layer laid over an <img> (#hero, frame.work's
    hero: it keeps its white, not inked dark on the light glass) and black
    sections of white text, more text than the page's own;
  - /brand.html on brand.test, whose dedicated site style clears the
    body, the header and the sections whatever the marks (as the bundled
    rust-lang style does): coloured sections of white text.
Checked: under the light theme both are light (no dark tint on <html>,
the header's dark links and the dark headline not inked white); under a
dark one (no Dark Reader here) the tone is the text's, as before: dark.

And a page with a light version whose own toggle sets html.dark (from the
start, /toggle.html?dark, or a little after it loads, /toggle.html?late):
under the light theme the class is taken off and the page is light; under
a dark one the class is back and the page dark. A page dark by its own
style with html.dark and no light version (/darkonly.html) keeps the class
and stays dark under the light theme.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
HOSTS = ("plain.test", "brand.test")
CLEAR_CSS = ("%s { background-color: transparent !important; background: none !important;"
             " border: none !important; box-shadow: none !important; }\n")
GENERIC_CSS = CLEAR_CSS % "html, body, header, nav, section, main"
BRAND_CSS = CLEAR_CSS % "html, body, nav, header, section, h1, h2, h3"
WHITE_LINES = "<p>" + "White text drawn for its own dark backing. " * 6 + "</p>"
PHOTO = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='20'%3E"
         "%3Crect width='40' height='20' fill='%23604030'/%3E%3C/svg%3E")
HEAD = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;background:rgb(255,255,255);color:rgb(0,0,0)}
header{position:sticky;top:0;background:rgb(255,255,255)} header a{color:rgb(42,52,57);margin:8px}
h1{color:rgb(0,0,0)} .white{color:rgb(255,255,255);padding:16px}
"""
SHOP_PAGE = HEAD + """
.hero{background:url("%s") center/cover;height:320px} .black{background:rgb(0,0,0)}
.stage{position:relative} .stage img{display:block;width:100%%;height:320px}
.over{position:absolute;inset:0;z-index:2}
</style></head><body><header><a id="logo" href="/">shop</a><a href="#">Laptops</a></header>
<main><h1 id="title">A light shop</h1><p>Some dark text on the white page.</p>
<section class="hero white">%s</section>
<div class="stage"><img src="%s" alt=""><div class="over white"><h2 id="hero">White headline in a layer over a photo</h2>
</div></div>""" % (PHOTO, WHITE_LINES * 2, PHOTO) + (
    '<section class="black white">' + WHITE_LINES * 2 + "</section>") * 4 + "</main></body></html>"
BRAND_PAGE = HEAD + """
.green{background:rgb(11,114,97)} .purple{background:rgb(46,36,89)} .red{background:rgb(167,33,69)}
</style></head><body><header><a id="logo" href="/">brand</a><a href="#">Learn</a><a href="#">Tools</a></header>
<h1 id="title">Rust-like</h1><p>A language empowering everyone.</p>""" + "".join(
    '<section class="%s white"><h2>Why?</h2>%s</section>' % (c, WHITE_LINES * 3)
    for c in ("green", "purple", "red")) + "</body></html>"
TOGGLE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40)}
html.dark{background:rgb(13,17,23)} html.dark body{color:rgb(230,237,243)}
</style></head><body>""" + "<p>Main text of the page, in the tone of its theme.</p>" * 8 + """
<script>const q = location.search;
if (q === "?dark") document.documentElement.classList.add("dark");
if (q === "?late") setTimeout(() => document.documentElement.classList.add("dark"), 500);</script></body></html>"""
DARK_ONLY_PAGE = """<!doctype html><html class="dark"><head><meta charset="utf-8"><style>
html{background:rgb(13,17,23)} body{margin:0;color:rgb(230,237,243)}
</style></head><body>""" + "<p>Main text of a page dark by its own style.</p>" * 8 + "</body></html>"
HAS_DARK = "return document.documentElement.classList.contains('dark');"
INK_OF = "return getComputedStyle(document.getElementById(arguments[0])).color;"


def stylesheet():
    sites = bg.Sites({"brand.test.css": {"transparency": BRAND_CSS},
                      bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LightBodyE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_light_body(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def tone_is(self, b, want):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute(arguments[0]);",
                                                tone.TONE), want))

    def check(self, binary):
        routes = {"/shop.html": ("text/html; charset=utf-8", SHOP_PAGE.encode("utf-8")),
                  "/brand.html": ("text/html; charset=utf-8", BRAND_PAGE.encode("utf-8")),
                  "/toggle.html": ("text/html; charset=utf-8", TOGGLE_PAGE.encode("utf-8")),
                  "/darkonly.html": ("text/html; charset=utf-8", DARK_ONLY_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS + HOSTS)))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            for path, host in (("/shop.html", "plain.test"), ("/brand.html", "brand.test")):
                with self.subTest(page=path):
                    tone.set_scheme(b, False)
                    b.navigate(srv.url(path, host))
                    b.js(tone.RUN_CONTENT, self.content_js)
                    self.tone_is(b, "light")
                    self.assertEqual(tone.colors(b)[1], "rgba(0, 0, 0, 0)")
                    for name in ("title", "logo"):
                        self.assertLess(tone.luminance(tone.rgba(b.js(INK_OF, name))), 0.05, name)
                    if path == "/shop.html":
                        # a layer over a photo: the white drawn for the photo stays
                        self.assertGreater(tone.luminance(tone.rgba(b.js(INK_OF, "hero"))), 0.9)
                    # the theme switched live: the dark one keeps the text's
                    # tone, the light one comes back light
                    tone.set_scheme(b, True)
                    self.tone_is(b, "dark")
                    tone.set_scheme(b, False)
                    self.tone_is(b, "light")
            for query in ("?dark", "?late"):
                with self.subTest(page="/toggle.html" + query):
                    tone.set_scheme(b, False)
                    b.navigate(srv.url("/toggle.html" + query, "plain.test"))
                    b.js(tone.RUN_CONTENT, self.content_js)
                    if query == "?late":
                        self.assertTrue(b.wait_for("return window.performance.now() > 900;"))
                    self.tone_is(b, "light")
                    self.assertFalse(b.js(HAS_DARK))
                    tone.set_scheme(b, True)
                    self.tone_is(b, "dark")
                    self.assertTrue(b.js(HAS_DARK))
                    tone.set_scheme(b, False)
                    self.tone_is(b, "light")
                    self.assertFalse(b.js(HAS_DARK))
            with self.subTest(page="/darkonly.html"):
                tone.set_scheme(b, False)
                b.navigate(srv.url("/darkonly.html", "plain.test"))
                b.js(tone.RUN_CONTENT, self.content_js)
                self.tone_is(b, "dark")
                self.assertTrue(b.js(HAS_DARK))


if __name__ == "__main__":
    unittest.main()

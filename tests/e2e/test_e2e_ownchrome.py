"""End-to-end: the site's own sections kept for their text (KEPT,
data-browserglass-own), in a bar and as a wide band on the tone's side.
In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_ownchrome.py' -v

Under the real generic style (it clears sections, headers and navs):
  - /light.html (light.test), a light page: a sticky see-through header
    holding a dark nav of white links (Le Monde's compact header), then a
    wide near-white hero (rgb(248, 248, 248)) of pale grey text
    (Aftership's). Under the light theme the header is a bar, its light
    veil its one surface: the dark nav is not kept, its links are inked
    dark; the near-white hero is not kept either (no solid light band over
    the glass), its pale text is inked dark. An open mega menu laid over
    the page (MDN's): veiled, its navy title row of light links
    see-through on the light veil, the links inked.
  - /dark.html (dark.test), the same with the colours swapped, under a
    dark theme, unchanged: the light nav filling the dark-veiled header
    is see-through too, its dark links inked light; the navy title row of
    the dark mega menu keeps its colour.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
BAR, INK, OWN = bg.ATTR_BAR, bg.ATTR_INK, bg.ATTR_OWN
LONG = "<p>" + "Main text of the page, in its own tone. " * 8 + "</p>"


def page(text, nav, link, hero, pale, menu):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:%s}
#head {position:sticky; top:0; z-index:5}
#nav {height:48px; background:%s} #nav a {color:%s; margin:12px}
#hero {height:900px; background:%s; color:%s}
#long {height:300vh}
#mega {position:absolute; top:120px; left:20%%; width:60%%; z-index:100; background:%s}
#megatitle {margin:0; height:46px; background:rgb(7, 36, 70)} #megalink {color:rgb(164, 206, 254)}
</style></head><body><header id="head"><nav id="nav"><a id="link" href="#">News</a><a href="#">Sport</a></nav></header>
<main><section id="hero"><h1 id="pale">A pale headline over the hero</h1>%s</section>
<div id="long">%s</div></main>
<div id="mega" role="menu"><p id="megatitle"><a id="megalink" href="#">CSS: Styling language</a></p>
<p>Properties</p><p>Selectors</p><p>At-rules</p><p>Values</p></div></body></html>""" % (
        text, nav, link, hero, pale, menu, LONG, LONG * 6)


LIGHT_PAGE = page("rgb(20, 20, 20)", "rgb(30, 30, 40)", "rgb(255, 255, 255)",
                  "rgb(248, 248, 248)", "rgb(160, 160, 160)", "rgb(255, 255, 255)")
DARK_PAGE = page("rgb(235, 235, 235)", "rgb(240, 240, 240)", "rgb(20, 20, 20)",
                 "rgb(16, 16, 16)", "rgb(235, 235, 235)", "rgb(24, 24, 28)")
TONE_IS = "return document.documentElement.getAttribute(arguments[0]) === arguments[1];"
HAS = "return document.getElementById(arguments[0]).hasAttribute(arguments[1]);"
LACKS = "return !document.getElementById(arguments[0]).hasAttribute(arguments[1]);"
BG_OF = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
CLEAR = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class OwnChromeE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_own_chrome(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def check(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/light.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/dark.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/light.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "the light page not light")
            b.js("window.scrollTo(0, 50);")
            self.assertTrue(b.wait_for(HAS, mn.WAIT_TIMEOUT, "head", BAR), "the sticky header not a bar")
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "link", INK, "dark"),
                            "the dark nav's white links not inked on the light veil")
            self.assertFalse(b.js(HAS, "nav", OWN), "the dark nav kept in the light veil")
            self.assertTrue(b.wait_for(CLEAR, mn.WAIT_TIMEOUT, "nav"), "the dark nav left a solid slab")
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "pale", INK, "dark"),
                            "the hero's pale headline not inked on the light glass")
            self.assertFalse(b.js(HAS, "hero", OWN), "the near-white hero kept as a solid band")
            self.assertTrue(b.wait_for(CLEAR, mn.WAIT_TIMEOUT, "hero"), "the near-white hero left opaque")
            # the mega menu: veiled, its navy title row see-through on the
            # veil, its light link inked for it
            b.js("window.scrollTo(0, 0);")
            self.assertTrue(b.wait_for(HAS, mn.WAIT_TIMEOUT, "mega", BAR), "the mega menu not veiled")
            self.assertTrue(b.wait_for(CLEAR, mn.WAIT_TIMEOUT, "megatitle"), "the menu's navy row left a solid strip")
            self.assertTrue(b.wait_for(HAS, mn.WAIT_TIMEOUT, "megalink", INK), "the menu's light link not inked")

            # the dark theme, as before: the light nav filling the dark-veiled
            # header is no slab of its own either, its dark links inked light
            tone.set_scheme(b, True)
            b.navigate(srv.url("/dark.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "the dark page not dark")
            b.js("window.scrollTo(0, 50);")
            self.assertTrue(b.wait_for(HAS, mn.WAIT_TIMEOUT, "head", BAR), "the sticky header not a bar")
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "link", INK, "light"),
                            "the light nav's dark links not inked on the dark veil")
            self.assertFalse(b.js(HAS, "nav", OWN), "the light nav kept in the dark veil")
            self.assertTrue(b.wait_for(CLEAR, mn.WAIT_TIMEOUT, "nav"), "the light nav left a solid slab")
            # the navy row of a dark mega menu stays the site's
            b.js("window.scrollTo(0, 0);")
            self.assertTrue(b.wait_for(HAS, mn.WAIT_TIMEOUT, "mega", BAR), "the mega menu not veiled")
            self.assertEqual(b.js(BG_OF, "megatitle"), "rgb(7, 36, 70)", "the dark menu's navy row made see-through")

if __name__ == "__main__":
    unittest.main()

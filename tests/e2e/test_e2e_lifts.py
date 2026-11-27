"""End-to-end: how a veiled header is lifted and how a floating layer
closes, in a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_lifts.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Checked, on a dark page under a dark theme, a light page under a light
theme, and a light page Dark Reader darkens:
  - a header in the flow holding a fixed header at a z-index of 25 and its
    mega menu (Figma) stays over a hero at 10 after it once veiled; the
    site's own ::before on it, 30px tall, never shrinks the blur;
  - a static header holding an absolute nav placed by the page, 100% of the
    window wide (Apple), keeps that nav's width: it is left static, its
    veil without the blur;
  - a mega menu shown a while after the pointer came, with no other event,
    gets the veil; hidden by its content's opacity (Shopify), it loses it.
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
BAR, FLAT = bg.ATTR_BAR, bg.ATTR_FLAT
VEILS = {tone_: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, tone_) + (bg.NAV_BAR_OPACITY,))
         for tone_ in ("dark", "light")}


def lifts_page(page, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#hwrap {height:64px}
#hwrap::before {content:""; position:absolute; left:0; top:0; width:100%%; height:30px}
#fhead {position:fixed; top:0; left:0; right:0; height:64px; z-index:25; display:flex; gap:24px;
  align-items:center; background:%(page)s}
#mega {position:absolute; top:64px; left:0; width:100%%; height:300px; background:%(page)s}
#hero {position:absolute; top:64px; left:0; width:100%%; height:600px; z-index:10; background:%(page)s}
#long {height:300vh}
</style></head><body>
<div id="hwrap"><header id="fhead"><nav><a href="#">Products</a> <a href="#">Resources</a></nav>
<div id="mega" role="menu"><a href="#">Webinars</a> <a href="#">Help center</a></div></header></div>
<div id="hero"><h1>Hero</h1></div>
<div id="long">%(lorem)s</div>
</body></html>""" % {"page": page, "text": text, "lorem": dk.TEXT * 10}


def flat_page(page, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#ghead {width:70%%; height:44px; margin:0 auto}
#gnav {position:absolute; top:0; left:0; width:100%%; min-width:320px; height:44px; display:flex; gap:24px}
#long {height:300vh}
</style></head><body>
<div id="ghead"><nav id="gnav"><a href="#">Store</a> <a href="#">Mac</a> <a href="#">iPad</a></nav></div>
<main id="long">%(lorem)s</main>
</body></html>""" % {"page": page, "text": text, "lorem": dk.TEXT * 10}


def hover_page(page, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#shead {position:sticky; top:0; z-index:5; height:48px; display:flex; gap:24px; align-items:center;
  background:%(page)s}
#lvl2 {display:none; position:absolute; top:48px; left:0; width:100%%; height:300px; background:%(page)s}
#long {height:300vh}
</style></head><body>
<header id="shead"><nav><a href="#" id="products">Products</a> <a href="#">Pricing</a></nav>
<div id="lvl2"><div id="lvl2in"><a href="#">Online store</a> <a href="#">Point of sale</a></div></div></header>
<div id="long"><p id="para">%(lorem)s</p></div>
</body></html>""" % {"page": page, "text": text, "lorem": dk.TEXT * 10}


BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
HAS_BG = BG[:-1] + " === arguments[1];"
BEFORE = "return getComputedStyle(document.getElementById(arguments[0]), '::before')[arguments[1]];"
TOP_AT = "return document.elementFromPoint(arguments[0], arguments[1]).closest('#mega, #hero').id;"
WIDTH = "return document.getElementById(arguments[0]).getBoundingClientRect().width;"
HOVER = ("document.getElementById(arguments[0]).dispatchEvent("
         "new PointerEvent('pointerover', {bubbles: true}));")
# the settle passes after load (SETTLE in content.js) over, so only the
# hover pass may find the menu
SETTLED_S = 3.5


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LiftsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def run_cases(self, make, check):
        routes = {"/d.html": ("text/html; charset=utf-8", make("rgb(18,20,22)", "rgb(235,235,235)").encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", make("rgb(255,255,255)", "rgb(20,20,20)").encode("utf-8"))}
        cases = [("/d.html", True, False, "dark"), ("/l.html", False, False, "light"),
                 ("/l.html", True, True, "dark")]
        for name, binary in tone.browsers():
            for page, dark, darken, veil in cases:
                with self.subTest(browser=name, page=page, darken=darken), mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(page, "dark.test" if page == "/d.html" else "light.test"))
                    if darken:
                        b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                        self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                    else:
                        b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                               mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
                    check(b, VEILS[veil])

    def test_lifted_head(self):
        self.run_cases(lifts_page, self.check_lifted)

    def check_lifted(self, b, veil):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "hwrap", BAR), "the header not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "hwrap", veil), "the header: %r" % b.js(BG, "hwrap"))
        self.assertEqual(b.js(TOP_AT, 100, 200), "mega", "the header's menu under the hero")
        self.assertIn("blur(20px)", b.js(BEFORE, "hwrap", "backdropFilter"))
        self.assertEqual(b.js(BEFORE, "hwrap", "height"), "64px", "the blur shrunk to the site's ::before")

    def test_flat_head(self):
        self.run_cases(flat_page, self.check_flat)

    def check_flat(self, b, veil):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "ghead", BAR), "the header not veiled")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "ghead", FLAT), "the header not left static")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "ghead", veil), "the header: %r" % b.js(BG, "ghead"))
        self.assertEqual(b.js(WIDTH, "gnav"), b.js("return document.documentElement.clientWidth;"),
                         "the nav placed by the page shrunk to the header")
        self.assertEqual(b.js(BEFORE, "ghead", "content"), "none")

    def test_late_hover(self):
        self.run_cases(hover_page, self.check_hover)

    def check_hover(self, b, veil):
        time.sleep(SETTLED_S)
        b.js(HOVER + "setTimeout(() => { document.getElementById('lvl2').style.display = 'block'; }, 150);",
             "products")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "lvl2", BAR), "the late menu not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "lvl2", veil), "the menu: %r" % b.js(BG, "lvl2"))
        # closed by its content's opacity, the wrapper left as it was
        b.js("document.getElementById('lvl2in').style.opacity = '0';" + HOVER, "para")
        self.assertTrue(b.wait_for("return !" + dk.MARKED[7:], mn.WAIT_TIMEOUT, "lvl2", BAR),
                        "the closed menu still veiled")


if __name__ == "__main__":
    unittest.main()

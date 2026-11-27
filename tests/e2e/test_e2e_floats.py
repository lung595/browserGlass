"""End-to-end: the floating layers of a page (menus, drawers, popovers,
dialogs, cookie banners) get the bar's veil (liveControl): the DMS surface
at NAV_BAR_OPACITY over the bar's blur, never bare glass (their text over
the page's) nor the site's opaque panel. In a real headless Firefox (and
LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_floats.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked, on a dark page under a dark theme, a light
page under a light theme, and a light page Dark Reader darkens:
  - a hamburger drawer (frame.work): a fixed dialog in the page's colour
    inside a sticky header, opened by a click, gets the veil and the
    blur, its rows in its colour see-through; closed, it loses the mark;
    the scrim beside it (fixed over the whole window, no text) is left
    alone;
  - a mega menu under the top nav (aftership.com): a see-through box laid
    absolutely below the header, shown on hover, gets the veil;
  - a cookie dialog centred in a fixed wrapper over the whole window: the
    dialog's box gets the veil, the wrapper does not;
  - a badge laid absolutely over an in-page card, and the card, get no
    veil of a floating layer.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
CANVAS, BAR = bg.ATTR_CANVAS, bg.ATTR_BAR
VEILS = {tone_: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, tone_) + (bg.NAV_BAR_OPACITY,))
         for tone_ in ("dark", "light")}


def floats_page(page, text, card):
    """The page in its colour `page`, its text `text`, an in-page card `card`."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {position:sticky; top:0; z-index:60; height:48px; display:flex; gap:24px; align-items:center;
  background:%(page)s}
#drawer {display:none; position:fixed; top:0; left:0; width:70vw; height:100vh; z-index:10; background:%(page)s}
#drawer .row {display:block; height:48px; background:%(page)s; color:%(text)s}
#scrim {display:none; position:fixed; inset:0; z-index:5; background:rgba(0,0,0,0.5)}
#nav {position:relative; height:48px}
#mega {display:none; position:absolute; top:48px; left:0; width:90vw; height:300px; z-index:40}
#nav:hover #mega {display:flex}
#hero {font-size:64px; margin:80px 40px}
#card {position:relative; width:300px; height:200px; margin:40px; background:%(card)s}
#badge {position:absolute; top:4px; left:4px; width:150px; height:80px; z-index:2; background:rgb(200,30,30);
  color:white}
#wrap {display:none; position:fixed; inset:0; z-index:1000; align-items:center; justify-content:center}
#box {width:50vw; height:40vh; background:%(page)s}
#long {height:300vh}
</style></head><body>
<header id="head"><button id="menubtn" aria-expanded="false">Menu</button>
<div id="drawer" role="dialog" aria-modal="true"><a class="row" id="row" href="#">Framework Desktop</a>
<a class="row" href="#">Framework Laptop 13</a><a class="row" href="#">Support</a></div>
<nav id="nav"><button id="resources">Resources</button><div id="mega"><a href="#">Blog</a> <a href="#">Guides</a>
<a href="#">Webinars</a> <a href="#">Customer stories</a></div></nav></header>
<div id="scrim"></div>
<h1 id="hero">Make every tracking moment count</h1>
<div id="card"><span id="badge">New in stock</span><p>An in-page card</p></div>
<div id="long">%(lorem)s</div>
<div id="wrap"><div id="box"><p>We use cookies to improve your experience.</p><button>Reject all</button></div></div>
</body></html>""" % {"page": page, "text": text, "card": card, "lorem": dk.TEXT * 10}


DARK_PAGE = floats_page("rgb(18,20,22)", "rgb(235,235,235)", "rgb(40,40,48)")
LIGHT_PAGE = floats_page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(235,235,240)")
# a click (the add-on's settle passes), as the site's own menu button
OPEN = ("document.getElementById(arguments[0]).style.display = arguments[1];"
        "document.getElementById('menubtn').dispatchEvent(new MouseEvent('click', {bubbles: true}));")
BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
# the blur, on the bar's ::before
BACKDROP = "return getComputedStyle(document.getElementById(arguments[0]), '::before').backdropFilter;"
HAS_BG = BG[:-1] + " === arguments[1];"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FloatsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_floats(self):
        routes = {"/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8"))}
        # (page, dark theme, Dark Reader, the veil's tone)
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
                    self.check(b, VEILS[veil])

    def check(self, b, veil):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        # the hamburger drawer, opened by a click: the veil and the blur,
        # its rows in its colour see-through; the scrim left alone
        b.js("document.getElementById('scrim').style.display = 'block';")
        b.js(OPEN, "drawer", "block")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "drawer", BAR), "the opened drawer not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "drawer", veil),
                        "the drawer's veil: %r" % b.js(BG, "drawer"))
        self.assertIn("blur(20px)", b.js(BACKDROP, "drawer"))
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "row", "rgba(0, 0, 0, 0)"),
                        "a row in the drawer's colour left opaque on the veil: %r" % b.js(BG, "row"))
        self.assertFalse(b.js(dk.MARKED, "scrim", BAR), "the scrim veiled")
        # closed: no mark left
        b.js("document.getElementById('scrim').style.display = 'none';")
        b.js(OPEN, "drawer", "none")
        self.assertTrue(b.wait_for("return !" + dk.MARKED[7:], mn.WAIT_TIMEOUT, "drawer", BAR),
                        "the closed drawer still marked")
        # the mega menu, shown on hover, see-through: the veil
        b.send("WebDriver:PerformActions", {"actions": [{"type": "pointer", "id": "mouse",
                                                         "parameters": {"pointerType": "mouse"},
                                                         "actions": [{"type": "pointerMove", "x": 0, "y": 0,
                                                                      "origin": b.js("return document.getElementById"
                                                                                     "('resources');")}]}]})
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "mega", BAR), "the hovered mega menu not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "mega", veil),
                        "the mega menu's veil: %r" % b.js(BG, "mega"))
        b.send("WebDriver:PerformActions", {"actions": [{"type": "pointer", "id": "mouse",
                                                         "parameters": {"pointerType": "mouse"},
                                                         "actions": [{"type": "pointerMove", "x": 600, "y": 500,
                                                                      "origin": "viewport"}]}]})
        # the cookie dialog in its window-wide wrapper: the box veiled
        b.js(OPEN, "wrap", "flex")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "box", BAR), "the cookie dialog not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "box", veil), "the dialog's veil: %r" % b.js(BG, "box"))
        self.assertFalse(b.js(dk.MARKED, "wrap", BAR), "the window-wide wrapper veiled")
        # the badge over the in-page card, and the card: as they were
        for name in ("badge", "card"):
            self.assertFalse(b.js(dk.MARKED, name, BAR), name + " veiled")
        # (its own fill, or the lighter veil of a block Dark Reader darkens)
        self.assertNotEqual(b.js(BG, "card"), veil, "the in-page card got the bar's veil")


if __name__ == "__main__":
    unittest.main()

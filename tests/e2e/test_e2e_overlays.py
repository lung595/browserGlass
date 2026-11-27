"""End-to-end: the chrome a skeptic sweep found off the norm after the
floating layers were veiled (liveControl). In a real headless Firefox (and
LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_overlays.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Checked, on a dark page under a dark theme, a light page under a light
theme, and a light page Dark Reader darkens:
  - floating layers: a drawer inside the veiled header (frame.work) gets
    its blur over the page (the header's blur painted by its ::before, the
    header no Backdrop Root nor the containing block of its fixed parts),
    and the site's scrim beside it keeps its size and colour; a dialog in a full-window backdrop with no z-index, a scrim
    (GitHub), a popover in a fixed positioner of no size (Galaxus), a
    dropdown its checked popup toggle shows in the page's title bar
    (Vector's language menu) get the veil;
  - headers: under a consent wall over the whole window (Ars Technica), a
    row of links at the top with no nav (Arch Linux), the header in the
    flow under it, and a row holding the site's nav right under that one
    (Swissinfo's mega-menu row, its inner fill see-through) get the veil;
    an article's header in the page's main content does not.
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


def floats_page(page, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {position:sticky; top:0; z-index:60; height:48px; display:flex; gap:24px; align-items:center;
  background:%(page)s}
#drawer {display:none; position:fixed; top:0; left:0; width:70vw; height:100vh; z-index:10; background:%(page)s}
#drawer a {display:block; height:48px}
#dim {display:none; position:fixed; inset:0; z-index:5; background:rgb(31,31,31); opacity:0.5}
#title {position:relative; display:flex; justify-content:space-between; margin:20px 40px}
.dropdown {position:relative}
#lang {display:none; position:absolute; top:30px; right:0; width:171px; height:400px; z-index:50;
  background:%(page)s}
#langbox:checked ~ #lang {display:block}
#pos {position:fixed; top:60px; right:20px; width:0; height:0; z-index:12}
#pop {display:none; position:relative; left:-474px; width:474px; height:300px; background:%(page)s}
#backdrop {display:none; position:fixed; inset:0; background:rgba(33,40,48,0.4); align-items:center;
  justify-content:center}
#dlg {width:480px; height:142px; background:%(page)s}
#long {height:300vh}
</style></head><body>
<header id="head"><nav><a href="#">Home</a> <a href="#">Shop</a></nav><button id="menubtn">Menu</button>
<div id="drawer" role="dialog"><a href="#">Framework Desktop</a><a href="#">Framework Laptop 13</a></div>
<div id="dim"></div></header>
<div id="title"><h1>Page title</h1><div class="dropdown"><input type="checkbox" id="langbox"
aria-haspopup="true"><label for="langbox">33 languages</label><div id="lang"><a href="#">Deutsch</a>
<a href="#">Espanol</a> <a href="#">Francais</a></div></div></div>
<div id="pos"><div id="pop"><p>Settings: theme, language, currency</p></div></div>
<div id="backdrop"><div id="dlg" role="dialog"><p>Appearance settings</p></div></div>
<div id="long">%(lorem)s</div>
</body></html>""" % {"page": page, "text": text, "lorem": dk.TEXT * 10}


def heads_page(page, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#wall {position:fixed; inset:0; z-index:1; background:rgba(0,0,0,0.25); display:flex; align-items:center;
  justify-content:center}
#consent {width:60vw; height:50vh; background:%(page)s}
#topbar {height:60px} #topbar ul {display:flex; gap:24px; margin:0; padding:20px; list-style:none}
#vhead {height:50px}
#rowin {width:86%%; height:43px; margin:0 auto; background:%(page)s}
#long {height:300vh}
</style></head><body>
<div id="wall" role="alertdialog"><div id="consent" role="document"><p>We value your privacy.</p>
<button>Accept</button></div></div>
<div id="topbar"><ul><li><a href="#">Home</a></li><li><a href="#">Packages</a></li><li><a href="#">Forums</a></li>
<li><a href="#">Wiki</a></li></ul></div>
<header id="vhead"><nav><a href="#">Main menu</a> <a href="#">Search</a></nav></header>
<div id="row"><div id="rowin"><nav><a href="#">Geopolitics</a> <a href="#">Democracy</a></nav></div></div>
<main><article><header id="arthead"><nav><a href="#">Share</a></nav><h1>An article</h1></header>
<div id="long">%(lorem)s</div></article></main>
</body></html>""" % {"page": page, "text": text, "lorem": dk.TEXT * 10}


CLICK = "document.getElementById('menubtn').dispatchEvent(new MouseEvent('click', {bubbles: true}));"
SHOW = "document.getElementById(arguments[0]).style.display = arguments[1];" + CLICK
BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
BACKDROP = "return getComputedStyle(document.getElementById(arguments[0]), arguments[1] || null).backdropFilter;"
HAS_BG = BG[:-1] + " === arguments[1];"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class OverlaysE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def run_cases(self, make, check):
        routes = {"/d.html": ("text/html; charset=utf-8", make("rgb(18,20,22)", "rgb(235,235,235)").encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", make("rgb(255,255,255)", "rgb(20,20,20)").encode("utf-8"))}
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
                    self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                               mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
                    check(b, VEILS[veil])

    def veiled(self, b, name, veil, what):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, name, BAR), what + " not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, name, veil), what + ": %r" % b.js(BG, name))

    def test_floats(self):
        self.run_cases(floats_page, self.check_floats)

    def check_floats(self, b, veil):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR), "the header not veiled")
        # the drawer in the veiled header: its blur over the page, the
        # header's veil on its ::before; the site's scrim as it was
        b.js("document.getElementById('dim').style.display = 'block';")
        b.js(SHOW, "drawer", "block")
        self.veiled(b, "drawer", veil, "the drawer")
        self.assertIn("blur(20px)", b.js(BACKDROP, "drawer", "::before"))
        # no Backdrop Root, nor the containing block of its fixed parts
        self.assertEqual(b.js(BACKDROP, "head"), "none")
        self.assertIn("blur(20px)", b.js(BACKDROP, "head", "::before"))
        self.assertGreater(b.js("return document.getElementById('dim').getBoundingClientRect().height;"), 200,
                           "the header's scrim shrunk to the header")
        self.assertFalse(b.js(dk.MARKED, "dim", CANVAS), "the drawer's scrim made see-through")
        # (its own colour, or Dark Reader's for it)
        self.assertNotEqual(b.js(BG, "dim"), "rgba(0, 0, 0, 0)")
        b.js("document.getElementById('dim').style.display = 'none';")
        b.js(SHOW, "drawer", "none")
        self.assertTrue(b.wait_for("return !" + dk.MARKED[7:], mn.WAIT_TIMEOUT, "drawer", BAR),
                        "the closed drawer still marked")
        # the dropdown its popup toggle shows, in the title bar
        b.js("document.getElementById('langbox').checked = true;" + CLICK)
        self.veiled(b, "lang", veil, "the language dropdown")
        b.js("document.getElementById('langbox').checked = false;" + CLICK)
        # the popover in a positioner of no size
        b.js(SHOW, "pop", "block")
        self.veiled(b, "pop", veil, "the popover in its positioner")
        self.assertFalse(b.js(dk.MARKED, "pos", BAR), "the positioner veiled")
        b.js(SHOW, "pop", "none")
        # the dialog in its scrim, over the whole window, no z-index
        b.js(SHOW, "backdrop", "flex")
        self.veiled(b, "dlg", veil, "the dialog in its backdrop")
        self.assertFalse(b.js(dk.MARKED, "backdrop", BAR), "the backdrop veiled")
        self.assertTrue(b.js(BG, "backdrop").endswith(", 0.4)"), "the backdrop's scrim: %r" % b.js(BG, "backdrop"))

    def test_heads(self):
        self.run_cases(heads_page, self.check_heads)

    def check_heads(self, b, veil):
        self.veiled(b, "consent", veil, "the consent box")
        self.veiled(b, "topbar", veil, "the row of links at the top under the consent wall")
        self.veiled(b, "vhead", veil, "the header under the top row")
        self.veiled(b, "row", veil, "the nav row under the header")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "rowin", "rgba(0, 0, 0, 0)"),
                        "the nav row's own fill left on the veil: %r" % b.js(BG, "rowin"))
        self.assertFalse(b.js(dk.MARKED, "arthead", BAR), "the article's header veiled")
        self.assertFalse(b.js(dk.MARKED, "wall", BAR), "the consent wall veiled")


if __name__ == "__main__":
    unittest.main()

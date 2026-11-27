"""End-to-end: search popups get the bar's veil like the other floating
layers (liveControl), in a real headless Firefox (and LibreWolf with
BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_search.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers and stand-in add-on API as test_e2e_floats.py.
Checked, on a dark page under a dark theme, a light page under a light
theme, and a light page Dark Reader darkens:
  - a search flyout hanging out of a fixed nav that stands under another
    bar shown after it (apple.com: the nav 70 px down, here 40, under a locale
    banner, met alone first as a floating layer; the flyout laid from the nav's
    top edge, in the nav's colour) gets the veil itself, never left a
    see-through row of the nav nor an opaque slab; the nav stays a bar;
  - a suggestion list lying within the nav's box gets no second veil;
  - an empty, inert opaque panel laid behind a suggestion list across the
    window (digitec.ch) goes see-through, the list keeping the veil: one
    surface, not the veil over the site's slab;
  - search suggestions dropping from a header in the flow at a z-index of
    their own (ikea.com) stay over the page's positioned row after the
    header, the header's veil (a stacking context) lifted over it.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_floats as fl  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
CANVAS, BAR = bg.ATTR_CANVAS, bg.ATTR_BAR


def search_page(page, text, nav):
    """The page in its colour `page`, its text `text`, the nav and its flyout in `nav`."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#locale {display:none; position:fixed; top:0; left:0; right:0; height:40px; z-index:10000; background:%(page)s}
#nav {position:fixed; top:40px; left:0; right:0; height:44px; z-index:9999; background:%(nav)s; color:white}
#nav ul {display:flex; gap:24px; margin:0; padding:12px 200px; list-style:none}
#flyout {display:none; position:absolute; top:0; left:0; width:100%%; height:260px; background:%(nav)s}
#flyout form {margin:60px 200px 0}
#inbar {display:none; position:absolute; top:2px; left:700px; width:300px; height:40px; background:%(nav)s}
#backing {display:none; position:absolute; top:0; left:0; width:100%%; height:500px; background:%(page)s}
#suggest {display:none; position:absolute; top:120px; left:200px; width:600px; height:300px; z-index:2;
  background:%(page)s}
#hero {font-size:64px; margin:160px 40px 0}
#long {height:300vh}
</style></head><body>
<aside id="locale"><p>Choose another country or region to see content specific to your location.</p></aside>
<nav id="nav"><ul><li>Store</li><li>Mac</li><li>iPad</li><li><button id="find">Search</button>
<div id="flyout"><form role="search"><input value="test"><p>Quick links: Find a Store, Apple Vision Pro,
AirPods, Apple Intelligence</p></form></div></li></ul>
<div id="inbar" role="listbox"><span>test results in the bar</span></div>
<div id="backing" inert></div>
<div id="suggest" role="listbox"><p>tester</p><p>testeur de piles</p><p>test usb</p></div></nav>
<h1 id="hero">Black Friday, gifts that light up</h1>
<div id="long">%(lorem)s</div>
</body></html>""" % {"page": page, "text": text, "nav": nav, "lorem": dk.TEXT * 10}


# Apple's dark page paints its flyout in the page's colour, its light one
# in its dark nav's
DARK_PAGE = search_page("rgb(22,22,23)", "rgb(235,235,235)", "rgb(22,22,23)")
LIGHT_PAGE = search_page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(22,22,23)")
OPEN = ("for (const id of arguments[0]) document.getElementById(id).style.display = arguments[1];"
        "document.getElementById('find').dispatchEvent(new MouseEvent('click', {bubbles: true}));")


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class SearchE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_search(self):
        self.each(DARK_PAGE, LIGHT_PAGE, self.check)

    def test_header_dropdown(self):
        self.each(HEAD_DARK, HEAD_LIGHT, self.check_head)

    def each(self, dark_page, light_page, check):
        routes = {"/d.html": ("text/html; charset=utf-8", dark_page.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", light_page.encode("utf-8"))}
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
                    check(b, fl.VEILS[veil])

    def check(self, b, veil):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        # the locale banner shown once the nav below it was met alone
        # (taken as a floating layer then): the nav is a bar stacked to it
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "nav", BAR), "the nav not veiled")
        b.js(OPEN, ["locale"], "block")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "locale", BAR), "the locale banner not a bar")
        # the flyout hanging out of the nav: its own veil and blur
        b.js(OPEN, ["flyout", "inbar"], "block")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "flyout", BAR), "the search flyout not veiled")
        self.assertTrue(b.wait_for(fl.HAS_BG, mn.WAIT_TIMEOUT, "flyout", veil),
                        "the flyout's veil: %r" % b.js(fl.BG, "flyout"))
        self.assertIn("blur(20px)", b.js(fl.BACKDROP, "flyout"))
        self.assertFalse(b.js(dk.MARKED, "flyout", CANVAS), "the flyout left a see-through row of the nav")
        self.assertTrue(b.js(dk.MARKED, "nav", BAR), "the nav lost its veil")
        self.assertEqual(b.js(fl.BG, "nav"), veil)
        # the list within the nav's box: on the nav's veil, none of its own
        self.assertFalse(b.js(dk.MARKED, "inbar", BAR), "a second veil stacked on the nav's")
        b.js(OPEN, ["flyout", "inbar"], "none")
        self.assertTrue(b.wait_for("return !" + dk.MARKED[7:], mn.WAIT_TIMEOUT, "flyout", BAR),
                        "the closed flyout still marked")
        # the suggestion list over an empty inert panel: the list veiled,
        # the panel see-through
        b.js(OPEN, ["backing", "suggest"], "block")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "suggest", BAR), "the suggestion list not veiled")
        self.assertTrue(b.wait_for(fl.HAS_BG, mn.WAIT_TIMEOUT, "backing", "rgba(0, 0, 0, 0)"),
                        "the panel behind the list left opaque: %r" % b.js(fl.BG, "backing"))
        self.assertFalse(b.js(dk.MARKED, "backing", BAR), "the panel behind the list veiled too")

    def check_head(self, b, veil):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR), "the header in the flow not veiled")
        b.js("document.getElementById('field').dispatchEvent(new FocusEvent('focusin', {bubbles: true}));"
             "document.getElementById('drop').style.display = 'block';")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "drop", BAR), "the suggestions not veiled")
        self.assertTrue(b.wait_for(fl.HAS_BG, mn.WAIT_TIMEOUT, "drop", veil),
                        "the suggestions' veil: %r" % b.js(fl.BG, "drop"))
        # over the pill row laid after the header: the suggestions on top
        self.assertTrue(b.wait_for(ON_TOP, mn.WAIT_TIMEOUT), "the page's pills paint over the suggestions: %r"
                        % b.js("return document.elementFromPoint(300, 120).id;"))


# IKEA: a header in the flow (static, no z-index) with a search field whose
# suggestions drop at a z-index of their own over the row of category
# pills (relative) laid after the header
def head_page(page, text, pill):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {height:96px; display:flex; align-items:center; gap:24px; padding:0 24px}
#box {position:relative; z-index:5004; width:400px}
#field {width:380px}
#drop {display:none; position:absolute; top:40px; left:0; width:400px; height:260px; z-index:5004;
  background:%(page)s}
#pills {position:relative; display:flex; gap:12px; margin:8px 24px; height:48px}
.pill {position:relative; width:180px; background:%(pill)s}
#long {height:300vh}
</style></head><body>
<header id="head"><nav><a href="#">Produits</a> <a href="#">Pieces</a></nav>
<div id="box"><input id="field" value="test"><div id="drop" role="dialog"><p>test</p><p>testeur</p>
<p>table de test</p></div></div></header>
<div id="pills"><a class="pill" href="#">Petit rangement</a><a class="pill" href="#">Lits et matelas</a></div>
<div id="long">%(lorem)s</div>
</body></html>""" % {"page": page, "text": text, "pill": pill, "lorem": dk.TEXT * 10}


HEAD_DARK = head_page("rgb(18,20,22)", "rgb(235,235,235)", "rgb(50,50,56)")
HEAD_LIGHT = head_page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(245,245,245)")
ON_TOP = "return !!document.elementFromPoint(300, 120).closest('#drop');"


if __name__ == "__main__":
    unittest.main()

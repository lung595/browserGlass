"""End-to-end: a fixed or sticky sidebar as tall as the window, holding the
site's menus, gets the bar's veil (liveControl): the DMS surface at
NAV_BAR_OPACITY over the bar's blur, see-through, over nothing but the
page. In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_sides.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked, on a dark page under a dark theme, a light
page under a light theme, and a light page Dark Reader darkens:
  - a see-through guide fixed under the header down the left edge,
    role=navigation on it (YouTube's guide): the veil and the blur,
    still once scrolled;
  - a see-through sticky navigation of a docs page 16px off the left
    edge, a <nav> in it (Python's docs): the veil and the blur, still
    once scrolled;
  - an in-page card and a column of links in the flow beside the
    content: no veil.
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
BAR = bg.ATTR_BAR
VEILS = {tone_: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, tone_) + (bg.NAV_BAR_OPACITY,))
         for tone_ in ("dark", "light")}
LINKS = "".join('<a href="#">Section %d</a>' % i for i in range(12))


def sides_page(page, text, card, side):
    """The page in its colour `page`, its text `text`, an in-page card
    `card`, a column of links in the flow, and the sidebar `side`."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#guide {position:fixed; top:56px; bottom:0; left:0; width:240px; z-index:20; overflow-y:auto}
#guide a, #docnav a, #flow a {display:block; padding:8px 16px; color:inherit}
#cols {display:flex; align-items:flex-start; margin:0 16px}
#docs {position:sticky; top:0; width:300px; height:100vh; flex:none}
#main {flex:1; min-width:0; padding:0 32px}
#guided #main {margin-left:240px}
#card {width:300px; height:200px; margin:40px 0; background:%(card)s}
#flow {width:200px; flex:none}
</style></head><body id="%(kind)s"><div id="cols">%(side)s
<main id="main"><h1>Reference</h1><div id="card"><p>An in-page card</p></div>%(lorem)s</main>
<div id="flow"><a href="#">Edit this page</a><a href="#">Report a bug</a></div></div>
</body></html>""" % {"page": page, "text": text, "card": card, "side": side, "lorem": dk.TEXT * 40,
                     "kind": "guided" if "guide" in side else "docsed"}


GUIDE = '<div id="guide" role="navigation">' + LINKS + '</div>'
DOCS = '<div id="docs"><nav id="docnav">' + LINKS + '</nav></div>'
PAGES = {"dark": ("rgb(18,20,22)", "rgb(235,235,235)", "rgb(40,40,48)"),
         "light": ("rgb(255,255,255)", "rgb(20,20,20)", "rgb(235,235,240)")}
SIDES = {"guide": GUIDE, "docs": DOCS}
BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
# the blur, on the bar's ::before
BACKDROP = "return getComputedStyle(document.getElementById(arguments[0]), '::before').backdropFilter;"
HAS_BG = BG[:-1] + " === arguments[1];"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class SidesE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_sides(self):
        routes = {"/%s-%s.html" % (t, k): ("text/html; charset=utf-8", sides_page(*PAGES[t], side).encode("utf-8"))
                  for t in PAGES for k, side in SIDES.items()}
        # (the page's tone, dark theme, Dark Reader, the veil's tone)
        cases = [("dark", True, False, "dark"), ("light", False, False, "light"), ("light", True, True, "dark")]
        for name, binary in tone.browsers():
            for page, dark, darken, veil in cases:
                for kind in SIDES:
                    with self.subTest(browser=name, page=page, darken=darken, side=kind), \
                            mn.TestServer(routes) as srv, \
                            mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(),
                                       firefox=binary) as b:
                        tone.set_scheme(b, dark)
                        b.navigate(srv.url("/%s-%s.html" % (page, kind), "%s.test" % page))
                        if darken:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                            self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                        else:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                        self.check(b, kind, VEILS[veil])

    def check(self, b, side, veil):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, side, BAR), "the sidebar not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, side, veil), "the sidebar's veil: %r" % b.js(BG, side))
        self.assertIn("blur(20px)", b.js(BACKDROP, side))
        for name in ("card", "flow", "main"):
            self.assertFalse(b.js(dk.MARKED, name, BAR), name + " veiled")
        b.js("window.scrollTo(0, 700);")
        b.js("return new Promise((done) => setTimeout(done, 600));")
        self.assertTrue(b.js(dk.MARKED, side, BAR), "the sidebar lost its veil once scrolled")
        self.assertEqual(b.js(BG, side), veil, "the sidebar's veil once scrolled")


if __name__ == "__main__":
    unittest.main()

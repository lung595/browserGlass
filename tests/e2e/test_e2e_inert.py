"""End-to-end: the page's bars under a modal, and a header under a slot at
the top of the page, get the bar's veil (liveControl). In a real headless
Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_inert.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked, on a dark page under a dark theme, a light
page under a light theme, and a light page Dark Reader darkens:
  - a native <dialog> opened with showModal() before the add-on runs: the
    rest of the page is inert, no hit test reaches it, yet its sticky
    header, its fixed sidebar and its fixed bottom bar (a solid fill of
    the page's colour) get the veil;
  - a page root made inert under a sheet of the site's own (Booking): its
    static header at the top gets the veil;
  - a header in the flow under an ad's empty slot 258px high (NZZ), its
    white container across it: the header gets the veil, that container
    see-through, not a lighter veil of its own.
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
LINKS = "".join('<a href="#">Section %d</a> ' % i for i in range(6))
STYLE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#long {height:300vh}
"""


def modal_page(page, text):
    return (STYLE + """
#top {position:sticky; top:0; z-index:20; height:56px; display:flex; gap:20px; align-items:center;
  background:%(page)s}
#side {position:fixed; top:57px; left:0; bottom:56px; width:200px; z-index:5; background:%(page)s}
#side a {display:block; padding:6px 8px; color:inherit}
#bottom {position:fixed; left:0; right:0; bottom:0; height:56px; z-index:6; display:flex;
  justify-content:space-around; align-items:center; background:%(page)s}
#long {margin-left:220px}
dialog {width:420px; background:%(page)s; color:%(text)s}
</style></head><body>
<header id="top"><b>Brand</b><nav>%(links)s</nav></header>
<nav id="side">%(links)s</nav>
<div id="long">%(lorem)s</div>
<div id="bottom"><a href="#">Home</a><a href="#">Saved</a><a href="#">Settings</a></div>
<dialog id="dlg"><h2>Modal dialog</h2><p>Opened with showModal().</p><button>Close</button></dialog>
<script>document.getElementById("dlg").showModal();</script>
</body></html>""") % {"page": page, "text": text, "links": LINKS, "lorem": dk.TEXT * 30}


def inert_page(page, text):
    return (STYLE + """
#ihead {height:96px; display:flex; gap:20px; align-items:center}
#scrim {position:fixed; inset:0; z-index:300; background:rgba(26, 26, 26, 0.6)}
#sheet {position:absolute; bottom:0; left:0; right:0; height:300px; background:%(page)s}
</style></head><body>
<div id="app" inert><header id="ihead"><b>Brand</b><nav>%(links)s</nav></header>
<div id="long">%(lorem)s</div></div>
<div id="scrim"><div id="sheet" role="dialog" aria-modal="true"><h2>Deals are live</h2><button>Close</button></div></div>
</body></html>""") % {"page": page, "text": text, "links": LINKS, "lorem": dk.TEXT * 30}


def slot_page(page, text):
    return (STYLE + """
#slot {height:258px}
#col {width:80%%; margin:0 auto}
#shead {position:relative; z-index:50}
#shead nav {height:62px; display:flex; gap:20px; align-items:center}
#paint {position:relative; height:136px; background:%(page)s}
</style></head><body>
<div id="slot"><div class="placeholder"></div></div>
<div id="col"><header id="shead"><nav>%(links)s</nav><div id="paint"><b>Brand</b></div></header>
<main id="long">%(lorem)s</main></div>
</body></html>""") % {"page": page, "text": text, "links": LINKS, "lorem": dk.TEXT * 30}


BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
HAS_BG = BG[:-1] + " === arguments[1];"
BEFORE = "return getComputedStyle(document.getElementById(arguments[0]), '::before').backdropFilter;"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class InertE2E(unittest.TestCase):

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

    def veiled(self, b, el, veil):
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, el, BAR), el + " not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, el, veil), "%s: %r" % (el, b.js(BG, el)))
        self.assertIn("blur(20px)", b.js(BEFORE, el))

    def test_modal(self):
        self.run_cases(modal_page, self.check_modal)

    def check_modal(self, b, veil):
        self.assertTrue(b.js("return document.getElementById('dlg').matches(':modal');"))
        for el in ("top", "side", "bottom"):
            self.veiled(b, el, veil)

    def test_inert_root(self):
        self.run_cases(inert_page, self.check_inert)

    def check_inert(self, b, veil):
        self.veiled(b, "ihead", veil)
        self.assertFalse(b.js(dk.MARKED, "app", BAR), "the inert page root veiled")

    def test_slot_head(self):
        self.run_cases(slot_page, self.check_slot)

    def check_slot(self, b, veil):
        self.veiled(b, "shead", veil)
        self.assertTrue(b.wait_for(BG[:-1] + " === 'rgba(0, 0, 0, 0)';", mn.WAIT_TIMEOUT, "paint"),
                        "the header's container: %r" % b.js(BG, "paint"))
        self.assertFalse(b.js(dk.MARKED, "slot", BAR), "the slot veiled")


if __name__ == "__main__":
    unittest.main()

"""End-to-end: text on the light veil and on see-through backings of the
glass is shaded against the worst of what can sit under it, not against
the veil's own colour. In a real headless Firefox (and LibreWolf with
BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_veilworst.py' -v

A bar's light veil (the surface at NAV_BAR_OPACITY) is see-through: under
it scroll a red thumbnail, a site's dark code window, a playing video, a
site's scrim, the glass over a dark wallpaper. The worst of these is
black: the veil over black is a mid grey, where a secondary grey or a
site's blue link reading 4.5:1 on the bare veil reads about 2.5:1. A
see-through backing laid on the glass (a description box in
rgba(0, 0, 0, 0.05), a card in rgba(255, 255, 255, 0.6)) shows over the
glass over the worst wallpaper too. Checked under the light theme, on a
light page, that each text reads 4.5:1 at least against those composites:
  - a grey link, a blue one and a red one in a fixed header (a bar), the
    red one's background a list of empty layers (`none, none`, DSFR's
    buttons), no picture;
  - a grey hint and a blue match in a search panel (a bar) laid over a
    dark code window, the panel last in a page of more text nodes than
    the ink pass walks in the page's order (Wikipedia's language list);
  - a grey line in a faint description box, a blue link on a
    see-through white card, straight on the glass.
The page's main text keeps its near-black. Under the dark theme, on a dark
page, the dark veil's grey and blue labels stay light.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
# the tint's opacity in dk.stylesheet
TINT = 0.8

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s; font:14px sans-serif}
#head {position:fixed; top:0; left:0; right:0; height:56px; z-index:20; background:%(page)s}
#grey, #hint, #descline {color:%(grey)s}
#blue, #match {color:%(link)s}
#red {color:rgb(225,0,15); background-image:none, none}
mark {background:none}
#wiki {color:rgb(51,102,204)}
#main {padding-top:72px}
#code {height:300px; background:rgb(3,7,18); color:rgb(230,230,230)}
#desc {background:rgba(0,0,0,0.05); padding:8px; border-radius:12px}
#card {width:300px; padding:8px; background:rgba(255,255,255,0.6)}
#panel {position:fixed; top:20vh; left:20vw; width:50vw; height:40vh; z-index:40; background:%(page)s}
#long {height:200vh}
</style></head><body>
<div id="head"><a id="grey" href="#">Shorts</a> <a id="blue" href="#">Sign in</a>
<a id="red" href="#">For companies</a></div>
<div id="main"><h1 id="title">Main title</h1><p>%(lorem)s</p>
<div id="desc"><p>%(lorem)s</p><span id="descline">Audio tracks for some languages were generated.</span></div>
<div id="card"><a id="wiki" href="#">single crystal</a></div>
<div id="code">const x = 1;</div>
<div id="long">%(lorem)s%(many)s</div></div>
<div id="panel" role="dialog" aria-modal="true"><p>Suggestions</p>
<span id="hint">in Video games and consoles</span> <mark id="match">text</mark></div>
</body></html>"""


# more text nodes before the panel than the ink pass walks in the page's
# order (INK_NODES, 4000): the panel, appended at the end of the body, is
# read first as a veiled layer
MANY = 4500


def page(page, text, grey, link):
    """The page in `page`, its text `text`, its secondary text `grey`, its links `link`."""
    return PAGE % {"page": page, "text": text, "grey": grey, "link": link, "lorem": dk.TEXT * 3,
                   "many": "<i>w</i> " * MANY}


# #5f6368 reads 6:1 on white, 2.4:1 on the light veil over black; the
# dark page's own greys and links, for the dark veil
LIGHT_PAGE = page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(95,99,104)", "rgb(6,95,212)")
DARK_PAGE = page("rgb(16,20,24)", "rgb(235,235,235)", "rgb(150,150,150)", "rgb(110,160,240)")
COLOR = "return getComputedStyle(document.getElementById(arguments[0])).color;"
# the text's colour light: its weighted channels over 110
LIGHT_TEXT = ("const m = getComputedStyle(document.getElementById(arguments[0])).color.match(/[\\d.]+/g).map(Number);"
              " return 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2] > 110;")
BACK = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"


def over(top, a, under):
    """`top` (r, g, b) at `a` over `under`, mixed in sRGB."""
    return tuple(a * t + (1 - a) * u for t, u in zip(top, under))


def ratio(fg, back):
    """Contrast of the computed colour `fg` (its alpha over `back`) on `back`."""
    r, g, b_, a = tone.rgba(fg)
    hi, lo = sorted((tone.luminance(over((r, g, b_), a, back)), tone.luminance(back)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class VeilWorstE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_worst_under(self):
        routes = {"/l.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        for name, binary in tone.browsers():
            for dark in (False, True):
                with self.subTest(browser=name, dark=dark), mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url("/d.html" if dark else "/l.html", "dark.test" if dark else "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.check_dark(b) if dark else self.check_light(b)

    def wait_bars(self, b, mode):
        self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE, mode), "the tone never measured %s" % mode)
        for bar in ("head", "panel"):
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, bar, bg.ATTR_BAR), "%s not veiled" % bar)

    def check_light(self, b):
        self.wait_bars(b, "light")
        surface = bg.surface_rgb(None, "light")
        black = (0.0,) * 3
        glass = over(surface, TINT, black)
        veil = over(surface, bg.NAV_BAR_OPACITY, black)

        def backing(element_id):
            r, g, b_, a = tone.rgba(b.js(BACK, element_id))
            return over((r, g, b_), a, glass)
        cases = [("grey", veil), ("blue", veil), ("red", veil), ("hint", veil), ("match", veil),
                 ("descline", backing("desc")), ("wiki", backing("card"))]
        for element_id, back in cases:
            # the ink comes with a later pass: polled, WAIT_TIMEOUT at most
            for _ in range(int(mn.WAIT_TIMEOUT * 10)):
                if ratio(b.js(COLOR, element_id), back) >= 4.5:
                    break
                b.js("return new Promise((resolve) => setTimeout(resolve, 100));")
            self.assertGreaterEqual(ratio(b.js(COLOR, element_id), back), 4.5,
                                    "%s (%s) over the worst under it %s" % (element_id, b.js(COLOR, element_id), back))
        # the links keep their hue: still a blue
        for element_id in ("blue", "match", "wiki"):
            r, g, b_, _ = tone.rgba(b.js(COLOR, element_id))
            self.assertGreater(b_, max(r, g) + 40, "%s lost its blue: %r" % (element_id, b.js(COLOR, element_id)))
        self.assertEqual(b.js(COLOR, "title"), "rgb(20, 20, 20)")

    def check_dark(self, b):
        self.wait_bars(b, "dark")
        # the dark veil's labels light, never a light theme's dark shade
        for element_id in ("grey", "blue", "hint"):
            self.assertTrue(b.wait_for(LIGHT_TEXT, mn.WAIT_TIMEOUT, element_id),
                            "%s left dark on the dark veil: %s" % (element_id, b.js(COLOR, element_id)))


if __name__ == "__main__":
    unittest.main()

"""End-to-end: a backdrop drawn in a canvas on a see-through page (YouTube's
ambient mode) is hidden (liveControl). YouTube's watch page lays, behind
the player, a box that takes no pointer events, scaled 1.5 times wide and
2 times high, holding a canvas of about 110x75 pixels stretched over it:
the header, the player and the video's details. It fades in to an opaque
#0f0f0f, an opaque panel over the glass. The walks over the page's layers
never meet it (elementsFromPoint skips what takes no pointer events).
In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_backdrop.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked, on a dark page, under a dark theme:
  - the stretched canvas, shown after the page's layers were marked, is
    hidden (UNDER, opacity 0), the player over it left alone;
  - a chart drawn at the size it is shown, a small stretched canvas and a
    large stretched one taking pointer events (a game, a map) are left
    alone;
  - shrunk to a small box, the canvas is shown again.
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
UNDER = bg.ATTR_UNDER

# The watch page: a see-through dark page, the player in a column, the
# ambient box behind it (hidden at first, as YouTube shows it once the
# video plays), its canvases filled with the page's colour. Below, a
# chart drawn at its size, a small stretched canvas, and a large
# stretched one taking pointer events.
AMBIENT_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><style>
html, body {margin:0; background:transparent; color:rgb(241,241,241)}
#column {position:relative; width:70vw; margin:60px 0 0 24px}
#ambient {position:absolute; top:0; left:0; width:100%; aspect-ratio:16/9; pointer-events:none;
  display:none; justify-content:center; align-items:center}
#scaled {position:relative; width:100%; height:100%; transform:scale(1.5, 2)}
#scaled canvas {position:absolute; top:0; left:0; width:100%; height:100%}
#player {position:relative; aspect-ratio:16/9; background:rgb(0,0,0)}
#chart {display:block; width:400px; height:200px; pointer-events:none}
#small {display:block; width:300px; height:200px; pointer-events:none}
#game {display:block; width:90vw; height:80vh}
</style></head><body><div id="column"><div id="ambient"><div id="scaled">
<canvas id="back" width="110" height="75"></canvas><canvas id="front" width="110" height="75"></canvas>
</div></div><div id="player">Player</div><h1>Title</h1>""" + dk.TEXT + """</div>
<canvas id="chart" width="400" height="200"></canvas><canvas id="small" width="40" height="30"></canvas>
<canvas id="game" width="160" height="90"></canvas>
<script>
for (const c of document.querySelectorAll("canvas")) {
  const x = c.getContext("2d");
  x.fillStyle = "#0f0f0f";
  x.fillRect(0, 0, c.width, c.height);
}
</script></body></html>"""
SHOW = "document.getElementById('ambient').style.display = 'flex';"
SHRINK = "document.getElementById('column').style.width = '200px';"
OPACITY = "return getComputedStyle(document.getElementById(arguments[0])).opacity;"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class BackdropE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_ambient(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_ambient(binary)

    def check_ambient(self, binary):
        routes = {"/watch.html": ("text/html; charset=utf-8", AMBIENT_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/watch.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            b.js(SHOW)
            for name in ("back", "front"):
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, name, UNDER),
                                "the ambient canvas %s left over the glass" % name)
                self.assertEqual(b.js(OPACITY, name), "0")
            for name in ("player", "chart", "small", "game"):
                self.assertFalse(b.js(dk.MARKED, name, UNDER), name + " hidden")
            self.assertEqual(b.js(OPACITY, "game"), "1")
            b.js(SHRINK)
            self.assertTrue(b.wait_for("return !document.getElementById('front').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, UNDER), "a small canvas kept hidden")


if __name__ == "__main__":
    unittest.main()

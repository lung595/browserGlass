"""End-to-end: grey text is judged against the glass over the worst
wallpaper, not against the bare surface. In a real headless Firefox (and
LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_wallglass.py' -v

The page glass is the theme's surface at the tint's opacity over the
wallpaper: the light tint over a dark wallpaper is a mid grey, the dark one
over a light wallpaper a lighter grey. A secondary grey reading 4.5:1 on
the bare surface (#6b7280 on the light one) is under it there. Checked,
under the light theme on a light page and under the dark theme on a dark
one, that each grey reads 4.5:1 at least on the worst composite:
  - a muted line and a thin (weight 200) one straight on the page glass,
    a site's blue link there (shaded, its hue kept) and a see-through
    black (or white) text;
  - a grey link in a fixed bottom bar (its veil over that glass);
  - a light panel's grey hint (light theme), the panel veiled and laid
    over a site's scrim (rgba(0, 0, 0, 0.5)) over the glass.
Text on a white card of its own keeps its grey.
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
SCRIM = 0.5


def wall_page(page, text, grey, card, link, faint):
    """A page in `page`, its text `text`, its secondary text `grey`, a
    link in `link`, a see-through text in `faint`."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
.muted {color:%(grey)s}
#thin {font-weight:200}
#link {color:%(link)s} #faint {color:%(faint)s}
#card {width:300px; padding:8px; background:%(card)s}
#bottom {position:fixed; bottom:0; left:0; right:0; height:48px; z-index:20; background:%(page)s}
#scrim {position:fixed; inset:0; z-index:30; background:rgba(0,0,0,%(scrim)s)}
#panel {position:fixed; top:20vh; left:20vw; width:50vw; height:30vh; z-index:40; background:%(page)s}
#long {height:200vh}
</style></head><body>
<h1>Main title</h1><p>%(lorem)s</p>
<p class="muted" id="muted">A muted line of secondary text.</p>
<p class="muted" id="thin">A thin muted line of secondary text.</p>
<p><a id="link" href="#">A site's own blue link</a> <span id="faint">A see-through muted text</span></p>
<div id="card"><p class="muted" id="carded">A muted line on its own card.</p></div>
<div id="long">%(lorem)s</div>
<div id="bottom"><a class="muted" id="barlink" href="#">Privacy</a></div>
<div id="scrim"></div>
<div id="panel" role="dialog" aria-modal="true"><p>Suggestions</p>
<span class="muted" id="hint">in Video games and consoles</span></div>
</body></html>""" % {"page": page, "text": text, "grey": grey, "card": card, "scrim": SCRIM,
                     "link": link, "faint": faint,
                     "lorem": dk.TEXT * 4}


# #6b7280: 4.6:1 on the light surface, 2.9:1 on its glass over black;
# #808080: 4.7:1 on the dark surface, 2.7:1 on its glass over white
# a link 5:1 on its surface, a see-through text 4.7:1 there
LIGHT_PAGE = wall_page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(107,114,128)", "rgb(255,255,255)",
                       "rgb(6,95,212)", "rgba(5,5,5,0.57)")
DARK_PAGE = wall_page("rgb(16,20,24)", "rgb(235,235,235)", "rgb(128,128,128)", "rgb(16,20,24)",
                      "rgb(64,130,230)", "rgba(250,250,250,0.5)")
COLOR = "return getComputedStyle(document.getElementById(arguments[0])).color;"


def over(top, a, under):
    """`top` (r, g, b) at `a` over `under`, mixed in sRGB."""
    return tuple(a * t + (1 - a) * u for t, u in zip(top, under))


def ratio(fg, back):
    """Contrast of the computed colour `fg` (its alpha over `back`) on `back`."""
    r, g, b_, a = tone.rgba(fg)
    hi, lo = sorted((tone.luminance(over((r, g, b_), a, back)), tone.luminance(back)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class WallGlassE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_worst_wallpaper(self):
        routes = {"/l.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        for name, binary in tone.browsers():
            for page, dark in (("/l.html", False), ("/d.html", True)):
                with self.subTest(browser=name, page=page), mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(page, "dark.test" if dark else "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.check(b, "dark" if dark else "light")

    def check(self, b, mode):
        self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE, mode), "the tone never measured %s" % mode)
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bottom", bg.ATTR_BAR), "the bottom bar not veiled")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "panel", bg.ATTR_BAR), "the panel not veiled")
        surface = bg.surface_rgb(None, mode)
        wall = (255.0,) * 3 if mode == "dark" else (0.0,) * 3
        glass = over(surface, TINT, wall)
        veil = over(surface, bg.NAV_BAR_OPACITY, glass)
        cases = [("muted", glass), ("thin", glass), ("link", glass), ("faint", glass), ("barlink", veil)]
        if mode == "light":
            cases.append(("hint", over(surface, bg.NAV_BAR_OPACITY, over((0, 0, 0), SCRIM, glass))))
        for element_id, back in cases:
            # the ink comes with a later pass: polled, WAIT_TIMEOUT at most
            for _ in range(int(mn.WAIT_TIMEOUT * 10)):
                if ratio(b.js(COLOR, element_id), back) >= 4.5:
                    break
                b.js("return new Promise((resolve) => setTimeout(resolve, 100));")
            self.assertGreaterEqual(ratio(b.js(COLOR, element_id), back), 4.5,
                                    "%s (%s) on the glass over the worst wallpaper %s" % (element_id, mode, back))
        # the link keeps its hue: still a blue
        r, g, b_, _ = tone.rgba(b.js(COLOR, "link"))
        self.assertGreater(b_, max(r, g) + 40, "the link lost its blue: %r" % b.js(COLOR, "link"))
        # a grey on its own opaque card is left as the site drew it
        self.assertFalse(b.js(dk.MARKED, "carded", bg.ATTR_INK), "a grey on its own card inked")


if __name__ == "__main__":
    unittest.main()

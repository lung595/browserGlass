"""End-to-end: text is judged by the colour it shows with, and the inks the
walk of text nodes never met get readable too. In a real headless Firefox
(and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_effective.py' -v

Checked, under the light theme on a light page and under the dark theme on
a dark one, on the glass over the worst wallpaper (black under the light
tint, white under the dark one), or on the opaque box a text sits on:
  - a grey ::placeholder in a field of its own fill reads 4.5:1 on it;
  - a text in an opacity: 0.6 wrapper reads 4.5:1 as it shows (its colour
    at 0.6 over the glass);
  - a gradient clipped to the text (background-clip: text, its colour
    transparent) reads 4.5:1, a hue kept;
  - a grey count on its own opaque box reads 4.5:1 on that box, and an
    orange link there too, still orange;
  - the focus ring of a focused button reads 3:1 on the glass.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_wallglass as wg  # noqa: E402

bg = dk.bg


def effective_page(page, text, field, holder, faded, gradient, box, grey, orange, ring):
    """A page in `page`, its text `text`; a field `field` with a
    placeholder `holder`, a faded text `faded`, a clipped `gradient`, a
    box `box` holding a `grey` count and an `orange` link, a button with a
    `ring` focus ring."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#field {background:%(field)s; color:%(text)s; border:1px solid #888}
#field::placeholder {color:%(holder)s; opacity:1}
#wrap {opacity:0.6} #faded {color:%(faded)s}
#clip {background:linear-gradient(90deg, %(gradient)s); -webkit-background-clip:text; background-clip:text;
       color:transparent; font-size:32px; font-weight:800}
#box {position:absolute; top:400px; left:600px; width:240px; padding:8px; background:%(box)s}
#count {color:%(grey)s} #orange {color:%(orange)s}
#btn {background:transparent; color:%(text)s; border:1px solid #888}
#btn:focus-visible {outline:2px solid %(ring)s; outline-offset:2px}
#long {height:200vh}
</style></head><body>
<h1>Main title</h1><p>%(lorem)s</p>
<p><input id="field" placeholder="Search the shop"></p>
<div id="wrap"><p id="faded">A line in a faded wrapper.</p></div>
<div id="clip">Gradient headline</div>
<p><button id="btn">Focus me</button></p>
<div id="box"><span id="count">0 products</span> <a id="orange" href="#">Home page</a></div>
<div id="long">%(lorem)s</div>
</body></html>""" % {"page": page, "text": text, "field": field, "holder": holder, "faded": faded,
                     "gradient": gradient, "box": box, "grey": grey, "orange": orange, "ring": ring,
                     "lorem": dk.TEXT * 4}


# #aaa: 2.3:1 in a white field; #333 at 0.6: 2.9:1 over the light glass
# on black; a red-orange gradient 2.3:1 there; #999 on white 2.8:1, an
# orange link 2.9:1; a blue ring 2.2:1 on that glass. The dark page mirrors
# them on the dark side.
LIGHT_PAGE = effective_page("rgb(255,255,255)", "rgb(20,20,20)", "rgb(255,255,255)", "rgb(170,170,170)",
                            "rgb(51,51,51)", "#f12711, #f5af19", "rgb(255,255,255)", "rgb(153,153,153)",
                            "rgb(255,102,0)", "rgb(59,130,246)")
DARK_PAGE = effective_page("rgb(16,20,24)", "rgb(235,235,235)", "rgb(30,30,30)", "rgb(100,100,100)",
                           "rgb(200,200,200)", "#e05a3a, #3a9ae0", "rgb(30,30,30)", "rgb(110,110,110)",
                           "rgb(160,60,0)", "rgb(40,60,140)")
STYLE = "return getComputedStyle(document.getElementById(arguments[0]), arguments[1] || null)[arguments[2]];"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class EffectiveInkE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_effective_ink(self):
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

    def reads(self, b, what, back, need, label, op=1.0):
        """Polls `what` (element id, pseudo, property) until its colour at
        `op` reads `need` on `back`; WAIT_TIMEOUT at most. A case of its own."""
        with self.subTest(case=label):
            self.poll(b, what, back, need, label, op)

    def poll(self, b, what, back, need, label, op):
        ratio = lambda: wg.ratio(self.faded(b.js(STYLE, *what), op), back)  # noqa: E731
        for _ in range(int(mn.WAIT_TIMEOUT * 10)):
            if ratio() >= need:
                break
            b.js("return new Promise((resolve) => setTimeout(resolve, 100));")
        self.assertGreaterEqual(ratio(), need, "%s: %s on %s" % (label, b.js(STYLE, *what), back))

    @staticmethod
    def faded(color, op):
        r, g, b_, a = tone.rgba(color)
        return "rgba(%s, %s, %s, %s)" % (r, g, b_, a * op)

    def check(self, b, mode):
        self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE, mode), "the tone never measured %s" % mode)
        surface = bg.surface_rgb(None, mode)
        glass = wg.over(surface, wg.TINT, (255.0,) * 3 if mode == "dark" else (0.0,) * 3)
        field = tone.rgba(b.js(STYLE, "field", None, "backgroundColor"))[:3]
        box = tone.rgba(b.js(STYLE, "box", None, "backgroundColor"))
        # the box keeps its own fill, or the glass cleared it
        box = box[:3] if box[3] >= 0.99 else glass
        self.reads(b, ("field", "::placeholder", "color"), field, 4.5, "placeholder (%s)" % mode)
        self.reads(b, ("faded", None, "color"), glass, 4.5, "faded text (%s)" % mode, 0.6)
        self.reads(b, ("clip", None, "webkitTextFillColor"), glass, 4.5, "clipped gradient (%s)" % mode)
        self.reads(b, ("count", None, "color"), box, 4.5, "grey count on its box (%s)" % mode)
        self.reads(b, ("orange", None, "color"), box, 4.5, "orange link on its box (%s)" % mode)
        r, g, b_, _ = tone.rgba(b.js(STYLE, "orange", None, "color"))
        with self.subTest(case="orange hue (%s)" % mode):
            self.assertGreater(r, b_ + 40, "the orange link lost its hue")
        b.js("document.getElementById('btn').focus({focusVisible: true});")
        self.assertTrue(b.js("return document.getElementById('btn').matches(':focus-visible');"))
        self.reads(b, ("btn", None, "outlineColor"), glass, 3, "focus ring (%s)" % mode)


if __name__ == "__main__":
    unittest.main()

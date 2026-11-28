"""End-to-end: what keeps a backing of its own on a darkened page. A light
page under the light theme (left as it is), then under a dark one (Dark
Reader darkens it), then the light one again. In a real headless Firefox
(and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_backed.py' -v

Checked, darkened:
  - a white button with an indigo label on an indigo call to action band
    (#signup): its white fill and its label's colour kept (BRAND "self");
    a light grey button on the white page (#plain) is left to Dark Reader;
  - a dark headline over a light photo (#headline, the photo a picture
    Dark Reader leaves as it is): its own dark colour kept (BRAND "text");
  - a text drawn only by its text-shadow, its colour transparent (#shadow):
    inked light, its shadow gone;
  - a focus ring Dark Reader darkens (#ring, focused with a visible ring):
    the light ink.
Under the light theme, before and after: the page's own colours, no mark.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
BRAND, INK = bg.ATTR_BRAND, bg.ATTR_INK

# a light photo, served from the page's origin (Dark Reader's fetch, which
# hands over stylesheets only, cannot read it: it is left as it is)
PHOTO = (b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
         b'<rect width="400" height="200" fill="rgb(212,228,245)"/>'
         b'<circle cx="300" cy="60" r="40" fill="rgb(250,240,200)"/></svg>')
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#wrap {background:rgb(255,255,255); min-height:100vh}
#cta {background:rgb(79,70,229); color:rgb(255,255,255); padding:24px; text-align:center}
#signup {display:inline-block; background:rgb(255,255,255); color:rgb(79,70,229); padding:8px 16px;
  border:1px solid rgb(255,255,255); border-radius:6px}
#plain {background:rgb(246,248,250); color:rgb(36,41,47); border:1px solid rgb(208,215,222); padding:8px 16px}
#pic {background:url(/photo.svg) center/cover; padding:40px 24px}
#headline {color:rgb(34,34,34); font-size:22px; margin:0}
#shadow {color:transparent; text-shadow:0 0 0 rgb(51,51,51)}
#ring:focus-visible {outline:2px solid rgb(37,99,235); outline-offset:2px}
</style></head><body><div id="wrap">""" + dk.TEXT + """
<div id="cta"><h2>A call to action</h2><a id="signup" href="#">Sign up</a></div>
<p><button id="plain" type="button">Code</button></p>
<section id="pic"><p id="headline">Dark headline over a light photo</p></section>
<p id="shadow">Text drawn only by its text-shadow, colour transparent.</p>
<p><button id="ring" type="button">Focused with a visible ring</button></p>""" + dk.TEXT + """</div></body></html>"""
OUTLINE = "return getComputedStyle(document.getElementById(arguments[0])).outlineColor;"
FOCUS = "document.getElementById('ring').focus({focusVisible: true});"
UNMARKED = ("return !document.querySelector('style.darkreader')"
            " && !document.querySelector('[' + arguments[0] + ']');")


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class BackedE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_backed(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_backed(binary)

    def color(self, b, name):
        return b.js(dk.PART_COLOR, name, None)

    def check_light(self, b):
        self.assertTrue(b.wait_for(UNMARKED, mn.WAIT_TIMEOUT, BRAND), "marked under a light theme")
        for name in ("signup", "headline", "shadow"):
            self.assertFalse(b.js(dk.MARKED, name, INK), name + " inked under a light theme: %r" % b.js(
                "const e = document.getElementById(arguments[0]); return [e.outerHTML, getComputedStyle(e).color,"
                " getComputedStyle(e).backgroundColor, getComputedStyle(e.parentElement).backgroundColor];", name))
        self.assertEqual(b.js(dk.PART_BG, "signup", None), "rgb(255, 255, 255)")
        self.assertEqual(self.color(b, "signup"), "rgb(79, 70, 229)")
        self.assertLess(tone.luminance(tone.rgba(self.color(b, "headline"))), 0.05)
        self.assertEqual(b.js("return getComputedStyle(document.getElementById('shadow')).textShadow;"),
                         "rgb(51, 51, 51) 0px 0px 0px")
        b.js(FOCUS)
        self.assertEqual(b.js(OUTLINE, "ring"), "rgb(37, 99, 235)")

    def check_backed(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", PAGE.encode("utf-8")),
                  "/photo.svg": ("image/svg+xml", PHOTO)}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/p.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
            self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "not light")
            self.check_light(b)
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for(dk.DARKENED), "not darkened")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "wrap", dk.CANVAS), "wrapper not marked")
            # the white button on the brand band, its label's colour
            self.assertEqual(b.js(dk.TILED, "signup", BRAND), "self")
            self.assertEqual(b.js(dk.PART_BG, "signup", None), "rgb(255, 255, 255)")
            self.assertEqual(self.color(b, "signup"), "rgb(79, 70, 229)")
            self.assertFalse(b.js(dk.MARKED, "plain", BRAND), "a plain button on the page kept")
            # the headline on its own light photo
            self.assertEqual(b.js(dk.TILED, "headline", BRAND), "text")
            self.assertLess(tone.luminance(tone.rgba(self.color(b, "headline"))), 0.05, self.color(b, "headline"))
            # the text drawn by its shadow: light ink
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "shadow", INK, "light"),
                            "shadow: %r" % b.js(dk.TILED, "shadow", INK))
            self.assertGreater(tone.luminance(tone.rgba(self.color(b, "shadow"))), 0.5)
            # the focus ring: light
            b.js(FOCUS)
            self.assertGreater(tone.luminance(tone.rgba(b.js(OUTLINE, "ring"))), 0.5, b.js(OUTLINE, "ring"))
            # the light theme again: the page's own colours
            tone.set_scheme(b, False)
            self.check_light(b)


if __name__ == "__main__":
    unittest.main()

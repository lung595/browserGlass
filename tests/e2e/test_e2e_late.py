"""End-to-end: a page that paints its own dark theme late (liveControl).
A single-page app (YouTube) shows its text black while its style sheets
are still coming: the tone first measured is light, and the bar's veil
with it. Its theme then lands without a reload and without touching
<html>: a style sheet added to <head>, or a class put on <body>. The tone
is read again then, and the header's veil and its labels follow; while
the page declares its dark version on <html> ([dark]), the bar never
shows the light veil over the dark glass, whatever was measured. In a
real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_late.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked:
  - [dark] on <html> from the start, the text black, then a sheet in
    <head> turning it light (dark theme): the header's veil dark before
    and after, the tone dark after, its label no longer inked;
  - no marker, the same late sheet, under a dark and a light theme: the
    tone and the header's veil dark once the sheet is in;
  - no marker, the dark theme a class put on <body> late: the same.
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
VEILS = {tone_: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, tone_) + (bg.NAV_BAR_OPACITY,))
         for tone_ in ("dark", "light")}
LIGHT_TEXT = "rgb(241,241,241)"
DARK_BAR = "rgb(15,15,15)"


def late_page(marker):
    """A page whose text is black and its header white until its theme
    lands: a fixed header over long text, [dark] on <html> when `marker`, and a body.dark rule
    ready for the class."""
    return """<!doctype html><html%(marker)s><head><meta charset="utf-8"><style>
html, body {margin:0; color:rgb(0,0,0)}
body.dark {color:%(light)s}
body.dark #masthead {background:%(bar)s}
#masthead {background:rgb(255,255,255); position:fixed; top:0; left:0; right:0; z-index:10; height:56px;
  display:flex; gap:24px; align-items:center; padding:0 16px}
#main {padding-top:80px}
</style></head><body>
<div id="masthead"><span id="logo">YouTube</span><span>Create</span></div>
<div id="main">%(text)s</div>
</body></html>""" % {"marker": " dark" if marker else "", "light": LIGHT_TEXT, "bar": DARK_BAR,
                       "text": dk.TEXT * 6}


SHEET = ("const s = document.createElement('style');"
         "s.textContent = 'body {color: %s} #masthead {background: %s}';"
         "document.head.append(s);" % (LIGHT_TEXT, DARK_BAR))
BODY_CLASS = "document.body.classList.add('dark');"
TONE = "return document.documentElement.getAttribute(arguments[0]);"
IS_TONE = TONE[:-1] + " === arguments[1];"
BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
HAS_BG = BG[:-1] + " === arguments[1];"
UNINKED = "return !document.getElementById(arguments[0]).hasAttribute(arguments[1]);"
PAUSE = "return new Promise((done) => setTimeout(done, arguments[0]));"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LateE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_late(self):
        routes = {"/marker.html": ("text/html; charset=utf-8", late_page(True).encode("utf-8")),
                  "/plain.html": ("text/html; charset=utf-8", late_page(False).encode("utf-8"))}
        # (page, dark theme, how the theme lands)
        cases = [("marker", True, SHEET), ("plain", True, SHEET), ("plain", False, SHEET),
                 ("plain", True, BODY_CLASS)]
        for name, binary in tone.browsers():
            for page, dark, lands in cases:
                with self.subTest(browser=name, page=page, dark=dark, lands=lands[:30]), \
                        mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url("/%s.html" % page, "plain.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.check(b, page == "marker", lands)

    def check(self, b, marker, lands):
        # the black text first: a light page, its header a bar
        self.assertTrue(b.wait_for(IS_TONE, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "light"),
                        "the black text not measured light: %r" % b.js(TONE, bg.ATTR_TONE))
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "masthead", bg.ATTR_BAR), "the header not veiled")
        if marker:
            # a page declaring its dark version: never the light veil
            self.assertEqual(b.js(BG, "masthead"), VEILS["dark"], "the light veil on a [dark] page")
        # the page's own passes are over when its theme lands
        b.js(PAUSE, 1500)
        b.js(lands)
        self.assertTrue(b.wait_for(IS_TONE, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "dark"),
                        "the late dark theme never read: %r" % b.js(TONE, bg.ATTR_TONE))
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, "masthead", VEILS["dark"]),
                        "the header kept the veil of the other tone: %r" % b.js(BG, "masthead"))
        self.assertTrue(b.wait_for(UNINKED, mn.WAIT_TIMEOUT, "logo", bg.ATTR_INK),
                        "the header's light label kept its ink")


if __name__ == "__main__":
    unittest.main()

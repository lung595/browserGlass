"""End-to-end: white pictures straight on the glass of a light page, with
no label of their own beside them (GNOME's Discourse: its white logo in a
see-through header holding only two blue buttons; a white svg drawn on a
light page). In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_logo.py' -v

Checked, the light page under a light theme and under a dark one (the
light glass both times): the white word mark in the header (#logo) and
the white svg on the page (#mark) are tiled "invert" (their ink dark),
whatever the header's labels; the colour logos (#color, the yellow #sun) and the white
icon on the site's blue button (#onbtn) are left alone. A dark page under
a dark theme: none of them tiled.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
TILE = bg.ATTR_TILE


def page(back, text, para):
    """A page in `back`, its text `text`."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(back)s; color:%(text)s; font:14px sans-serif}
#head {position:sticky; top:0; z-index:10; height:56px; display:flex; align-items:center; gap:16px;
  padding:0 16px}
#head button {background:rgb(0,111,201); color:rgb(255,255,255); border:0; padding:6px 10px}
.row {display:flex; align-items:center; gap:8px; margin:16px}
</style></head><body><div id="head"><svg id="logo" width="110" height="36" viewBox="0 0 110 36">
<path fill="#fff" d="M4 4h20v28H4z M30 8h12v20H30z M48 4h20v8H48z M48 16h20v16H48z M74 4h32v28H74z"/></svg>
<span style="flex:1"></span><button>Sign Up</button><button id="btn"><svg id="onbtn" width="14" height="14"
viewBox="0 0 14 14"><circle cx="7" cy="7" r="6" fill="#fff"/></svg> Log In</button></div>
<div class="row"><svg id="mark" width="24" height="24" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18"
rx="4" fill="#fff" stroke="#e5e7eb"/></svg><span>A white svg on the page</span></div>
<div class="row"><svg id="color" width="96" height="32" viewBox="0 0 96 32"><rect width="30" height="32"
fill="#ea4335"/><rect x="33" width="30" height="32" fill="#fbbc05"/><rect x="66" width="30" height="32"
fill="#34a853"/></svg><svg id="sun" width="120" height="40" viewBox="0 0 120 40"><rect x="10" y="10"
width="100" height="20" fill="rgb(255,200,0)"/></svg></div>%(para)s</body></html>""" % {"back": back, "text": text, "para": para * 12}


LIGHT = page("rgb(255,255,255)", "rgb(20,20,20)", dk.TEXT)
DARK = page("rgb(18,20,22)", "rgb(235,235,235)", "<p>" + "Light text of a dark page. " * 8 + "</p>")


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LogoE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_logo(self):
        routes = {"/l.html": ("text/html; charset=utf-8", LIGHT.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK.encode("utf-8"))}
        for name, binary in tone.browsers():
            for path, dark in (("/l.html", False), ("/l.html", True), ("/d.html", True)):
                with self.subTest(browser=name, page=path, dark=dark), mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(path, "light.test" if path == "/l.html" else "dark.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    light = path == "/l.html"
                    self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE,
                                               "light" if light else "dark"), "the tone")
                    for el in ("logo", "mark"):
                        if light:
                            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, el, TILE, "invert"),
                                            "%s left %r" % (el, b.js(dk.TILED, el, TILE)))
                    # a later pass has run (the tone set, the logo read)
                    b.js("window.scrollBy(0, 10);")
                    for el in ("color", "sun", "onbtn") + (() if light else ("logo", "mark")):
                        self.assertIsNone(b.js(dk.TILED, el, TILE), el + " tiled")


if __name__ == "__main__":
    unittest.main()

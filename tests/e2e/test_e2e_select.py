"""End-to-end: a drop-down field (<select>) drawn white for a dark top
bar, the bar's dark band cleared by the glass (admin.ch's language
switcher, "FR"). The option the field shows is drawn in the field's
colour, its text in an <option> with no box of its own. In a real
headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_select.py' -v

Checked, the light page under a light theme and under a dark one (the
light glass both times): the link beside the field on the band (#link)
and the field (#lang) are inked dark, the field's options in the
system's colours (not the ink on the site's dark option fill). A dark
page under a dark theme: the field keeps its white, no ink.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
INK = bg.ATTR_INK


def page(back, text, para):
    """A page in `back`, its text `text`, a header with the dark band."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(back)s; color:%(text)s; font:14px sans-serif}
header {position:sticky; top:0; z-index:10; background:%(back)s}
#band {background:rgb(47,67,86); color:rgb(255,255,255); height:40px; display:flex; align-items:center;
  justify-content:space-between; padding:0 16px}
#link {color:rgb(255,255,255)}
#lang {background:transparent; color:rgb(255,255,255); border:0; font-size:14px}
#lang option {background:rgb(47,67,86)}
#brand {height:80px; padding:16px}
</style></head><body><header><div id="band"><a id="link" href="#">Les autorités fédérales</a>
<select id="lang"><option>DE</option><option selected>FR</option><option>IT</option></select></div>
<div id="brand">Le Conseil fédéral</div></header>%(para)s</body></html>""" % {
        "back": back, "text": text, "para": para * 12}


LIGHT = page("rgb(255,255,255)", "rgb(20,20,20)", dk.TEXT)
DARK = page("rgb(18,20,22)", "rgb(235,235,235)", "<p>" + "Light text of a dark page. " * 8 + "</p>")
OPTION = "return getComputedStyle(document.querySelector('#lang option')).color;"
OPTION_BG = "return getComputedStyle(document.querySelector('#lang option')).backgroundColor;"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class SelectE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_select(self):
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
                    if path == "/l.html":
                        self.check_light(b)
                    else:
                        self.check_dark(b)

    def check_light(self, b):
        self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "light"), "not light")
        self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "link", INK),
                        "the link on the cleared band not inked")
        self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "lang", INK),
                        "the field left %s" % b.js(dk.PART_COLOR, "lang", None))
        option, back = b.js(OPTION), b.js(OPTION_BG)
        self.assertGreaterEqual(tone.contrast(option, back), 4.5, (option, back))

    def check_dark(self, b):
        self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "dark"), "not dark")
        # the pass ran: the header is a bar
        self.assertTrue(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']');",
                                   mn.WAIT_TIMEOUT, bg.ATTR_BAR), "no bar")
        self.assertIsNone(b.js(dk.TILED, "lang", INK), "the field inked on a dark page")
        self.assertEqual(b.js(dk.PART_COLOR, "lang", None), "rgb(255, 255, 255)")


if __name__ == "__main__":
    unittest.main()

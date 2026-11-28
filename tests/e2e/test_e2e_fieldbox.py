"""End-to-end: search fields in a bar, as sites draw them. In a real headless
Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_fieldbox.py' -v

/page.html on plain.test (the generic style clears html, body, header and
main, as the bundled one does), under the light theme:
  - a white search field (#q) in a header in the flow of a sticky wrapper
    (the bar; the header in it is the page's first, no bar of its own: made
    one on each pass, it would strip the veils of its fields), its
    suggestion list open
    under it (an absolute box beside the field's wrapper, larger than it,
    not over it): the field is veiled, the list no face of its wrapper;
  - a see-through field (#tube) whose wrapper paints the field (#box: a
    white bordered box round it, the field's own fill transparent): the
    wrapper is veiled;
  - a field mark another pass takes off: marked again;
  - a mega menu (an absolute dark blue panel the glass veils) holding a
    field in a faint white tint with white text and placeholder (#mega):
    its text and placeholder are inked dark on the light veil.
Under a dark theme (no Dark Reader here) the page keeps its tone: the marks
stay as they were.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
GENERIC_CSS = ("html, body, header, main { background-color: transparent !important;"
               " background: none !important; border: none !important; box-shadow: none !important; }\n")
TEXT = "<p>" + "Some dark text on the page, read on the glass. " * 4 + "</p>"
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40);font:16px/1.5 sans-serif}
#pin{position:sticky;top:0;z-index:20;background:rgb(255,255,255)}
header{display:flex;gap:16px;align-items:center;padding:8px 12px;background:rgb(255,255,255)}
header a{color:rgb(55,65,81)}
.wrap{position:relative}
#q{background:rgb(255,255,255);border:1px solid rgb(208,215,222);color:rgb(31,35,40);padding:6px}
.ac{position:absolute;top:40px;left:0;width:280px;margin:0;padding:4px 0;list-style:none;z-index:30;
  background:rgb(255,255,255);border:1px solid rgb(229,231,235)}
#box{background:rgb(255,255,255);border:1px solid rgb(208,215,222);border-radius:20px;padding:6px 12px}
#tube{background:transparent;border:0;color:rgb(15,15,15);width:300px}
nav{position:relative}
.mega{position:absolute;top:64px;left:0;right:0;z-index:35;height:360px;padding:16px 40px;
  background:rgb(5,41,98);color:rgb(255,255,255);display:flex;gap:48px}
.mega a{display:block;color:rgb(255,255,255);padding:4px 0}
#mega{background:rgba(255,255,255,0.1);border:0;border-radius:18px;color:rgb(255,255,255);padding:8px 12px;
  width:280px}
#mega::placeholder{color:rgb(255,255,255);opacity:1}
main{padding:0 24px}
</style></head><body>
<div id="pin"><header><b>Site</b><nav><a href="#n">News</a> <a href="#o">Opinion</a>
<div class="mega" role="menu"><div><a href="#w">World</a><a href="#u">UK</a><a href="#c">Climate</a>
<a href="#s">Science</a></div><div><a href="#f">Football</a><a href="#t">Tennis</a></div>
<form><input id="mega" placeholder="Search the site"></form></div></nav>
<div class="wrap"><input id="q" placeholder="Search"><ul class="ac" role="listbox"><li>test</li>
<li>testing tools</li><li>test suite</li></ul></div>
<div id="box"><form><input id="tube" placeholder="Search"></form></div></header></div>
<main><h1>Fields in the bar</h1>%s</main></body></html>""" % (TEXT * 12)
BLOCKS = """return Object.fromEntries(arguments[0].map((id) =>
  [id, document.getElementById(id).getAttribute(arguments[1])]));"""
WANT = {"q": "veil", "box": "veil", "tube": None}
STRIP = "document.getElementById('q').removeAttribute(arguments[0]);"
MARKED = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === 'veil';"
SAMPLES = 10
SAMPLE_GAP = 0.2
INK_OF = "return getComputedStyle(document.getElementById(arguments[0])).color;"
HOLDER_OF = "return getComputedStyle(document.getElementById(arguments[0]), '::placeholder').color;"


def routes():
    return {"/page.html": ("text/html; charset=utf-8", PAGE.encode("utf-8"))}


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FieldBoxE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_fieldbox(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def tone_is(self, b, want):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute(arguments[0]);",
                                                tone.TONE), want))

    def marks_are(self, b):
        b.wait_for(MARKED, mn.WAIT_TIMEOUT, "box", bg.ATTR_BLOCK)
        b.wait_for(MARKED, mn.WAIT_TIMEOUT, "q", bg.ATTR_BLOCK)
        self.assertEqual(b.js(BLOCKS, list(WANT), bg.ATTR_BLOCK), WANT)
        # the field on the mega menu's light veil reads in dark ink
        b.wait_for("return getComputedStyle(document.getElementById('mega')).color !== 'rgb(255, 255, 255)';",
                   mn.WAIT_TIMEOUT)
        self.assertLess(tone.luminance(tone.rgba(b.js(INK_OF, "mega"))), 0.2)
        self.assertLess(tone.luminance(tone.rgba(b.js(HOLDER_OF, "mega"))), 0.3)

    def check(self, binary):
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes()) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/page.html", "plain.test"))
            b.js(tone.RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            self.marks_are(b)
            # the veil stays from pass to pass
            for _ in range(SAMPLES):
                time.sleep(SAMPLE_GAP)
                self.assertEqual(b.js(BLOCKS, ["q"], bg.ATTR_BLOCK), {"q": "veil"})
            # a mark another pass takes off comes back
            b.js(STRIP, bg.ATTR_BLOCK)
            b.js("window.scrollBy(0, 1);")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "q", bg.ATTR_BLOCK))
            # a dark theme: the page's tone, and so its marks, stay
            tone.set_scheme(b, True)
            self.tone_is(b, "light")
            self.marks_are(b)


if __name__ == "__main__":
    unittest.main()

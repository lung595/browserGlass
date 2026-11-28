"""End-to-end: a field over the site's scrim, in a header of the tone. In a
real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_scrim.py' -v

/light.html on plain.test, under the light theme: a sticky header (a bar,
veiled in the light tone) holds the search box, a wrapper with the site's
scrim in it (a fixed, empty layer in rgba(0, 0, 0, 0.5) over the whole
window, under the form) and the form over the scrim, its white field typed
in black (a shop's open search). The scrim dims the page round the field,
it is no backing of the wrapper: the field's black text keeps its ink (no
INK "light", near-white on the site's white field, never veiled).

/dark.html on plain.test, under the dark theme: the dark twin (a page in
its own dark colours, a dark field typed in light grey) keeps its light
text: no INK "dark".
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
TEXT = "<p>" + "Some text on the page, read on the glass. " * 4 + "</p>"
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:%(page)s} body{margin:0;color:%(text)s;font:16px/1.5 sans-serif}
main{padding:0 24px}
#head{position:sticky;top:0;z-index:13;height:98px;box-sizing:border-box;padding:34px 0 0 224px;background:%(page)s}
#box{width:900px;height:40px;z-index:13}
#scrim{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5)}
.open #scrim{display:block}
#form{position:relative;z-index:1;height:40px}
#q{position:relative;z-index:2;box-sizing:border-box;width:100%%;height:40px;border:0;padding:0 40px;
  font:16px sans-serif;background:%(field)s;color:%(text)s}
</style></head><body><div id="head"><div id="box"><div id="scrim"></div>
<form id="form"><input id="q" type="search" value="test"></form></div></div>
<main><h1>A shop</h1>%(body)s</main></body></html>"""
LIGHT_PAGE = PAGE % {"page": "rgb(255,255,255)", "text": "rgb(0,0,0)", "field": "rgb(255,255,255)",
                     "body": TEXT * 12}
DARK_PAGE = PAGE % {"page": "rgb(13,17,23)", "text": "rgb(230,237,243)", "field": "rgb(13,17,23)",
                    "body": TEXT * 12}
INK_OF = "return document.getElementById('q').getAttribute(arguments[0]);"
# the passes after the marks: long enough for markInk to have run again
PASSES_S = 2.5


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ScrimE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_scrim(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def open(self, b, url, dark):
        tone.set_scheme(b, dark)
        b.navigate(url)
        b.js(tone.RUN_CONTENT, self.content_js)
        want = "dark" if dark else "light"
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone not %r" % want)
        if not b.wait_for("return document.getElementById('head').hasAttribute(arguments[0]);",
                          mn.WAIT_TIMEOUT, bg.ATTR_BAR):
            self.fail("the header is no bar")
        # the field keeps the site's own fill: no block mark
        self.assertIsNone(b.js("return document.getElementById('q').getAttribute(arguments[0]);", bg.ATTR_BLOCK))
        # the search opens: the scrim shows, the field focused
        b.js("document.getElementById('box').classList.add('open'); document.getElementById('q').focus();")
        time.sleep(PASSES_S)
        return b.js(INK_OF, bg.ATTR_INK)

    def check(self, binary):
        routes = {"/light.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/dark.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            with self.subTest(page="/light.html"):
                self.assertNotEqual(self.open(b, srv.url("/light.html", "plain.test"), False), "light")
            with self.subTest(page="/dark.html"):
                self.assertNotEqual(self.open(b, srv.url("/dark.html", "plain.test"), True), "dark")


if __name__ == "__main__":
    unittest.main()

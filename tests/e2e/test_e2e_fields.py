"""End-to-end: fields, secondary buttons and lone panels on the glass, and a
fade into a colour space other than rgb(). In a real headless Firefox (and
LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_fields.py' -v

/light.html on plain.test (the generic style clears html, body, header
and main, as the bundled one does; a white band across the page, above
the content, is the page's layer), under the light theme:
  - a white search field in a sticky header the style made glass
    (#q, bordered) and a light grey borderless button (#flat): both keep
    the site's own look (no block mark, their fill and no ring);
  - a fixed cookie box with a brand button (#accept, its green kept) and
    a light secondary one (#more, no mark, its own fill);
  - a white button on an indigo band (#onband): it keeps its white;
  - a lone light grey panel of text (#panel, 800 px wide, too narrow for
    a module) and a low bordered header bar (#bar, 900x54): both veiled;
  - a row of white tiles whose frames are drawn with thin gradient lines
    (#tile): veiled as a row of cards, the lines are no picture;
  - a sticky side column of links (a bar) whose footer fades in a ::before into
    color(srgb 1 1 1) (#foot): the fade is see-through (FADE_PSEUDO).
Under a dark theme (no Dark Reader here) the page keeps its tone (its text
is dark): the marks stay as they were.

/toggle.html?dark, a page whose own toggle sets html.dark, under the dark
theme: its white search field (#q, the browser's default) keeps its white
and its dark text: no veil under the dark theme.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
GENERIC_CSS = ("html, body, header, main { background-color: transparent !important;"
               " background: none !important; border: none !important; box-shadow: none !important; }\n")
TEXT = "<p>" + "Some dark text on the page, read on the glass. " * 4 + "</p>"
LINES = ("linear-gradient(rgb(221,221,221), rgb(221,221,221)) 0 0/100% 1px no-repeat,"
         " linear-gradient(rgb(221,221,221), rgb(221,221,221)) 0 100%/100% 1px no-repeat")
LIGHT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40);font:16px/1.5 sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;gap:16px;padding:12px;background:rgb(255,255,255)}
input{background:rgb(255,255,255);border:1px solid rgb(208,215,222);color:rgb(31,35,40);padding:6px}
.btn{background:rgb(246,248,250);border:1px solid rgb(208,215,222);color:rgb(36,41,47);padding:6px 14px}
.primary{background:rgb(31,136,61);border:1px solid rgb(31,136,61);color:rgb(255,255,255);padding:6px 14px}
#flat{background:rgb(238,238,238);border:none;color:rgb(36,41,47);padding:6px 14px}
.top{height:48px;background:rgb(255,255,255)} .layout{display:flex} aside{position:sticky;top:0;width:200px;height:100vh;background:rgb(255,255,255)}
#foot{position:relative;margin-top:300px;padding:8px}
#foot::before{content:"";position:absolute;left:0;right:0;top:-24px;height:24px;
  background:linear-gradient(rgba(0,0,0,0), color(srgb 1 1 1))}
main{flex:1;padding:0 24px}
.indigo{background:rgb(55,48,163);color:rgb(255,255,255);padding:16px}
#onband{background:rgb(255,255,255);border:none;color:rgb(55,48,163);padding:6px 14px}
#panel{width:800px;height:196px;background:rgb(246,245,247);padding:0 16px;box-sizing:border-box}
#bar{width:900px;height:54px;background:rgb(246,248,250);border:1px solid rgb(208,215,222);box-sizing:border-box;
  padding:12px}
.tiles{display:flex;gap:16px} .tile{width:188px;height:208px;padding:12px;box-sizing:border-box;
  background:%s;background-color:rgb(255,255,255)}
.cookie{position:fixed;right:16px;bottom:16px;z-index:9;width:360px;padding:16px;background:rgb(255,255,255);
  border:1px solid rgb(208,215,222)}
</style></head><body>
<header><b>Site</b><a href="#a">Docs</a><input id="q" placeholder="Search"><button id="flat">Menu</button></header>
<div class="top"><p>A white band across the page: its layer.</p></div>
<div class="layout"><aside><nav><a href="#l">Latest</a> <a href="#t">Top</a></nav><div id="foot">About</div></aside><main>
<h1>Fields on the glass</h1>%s
<div class="indigo"><p>A brand band of white text.</p><button id="onband">Join</button></div>%s
<div id="bar">Files in this folder</div>%s
<div id="panel"><h2>France services</h2><p>Une aide de proximit&eacute; pour vos d&eacute;marches.</p></div>%s
<div class="tiles"><div class="tile" id="tile"><h3>A tile</h3><p>Its frame drawn with lines.</p></div>
<div class="tile"><h3>Another tile</h3><p>Its frame drawn with lines.</p></div></div>%s%s</main></div>
<div class="cookie"><p>We use cookies.</p><button id="accept" class="primary">Accept</button>
<button id="more" class="btn">Settings</button></div>
</body></html>""" % (LINES, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT * 6)
TOGGLE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40)}
header{position:sticky;top:0;padding:12px;background:rgb(255,255,255)}
html.dark{background:rgb(13,17,23)} html.dark body{color:rgb(201,209,217)}
html.dark header{background:rgb(22,27,34)}
</style></head><body><header><b>Site</b> <input id="q" placeholder="Search"></header>""" + (
    "<p>Main text of the page, in the tone of its theme.</p>" * 12) + """
<script>if (location.search === "?dark") document.documentElement.classList.add("dark");</script></body></html>"""
BLOCKS = """return Object.fromEntries(arguments[0].map((id) =>
  [id, document.getElementById(id).getAttribute(arguments[1])]));"""
IDS = ("q", "flat", "accept", "more", "onband", "panel", "bar", "tile")
WANT = {"q": None, "flat": None, "accept": None, "more": None, "onband": None,
        "panel": "veil", "bar": "veil", "tile": "veil"}
FADING = "return document.getElementById('foot').getAttribute(arguments[0]);"
FILL_OF = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
INK_OF = "return getComputedStyle(document.getElementById(arguments[0])).color;"
SHADOW_OF = "return getComputedStyle(document.getElementById(arguments[0])).boxShadow;"


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FieldsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_fields(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def tone_is(self, b, want):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute(arguments[0]);",
                                                tone.TONE), want))

    def marks_are(self, b):
        b.wait_for("return document.getElementById('panel').hasAttribute(arguments[0]);", mn.WAIT_TIMEOUT, bg.ATTR_BLOCK)
        self.assertEqual(b.js(BLOCKS, list(IDS), bg.ATTR_BLOCK), WANT)
        # fields and secondary buttons keep the site's own fill, no ring
        for el, fill in (("q", "rgb(255, 255, 255)"), ("flat", "rgb(238, 238, 238)"), ("more", "rgb(246, 248, 250)")):
            self.assertEqual(b.js(FILL_OF, el), fill)
            self.assertEqual(b.js(SHADOW_OF, el), "none")
        self.assertEqual(b.js(FADING, bg.ATTR_FADE_PSEUDO), "before")
        # the brand button keeps its green, the one on the band its white
        self.assertEqual(b.js(FILL_OF, "accept"), "rgb(31, 136, 61)")
        self.assertEqual(b.js(FILL_OF, "onband"), "rgb(255, 255, 255)")

    def check(self, binary):
        routes = {"/light.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/toggle.html": ("text/html; charset=utf-8", TOGGLE_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            with self.subTest(page="/light.html"):
                tone.set_scheme(b, False)
                b.navigate(srv.url("/light.html", "plain.test"))
                b.js(tone.RUN_CONTENT, self.content_js)
                self.tone_is(b, "light")
                self.marks_are(b)
                # a dark theme: the page's tone, and so its marks, stay
                tone.set_scheme(b, True)
                self.tone_is(b, "light")
                self.marks_are(b)
            with self.subTest(page="/toggle.html?dark"):
                tone.set_scheme(b, True)
                b.navigate(srv.url("/toggle.html?dark", "plain.test"))
                b.js(tone.RUN_CONTENT, self.content_js)
                self.tone_is(b, "dark")
                self.assertIsNone(b.js(BLOCKS, ["q"], bg.ATTR_BLOCK)["q"])
                self.assertEqual(b.js(FILL_OF, "q"), "rgb(255, 255, 255)")
                self.assertLess(tone.luminance(tone.rgba(b.js(INK_OF, "q"))), 0.5)


if __name__ == "__main__":
    unittest.main()

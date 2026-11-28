"""End-to-end: icons and logos drawn for a dark header, on the light veil
(python.org's white and grey word mark beside its colour snake, MDN's pale
blue and white word mark and its white mask chevrons, frame.work's white
"menu" ligature beside its hidden dark scrim, Le Monde's grey account
icon), and a black logo the site's own filter draws on a page Dark Reader
darkens (frame.work's). In a real headless Firefox (and LibreWolf with
BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_icons.py' -v

Checked, a light page whose sticky header is a dark band, under a light
theme:
  - an <img> logo whose white part is lost on the veil beside a blue and
    a yellow part (#py in the header, #py2 on the page) gets a dark
    backing ("back"), its colours untouched;
  - an inline svg in pale blue and white in the header (#mdn) is inverted;
  - a button whose ::after paints a white mask chevron (#chev) is inked
    dark, the chevron in its ink;
  - a white ligature icon (#menu) in a box holding a hidden dark scrim
    over the window is inked dark, not light;
  - a 24 px svg in a grey under 3:1 with a white part (#acct) is inverted;
  - a colour logo whose white part is small (#color) is left alone.
Under a dark theme with Dark Reader: a white word mark the site's own
invert(1) turns black in the header (#fw) gets "plain" (no filter); under
the light theme it is left alone.
"""

import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
TILE = bg.ATTR_TILE
INK = bg.ATTR_INK
GLYPH = bg.ATTR_GLYPH

# A word mark: a blue and a yellow part (a snake), and a wide light grey
# part (the letters), with see-through gaps.
PY_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="145" height="41" viewBox="0 0 145 41">
<rect x="0" y="2" width="18" height="36" fill="#3776ab"/><rect x="18" y="2" width="14" height="36" fill="#ffd43b"/>
<rect x="40" y="8" width="20" height="26" fill="#dcdcdc"/><rect x="64" y="8" width="20" height="26" fill="#e6e6e6"/>
<rect x="88" y="8" width="20" height="26" fill="#dcdcdc"/><rect x="112" y="8" width="20" height="26" fill="#e6e6e6"/>
</svg>"""
# The same with a large blue part and a small white one: a colour logo.
COLOR_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="145" height="41" viewBox="0 0 145 41">
<rect x="0" y="2" width="100" height="36" fill="#3776ab"/><rect x="104" y="2" width="20" height="36" fill="#ffffff"/>
</svg>"""
WHITE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="160" height="21" viewBox="0 0 160 21">
<rect x="0" y="2" width="70" height="17" fill="#fff"/><rect x="80" y="2" width="80" height="17" fill="#fff"/></svg>"""
CHEVRON = "data:image/svg+xml," + urllib.parse.quote(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M4 7l6 6 6-6" stroke="#000" '
    'stroke-width="2" fill="none"/></svg>')

PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20); font:14px sans-serif}
#hdr {position:sticky; top:0; z-index:10; height:64px; display:flex; align-items:center; gap:16px; padding:0 16px;
  background:rgb(27,27,27); color:rgb(255,255,255)}
#hdr a, #hdr button {color:rgb(255,255,255); background:transparent; border:0; font:inherit}
#chev::after {content:""; display:inline-block; width:20px; height:20px; background-color:rgb(255,255,255);
  mask-image:url("%(chevron)s"); mask-size:contain}
#scrim {position:fixed; inset:0; background:rgb(31,31,31); visibility:hidden; opacity:0.5}
.row {display:flex; align-items:center; gap:8px; margin:16px}
</style></head><body><header id="hdr"><img id="py" width="145" height="41" alt="" src="/py.svg">
<svg id="mdn" width="83" height="24" viewBox="0 0 83 24"><path d="M0 2h20v20H0z" fill="rgb(164,206,254)"/>
<path d="M26 6h34v16H26z" fill="#fff"/><path d="M64 20h18v2H64z" fill="rgb(164,206,254)"/></svg>
<a id="lnk" href="#">Docs</a><button id="chev" type="button">HTML</button>
<div id="box"><div id="scrim"></div><button type="button"><span id="menu">menu</span></button></div></header>
<div class="row"><img id="py2" width="145" height="41" alt="" src="/py.svg"><span>A colour logo on the page</span></div>
<div class="row"><img id="color" width="145" height="41" alt="" src="/color.svg">
<svg id="acct" width="24" height="24" viewBox="0 0 24 24"><path d="M2 2h9v9H2z" fill="#a7a9ad"/>
<path d="M13 2h9v9h-9z" fill="#a7a9ad"/><path d="M2 13h9v9H2z" fill="#a7a9ad"/><path d="M15 15h5v5h-5z" fill="#fff"/></svg>
<span>Account</span></div>%(text)s</body></html>""" % {"chevron": CHEVRON, "text": dk.TEXT * 12}
# A light page's white sticky header: its logo a white picture its own
# invert(1) turns black (frame.work's class "filter-invert").
FW_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20); font:14px sans-serif}
#hdr {position:sticky; top:0; z-index:10; height:64px; display:flex; align-items:center; gap:16px; padding:0 16px;
  background:rgb(255,255,255)}
#fw {filter:invert(1)}
</style></head><body><header id="hdr"><a href="/"><img id="fw" width="160" height="21" alt="" src="/white.svg"></a>
<a href="#">Laptops</a></header>%(text)s</body></html>""" % {"text": dk.TEXT * 12}

AFTER_FILL = ("const el = document.getElementById(arguments[0]);"
              "return [getComputedStyle(el, '::after').backgroundColor, getComputedStyle(el).color];")


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class IconsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def routes(self):
        return {"/p.html": ("text/html; charset=utf-8", PAGE.encode("utf-8")),
                "/f.html": ("text/html; charset=utf-8", FW_PAGE.encode("utf-8")),
                "/py.svg": ("image/svg+xml", PY_SVG), "/color.svg": ("image/svg+xml", COLOR_SVG),
                "/white.svg": ("image/svg+xml", WHITE_SVG)}

    def tiled(self, b, el, kind):
        self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, el, TILE, kind),
                        "%s: %r, not %r" % (el, b.js(dk.TILED, el, TILE), kind))

    def test_light(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name), mn.TestServer(self.routes()) as srv, \
                    mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
                tone.set_scheme(b, False)
                b.navigate(srv.url("/p.html", "light.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "light"), "the tone")
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "hdr", bg.ATTR_BAR), "the header no bar")
                for el, kind in (("py", "back"), ("py2", "back"), ("mdn", "invert"), ("acct", "invert")):
                    self.tiled(b, el, kind)
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "chev", INK, "dark"),
                                "the chevron's button: %r" % b.js(dk.TILED, "chev", INK))
                self.assertIn("after", b.js(dk.TILED, "chev", GLYPH) or "")
                fill, color = b.js(AFTER_FILL, "chev")
                self.assertEqual(fill, color, "the chevron not in the ink")
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "menu", INK, "dark"),
                                "the menu icon: %r" % b.js(dk.TILED, "menu", INK))
                b.js("window.scrollBy(0, 10);")
                self.assertIsNone(b.js(dk.TILED, "color", TILE), "a colour logo tiled")
                b.navigate(srv.url("/f.html", "light.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "light"), "the tone")
                b.js("window.scrollBy(0, 10);")
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "hdr", bg.ATTR_BAR), "the header no bar")
                self.assertIsNone(b.js(dk.TILED, "fw", TILE), "a black logo on the light veil tiled")

    def test_dark(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name), mn.TestServer(self.routes()) as srv, \
                    mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
                tone.set_scheme(b, True)
                b.navigate(srv.url("/f.html", "light.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "hdr", bg.ATTR_BAR), "the header no bar")
                self.tiled(b, "fw", "plain")


if __name__ == "__main__":
    unittest.main()

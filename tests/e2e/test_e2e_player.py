"""End-to-end: the controls of a video player on a light page, under a
light theme and a dark one (the page is light: the light glass both
times). In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_player.py' -v

The player (YouTube's) is a box with no fill of its own holding, among
many hidden overlays, a <video> in a box of its own, moved out of the
player until it plays, an empty overlay for its poster (set late, once
the page has settled), a control bar laid absolutely over both, its time
white on a see-through dark pill, and a settings popup in the site's dark
panel (rgba(28, 28, 28, 0.9)) opened by a click, its labels white and its
values white at 70 %, each value beside a small white chevron drawn as a
background image of its box. Checked:
  - a white text right on the glass (#plain) is inked dark (the pass ran);
  - the time on its pill keeps its white: the control bar is laid in the
    player, over its video, before and after the poster is set;
  - the popup gets the bar's veil, its labels and values inked dark on
    it: the chevron is an icon, not a picture behind the value.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402
import test_e2e_darken as dk  # noqa: E402

bg = tone.bg
BAR, INK = bg.ATTR_BAR, bg.ATTR_INK

PHOTO = (b'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">'
         b'<rect width="400" height="200" fill="rgb(120,140,170)"/>'
         b'<circle cx="300" cy="60" r="40" fill="rgb(250,240,200)"/></svg>')
CHEVRON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24'%3E"
           "%3Cpath fill='%23fff' d='m9 18-1-1 5-5-5-5 1-1 6 6z'/%3E%3C/svg%3E")
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(15,15,15); font:14px sans-serif}
#plain {color:rgb(255,255,255)}
#player {position:relative; width:960px; height:540px; margin:16px; overflow:hidden; border-radius:12px}
#box {position:absolute; inset:0}
#video {position:absolute; left:0; top:-100%%; width:100%%; height:100%%}
.overlay {display:none}
#poster {position:absolute; inset:0}
#poster.shown {background:url(/photo.svg) center/cover no-repeat}
#bottom {position:absolute; left:12px; right:12px; bottom:0; height:48px; z-index:59}
#pill {display:inline-block; background:rgba(0,0,0,0.3); border-radius:20px; padding:8px 12px}
#time {color:rgb(255,255,255)}
#gear {margin-left:24px}
#menu {display:none; position:absolute; right:12px; bottom:60px; width:320px; height:200px; z-index:71;
  background:rgba(28,28,28,0.9); border-radius:12px}
#panel {position:absolute; inset:0}
.item {display:flex; justify-content:space-between; padding:10px 16px; color:rgb(238,238,238)}
.value {width:150px; padding-right:32px; text-align:right; color:rgba(255,255,255,0.7);
  background:url("%(chevron)s") no-repeat calc(100%% - 12px) 50%% / 18px 18px}
</style></head><body>%(text)s<p id="plain">White text on the page</p>
<div id="player"><div id="box"><video id="video"></video></div><div id="poster"></div>%(overlays)s
<div id="bottom"><span id="pill"><span id="time">0:00 / 8:13</span></span>
<button id="gear" aria-haspopup="true" aria-controls="menu" aria-expanded="false">Settings</button></div>
<div id="menu"><div id="panel">
<div class="item"><span id="label">Sleep timer</span><span class="value" id="value">Off</span></div>
<div class="item"><span>Playback speed</span><span class="value">Normal</span></div>
</div></div></div>%(more)s</body></html>""" % {"chevron": CHEVRON, "text": dk.TEXT, "more": dk.TEXT * 6,
                    "overlays": '<div class="overlay"></div>' * 20}
# a click (the add-on's settle passes), as the site's own settings button
OPEN = ("document.getElementById('menu').style.display = arguments[0];"
        "document.getElementById('gear').setAttribute('aria-expanded', String(arguments[0] !== 'none'));"
        "document.getElementById('gear').dispatchEvent(new MouseEvent('click', {bubbles: true}));")
COLOR = "return getComputedStyle(document.getElementById(arguments[0])).color;"
POSTER = "document.getElementById('poster').classList.add('shown');"
INKED = dk.TILED + " === 'dark';"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class PlayerE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_player(self):
        routes = {"/p.html": ("text/html; charset=utf-8", PAGE.encode("utf-8")),
                  "/photo.svg": ("image/svg+xml", PHOTO)}
        for name, binary in tone.browsers():
            for dark in (False, True):
                with self.subTest(browser=name, dark=dark), mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url("/p.html", "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.check(b)

    def check(self, b):
        self.assertTrue(b.wait_for(dk.TONE_IS, mn.WAIT_TIMEOUT, bg.ATTR_TONE, "light"), "not light")
        self.assertTrue(b.wait_for(INKED, mn.WAIT_TIMEOUT, "plain", INK), "white text on the glass not inked")
        self.assertIsNone(b.js(dk.TILED, "time", INK), "the time over the video inked")
        b.js(POSTER)
        # the popup, opened by a click: the veil, its text inked dark
        b.js(OPEN, "block")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "menu", BAR), "the popup not veiled")
        for name in ("label", "value"):
            self.assertTrue(b.wait_for(INKED, mn.WAIT_TIMEOUT, name, INK),
                            "%s left %s on the light veil" % (name, b.js(COLOR, name)))
        self.assertIsNone(b.js(dk.TILED, "time", INK), "the time over the poster inked")
        self.assertEqual(b.js(COLOR, "time"), "rgb(255, 255, 255)")


if __name__ == "__main__":
    unittest.main()

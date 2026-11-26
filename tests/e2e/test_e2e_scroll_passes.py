"""End-to-end: a long scroll costs a few layer passes, not one per frame.
Every scroll event (any scroller, caught on its way down) asks for the
layers again; each pass runs hit-test grids (elementsFromPoint) and style
reads, so content.js runs it at most once per INK_MS, the last request
still served.
In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_scroll_passes.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_layers as ly  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

FRAMES = 30
# Scroll a few pixels on each of FRAMES animation frames, and count the
# frames in which the page was hit-tested (a layer pass, or ink).
SCROLL = ("const hits = {n: 0};"
          "for (const proto of [Document.prototype, ShadowRoot.prototype]) {"
          "  const f = proto.elementsFromPoint;"
          "  proto.elementsFromPoint = function (...a) { hits.n++; return f.apply(this, a); };"
          "}"
          "return new Promise((done) => {"
          "  let frame = 0, busy = 0, seen = 0;"
          "  requestAnimationFrame(function step() {"
          "    if (hits.n > seen) busy++;"
          "    seen = hits.n;"
          "    if (++frame > arguments[0]) return done(busy);"
          "    window.scrollBy(0, 4);"
          "    requestAnimationFrame(step);"
          "  });"
          "});".replace("arguments[0]", str(FRAMES)))


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ScrollPassesE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_scroll_passes(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                routes = {"/s.html": ("text/html; charset=utf-8", ly.STICKY_PAGE.encode("utf-8"))}
                with mn.TestServer(routes) as srv, \
                        mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, True)
                    b.navigate(srv.url("/s.html", "dark.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    b.js("window.scrollTo(0, 400);")
                    self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", ly.BAR), "nav not a bar")
                    # the passes after the load (SETTLE_MS) are over
                    time.sleep(3.5)
                    busy = b.js(SCROLL)
                    # FRAMES frames are about 500 ms: a pass at the start,
                    # one INK_MS later, ink's own, a last one at most
                    self.assertLessEqual(busy, 5, "hit-tested on %d of %d scrolled frames" % (busy, FRAMES))
                    # the last request is served: the nav, scrolled back
                    # into the flow, is no bar
                    b.js("window.scrollTo(0, 0);")
                    self.assertTrue(b.wait_for("return !document.getElementById('bar').hasAttribute(arguments[0]);",
                                               mn.WAIT_TIMEOUT, ly.BAR), "nav still a bar at the top")


if __name__ == "__main__":
    unittest.main()

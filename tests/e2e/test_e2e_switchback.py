"""End-to-end: a live light -> dark -> light switch of the system's colour
scheme gives the light page back its marks. In a real headless Firefox
(and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_switchback.py' -v

/app.html on plain.test: a single-page app whose html, body and body > div
the generic style clears, with the bundled style's 0.5 s fade of their
background (so the glass tint eases in and out once the scheme switches),
holding a white wrapper (#app) of dark text, grey text (#muted) and, far below the window,
a light grey secondary button (#far).
Under the light theme the wrapper is glass (no OWN, no CANVAS: the style
clears it), the grey text gets the soft ink and the button its veil
(BLOCK "veil"). Under a dark theme (no Dark Reader here) the page keeps its
light tone, and so its marks: the wrapper is not kept as the site's own
(OWN) for text read while the root's tint still fades in (no tint yet).
Back to the light theme everything is as on the first load: the far button
keeps its veil (the root fading out is no page without glass, which would
drop the marks far from the window).
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
GENERIC_CSS = ("html, body, body > div { background-color: transparent !important; background: none !important;"
               " border: none !important; box-shadow: none !important;"
               " transition: background-color 0.5s ease-in-out, background 0.5s ease-in-out; }\n")
APP_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body{background:transparent;margin:0;font:16px/1.5 sans-serif;color:rgb(31,35,40)}
#app{background:rgb(255,255,255);min-height:100vh} main{max-width:900px;margin:0 auto;padding:16px}
#muted{color:rgb(107,114,128)}
.btn{background:rgb(246,248,250);border:1px solid rgb(208,215,222);color:rgb(36,41,47);padding:6px 14px}
</style></head><body><div id="app"><main><h1>An app on a white wrapper</h1>""" + (
    "<p>Body text on the wrapper, dark on white, read on the glass.</p>" * 6) + """
<p id="muted">A muted grey line on the wrapper.</p><div style="height:2400px"></div>
<button id="far" class="btn">Secondary button far below</button></main></div></body></html>"""
STATE = """const el = (id) => document.getElementById(id);
return [el('app').hasAttribute(arguments[0]), el('app').hasAttribute(arguments[3]),
  el('muted').getAttribute(arguments[1]), el('far').getAttribute(arguments[2])];"""
SWITCH_S = 3


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class SwitchBackE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_switch_back(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def state(self, b):
        return b.js(STATE, bg.ATTR_OWN, bg.ATTR_INK, bg.ATTR_BLOCK, bg.ATTR_CANVAS)

    def check(self, binary):
        routes = {"/app.html": ("text/html; charset=utf-8", APP_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        light = [False, False, "soft", "veil"]
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/app.html", "plain.test"))
            b.js(tone.RUN_CONTENT, self.content_js)
            # the far button is judged once it is near the window
            b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'light';",
                       mn.WAIT_TIMEOUT, tone.TONE)
            b.js("scrollTo(0, document.documentElement.scrollHeight);")
            b.wait_for("return document.getElementById('far').getAttribute(arguments[0]) === 'veil';",
                       mn.WAIT_TIMEOUT, bg.ATTR_BLOCK)
            b.js("scrollTo(0, 0);")
            time.sleep(1)
            self.assertEqual(self.state(b), light)
            tone.set_scheme(b, True)
            time.sleep(SWITCH_S)
            self.assertEqual(self.state(b), light)
            tone.set_scheme(b, False)
            time.sleep(SWITCH_S)
            self.assertEqual(self.state(b), light)


if __name__ == "__main__":
    unittest.main()

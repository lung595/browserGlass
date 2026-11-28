"""End-to-end: buttons and fields keep the site's own look on the glass. In a
real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_ownbuttons.py' -v

A white pill button (#pill: #f1f1f1, a 20px radius, no border: YouTube's
"Subscribe"), a white borderless button (#flat) and a white bordered field
(#q), on a page of the site's own dark theme (/dark.html, its background
near-black) and on a light page (/light.html), each under the dark and the
light theme (no Dark Reader here): their computed background, box-shadow,
border and radius are those the page gives them without the add-on, from
pass to pass, and none gets a block mark.
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
html{background:%s} body{margin:0;color:%s;font:16px/1.5 sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;gap:16px;padding:12px;background:%s}
#q{background:rgb(255,255,255);border:1px solid rgb(211,211,211);border-radius:20px;color:rgb(15,15,15);
  padding:6px 12px;width:320px}
#pill{background:rgb(241,241,241);border:none;border-radius:20px;color:rgb(15,15,15);padding:0 16px;height:36px}
#flat{background:rgb(255,255,255);border:none;color:rgb(15,15,15);padding:6px 14px}
main{padding:0 24px}
</style></head><body>
<header><b>Site</b><input id="q" placeholder="Search"><button id="flat" type="button">Menu</button></header>
<main><h1>A video</h1><div><b>A channel</b> <button id="pill" type="button">Subscribe</button></div>%s</main>
</body></html>"""
PAGES = {"/dark.html": ("rgb(15,15,15)", "rgb(241,241,241)", "rgb(15,15,15)", "dark"),
         "/light.html": ("rgb(255,255,255)", "rgb(15,15,15)", "rgb(255,255,255)", "light")}
IDS = ("pill", "flat", "q")
LOOKS = """return Object.fromEntries(arguments[0].map((id) => {
  const el = document.getElementById(id), s = getComputedStyle(el);
  return [id, [s.backgroundColor, s.boxShadow, s.borderTopWidth + ' ' + s.borderTopColor, s.borderTopLeftRadius,
               el.getAttribute(arguments[1])]];
}));"""
SAMPLES = 10
SAMPLE_GAP = 0.2


def routes():
    return {path: ("text/html; charset=utf-8", (PAGE % (page, ink, head, TEXT * 12)).encode("utf-8"))
            for path, (page, ink, head, _) in PAGES.items()}


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class OwnButtonsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_own_buttons(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def check(self, binary):
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes()) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            for path, (_, _, _, want_tone) in PAGES.items():
                for dark in (True, False):
                    with self.subTest(page=path, dark=dark):
                        tone.set_scheme(b, dark)
                        b.navigate(srv.url(path, "plain.test"))
                        # the site's own look, before the add-on runs
                        own = b.js(LOOKS, list(IDS), bg.ATTR_BLOCK)
                        b.js(tone.RUN_CONTENT, self.content_js)
                        self.assertTrue(b.wait_for(
                            "return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                            mn.WAIT_TIMEOUT, tone.TONE, want_tone), "tone not " + want_tone)
                        for _ in range(SAMPLES):
                            time.sleep(SAMPLE_GAP)
                            b.js("window.scrollBy(0, 1);")
                            self.assertEqual(b.js(LOOKS, list(IDS), bg.ATTR_BLOCK), own)


if __name__ == "__main__":
    unittest.main()

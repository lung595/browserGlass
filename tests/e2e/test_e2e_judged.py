"""End-to-end: fills judged again once they change, and a lone panel of the
dark tone. In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_judged.py' -v

/late.html on plain.test, under the light theme: three light grey buttons
right on the glass keep their own grey, no block mark. Then the page turns
two into brand buttons, as a framework does once hydrated or once its
style sheet arrives late: #code gets data-variant="primary" (a green fill,
faded in by a transition), #late a green fill from a style sheet added
afterwards. Their green shows, no mark; #more keeps its grey.

/dark.html on plain.test, under the dark theme: a page in its own dark
colours (no Dark Reader here) with a lone opaque dark grey box (#commit,
904x54, rgb(21, 27, 35), the page's layer see-through) right on the glass:
it is veiled as its light twin is (BLOCK "veil").
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
LATE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40);font:16px/1.5 sans-serif}
main{padding:0 24px}
.btn{background:rgb(246,248,250);border:1px solid rgb(208,215,222);color:rgb(36,41,47);padding:6px 14px;
  transition:background-color 80ms}
.btn[data-variant=primary]{background:rgb(31,136,61);color:rgb(255,255,255)}
</style></head><body><main><h1>A repository</h1>%s
<p><button id="code" class="btn">Code</button> <button id="late" class="btn">Clone</button>
<button id="more" class="btn">Settings</button></p>%s</main></body></html>""" % (TEXT, TEXT * 8)
DARK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(13,17,23)} body{margin:0;color:rgb(240,246,252);font:16px/1.5 sans-serif}
main{padding:0 24px}
#commit{width:904px;height:54px;box-sizing:border-box;padding:12px;background:rgb(21,27,35);
  border:1px solid rgb(61,68,77);border-radius:6px}
</style></head><body><main><h1>A repository</h1>%s
<div id="commit">Latest commit: fix the build</div>%s</main></body></html>""" % (TEXT, TEXT * 8)
HYDRATE = """document.getElementById('code').setAttribute('data-variant', 'primary');
const sheet = document.createElement('style');
sheet.textContent = '#late{background:rgb(31,136,61);color:rgb(255,255,255)}';
document.head.append(sheet);
document.body.append(document.createElement('div'));"""
BLOCKS = """return Object.fromEntries(arguments[0].map((id) =>
  [id, document.getElementById(id).getAttribute(arguments[1])]));"""
SETTLED = """return arguments[0].every((id) => !document.getElementById(id).hasAttribute(arguments[1])
  && getComputedStyle(document.getElementById(id)).backgroundColor === 'rgb(31, 136, 61)');"""
GREEN = "rgb(31, 136, 61)"
GREY = "rgb(246, 248, 250)"
FILL_OF = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
SETTLE_S = 1


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class JudgedE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_judged(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def tone_is(self, b, want):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute(arguments[0]);",
                                                tone.TONE), want))

    def block_is(self, b, el, want):
        if not b.wait_for("return document.getElementById(arguments[0]).getAttribute(arguments[1]) === arguments[2];",
                          mn.WAIT_TIMEOUT, el, bg.ATTR_BLOCK, want):
            self.fail("#%s block %r, not %r" % (el, b.js(BLOCKS, [el], bg.ATTR_BLOCK)[el], want))

    def check(self, binary):
        routes = {"/late.html": ("text/html; charset=utf-8", LATE_PAGE.encode("utf-8")),
                  "/dark.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            with self.subTest(page="/late.html"):
                tone.set_scheme(b, False)
                b.navigate(srv.url("/late.html", "plain.test"))
                b.js(tone.RUN_CONTENT, self.content_js)
                self.tone_is(b, "light")
                time.sleep(SETTLE_S)
                self.assertEqual(b.js(BLOCKS, ["code", "late", "more"], bg.ATTR_BLOCK),
                                 {"code": None, "late": None, "more": None})
                self.assertEqual(b.js(FILL_OF, "more"), GREY)
                b.js(HYDRATE)
                if not b.wait_for(SETTLED, mn.WAIT_TIMEOUT, ["code", "late"], bg.ATTR_BLOCK):
                    self.fail("brand buttons not green: %r" % b.js(BLOCKS, ["code", "late"], bg.ATTR_BLOCK))
                time.sleep(SETTLE_S)
                self.assertEqual(b.js(BLOCKS, ["more"], bg.ATTR_BLOCK), {"more": None})
                self.assertEqual(b.js(FILL_OF, "more"), GREY)
            with self.subTest(page="/dark.html"):
                tone.set_scheme(b, True)
                b.navigate(srv.url("/dark.html", "plain.test"))
                b.js(tone.RUN_CONTENT, self.content_js)
                self.tone_is(b, "dark")
                self.block_is(b, "commit", "veil")


if __name__ == "__main__":
    unittest.main()

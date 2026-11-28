"""End-to-end: text read on what it really sits on. In a real headless
Firefox (and LibreWolf with BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_readable.py' -v

On plain.test, the page's own background cleared by the generic style (the
glass at 0.7 under it):

- /caption.html, light theme: a figure in display: table, painting a light
  grey, its caption in display: table-caption (Wikipedia's figures). The
  table's fill is not painted under its caption: the caption's blue link
  sits on the glass (over a dark wallpaper, under 4.5:1) and is shaded
  (INK "soft"), as a link on the glass is.
- /button.html, light and dark theme: a button in a mid violet with a white
  label (3.2:1, Galaxus's "Sign in"): the label on its fill under 4.5:1,
  though on the far side of it, gets INK "soft", the fill kept.
- /menu.html, dark theme: a page in its own dark colours, a white menu in
  its sticky header (a floating layer, veiled dark) over a white section,
  its links a light grey: the dark veil over that white shows mid grey,
  the links (3.7:1 there) are lifted (INK "soft").
- /faded.html, dark theme: a text at opacity 0.6 on the dark glass: even
  white does not read 4.5:1 there, its opacity is raised (ATTR_UNFADE) just
  enough; a line at 0.9 keeps its opacity.
- /caption.html, both themes: a selection with the browser's default
  colours gets the readable ones of the style (SELECTION_FILL, white).
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
GENERIC_CSS = ("html, body, header, main, section { background-color: transparent !important;"
               " background: none !important; border: none !important; box-shadow: none !important; }\n")
TEXT = "<p>" + "Some text on the page, read on the glass. " * 4 + "</p>"
HEAD = ('<!doctype html><html><head><meta charset="utf-8"><style>'
        "html{background:%(page)s} body{margin:0;color:%(text)s;font:16px/1.5 sans-serif} main{padding:0 24px}"
        "%(style)s</style></head><body>")
LIGHT = {"page": "rgb(255,255,255)", "text": "rgb(32,33,34)"}
DARK = {"page": "rgb(13,17,23)", "text": "rgb(230,237,243)"}
PHOTO = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='120'>"
         "<rect width='150' height='120' fill='orange'/><rect x='150' width='150' height='120' fill='teal'/></svg>")
CAPTION_PAGE = (HEAD % dict(LIGHT, style="figure{display:table;background:rgb(248,249,250);margin:0;padding:3px}"
                            "figcaption{display:table-caption;caption-side:bottom;padding:4px;background:rgba(255,255,255,0.35)}"
                            "a{color:rgb(51,102,204)}")
                + "<main><h1>Glass</h1>" + TEXT * 2
                + '<figure><img width="300" height="120" alt="" src="' + PHOTO + '">'
                + '<figcaption>Microscopically, a <a id="cap" href="#c">single crystal</a> has atoms.</figcaption>'
                + "</figure>" + TEXT * 8 + "</main></body></html>")
BUTTON_STYLE = ("#go{background:rgb(175,121,212);color:rgb(255,255,255);border:0;border-radius:4px;"
                "padding:8px 16px;font:16px sans-serif}")
BUTTON_BODY = '<main><h1>A shop</h1><button id="go">Sign in</button>' + TEXT * 10 + "</main></body></html>"
MENU_PAGE = (HEAD % dict(DARK, style="header{position:sticky;top:0;z-index:10;background:rgb(17,22,29);"
                         "display:flex;gap:20px;padding:14px 24px} header a{color:rgb(201,209,217)}"
                         ".hov{position:relative} .menu{position:absolute;top:28px;left:0;width:220px;"
                         "background:#fff;padding:8px;z-index:20} .menu a{display:block;padding:4px 6px}"
                         ".late{background:#fff;padding:24px;color:#000}")
             + '<header><b>Dyn</b><span class="hov"><a href="#p">Products</a><div class="menu" id="menu">'
             + '<a href="#h1">Hover item one</a><a id="item" href="#h3">Hover item three</a></div></span>'
             + '<a href="#x">About</a></header><main><div class="late"><h2>Late section</h2>'
             + "<p>Dark text on white.</p></div>" + TEXT * 10 + "</main></body></html>")
FADED_PAGE = (HEAD % dict(DARK, style=".op6{opacity:0.6;color:#333} .op9{opacity:0.9}")
              + '<main><h1>Faded</h1><p class="op6" id="op6">Text #333 at opacity 0.6 on the page.</p>'
              + '<p class="op9" id="op9">Text at opacity 0.9 on the page.</p>' + TEXT * 10 + "</main></body></html>")
# the passes after the marks: long enough for markInk to have run again
PASSES_S = 2.5
INK_OF = "return document.getElementById(arguments[0]).getAttribute(arguments[1]);"
SELECTION_OF = ("const p = document.querySelector('p'); const r = document.createRange(); r.selectNodeContents(p);"
                "getSelection().removeAllRanges(); getSelection().addRange(r);"
                "const s = getComputedStyle(p, '::selection'); return [s.backgroundColor, s.color];")


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.7, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ReadableE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        with open(os.path.join(tone.REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()

    def test_readable(self):
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
        time.sleep(PASSES_S)

    def check(self, binary):
        routes = {"/caption.html": CAPTION_PAGE,
                  "/light-button.html": HEAD % dict(LIGHT, style=BUTTON_STYLE) + BUTTON_BODY,
                  "/dark-button.html": HEAD % dict(DARK, style=BUTTON_STYLE) + BUTTON_BODY,
                  "/menu.html": MENU_PAGE, "/faded.html": FADED_PAGE}
        routes = {k: ("text/html; charset=utf-8", v.encode("utf-8")) for k, v in routes.items()}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            url = lambda path: srv.url(path, "plain.test")  # noqa: E731
            with self.subTest(page="/caption.html"):
                self.open(b, url("/caption.html"), False)
                self.assertEqual(b.js(INK_OF, "cap", bg.ATTR_INK), "soft")
                self.assertEqual(b.js(SELECTION_OF), [bg.SELECTION_FILL, "rgb(255, 255, 255)"])
            for dark in (False, True):
                with self.subTest(page="/button.html", dark=dark):
                    self.open(b, url("/dark-button.html" if dark else "/light-button.html"), dark)
                    self.assertEqual(b.js(INK_OF, "go", bg.ATTR_INK), "soft")
                    self.assertEqual(b.css("#go", "background-color")["background-color"], "rgb(175, 121, 212)")
                    if dark:
                        self.assertEqual(b.js(SELECTION_OF), [bg.SELECTION_FILL, "rgb(255, 255, 255)"])
            with self.subTest(page="/menu.html"):
                self.open(b, url("/menu.html"), True)
                self.assertIsNotNone(b.js(INK_OF, "menu", bg.ATTR_BAR), "the menu is not veiled")
                self.assertEqual(b.js(INK_OF, "item", bg.ATTR_INK), "soft")
            with self.subTest(page="/faded.html"):
                self.open(b, url("/faded.html"), True)
                self.assertIsNotNone(b.js(INK_OF, "op6", bg.ATTR_UNFADE))
                self.assertGreater(float(b.css("#op6", "opacity")["opacity"]), 0.6)
                self.assertIsNone(b.js(INK_OF, "op9", bg.ATTR_UNFADE))
                self.assertEqual(b.css("#op9", "opacity")["opacity"], "0.9")


if __name__ == "__main__":
    unittest.main()

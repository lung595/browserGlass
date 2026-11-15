"""End-to-end: the page layers the companion add-on marks (liveControl). The
lowest layer that paints the background of a page whose root and body are
see-through (a fixed full-window container, as in Jellyfin) becomes glass;
a navigation bar fixed or stuck along an edge of the window (a header, a
sidebar), whatever its own colours, gets a light veil of the DMS surface (35 %) over a strong blur.
In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_layers.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked:
  - the fixed background container is marked and see-through, a card over
    it is neither; the fixed header is marked, in the dark surface (a dark
    page), under a dark theme and a light one;
  - a fixed left sidebar with its own colour is marked too;
  - a background rendered late inside an existing element (as an Angular
    app does) is marked once it is there;
  - a sticky nav below a hero is left alone until it sticks to the top,
    marked while it is, and left alone again back at the top;
  - in a web app's shell (a page that does not scroll, a pane scrolls
    inside), the sidebar and the header in the flow are marked, the whole
    sidebar and not a list inside it, the pane is not; once the page itself
    scrolls, they are left alone;
  - short rows of links in the shell's pane, the one cut by the bottom edge
    included, are left alone, before and after the pane scrolls;
  - in a page that does not scroll, a side panel showing a picture and a
    plain block along an edge (no link, no nav role) are left alone;
  - a header in the flow of a page whose body is fixed to lock its scroll
    (a dialog open) is left alone.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
CANVAS, BAR = bg.ATTR_CANVAS, bg.ATTR_BAR
DARK_SURFACE = "rgba(%d, %d, %d, 0.35)" % bg.surface_rgb(None, "dark")
BLUR = bg.NAV_BAR_BLUR

STYLE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><style>
html, body {margin:0; background:rgb(16,16,16); color:rgb(235,235,235)}
#long {height:300vh}
"""
# A single-page app: a fixed full-window background under the content, a
# fixed header left see-through (as the generic style leaves a <header>;
# these stylesheets have no site styles).
APP_PAGE = STYLE + """
#bg {position:fixed; inset:0; background:rgb(16,16,16); z-index:-1}
header {position:fixed; top:0; left:0; right:0; height:50px; background:transparent; z-index:2}
#card {background:rgb(40,40,40); width:300px; height:100px; margin-top:80px}
#side {position:fixed; top:50px; bottom:0; left:0; width:180px; background:rgb(60,30,30)}
</style></head><body><div id="bg"></div><header id="bar">Bar</header>
<aside id="side">Side</aside>
<div id="card">Card</div><div id="long">""" + dk.TEXT + """</div></body></html>"""
# An app rendered late: its background wrapper appears after load inside an
# element that was already there.
LATE_PAGE = STYLE + """
html, body {background:transparent}
</style></head><body><div id="app"></div></body></html>"""
LATE = ("const w = document.createElement('div'); w.id = 'late';"
        "w.style = 'background:rgb(16,16,16); min-height:100vh';"
        "w.textContent = 'Late'; document.getElementById('app').append(w);")
# A see-through sticky <nav> below a hero.
STICKY_PAGE = STYLE + """
#hero {height:300px}
nav {position:sticky; top:0; height:60px; background:rgba(32,32,32,0.2)}
</style></head><body><div id="hero">Hero</div><nav id="bar">Nav</nav>
<div id="long">""" + dk.TEXT + """</div></body></html>"""

# A web app's shell: the page does not scroll, a pane does; the sidebar and
# the header are in the flow (neither fixed nor sticky).
SHELL_PAGE = STYLE + """
html, body {height:100%; overflow:hidden}
#shell {display:flex; height:100%}
#side {width:220px; background:rgb(60,30,30)}
#list {height:90%; padding-left:0}
#right {flex:1; display:flex; flex-direction:column; min-width:0}
#top {height:56px; background:rgb(30,30,60)}
#pane {flex:1; overflow:auto; background:rgb(20,20,20)}
#pane div {height:300vh}
</style></head><body><div id="shell"><nav id="side"><ul id="list"><li>Inbox</li></ul></nav>
<div id="right"><header id="top">Search</header><main id="pane"><div>Mail</div></main></div>
</div></body></html>"""

# The shell with a list of short rows of links in its pane.
ROWS_PAGE = SHELL_PAGE.replace("#pane div {height:300vh}", ".row {height:40px}").replace(
    "<div>Mail</div>", "".join('<div class="row" id="r%d"><a href="#">Mail %d</a></div>' % (i, i)
                               for i in range(80)))
# A sign-in page that fits the window: a picture panel, a form, a plain
# block, and a fixed bottom bar.
SPLIT_PAGE = STYLE + """
html, body {height:100%; overflow:hidden}
#split {display:flex; height:100%}
#photo {width:35%; background:rgb(40,60,80) linear-gradient(rgb(90,60,30), rgb(30,60,90))}
#form {flex:1}
#plain {width:30%; background:rgb(50,50,50)}
#fixbar {position:fixed; left:0; right:0; bottom:0; height:50px; background:rgb(30,30,30)}
</style></head><body><div id="split"><aside id="photo"></aside>
<div id="form"><a href="#">Sign in</a></div><div id="plain">Plain</div></div>
<div id="fixbar">Bar</div></body></html>"""
# A page with a header in the flow, its scroll then locked by fixing the
# body (as a dialog does).
LOCK_PAGE = STYLE + """
#head {height:56px; background:rgb(30,30,60)}
</style></head><body><header id="head"><a href="#">Home</a></header>
<div id="long">""" + dk.TEXT + """</div></body></html>"""
LOCK = ("document.body.style = 'position:fixed; top:0; left:0; right:0';"
        "const s = document.createElement('div'); s.id = 'lockside';"
        "s.style = 'position:fixed; top:0; bottom:0; right:0; width:200px; background:rgb(30,30,30)';"
        "document.body.append(s);")
ROWS_MARKED = "return [...document.querySelectorAll('.row')].filter((e) => e.hasAttribute(arguments[0])).length > 0;"

BAR_COLOR = "return getComputedStyle(document.getElementById('bar')).backgroundColor;"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LayersE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_layers(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def marked(self, b, element_id, attr):
        return b.js(dk.MARKED, element_id, attr)

    def check(self, binary):
        routes = {"/a.html": ("text/html; charset=utf-8", APP_PAGE.encode("utf-8")),
                  "/s.html": ("text/html; charset=utf-8", STICKY_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LATE_PAGE.encode("utf-8")),
                  "/shell.html": ("text/html; charset=utf-8", SHELL_PAGE.encode("utf-8")),
                  "/rows.html": ("text/html; charset=utf-8", ROWS_PAGE.encode("utf-8")),
                  "/split.html": ("text/html; charset=utf-8", SPLIT_PAGE.encode("utf-8")),
                  "/lock.html": ("text/html; charset=utf-8", LOCK_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/a.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bg", CANVAS), "background not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('bg')).backgroundColor;"),
                             "rgba(0, 0, 0, 0)")
            self.assertFalse(self.marked(b, "card", CANVAS))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('card')).backgroundColor;"),
                             "rgb(40, 40, 40)")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "header not marked")
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('bar')).backdropFilter;"),
                             BLUR)
            self.assertFalse(self.marked(b, "card", BAR))
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR), "sidebar not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('side')).backgroundColor;"),
                             DARK_SURFACE)
            # a dark page keeps a dark header under a light theme
            tone.set_scheme(b, False)
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            tone.set_scheme(b, True)

            b.navigate(srv.url("/l.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            b.js("return new Promise((resolve) => setTimeout(resolve, 300));")
            b.js(LATE)
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "late", CANVAS), "late background not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('late')).backgroundColor;"),
                             "rgba(0, 0, 0, 0)")

            b.navigate(srv.url("/s.html", "plain.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            self.assertFalse(self.marked(b, "bar", BAR), "marked below the hero")
            self.assertEqual(b.js(BAR_COLOR), "rgba(32, 32, 32, 0.2)")
            b.js("window.scrollTo(0, 600);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "stuck nav not marked")
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            b.js("window.scrollTo(0, 0);")
            self.assertTrue(b.wait_for("return !document.getElementById('bar').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, BAR), "still marked back at the top")

            b.navigate(srv.url("/shell.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR), "shell sidebar not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "top", BAR), "shell header not marked")
            for element_id in ("side", "top"):
                self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;",
                                      element_id), DARK_SURFACE)
                self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0])).backdropFilter;",
                                      element_id), BLUR)
            self.assertFalse(self.marked(b, "list", BAR), "a list inside the sidebar marked")
            self.assertFalse(self.marked(b, "pane", BAR), "the scrolling pane marked")
            b.js("document.documentElement.style.overflow = 'auto'; document.body.style.overflow = 'visible';"
                 "document.body.style.height = 'auto'; document.getElementById('shell').style.height = '300vh';")
            self.assertTrue(b.wait_for("return !document.getElementById('side').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, BAR), "sidebar still marked once the page scrolls")

            b.navigate(srv.url("/rows.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR), "shell sidebar not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "top", BAR), "shell header not marked")
            self.assertFalse(b.wait_for(ROWS_MARKED, 2.0, BAR), "a row of the pane marked")
            b.js("document.getElementById('pane').scrollTop = 517;")
            self.assertFalse(b.wait_for(ROWS_MARKED, 2.0, BAR), "a row of the pane marked once it scrolls")

            b.navigate(srv.url("/split.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "fixbar", BAR), "fixed bottom bar not marked")
            self.assertFalse(self.marked(b, "photo", BAR), "the picture panel marked")
            self.assertFalse(self.marked(b, "plain", BAR), "a plain block marked")
            self.assertNotEqual(b.js("return getComputedStyle(document.getElementById('photo')).backgroundImage;"),
                                "none")

            b.navigate(srv.url("/lock.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            b.js(LOCK)
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "lockside", BAR), "fixed sidebar not marked")
            self.assertFalse(self.marked(b, "head", BAR), "a header marked under a scroll lock")


if __name__ == "__main__":
    unittest.main()

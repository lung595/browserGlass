"""End-to-end: the page layers the companion add-on marks (liveControl). The
lowest layer that paints the background of a page whose root and body are
see-through (a fixed full-window container, as in Jellyfin) becomes glass;
a navigation bar fixed or stuck along an edge of the window (a header, a
sidebar) with a background of its own gets a light veil of the DMS surface
(35 %) over a strong blur; text left without contrast on the glass gets a
readable colour.
In a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_layers.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked:
  - the fixed background container is marked and see-through, a card over
    it is neither; the fixed header is marked, in the dark surface (a dark
    page), under a dark theme and a light one;
  - a fixed left sidebar with its own colour is marked too, a see-through
    fixed bar is not;
  - a tall see-through fixed header is left alone over nothing, and marked
    once content lies under its lower row only (its top row a notice); a
    thin see-through strip down the right edge over the content is not;
  - a background rendered late inside an existing element (as an Angular
    app does) is marked once it is there;
  - a sticky nav below a hero is left alone until it sticks to the top,
    marked while it is, and left alone again back at the top;
  - in a web app's shell (a page that does not scroll, a pane scrolls
    inside), the sidebar and the header in the flow keep their own look,
    and so do the short rows of links in the pane (1.3.1);
  - in a page that does not scroll, a side panel showing a picture and a
    plain block along an edge (no link, no nav role) are left alone;
  - a header in the flow of a page whose body is fixed to lock its scroll
    (a dialog open) is left alone;
  - black text straight on the root of a dark page under a light theme
    (the dark tint at 88 % over the light glass, mixed in sRGB) is inked;
  - dark text straight on the dark glass gets the light surface colour,
    the same text on its own white card is left alone; so is dark text
    over a light face at opacity 0 (a hover state) or a gradient underline
    2px high, but not over a full gradient; text with a colour transition
    keeps its mark from pass to pass, its style attribute put back;
  - a black logo blended with multiply on the dark glass is shown on a
    white tile (not blended, not inverted), the same logo on its own
    white card is left alone;
  - page columns narrower than the window (test_columns): a feed centred
    in it, in the page's dark colour or white on a light page, and a dark
    side panel down to the bottom are marked, a card on the feed is not;
    the feed's sticky title row (its colour painted by a child) is a bar,
    its child filled, its ::after strip in the page's colour see-through;
    an app's surface right of its menu, down to near the bottom, is
    marked, its panels are not, under a light theme too (the root under
    the dark tint); the app's see-through menu, its first child a scrim at
    opacity 0, is no bar; a menu row across the window,
    dark or light, is marked, a coloured band under it is not; a coloured
    column, a column filled by a player, a light column on a dark page and
    a short card are left alone.
"""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = dk.bg
CANVAS, BAR = bg.ATTR_CANVAS, bg.ATTR_BAR
DARK_SURFACE = "rgba(%d, %d, %d, 0.65)" % bg.surface_rgb(None, "dark")
LIGHT_INK = "rgb(%d, %d, %d)" % bg.surface_rgb(None, "light")
BLUR = bg.NAV_BAR_BLUR

STYLE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><style>
html, body {margin:0; background:rgb(16,16,16); color:rgb(235,235,235)}
#long {height:300vh}
"""
# A single-page app: a fixed full-window background under the content, a
# fixed header with its own colour, a see-through fixed bottom bar over
# the text. In the
# header an empty scrim and a label painted with the page's colour, in the
# sidebar a panel of that colour covering it.
APP_PAGE = STYLE + """
#bg {position:fixed; inset:0; background:rgb(16,16,16); z-index:-1}
header {position:fixed; top:0; left:0; right:0; height:50px; background:rgb(24,24,24); z-index:2}
#ghost {position:fixed; bottom:0; left:0; right:0; height:40px; background:transparent}
#card {background:rgb(40,40,40); width:300px; height:100px; margin-top:80px}
#side {position:fixed; top:50px; bottom:0; left:0; width:180px; background:rgb(60,30,30)}
#scrim {display:block; width:60px; height:10px; background:rgb(16,16,16)}
#chip, #panel {background:rgb(16,16,16)}
#panel {position:absolute; inset:0}
</style></head><body><div id="bg"></div><header id="bar">Bar <span id="scrim"></span><b id="chip">Chip</b></header>
<aside id="side"><div id="panel">Side</div></aside><footer id="ghost">Ghost</footer>
<div id="card">Card</div><div id="long">""" + dk.TEXT + """</div></body></html>"""
# An app rendered late: its background wrapper appears after load inside an
# element that was already there.
LATE_PAGE = STYLE + """
html, body {background:transparent}
</style></head><body><div id="app"></div></body></html>"""
LATE = ("const w = document.createElement('div'); w.id = 'late';"
        "w.style = 'background:rgb(16,16,16); min-height:100vh';"
        "w.textContent = 'Late'; document.getElementById('app').append(w);")
# A sticky <nav> with its own colour below a hero.
STICKY_PAGE = STYLE + """
#hero {height:300px}
nav {position:sticky; top:0; height:60px; background:rgb(32,32,32)}
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
# Dark text on see-through layers (the glass behind it), and on a white card;
# a black logo blended with multiply on each. Buttons whose light face is a
# ::before, or a layer of children under the label, and text over a
# picture laid under it. Dark text the light faces do not hold: a ::before
# at opacity 0 (a hover state), a gradient 2px high (an underline); text
# with a colour transition (its mark kept, not taken off and set in turn);
# text on a full gradient, a picture. Light text drawn with a gradient
# clipped to it (its fill transparent): its stops are its colours.
LOGO = ("<img id=\"%s\" width=\"40\" height=\"20\" style=\"mix-blend-mode:multiply\" src=\"data:image/svg+xml,"
        "%%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='20'%%3E%%3Crect width='40' height='20'/%%3E%%3C/svg%%3E\">")
INK_PAGE = STYLE + """
html, body {background:transparent}
#dim, #oncard, #onpic {color:rgb(20,20,20)}
#card {background:rgb(255,255,255)}
.pill {position:relative; isolation:isolate; background:transparent; border:0; padding:8px; color:rgb(30,30,30)}
.pill.face::before {content:""; position:absolute; inset:0; z-index:-1; border-radius:8px; background:rgb(240,240,240)}
.under {position:absolute; inset:0; z-index:-1} .under span {position:absolute; inset:0; background:rgb(239,239,239)}
.pill.state::before {content:""; position:absolute; inset:0; z-index:-1; background:rgb(240,240,240); opacity:0}
#cta, #fade, #ongrad {color:rgb(20,20,20)}
#cta {background-image:linear-gradient(rgb(200,200,255), rgb(200,200,255)); background-size:400% 2px;
  background-repeat:no-repeat; background-position:0 100%}
#fade {transition:color 0.2s linear}
#ongrad {background-image:linear-gradient(rgb(250,250,250), rgb(240,240,240))}
#clip {color:transparent; -webkit-text-fill-color:transparent; background-clip:text;
  background-image:linear-gradient(90deg, rgb(255,214,125) 60%, rgb(241,180,52))}
</style></head><body><p id="dim">Notice</p>""" + LOGO % "logo" + """
<div id="card"><p id="oncard">Card</p>""" + LOGO % "cardlogo" + """</div>
<button class="pill face"><span id="pill">Upgrade</span></button>
<button class="pill"><span class="under"><span></span></span><span id="layered">Try</span></button>
<div style="position:relative"><img style="position:absolute; inset:0; width:100%; height:100%" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E"><p id="onpic">Hero</p></div>
<button class="pill state"><span id="ghost">New chat</span></button>
<p><a id="cta" href="#">Download</a></p><p id="fade" style="font-weight:bold">Fading</p><p id="ongrad">Gradient</p>
<p>Plain <span id="clip">highlighted</span></p>
</body></html>"""
INK = bg.ATTR_INK
TILE = bg.ATTR_TILE
# A dark page (light text) with one black line straight on the root: under
# a light theme the root is the dark tint at 88 % over the light glass,
# which the browser mixes in sRGB, so the black line sits on dark grey.
INK_ROOT_PAGE = STYLE + """
html, body {background:transparent} body {color:rgb(235,235,235)}
#black {color:rgb(0,0,0)}
</style></head><body>""" + "<p>Light text of a dark page.</p>" * 8 + """
<p id="black">Black</p></body></html>"""

# A cookie banner: a see-through fixed wrapper over the page's text, and in
# it a large opaque form; a modal fixed itself. Neither is the page's
# background.
BANNER_PAGE = STYLE + """
#wrap {position:fixed; inset:0; background:transparent; z-index:5}
#consent {position:absolute; inset:5% 2%; background:rgb(40,40,60)}
#modal {position:fixed; inset:0; background:rgb(50,40,40); z-index:6; display:none}
</style></head><body><div id="long">""" + dk.TEXT + """</div>
<div id="wrap"><form id="consent">Cookies</form></div><div id="modal">Modal</div></body></html>"""
# A tall see-through fixed header: its top row a notice with a colour of
# its own (a country redirect), its links in the row below; the content
# starts below the header, then is scrolled under the row of links only.
# Down the right edge, a thin see-through strip over the content (the
# marks of a find in the page): no bar.
TALL_PAGE = STYLE + """
#tall {position:fixed; top:0; left:0; right:0; height:110px; background:transparent; z-index:2}
#marks {position:fixed; top:0; bottom:0; right:0; width:15px; background:transparent; z-index:3}
#notice {height:60px; background:rgb(40,40,60)}
#cells {display:flex; margin-top:170px}
#cells div {flex:1; height:200px; margin:0 2px; background:rgb(40,40,40)}
</style></head><body><header id="tall"><div id="notice">Notice</div><a href="#">Home</a></header>
<div id="cells">""" + "<div>Cell</div>" * 5 + """</div><div id="long">""" + dk.TEXT + """</div>
<div id="marks"></div></body></html>"""
BAR_COLOR = "return getComputedStyle(document.getElementById('bar')).backgroundColor;"

# A feed centred in the window (Mastodon): a sticky menu on the left, its
# lower panel down to the bottom in a darker colour; the feed column in
# the page's colour, its sticky title row see-through, painted by the box
# inside it, a strip of the page's colour under its ::after (Mastodon); a
# card on the feed.
COLUMN_PAGE = STYLE + """
html, body {background:transparent}
#cols {display:flex; justify-content:center; align-items:flex-start}
#nav {position:sticky; top:0; width:22vw; height:100vh; display:flex; flex-direction:column}
#links {height:20vh} #navfoot {flex:1; background:rgb(7,6,14)}
#feed {width:44vw; min-height:300vh; background:rgb(21,21,30)}
#head {position:sticky; top:0; padding-top:4px; height:49px} #headbox {height:49px; background:rgb(21,21,30)}
#head::after {content:""; position:absolute; left:1px; right:1px; bottom:0; height:8px; z-index:-1;
  background:rgb(21,21,30)}
#post {height:120px; margin:16px; background:rgb(40,40,52)}
#aside {width:22vw}
</style></head><body><div id="cols"><nav id="nav"><div id="links"><a href="#">Explore</a></div>
<footer id="navfoot">About this server</footer></nav>
<main id="feed"><header id="head"><div id="headbox">Explore</div></header>
<div id="post">A post</div>""" + dk.TEXT * 4 + """</main><div id="aside">Links</div></div></body></html>"""
# The same feed on a light page: dark text, a white column.
LIGHT_COLUMN_PAGE = (COLUMN_PAGE.replace("color:rgb(235,235,235)", "color:rgb(20,20,20)")
                     .replace("rgb(21,21,30)", "rgb(255,255,255)").replace("rgb(7,6,14)", "rgb(245,245,248)")
                     .replace("rgb(40,40,52)", "rgb(235,235,240)"))
# An app's surface (Grafana): a see-through fixed top bar and menu, the
# surface right of the menu down to 4px above the bottom, with a border
# and round corners; panels on it. The menu's first child is a drawer's
# scrim faded out (YouTube's guide): opacity 0.
SURFACE_PAGE = STYLE + """
html, body {height:100%; overflow:hidden; background:transparent}
#top {position:fixed; top:0; left:0; right:0; height:48px}
#menu {position:fixed; top:48px; left:0; bottom:0; width:23vw}
#scrim {position:absolute; inset:0; background:rgba(0,0,0,0.5); opacity:0}
#surface {position:absolute; top:48px; left:23vw; right:4px; bottom:4px; overflow:auto;
  background:rgb(9,11,15); border:1px solid rgb(60,60,70); border-radius:8px}
.panel {height:30vh; margin:16px; background:rgb(24,27,31)}
</style></head><body><header id="top"><a href="#">Home</a></header><nav id="menu"><div id="scrim"></div><a href="#">Dashboards</a></nav>
<div id="surface"><div class="panel" id="panel">Panel</div><div class="panel">Panel</div></div></body></html>"""
# A site's second menu row (Gitea): a band across the window under its
# see-through header, in a plain colour near the page's; a coloured band
# under it is left alone.
BAND_PAGE = STYLE + """
html, body {background:transparent}
#top {height:49px} #band {height:45px; background:rgb(26,27,30)} #hero {height:150px; background:rgb(40,60,120)}
</style></head><body><header id="top"><a href="#">Explore</a></header><nav id="band"><a href="#">Repositories</a></nav>
<div id="hero">Welcome</div>""" + dk.TEXT + """</body></html>"""
LIGHT_BAND_PAGE = (BAND_PAGE.replace("color:rgb(235,235,235)", "color:rgb(20,20,20)")
                   .replace("rgb(26,27,30)", "rgb(249,250,251)"))
# Tall columns that are not the page's background: a coloured band, a
# player's black area filled by its canvas, a light column on a dark page,
# a card that does not reach the bottom.
NOT_COLUMN_PAGE = STYLE + """
html, body {height:100%; overflow:hidden; background:transparent}
#row {display:flex; height:100%}
#row > div {width:20vw}
#hue {background:rgb(40,60,120)} #player {background:rgb(0,0,0)} #player canvas {width:100%; height:100%}
#pale {background:rgb(230,230,230); color:rgb(20,20,20)} #short {height:50vh; margin-top:10vh; background:rgb(30,30,36)}
</style></head><body><div id="row"><div id="hue">Hero</div><div id="player"><canvas></canvas></div>
<div id="pale">Pale</div><div id="short">Card</div><div>Text of the page</div></div></body></html>"""


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

    def test_columns(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_columns(binary)

    def bg_of(self, b, element_id):
        return b.js("return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;", element_id)

    def check_columns(self, binary):
        routes = {"/c.html": ("text/html; charset=utf-8", COLUMN_PAGE.encode("utf-8")),
                  "/cl.html": ("text/html; charset=utf-8", LIGHT_COLUMN_PAGE.encode("utf-8")),
                  "/surface.html": ("text/html; charset=utf-8", SURFACE_PAGE.encode("utf-8")),
                  "/not.html": ("text/html; charset=utf-8", NOT_COLUMN_PAGE.encode("utf-8")),
                  "/band.html": ("text/html; charset=utf-8", BAND_PAGE.encode("utf-8")),
                  "/bandl.html": ("text/html; charset=utf-8", LIGHT_BAND_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            for page, card in (("/c.html", "rgb(40, 40, 52)"), ("/cl.html", "rgb(235, 235, 240)")):
                b.navigate(srv.url(page, "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "feed", CANVAS),
                                "a centred feed column not marked (%s)" % page)
                self.assertEqual(self.bg_of(b, "feed"), "rgba(0, 0, 0, 0)")
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "navfoot", CANVAS),
                                "a side panel down to the bottom not marked (%s)" % page)
                self.assertFalse(self.marked(b, "post", CANVAS), "a card on the feed marked")
                self.assertEqual(self.bg_of(b, "post"), card)
                # the feed's title row: a bar across the column, the box
                # painting it see-through
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR),
                                "the feed's sticky title row not marked (%s)" % page)
                self.assertTrue(b.wait_for("return document.getElementById('headbox')"
                                           ".getAttribute(arguments[0]) === 'fill';",
                                           mn.WAIT_TIMEOUT, CANVAS), "the title row's box not filled")
                self.assertEqual(self.bg_of(b, "headbox"), "rgba(0, 0, 0, 0)")
                # its ::after strip in the page's colour: see-through too
                self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('head'), '::after')"
                                           ".backgroundColor === 'rgba(0, 0, 0, 0)';", mn.WAIT_TIMEOUT),
                                "the title row's ::after strip left in the page's colour (%s)" % page)

            # the surface under a dark theme, then under a light one: the
            # dark app's root then carries the dark tint, glass as well
            for dark in (True, False):
                tone.set_scheme(b, dark)
                b.navigate(srv.url("/surface.html", "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "surface", CANVAS),
                                "an app's surface not marked (dark theme: %s)" % dark)
                self.assertEqual(self.bg_of(b, "surface"), "rgba(0, 0, 0, 0)")
                self.assertFalse(self.marked(b, "panel", CANVAS), "a panel on the surface marked")
                self.assertEqual(self.bg_of(b, "panel"), "rgb(24, 27, 31)")
                # the menu over nothing, its scrim at opacity 0: no bar
                self.assertFalse(b.wait_for(dk.MARKED, 2.0, "menu", BAR), "a menu backed by a faded scrim marked")
            tone.set_scheme(b, True)

            for page in ("/band.html", "/bandl.html"):
                b.navigate(srv.url(page, "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "band", CANVAS),
                                "a menu row across the window not marked (%s)" % page)
                self.assertEqual(self.bg_of(b, "band"), "rgba(0, 0, 0, 0)")
                self.assertFalse(self.marked(b, "hero", CANVAS), "a coloured band marked")
                self.assertEqual(self.bg_of(b, "hero"), "rgb(40, 60, 120)")

            b.navigate(srv.url("/not.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE))
            self.assertFalse(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']');",
                                        2.0, CANVAS), "a coloured, player, light or short column marked")

    def check(self, binary):
        routes = {"/a.html": ("text/html; charset=utf-8", APP_PAGE.encode("utf-8")),
                  "/s.html": ("text/html; charset=utf-8", STICKY_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LATE_PAGE.encode("utf-8")),
                  "/shell.html": ("text/html; charset=utf-8", SHELL_PAGE.encode("utf-8")),
                  "/rows.html": ("text/html; charset=utf-8", ROWS_PAGE.encode("utf-8")),
                  "/split.html": ("text/html; charset=utf-8", SPLIT_PAGE.encode("utf-8")),
                  "/lock.html": ("text/html; charset=utf-8", LOCK_PAGE.encode("utf-8")),
                  "/ink.html": ("text/html; charset=utf-8", INK_PAGE.encode("utf-8")),
                  "/inkroot.html": ("text/html; charset=utf-8", INK_ROOT_PAGE.encode("utf-8")),
                  "/banner.html": ("text/html; charset=utf-8", BANNER_PAGE.encode("utf-8")),
                  "/tall.html": ("text/html; charset=utf-8", TALL_PAGE.encode("utf-8"))}
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
            # the filter the blur refers to: without it, no blur at all
            self.assertEqual(b.js("return document.querySelectorAll('filter#browserglass-veil feFlood + feMerge').length;"),
                             1)
            self.assertFalse(self.marked(b, "card", BAR))
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR), "sidebar not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('side')).backgroundColor;"),
                             DARK_SURFACE)
            # see-through, but over the page's text: its own text would sit on it
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "ghost", BAR),
                            "a see-through bar over text not marked")
            # the page's colour inside the bars: the scrim and the covering
            # panel go see-through, a label keeps its colour
            for fill in ("scrim", "panel"):
                self.assertTrue(b.wait_for("return document.getElementById(arguments[0])"
                                           ".getAttribute(arguments[1]) === 'fill';",
                                           mn.WAIT_TIMEOUT, fill, CANVAS), fill + " not filled")
                self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0]))"
                                      ".backgroundColor;", fill), "rgba(0, 0, 0, 0)")
            self.assertFalse(self.marked(b, "chip", CANVAS), "a label in a bar filled")
            # a dark page keeps a dark header under a light theme
            tone.set_scheme(b, False)
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            tone.set_scheme(b, True)

            # a tall see-through header: left alone over nothing, marked once
            # content lies under its lower row only (its middle line on its
            # own notice)
            b.navigate(srv.url("/tall.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            self.assertFalse(b.wait_for(dk.MARKED, 2.0, "tall", BAR), "a see-through header over nothing marked")
            b.js("window.scrollTo(0, 110);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "tall", BAR),
                            "a tall see-through header over content under its lower row not marked")
            self.assertFalse(b.wait_for(dk.MARKED, 2.0, "marks", BAR), "a thin see-through strip marked")

            # a cookie banner over the text keeps its colour, and a modal
            b.navigate(srv.url("/banner.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            b.js("document.getElementById('modal').style.display = 'block'; window.dispatchEvent(new Event('resize'));")
            self.assertFalse(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']');",
                                        2.0, CANVAS), "a fixed layer over the text marked as the background")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('consent')).backgroundColor;"),
                             "rgb(40, 40, 60)")

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
            self.assertEqual(b.js(BAR_COLOR), "rgb(32, 32, 32)")
            b.js("window.scrollTo(0, 600);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "stuck nav not marked")
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            b.js("window.scrollTo(0, 0);")
            self.assertTrue(b.wait_for("return !document.getElementById('bar').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, BAR), "still marked back at the top")

            # an app shell's parts in the flow keep their own look
            for page in ("/shell.html", "/rows.html"):
                b.navigate(srv.url(page, "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                           mn.WAIT_TIMEOUT, tone.LIVE))
                self.assertFalse(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']');",
                                            2.0, BAR), "a part of the shell marked (%s)" % page)
                self.assertEqual(b.js("return getComputedStyle(document.getElementById('top')).backgroundColor;"),
                                 "rgb(30, 30, 60)")

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

            b.navigate(srv.url("/ink.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.getElementById('dim').getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, INK), "dark text on the glass not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('dim')).color;"), LIGHT_INK)
            self.assertFalse(self.marked(b, "oncard", INK), "text on its own white card marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('oncard')).color;"),
                             "rgb(20, 20, 20)")
            # the logo multiplied into the dark glass: on a white tile, not
            # blended (black on black) nor inverted
            self.assertTrue(b.wait_for("return document.getElementById('logo').getAttribute(arguments[0])"
                                       " === 'blend';", mn.WAIT_TIMEOUT, TILE),
                            "black logo on the glass not tiled")
            self.assertEqual(b.js("const s = getComputedStyle(document.getElementById('logo'));"
                                  "return [s.mixBlendMode, s.filter, s.backgroundColor];"),
                             ["normal", "none", "rgb(255, 255, 255)"])
            self.assertFalse(self.marked(b, "cardlogo", TILE), "logo on its own white card tiled")
            # a button whose light face is its ::before: its dark label keeps
            # its colour (white on white otherwise)
            self.assertFalse(self.marked(b, "pill", INK), "text on a light ::before face marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('pill')).color;"),
                             "rgb(30, 30, 30)")
            # its face a child layer under the label (the button see-through)
            self.assertFalse(self.marked(b, "layered", INK), "text on a light child face marked")
            # text over a picture: no guess
            self.assertFalse(self.marked(b, "onpic", INK), "text over a picture marked")
            self.assertFalse(self.marked(b, "ongrad", INK), "text over a full gradient marked")
            # a light face at opacity 0 holds no text; a thin gradient
            # underline is no picture
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "ghost", INK), "text over an opacity 0 face not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "cta", INK), "text over a gradient underline not marked")
            # light words drawn with a gradient clipped to them: marked dark
            # under a light theme (checked below); none here, light on dark
            self.assertFalse(self.marked(b, "clip", INK), "light gradient text on the dark glass marked")
            # a colour transition: the mark stays (each pass, from its
            # transitionend, would take it off and read the colour halfway)
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "fade", INK), "fading text not marked")
            seen = set()
            for _ in range(20):
                seen.add(b.js("return document.getElementById('fade').getAttribute(arguments[0]);", INK))
                time.sleep(0.1)
            self.assertEqual(seen, {"light"})
            self.assertEqual(b.js("return document.getElementById('fade').getAttribute('style');"), "font-weight:bold")

            # under a light theme, the light words drawn with a gradient
            # clipped to them: marked dark, the fill drawn over the gradient
            tone.set_scheme(b, False)
            b.navigate(srv.url("/ink.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.getElementById('clip').getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, INK), "light gradient text on the light glass not marked")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('clip')).webkitTextFillColor;"),
                             b.js("return getComputedStyle(document.getElementById('clip')).color;"))
            self.assertFalse(self.marked(b, "dim", INK), "dark text on the light glass marked")

            # a dark page under a light theme: the root's translucent tint
            # over the light glass, mixed as the browser mixes it (sRGB)
            tone.set_scheme(b, False)
            b.navigate(srv.url("/inkroot.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "dark page not measured dark")
            self.assertTrue(b.wait_for("return document.getElementById('black').getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, INK), "black text on the dark tint not marked")
            tone.set_scheme(b, True)


if __name__ == "__main__":
    unittest.main()

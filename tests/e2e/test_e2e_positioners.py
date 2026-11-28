"""End-to-end: the floating layers a site places through a see-through
positioner, or lays inside its header bar, get the bar's veil on their
painted panel; an empty positioner never keeps one. In a real headless
Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_positioners.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Checked on a light page under a light theme first, then on a dark page under
a dark theme and on a light page Dark Reader darkens (the dark runs keep
the same layers):
  - a popover in a fixed see-through positioner shaped as a sidebar
    (Galaxus' header popovers: the positioner at the window's right, taller
    than the panel, no pointer events), the panel in the flow of it: the
    panel is veiled, never the positioner;
  - the same positioner left empty while the page is inert under a search
    sheet (Galaxus' search): no veil on it (a ghost over the page);
  - the same, the positioner holding its popover closed (display:none,
    its text, buttons and icons still in the DOM; Galaxus' wish list once
    closed): no veil on it either;
  - a mega menu hanging from a header's nav, a see-through absolute
    wrapper around its painted list, in the list's flow (the French
    state's DSFR menus): the list is veiled, not the wrapper;
  - a menu laid within a tall bar's box over the bar's own text, the bar's
    nav holding hundreds of closed submenus first (python.org's header
    over its hero): the menu is veiled;
  - a painted panel of a menu laid beside the menu's box (python.org's
    side panel by its list): a veil of its own, the menu's stopping at its
    box;
  - a side drawer open over the page's fixed sidebar, a scrim between
    them: both are veiled, the sidebar's links never bare under the
    drawer's veil.
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
BAR = bg.ATTR_BAR

MARKED = "const e = document.getElementById(arguments[0]); return !!e && e.hasAttribute(arguments[1]);"
# the add-on's passes ran: the header got its veil
SETTLED = "return document.getElementById('head').hasAttribute(arguments[0]);"


def page(colors, body):
    return ("""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {position:sticky; top:0; z-index:60; height:48px; display:flex; gap:24px; align-items:center;
  background:%(page)s}
#long {height:300vh}
</style></head><body>%(body)s<div id="long">%(lorem)s</div></body></html>""" % dict(colors, body=body, lorem=dk.TEXT * 10))


HEAD = '<header id="head"><a href="#">Home</a> <a href="#">News</a></header>'
HIDDEN = "".join('<li style="display:none"><a href="#">Hidden entry %d</a></li>' % i for i in range(450))

# (name, body, [ids veiled], [ids not veiled])
CASES = [
    ("positioner", HEAD + """<div id="pos" style="position:fixed; top:64px; right:0; width:34vw; height:85vh;
  z-index:12; pointer-events:none"><div id="overlay" style="pointer-events:auto; height:316px;
  background:%(page)s"><p>Settings</p><p>Language</p><p>Comparison lists</p><p>Watch lists</p></div></div>""",
     ["overlay"], ["pos"]),
    ("ghost", HEAD.replace('id="head"', 'id="head" style="position:fixed; width:100%%"')
     + """<div id="app" inert style="padding-top:48px"><p>Search results behind the sheet</p></div>
<div id="pos" style="position:fixed; top:64px; right:0; width:34vw; height:85vh; z-index:12;
  pointer-events:none"><div id="overlay"></div></div>""", [], ["pos"]),
    ("closed", HEAD.replace('id="head"', 'id="head" style="position:fixed; width:100%%"')
     + """<div id="app" inert style="padding-top:48px"><p>Search results behind the sheet</p></div>
<div id="pos" style="position:fixed; top:64px; right:0; width:34vw; height:85vh;
  z-index:12; pointer-events:none"><div id="overlay" style="display:none; height:316px; background:%(page)s">
  <h2>Wish lists</h2><button>Close <svg width="16" height="16"><path d="M0 0L16 16"/></svg></button>
  <p>Click the heart symbol to add products.</p><button>Create a new list</button></div></div>""",
     [], ["pos", "overlay"]),
    ("dsfr", """<header id="head"><nav id="nav"><ul style="display:flex; gap:24px; margin:0; list-style:none">
  <li><a href="#">Home</a></li><li style="position:relative"><button aria-expanded="true"
  aria-controls="menu">Life events</button>
  <div id="menu" style="position:absolute; top:100%%; left:0; width:352px; z-index:3000;
  padding:0 16px 40px; box-sizing:border-box"><ul id="list" style="margin:0; height:448px;
  background:%(page)s; list-style:none"><li><a href="#">Moving house</a></li><li><a href="#">Having a child</a></li>
  <li><a href="#">Retiring</a></li></ul></div></li></ul></nav></header>""", ["list"], ["menu"]),
    ("longnav", HEAD + """<aside id="side" style="position:fixed; top:0; left:0; width:320px; height:100vh;
  z-index:70; background:%(page)s"><nav style="height:40px"><ul style="margin:0; list-style:none">
  <li style="position:relative"><a href="#">About</a>
  <div id="sub" style="position:absolute; top:64px; left:0; width:260px; z-index:10; background:%(card)s">
  <p>Applications</p><p>Quotes</p><p>Getting started</p><p>Help</p></div></li>""" + HIDDEN + """</ul></nav>
  <p style="margin-top:60px">Python is a programming language that lets you work quickly.</p>
  <p>Learn more about the language and its community.</p></aside>""", ["side", "sub"], []),
    ("beside", """<header id="head"><nav><ul style="display:flex; gap:24px; margin:0; list-style:none">
  <li><a href="#">Home</a></li><li style="position:relative"><a href="#">About</a>
  <ul id="sub" style="position:absolute; top:40px; left:0; width:229px; z-index:100; margin:0; padding:0;
  list-style:none; background:%(card)s"><li><a href="#">Applications</a></li><li><a href="#">Quotes</a></li>
  <li><a href="#">Getting started</a></li><li><a href="#">Help</a></li>
  <li id="super" style="position:absolute; top:0; left:100%%; width:441px; height:220px; background:%(page)s">
  <p>Python is a programming language that lets you work quickly.</p></li></ul></li></ul></nav></header>""",
     ["sub", "super"], []),
    ("sidedrawer", HEAD + """<nav id="side" style="position:fixed; top:57px; left:0; bottom:56px; width:200px;
  z-index:5; background:%(page)s"><a href="#">Home</a><br><a href="#">Explore</a><br><a href="#">Library</a></nav>
<div style="position:fixed; inset:0; z-index:50; background:rgba(0,0,0,0.4)"></div>
<aside id="drawer" style="position:fixed; top:0; left:0; bottom:0; width:300px; z-index:51;
  background:%(page)s"><b>Menu</b><p>Account</p><p>Orders</p><p>Help</p></aside>""", ["drawer", "side"], []),
]

COLORS = {"light": {"page": "rgb(255,255,255)", "text": "rgb(20,20,20)", "card": "rgb(214,229,242)"},
          "dark": {"page": "rgb(18,20,22)", "text": "rgb(235,235,235)", "card": "rgb(40,40,48)"}}


def routes():
    out = {}
    for tone_, colors in COLORS.items():
        for name, body, _, _ in CASES:
            out["/%s-%s.html" % (name, tone_)] = ("text/html; charset=utf-8",
                                                 page(colors, body % colors).encode("utf-8"))
    return out


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class PositionersE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_positioners(self):
        # (page tone, dark theme, Dark Reader): light first
        runs = [("light", False, False), ("dark", True, False), ("light", True, True)]
        for name, binary in tone.browsers():
            for page_tone, dark, darken in runs:
                with mn.TestServer(routes()) as srv, \
                        mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    for case, _, veiled, bare in CASES:
                        with self.subTest(browser=name, page=page_tone, darken=darken, case=case):
                            b.navigate(srv.url("/%s-%s.html" % (case, page_tone), "plain.test"))
                            if darken:
                                b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                                self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                            else:
                                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                            self.check(b, veiled, bare)

    def check(self, b, veiled, bare):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        # a click: the add-on's settle passes, as a site's own menu button
        b.js("document.body.dispatchEvent(new MouseEvent('click', {bubbles: true}));")
        self.assertTrue(b.wait_for(SETTLED, mn.WAIT_TIMEOUT, BAR), "the header never veiled")
        for el in veiled:
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, el, BAR), el + " not veiled")
        for el in bare:
            self.assertFalse(b.js(MARKED, el, BAR), el + " veiled")


if __name__ == "__main__":
    unittest.main()

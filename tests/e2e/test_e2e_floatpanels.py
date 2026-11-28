"""End-to-end: the floating layers markFloats used to miss or veil on the
wrong element get the bar's veil on the panel that paints them. In a real
headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_floatpanels.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Checked on a light page under a light theme first, then on a dark page under
a dark theme and on a light page Dark Reader darkens (the dark runs keep
the same layers):
  - a search dialog (GitLab): a window cover with a see-through column as
    tall as the window holding the short painted box: the box is veiled,
    not the column;
  - a navigation drawer in a shadow tree (SBB): a see-through fixed host
    over the whole window, no z-index, its dark panel inside: the panel;
  - a popup in a shadow tree hanging from the header (Reddit's user menu),
    its text slotted from the page: its painted body is veiled and the
    slotted white list made see-through;
  - a popover laid absolutely in the body (Discourse's "More" menu), a
    see-through positioner around its painted box: the box;
  - a side panel laid absolutely over a map (OpenStreetMap's sidebar),
    z-index 1, along the window's left edge: veiled; a caption card laid the
    same way in the middle of the map is not;
  - a dark toast and a dark tooltip, small: veiled; a brand-coloured chat
    button fixed in a corner is not;
  - a drawer opened in the flow of the header by its expanded button,
    taller than the window (admin.ch): veiled; an open FAQ answer in the
    page is not;
  - a dialog laid absolutely within a sticky sidebar's box over the
    sidebar's own links (Discourse's "More" menu): its painted box gets a
    veil of its own over the sidebar's;
  - a drawer holding a section of its own in a brand colour (NZZ's navy
    sections): the section is see-through on the drawer's veil.
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

# an element by id, in the document or an open shadow tree
FIND = ("const find = (r, id) => { const e = r.querySelector('#' + id); if (e) return e;"
        " for (const h of r.querySelectorAll('*')) if (h.shadowRoot) { const f = find(h.shadowRoot, id);"
        " if (f) return f; } return null; };")
MARKED = FIND + "const e = find(document, arguments[0]); return !!e && e.hasAttribute(arguments[1]);"
ALPHA = (FIND + "const c = getComputedStyle(find(document, arguments[0])).backgroundColor;"
         " const m = /\\(([^)]*)\\)/.exec(c); const a = m ? m[1].split(/[\\s,/]+/)[3] : '1';"
         " return a === undefined ? 1 : parseFloat(a);")
CLEAR = ALPHA.replace("return a === undefined ? 1 : parseFloat(a);", "return (a === undefined ? 1 : parseFloat(a)) < 0.5;")


def page(colors, body):
    return ("""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {position:sticky; top:0; z-index:60; height:48px; display:flex; gap:24px; align-items:center;
  background:%(page)s}
#long {height:300vh}
</style></head><body><header id="head"><a href="#">Home</a> <a href="#">News</a></header>
%(body)s<div id="long">%(lorem)s</div></body></html>""" % dict(colors, body=body, lorem=dk.TEXT * 10))


# (name, body, [ids veiled], [ids not veiled], [ids see-through])
CASES = [
    ("cover", """<div id="modal" role="dialog" style="position:fixed; inset:0; z-index:1050;
  background:rgba(5,5,6,0.24)"><div id="column" style="position:relative; width:60vw; height:100vh;
  margin:0 auto"><div id="box" style="position:relative; height:230px; background:%(page)s">
  <p>Search suggestions</p><p>Projects</p><p>Groups</p></div></div></div>""", ["box"], ["column", "modal"], []),
    ("shadowdrawer", """<x-nav id="host"></x-nav><script>
customElements.define("x-nav", class extends HTMLElement { constructor() { super();
  this.attachShadow({mode: "open"}).innerHTML = `<style>
:host {position:fixed; inset:0}
.container::before {content:""; position:absolute; inset:0; background:rgba(0,0,0,0.7)}
#panel {position:relative; width:35vw; height:100vh; background:rgb(21,21,21); color:white}
</style><div class="container"><div id="panel"><p>Travel</p><p>Tickets</p><p>Station</p></div></div>`; } });
document.getElementById("head").append(document.getElementById("host"));
</script>""", ["panel"], ["host"], []),
    ("shadowpopup", """<x-pop id="pop"><div id="drawercontent" style="width:256px; height:256px;
  background:%(page)s"><p>Profile</p><p>Settings</p><p>Log out</p></div></x-pop><script>
customElements.define("x-pop", class extends HTMLElement { constructor() { super();
  this.attachShadow({mode: "open"}).innerHTML = `<style>
#popup {position:absolute; top:36px; right:0; z-index:1}
#card {background:%(page)s}
</style><div id="popup"><div id="card" role="dialog"><slot></slot></div></div>`; } });
document.getElementById("head").style.position = "sticky";
document.getElementById("head").append(document.getElementById("pop"));
</script>""", ["card"], ["popup"], ["drawercontent"]),
    ("portal", """<div id="menu" style="position:absolute; top:188px; left:51px; width:210px; z-index:1400">
  <div id="inner" style="padding:1px 0; background:%(page)s"><p>Users</p><p>About</p><p>Guidelines</p><p>FAQ</p></div></div>""",
     ["inner"], ["menu"], []),
    ("side", """<div id="content" style="position:absolute; top:48px; left:0; right:0; height:90vh">
  <div id="map" style="position:absolute; inset:0; background:linear-gradient(90deg, rgb(170,210,160),
  rgb(200,220,240))"></div>
  <div id="sidebar" style="position:absolute; top:0; left:0; width:350px; height:430px; z-index:1;
  background:%(page)s"><h2>Welcome to the map</h2><p>A free map of the world, made by its people.</p></div>
  <div id="caption" style="position:absolute; top:100px; left:45vw; width:300px; height:200px; z-index:1;
  background:%(page)s"><p>A caption card over the picture</p></div></div>""", ["sidebar"], ["caption"], []),
    ("tips", """<button id="tipbtn">Hover me</button>
<div id="toast" role="status" style="position:fixed; top:72px; right:16px; background:#323232; color:#fff;
  padding:12px 16px; border-radius:6px; z-index:41">Saved to your library</div>
<div id="tip" style="position:absolute; top:220px; left:300px; background:#111; color:#fff; padding:6px 10px;
  font-size:13px; z-index:70">Custom tooltip, no title attribute</div>
<div id="chat" style="position:fixed; bottom:16px; right:16px; background:rgb(0,110,230); color:#fff;
  padding:14px 20px; border-radius:24px; z-index:50">Chat with us</div>""", ["toast", "tip"], ["chat"], []),
    ("inflow", """<style>#head {display:none}</style>
<header id="top" style="position:relative; z-index:30"><button aria-expanded="true"
  aria-controls="drawer">All federal authorities</button>
  <div id="drawer" style="height:110vh; background:rgb(47,67,86); color:white"><h2>Federal authorities</h2>
  <p>Departments</p><p>Federal Chancellery</p></div></header>
<main><button aria-expanded="true" aria-controls="faq">How to apply?</button>
  <div id="faq" style="background:%(card)s; height:200px"><p>Fill in the form and send it.</p></div></main>""",
     ["drawer"], ["faq"], []),
    ("insidebar", """<nav id="sidebar" style="position:sticky; top:48px; float:left; width:272px; height:90vh">
  <ul style="margin:0; list-style:none"><li style="position:relative"><a href="#">More</a>
  <div id="more" role="dialog" style="position:absolute; top:40px; left:20px; width:210px; z-index:1400">
  <div id="moreinner" style="padding:1px 0; background:%(page)s"><p>Users</p><p>About</p><p>Guidelines</p><p>FAQ</p></div></div></li>
  %(links)s</ul></nav>""", ["sidebar", "moreinner"], ["more"], []),
    ("section", """<div id="drawer" role="dialog" style="position:fixed; top:0; left:0; width:25vw; height:100vh;
  z-index:1001; overflow-y:auto; background:%(page)s"><p>Home</p><p>Latest</p>
  <ul id="navy" style="margin:0; height:150vh; background:rgb(21,24,90); color:white"><li>World</li>
  <li>Economy</li><li>Technology</li></ul></div>""", ["drawer"], [], ["navy"]),
]

LINKS = "".join('<li><a href="#">Category %d</a></li>' % i for i in range(12))
COLORS = {"light": {"page": "rgb(255,255,255)", "text": "rgb(20,20,20)", "card": "rgb(235,235,240)"},
          "dark": {"page": "rgb(18,20,22)", "text": "rgb(235,235,235)", "card": "rgb(40,40,48)"}}


def routes():
    out = {}
    for tone_, colors in COLORS.items():
        for name, body, _, _, _ in CASES:
            out["/%s-%s.html" % (name, tone_)] = ("text/html; charset=utf-8",
                                                 page(colors, body % dict(colors, links=LINKS)).encode("utf-8"))
    return out


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FloatPanelsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_float_panels(self):
        # (page tone, dark theme, Dark Reader): light first
        runs = [("light", False, False), ("dark", True, False), ("light", True, True)]
        for name, binary in tone.browsers():
            for page_tone, dark, darken in runs:
                with mn.TestServer(routes()) as srv, \
                        mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(),
                                   firefox=binary) as b:
                    tone.set_scheme(b, dark)
                    for case, _, veiled, bare, clear in CASES:
                        with self.subTest(browser=name, page=page_tone, darken=darken, case=case):
                            b.navigate(srv.url("/%s-%s.html" % (case, page_tone), "plain.test"))
                            if darken:
                                b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                                self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                            else:
                                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                            self.check(b, veiled, bare, clear)

    def check(self, b, veiled, bare, clear):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        # a click: the add-on's settle passes, as a site's own menu button
        b.js("document.body.dispatchEvent(new MouseEvent('click', {bubbles: true}));")
        for el in veiled:
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, el, BAR), el + " not veiled")
        for el in clear:
            self.assertTrue(b.wait_for(CLEAR, mn.WAIT_TIMEOUT, el),
                            el + " left opaque on the veil: %r" % b.js(ALPHA, el))
        for el in bare:
            self.assertFalse(b.js(MARKED, el, BAR), el + " veiled")


if __name__ == "__main__":
    unittest.main()

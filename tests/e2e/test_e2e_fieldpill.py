"""End-to-end: fields and secondary buttons in the boxes that paint them,
as sites draw them. In a real headless Firefox (and LibreWolf with
BG_LIBREWOLF).

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_fieldpill.py' -v

/page.html on plain.test (the generic style clears html, body, header and
main, as the bundled one does), under the light theme:
  - a white bordered search form (#arch) in a header (holding the site's
    menus) laid in a white wrapper right under a row of links at the top
    (two bars; the header under a bar is made one again on each pass),
    holding a white bordered field (#archq) and a light bordered button
    (#archgo), the form's white kept opaque in the bar (it holds controls):
    the form, the field and the button keep the site's look, no mark;
  - a search pill (#pill) under the bar, painted by empty absolute layers
    under its content (a white one, #pillbg, holding a grey one shown while
    a field is open, #pillopen), holding a see-through field and a coloured
    button:
    both layers and the coloured button keep the site's look, no mark;
  - an icon button in a wrapper holding its hidden white touch fill
    (#ibfill, YouTube's): no pill, the fill left alone;
  - a framed white card (a border: one the glass keeps opaque) holding a
    light bordered button (#cardbtn) and a white borderless one (#bare),
    and the same card in an open shadow tree (#xc): the buttons keep their
    own fill, no mark and no ring;
  - that stays so from pass to pass.
Under a dark theme (no Dark Reader here) the page keeps its tone: the marks
stay as they were. Darkened (Dark Reader, a dark theme): both buttons veiled
by the card's blocks (Dark Reader's fill, not the site's), and no ring.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import marionette as mn  # noqa: E402
import test_e2e_darken as dk  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
GENERIC_CSS = ("html, body, header, main { background-color: transparent !important;"
               " background: none !important; border: none !important; box-shadow: none !important; }\n")
TEXT = "<p>" + "Some dark text on the page, read on the glass. " * 4 + "</p>"
CARD_CSS = (".card{background:rgb(255,255,255);border:1px solid rgb(229,231,235);border-radius:8px;padding:16px;"
            "margin:16px 0} .card button{background:rgb(246,248,250);border:1px solid rgb(208,215,222);"
            "border-radius:6px;padding:6px 12px;color:rgb(36,41,47)} .card .bare{background:rgb(255,255,255);border:0}")
CARD = ('<div class="card"%s><b>Framed card</b><p>Text on the card.</p><button type="button"%s>Card button</button> '
        '<button type="button" class="bare"%s>Borderless</button></div>')
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(31,35,40);font:16px/1.5 sans-serif}
#nav{display:flex;align-items:center;gap:16px;height:40px;padding:0 12px;background:rgb(255,255,255)}
#nav ul{display:flex;gap:12px;list-style:none;margin:0;padding:0}
#pin{background:rgb(255,255,255)}
header{display:flex;gap:16px;align-items:center;padding:8px 12px;background:rgb(255,255,255)}
header a{color:rgb(55,65,81)}
#arch{display:flex;background:rgb(255,255,255);border:1px solid rgb(162,169,177);height:32px}
#archq{background:rgb(255,255,255);border:1px solid rgb(114,119,125);color:rgb(32,33,34);width:300px}
#archgo{background:rgb(248,249,250);border:1px solid rgb(114,119,125);color:rgb(64,66,68)}
#pill{position:relative;height:66px;width:520px;border-radius:33px}
#pillbg,#pillopen{position:absolute;inset:0;border-radius:33px}
#pillbg{background:rgb(255,255,255)} #pillopen{background:rgb(235,235,235);opacity:0}
.parts{position:relative;display:flex;align-items:center;height:66px;gap:24px;padding:0 8px 0 24px}
.part{display:flex;flex-direction:column} .lab{font-size:12px;font-weight:bold}
#where{background:transparent;border:0;color:rgb(34,34,34);width:160px}
#go{background:rgb(218,18,73);color:rgb(255,255,255);border:0;border-radius:24px;width:48px;height:48px}
%s
main{padding:0 24px}
#ib{position:relative;width:40px;height:40px}
#iconbtn{width:40px;height:40px;background:transparent;border:0;border-radius:20px;color:rgb(15,15,15)}
#ibfill{position:absolute;inset:0;border-radius:20px;background:rgb(255,255,255);opacity:0;pointer-events:none}
</style></head><body>
<div id="nav"><b>Site</b><ul><li><a href="#h">Home</a></li><li><a href="#p">Packages</a></li>
<li><a href="#f">Forums</a></li><li><a href="#w">Wiki</a></li></ul></div>
<div id="pin"><header><nav><a href="#n">News</a></nav>
<form id="arch"><input id="archq" placeholder="Search the wiki"><button id="archgo" type="button">Search</button></form>
</header></div>
<main><h1>Fields in their boxes</h1>
<div id="ib"><button id="iconbtn" type="button">=</button><div id="ibfill"></div></div>
<div id="pill"><div id="pillbg"><div id="pillopen"></div></div><div class="parts">
<div class="part"><div class="lab">Where</div><div><input id="where" placeholder="Destinations"></div></div>
<div class="part"><div class="lab">When</div><div>Add dates</div></div><button id="go" type="button">Go</button></div></div>
%s%s<x-card id="xc"></x-card>%s</main>
<script>customElements.define("x-card", class extends HTMLElement { connectedCallback() {
  const r = this.attachShadow({mode: "open"});
  r.innerHTML = '<style>%s</style>' + '%s'; } });</script></body></html>""" % (
    CARD_CSS, TEXT, CARD % (' id="card"', ' id="cardbtn"', ' id="bare"'), TEXT * 12, CARD_CSS, CARD % ("", "", ""))
BLOCKS = """const shadow = document.getElementById('xc').shadowRoot;
return Object.fromEntries(arguments[0].map((id) => {
  const el = id.startsWith('xc-') ? shadow.querySelector(id === 'xc-btn' ? 'button:not(.bare)' : '.bare')
    : document.getElementById(id);
  return [id, el ? el.getAttribute(arguments[1]) : 'missing'];
}));"""
WANT = {"arch": None, "archq": None, "archgo": None, "pillbg": None, "pillopen": None,
        "go": None, "where": None, "ibfill": None, "cardbtn": None, "bare": None, "xc-btn": None, "xc-bare": None}
# the site's own fill and no ring, judged once the page's tone is set
OWN = {"arch": "rgb(255, 255, 255)", "archq": "rgb(255, 255, 255)", "archgo": "rgb(248, 249, 250)",
       "pillbg": "rgb(255, 255, 255)", "cardbtn": "rgb(246, 248, 250)", "bare": "rgb(255, 255, 255)"}
LOOKS = """return Object.fromEntries(arguments[0].map((id) => {
  const s = getComputedStyle(document.getElementById(id));
  return [id, s.backgroundColor + ' ' + s.boxShadow];
}));"""
SAMPLES = 10
SAMPLE_GAP = 0.2
DARK_WANT = {"cardbtn": "veil", "bare": "veil"}
SHADOWS = "return arguments[0].map((id) => getComputedStyle(document.getElementById(id)).boxShadow);"
DARK_SETTLED = ("return document.getElementById('bare').hasAttribute(arguments[0])"
                " && document.getElementById('cardbtn').hasAttribute(arguments[0]);")


def routes():
    return {"/page.html": ("text/html; charset=utf-8", PAGE.encode("utf-8"))}


def stylesheet():
    sites = bg.Sites({bg.SITES_GENERIC_KEY: {"transparency": GENERIC_CSS}}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FieldPillE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_fieldpill(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def test_darkened(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_darkened(binary)

    def tone_is(self, b, want):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, tone.TONE, want):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute(arguments[0]);",
                                                tone.TONE), want))

    def marks_are(self, b):
        self.assertEqual(b.js(BLOCKS, list(WANT), bg.ATTR_BLOCK), WANT)
        self.assertEqual(b.js(LOOKS, list(OWN)), {k: v + " none" for k, v in OWN.items()})

    def check(self, binary):
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS)))
        with mn.TestServer(routes()) as srv, \
                mn.Browser(content_css=stylesheet(), prefs=prefs, firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/page.html", "plain.test"))
            b.js(tone.RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            self.marks_are(b)
            # no mark from pass to pass (the header made a bar again)
            for _ in range(SAMPLES):
                time.sleep(SAMPLE_GAP)
                b.js("window.scrollBy(0, 1);")
                self.marks_are(b)
            b.js("window.scrollTo(0, 0);")
            # a dark theme: the page's tone, and so its marks, stay
            tone.set_scheme(b, True)
            self.tone_is(b, "light")
            self.marks_are(b)

    def check_darkened(self, binary):
        with mn.TestServer(routes()) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/page.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
            self.assertTrue(b.wait_for(dk.DARKENED), "not darkened")
            self.assertTrue(b.wait_for(DARK_SETTLED, mn.WAIT_TIMEOUT, bg.ATTR_BLOCK), "card buttons not veiled")
            self.assertEqual(b.js(BLOCKS, list(DARK_WANT), bg.ATTR_BLOCK), DARK_WANT)
            # the veils stay from pass to pass, and no ring
            for _ in range(SAMPLES // 2):
                time.sleep(SAMPLE_GAP)
                b.js("window.scrollBy(0, 1);")
                self.assertEqual(b.js(BLOCKS, list(DARK_WANT), bg.ATTR_BLOCK), DARK_WANT)
                self.assertEqual(b.js(SHADOWS, list(DARK_WANT)), ["none", "none"])


if __name__ == "__main__":
    unittest.main()

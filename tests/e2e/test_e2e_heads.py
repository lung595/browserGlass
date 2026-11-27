"""End-to-end: the site's header at the top of the page (in the flow, or
sticky before anything scrolls under it) gets the bar's veil
(liveControl): the DMS surface at NAV_BAR_OPACITY over the bar's blur,
before any scroll, see-through or brand-coloured, its rows across it one
veil with it. In a real headless Firefox (and LibreWolf with
BG_LIBREWOLF).

Opt-in (needs a Firefox binary, a few seconds per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_heads.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers, stylesheets and stand-in add-on API as
test_e2e_darken.py. Checked, on a dark page under a dark theme, a light
page under a light theme, and a light page Dark Reader darkens:
  - a brand header in the flow (NZZ, Spiegel, Decathlon): a red header
    holding a black promo strip and a white row of links gets the veil
    and the blur at the top, both rows see-through, its yellow button
    keeping its fill; still marked once scrolled;
  - a see-through sticky header at the top (Vercel, KDE): the veil before
    any scroll;
  - a web component's header (SBB), its <header> in its shadow tree: the
    veil;
  - a tall brand header in the flow right under a strip of site links
    (Python's: its gradient, its main menu row, a hero panel inside):
    the veil, its menu row see-through, its hero panel kept;
  - a hero and an in-page card below the header: no veil.
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
VEILS = {tone_: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, tone_) + (bg.NAV_BAR_OPACITY,))
         for tone_ in ("dark", "light")}
CLEAR = "rgba(0, 0, 0, 0)"


def heads_page(page, text, card, head):
    """The page in its colour `page`, its text `text`, an in-page card
    `card`, and the header `head` at its top."""
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:%(page)s; color:%(text)s}
#head {display:block; background:rgb(220,0,30); color:white}
#promo {height:32px; background:rgb(17,17,17); color:white}
#navrow {display:flex; gap:24px; align-items:center; height:56px; background:rgb(255,255,255)}
#navrow a {color:rgb(20,20,20)}
#cta {background:rgb(255,200,0); color:rgb(20,20,20); border:0; padding:8px}
#sticky {position:sticky; top:0; z-index:10; display:flex; gap:24px; align-items:center; height:64px}
#hero {height:240px; font-size:48px; margin:0; padding:40px}
#card {width:300px; height:200px; margin:40px; background:%(card)s}
#long {height:300vh}
#strip {height:44px; background:rgb(43,59,74)}
#strip a {color:rgb(220,220,220)}
#tall {height:560px; background:rgb(43,91,132) linear-gradient(rgb(30,65,94) 10%%, rgb(43,91,132) 90%%)}
#mainnav {height:52px; margin:0 40px; background:rgb(45,97,140) linear-gradient(rgb(55,118,171) 30%%, rgb(45,97,140) 70%%)}
#mainnav a {color:white}
#subrow {height:40px; margin:0 40px; background:linear-gradient(rgb(55,118,171) 30%%, rgb(45,97,140) 70%%)}
#slides {height:300px; margin:20px 120px; background:rgb(30,41,51); color:white}
</style></head><body>
%(head)s
<h1 id="hero">Make every moment count</h1>
<div id="card"><p>An in-page card</p></div>
<div id="long">%(lorem)s</div>
<script>
customElements.define("x-head", class extends HTMLElement {
  connectedCallback() {
    if (this.shadowRoot)
      return;
    this.attachShadow({mode: "open"}).innerHTML = '<style>:host {display:block}'
      + 'header {display:flex; gap:24px; align-items:center; height:56px}</style>'
      + '<header><nav><a href="#">Timetable</a> <a href="#">Tickets</a> <a href="#">Travel</a></nav></header>';
  }
});
</script>
</body></html>""" % {"page": page, "text": text, "card": card, "head": head, "lorem": dk.TEXT * 10}


BRAND = ('<header id="head"><div id="promo">Black Friday: up to 50%% off</div>'
         '<nav id="navrow"><a href="#">News</a> <a href="#">Sport</a> <a href="#">Culture</a>'
         '<button id="cta">Subscribe</button></nav></header>')
STICKY = '<header id="sticky"><nav><a href="#">Products</a> <a href="#">Docs</a> <a href="#">Pricing</a></nav></header>'
SHADOW = '<x-head id="xhead"></x-head>'
TALL = ('<div id="strip"><nav><a href="#">Python</a> <a href="#">Docs</a> <a href="#">Jobs</a></nav></div>'
        '<header id="tall"><nav id="mainnav"><a href="#">About</a> <a href="#">Downloads</a></nav>'
        '<div id="subrow">Downloads: Windows, macOS</div><div id="slides">A slideshow panel</div></header>')
PAGES = {"dark": ("rgb(18,20,22)", "rgb(235,235,235)", "rgb(40,40,48)"),
         "light": ("rgb(255,255,255)", "rgb(20,20,20)", "rgb(235,235,240)")}
# the same as a style clearing the colours of headers and navs renders it:
# gradients alone, on a page of no colour
BARE = TALL + "<style>#tall, #mainnav {background-color: transparent !important}</style>"
HEADS = {"brand": BRAND, "sticky": STICKY, "shadow": SHADOW, "tall": TALL, "bare": BARE}
# Python's page: html and body see-through, its content painted by a
# wrapper under the header, a faint gradient over its colour
CONTENT = {"dark": ("rgb(18,20,22)", "rgb(26,28,30)"), "light": ("rgb(255,255,255)", "rgb(249,249,249)")}


def page_of(tone_, kind):
    """The test page of tone `tone_` with the header `kind`."""
    page, text, card = PAGES[tone_]
    if kind == "bare":
        return heads_page("transparent", text, "transparent", BARE)
    if kind != "tall":
        return heads_page(page, text, card, HEADS[kind])
    base, edge = CONTENT[tone_]
    return heads_page("transparent", text, card, TALL + '<div id="content" style="height:150vh; background:%s '
                      'linear-gradient(%s 10%%, %s 90%%)"><p>%s</p></div>' % (base, base, edge, dk.TEXT))
BG = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;"
# the blur, on the bar's ::before
BACKDROP = "return getComputedStyle(document.getElementById(arguments[0]), '::before').backdropFilter;"
HAS_BG = BG[:-1] + " === arguments[1];"


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class HeadsE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = dk.read("content.js")
        cls.darkreader_js = dk.read("vendor/darkreader.js")

    def test_heads(self):
        routes = {"/%s-%s.html" % (t, k): ("text/html; charset=utf-8", page_of(t, k).encode("utf-8"))
                  for t in PAGES for k in HEADS}
        # (the page's tone, dark theme, Dark Reader, the veil's tone)
        cases = [("dark", True, False, "dark"), ("light", False, False, "light"), ("light", True, True, "dark")]
        for name, binary in tone.browsers():
            for page, dark, darken, veil in cases:
                for kind, head in (("brand", "head"), ("sticky", "sticky"), ("shadow", "xhead"), ("tall", "tall"),
                                   ("bare", "tall")):
                    with self.subTest(browser=name, page=page, darken=darken, head=kind), \
                            mn.TestServer(routes) as srv, \
                            mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(),
                                       firefox=binary) as b:
                        tone.set_scheme(b, dark)
                        b.navigate(srv.url("/%s-%s.html" % (page, kind), "%s.test" % page))
                        if darken:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                            self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                        else:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                        self.check(b, head, VEILS[veil], kind == "brand")
                        if kind in ("tall", "bare"):
                            self.check_tall(b, kind == "tall")

    def check(self, b, head, veil, brand):
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, bg.ATTR_TONE), "the tone never measured")
        # at the top, before any scroll: the veil and the blur
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, head, BAR), "the header at the top not veiled")
        self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, head, veil), "the header's veil: %r" % b.js(BG, head))
        self.assertIn("blur(20px)", b.js(BACKDROP, head))
        for name in ("hero", "card"):
            self.assertFalse(b.js(dk.MARKED, name, BAR), name + " veiled")
        if not brand:
            return
        # its rows across it, one veil with it; its button keeps its fill
        for row in ("promo", "navrow"):
            self.assertTrue(b.wait_for(HAS_BG, mn.WAIT_TIMEOUT, row, CLEAR),
                            "a row of the header left opaque on the veil: %s %r" % (row, b.js(BG, row)))
        self.assertNotEqual(b.js(BG, "cta"), CLEAR, "the header's button lost its fill")
        # scrolled: still the header's veil
        b.js("window.scrollTo(0, 400);")
        b.js("return new Promise((done) => setTimeout(done, 600));")
        self.assertTrue(b.js(dk.MARKED, head, BAR), "the header lost its veil once scrolled")

    def check_tall(self, b, content):
        # one chrome: its strip too; its menu row see-through; its hero panel kept
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "strip", BAR), "the strip at the top not veiled")
        # rows of it in its colour under a gradient, or that gradient alone (a style clearing nav colours)
        for row in ("mainnav", "subrow"):
            self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0])).backgroundImage;", row),
                             "none", "a row of the header left opaque on the veil: " + row)
        self.assertNotEqual(b.js(BG, "slides"), CLEAR, "the hero's panel lost its fill")
        self.assertFalse(b.js(dk.MARKED, "slides", BAR), "the hero's panel veiled")
        if not content:
            return
        # the page's wrapper below: glass, its gradient too
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "content", bg.ATTR_CANVAS), "the page's wrapper not glass")
        self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('content')).backgroundImage === 'none';",
                                   mn.WAIT_TIMEOUT), "the page's wrapper kept its gradient")


if __name__ == "__main__":
    unittest.main()

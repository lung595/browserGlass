"""End-to-end: light pages under a dark theme (and dark pages under a light
one), in a real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 10 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_tone.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Throwaway browsers only (fake HOME, generated profile, 127.0.0.1 page
server, black-hole proxy); no browserglass.py subprocess: the stylesheets
come from its render functions.

One made-up site style, light.test.css, mapped to dark.test, makes html and
body transparent (as most site styles do, with !important). Two pages:
light.test (dark text on its own light background, no dark version
declared) and dark.test (light text on a dark background). Checked:
  - under a dark theme, without the add-on's tone attribute, the style
    leaves the light page alone (it paints its own background: readable);
  - with data-browserglass-tone="light" (set by Marionette, liveControl
    on), the light page gets the light tint (the light DMS surface at
    SITES_TONE_OPACITY) and the style; without liveControl the attribute
    changes nothing;
  - the dark page is glass (transparent) under a dark theme, and gets the
    dark tint under a light theme with data-browserglass-tone="dark";
  - in each case the text has a contrast of at least 4.5 against its
    effective background (the page's, or the tint over black and over
    white, the worst of the two);
  - the add-on's content.js (run in the page with a stand-in `browser`)
    measures the tone of both pages, again when the page switches its theme
    (a class on <html>) and when the colour scheme changes; text coloured
    in oklch() or color(display-p3) too; a page whose body keeps the default
    black and whose text shown is white through classes (YouTube) is dark;
  - grey text between the two tones (Hacker News' #828282 meta lines) does
    not vote while black or white text is shown, and the site's own menus
    (nav, the page's header and footer: a portal's long dark menu) do not
    vote while there is other text; a page with only grey text, or only a
    menu, is still measured from it;
  - text on cards painting an opaque background of their own (a news
    site's dark video cards on its white page) does not outvote the text
    on the page's background, under either colour scheme, nor on the
    mirror (white cards on a dark page); nor does the white text of a
    shop's banners drawn over pictures, nor a dark band below the first
    screen (a shop's tall footer) that is as wide as the page and taller
    than most of the window: both are read like cards;
  - a web app dark by its own style (Grafana: the dark class on <body>
    only, a header and a sidebar, the dashboard's light text on an opaque
    wrapper read like a card) whose only text on the page's background is
    black and out of sight (a skip link above the page, a label in a box
    of a pixel, clip, clip-path), or one short visible line, is dark under
    either scheme: glass under a dark theme, the dark tint under a light
    one; a dark marker on <body> counts as a declared dark version (no
    light tint, even measured light);
  - a light portal (Swisscom: a white body, its sections at opacity 0
    until scrolled to, a hero carousel's white headlines over pictures,
    the next slide's beside the window) is light under either scheme: the
    hidden text and the slide beside the window do not vote, and with no
    text left on the page's background the body's own colour decides;
    under a cookie dialog's half-opaque scrim too, the headline shown
    read on its picture, not on the scrim over it;
  - a drawing board (Excalidraw: a canvas filling the window, painted by
    its script, pale grey hints over it, dark text only on a toolbar) is
    light from its pixels, under either scheme, and dark once painted dark;
  - a site style that makes the text white (white.test.css) on a light
    page: under a dark theme the tone is that of the text shown, "dark"
    (the site style applies once the tone is set), so the page is glass
    and the white text readable on the dark tint;
  - the generic style (example.com.css) on plain.test, a light page with a
    shadow root: under a dark theme, without the tone, it leaves the shadow
    content alone (as in v1.0), with or without liveControl; under a light
    theme it applies there.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "py"))

import marionette as mn  # noqa: E402
from fakehome import load_script  # noqa: E402

bg = load_script()

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None
LIBREWOLF = mn.find_librewolf() if E2E else None

TONE, LIVE = bg.ATTR_TONE, bg.ATTR_LIVE
# The colour scheme of the pages: 0 dark, 1 light (live)
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
HOSTS = ("light.test", "dark.test", "white.test", "plain.test")
LIGHT_BG, LIGHT_TEXT = "rgb(250, 250, 250)", "rgb(20, 20, 20)"
DARK_BG, DARK_TEXT = "rgb(18, 18, 18)", "rgb(235, 235, 235)"

# A light page with dark text (no dark version declared); with class
# "night" on <html> (the page's own theme switch) or under a dark colour
# scheme when it has class "auto", light text on a dark background.
LIGHT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(250,250,250)} body{color:rgb(20,20,20);margin:0}
html.night{background:rgb(18,18,18)} html.night body{color:rgb(235,235,235)}
@media (prefers-color-scheme: dark) {
  html.auto{background:rgb(18,18,18)} html.auto body{color:rgb(235,235,235)}
}
</style></head><body><p>Readable text</p></body></html>"""
DARK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark"><style>
html{background:rgb(18,18,18)} body{color:rgb(235,235,235);margin:0}
</style></head><body><p>Readable text</p></body></html>"""
SITE_CSS = "html, body { background: transparent !important; }\n"
WHITE_CSS = SITE_CSS + "body { color: #fff !important; }\n"
GENERIC_CSS = "section { background: transparent !important; }\n"
WHITE = "rgb(255, 255, 255)"
SHADOW_BG = "rgb(238, 238, 238)"
# Text in oklch() (dark), or with class "p3" in color(display-p3) (light,
# on a dark background).
OKLCH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(250,250,250)} body{color:oklch(0.21 0.034 264.665);margin:0}
html.p3{background:rgb(18,18,18)} html.p3 body{color:color(display-p3 0.92 0.92 0.92)}
</style></head><body><p>Readable text</p></body></html>"""
# YouTube's dark theme: the body keeps the default (black) text colour, the
# text shown is white through classes; a hidden block of dark text must not
# count.
CLASSES_PAGE = """<!doctype html><html dark><head><meta charset="utf-8"><style>
html{background:rgb(15,15,15)} body{margin:0} .t{color:rgb(241,241,241)}
</style></head><body><div class="t"><h1>Video title</h1><p>Channel name</p></div>
<div style="display:none">""" + "Hidden dark text " * 50 + """</div></body></html>"""
# Hacker News: a light page whose grey meta lines (#828282, between the
# two tones) outweigh its black titles.
NEWS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(246,246,239)} body{margin:0;color:rgb(0,0,0)} .sub{color:rgb(130,130,130)}
</style></head><body>""" + ("<p><a>A title</a></p><p class=\"sub\">120 points by someone 3 hours ago"
                           " | hide | 45 comments</p>") * 20 + "</body></html>"
# A news portal (Le Monde): a dark header whose long menu (light links,
# more text nodes than SAMPLE_WALK) comes before the light page's content
# in the document.
PORTAL_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(250,250,250)} body{margin:0;color:rgb(20,20,20)}
header{background:rgb(20,20,30);color:rgb(240,240,240)} header a{display:inline-block;margin:2px}
</style></head><body><header><nav>""" + "<a>Rubrique</a>" * 2500 + """</nav></header>
<main>""" + "<p>Un article sur fond clair.</p>" * 30 + "</main></body></html>"
# Only a menu, light on dark: the menu still decides.
MENU_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(18,18,18)} body{margin:0;color:rgb(235,235,235)}
</style></head><body><nav>""" + "<a>Link</a> " * 30 + """</nav></body></html>"""
# Only mid-grey text on a dark page: the grey still decides.
GREY_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(18,18,18)} body{margin:0;color:rgb(136,136,136)}
</style></head><body><p>Grey text on a dark page.</p></body></html>"""
# A news site (RTS): a white page whose dark video cards, each painting
# its own opaque background, hold more light text than the page holds dark
# text (mid-grey captions aside). The text on the cards tells their tone,
# not the page's: light. With class "night" on <html>, the mirror: a dark
# page whose white cards hold more dark text: dark.
CARDS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(45,45,45)}
main{background:rgb(255,255,255)} .sub{color:rgb(130,130,130)}
.lane{display:flex;flex-wrap:wrap} .card{width:180px;margin:4px;background:rgb(45,45,45)}
.card h3{color:rgb(255,255,255);font-size:12px}
html.night, html.night main{background:rgb(18,18,18)} html.night body{color:rgb(235,235,235)}
html.night .card{background:rgb(255,255,255)} html.night .card h3{color:rgb(20,20,20)}
</style></head><body><main>""" + ("<p>Un article sur fond clair.</p><p class=\"sub\">Il y a 3 heures"
                                  " | Suisse</p>") * 15 + """<div class="lane">""" + (
    "<div class=\"card\"><h3>Le titre d'une video du jour</h3></div>") * 40 + "</div></main></body></html>"
# A shop (Amazon): a light page whose banners hold white headlines drawn
# over pictures, whose dark text sits on white cards, and whose dark footer
# band below the first screen is as wide as the page and taller than the
# window, its white links more text than the page's own dark titles. The
# banners and the band are read like cards: the page's titles decide, light.
SHOP_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(234,237,237)} body{margin:0;color:rgb(15,17,17)}
.heroes{display:flex;flex-wrap:wrap} .hero{position:relative;width:240px;height:280px;margin:4px}
.hero img{position:absolute;left:0;top:0;width:100%;height:100%}
.hero h2,.hero p{position:relative;margin:0;padding:8px;color:rgb(255,255,255);font-size:18px}
.grid{display:flex;flex-wrap:wrap;min-height:100vh} .card{width:200px;margin:6px;background:rgb(255,255,255)}
.band{min-height:100vh;padding:20px;background:rgb(35,47,62)} .band a{display:block;color:rgb(255,255,255)}
</style></head><body><div class="heroes">""" + (
    "<div class=\"hero\"><img alt=\"\" src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'"
    " width='24' height='28'%3E%3Crect width='24' height='28' fill='%23b03a10'/%3E%3C/svg%3E\">"
    "<h2>Les offres de la semaine</h2><p>Casques, audio et plus encore</p></div>") * 5 + (
    "</div><h2>Pour la maison</h2><h2>Pour la cuisine</h2><div class=\"grid\">") + (
    "<div class=\"card\"><h3>Lampe de chevet en bois</h3><p>Livraison gratuite d\u00e8s demain</p></div>") * 40 + (
    "</div><div class=\"band\">") + "<a href=\"#\">Informations sur la livraison</a>" * 40 + (
    "</div></body></html>")
# A web app dark by its own style (Grafana): the dark theme is a class on
# <body> only, <html> has none; a header and a sidebar (the site's menus),
# the dashboard's light text on an opaque dark wrapper beside the sidebar
# (read like a card); on the page's background, only black text out of
# sight: a skip link placed above the page until focused, a label for
# screen readers in a box of a pixel and clipped, one clipped with
# clip-path. With class "loading" on <html>, one short black line is
# left visible on the page (a loading message): too little to decide.
APP_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{background:rgb(255,255,255)} body{margin:0;color:rgb(0,0,0)}
body.theme-dark{background:rgb(17,18,23);color:rgb(204,204,220)}
.skip{position:absolute;top:-999px;left:12px} .skip span{color:rgb(0,0,0)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);color:rgb(0,0,0)}
.clipped{position:absolute;clip-path:inset(50%);color:rgb(0,0,0)}
.loader{display:none;color:rgb(0,0,0)} html.loading .loader{display:block}
header{height:40px;background:rgb(24,27,31)} header a,nav a{display:block;color:rgb(204,204,220)}
.app{display:flex} nav{width:240px;background:rgb(24,27,31)}
.wrapper{flex:1;min-height:100vh;background:rgb(17,18,23)}
</style></head><body class="theme-dark"><a class="skip" href="#main"><span>Skip to main content</span></a>
<span class="sr">Open the menu</span><span class="clipped">Search dashboards</span>
<p class="loader">Loading Grafana</p><header>""" + "<a>Home</a>" * 3 + """</header>
<div class="app"><nav>""" + "<a>Dashboards</a>" * 12 + """</nav><div class="wrapper" id="main">""" + (
    "<h3>CPU usage per instance</h3><p>Requests per second</p>") * 10 + "</div></div></body></html>"
APP_LOADING_PAGE = APP_PAGE.replace("<html>", '<html class="loading">', 1)
# A light portal (Swisscom): a white body, navy text, every section kept
# at opacity 0 until scrolled to (a reveal on scroll), a navy header (the
# site's menus) with white links; a hero carousel whose slides hold white
# headlines over pictures, the next slide laid beside the one shown, its
# middle right of the window. Neither the hidden text nor the next slide's
# headline votes; the white body decides, light, under either scheme.
# REVEAL_DIALOG_PAGE: the same under a cookie dialog, a white card over
# a fixed scrim of half-opaque black across the window: the headline shown
# is still read on its picture, not on the scrim painted over it.
REVEAL_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html{overflow-x:hidden} body{margin:0;background:rgb(255,255,255);color:rgb(0,17,85)}
header{background:rgb(0,17,85)} header a{display:inline-block;margin:6px;color:rgb(255,255,255)}
.hero{position:relative;height:420px;overflow:hidden} .track{display:flex;gap:2vw;width:300vw}
.slide{position:relative;flex:0 0 80vw;height:420px}
.slide img{position:absolute;left:0;top:0;width:100%;height:100%}
.slide h2,.slide p{position:relative;margin:0;padding:12px 24px;color:rgb(255,255,255)}
.reveal{opacity:0} .card{background:rgb(255,255,255);border:1px solid rgb(200,200,210)}
</style></head><body><header>""" + "<a>Abos</a>" * 8 + """</header><div class="hero"><div class="track">""" + (
    "<div class=\"slide\"><img alt=\"\" src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'"
    " width='24' height='28'%3E%3Crect width='24' height='28' fill='%23102050'/%3E%3C/svg%3E\">"
    "<h2>Le meilleur abonnement Internet de Suisse</h2><p>Internet et TV 1 an pour 39.90</p></div>") * 3 + (
    "</div></div>") + ("<div class=\"reveal\"><h2>Nos offres du moment</h2><p>Un abonnement mobile pour"
                       " toute la famille.</p><div class=\"card\"><p>Voir l'offre</p></div></div>") * 20 + (
    "</body></html>")
REVEAL_DIALOG_PAGE = REVEAL_PAGE.replace("</body>", (
    "<div style=\"position:fixed;inset:0;z-index:5;background:rgba(0,0,0,0.5)\"></div>"
    "<div style=\"position:fixed;top:60px;right:40px;width:420px;z-index:6;background:rgb(255,255,255);"
    "color:rgb(51,51,51);padding:16px\"><h2>Vous nous rendez visite depuis l'etranger</h2>"
    "<p>Afin d'assurer un fonctionnement de base du site, des cookies sont utilises.</p></div></body>"), 1)
# REVEAL_PROMO_PAGE: the same with a promotion shown at once in a modal
# <dialog> across the window (Swisscom's Black Weeks), see-through on its
# black backdrop, its headline and offer in white: the dialog's tone, not
# the page's (and the page under it, inert, is out of the hit tests: its
# carousel's headlines are not seen on their pictures). REVEAL_SHEET_PAGE:
# the same promotion in a fixed role="dialog" laid over the page, its
# black drawn by a ::before.
REVEAL_PROMO_PAGE = REVEAL_PAGE.replace("</body>", (
    "<dialog id=\"promo\" style=\"position:fixed;inset:0;width:auto;height:auto;max-width:none;max-height:none;"
    "margin:0;border:0;padding:460px 40px 0;background:transparent;color:rgb(255,255,255)\">"
    "<h2>Les Black Weeks sont la!</h2><p>Offres exceptionnelles et cadeaux pour tous les abonnements.</p>"
    "<p>Profitez maintenant des meilleurs prix de l'annee.</p></dialog>"
    "<style>#promo::backdrop{background:rgb(0,0,0)}</style>"
    "<script>document.getElementById('promo').showModal();</script></body>"), 1)
REVEAL_SHEET_PAGE = REVEAL_PAGE.replace("</body>", (
    "<div id=\"sheet\" role=\"dialog\" style=\"position:fixed;inset:0;z-index:9;padding:460px 40px 0;"
    "color:rgb(255,255,255)\"><h2>Les Black Weeks sont la!</h2>"
    "<p>Offres exceptionnelles et cadeaux pour tous les abonnements.</p>"
    "<p>Profitez maintenant des meilleurs prix de l'annee.</p></div>"
    "<style>#sheet::before{content:'';position:absolute;inset:0;z-index:-1;background:rgb(0,0,0)}</style></body>"), 1)
# A drawing board (Excalidraw): a <canvas> filling the window, painted
# white by its script (no style says so), under an empty transparent top
# canvas; over it, a welcome screen of pale grey hints (pointer-events
# none: on the picture) and on a white toolbar (a card) a little dark
# text; the canvas' fallback text is the only text on the page. The hints
# outweigh the toolbar: the board's pixels decide, light. With class
# "night" on <html>, the board is painted dark and the hints mid-grey: dark.
BOARD_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;height:100%;overflow:hidden;color:rgb(0,0,0)} canvas{position:absolute;inset:0;width:100%;height:100%}
.top{pointer-events:none} .welcome{position:absolute;top:30%;left:30%;pointer-events:none;color:rgb(184,184,184)}
html.night .welcome{color:rgb(122,122,122)}
.tools{position:absolute;top:10px;left:40%;background:rgb(255,255,255);color:rgb(16,20,24)}
html.night .tools{background:rgb(35,35,41);color:rgb(222,222,227)}
</style></head><body><canvas class="board">Drawing canvas</canvas><canvas class="top"></canvas>
<div class="welcome">""" + ("<p>Your drawings are saved in your browser's storage.</p>"
                            "<p>Export, preferences, languages</p><p>Pick a tool and start drawing</p>") * 3 + (
    """</div><div class="tools"><span>R</span><span>D</span><span>Shapes</span></div>
<script>const c = document.querySelector(".board"); c.width = innerWidth; c.height = innerHeight;
const g = c.getContext("2d");
g.fillStyle = document.documentElement.classList.contains("night") ? "rgb(18,18,18)" : "rgb(255,255,255)";
g.fillRect(0, 0, c.width, c.height);</script></body></html>""")
BOARD_NIGHT_PAGE = BOARD_PAGE.replace("<html>", '<html class="night">', 1)
# A light page with a web component: a light section in a shadow root.
SHADOW_PAGE = LIGHT_PAGE.replace("<p>Readable text</p>", """<p>Readable text</p><div id="host"></div>
<script>document.getElementById("host").attachShadow({mode: "open"}).innerHTML =
'<section style="background:rgb(238,238,238)">In a shadow tree</section>';</script>""")
SHADOW_BG_JS = ("return getComputedStyle(document.getElementById('host').shadowRoot"
                ".querySelector('section')).backgroundColor;")

# Run content.js in the page: a stand-in for the WebExtension API (an empty
# stored exclusion list, no messages).
RUN_CONTENT = ("const stub = {storage: {local: {get: () => Promise.resolve({excluded: []})}},"
               "  runtime: {onMessage: {addListener() {}}}};"
               "(new Function('browser', arguments[0]))(stub);")


def browsers():
    """[(name, binary)] of the browsers to run."""
    out = [("firefox", FIREFOX)]
    if LIBREWOLF:
        out.append(("librewolf", LIBREWOLF))
    return out


def stylesheet(live):
    sites = bg.Sites({"light.test.css": {"glass": SITE_CSS}, "white.test.css": {"glass": WHITE_CSS},
                      bg.SITES_GENERIC_KEY: {"glass": GENERIC_CSS}},
                     {"light.test.css": ["dark.test"]})
    values = bg.settings_from_json("{}")
    values.update(liveControl=live)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


def browser_prefs():
    prefs = mn.test_host_prefs(list(HOSTS))
    # LibreWolf's defaults: no HTTPS upgrade of the test server, real colour scheme
    prefs.update({"dom.security.https_only_mode": False,
                  "privacy.resistFingerprinting": False,
                  PREF_SCHEME: 0})
    return prefs


def set_scheme(b, dark):
    b.chrome_js("Services.prefs.setIntPref(arguments[0], arguments[1]);", PREF_SCHEME, 0 if dark else 1)
    if not b.wait_for("return matchMedia('(prefers-color-scheme: dark)').matches === arguments[0];",
                      mn.WAIT_TIMEOUT, dark):
        raise AssertionError("the colour scheme did not switch to %s" % ("dark" if dark else "light"))


def set_tone(b, tone):
    b.js("const root = document.documentElement;"
         "if (arguments[0] === null) { root.removeAttribute(arguments[1]); root.removeAttribute(arguments[2]); }"
         "else { root.setAttribute(arguments[1], arguments[0]); root.setAttribute(arguments[2], ''); }",
         tone, TONE, LIVE)


def colors(b):
    """(text colour of the body, background of html, background of body)."""
    return (b.css("body", "color")["color"], b.css("html", "background-color")["background-color"],
            b.css("body", "background-color")["background-color"])


def rgba(text):
    """(r, g, b, a) of a computed rgb()/rgba() value."""
    inside = text[text.index("(") + 1:text.index(")")]
    parts = [float(p) for p in inside.split(",")]
    return tuple(parts) if len(parts) == 4 else tuple(parts) + (1.0,)


def luminance(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b_ = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b_)


def contrast(text, background):
    """The worst contrast of `text` on `background` (computed values),
    composited over black and over white (what is behind the glass)."""
    fg = rgba(text)
    bgc = rgba(background)
    out = []
    for under in (0.0, 255.0):
        eff = [bgc[3] * c + (1 - bgc[3]) * under for c in bgc[:3]]
        hi, lo = sorted((luminance(fg), luminance(eff)), reverse=True)
        out.append((hi + 0.05) / (lo + 0.05))
    return min(out)


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class ToneE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.gated = stylesheet(True)
        cls.original = stylesheet(False)
        assert TONE in cls.gated and TONE not in cls.original
        with open(os.path.join(REPO, bg.EXTENSION_DIR, "content.js"), encoding="utf-8") as f:
            cls.content_js = f.read()
        a = bg.format_number(bg.SITES_TONE_OPACITY)
        cls.tint = {mode: "rgba(%d, %d, %d, %s)" % (bg.surface_rgb(None, mode) + (a,))
                    for mode in bg.MODES}

    def test_tone(self):
        for name, binary in browsers():
            with self.subTest(browser=name):
                self.check_styles(binary)
                self.check_content_js(binary)
                self.check_shadow(binary)

    def check_shadow(self, binary):
        routes = {"/s.html": ("text/html; charset=utf-8", SHADOW_PAGE.encode("utf-8"))}
        for css in (self.gated, self.original):
            with mn.TestServer(routes) as srv, \
                    mn.Browser(content_css=css, prefs=browser_prefs(), firefox=binary) as b:
                b.navigate(srv.url("/s.html", "plain.test"))
                set_scheme(b, True)
                self.assertEqual(b.js(SHADOW_BG_JS), SHADOW_BG)
                set_scheme(b, False)
                self.assertEqual(b.js(SHADOW_BG_JS), "rgba(0, 0, 0, 0)")

    def readable(self, text, background):
        self.assertGreaterEqual(contrast(text, background), 4.5, (text, background))

    def check_styles(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.gated, prefs=browser_prefs(), firefox=binary) as b:
            b.navigate(srv.url("/p.html", "light.test"))
            set_scheme(b, True)
            # no tone (no add-on yet): the light page keeps its own background
            text, html, body = colors(b)
            self.assertEqual((text, html), (LIGHT_TEXT, LIGHT_BG))
            self.readable(text, html)
            # tone measured light: the light tint, the site style applies
            set_tone(b, "light")
            text, html, body = colors(b)
            self.assertEqual(html, self.tint["light"])
            self.assertEqual(body, "rgba(0, 0, 0, 0)")
            self.readable(text, html)
            # a page declaring its dark version never gets the light tint,
            # even measured light (a single-page app measured too early)
            b.js("document.documentElement.setAttribute('dark', '');")
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            b.js("document.documentElement.removeAttribute('dark');")
            self.assertEqual(colors(b)[1], self.tint["light"])
            # nor one declaring it on <body> only (Grafana's theme-dark)
            b.js("document.body.classList.add('theme-dark');")
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            b.js("document.body.classList.remove('theme-dark');")
            self.assertEqual(colors(b)[1], self.tint["light"])
            # under a light theme the light page is glass, untinted
            set_scheme(b, False)
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            # the dark page: glass under a dark theme, the dark tint under a
            # light one once measured dark
            b.navigate(srv.url("/d.html", "dark.test"))
            set_scheme(b, True)
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            set_tone(b, "dark")
            self.assertEqual(colors(b)[1:], ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            set_scheme(b, False)
            text, html, body = colors(b)
            self.assertEqual((text, html), (DARK_TEXT, self.tint["dark"]))
            self.readable(text, html)
            set_tone(b, None)
            text, html, body = colors(b)
            self.assertEqual(html, "rgba(0, 0, 0, 0)")
        # without liveControl the attribute changes nothing
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.original, prefs=browser_prefs(), firefox=binary) as b:
            b.navigate(srv.url("/p.html", "light.test"))
            set_scheme(b, True)
            set_tone(b, "light")
            self.assertEqual(colors(b)[:2], (LIGHT_TEXT, LIGHT_BG))

    def tone_is(self, b, tone):
        if not b.wait_for("return document.documentElement.getAttribute(arguments[0]) === arguments[1];",
                          mn.WAIT_TIMEOUT, TONE, tone):
            self.fail("tone %r, not %r" % (b.js("return document.documentElement.getAttribute("
                                                "arguments[0]);", TONE), tone))

    def check_content_js(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", LIGHT_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_PAGE.encode("utf-8")),
                  "/o.html": ("text/html; charset=utf-8", OKLCH_PAGE.encode("utf-8")),
                  "/c.html": ("text/html; charset=utf-8", CLASSES_PAGE.encode("utf-8")),
                  "/n.html": ("text/html; charset=utf-8", NEWS_PAGE.encode("utf-8")),
                  "/portal.html": ("text/html; charset=utf-8", PORTAL_PAGE.encode("utf-8")),
                  "/menu.html": ("text/html; charset=utf-8", MENU_PAGE.encode("utf-8")),
                  "/g.html": ("text/html; charset=utf-8", GREY_PAGE.encode("utf-8")),
                  "/cards.html": ("text/html; charset=utf-8", CARDS_PAGE.encode("utf-8")),
                  "/shop.html": ("text/html; charset=utf-8", SHOP_PAGE.encode("utf-8")),
                  "/app.html": ("text/html; charset=utf-8", APP_PAGE.encode("utf-8")),
                  "/loading.html": ("text/html; charset=utf-8", APP_LOADING_PAGE.encode("utf-8")),
                  "/board.html": ("text/html; charset=utf-8", BOARD_PAGE.encode("utf-8")),
                  "/night.html": ("text/html; charset=utf-8", BOARD_NIGHT_PAGE.encode("utf-8")),
                  "/reveal.html": ("text/html; charset=utf-8", REVEAL_PAGE.encode("utf-8")),
                  "/dialog.html": ("text/html; charset=utf-8", REVEAL_DIALOG_PAGE.encode("utf-8")),
                  "/promo.html": ("text/html; charset=utf-8", REVEAL_PROMO_PAGE.encode("utf-8")),
                  "/sheet.html": ("text/html; charset=utf-8", REVEAL_SHEET_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=self.gated, prefs=browser_prefs(), firefox=binary) as b:
            set_scheme(b, True)
            b.navigate(srv.url("/p.html", "light.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            self.assertTrue(b.js("return document.documentElement.hasAttribute(arguments[0]);", LIVE))
            self.assertEqual(colors(b)[1], self.tint["light"])
            # the page switches its own theme: a class on <html>
            b.js("document.documentElement.classList.add('night');")
            self.tone_is(b, "dark")
            text, html, body = colors(b)
            self.assertEqual((text, html), (DARK_TEXT, "rgba(0, 0, 0, 0)"))
            # a page following the colour scheme
            b.js("document.documentElement.className = 'auto';")
            self.tone_is(b, "dark")
            set_scheme(b, False)
            self.tone_is(b, "light")
            set_scheme(b, True)
            self.tone_is(b, "dark")
            b.navigate(srv.url("/d.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            # colours in other colour spaces
            b.navigate(srv.url("/o.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "light")
            b.js("document.documentElement.classList.add('p3');")
            self.tone_is(b, "dark")
            # the body's colour unset, the text shown white through classes
            b.navigate(srv.url("/c.html", "dark.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            # a site style making the text white: the tone of the text shown
            b.navigate(srv.url("/p.html", "white.test"))
            b.js(RUN_CONTENT, self.content_js)
            self.tone_is(b, "dark")
            text, html, body = colors(b)
            self.assertEqual((text, html), (WHITE, "rgba(0, 0, 0, 0)"))
            self.readable(text, "rgb(%d, %d, %d)" % bg.surface_rgb(None, "dark"))
            # mid-grey text does not vote while black or white text does
            for path, want in (("/n.html", "light"), ("/portal.html", "light"),
                               ("/menu.html", "dark"), ("/g.html", "dark")):
                b.navigate(srv.url(path, "light.test"))
                b.js(RUN_CONTENT, self.content_js)
                with self.subTest(page=path):
                    self.tone_is(b, want)
            # text on cards of its own does not outvote the page's text,
            # under either scheme, nor on the mirrored dark page
            for dark in (True, False):
                set_scheme(b, dark)
                b.navigate(srv.url("/cards.html", "light.test"))
                b.js(RUN_CONTENT, self.content_js)
                with self.subTest(page="/cards.html", dark=dark):
                    self.tone_is(b, "light")
                    b.js("document.documentElement.classList.add('night');")
                    self.tone_is(b, "dark")
            # nor do a shop's banners over pictures and its tall footer band
            for dark in (True, False):
                set_scheme(b, dark)
                b.navigate(srv.url("/shop.html", "light.test"))
                b.js(RUN_CONTENT, self.content_js)
                with self.subTest(page="/shop.html", dark=dark):
                    self.tone_is(b, "light")
            # a web app dark by its own style: text out of sight, and one
            # short line on the page, do not outvote the dashboard on its
            # wrapper; glass under a dark theme, the dark tint under a light
            for dark in (True, False):
                set_scheme(b, dark)
                for path in ("/app.html", "/loading.html"):
                    b.navigate(srv.url(path, "light.test"))
                    b.js(RUN_CONTENT, self.content_js)
                    with self.subTest(page=path, dark=dark):
                        self.tone_is(b, "dark")
                        self.assertEqual(colors(b)[1], "rgba(0, 0, 0, 0)" if dark else self.tint["dark"])
            # a drawing board: its pixels decide, not the hints over it
            for dark in (True, False):
                set_scheme(b, dark)
                for path, want in (("/board.html", "light"), ("/night.html", "dark")):
                    b.navigate(srv.url(path, "light.test"))
                    b.js(RUN_CONTENT, self.content_js)
                    with self.subTest(page=path, dark=dark):
                        self.tone_is(b, want)
            # a light portal whose text is hidden until scrolled to: the
            # next slide's headline beside the window does not vote, the
            # white body decides (no site style: read past the page rules);
            # under a cookie dialog's scrim too, the headline shown read on
            # its picture; under a promotion's dialog, its white text
            # telling the dialog's tone
            for path in ("/reveal.html", "/dialog.html", "/promo.html", "/sheet.html"):
                for dark in (True, False):
                    set_scheme(b, dark)
                    b.navigate(srv.url(path, "plain.test"))
                    b.js(RUN_CONTENT, self.content_js)
                    with self.subTest(page=path, dark=dark):
                        self.tone_is(b, "light")


if __name__ == "__main__":
    unittest.main()

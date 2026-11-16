"""End-to-end: dark pages (darkPages). Under a dark theme the companion
add-on turns a light page dark with its Dark Reader engine
(extension/vendor/darkreader.js), and the large elements that paint the
page's background become glass. In a real headless Firefox (and LibreWolf
with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 10 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_darken.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Same throwaway browsers and stylesheets as test_e2e_tone.py; Dark Reader and
content.js run in the page with a stand-in `browser`, whose storage holds
the list and the helper's darken flag (the darkPages setting, sent with
the list). Checked:
  - a light page under a dark theme: darkened (light text), html and body
    see-through, the full-page wrapper marked as canvas and see-through, a
    small grey card a light veil, not marked as canvas; the fetch Dark Reader gets
    returns a stylesheet, and refuses another type or a missing file;
    grey text stays grey (the text colour's tint is muted); a frame keeps
    its colour scheme (not Dark Reader's dark one);
  - a light theme gives the page its own colours back (no Dark Reader
    style, tone light), the wrapper, its lowest layer, still glass; a dark
    theme darkens it again; the helper turning darken off live (a message)
    gives the page back at once;
  - left alone: a page that declares a dark version (on <html>, or on
    <body> only: a web app dark by its own style, measured dark despite
    its black skip link out of sight), an excluded page, and
    any page with darkPages off, a page under the style file's colours
    while the helper says darken false, and a page that sets the darkening
    colours itself, under a light theme and under a dark one (darken
    false: the colours alone never darken);
  - a page with its own dark theme behind a class (a "dark" class on
    <html>, its text colour animated) gets it instead of Dark Reader, and
    gives it back under a light theme; a page without one is left with no
    such mark once darkened;
  - a darkened page that turns its own dark theme on late (DSFR's
    data-fr-theme set by a module script) gets Dark Reader off, its own
    dark kept; a mark that leaves the page light (data-header-theme)
    gets Dark Reader back at once;
  - a site style of data/sites/ on a darkened page: Stack Overflow's
    filled buttons and search field (the real Stacks var() fallback chains,
    which Dark Reader maps to the page's white) keep a fill of their own
    under a dark theme, and the site's own colours under a light one;
  - Wikipedia's site style on its own night and day themes: the infobox's
    cells and lines and a plain hatnote see-through (a cell's own inline
    colour kept), its header and section bars and a hatnote banner under
    a light veil with a thin border, the search field translucent on a
    clear form;
  - pictures on a white card Dark Reader darkens: a photo blended with
    multiply is shown on a white tile (not blended, not inverted, a white
    margin drawn by a shadow, rounded outside, with no seam of the dark
    background at the photo's corners), and so is a black product cut out
    of its photo (shaded grey); see-through dark ink of one tone of the
    page's origin or a data: URL (a black or navy logo) is inverted to
    light ink, its hues turned back, with no tile, and so are icons (a
    black square under 24 px, thin black lines with a red accent 24 px
    square, whatever the share of red, a black one blended with multiply);
    an opaque product photo shot on white (a JPEG, in an absolute box,
    faded in once loaded) is on a white tile too;
    left alone: a photo as wide as the page, the same ink from another
    origin (its pixels cannot be read), a light logo, an opaque photo
    filling its frame, a shaded round avatar, a round avatar shot on white; a light theme takes the tiles off. A multiplied photo loaded late (a lazy one: no width, so
    no tile, until it is in) is tiled once loaded, with nothing else
    moving on the page;
  - inline SVG logos in a header Dark Reader inverts: one whose shapes the
    page's style sheet paints (Dark Reader lightens that rule) shows its
    light ink with no filter, one dark by its attributes alone stays
    inverted; a light theme takes the mark off;
  - glyphs drawn with a background that Dark Reader darkens (a menu
    button's bars: an empty span and its ::before and ::after; bars in a
    small box) are painted in the text colour, which reads on the glass;
    a wide rule, a separator in a line of text, a thick pill and a bar
    that still reads are not glyphs; thin rules in a neutral colour Dark
    Reader leaves without contrast (the wide rule, a vertical separator
    between a header's logo and its title, as admin.ch draws it) are
    painted a light neutral that reads on the glass, while the thick pill,
    a bar in a colour that reads and the glyphs are left alone; a light
    theme takes the marks off;
  - white blocks Dark Reader turns into opaque near-black panels (news
    cards, a card's inner content box, a secondary button, a strip across
    the window, as admin.ch, boursorama.com and postfinance.ch draw them):
    the outer card a light veil (its border kept), the box inside it
    see-through, the button a veil of its own, the strip glass, the text
    still light; left alone: a coloured button, a fixed dialog, a popup
    menu over the page, a player's black box; a light theme gives the
    white back;
  - buttons in a saturated brand colour Dark Reader dulls (a link whose
    ::before paints postfinance.ch's yellow from a variable under a petrol
    label, proton.me's violet button, an input button, a crimson fill in
    oklch(), a pastel teal under a dark label) keep their fill and label
    colours as the page had them; a black button under a white label in
    a fixed header keeps them with a thin light ring ("lift"); text
    buttons whose background is a var() the page never sets, which Dark
    Reader fills, are see-through again ("clear"), a tab the page fills
    once darkened is not; left alone: a pale button, a light grey and a
    light blue one under a dark label, a wide banner, a coloured link with
    no label, a label that does not read on its fill; a light theme takes
    the marks and their inline colours off;
  - a page whose only opaque surface is a white column half the window
    wide (ch.ch), light words on its see-through half: the column's navy
    text votes, the page is darkened; under a light theme the column is
    glass and the white label of its tagline too, not a popup menu laid
    over it; a view whose navy line was inked light on the dark glass
    turns light once its light text is gone (the inked line votes with
    its own colour); text in a see-through fixed footer over a white box
    of the page is not inked, beside it over the glass it is;
  - a light page with dark sections holding white text, with the real
    generic style (MeteoSuisse's forecast): under a light theme the
    section and one in an open shadow tree (white text of its own, and a
    heading slotted in from the page) keep their own colour, their text
    not inked, while a white section is cleared; under Dark Reader the
    shadow section is glass or a light veil, not an opaque slab; a light
    theme gives its colour back; a kept section grown to fill the window
    never becomes the page's layer; a yellow half kept while the page was
    measured dark is glass once it is light; under a dark theme, a dark
    section in a shadow tree that made the layer of a page measured dark
    while it loads is kept, its own colour back, once the page is light;
  - a dark page with a light section (GitLab's feature cards, the real
    generic style): the section's ::before, its tint clipped by its
    padding to a band, is no face behind the dark heading, so the section
    keeps its own colour and the heading is not inked, under either
    theme; the sticky header's mid-grey links, drawn for its white, are
    inked light on its dark veil once stuck.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402
import test_e2e_tone as tone  # noqa: E402

bg = tone.bg
CANVAS, OFF, TILE, UNINVERT = bg.ATTR_CANVAS, bg.ATTR_OFF, bg.ATTR_TILE, bg.ATTR_UNINVERT
BAR = bg.ATTR_BAR
EXT = os.path.join(tone.REPO, "extension")

TEXT = "<p>" + "Some readable dark text on a light page. " * 8 + "</p>"
WRAPPED_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#wrap {background:rgb(255,255,255); min-height:100vh}
#card {background:rgb(240,240,240); width:200px; height:100px}
.meta {color:rgb(130,130,130)}
</style></head><body><div id="wrap">""" + TEXT + """<p id="grey" class="meta">120 points by someone</p>
<div id="card">Card</div><iframe id="frame" src="about:blank" width="20" height="20"></iframe></div></body></html>"""

# A light page with its own dark theme, on a "dark" class of <html>; the
# text colour is animated, as theme switches often are.
NATIVE_PAGE = """<!doctype html><html class="app"><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20); transition: color 2s}
html.dark, html.dark body {background:rgb(17,17,17); color:rgb(230,230,230)}
</style></head><body>""" + TEXT + """</body></html>"""
CLASSES = "return document.documentElement.className;"

# A light page whose own dark theme turns its text light, so it is kept,
# then shows dark text of its own (#late, an inline colour the ".dark"
# scope does not change): the theme is taken back and the page
# darkened. Its crimson button easing to a coral token under ".dark"
# (#ease, letemps.ch's subscribe button) keeps its own colours, read once
# the theme is gone, not on its way back.
TAKEN_BACK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
.dark body {color:rgb(230,230,230)}
#ease {background:rgb(176,20,50); color:rgb(255,255,255); padding:10px 20px; transition:background-color 2s, color 2s}
.dark #ease {background:rgb(240,99,104); color:rgb(20,20,20)}
</style></head><body><div id="wrap">""" + TEXT + """<p><a id="ease" href="#">S'abonner</a></p></div>
<script>setTimeout(() => {
  const late = document.createElement("div");
  late.id = "late";
  late.style.color = "rgb(20,20,20)";
  late.innerHTML = """ + repr(TEXT * 4) + """;
  document.getElementById("wrap").append(late);
}, 1500);</script></body></html>"""

# A light page whose own dark theme a late script turns on with DSFR's
# mark (data-fr-theme on <html>); data-header-theme="dark" darkens nothing.
LATE_DARK_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#wrap {background:rgb(255,255,255); min-height:100vh}
html[data-fr-theme="dark"], html[data-fr-theme="dark"] body, html[data-fr-theme="dark"] #wrap
  {background:rgb(22,22,22); color:rgb(230,230,230)}
</style></head><body><div id="wrap">""" + TEXT + """</div></body></html>"""

# Dark Reader as a module (its UMD wrapper fills `exports`), then content.js
# with it and a stand-in WebExtension API (the stored exclusion list and
# darken flag, arguments[3]: left out, as test_e2e_layers.py does, none is
# stored, which is false). The fetch method content.js hands Dark Reader is
# kept as window.bgFetch, its message listener as window.bgMessage.
RUN = ("const exp = {}; (new Function('exports', 'module', arguments[1]))(exp, {exports: exp});"
       "const setFetch = exp.setFetchMethod;"
       "exp.setFetchMethod = (f) => { window.bgFetch = f; setFetch(f); };"
       "const stored = {excluded: arguments[2]};"
       "if (arguments[3] !== undefined) stored.darken = arguments[3];"
       "const stub = {storage: {local: {get: () => Promise.resolve(stored)}},"
       "  runtime: {onMessage: {addListener(f) { window.bgMessage = f; }}}};"
       "(new Function('browser', 'DarkReader', arguments[0]))(stub, exp);")
# The helper's list as background.js forwards it to the page.
MESSAGE = "window.bgMessage({type: 'excluded', domains: arguments[0], darken: arguments[1]});"
DARKENED = "return !!document.querySelector('style.darkreader');"
FETCHED = ("return window.bgFetch(arguments[0]).then((r) => r.text(), () => 'refused');")

# A light page that sets the darkening colours itself.
SPOOF_PAGE = WRAPPED_PAGE.replace(
    "</style>", ":root {--browserglass-darken-bg: #000; --browserglass-darken-fg: #fff}</style>")
MARKED = "return document.getElementById(arguments[0]).hasAttribute(arguments[1]);"


def svg(width, height, body):
    """A data: URL of an SVG picture."""
    return "data:image/svg+xml," + urllib.parse.quote(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">%s</svg>' % (width, height, body))


# Pictures on a white shop card Dark Reader darkens: a product photo whose
# white the site wipes out with multiply (#photo), one as wide as the
# page (#hero), one fitted in a square box (#fit: tiled whole);
# see-through black ink of the page's origin (#ink, from /ink.svg) and of a data: URL (#mark), and navy ink (#navy), of one tone
# (inverted), a black product cut out of its photo (#puck, see-through,
# shaded grey: tiled), and the same ink from another origin (#far, its
# source set by the test: its pixels cannot be read); a see-through light
# logo (#sun), an opaque photo filling its frame (#opaque: an editorial
# one), a product photo shot on white (#shot: opaque, tiled) and a round
# avatar shot on white (#round: left alone), a black icon under 24 px
# (#icon: inverted), icons 24 px square of thin black lines with a red
# accent, more or less of it (#line1 to #line3, as a bank's list of
# services draws them: all inverted, none tiled), a shaded round avatar
# 32 px wide (#avatar: left alone), a black icon blended with multiply
# (#blendicon: inverted, never on a tile), and a multiplied photo of a fixed height whose source the test
# sets late (#late: a lazy picture, no width before).
INK_RECT = '<rect x="10" y="10" width="100" height="20" fill="black"/>'
INK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="40">' + INK_RECT + '</svg>'
PHOTO = svg(120, 80, '<rect width="120" height="80" fill="white"/>'
                     '<circle cx="60" cy="40" r="30" fill="rgb(200,40,40)"/>')
# A product photo shot on white, opaque (a JPEG): a shaded can on a white
# background; an editorial photo filling its frame (a sky over a field).
SHOT_BODY = ('<rect width="%d" height="%d" fill="white"/><defs><linearGradient id="c">'
             '<stop offset="0" stop-color="rgb(180,20,30)"/><stop offset="1" stop-color="rgb(60,10,10)"/>'
             '</linearGradient></defs><rect x="25%%" y="15%%" width="50%%" height="70%%" rx="6" fill="url(#c)"/>')
SHOT_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="100">%s</svg>'
            % (SHOT_BODY % (120, 100))).encode("utf-8")
SHOT = svg(120, 100, SHOT_BODY % (120, 100))
SCENE = ('<defs><linearGradient id="s" x2="0" y2="1"><stop offset="0" stop-color="rgb(90,150,220)"/>'
         '<stop offset="1" stop-color="rgb(230,240,250)"/></linearGradient></defs>'
         '<rect width="120" height="80" fill="url(#s)"/><rect y="55" width="120" height="25" fill="rgb(60,120,40)"/>')
# #shot fills an absolute box in its card, taller than the photo (fitted
# with object-fit: contain, empty bands above and below it), with a label
# in white laid on the lower band, and fades in once loaded (as migros.ch
# shows its product photos).
CARD = ('<article class="card"><img id="shot" class="fade-in" onload="this.classList.add(\'loaded\')"'
        ' src="' + SHOT + '"><span id="badge">2 for 1</span></article>')
PICTURES = (
    ("photo", PHOTO, 'class="blend" width="120" height="80"'),
    ("hero", PHOTO, 'class="blend" style="width:100%; height:80px; margin:0"'),
    ("fit", PHOTO, 'class="blend" style="width:120px; height:120px; object-fit:contain"'),
    ("ink", "/ink.svg", 'width="120" height="40"'),
    ("mark", svg(120, 40, INK_RECT), 'width="120" height="40"'),
    ("navy", svg(120, 40, INK_RECT.replace("black", "rgb(20,40,120)")), 'width="120" height="40"'),
    ("puck", svg(120, 80, '<defs><linearGradient id="g"><stop offset="0" stop-color="black"/>'
                          '<stop offset="1" stop-color="rgb(80,80,80)"/></linearGradient></defs>'
                          '<rect x="10" y="10" width="100" height="60" rx="20" fill="url(#g)"/>'),
     'width="120" height="80"'),
    ("far", "", 'width="120" height="40"'),
    ("sun", svg(120, 40, INK_RECT.replace("black", "rgb(255,200,0)")), 'width="120" height="40"'),
    ("opaque", svg(120, 80, SCENE), 'width="120" height="80"'),
    ("round", svg(64, 64, SHOT_BODY % (64, 64)), 'style="width:64px; height:64px; border-radius:50%"'),
    ("icon", svg(16, 16, '<rect x="2" y="2" width="12" height="12" fill="black"/>'), 'width="16" height="16"'),
) + tuple(
    ("line%d" % (i + 1), svg(24, 24, '<path d="M3 21 L12 3 L21 21 Z" fill="none" stroke="black" stroke-width="1"/>'
                                     '<circle cx="12" cy="15" r="%d" fill="none" stroke="rgb(230,0,0)"'
                                     ' stroke-width="1.5"/>' % r), 'width="24" height="24"')
    for i, r in enumerate((1, 2, 3))
) + (
    ("avatar", svg(32, 32, '<defs><radialGradient id="a"><stop offset="0" stop-color="rgb(160,130,110)"/>'
                           '<stop offset="1" stop-color="black"/></radialGradient></defs>'
                           '<circle cx="16" cy="16" r="16" fill="url(#a)"/>'), 'width="32" height="32"'),
    ("blendicon", svg(24, 24, '<rect x="4" y="4" width="16" height="16" fill="black"/>'),
     'class="blend" width="24" height="24"'),
    ("late", "", 'class="blend" style="height:80px"'),
)
TILE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#shop {background:rgb(255,255,255); padding:20px 0}
#shop img {display:block; margin:12px}
.blend {mix-blend-mode:multiply}
.card {position:relative; width:140px; height:160px; background:rgb(255,255,255)}
.card img {position:absolute; inset:10px; width:120px; height:140px; margin:0; object-fit:contain}
#badge {position:absolute; left:14px; top:132px; font:bold 12px sans-serif; color:rgb(255,255,255);
  background:rgb(220,80,0); padding:0 2px}
.fade-in {opacity:0; transition:opacity 0.3s}
.fade-in.loaded {opacity:1}
</style></head><body>""" + TEXT + '<div id="shop">' + "".join(
    '<img id="%s"%s %s>' % (name, ' src="%s"' % src if src else "", attrs)
    for name, src, attrs in PICTURES) + CARD + "</div></body></html>"
TILED = "return document.getElementById(arguments[0]).getAttribute(arguments[1])"
# The tile around a picture as shown (drawn in the chrome): the darkest
# channel within 3 px of each corner of the picture (the picture's own
# corner meeting the margin), and that of the tile's outer corner pixel.
CORNERS = """
const [x, y, w, h, pad] = arguments;
const win = gBrowser.selectedBrowser.browsingContext.currentWindowGlobal;
return win.drawSnapshot(new DOMRect(x - pad, y - pad, w + 2 * pad, h + 2 * pad), 1, "rgb(0, 0, 0)").then((bmp) => {
  const c = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  c.width = bmp.width; c.height = bmp.height;
  const g = c.getContext("2d");
  g.drawImage(bmp, 0, 0);
  const px = g.getImageData(0, 0, c.width, c.height).data;
  const at = (i, j) => Math.min(px[(j * c.width + i) * 4], px[(j * c.width + i) * 4 + 1], px[(j * c.width + i) * 4 + 2]);
  let inner = 255;
  for (const [cx, cy] of [[pad, pad], [pad + w, pad], [pad, pad + h], [pad + w, pad + h]])
    for (let i = cx - 3; i < cx + 3; i++)
      for (let j = cy - 3; j < cy + 3; j++)
        inner = Math.min(inner, at(i, j));
  return [inner, at(0, 0)];
});"""
# The darkest channel of the brightest pixel of a rect of the page as
# shown (drawn in the chrome).
BRIGHTEST = """
const [x, y, w, h] = arguments;
const win = gBrowser.selectedBrowser.browsingContext.currentWindowGlobal;
return win.drawSnapshot(new DOMRect(x, y, w, h), 1, "rgb(0, 0, 0)").then((bmp) => {
  const c = document.createElementNS("http://www.w3.org/1999/xhtml", "canvas");
  c.width = bmp.width; c.height = bmp.height;
  const g = c.getContext("2d");
  g.drawImage(bmp, 0, 0);
  const px = g.getImageData(0, 0, c.width, c.height).data;
  let best = 0;
  for (let i = 0; i < px.length; i += 4)
    best = Math.max(best, Math.min(px[i], px[i + 1], px[i + 2]));
  return best;
});"""
LOADED = "return [...document.images].every((i) => !i.src || i.complete);"

# Inline SVG logos in a fixed header, see-through, on a page Dark Reader
# darkens; Dark Reader inverts both (a "logo" class, dark fills in their
# markup on nothing). #styled's shapes are painted by the page's style
# sheet (next.ink's .next-logo path { fill: var(--color-text) }), which
# Dark Reader lightens: its ink is light already, the invert must go.
# #plain's dark fills come from its attributes only: the invert stays.
LOGO_PATHS = ('<path d="M2 2h40v24H2z" fill="#242424"/><path d="M50 2h40v24H50z" fill="#242424"/>'
              '<path class="accent" d="M96 2h16v24H96z" fill="#4F62FF"/>')
LOGO = '<svg id="%s" class="%s" width="115" height="29" viewBox="0 0 115 29" fill="none" xmlns="http://www.w3.org/2000/svg">' + LOGO_PATHS + '</svg>'
LOGO_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
:root {--color-text: #242424}
html, body {margin:0; background:rgb(255,255,255); color:var(--color-text)}
header {position:fixed; top:0; left:0; right:0; height:60px; background:rgb(255,255,255)}
.styled-logo path {fill: var(--color-text)}
.styled-logo .accent {fill: rgb(79, 98, 255)}
main {padding-top:80px}
</style></head><body><header>""" + LOGO % ("styled", "styled-logo") + LOGO % ("plain", "plain-logo") + \
    "</header><main>" + TEXT * 4 + "</main></body></html>"
FILTER = "return getComputedStyle(document.getElementById(arguments[0])).filter;"


# Glyphs drawn with a background in a header on a page Dark Reader
# darkens, painted in the page's navy text colour, as boursorama.com draws
# its menu button: an empty <span> 26x3 and its ::before and ::after, in a
# <button> (#burger); three empty <i> bars in a small <div> (#bars, no
# control). Dark Reader darkens them as backgrounds. Left alone: a thin rule
# of the page in its light grey (#rule, wide), a short separator in a
# line of text (#sep, outside any control), a coloured pill in a link
# (#pill, thicker), and a bar in a light accent colour that still reads
# (#accent). #rule and #sep, and a vertical separator between a logo and a
# title in the header (#divider, admin.ch's div.logo__separator, 1x70 in
# light grey), are thin rules: painted a light neutral (RULE).
GLYPH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(26,46,69)}
#wrap {background:rgb(255,255,255); min-height:100vh}
header {height:60px; display:flex; align-items:center; gap:20px; padding:0 20px}
button {color:inherit; background:none; border:0; padding:0; width:40px; height:40px; position:relative}
.box {position:absolute; left:7px; top:10px; width:26px; height:20px}
#burger, #burger::before, #burger::after {position:absolute; display:block; width:26px; height:3px;
  background-color:rgb(26,46,69)}
#burger {top:50%}
#burger::before, #burger::after {content:""}
#burger::before {top:-8px}
#burger::after {top:8px}
#bars {width:24px; height:18px; display:flex; flex-direction:column; justify-content:space-between}
#bars i {display:block; height:2px; background-color:rgb(26,46,69)}
#rule {height:1px; background-color:rgb(220,220,220); margin:10px 0}
#sep {display:inline-block; width:1px; height:14px; background-color:rgb(26,46,69); margin:0 6px}
#pill {display:inline-block; width:20px; height:8px; border-radius:4px; background-color:rgb(26,46,69)}
#accent {display:inline-block; width:20px; height:3px; background-color:rgb(255,200,0)}
#divider {display:inline-block; width:1px; height:70px; background-color:rgb(209,213,219)}
</style></head><body><div id="wrap"><header>
<button type="button"><span class="box"><span id="burger"></span></span></button>
<div id="bars"><i id="bar1"></i><i></i><i></i></div>
<a href="#"><span id="pill"></span></a><a href="#"><span id="accent"></span></a>
<div id="divider"></div><span>The federal council</span>
</header><div id="rule"></div><p>Markets<span id="sep"></span>News</p>""" + TEXT + """</div></body></html>"""
GLYPH = bg.ATTR_GLYPH
RULE = bg.ATTR_RULE
PART_BG = "return getComputedStyle(document.getElementById(arguments[0]), arguments[1]).backgroundColor;"
PART_COLOR = "return getComputedStyle(document.getElementById(arguments[0]), arguments[1]).color;"
RING = "return getComputedStyle(document.getElementById(arguments[0])).boxShadow;"
TILED_IS = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === arguments[2];"

# White blocks on a light page, which Dark Reader turns into opaque
# near-black panels: a strip of links across the window at its top
# (#meta, postfinance.ch's metanavigation), news cards with a fine border
# (#news, admin.ch's div.card) whose content box is white too (#body), a
# secondary button on a card (#more, white with a border), as boursorama.com
# and postfinance.ch draw them. Left alone: a coloured button (#buy), a
# fixed dialog (#dialog, a cookie notice), a popup menu over the page
# (#menu, absolute with a z-index), a player's black box (#player, a
# <canvas> filling it). Before them in the page's order, a closed menu of
# more links than INK_ELEMENTS, indented (more nodes than INK_NODES with
# the blank ones), as boursorama.com's header holds: the cards are still
# read. A card whose empty ::before paints a white band along its top
# (#banded, raiffeisen.ch's teaser card): veiled, the band cleared. Kept
# opaque: a caption card laid over the foot of its photo (#caption, the
# same teaser) and a card on a hero's background picture (#herocard).
# Veiled: a card (#below, ldlc.com's div.bloc-universe) just under a cover
# image cut down to its frame (overflow hidden), whose own box runs over
# the card.
# the hero's photo (/hero.svg), dark: Dark Reader hides a large light
# background picture
HERO_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80">'
            '<rect width="120" height="80" fill="rgb(30,60,90)"/><circle cx="60" cy="40" r="30" fill="rgb(200,140,40)"/></svg>')
MEGA_MENU = ('<nav id="mega" hidden><ul>'
             + "".join('\n  <li>\n    <a href="#">Entry %d</a>\n  </li>' % i for i in range(1100))
             + "\n</ul></nav>")
BLOCKS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#wrap {background:rgb(255,255,255); min-height:100vh; position:relative}
#meta {background:rgb(245,245,245); height:40px; display:flex; gap:16px; align-items:center; padding:0 20px}
.cards {display:flex; gap:20px; padding:20px}
.card {background:rgb(255,255,255); border:1px solid rgb(220,220,220); width:280px}
.card__content {background:rgb(255,255,255); padding:16px}
#more {background:rgb(255,255,255); border:1px solid rgb(180,180,180); color:rgb(20,20,20); padding:6px}
#buy {background:rgb(0,102,204); color:rgb(255,255,255); border:0; padding:6px}
#menu {position:absolute; z-index:10; top:50px; left:20px; width:200px; background:rgb(255,255,255)}
#player {background:rgb(0,0,0); color:rgb(255,255,255); width:320px; height:180px; position:relative}
#player canvas {position:absolute; inset:0; width:100%; height:100%}
#dialog {position:fixed; bottom:0; left:0; width:400px; background:rgb(255,255,255); padding:10px}
#banded::before {content:""; display:block; height:16px; background:rgb(255,255,255)}
#teaser {width:400px; margin:20px}
#teaser img {display:block; width:400px; height:200px}
#caption {position:relative; margin-top:-80px; width:300px; background:rgb(255,255,255); padding:16px}
#hero {background:url("/hero.svg") center / cover; padding:40px; width:500px; margin:20px}
#cover {width:400px; height:120px; overflow:hidden; margin:20px 20px 0}
#cover img {display:block; width:400px; height:400px}
#below {background:rgb(255,255,255); border:1px solid rgb(220,220,220); width:380px; padding:10px; margin:0 20px}
#herocard {background:rgb(255,255,255); padding:16px; width:300px}
</style></head><body><div id="wrap">""" + MEGA_MENU + """<div id="meta"><a href="#">Private</a><a href="#">Business</a></div>
<div class="cards"><div class="card" id="news"><div class="card__content" id="body"><h3 id="title">Council news</h3>
<p>""" + "A short report on the latest decision of the council. " * 3 + """</p>
<button id="more" type="button">More</button> <button id="buy" type="button">Open an account</button></div></div>
<div class="card"><div class="card__content"><h3>Second card</h3><p>Another short report.</p></div></div>
<div class="card" id="banded"><div class="card__content"><h3>Third card</h3><p>A band along its top.</p></div></div></div>
<div id="teaser"><img src=""" + '"%s"' % PHOTO + """ alt=""><div id="caption"><h3>Dreams come true</h3>
<p>A caption laid over the foot of its photo.</p></div></div>
<div id="cover"><img src=""" + '"%s"' % PHOTO + """ alt=""></div><div id="below"><h3>Televisions</h3>
<p>Every screen size, from the kitchen to the living room.</p></div>
<div id="hero"><div id="herocard"><h3>On a hero</h3><p>A card on a background picture.</p></div></div>
<div id="player"><canvas width="32" height="18"></canvas><span>Live</span></div>""" + TEXT + """
<div id="menu">Menu entries over the page</div></div>
<div id="dialog">This site uses cookies to improve its offer.</div></body></html>"""
BLOCK = bg.ATTR_BLOCK

# Buttons in a saturated brand colour, which Dark Reader dulls: a link
# whose ::before paints the brand yellow from a variable under a petrol
# label in a span (#yellow, postfinance.ch's .styled-button--primary), a
# violet button with a white label (#violet, proton.me), an input button
# (#send), a crimson link whose computed colour stays oklch() (#crimson,
# letemps.ch's subscribe button), a pastel teal under a dark label (#teal).
# A black button under a white label in a fixed header (#black,
# raiffeisen.ch's E-Banking): kept, with a thin light ring. Text buttons
# whose background-color is a var() the page never sets (#ghost in the
# header, #close with no label, #aside in the text: letemps.ch's
# .lt-button--text), which Dark Reader fills with its own colour:
# see-through again. Left alone: a pale button (#pale, low chroma), a
# light grey one and a light blue one under a dark label (#grey, GitHub's
# secondary button; #tint), a banner link wider than a button (#banner), a
# coloured link with no label (#dot), a button whose label does not read
# on it (#faint), a see-through tab the page fills once darkened (#tab).
# A crimson button easing its colours (#ease, letemps.ch's subscribe
# button) that a ".dark" token scope turns coral under a dark label, while
# the page's own dark theme is tried and taken back: its own colours kept.
BRAND_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
:root {--gelb: #FFCC00}
#wrap {background:rgb(255,255,255); min-height:100vh}
.styled-button {position:relative; z-index:0; display:inline-block; padding:12px 24px; color:rgb(0,75,90)}
.styled-button::before {content:""; position:absolute; inset:0; z-index:-1; border-radius:24px;
  background-color:var(--gelb)}
#violet {background:rgb(109,74,255); color:rgb(255,255,255); border:0; padding:10px 20px}
#send {background:rgb(220,53,69); color:rgb(255,255,255); border:0; padding:10px 20px}
#pale {background:rgb(232,240,254); color:rgb(26,115,232); border:0; padding:10px 20px}
#banner {display:block; width:900px; height:200px; background:rgb(0,102,204); color:rgb(255,255,255)}
#dot {display:inline-block; width:20px; height:20px; background:rgb(255,0,0)}
#faint {background:rgb(255,204,0); color:rgb(255,255,255); border:0; padding:10px 20px}
#crimson {background:oklch(0.4199 0.1684 19.11); color:rgb(255,255,255); padding:10px 20px}
#teal {background:rgb(126,201,197); color:rgb(20,20,20); padding:10px 20px}
#grey {background:rgb(246,248,250); color:rgb(36,41,47); border:1px solid rgb(208,215,222); padding:10px 20px}
#tint {background:rgb(219,234,254); color:rgb(30,58,138); border:0; padding:10px 20px}
#top {position:fixed; top:0; left:0; right:0; height:60px; background:rgb(255,255,255)}
#black {background:rgb(26,26,26); color:rgb(255,255,255); padding:10px 20px}
.lt-button {background-color:var(--c-button-background); color:rgb(20,20,20); border:0; padding:10px}
.lt-button:not(.lt-button--text) {--c-button-background: rgb(255,255,255)}
#tab.on {background:rgb(240,240,240)}
#ease {background:rgb(176,20,50); color:rgb(255,255,255); padding:10px 20px; transition:background-color 2s, color 2s}
.dark #ease {background:rgb(240,99,104); color:rgb(20,20,20)}
</style></head><body><div id="wrap">
<div id="top"><a id="black" href="#">E-Banking</a> <button id="ghost" class="lt-button lt-button--text">Menu</button>
<button id="close" class="lt-button lt-button--text" aria-label="Close"></button></div>
<div style="height:60px"></div>""" + TEXT + """
<p><a id="crimson" href="#">S'abonner</a> <a id="teal" href="#">Je m'inscris</a>
<button id="aside" class="lt-button lt-button--text">Partager</button>
<button id="grey" type="button">Code</button> <button id="tint" type="button">Tint</button>
<a id="tab" href="#">Tab</a> <a id="ease" href="#">S'abonner</a></p>
<p><a id="yellow" class="styled-button" href="#"><span id="label">Fermer</span></a>
<button id="violet" type="button">Get Proton for free</button>
<input id="send" type="submit" value="Send"></p>
<p><button id="pale" type="button">Pale</button> <a id="dot" href="#"></a>
<button id="faint" type="button">Faint</button></p>
<a id="banner" href="#">A large banner in a brand colour</a></div></body></html>"""
BRAND = bg.ATTR_BRAND


# A Stacks page as Stack Overflow serves it signed out (no dark theme):
# filled buttons and a search field painted from the Stacks variables,
# with their chains of var() fallbacks.
STACKS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
:root {--white: hsl(0,0%,100%); --blue-400: hsl(210,77%,46%); --black-300: hsl(210,8%,75%);
  --theme-secondary-400: var(--blue-400)}
.s-btn {--_bu-filled-bg: var(--theme-button-primary-background-color, var(--theme-secondary-400));
  display:inline-block; padding:8px; color:#fff; border:1px solid transparent}
.s-btn.s-btn__filled {background-color:var(--_bu-filled-bg)}
.s-input {--_in-bg: var(--white); --_in-bc: var(--black-300);
  background-color:var(--_in-bg); border:1px solid var(--_in-bc); width:300px}
#wrap {background:rgb(255,255,255); min-height:100vh}
</style></head><body class="unified-theme"><div id="wrap">""" + TEXT + """
<a id="ask" class="s-btn s-btn__filled" href="#">Ask Question</a>
<input id="search" class="s-input" placeholder="Search"></div></body></html>"""
STACKS = "stackoverflow.com.css"
STACKS_HOST = "stackoverflow.test"


def stacks_sites():
    """The bundled Stack Overflow style and its site fix, under a .test
    host."""
    return bundled_site(STACKS, STACKS_HOST + ".css")


def bundled_site(key, name):
    """The bundled style `key` and its site fix, as the style `name` (of a
    .test host)."""
    data = os.path.join(tone.REPO, "data")
    with open(os.path.join(data, "styles.json"), encoding="utf-8") as f:
        style = json.load(f)["website"][key]
    with open(os.path.join(data, bg.SITES_OWN_DIR, key), encoding="utf-8") as f:
        fix = f.read()
    tmp = tempfile.mkdtemp()
    try:
        with open(os.path.join(tmp, "styles.json"), "w", encoding="utf-8") as f:
            json.dump({"website": {name: style}}, f)
        os.mkdir(os.path.join(tmp, bg.SITES_OWN_DIR))
        with open(os.path.join(tmp, bg.SITES_OWN_DIR, name), "w", encoding="utf-8") as f:
            f.write(fix)
        return bg.sites_load(tmp)
    finally:
        shutil.rmtree(tmp)


# A Wikipedia article as its skin paints it, day and night (the night
# theme follows the system here): the infobox's cells and lines, its
# header and section bars in the colour of the infobox's kind (frwiki's
# .entete and caption, inline), a hatnote banner (frwiki), a plain hatnote
# (enwiki), and the search field on its form.
WIKI_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(32,33,34)}
html.night, html.night body {background:rgb(16,16,16); color:rgb(234,236,240)}
.night .infobox td, .night .infobox th, .night .infobox p {background:rgb(32,33,34)}
.night .entete, .night caption {background-color:rgb(12,12,12) !important}
.bandeau-container {background:rgb(255,255,255); border:1px solid rgb(162,169,177)}
.night .bandeau-container, .night .hatnote {background:rgb(32,33,34)}
.cdx-search-input {background:rgb(255,255,255); border:1px solid rgb(162,169,177)}
.night .cdx-search-input {background:rgb(16,20,24)}
.cdx-text-input__input {background:rgb(255,255,255); border:1px solid rgb(162,169,177)}
.night .cdx-text-input__input {background:rgb(16,16,16)}
</style><script>
const mq = matchMedia("(prefers-color-scheme: dark)");
const paint = () => document.documentElement.classList.toggle("night", mq.matches);
paint();
mq.addEventListener("change", paint);
</script></head><body>
<form id="form" class="cdx-search-input"><input id="field" class="cdx-text-input__input"></form>
<div id="banner" class="bandeau-container hatnote">For the homonymous articles, see Switzerland.</div>
<div id="note" class="hatnote">This article is about the country.</div>""" + TEXT + """
<div class="infobox_v3 infobox" style="width:320px"><div id="head" class="entete"
style="background-color: #e3e3e3;">Swiss Confederation</div><p id="line">(de) Schweiz</p>
<table><caption id="bar" style="background-color:#e3e3e3;">Geography</caption>
<tr><th id="label">Capital</th><td id="cell">Bern</td>
<td id="own" style="background:rgb(200,30,40)">Party</td></tr></table></div></body></html>"""
WIKI = "+wikipedia.org.css"
WIKI_HOST = "fr.wikipedia.test"

# A page whose only opaque surface is a white column (ch.ch): its left
# half, its navy text and a tagline on a white label, a white popup menu
# laid over it, the rest of the page see-through, with light words there
# (a heading drawn for a dark hero).
PANEL_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; color:rgb(10,30,80)}
#row {display:flex; min-height:100vh}
#left {width:50vw; background:rgb(255,255,255)} #right {flex:1}
#claim {position:relative; background:rgb(255,255,255)} .hero {color:rgb(250,250,250)}
#pop {position:absolute; top:40px; left:20px; background:rgb(255,255,255)}
</style></head><body><div id="row"><div id="left"><p><span id="claim">The federal portal</span></p>
<div id="pop">A menu over the page</div>""" + (
    "<p>" + "Navy text of the page on its white column. " * 4 + "</p>") * 3 + """</div>
<div id="right"><h1 class="hero">Light words on the glass</h1><p class="hero">Over a picture once</p></div>
</div></body></html>"""
# A page's view swapped (a single-page app): first light text and one navy
# line on the glass of a dark theme (the line inked light), then the light
# text gone and the theme class set: the navy line is a light page.
SWAP_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0} #lights {color:rgb(240,240,240)} #navy {color:rgb(10,30,80)}
</style></head><body><div id="lights">""" + (
    "<p>" + "Light text of the dark view. " * 6 + "</p>") * 4 + """</div>
<p id="navy">""" + "Navy text of the light view. " * 6 + """</p></body></html>"""
# A see-through fixed footer of a dark page (half the window wide: no
# bar), its left line of navy text over a white box of the page under it,
# its right one over the glass.
FOOTER_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; color:rgb(235,235,235)}
#box {position:absolute; left:0; top:calc(100vh - 120px); width:30vw; height:120px; background:rgb(255,255,255)}
#foot {position:fixed; left:0; bottom:0; width:50vw; height:40px; display:flex; z-index:2}
#foot p {margin:0; color:rgb(10,30,80)} #onbox {width:30vw} #onglass {margin-left:5vw}
</style></head><body>""" + ("<p>" + "Light text of a dark page. " * 6 + "</p>") * 4 + """
<div id="box"></div><footer id="foot"><p id="onbox">Navy claim</p><p id="onglass">Navy link</p></footer>
</body></html>"""
# A light page with sections of the opposite tone (MeteoSuisse's forecast
# hero): a dark one holding white text, and a full-width one in a shadow
# tree, white text of its own and a heading slotted in from the page; a
# white section of navy text beside them; at the end a dark one that grows
# to fill the window once kept.
OWN_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(10,30,80)}
#hero, #big {background:rgb(28,40,52); color:rgb(255,255,255); padding:20px}
#slotted {color:rgb(255,255,255)} #plain {background:rgb(255,255,255)}
</style></head><body>""" + TEXT + """<section id="hero"><h2 id="herotitle">Forecast</h2>
<p id="herotext">White text drawn for its own dark section.</p></section>
<div id="host"><h2 id="slotted" slot="title">A heading slotted in</h2></div>
<section id="plain">""" + TEXT + """</section>
<section id="big"><p id="bigtext">White text of a section filling the window.</p></section>
<script>
document.getElementById("host").attachShadow({mode: "open"}).innerHTML = "<style>"
  + "section {background:rgb(28,40,52); color:rgb(255,255,255); min-height:300px; padding:20px}</style>"
  + "<section id='shero'><slot name='title'></slot><p id='stext'>White text in a shadow tree.</p></section>";
</script></body></html>"""
SHADOW = ("const el = document.getElementById('host').shadowRoot.getElementById(arguments[0]);"
          " return arguments[1] ? el.hasAttribute(arguments[1]) : getComputedStyle(el).backgroundColor;")
OWN_BG = "rgb(28, 40, 52)"
# A page measured dark while it loads (ch.ch): light text that goes, and
# navy text on a yellow half of its own.
YELLOW_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255)} #lights {color:rgb(240,240,240)}
#yellow {display:block; background:rgb(240,225,117); color:rgb(1,46,90); min-height:60vh; padding:20px}
</style></head><body><div id="lights">""" + (
    "<p>" + "Light text of the loading view. " * 6 + "</p>") * 4 + """</div>
<main id="yellow"><p id="yellowtext">""" + "Navy text on the yellow half. " * 6 + """</p></main></body></html>"""
# A page measured dark while it loads (MeteoSuisse): a dark section of
# white text filling the window, in a shadow tree the generic style never
# reaches, light text that goes, then navy text.
SHADOW_NIGHT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; color:rgb(10,30,80)} #lights {color:rgb(240,240,240)}
</style></head><body><x-forecast id="host"></x-forecast><div id="lights">""" + (
    "<p>" + "Light text of the loading view. " * 6 + "</p>") * 16 + """</div>""" + (
    "<p>" + "Navy text of the page. " * 6 + "</p>") * 8 + """
<script>
document.getElementById("host").attachShadow({mode: "open"}).innerHTML = `<style>
#night {display:block; background:rgb(28,40,52); color:rgb(255,255,255); min-height:100vh; padding:20px}
</style><section id="night"><p id="nighttext">Forecast</p></section>`;
</script></body></html>"""
# In the host's shadow tree: has the element the attribute given, or its
# background colour.
NIGHT = ("const el = document.getElementById('host').shadowRoot.getElementById(arguments[0]);"
         " return arguments[1] ? el.hasAttribute(arguments[1]) : getComputedStyle(el).backgroundColor;")
# A dark page with a light section (GitLab's feature cards): its dark
# heading drawn for the section's own light colour, a ::before over the
# whole section whose tint is clipped by its padding to a band across the
# middle (background-clip: content-box), the heading above the band; a
# sticky header turned white by the site over light content, its links a
# mid-grey that reads on white.
MIXED_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(24,23,29); color:rgb(236,236,239)}
#nav {position:sticky; top:0; z-index:10; height:56px; display:flex; gap:24px; align-items:center;
  padding:0 24px; background:rgb(255,255,255)}
#nav a {color:rgb(116,113,122)}
#cards {position:relative; min-height:900px; padding:40px; background:rgb(252,251,252); color:rgb(24,23,29)}
#cards::before {content:""; position:absolute; inset:0; box-sizing:border-box; padding-block:300px;
  background-clip:content-box; background-color:rgb(236,234,240)}
#cardtitle, #cardtext {position:relative; margin:0} #cardtitle {color:rgb(26,26,26)}
</style></head><body><header id="nav"><a id="navlink" href="#">Platform</a><a href="#">Pricing</a>
<a href="#">Sign in</a></header>""" + ("<p>" + "Light text of a dark page. " * 8 + "</p>") * 6 + """
<section id="cards"><h2 id="cardtitle">Ship faster. Stay in control.</h2>
<p id="cardtext">Dark text drawn for the light section.</p></section>""" + (
    "<p>" + "Light text of a dark page. " * 8 + "</p>") * 12 + "</body></html>"
MIXED_BG = "rgb(252, 251, 252)"
INK = bg.ATTR_INK
TONE_IS = "return document.documentElement.getAttribute(arguments[0]) === arguments[1];"


def stylesheet(dark_pages, sites=None):
    sites = sites or bg.Sites({}, {})
    values = bg.settings_from_json("{}")
    values.update(liveControl=True, darkPages=dark_pages)
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


SCHEME = "return getComputedStyle(document.getElementById(arguments[0])).colorScheme;"


def alpha(colour):
    """The opacity of a computed colour: rgb(), rgba() or color(srgb … / a)
    (color-mix())."""
    if colour.startswith("color("):
        return float(colour.rsplit("/", 1)[1].rstrip(") ")) if "/" in colour else 1.0
    return tone.rgba(colour)[3]


def saturation(rgba):
    """The HSL saturation of an (r, g, b, a) colour."""
    hi, lo = max(rgba[:3]) / 255, min(rgba[:3]) / 255
    light = (hi + lo) / 2
    return 0.0 if hi == lo else (hi - lo) / (1 - abs(2 * light - 1))


def read(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(tone.E2E and tone.FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class DarkenE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        cls.content_js = read("content.js")
        cls.darkreader_js = read("vendor/darkreader.js")

    def test_darken(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_darken(binary)
                self.check_left_alone(binary)
                self.check_native(binary)
                self.check_stacks(binary)
                self.check_tiles(binary)
                self.check_logos(binary)
                self.check_glyphs(binary)
                self.check_blocks(binary)
                self.check_brands(binary)
                self.check_panel(binary)

    def test_late_dark(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_late_dark(binary)

    def test_taken_back(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_taken_back(binary)

    def check_taken_back(self, binary):
        routes = {"/t.html": ("text/html; charset=utf-8", TAKEN_BACK_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/t.html", "light.test"))
            self.run_content(b)
            # its own dark theme kept first, while its text is light
            self.assertTrue(b.wait_for("return document.documentElement.classList.contains('dark');"),
                            "own dark theme not kept")
            # the dark text shows: taken back, darkened
            self.assertTrue(b.wait_for(DARKENED), "not darkened once the page shows dark text")
            self.assertNotIn("dark", b.js(CLASSES).split())
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "ease", BRAND), "crimson button not kept")
            # its own colours, not those it eased from
            self.assertEqual(b.js("return document.getElementById('ease').style"
                                  ".getPropertyValue('--browserglass-brand-fill');"), "rgb(176, 20, 50)")
            self.assertEqual(b.js(PART_COLOR, "ease", None), "rgb(255, 255, 255)")

    def check_late_dark(self, binary):
        routes = {"/d.html": ("text/html; charset=utf-8", LATE_DARK_PAGE.encode("utf-8"))}
        root = "document.documentElement"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/d.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            # the site's own dark theme comes on: Dark Reader goes
            b.js(root + ".setAttribute('data-fr-theme', 'dark');")
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader');"),
                            "Dark Reader left over the page's own dark theme")
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "own dark not dark")
            self.assertEqual(b.js("return " + root + ".getAttribute('data-fr-theme');"), "dark")
            # its own dark wrapper, or glass once found a layer of the page
            # (markCanvas may have run by then)
            self.assertEqual(b.js("return getComputedStyle(document.body).color;"), "rgb(230, 230, 230)")
            wrap = self.bg_of(b, "wrap")
            if not b.js(MARKED, "wrap", CANVAS):
                self.assertEqual(wrap, "rgb(22, 22, 22)")
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertFalse(b.js(DARKENED), "Dark Reader back over the page's own dark theme")
            # light again: Dark Reader again
            b.js(root + ".removeAttribute('data-fr-theme');")
            self.assertTrue(b.wait_for(DARKENED), "not darkened once light again")
            # a dark mark that leaves the page light: Dark Reader stays
            b.js(root + ".setAttribute('data-header-theme', 'dark');")
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertTrue(b.js(DARKENED), "a light page left undarkened")
            self.assertEqual(b.js("return " + root + ".getAttribute(arguments[0]);", tone.TONE), "dark")

    def test_wiki_panels(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_wiki_panels(binary)

    def check_wiki_panels(self, binary):
        # the bundled Wikipedia style and its site fix, night then day:
        # no solid panel in the article, a light veil and a thin border on
        # the bars and the banner, the search field translucent
        routes = {"/w.html": ("text/html; charset=utf-8", WIKI_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS) + [WIKI_HOST]))
        look = ("const s = getComputedStyle(document.getElementById(arguments[0]));"
                "return [s.backgroundColor, s.borderTopWidth];")
        sites = bundled_site(WIKI, "+wikipedia.test.css")
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, sites), prefs=prefs, firefox=binary) as b:
            for dark in (True, False):
                tone.set_scheme(b, dark)
                b.navigate(srv.url("/w.html", WIKI_HOST))
                self.run_content(b)
                self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark" if dark else "light"))
                self.assertEqual(b.js("return document.documentElement.classList.contains('night');"), dark)
                for name in ("cell", "label", "line", "note", "form"):
                    self.assertEqual(self.bg_of(b, name), "rgba(0, 0, 0, 0)", (name, dark))
                self.assertEqual(self.bg_of(b, "own"), "rgb(200, 30, 40)", "a cell's own colour lost")
                for name, most in (("head", 0.5), ("bar", 0.5), ("banner", 0.5), ("field", 0.6)):
                    fill, border = b.js(look, name)
                    self.assertTrue(0 < alpha(fill) <= most, (name, dark, fill))
                    self.assertEqual(border, "1px", (name, dark))

    def test_own_surfaces(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_own(binary)

    def run_content(self, b, excluded=(), darken=True):
        """content.js with the stored list `excluded` and darken flag
        `darken` (None: none stored)."""
        if darken is None:
            b.js(RUN, self.content_js, self.darkreader_js, list(excluded))
        else:
            b.js(RUN, self.content_js, self.darkreader_js, list(excluded), darken)

    def bg_of(self, b, element_id):
        return b.js("return getComputedStyle(document.getElementById(arguments[0])).backgroundColor;",
                    element_id)

    def check_darken(self, binary):
        routes = {"/w.html": ("text/html; charset=utf-8", WRAPPED_PAGE.encode("utf-8")),
                  "/s.css": ("text/css; charset=utf-8", b"p {}"),
                  "/s.json": ("application/json", b"{}")}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            # Dark Reader's fetch hands over stylesheets only
            self.assertEqual(b.js(FETCHED, srv.url("/s.css", "light.test")), "p {}")
            self.assertEqual(b.js(FETCHED, srv.url("/s.json", "light.test")), "refused")
            self.assertEqual(b.js(FETCHED, srv.url("/none.css", "light.test")), "refused")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS), "wrapper not marked")
            # its own dark theme was tried first, and taken back
            self.assertEqual(b.js(CLASSES), "")
            self.assertIsNone(b.js("return document.documentElement.getAttribute('data-theme');"))
            self.assertEqual(b.js("return document.documentElement.getAttribute(arguments[0]);",
                                  tone.TONE), "dark")
            text, html, body = tone.colors(b)
            self.assertGreater(tone.luminance(tone.rgba(text)), 0.179, text)
            self.assertEqual((html, body), ("rgba(0, 0, 0, 0)", "rgba(0, 0, 0, 0)"))
            self.assertEqual(self.bg_of(b, "wrap"), "rgba(0, 0, 0, 0)")
            # the grey card a light veil, not an opaque panel
            self.assertTrue(b.wait_for(TILED + " === 'veil';", mn.WAIT_TIMEOUT, "card", BLOCK), "card not veiled")
            card = tone.rgba(self.bg_of(b, "card"))
            self.assertEqual(card[3], bg.BLOCK_VEIL_OPACITY)
            self.assertLess(tone.luminance(card), 0.05, card)
            self.assertFalse(b.js(MARKED, "card", CANVAS))
            # grey text stays grey: Dark Reader gives it the hue and
            # saturation of the text colour, whose near-white (#f7f9ff) has
            # a saturation of 100%
            grey = tone.rgba(b.js("return getComputedStyle(document.getElementById('grey')).color;"))
            self.assertLessEqual(saturation(grey), 0.15, grey)
            # a frame keeps its colour scheme (Dark Reader makes every one
            # dark: a light page from another site gets an opaque backdrop),
            # one added later too
            self.assertEqual(b.js(SCHEME, "frame"), "normal")
            b.js("const f = document.createElement('iframe'); f.id = 'late'; document.body.append(f);")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('late')).colorScheme"
                                       " === 'normal';"), "a frame added later turned dark")
            # a light theme: the page's own colours, the wrapper (its lowest
            # layer) still glass, the card white again
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && document.documentElement.getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "still darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))
            self.assertEqual(self.bg_of(b, "wrap"), "rgba(0, 0, 0, 0)")
            self.assertEqual(self.bg_of(b, "card"), "rgb(240, 240, 240)")
            # the frames' own style given back
            self.assertIsNone(b.js("return document.getElementById('frame').style.colorScheme || null;"))
            # dark again
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened again")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS))
            # the helper turns darken off live: the page is given back at
            # once, the style file's colours still there; and on again
            b.js(MESSAGE, [], False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && document.documentElement.getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "still darkened with darken off")
            b.js(MESSAGE, [], True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened with darken back on")

    def check_stacks(self, binary):
        # Dark Reader maps the filled buttons and the search field to the
        # page's white, which the bundled style makes transparent; the site
        # fix gives them a fill back
        routes = {"/so.html": ("text/html; charset=utf-8", STACKS_PAGE.encode("utf-8"))}
        prefs = tone.browser_prefs()
        prefs.update(mn.test_host_prefs(list(tone.HOSTS) + [STACKS_HOST]))
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, stacks_sites()), prefs=prefs, firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/so.html", STACKS_HOST))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE))
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertEqual(self.bg_of(b, "ask"), "rgb(23, 102, 181)")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('ask')).color;"),
                             "rgb(255, 255, 255)")
            self.assertEqual(self.bg_of(b, "search"), "rgba(255, 255, 255, 0.08)")
            # light: the site's own colours
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader');"))
            self.assertEqual(self.bg_of(b, "ask"), "rgb(27, 117, 208)", "the site's own blue")

    def check_tiles(self, binary):
        routes = {"/t.html": ("text/html; charset=utf-8", TILE_PAGE.encode("utf-8")),
                  "/ink.svg": ("image/svg+xml", INK_SVG.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/t.html", "light.test"))
            b.js("document.getElementById('far').src = arguments[0];", srv.url("/ink.svg", "dark.test"))
            self.assertTrue(b.wait_for(LOADED), "pictures not loaded")
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            shop = tone.rgba(self.bg_of(b, "shop"))
            self.assertLess(tone.luminance(shop), 0.05, shop)
            # the multiplied photo on a white tile, not inverted or blended
            self.assertTrue(b.wait_for(TILED + " === 'blend';", mn.WAIT_TIMEOUT, "photo", TILE),
                            "multiplied photo not tiled")
            look = b.js("const s = getComputedStyle(document.getElementById('photo'));"
                        "return [s.mixBlendMode, s.filter, s.backgroundColor, s.boxShadow];")
            self.assertEqual(look[:3], ["normal", "none", "rgb(255, 255, 255)"])
            self.assertIn("0px 0px 0px %dpx" % bg.TILE_PAD, look[3])
            # white all through the corners where the photo meets its
            # margin (no seam of the dark background), rounded outside
            box = b.js("const el = document.getElementById('photo'); el.scrollIntoView({block: 'center'});"
                       "const r = el.getBoundingClientRect();"
                       "return [r.left + scrollX, r.top + scrollY, r.width, r.height];")
            inner, outer = b.chrome_js(CORNERS, *box, bg.TILE_PAD)
            self.assertGreaterEqual(inner, 250, "a seam at the photo's corners")
            self.assertLess(outer, 128, "the tile's outer corner not rounded")
            # see-through shaded dark ink on a white tile
            self.assertTrue(b.wait_for(TILED + " === 'ink';", mn.WAIT_TIMEOUT, "puck", TILE),
                            "puck: dark ink not tiled: %r" % b.js(TILED, "puck", TILE))
            # an opaque product photo shot on white, in an absolute box,
            # faded in: on a white tile, as it is (no filter, no blending)
            self.assertTrue(b.wait_for(TILED + " === 'photo';", mn.WAIT_TIMEOUT, "shot", TILE),
                            "photo shot on white not tiled: %r" % b.js(TILED, "shot", TILE))
            look = b.js("const s = getComputedStyle(document.getElementById('shot'));"
                        "return [s.mixBlendMode, s.filter, s.backgroundColor, s.boxShadow];")
            self.assertEqual(look[:3], ["normal", "none", "rgb(255, 255, 255)"])
            self.assertIn("0px 0px 0px %dpx" % bg.TILE_PAD, look[3])
            # fitted in its box: the tile around the photo as shown (the
            # 20 px bands above and below it left clear, the label on the
            # lower one on the dark card, not on white)
            sides = b.js("const s = document.getElementById('shot').style;"
                         "return arguments[0].map((name) => s.getPropertyValue(name));", list(bg.TILE_SIDES))
            self.assertEqual(sides, ["20px", "0px", "20px", "0px"])
            box = b.js("const el = document.getElementById('shot'); el.scrollIntoView({block: 'center'});"
                       "const r = el.getBoundingClientRect();"
                       "return [r.left + scrollX, r.top + scrollY, r.width, r.height];")
            band = [box[0] + 40, box[1] + 2, 40, 6]
            self.assertLess(b.chrome_js(BRIGHTEST, *band), 128, "the tile over the empty band")
            photo = [box[0] + 2, box[1] + 22, 10, 6]
            self.assertGreaterEqual(b.chrome_js(BRIGHTEST, *photo), 250, "the photo's white not shown")
            # a multiplied photo fitted in its box: tiled whole (the white
            # card it was blended into)
            self.assertTrue(b.wait_for(TILED + " === 'blend';", mn.WAIT_TIMEOUT, "fit", TILE), "fit not tiled")
            self.assertEqual(b.js("const s = document.getElementById('fit').style;"
                                  "return arguments[0].map((name) => s.getPropertyValue(name));",
                                  list(bg.TILE_SIDES)), ["", "", "", ""])
            # see-through dark ink of one tone, of the page's origin or a
            # data: URL, black or navy, and icons, a red accent beside
            # their lines or not: inverted to light ink, no tile around it
            for name in ("ink", "mark", "navy", "icon", "line1", "line2", "line3", "blendicon"):
                self.assertTrue(b.wait_for(TILED + " === 'invert';", mn.WAIT_TIMEOUT, name, TILE),
                                name + ": monochrome ink not inverted: %r" % b.js(TILED, name, TILE))
                look = b.js("const s = getComputedStyle(document.getElementById(arguments[0]));"
                            "return [s.filter, s.backgroundColor, s.boxShadow];", name)
                self.assertEqual(look, ["invert(%s) hue-rotate(180deg)" % bg.TILE_INVERT, "rgba(0, 0, 0, 0)", "none"], name)
            # left as they are: a full-bleed photo, a picture of another
            # origin (unreadable), a light logo, an opaque photo filling
            # its frame, a shaded avatar, a round one shot on white
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            for name in ("hero", "far", "sun", "opaque", "avatar", "round"):
                self.assertFalse(b.js(MARKED, name, TILE), name + " tiled")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('hero')).mixBlendMode;"),
                             "multiply")
            # a multiplied photo loaded late, the passes over: tiled once in
            self.assertEqual(b.js("return document.getElementById('late').getBoundingClientRect().width;"), 0)
            self.assertFalse(b.js(MARKED, "late", TILE), "late photo tiled with no width")
            b.js("document.getElementById('late').src = arguments[0];", PHOTO)
            self.assertTrue(b.wait_for(TILED + " === 'blend';", 3.0, "late", TILE),
                            "multiplied photo loaded late not tiled")
            # a light theme: the page's own white, no tile left
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && !document.querySelector('[' + arguments[0] + ']');",
                                       mn.WAIT_TIMEOUT, TILE), "still tiled under a light theme")
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('photo')).mixBlendMode;"),
                             "multiply")

    def check_logos(self, binary):
        routes = {"/l.html": ("text/html; charset=utf-8", LOGO_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/l.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            for name in ("styled", "plain"):
                self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, name, "data-darkreader-inline-invert"),
                                name + " not inverted by Dark Reader")
            fill = b.js("return getComputedStyle(document.querySelector('#styled path')).fill;")
            self.assertGreater(tone.luminance(tone.rgba(fill)), 0.4, "styled logo's ink not lightened")
            # the light ink of the styled logo shown as it is, no filter
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "styled", UNINVERT),
                            "a light logo inverted to dark")
            self.assertEqual(b.js(FILTER, "styled"), "none")
            # the dark fills of the plain one still inverted
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertFalse(b.js(MARKED, "plain", UNINVERT), "a dark logo left dark")
            self.assertIn("invert(1)", b.js(FILTER, "plain"))
            # a light theme: Dark Reader and the mark gone
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && !document.querySelector('[' + arguments[0] + ']');",
                                       mn.WAIT_TIMEOUT, UNINVERT), "still marked under a light theme")
            self.assertEqual(b.js(FILTER, "styled"), "none")

    def check_glyphs(self, binary):
        routes = {"/g.html": ("text/html; charset=utf-8", GLYPH_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/g.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS), "wrapper not marked")
            glass = b.js("return getComputedStyle(document.documentElement).getPropertyValue(arguments[0]).trim();",
                         "--browserglass-glass")
            # the menu button's three bars, and the bars in a small box,
            # painted in the text colour, which reads on the glass
            self.assertTrue(b.wait_for("return document.getElementById('burger').getAttribute(arguments[0])"
                                       " === 'self before after';", mn.WAIT_TIMEOUT, GLYPH),
                            "menu bars not marked: %r" % b.js(TILED, "burger", GLYPH))
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "bar1", GLYPH), "bars in a box not marked")
            for name, part in (("burger", None), ("burger", "::before"), ("burger", "::after"), ("bar1", None)):
                paint = b.js(PART_BG, name, part)
                self.assertEqual(paint, b.js(PART_COLOR, name, part), (name, part))
                self.assertGreaterEqual(tone.contrast(paint, glass), 2, (name, part, paint, glass))
            # left alone: a wide rule, a separator in text, a thick pill,
            # a bar that reads
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            for name in ("rule", "sep", "pill", "accent"):
                self.assertFalse(b.js(MARKED, name, GLYPH), name + " marked as a glyph")
            self.assertNotEqual(b.js(PART_BG, "pill", None), b.js(PART_COLOR, "pill", None))
            # thin rules in a neutral colour Dark Reader left without
            # contrast: a light neutral that reads on the glass
            for name in ("rule", "divider"):
                self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, name, RULE), name + " rule not marked")
                paint = tone.rgba(b.js(PART_BG, name, None))
                self.assertEqual(paint[:3], (255, 255, 255), name)
                shown = tuple(paint[3] * c + (1 - paint[3]) * g for c, g in zip(paint[:3], tone.rgba(glass)[:3]))
                self.assertGreaterEqual(tone.contrast("rgb%r" % (shown,), glass), 1.5, (name, shown, glass))
            for name in ("pill", "accent", "bar1", "burger"):
                self.assertFalse(b.js(MARKED, name, RULE), name + " marked as a rule")
            # a light theme: the page's own rules
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && !document.querySelector('[' + arguments[0] + ']');",
                                       mn.WAIT_TIMEOUT, RULE), "rules still marked under a light theme")

    def check_blocks(self, binary):
        routes = {"/b.html": ("text/html; charset=utf-8", BLOCKS_PAGE.encode("utf-8")),
                  "/hero.svg": ("image/svg+xml", HERO_SVG.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/b.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS), "wrapper not marked")
            # the card a light veil, its fine border kept; the box inside it
            # see-through; the button on it a veil of its own
            self.assertTrue(b.wait_for(TILED + " === 'veil';", mn.WAIT_TIMEOUT, "news", BLOCK),
                            "card not veiled: %r" % b.js(TILED, "news", BLOCK))
            news = tone.rgba(self.bg_of(b, "news"))
            self.assertEqual(news[3], bg.BLOCK_VEIL_OPACITY)
            self.assertLess(tone.luminance(news), 0.05, news)
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('news')).borderTopWidth;"), "1px")
            self.assertEqual(b.js(TILED, "body", BLOCK), "glass")
            self.assertEqual(self.bg_of(b, "body"), "rgba(0, 0, 0, 0)")
            self.assertEqual(b.js(TILED, "more", BLOCK), "veil")
            # a card's empty ::before in its colour (a band along its top):
            # cleared with the veil, not an opaque dark band on it
            self.assertEqual(b.js(TILED, "banded", BLOCK), "veil before")
            self.assertEqual(b.js(PART_BG, "banded", "::before"), "rgba(0, 0, 0, 0)")
            # a card over a picture keeps Dark Reader's opaque fill
            for name in ("caption", "herocard"):
                self.assertEqual(b.js(TILED, name, BLOCK), "solid", name)
                self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)
            # not a card under a picture whose overflow its frame cuts off
            self.assertEqual(b.js(TILED, "below", BLOCK), "veil")
            # the strip across the window: glass, a layer of the page
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "meta", CANVAS), "strip not glass")
            self.assertEqual(self.bg_of(b, "meta"), "rgba(0, 0, 0, 0)")
            # the text on them still light
            title = tone.rgba(b.js("return getComputedStyle(document.getElementById('title')).color;"))
            self.assertGreater(tone.luminance(title), 0.4, title)
            # left alone: the coloured button, the dialog, the popup menu,
            # the player
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            for name in ("buy", "dialog", "menu", "player"):
                self.assertIsNone(b.js(TILED, name, BLOCK), name + " veiled")
                self.assertFalse(b.js(MARKED, name, CANVAS), name + " made glass")
                self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)
            self.assertGreater(saturation(tone.rgba(self.bg_of(b, "buy"))), 0.5)
            # a light theme: the page's own white, no mark left
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && !document.querySelector('[' + arguments[0] + ']');",
                                       mn.WAIT_TIMEOUT, BLOCK), "still veiled under a light theme")
            self.assertEqual(self.bg_of(b, "news"), "rgb(255, 255, 255)")

    def check_brands(self, binary):
        routes = {"/br.html": ("text/html; charset=utf-8", BRAND_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/br.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "wrap", CANVAS), "wrapper not marked")
            # the brand fills and their labels' colours, as the page had them
            self.assertEqual(b.js(PART_BG, "yellow", "::before"), "rgb(255, 204, 0)")
            self.assertEqual(b.js(PART_COLOR, "label", None), "rgb(0, 75, 90)")
            self.assertEqual(b.js(TILED, "yellow", BRAND), "before")
            self.assertEqual(b.js(PART_BG, "violet", None), "rgb(109, 74, 255)")
            self.assertEqual(b.js(PART_COLOR, "violet", None), "rgb(255, 255, 255)")
            self.assertEqual(b.js(PART_BG, "send", None), "rgb(220, 53, 69)")
            # a fill in another colour space, a pastel under a dark label
            self.assertEqual(b.js(PART_BG, "crimson", None), "oklch(0.4199 0.1684 19.11)")
            self.assertEqual(b.js(PART_BG, "teal", None), "rgb(126, 201, 197)")
            self.assertEqual(b.js(PART_COLOR, "teal", None), "rgb(20, 20, 20)")
            # read once the page's own dark theme is taken back, not on its way
            # (its transition run out)
            self.assertTrue(b.wait_for(PART_BG.replace("return ", "return 'rgb(176, 20, 50)' === "),
                                       mn.WAIT_TIMEOUT, "ease", None), "eased: %r" % b.js(PART_BG, "ease", None))
            self.assertEqual(b.js(PART_COLOR, "ease", None), "rgb(255, 255, 255)")
            # a black button: its colours and a thin light ring
            self.assertEqual(b.js(TILED, "black", BRAND), "self lift")
            self.assertEqual(b.js(PART_BG, "black", None), "rgb(26, 26, 26)")
            self.assertEqual(b.js(PART_COLOR, "black", None), "rgb(255, 255, 255)")
            self.assertEqual(b.js(RING, "black"), "rgba(255, 255, 255, 0.25) 0px 0px 0px 1px inset")
            # text buttons Dark Reader filled from an unset var(): see-through
            for name in ("ghost", "close", "aside"):
                self.assertTrue(b.wait_for(TILED_IS, mn.WAIT_TIMEOUT, name, BRAND, "clear"), name + " not cleared")
                self.assertEqual(self.bg_of(b, name), "rgba(0, 0, 0, 0)", name)
                self.assertFalse(b.js(MARKED, name, BLOCK), name + " veiled")
            # the page fills a see-through tab once darkened: its fill stays
            b.js("document.getElementById('tab').classList.add('on');")
            b.js("return new Promise((resolve) => setTimeout(resolve, 1500));")
            self.assertFalse(b.js(MARKED, "tab", BRAND), "a tab the page filled cleared")
            self.assertGreater(alpha(self.bg_of(b, "tab")), 0)
            # left alone: a pale button, light grey and light blue ones, a
            # banner, a link with no label, a label that does not read on
            # its fill
            for name in ("pale", "grey", "tint", "banner", "dot", "faint"):
                self.assertFalse(b.js(MARKED, name, BRAND), name + " kept as a brand button")
            self.assertNotEqual(b.js(PART_BG, "pale", None), "rgb(232, 240, 254)")
            # a light theme: the page's own colours, no mark or inline style left
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader')"
                                       " && !document.querySelector('[' + arguments[0] + ']');",
                                       mn.WAIT_TIMEOUT, BRAND), "still marked under a light theme")
            self.assertIsNone(b.js("return document.getElementById('violet').getAttribute('style');"))
            self.assertEqual(b.js(PART_BG, "yellow", "::before"), "rgb(255, 204, 0)")

    def check_native(self, binary):
        routes = {"/n.html": ("text/html; charset=utf-8", NATIVE_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/n.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for("return document.documentElement.getAttribute(arguments[0]) === 'dark';",
                                       mn.WAIT_TIMEOUT, tone.TONE), "own dark theme not on")
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertFalse(b.js(DARKENED), "Dark Reader used over the page's own dark theme")
            self.assertIn("dark", b.js(CLASSES).split())
            self.assertIn("app", b.js(CLASSES).split())
            text = tone.colors(b)[0]
            self.assertGreater(tone.luminance(tone.rgba(text)), 0.179, text)
            # a light theme takes it back, the page's own class kept
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return document.documentElement.className === 'app'"
                                       " && document.documentElement.getAttribute('data-theme') === null;"),
                            "own dark theme not taken back")
            # dark again: tried again
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for("return document.documentElement.classList.contains('dark');"),
                            "own dark theme not tried again")
            self.assertFalse(b.js(DARKENED))

    def check_panel(self, binary):
        routes = {"/p.html": ("text/html; charset=utf-8", PANEL_PAGE.encode("utf-8")),
                  "/s.html": ("text/html; charset=utf-8", SWAP_PAGE.encode("utf-8")),
                  "/f.html": ("text/html; charset=utf-8", FOOTER_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            # the white column is the page's: its navy text votes, the page
            # is light and darkened
            b.navigate(srv.url("/p.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(DARKENED), "a page on a white column not darkened")
            # under a light theme the column is glass, and the white label
            # of its tagline with it (no white strip left)
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "left", CANVAS), "column not marked")
            self.assertTrue(b.wait_for("return document.getElementById('claim').getAttribute(arguments[0])"
                                       " === 'fill';", mn.WAIT_TIMEOUT, CANVAS), "tagline label not cleared")
            self.assertEqual(self.bg_of(b, "claim"), "rgba(0, 0, 0, 0)")
            self.assertFalse(b.js(MARKED, "pop", CANVAS), "a menu over the column cleared")
            # text inked light on the glass of the dark view votes with its
            # own navy once the view is light
            tone.set_scheme(b, True)
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b, darken=False)
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "dark view not dark")
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "navy", INK), "navy line not inked")
            b.js("document.getElementById('lights').remove(); document.documentElement.className = 'swap';")
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"),
                            "inked navy text voted light")
            # a see-through fixed footer: its text read on what is under it
            b.navigate(srv.url("/f.html", "dark.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "onglass", INK), "footer text on the glass not inked")
            self.assertFalse(b.js(MARKED, "onbox", INK), "footer text over a white box inked")

    def check_own(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/o.html": ("text/html; charset=utf-8", OWN_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/o.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "page not light")
            # the dark sections keep their own colour, their white text
            # reads on it: not inked
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "hero", bg.ATTR_OWN), "hero not kept")
            self.assertEqual(self.bg_of(b, "hero"), OWN_BG)
            self.assertTrue(b.wait_for(SHADOW, mn.WAIT_TIMEOUT, "shero", bg.ATTR_OWN),
                            "section in a shadow tree not kept: %s" % b.js(SHADOW, "shero", None))
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertEqual(b.js(SHADOW, "shero", None), OWN_BG)
            for name in ("herotitle", "herotext", "slotted"):
                self.assertFalse(b.js(MARKED, name, INK), name + " inked")
            self.assertFalse(b.js(SHADOW, "stext", INK), "shadow text inked")
            # the white section is cleared as before
            self.assertFalse(b.js(MARKED, "plain", bg.ATTR_OWN), "white section kept")
            self.assertEqual(self.bg_of(b, "plain"), "rgba(0, 0, 0, 0)")
            # a kept section grown to fill the window: kept, no page layer
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "big", bg.ATTR_OWN), "big section not kept")
            b.js("const big = document.getElementById('big'); window.bgLayered = false;"
                 " new MutationObserver(() => { window.bgLayered ||= big.hasAttribute(arguments[0]); })"
                 ".observe(big, {attributes: true, attributeFilter: [arguments[0]]});"
                 " big.style.minHeight = '120vh'; window.scrollTo(0, big.offsetTop);", CANVAS)
            b.js("return new Promise((resolve) => setTimeout(resolve, 1500));")
            self.assertFalse(b.js("return window.bgLayered;"), "a kept section made the page's layer")
            self.assertEqual(self.bg_of(b, "big"), OWN_BG)
            b.js("window.scrollTo(0, 0);")
            # Dark Reader: the dark section in the shadow tree is no
            # opaque slab (glass, or a light veil)
            tone.set_scheme(b, True)
            self.assertTrue(b.wait_for(DARKENED), "not darkened")
            self.assertTrue(b.wait_for(
                "const c = (() => { " + SHADOW + " })();"
                " const m = /rgba\\([^)]*,\\s*([\\d.]+)\\)/.exec(c);"
                " return c === 'transparent' || (m !== null && parseFloat(m[1]) <= arguments[2]);",
                mn.WAIT_TIMEOUT, "shero", None, bg.BLOCK_VEIL_OPACITY),
                "shadow section an opaque slab: %s" % b.js(SHADOW, "shero", None))
            # a light theme: the own colours back
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for("return !document.querySelector('style.darkreader');"), "still darkened")
            self.assertTrue(b.wait_for("const c = (() => { " + SHADOW + " })(); return c === arguments[2];",
                                       mn.WAIT_TIMEOUT, "shero", None, OWN_BG),
                            "own colour not back: %s" % b.js(SHADOW, "shero", None))
            self.assertFalse(b.js(SHADOW, "shero", CANVAS), "still glass under a light theme")
            self.assertEqual(self.bg_of(b, "hero"), OWN_BG)

    def test_mixed_tone(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_mixed_tone(binary)

    def check_mixed_tone(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/m.html": ("text/html; charset=utf-8", MIXED_PAGE.encode("utf-8"))}
        inked = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === arguments[2];"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            for dark in (True, False):
                tone.set_scheme(b, dark)
                b.navigate(srv.url("/m.html", "light.test"))
                self.run_content(b)
                with self.subTest(dark=dark):
                    self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "page not dark")
                    # the light section keeps its colour for its dark
                    # text: the ::before's band is no face behind it
                    self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "cards", bg.ATTR_OWN),
                                    "light section not kept: %s" % self.bg_of(b, "cards"))
                    self.assertEqual(self.bg_of(b, "cards"), MIXED_BG)
                    for name in ("cardtitle", "cardtext"):
                        self.assertFalse(b.js(MARKED, name, INK), name + " inked")
                    # over the light section, the header's mid-grey links
                    # are inked light on its dark veil
                    b.js("window.scrollTo(0, document.getElementById('cards').offsetTop);")
                    self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "nav", BAR), "the sticky header not a bar")
                    self.assertTrue(b.wait_for(inked, mn.WAIT_TIMEOUT, "navlink", INK, "light"),
                                    "mid-grey links on the dark veil not inked light: %s"
                                    % b.js("return document.getElementById('navlink').getAttribute(arguments[0]);",
                                           INK))

    def test_own_tone_swap(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_own_tone_swap(binary)

    def check_own_tone_swap(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/y.html": ("text/html; charset=utf-8", YELLOW_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/y.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "loading view not dark")
            # navy text on the dark glass: its yellow half kept for it
            self.assertTrue(b.wait_for(MARKED, mn.WAIT_TIMEOUT, "yellow", bg.ATTR_OWN), "yellow half not kept")
            b.js("document.getElementById('lights').remove(); document.documentElement.className = 'loaded';")
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "page not light")
            # light now, the navy text reads on the glass: the yellow half
            # is judged again, glass like the rest
            self.assertTrue(b.wait_for("return !document.getElementById('yellow').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, bg.ATTR_OWN), "yellow half still kept once light")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('yellow')).backgroundColor"
                                       " === 'rgba(0, 0, 0, 0)';"),
                            "yellow half left opaque: %s" % self.bg_of(b, "yellow"))
            self.assertFalse(b.js(MARKED, "yellowtext", INK), "navy text inked on the light glass")

    def test_own_shadow_section(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_own_shadow_section(binary)

    def check_own_shadow_section(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/s.html": ("text/html; charset=utf-8", SHADOW_NIGHT_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(False, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            # a dark theme: the page's root clear while it is dark, tinted
            # once light, glass all along
            tone.set_scheme(b, True)
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b)
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "dark"), "loading view not dark")
            # dark on the dark page: its layer
            self.assertTrue(b.wait_for(NIGHT, mn.WAIT_TIMEOUT, "night", CANVAS), "dark section no layer")
            b.js("document.getElementById('lights').remove(); document.documentElement.className = 'loaded';")
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "page not light")
            # light now, white text on it: a section of the site's own,
            # kept, no longer the page's layer (its text on the light glass)
            self.assertTrue(b.wait_for(NIGHT, mn.WAIT_TIMEOUT, "night", bg.ATTR_OWN), "dark section not kept")
            self.assertFalse(b.js(NIGHT, "night", CANVAS), "dark section left a page layer")
            self.assertEqual(b.js(NIGHT, "night"), OWN_BG)
            self.assertFalse(b.js(NIGHT, "nighttext", INK), "its white text inked")

    def left_alone(self, b, why):
        # content.js decides once the list is there and the page loaded:
        # both are by the time LIVE is set
        self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                   mn.WAIT_TIMEOUT, tone.LIVE), why)
        b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
        self.assertFalse(b.js(DARKENED), why)

    def check_left_alone(self, binary):
        routes = {"/w.html": ("text/html; charset=utf-8", WRAPPED_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", tone.DARK_PAGE.encode("utf-8")),
                  "/s.html": ("text/html; charset=utf-8", SPOOF_PAGE.encode("utf-8")),
                  "/app.html": ("text/html; charset=utf-8", tone.APP_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/d.html", "dark.test"))
            self.run_content(b)
            self.left_alone(b, "a page with a dark version")
            # a web app dark by its own style, its dark class on <body>
            # only, a black skip link out of sight: its own dark, no
            # darkening colours, no marks added on <html>
            b.navigate(srv.url("/app.html", "light.test"))
            self.run_content(b)
            self.left_alone(b, "a page dark by its own style")
            self.assertEqual(b.js("return document.documentElement.getAttribute(arguments[0]);",
                                  tone.TONE), "dark")
            self.assertEqual(b.js(CLASSES), "")
            self.assertEqual(b.js("return getComputedStyle(document.documentElement)"
                                  ".getPropertyValue('--browserglass-darken-bg');"), "")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, ["light.test"])
            self.left_alone(b, "an excluded page")
            self.assertTrue(b.js("return document.documentElement.hasAttribute(arguments[0]);", OFF))
            # the style file's colours, but the helper says no (darkPages
            # turned off, the browser not restarted), or says nothing
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "darken false")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=None)
            self.left_alone(b, "no darken stored")
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken="true")
            self.left_alone(b, "darken not a boolean")
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "darkPages off")
            # the page's own darkening colours with darkPages off (darken
            # false): under a dark theme, then a light one
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b, darken=False)
            self.left_alone(b, "colours set by the page, darken false")
            tone.set_scheme(b, False)
            b.navigate(srv.url("/s.html", "light.test"))
            self.run_content(b)
            self.left_alone(b, "colours set by the page, light theme")


if __name__ == "__main__":
    unittest.main()

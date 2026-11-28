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
  - a tall see-through fixed header at the top holding the site's links
    is marked before any scroll (a header gets the bar's veil), and stays
    marked once content lies under its lower row only (its top row a
    notice); a thin see-through strip down the right edge over the
    content is not;
  - a background rendered late inside an existing element (as an Angular
    app does) is marked once it is there;
  - a sticky nav below a hero is left alone until it sticks to the top,
    marked while it is, and left alone again back at the top;
  - a sticky header below a notice, painted by an empty layer behind its
    content in the page's colour (Bitwarden), has that layer filled, then
    is marked once stuck over a hero as large as the window, the layer
    still see-through under the veil;
  - in a web app's shell (a page that does not scroll, a pane scrolls
    inside), the header at the top gets the bar's veil (a header in the
    flow), the sidebar in the flow keeps its own look, and so do the short
    rows of links in the pane (1.3.1);
  - in a page that does not scroll, a side panel showing a picture and a
    plain block along an edge (no link, no nav role) are left alone;
  - a header in the flow at the top of a page whose body is fixed to lock
    its scroll (a dialog open) keeps the bar's veil of a header in the
    flow, in the dark surface;
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
  - icons and logos of a dark page not darkened (test_icons): in a white
    fixed header (a bar, veiled dark) a chevron drawn in its dark label's
    colour (currentColor), and on the glass a navy search icon alone in
    its link, follow the readable colour; an inline caret in a dark colour
    of its own beside that label, a black word mark from another
    origin whose server allows it (CORS), a 24 px icon of black lines
    with a red accent and a navy pictogram from another origin are
    inverted to light ink, the hues turned back; the same word mark on
    the site's own dark card, one with a filter of its own or under an
    element with one (Wikipedia's night logo), a shaded
    picture from another origin, a word mark from another origin whose
    server does not allow it, an illustrated badge (a flat dark sky,
    the rest in many tones), a mascot whose readable part is larger than
    its dark ink and an opaque photo shot on white are left alone;
  - white artwork in a site's dark header under a light theme
    (test_light_bar_icons): the header a bar with the light veil, its
    white link inked dark, a word mark painting #fff and a white icon are
    inverted to dark ink, a black icon the site whitens with its filter
    loses the filter; a colour logo and a white icon on its own red button
    are left alone;
  - page columns narrower than the window (test_columns): a feed centred
    in it, in the page's dark colour or white on a light page, and a dark
    side panel down to the bottom are marked, a card on the feed is not;
    the feed's sticky title row (its colour painted by a child) is a bar,
    its child filled, its ::after strip in the page's colour see-through;
    an app's surface right of its menu, down to near the bottom, is
    marked, its panels are not, under a light theme too (the root under
    the dark tint); the app's see-through menu down the left edge, its
    first child a scrim at opacity 0, is a bar (a sidebar holding the
    site's menus); a menu row across the window,
    dark or light, is marked, a coloured band under it is not; a coloured
    column, a column filled by a player, a light column on a dark page and
    a short card are left alone;
  - rows of a bar (test_bar_rows): a sticky header's row of links in the
    page's colour over half of it is see-through once the header is a
    bar, a menu hidden in it keeping its colour once opened, and a header whose rows were bands before it stuck still gets
    its veil; the layer behind a bar's content holding skip links is
    hidden (UNDER) until its link gets the focus, the list of links in
    the bar's colour, each link in it and a cell as tall as the bar
    see-through, a white button kept;
  - a header stuck from load (test_stuck_header): a sticky header at the
    top before any scroll, see-through but for its first row in the
    page's colour, is a bar and that row see-through, while the search
    field's box and the toggle in the row keep their colour, scrolled as
    well; a side panel down the page in a colour near the page's, holding
    a sticky list (a bar), is a page layer, see-through;
  - a late cookie banner (test_late_banner, BBC) on a light page under
    the real generic style: fixed along the bottom, inserted after load,
    its dark section kept for its light text before the box is a bar,
    is a bar whose kept section stays opaque, never filled as the bar's
    own colour, its title not inked;
  - stacked bars (test_stacked_bars): a sticky row held right under a
    sticky masthead (SRF) is a bar too, veiled, the ::before of its
    wrapper painting its colour see-through, while a sticky row the
    flow puts there before it sticks elsewhere is not; a sticky side
    column under a header (Docker's docs), in a colour near the page's
    or one of its own, is a bar, never a page layer, and the block of
    links at its top in its colour, as wide as it, is see-through; on a
    light page too, a sticky sidebar of navigation links beside a white
    content column, also scrolled;
  - a tucked bar (test_tucked_bars): a sticky row stacked under a sticky
    masthead at load, slid up under it once scrolled (BBC's sections),
    shows nothing of its covered part through the masthead's veil, its
    part below the masthead shown, and is whole again back in its place;
  - a tucked row (test_tucked_row): a see-through sticky row that is no
    bar, stuck under a tall header's lower part once scrolled (Ricardo's
    categories), shows nothing through the header's veil, whole again
    back in the flow below it;
  - a light page for a white one (test_light_glass): a strip along its
    top in a grey near the page's white is glass, a list's fade into the
    white (an empty ::after) paints nothing, under a dark theme too on a
    dark page into its colour, a fade into blue stays; a pale grey
    straight on the light glass is inked dark, on its own white card shaded;
  - pseudo-elements in the page's colour (test_page_pseudos), in the
    site's own dark and light themes and darkened by Dark Reader: the
    gutters a section draws down its sides (an empty ::before and ::after)
    are see-through, a sticky header's fade under its scroll button, no
    text in it, paints nothing; an empty strip in that colour across a
    story's top (a whitecover) is see-through; a strip in that colour on
    a red card and a cover hiding the site's content stay;
  - link cards (test_cards): on a see-through page in its own dark theme
    and in its light one, a row of opaque link cards in the tone's plain
    colour gets the block veil in the tone's surface, its border kept,
    its text box in its colour see-through, the frame of its photo and
    the photo left; a lone link card and a panel that is no link stay;
  - card parts (test_card_parts): the card is the box painted round a
    link, a link stretched over a short card from an open shadow tree and
    a face filling a frame of the page's colour included, the face
    see-through; a row of pills, of boxes of link lists, of photo cards
    and of boxes outlined round a link stay;
  - a page built of web components (test_shadow): in open shadow trees,
    its background layer, painted by an empty ::before, is marked, the
    ::before see-through, and so is a band in its colour; its fixed header and the bottom bar
    of a nested tree are bars in the dark surface (under a light theme
    too), blurred through a veil in their tree; dark text in a fixed
    see-through layer over the tree's white card, and the page's label
    slotted on the tree's red button, get no ink;
  - a white band of a light page in an open shadow tree (test_shadow_band,
    SBB), between the rows of the grid, its text slotted from the page:
    marked, see-through;
  - the site's own bars on a dark page in its own colours (test_masthead,
    GitHub), its root and body see-through, between the rows of the grid:
    a dark masthead along the page's top edge, a band holding its menus
    and a footer along its bottom edge keep their colour; a band of the
    page with neither is marked, see-through, and so is a grey bar of the
    site lighter than the dark glass, in a <header> holding a <nav>
    (IKEA's utility bar);
  - sections in the page's colour (test_sections): on a dark page cleared
    by the glass, the bands across the window in a colour near the page's
    are see-through, those below the first screen once scrolled to, a
    band in it too, one whose top shows only along the window's bottom
    edge (below the grid's last row) before any scroll; a hero's gradient from the page's colour into blue
    loses its solid top, the blue kept; a white island, a blue band and a
    grey card in a band stay; a sticky scrim in a sidebar fading the
    page's colour out paints nothing; the scrollbars of a dark page get a
    light thumb over a see-through track;
  - a page that shows an error notice on any error (test_resize_loop,
    crates.io): its window.onerror sees no ResizeObserver loop error
    while its body grows during the load, three loads in a row;
  - a column built of rows in the page's colour, stacked edge to edge
    (test_page_rows, Watson's clusters), black on a dark page, white on a
    light one: every row is see-through, below the first screen too, a
    card in a row and a blue row keep their colours; the 16px borders in
    the rows' colour (down the rows' sides, along the column's top) are
    see-through too; the white bylines on a photo in a row above the
    window keep the light page light;
  - the same rows, the headlines in teasers of the rows' colour, only
    mid-grey section titles of the other side right on the rows
    (test_page_teasers, Watson's pink titles): the page keeps its tone
    at load, dark and light;
  - boxes painting exactly the page's colour, narrower than the window
    (test_page_boxes, Heise's empty ad slots), off a page layer or on one:
    see-through, while a box with a border, one holding a picture, one
    with text of its own and a box in another grey keep theirs;
  - a light page's blue header in the flow and green hero a site style
    clears (test_cleared_header: booking.com, PyPI, crates.io): the
    header gets the bar's light veil, its white link and the hero's white title are inked dark, the
    title without its dark text-shadow, an icon-font glyph (an empty <i>
    drawing its ::before) is inked dark, the white word mark follows the
    links (inverted), and one on its own blue button stays white, as
    does a colour logo in white, yellow and blue (PyPI's);
  - a dark page's fixed header (test_accent_link, watson.ch): its
    mid-grey link is inked light for the veil over a light section,
    while its pink active link, which reads on the veil, keeps its colour.
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
import test_e2e_wallglass as wg  # noqa: E402

bg = dk.bg
CANVAS, BAR, UNDER = bg.ATTR_CANVAS, bg.ATTR_BAR, bg.ATTR_UNDER
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
# A sticky header below a notice (Bitwarden): see-through, painted by an
# empty layer behind its content (absolute, inset 0, z-index -10, clicks
# passing through) in the page's colour, over a hero as large as the
# window once scrolled.
LAYER_BAR_PAGE = STYLE + """
html, body {background:transparent}
#wrap {background:rgb(16,16,16)}
#notice {height:40px}
header {position:sticky; top:0; height:68px; z-index:50}
#paint {position:absolute; inset:0; z-index:-10; pointer-events:none; background:rgb(16,16,16)}
#hero {height:95vh; background:rgb(40,60,120)}
</style></head><body><div id="wrap"><div id="notice">Notice</div>
<header id="bar"><div id="paint"></div><nav><a href="#">Pricing</a></nav></header>
<div id="hero">Hero</div><div id="long">""" + dk.TEXT + """</div></div></body></html>"""

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
# Dark text on see-through layers (the glass behind it), and on a white card
# (half the window wide: a band across it is the page's);
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
#card {width:50vw; background:rgb(255,255,255)}
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
# it a large opaque form (a floating layer: the bar's veil); a modal fixed
# itself. Neither is the page's background.
BANNER_PAGE = STYLE + """
#wrap {position:fixed; inset:0; background:transparent; z-index:5}
#consent {position:absolute; inset:5% 2%; background:rgb(40,40,60)}
#modal {position:fixed; inset:0; background:rgb(50,40,40); z-index:6; display:none}
</style></head><body><div id="long">""" + dk.TEXT + """</div>
<div id="wrap"><form id="consent">Cookies</form></div><div id="modal">Modal</div></body></html>"""
# A light page under the real generic style (BBC): a cookie banner fixed
# along the bottom, inserted late deep in the page (no pass of the layers
# follows), its see-through box covered by a dark section of its own
# holding light text (KEPT), read before the box is a bar (a picture
# loaded: a pass of the text only).
COOKIE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(20,20,20)}
#long {height:300vh}
#prompt {position:fixed; left:0; right:0; bottom:0; z-index:10}
#notice {height:75px; background:rgb(50,50,50); color:rgb(190,190,190)}
#notice h2 {margin:0; color:rgb(255,255,255)}
</style></head><body><div id="long">""" + dk.TEXT + """</div><div><div id="slot"></div></div></body></html>"""
COOKIE = ("document.getElementById('slot').innerHTML = '<div id=\"prompt\"><section id=\"notice\">"
          "<h2 id=\"title\">Let us know you agree to cookies</h2><p>We use cookies.</p></section></div>';")
PICTURE = ("const img = new Image(1, 1); img.src = arguments[0];"
           "document.getElementById('long').prepend(img);")
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
# and round corners; a row of panels on it (veiled as cards are). The menu's first child is a drawer's
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
# A sticky header in two rows (MDN), both in the page's colour, nothing
# else painting it: the breadcrumbs row under the points of markCanvas is
# a band across the window (glass), the row of links above it (over half
# the header) is not; a menu hidden in that row keeps its colour once
# opened. With a notice above the header (ROW_NOTICE_PAGE),
# the row of links is a band too before the header sticks, then both.
ROW_BAR_PAGE = STYLE + """
html, body {background:transparent}
#notice {height:60px; background:rgb(40,60,120)}
#rowbar {position:sticky; top:0; z-index:5}
#row {height:50px; background:rgb(24,25,27)} #drop {display:none; position:absolute; height:200px; background:rgb(24,25,27)} #crumbs {height:40px; background:rgb(24,25,27)}
#long {height:auto}
</style></head><body><header id="rowbar"><nav id="row"><a href="#">CSS</a><div id="drop">Menu</div></nav><div id="crumbs">Web</div></header>
<div id="wrap"><div id="long">""" + dk.TEXT * 30 + """</div></div></body></html>"""
ROW_NOTICE_PAGE = ROW_BAR_PAGE.replace('<header id="rowbar">', '<div id="notice">Notice</div><header id="rowbar">')
# A sticky bar backed by a layer behind its content (ARTE): the layer
# (absolute, z-index -1) holds the skip links the header covers; the list
# of links in the middle of the header paints the bar's colour, each link
# in it too, and so does the cell of a language menu as tall as it; the
# header itself see-through (as the generic style leaves a <header>). No layer of
# the page's background.
SKIP_BAR_PAGE = STYLE + """
html, body {background:transparent}
#skipbar {position:sticky; top:0; z-index:100; display:flex; height:56px}
#skip {position:absolute; z-index:-1; width:100%; height:100%; display:flex; justify-content:space-around;
  background:rgb(21,21,21)}
#skip:focus-within {z-index:2}
#skiphead {width:100%; display:flex; align-items:center}
#links {width:50%; height:48px; background:rgb(21,21,21)} #list {margin:0; height:100%; background:rgb(21,21,21)}
#item {display:inline-block; padding:12px; background:rgb(21,21,21)} #lang {width:72px; height:56px; background:rgb(21,21,21)}
#cta {background:rgb(255,255,255); color:rgb(0,0,0)}
#long {height:auto}
</style></head><body><div id="skipbar"><div id="skip"><a id="skiplink" href="#long">Skip to the content</a></div>
<header id="skiphead"><a href="#">Logo</a><div id="links"><ul id="list"><li><a id="item" href="#">Guide</a></li></ul></div>
<a id="cta" href="#">Sign up</a><div id="lang">FR</div></header></div><div id="long">""" + dk.TEXT * 30 + """</div></body></html>"""
# Stacked bars (SRF): a sticky masthead, a sticky sub-navigation held
# right under it (top 72px) in a colour of its own, painted again by its
# wrapper's empty ::before (absolute, z-index -1) over the shadow its
# ::after casts (z-index -2), then a sticky row of
# tabs the flow puts under that one but that sticks at the top.
STACK_PAGE = STYLE + """
html, body {background:transparent}
#mast {position:sticky; top:0; z-index:10; height:72px; background:rgb(34,33,29)}
#sub {position:sticky; top:72px; z-index:9; height:76px; background:rgb(46,45,41)}
#subwrap {height:100%}
#subwrap::before {content:""; position:absolute; inset:0; z-index:-1; background:rgb(46,45,41)}
#subwrap::after {content:""; position:absolute; top:34px; bottom:0; left:0; right:0; z-index:-2;
  box-shadow:0 4px 8px rgba(0,0,0,0.16)}
#tabs {position:sticky; top:0; z-index:8; height:40px; background:rgb(46,45,41)}
#long {height:auto}
</style></head><body><header id="mast"><a href="#">News</a></header>
<nav id="sub"><div id="subwrap"><a href="#">Live TV</a></div></nav>
<div id="tabs"><a href="#">Latest</a></div><div id="long">""" + dk.TEXT * 30 + """</div></body></html>"""
# A sticky row tucked under a higher sticky bar (BBC's sections): held
# right under the masthead at load (a bar, stacked), it slides up under it
# once scrolled (top -24px, the masthead covering its upper part), as the
# site hides it behind the masthead's opaque fill. A red chip in each part
# of the row: the one under the masthead must not show through its veil,
# the one below it stays.
TUCK_PAGE = STYLE + """
html, body {background:transparent}
#mast {position:sticky; top:0; z-index:10; height:64px; background:rgb(34,33,29)}
#row {position:sticky; top:64px; z-index:9; height:120px; background:rgb(46,45,41)}
.chip {position:absolute; left:20px; width:200px; background:rgb(255,0,0)}
#hid {top:34px; height:20px} #shown {top:98px; height:16px}
#long {height:auto}
</style></head><body><header id="mast"></header>
<nav id="row"><a class="chip" id="hid" href="#"></a><a class="chip" id="shown" href="#"></a></nav>
<div id="long">""" + dk.TEXT * 30 + """</div></body></html>"""
# A sticky row that is no bar tucked under a sticky header (Ricardo's
# category row, top 74px under a 131px header, see-through): in the flow
# below the header at load, it sticks under the header's lower half once
# scrolled, as the site hides it behind the header's opaque fill. A red
# chip in it must not show through the header's veil.
TUCK_ROW_PAGE = STYLE + """
html, body {background:transparent}
#head {position:sticky; top:0; z-index:3; height:131px; background:rgb(34,33,29)}
#cats {position:sticky; top:74px; z-index:2; height:40px}
#cat {position:absolute; left:20px; top:10px; width:200px; height:20px; background:rgb(255,0,0)}
#long {height:auto}
</style></head><body><header id="head"><a href="#">Shop</a></header>
<div id="cats"><a id="cat" href="#"></a></div>
<div id="long">""" + dk.TEXT * 30 + """</div></body></html>"""
# The reddest pixel (red over green) of a rect
# of the page as shown (drawn in the chrome).
REDDEST = """
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
    best = Math.max(best, px[i] - px[i + 1]);
  return best;
});"""
# A sticky side column under a header (Docker's docs), in a plain dark
# colour near a page's, its block of links at the top in that colour
# too: as wide as the column, not a fifth of it. A bar all the same,
# never a page layer, as is the same column in a blue of its own
# (BAR_SIDE_PAGE).
SIDE_PAGE = STYLE + """
#top {position:sticky; top:0; z-index:20; height:64px; background:rgb(0,61,181)}
#cols {display:flex; align-items:flex-start}
#side {position:sticky; top:64px; width:320px; height:calc(100vh - 64px); background:rgb(36,40,52)}
#links {width:300px; height:178px; background:rgb(36,40,52)}
#main {flex:1}
#long {height:auto}
</style></head><body><header id="top"><a href="#">Docs</a></header><div id="cols"><aside id="side">
<div id="links"><a href="#">Get started</a></div></aside><main id="main"><div id="long">""" + dk.TEXT * 30 + """</div>
</main></div></body></html>"""
BAR_SIDE_PAGE = SIDE_PAGE.replace("rgb(36,40,52)", "rgb(20,30,60)")
# The same on a light page (Docker's docs under a light theme): a white
# content column beside a sticky sidebar in a pale grey holding a list of
# navigation links, both under a sticky blue header, the page see-through.
NAV_SIDE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(20,20,20)}
#top {position:sticky; top:0; z-index:20; height:64px; background:rgb(17,85,204); color:rgb(255,255,255)}
#top a {color:inherit}
#cols {display:flex; align-items:flex-start}
#side {position:sticky; top:64px; width:320px; height:calc(100vh - 64px); overflow-y:auto;
  background:rgb(241,243,247)}
#side a {display:block; padding:8px 12px; color:rgb(60,64,72)}
#main {flex:1; min-width:0; background:rgb(255,255,255); padding:32px}
</style></head><body><header id="top"><a href="#">Docs</a> <a href="#">Guides</a></header>
<div id="cols"><aside id="side"><nav>""" + "".join('<a href="#">Guide %d</a>' % i for i in range(12)) + """</nav>
</aside><main id="main">""" + dk.TEXT * 40 + """</main></div></body></html>"""
# A shop's header stuck at the top from load (Migros): see-through, its
# first row in the page's colour over half of it, holding a search field
# and a toggle drawn in a lighter grey; its nav row see-through. Below, a
# tall side panel in a colour near the page's (the drawer) holds a sticky
# list, a bar down the right edge. The page's colour on a wrapper.
STUCK_PAGE = STYLE + """
html, body {background:transparent}
#shop {background:rgb(18,20,22)}
#stuck {position:sticky; top:0; z-index:40}
#first {height:60px; margin:0 24px; display:flex; gap:8px; align-items:center; background:rgb(18,20,22)}
#field, #toggle {height:44px; background:rgb(27,30,33)} #field {width:40vw} #toggle {width:20vw}
#second {height:48px}
#grid {display:flex; align-items:flex-start} #main {flex:1}
#drawer {width:22vw; min-height:300vh; position:relative; background:rgb(27,30,33)}
#list {position:sticky; top:108px; height:calc(100vh - 108px); background:rgb(27,30,33)}
#long {height:auto}
</style></head><body><div id="shop"><header id="stuck"><div id="first"><a href="#">Logo</a>
<div id="field"><input placeholder="Search"></div><div id="toggle"><input type="radio" name="t">Store</div></div>
<nav id="second"><a href="#">Home</a></nav></header>
<div id="grid"><main id="main"><div id="long">""" + dk.TEXT * 30 + """</div></main>
<aside id="drawer"><div id="list">Shopping list</div></aside></div></div></body></html>"""

# A ::before whose fade is gone (see-through where it painted the bar's colour)
NO_FADE = "return getComputedStyle(document.getElementById(arguments[0]), '::before').backgroundImage === 'none';"

# A header in the page's colour (heise, NZZ): a low band across the window
# whose row in its colour holds an icon, then a sticky row of sections in
# a darker grey below an advert, in the flow until scrolled to, its slider
# arrow a button as tall as it in its colour, fading the links out under
# it (a ::before, a gradient into that colour), and one in a colour of its
# own; below it, a row of headlines scrolling sideways under a square icon
# button in the page's colour (heise's news ticker).
RISER_PAGE = STYLE + """
html, body {background:transparent}
#band {margin-top:70px}
#band, #row {height:40px; background:rgb(40,40,40)}
#row img {width:12px; height:12px}
#ad {height:200px}
#nav {position:sticky; top:0; height:56px; margin:0 24px; z-index:5; background:rgb(8,8,8)}
#next, #go {position:absolute; top:0; width:56px; height:55px; border:0}
#next {right:0; background:rgb(8,8,8)} #go {right:80px; background:rgb(200,60,60)}
#next::before {content:""; position:absolute; top:0; left:-40px; width:40px; height:52px;
  background-image:linear-gradient(to right, transparent, rgb(8,8,8))}
#ticker {position:relative; height:90px; overflow:hidden; white-space:nowrap}
#more {position:absolute; top:0; right:0; width:40px; height:90px; border:0; padding:0; background:rgb(40,40,40)}
</style></head><body><div id="band"><div><div id="row"><a href="#">News</a>
<img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 8 8'%3E%3Cpath d='M0 0h8v8z'/%3E%3C/svg%3E" alt="">
</div></div></div><div id="ad">Advert</div>
<div id="nav"><a href="#">Sections</a><button id="go">Go</button><button id="next">&gt;</button></div>
<div id="ticker"><p>Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. Headline of the hour, a story told. </p><button id="more">
<svg width="24" height="24" viewBox="0 0 24 24"><path d="M8 4l8 8-8 8" stroke="currentColor" fill="none"/></svg>
</button></div>
<div id="long">""" + dk.TEXT + """</div></body></html>"""

# A dark page by design (1Password): the page's colour on a wrapper, and on
# it a hero (a gradient from a colour near the page's into blue), bands in
# that colour (one below the first screen, one holding another), a white
# island, a blue band, a band holding a grey card a little narrower.
SECTION = "rgb(29,29,33)"
SECTIONS_PAGE = STYLE + """
html, body {background:transparent}
#page {background:rgb(18,20,22)}
#hero {margin:0 2vw; height:150vh; background:linear-gradient(SECTION 0, SECTION 25%, rgb(20,95,228) 70%,
  rgb(153,190,255) 100%)}
#band, #outer, #inner, #last {background:SECTION} #band {height:70vh} #inner {height:160vh}
#island {height:90vh; background:rgb(255,255,255); color:rgb(20,20,20)} #blue {height:80vh; background:rgb(20,95,228)}
#last {height:150vh; padding-top:10vh} #card {width:89vw; margin:0 auto; height:120vh; background:rgb(60,61,68)}
</style></head><body><div id="page"><div id="hero">Secure access</div><div id="band">Logos</div>
<div id="outer"><div id="inner">One platform</div></div><div id="island">A story</div><div id="blue">Blue</div>
<div id="last"><div id="card">A card</div></div></div></body></html>""".replace("SECTION", SECTION)
# A band in the page's colour whose top is 30px above the window's
# bottom, below the last row of the grid (impots.gouv.fr's news band);
# at the top, above the grid's first row, the site's header in the flow,
# 48px in that colour (GitHub's): kept solid.
EDGE_PAGE = STYLE + """
html, body {background:transparent}
#page {background:rgb(18,20,22)} #masthead {height:48px; background:SECTION}
#lead {height:calc(100vh - 78px)} #edge {height:100vh; background:SECTION}
</style></head><body><div id="page"><div id="masthead">Code</div><div id="lead">Lead</div><div id="edge">News</div></div>
<div id="long"></div></body></html>""".replace("SECTION", SECTION)
# A light page for a white one (Zalando, Le Figaro, Docker's docs): its
# white on a wrapper; along its top, above the grid's first row, a strip
# of service links in the flow in rgb(241,241,241), near the white; a news
# list fading out at its foot into the page's white by an empty ::after,
# another into blue; a breadcrumb in Tailwind's gray-400 straight on the
# page, and one in a slate grey tinted blue (Docker's docs), the same grey
# on a white card of its own; a shop's meta line in #7a7a7a (ricardo.ch:
# 4.3:1 on white, near 3.3:1 on the light glass).
LIGHT_GLASS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(20,20,20)}
#page {background:rgb(255,255,255); min-height:300vh}
#strip {height:32px; background:rgb(241,241,241)}
#list, #blue {position:relative; width:40vw; height:160px; overflow:hidden}
#list::after, #blue::after {content:""; position:absolute; left:0; right:0; bottom:0; height:80px}
#list::after {background-image:linear-gradient(rgba(255,255,255,0) 0%, rgba(255,255,255,0.5) 50%, rgb(255,255,255) 100%)}
#blue::after {background-image:linear-gradient(rgba(20,95,228,0), rgb(20,95,228))}
#crumb, #cardgrey {color:rgb(156,163,175)}
#orange {color:rgb(255,102,0)}
#meta {color:rgb(122,122,122)}
#slate {color:rgb(139,153,178)}
#card {width:30vw; height:100px; background:rgb(255,255,255); border:1px solid rgb(220,220,220)}
</style></head><body><div id="page"><div id="strip"><a href="#">Help</a> Free delivery</div>
<p><a href="#">Home</a> / <span id="crumb">Get started</span> <span id="orange">Home page</span>
<span id="slate">Docker Desktop</span> <span id="meta">3 bids, ends in 2 days</span></p>
<div id="list">""" + "<p>16:05 A news item in the flash list</p>" * 6 + """</div>
<div id="blue">""" + "<p>A teaser fading into blue</p>" * 6 + """</div>
<div id="card"><p><span id="cardgrey">On its own card</span></p></div></div></body></html>"""
# The fading list on a dark page by design, into the page's own colour.
DARK_FADE_PAGE = (LIGHT_GLASS_PAGE.replace("color:rgb(20,20,20)", "color:rgb(235,235,235)")
                  .replace("rgba(255,255,255,0)", "rgba(18,20,22,0)").replace("rgba(255,255,255,0.5)", "rgba(18,20,22,0.5)")
                  .replace("rgb(255,255,255) 100%", "rgb(18,20,22) 100%")
                  .replace("#page {background:rgb(255,255,255)", "#page {background:rgb(18,20,22)")
                  # a section in the page's colour, a slate caption in it
                  .replace("</style>", "#sect {background:rgb(18,20,22); padding:8px; min-height:300px}"
                           " #credit {color:rgb(86,94,112)}</style>")
                  .replace('<div id="card">', '<div id="sect"><p><span id="credit">Photo credit</span></p></div>'
                           '<div id="card">'))
# Pseudo-elements painting the page's colour (Tages-Anzeiger): a sticky
# header (a bar) whose row of links fades out under its scroll button by
# an empty ::after (a gradient into the page's colour, no text in the
# button), a lead story whose section draws 40px gutters down its sides
# by an empty ::before and ::after in the page's colour (z-index 100) and
# an empty div across its top in that colour (#strip, its whitecover), and
# a red card with a strip in the page's colour down its left edge, which
# stays, as do an empty div in that colour on the card (#cardstrip) and
# one laid over a red box to hide it (#cover). Above the lead, a band
# of headlines on its own backdrop in the page's colour (a sibling) with
# an empty strip in that colour across its top (#deckstrip, DER
# SPIEGEL's band under its navigation), see-through. In the page's colours
# `page` (r, g, b) and its text `text`.
def page_pseudos_page(page, text):
    rgb = "rgb(%d,%d,%d)" % page
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:%(text)s}
#page {background:%(rgb)s; min-height:300vh}
#top {position:sticky; top:0; z-index:5; height:48px; display:flex; background:%(rgb)s}
#links {flex:1; overflow:hidden; white-space:nowrap}
#right {position:relative; width:36px}
#right::after {content:""; position:absolute; top:0; left:-30px; width:30px; height:36px;
  background-image:linear-gradient(to left, %(rgb)s 0%%, rgba(%(rgba)s,0.7) 50%%, transparent)}
#right button {width:36px; height:36px}
#lead {position:relative; margin:40px 80px; min-height:500px}
#lead::before, #lead::after {content:""; position:absolute; top:0; width:40px; height:600px; z-index:100;
  background:%(rgb)s}
#lead::before {left:-40px} #lead::after {right:-40px}
#card {position:relative; margin:0 80px; height:120px; background:rgb(200,30,30); color:rgb(255,255,255)}
#card::before {content:""; position:absolute; left:0; top:0; bottom:0; width:12px; background:%(rgb)s}
#strip, #cardstrip {position:relative; z-index:1; height:40px; background:%(rgb)s}
#peek {position:relative}
#peek p {margin:0; height:40px}
#under {height:60px; background:rgb(200,30,30); color:rgb(255,255,255)}
#cover {position:absolute; left:0; right:0; bottom:0; height:60px; background:%(rgb)s}
#deck {position:relative; margin-top:100px; padding-top:20px}
#deckfull {position:absolute; inset:0; background:%(rgb)s}
#deckstrip {position:absolute; top:0; left:0; right:0; height:10px; background:%(rgb)s}
#deck p {position:relative; margin:0}
</style></head><body><div id="page"><header id="top"><div id="links"><a href="#">Zurich</a>
<a href="#">Sport</a> <a href="#">Das Magazin</a></div><div id="right"><button aria-label="More"></button></div>
</header><div id="deck"><div id="deckfull"></div><div id="deckstrip"></div><p>The headlines</p></div>
<section id="lead"><div id="strip"></div><h1>The lead story</h1>
<div id="peek"><p>A caption over the box</p><div id="under">Hidden by the site</div><div id="cover"></div></div>""" % {"rgb": rgb, "rgba": "%d,%d,%d" % page, "text": text} + \
        "<p>A paragraph of the lead story.</p>" * 8 + """</section>
<div id="card"><div id="cardstrip"></div><p>On a red card</p></div></div></body></html>"""


DARK_PSEUDOS_PAGE = page_pseudos_page((18, 18, 18), "rgb(235,235,235)")
LIGHT_PSEUDOS_PAGE = page_pseudos_page((255, 255, 255), "rgb(20,20,20)")
# The same page on a white wrapper (1Password at its sections): its light
# text measures it dark, so its white is the page's colour hidden under
# the dark glass, and the dark hero top and bands, the tone's own colour,
# are the page's too; the blue band and the grey card stay.
WHITE_SECTIONS_PAGE = SECTIONS_PAGE.replace("#page {background:rgb(18,20,22)}", "#page {background:rgb(255,255,255)}")
# A sidebar scrolling on its own (MDN): a band across the window in the
# page's colour, then a sticky sidebar holding a sticky scrim (a gradient
# fading a colour near the page's out) behind its filter field.
# A link in it underlined by a gradient line in that colour.
SCRIM_PAGE = STYLE + """
html, body {background:transparent}
#crumbs {height:100px; background:rgb(33,36,38)}
#side {position:sticky; top:0; width:278px; height:100vh; overflow-y:auto}
#scrim {position:sticky; top:0; height:76px; background:linear-gradient(rgb(24,25,27) 0, rgb(24,25,27)
  calc(100% - 32px), transparent 100%)}
#links {height:300vh}
#line {background:linear-gradient(rgb(24,25,27), rgb(24,25,27)) 0 100% / 100% 1.4px no-repeat}
</style></head><body><div id="crumbs">Web</div><aside id="side"><nav><div id="scrim"><input value="Filter"></div>
<div id="links"><a href="#"><span id="line">Link</span></a></div></nav></aside></body></html>"""


# Icons and logos of a dark page Dark Reader does not darken (1Password,
# ch.ch): a white fixed header (a bar, veiled dark) with its dark label, a
# chevron drawn in the label's colour (currentColor), a caret in a dark
# colour of its own beside a label, a black word mark
# from another origin whose server allows it (CORS) and a 24 px icon of
# black lines with a red accent; on the glass a navy search icon in its
# link's colour (no text beside it) and a navy pictogram from another
# origin; left alone: the
# same word mark on the site's own dark card, one with a filter of its own,
# a shaded picture from another origin (a shop's photo), a word mark from
# another origin whose server does not allow it, an illustrated badge
# from another origin, its dark part flat, the rest in many tones, a
# mascot from another origin (a black head round a larger pink face), and
# an opaque product photo shot on white (the site shows its photos as it means
# to: only a page Dark Reader darkens gets them on a tile).
def icon_svg(width, height, body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">%s</svg>'
            % (width, height, body)).encode("utf-8")


WORDMARK = icon_svg(140, 28, '<rect x="4" y="6" width="132" height="16" fill="black"/>')
PICTO = icon_svg(140, 160, '<circle cx="70" cy="80" r="50" fill="rgb(0,34,68)"/>')
SHADED = icon_svg(120, 80, '<defs><linearGradient id="g"><stop offset="0" stop-color="black"/>'
                           '<stop offset="1" stop-color="rgb(80,80,80)"/></linearGradient></defs>'
                           '<rect x="10" y="10" width="100" height="60" rx="20" fill="url(#g)"/>')
ACCENT = icon_svg(24, 24, '<path d="M3 21 L12 3 L21 21 Z" fill="none" stroke="black" stroke-width="1"/>'
                          '<circle cx="12" cy="15" r="2" fill="none" stroke="rgb(230,0,0)" stroke-width="1"/>')
# An illustrated badge: a flat dark purple sky over most of it, a white
# machine and an orange planet shaded (GitHub's achievement badges).
BADGE = icon_svg(64, 64, '<defs><linearGradient id="o" x1="0" y1="0" x2="0" y2="1">'
                         '<stop offset="0" stop-color="rgb(250,190,150)"/><stop offset="1" stop-color="rgb(150,50,70)"/>'
                         '</linearGradient></defs><rect x="4" y="2" width="56" height="34" fill="rgb(34,11,81)"/>'
                         '<rect x="22" y="10" width="20" height="10" fill="white"/>'
                         '<rect x="4" y="36" width="56" height="26" fill="url(#o)"/>')
# A mascot: a black head round a large pink face, purple eyes (GitHub's
# Mona on its home page): mostly readable, a picture, not dark ink with
# an accent.
MASCOT = icon_svg(120, 120, '<circle cx="60" cy="60" r="56" fill="black"/>'
                            '<circle cx="60" cy="64" r="44" fill="rgb(240,140,150)"/>'
                            '<circle cx="44" cy="58" r="8" fill="rgb(70,40,120)"/>'
                            '<circle cx="76" cy="58" r="8" fill="rgb(70,40,120)"/>')
CORS = {"Access-Control-Allow-Origin": "*"}
CHEVRON = ('<svg id="%s" width="12" height="12" viewBox="0 0 12 12"><path d="M2 4 L6 8 L10 4" fill="none"'
           ' stroke="currentColor" stroke-width="1.5"/></svg>')
CARET = ('<svg id="caret" width="12" height="12" viewBox="0 0 12 12"><path d="M2 4 H10 L6 9 Z"'
         ' fill="rgb(40,40,40)"/></svg>')
# A light page whose fixed header is dark, its links and artwork white
# (rtbf.be, Docker's docs): under a light theme the header is a bar with a
# light veil and its links get dark ink. In it, following them: a word
# mark painting fill="#fff" (not its text colour), a white icon, a black
# icon the site whitens with a filter of its own; left alone: a colour
# logo, a white icon on its own red button, and an inline toggle icon,
# a saturated blue pill with a white knob and tick (The Verge's privacy
# choices icon: its light ink of one hue, the drawing not).
TOGGLE = ('<svg id="toggle" width="30" height="14" viewBox="0 0 30 14"><rect width="30" height="14" rx="7"'
          ' fill="#0A57FA"/><rect x="17" y="2" width="11" height="10" rx="5" fill="#fff"/>'
          '<path d="M5 7 L7 9 L11 5 L12 6 L7 11 L4 8 Z" fill="#fff"/></svg>')
WHITE_ICON = icon_svg(24, 24, '<path d="M3 21 L12 3 L21 21 Z" fill="white"/>')
BLACK_ICON = icon_svg(24, 24, '<path d="M3 21 L12 3 L21 21 Z" fill="black"/>')
COLOR_LOGO = icon_svg(48, 24, '<rect x="2" y="4" width="20" height="16" fill="rgb(220,30,30)"/>'
                              '<rect x="26" y="4" width="20" height="16" fill="rgb(20,90,200)"/>')
LIGHT_BAR_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
header {position:fixed; top:0; left:0; right:0; height:56px; background:rgb(0,61,96); color:rgb(255,255,255);
  display:flex; align-items:center; z-index:2}
header a {color:inherit; margin:0 8px}
img {display:block}
#whitened {filter:invert(0.92) sepia(1) saturate(0) brightness(1.02)}
#red {background:rgb(200,0,0); padding:4px}
#long {margin-top:70px}
#caret, #masked {display:inline-block; width:16px; height:16px}
#caret {background:url(/white.svg) center / contain no-repeat}
#masked {background-color:rgb(255,255,255); mask:url(/white.svg) center / contain no-repeat}
</style></head><body><header id="bar">
<a href="/"><svg id="mark" width="160" height="24" fill="none" viewBox="0 0 160 24"><path d="M0 4 H40 V20 H0 Z"
 fill="#fff"/><path d="M50 4 H150 V20 H50 Z" fill="#fff"/></svg></a>
<a id="info" href="#">Info</a><a href="#">Sport</a><a href="#">Live TV <span id="caret"></span></a><a href="#">Radio <span id="masked"></span></a>
<a href="#" aria-label="Search"><img id="white" width="24" height="24" src="/white.svg"></a>
<a href="#" aria-label="User"><img id="whitened" width="24" height="24" src="/black.svg"></a>
<a href="#"><img id="logo" width="48" height="24" src="/color.svg"></a>
<a id="red" href="#"><img id="onred" width="24" height="24" src="/white.svg"></a>
<a href="#">Your Privacy Choices """ + TOGGLE + """</a>
</header><div id="long">""" + dk.TEXT * 20 + """</div></body></html>"""
# A light page whose blue header in the flow and green hero a site style
# clears (booking.com, PyPI, crates.io; HEAD_CSS): the header's white
# links, a white word mark painting fill="#fff", an icon-font glyph drawn
# by an empty <i>'s ::before in the link's white (Font Awesome's
# fa-language); the hero's white title with a dark green text-shadow
# drawn for the hero. Left alone: a white word mark on its own blue
# button, and a colour logo in white, yellow and blue (#pylogo, PyPI's:
# its light ink of one tone, white and yellow, but not of one colour).
PY_LOGO = icon_svg(72, 48, '<rect y="4" width="24" height="40" fill="#3775a9"/>'
                   '<rect x="24" y="4" width="24" height="40" fill="#ffffff"/>'
                   '<rect x="48" y="4" width="16" height="40" fill="#ffd242"/>')
HEAD_CSS = "#head, #hero {background:none !important}"
WORD_MARK = ('<svg id="%s" width="144" height="24" fill="none" viewBox="0 0 144 24"><path d="M0 4 H60 V20 H0 Z"'
             ' fill="#fff"/><path d="M70 4 H144 V20 H70 Z" fill="#fff"/></svg>')
HEAD_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#head {background:rgb(0,53,128); color:rgb(255,255,255); display:flex; align-items:center; gap:16px; height:64px}
#head a {color:inherit}
#own {background:rgb(0,53,128); padding:4px}
.glyph::before {content:"\\2726"}
#hero {background:rgb(20,90,40); padding:40px}
#title {color:rgb(255,255,255); text-shadow:rgb(40,70,37) 1px 3px 2px}
</style></head><body><header id="head"><a href="/">""" + WORD_MARK % "wordmark" + """</a>
<a id="headlink" href="#">List your property</a><a href="#" aria-label="Language"><i id="glyph" class="glyph"></i></a>
<a id="own" href="#">""" + WORD_MARK % "ownmark" + """</a>
<a href="/"><img id="pylogo" width="72" height="48" alt="" src="/pylogo.svg"></a></header>
<section id="hero"><h1 id="title">The community's registry</h1></section>
<div id="long">""" + dk.TEXT * 20 + """</div></body></html>"""
# A dark page's fixed header (watson.ch), a bar with the dark veil: its
# active language link in the site's pink, which reads on the veil, and a
# mid-grey link drawn for a white header.
ACCENT_PAGE = STYLE + """
header {position:fixed; top:0; left:0; right:0; height:50px; background:rgb(30,30,30); z-index:2}
#fr {color:rgb(244,15,151)} #de {color:rgb(116,113,122)}
</style></head><body><header id="bar"><a id="fr" href="#">FR</a> <a id="de" href="#">DE</a></header>
<div id="long">""" + dk.TEXT + """</div></body></html>"""
ICON_PAGE = STYLE + """
html, body {background:transparent}
header {position:fixed; top:0; left:0; right:0; height:50px; background:rgb(255,255,255); z-index:2;
  color:rgb(48,49,54); display:flex; align-items:center}
header button {background:transparent; border:0; color:inherit}
#find {color:rgb(1,46,90)}
#card {background:rgb(40,40,40); padding:10px; margin-top:80px}
img {display:block; margin:8px}
header img {margin:0 8px}
</style></head><body><header id="bar"><img id="brand" width="140" height="28" src="%(far)s/wordmark.svg">
<button><span id="menu">Products</span>""" + CHEVRON % "chevron" + """</button>
<button><span id="docs">Docs</span>""" + CARET + """</button>
<img id="accent" width="24" height="24" src="/accent.svg"></header>
<div id="card"><img id="cardmark" width="140" height="28" src="/wordmark.svg"></div>
<a id="find" href="#" aria-label="Search">""" + CHEVRON % "search" + """</a>
<img id="picto" width="140" height="160" src="%(far)s/picto.svg">
<img id="own" width="140" height="28" style="filter:brightness(0.5)" src="/wordmark.svg">
<span style="display:block; filter:invert(1) hue-rotate(180deg)"><img id="under" width="140" height="28" src="/wordmark.svg"></span>
<img id="photo" width="120" height="80" src="%(far)s/shaded.svg">
<img id="closed" width="140" height="28" src="%(far)s/closed.svg">
<img id="badge" width="64" height="64" src="%(far)s/badge.svg">
<img id="mascot" width="120" height="120" src="%(far)s/mascot.svg">
<img id="shot" width="120" height="100" src="/shot.svg">
<div id="long">""" + dk.TEXT + """</div></body></html>"""


# A page built of web components (sbb.ch, MeteoSuisse, Home Assistant):
# its background (painted by an empty ::before, as Home Assistant's panel
# is), a band in its colour, its fixed header, a dark label in a fixed
# see-through layer over a white card of its own and a red button showing
# a label of the page (a slot) all in the open shadow tree of #app, a
# fixed bottom bar in that of #dock, a host inside it. The document's hit
# tests stop at #app.
SHADOW_PAGE = STYLE + """
html, body {background:transparent}
</style></head><body><x-app id="app"><span id="label">Tickets</span></x-app>
<div id="long">""" + dk.TEXT + """</div>
<script>
document.getElementById("app").attachShadow({mode: "open"}).innerHTML = `<style>
#page {position:relative; min-height:150vh; padding-top:100px}
#page::before {content:""; position:absolute; inset:0; z-index:-1; background:rgb(16,16,16)}
#band {height:200px; background:rgb(16,16,16)}
header {position:fixed; top:0; left:0; right:0; height:50px; background:rgb(24,24,24); z-index:2}
#white {position:absolute; top:190px; left:380px; width:260px; height:80px; background:rgb(255,255,255)}
#float {position:fixed; top:210px; left:400px; width:200px; height:40px; color:rgb(30,30,30); z-index:3}
#cta {display:inline-block; background:rgb(235,0,0); color:rgb(255,255,255); padding:8px}
</style><div id="page"><header id="top">Top</header><div id="band">Band</div><a id="cta" href="#"><slot></slot></a>
<div id="white"></div><div id="float"><span id="dark">Dark on white</span></div><x-dock id="dock"></x-dock></div>`;
document.getElementById("app").shadowRoot.getElementById("dock").attachShadow({mode: "open"}).innerHTML =
  `<style>nav {position:fixed; bottom:0; left:0; right:0; height:52px; background:rgb(18,20,22)}</style>`
  + `<nav id="dockbar">Dock</nav>`;
</script></body></html>"""
# A light page of web components (SBB): its root and body see-through, a
# white band across the window in the open shadow tree of a component,
# holding the page's text by a slot, laid between two rows of the grid of
# markCanvas (12 to 27 % of the window's height), which never hits it.
SHADOW_BAND_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(20,20,20)}
#hero {height:12vh} #long {min-height:200vh}
</style></head><body><div id="hero"></div><x-box id="box"><p>Traffic situation</p></x-box>
<div id="long">""" + dk.TEXT + """</div>
<script>
document.getElementById("box").attachShadow({mode: "open"}).innerHTML = `<style>
:host {display:block} #band {height:15vh; overflow:hidden; background:rgb(255,255,255)}
#inner {max-width:80vw; margin:0 auto}
</style><div id="band"><div id="inner"><slot></slot></div></div>`;
</script></body></html>"""
# A dark page in its own colours (GitHub), its root and body see-through
# and nothing painting under its text, between the rows of the grid of
# markCanvas (10, 30 % of the window's height ...): a dark masthead in the
# flow along the page's top edge (0 to 8 %), a band holding a <nav> (12 to
# 27 %), a band of the page (32 to 47 %), a grey bar lighter than the dark
# glass in a <header>, holding a <nav> (IKEA's utility bar in its hidden
# dark theme, 52 to 67 %), and a footer along the page's bottom edge, below
# the first screen.
MASTHEAD = "rgb(13, 17, 23)"
MASTHEAD_PAGE = STYLE + """
html, body {background:transparent}
#masthead, #menu, #plain, #foot {background:rgb(13, 17, 23); overflow:hidden}
#masthead {height:8vh} #menu {margin-top:4vh; height:15vh} #plain {margin-top:5vh; height:15vh}
#utility {margin-top:5vh; height:15vh; overflow:hidden; background:rgb(51, 51, 51)}
#rest {min-height:100vh} #foot {height:8vh}
</style></head><body><div id="masthead"><h2>Navigation Menu</h2><a href="#">Product</a></div>
<div id="menu"><nav><a href="#">Code</a> <a href="#">Issues</a></nav></div>
<div id="plain"><p>About this repository</p></div>
<header><div id="utility"><nav><a href="#">Choose a store</a></nav></div></header>
<div id="rest">""" + dk.TEXT + """</div><div id="foot"><p>Terms</p></div></body></html>"""
# A light app in shadow trees (Home Assistant): a panel painting the page's
# colour by a fixed ::before over the window, the view's own background in
# the same colour inside it, fixed at a negative z-index (under the
# panel's ::before), in a nested tree, so the view background is the
# lowest layer met.
PANEL_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
</style></head><body><x-main id="main"></x-main>
<script>
document.getElementById("main").attachShadow({mode: "open"}).innerHTML = `<style>
#panel {display:block; min-height:100vh}
#panel::before {content:""; position:fixed; inset:0; background:rgb(250,250,250)}
</style><div id="panel"><x-view id="view"></x-view></div>`;
document.getElementById("main").shadowRoot.getElementById("view").attachShadow({mode: "open"}).innerHTML = `<style>
#bg {position:fixed; inset:0; z-index:-1; background:rgb(250,250,250)}
#cards {position:relative; padding:40px}
</style><div id="bg"></div><div id="cards">""" + dk.TEXT * 6 + """</div>`;
</script></body></html>"""
# A page with its own dark theme, following the system's scheme (SRF), its
# root and body see-through: a row of link cards in an opaque colour near
# the page's (SRF's teasers, the Docker docs' link cards), each with a
# photo in a frame of the card's colour and a text box in it; a lone notice
# card in the flow (YouTube's history notice, a <div>) and a lone link card
# in a colour of its own; under a light theme the same in white.
CARDS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(235,235,235)}
#page {background:rgb(18,20,22); min-height:200vh; padding:20px}
.row {display:flex; gap:20px}
.card {display:block; width:260px; background:rgb(30,33,41); border:1px solid rgb(60,64,72);
  color:inherit; text-decoration:none}
.frame {background:rgb(30,33,41)}
.frame img {display:block; width:260px; height:140px}
.text {background:rgb(30,33,41); padding:12px}
#notice {width:700px; margin-top:20px; padding:20px; background:rgb(33,33,33)}
#lone {display:block; width:300px; margin-top:20px; padding:20px; background:rgb(40,40,40); color:inherit}
@media (prefers-color-scheme: light) {
  html, body {color:rgb(20,20,20)}
  #page {background:rgb(245,245,245)}
  .card, .frame, .text {background:rgb(255,255,255)}
  #notice {background:rgb(255,255,255)}
  #lone {background:rgb(250,250,250)}
}
</style></head><body><div id="page"><div class="row">""" + "".join(
    '<a class="card" id="card%d" href="#"><div class="frame" id="frame%d"><img id="photo%d" src="%s" alt=""></div>'
    '<div class="text" id="text%d"><h3>Teaser %d</h3><p>A short report under its photo.</p></div></a>'
    % (i, i, i, dk.PHOTO, i, i) for i in range(3)) + """</div>
<div id="notice"><h3>Your history is off</h3><p>A notice of the site, alone on the page.</p></div>
<a id="lone" href="#"><h3>Alone</h3><p>A single link card in a colour of its own.</p></a>
""" + dk.TEXT + """</div></body></html>"""
# The same page, its cards drawn by the boxes around their links: offer
# cards lower than CARD_SIDE whose link is stretched over them from the
# open shadow tree of a component in them (SBB's sbb-card-link), service
# cards whose grey face fills a frame in the page's colour, the same size,
# a short title link in it (IKEA's); left as painted: a row of pills round
# their links, a row of boxes holding a list of links, a row of cards
# that are their photo, a row of product tiles, a photo set in each with
# a margin round it (LDLC's), a row of boxes outlined by a border of their own
# round a link (GitHub's pinned repositories), a lone card.
CARD_PARTS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(235,235,235)}
#page {background:rgb(18,20,22); min-height:200vh; padding:20px}
.row {display:flex; gap:20px; margin-bottom:20px}
.offer {position:relative; width:300px; height:90px; padding:12px; box-sizing:border-box;
  background:rgb(36,36,36); border-radius:8px}
.offer h3, .offer p {margin:0}
x-link {position:absolute; inset:0}
.service {width:220px; height:180px; background:rgb(18,20,22)}
.framed {width:300px; height:100px; background:rgb(18,20,22); border:1px solid rgb(48,54,61)}
.face {height:100%; padding:16px; box-sizing:border-box; background:rgb(30,30,30)}
.face a {color:inherit}
.pill {width:160px; height:48px; background:rgb(51,51,51); border-radius:24px}
.list {width:400px; padding:10px; background:rgb(28,28,28)}
.list a {display:block; color:inherit}
.pic {position:relative; width:200px; height:150px; background:rgb(40,40,40)}
.pic img {display:block; width:100%; height:100%}
.pic a {position:absolute; left:8px; bottom:8px; color:inherit}
.mat {width:260px; height:220px; padding:20px 50px; box-sizing:border-box; background:rgb(34,34,34)}
.mat img {display:block; width:160px; height:140px}
.mat a {color:inherit}
#lone {width:300px; height:140px; background:rgb(44,44,44)}
@media (prefers-color-scheme: light) {
  html, body {color:rgb(20,20,20)}
  #page {background:rgb(255,255,255)}
  .offer {background:rgb(246,246,246)}
  .service, .framed {background:rgb(255,255,255)}
  .face {background:rgb(240,240,240)}
  .pill {background:rgb(245,245,245)}
  .list {background:rgb(248,248,248)}
  .pic {background:rgb(240,240,240)}
  .mat {background:rgb(250,250,250)}
  #lone {background:rgb(242,242,242)}
}
</style></head><body><div id="page">
<div class="row">""" + "".join(
    '<div class="offer" id="offer%d"><h3>Offer %d</h3><p>Half the fare for a year.</p><x-link></x-link></div>'
    % (i, i) for i in range(2)) + """</div>
<div class="row">""" + "".join(
    '<div class="service" id="service%d"><div class="face" id="face%d"><a href="#">Service %d</a>'
    '<p>Help with your order.</p></div></div>' % (i, i, i) for i in range(3)) + """</div>
<div class="row">""" + "".join(
    '<div class="pill" id="pill%d"><a href="#">Pill %d</a></div>' % (i, i) for i in range(2)) + """</div>
<div class="row">""" + "".join(
    '<div class="list" id="list%d">' % i + "".join('<a href="#">File %d</a>' % j for j in range(6)) + '</div>'
    for i in range(2)) + """</div>
<div class="row">""" + "".join(
    '<div class="pic" id="pic%d"><img src="%s" alt=""><a href="#">Photo %d</a></div>' % (i, dk.PHOTO, i)
    for i in range(2)) + """</div>
<div class="row">""" + "".join(
    '<div class="mat" id="mat%d"><a href="#"><img src="%s" alt="">Product %d</a></div>' % (i, dk.PHOTO, i)
    for i in range(2)) + """</div>
<div class="row">""" + "".join(
    '<div class="framed" id="framed%d"><a href="#">Repository %d</a><p>A project pinned.</p></div>' % (i, i)
    for i in range(2)) + """</div>
<div id="lone"><a href="#">Alone</a><p>A single card of its own.</p></div>
""" + dk.TEXT + """</div>
<script>
customElements.define("x-link", class extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"}).innerHTML = '<a href="#" style="position:absolute; inset:0"></a>';
  }
});
</script></body></html>"""
# A page with its own dark theme, following the system's scheme (Heise,
# crates.io), its root and body see-through: a module in its card colour
# across 80% of the window, alone in that colour (#module, Heise's
# promotion and its "Meistgelesen" list): a heading, a photo set on its
# left beside its text, a list of more links than CARD_LINKS with plain
# text between them; a row of link cards 72 px high (#crate0..2,
# crates.io's crate list); a row of two teaser text boxes pulled up over
# their photos (#teaser0, #teaser1, Heise's hero teasers), cards in a row
# too. Left as painted: a lone notice (#notice), a band in a saturated
# brand colour as wide as the module (#brand). Under a light theme the
# same in white on a light grey page.
MODULES_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(235,235,235)}
#page {background:rgb(32,32,32); min-height:200vh; padding:20px}
#module {width:80vw; box-sizing:border-box; padding:20px; background:rgb(50,50,50)}
#module h2 {margin:0 0 12px}
#promo {display:flex; gap:20px; margin-bottom:12px}
#promo img {display:block; width:300px; height:170px}
#module ol a {color:inherit}
.row {display:flex; gap:20px; margin-top:20px}
.crate {display:block; width:284px; height:72px; padding:8px; box-sizing:border-box;
  background:rgb(20,20,19); border-radius:5px; color:inherit; text-decoration:none}
.crate h3, .crate p {margin:0}
.hero {width:484px}
.hero img {display:block; width:484px; height:240px}
.teaser {position:relative; margin:-80px 20px 0; padding:16px; background:rgb(60,60,60)}
#notice {width:500px; margin-top:20px; padding:20px; background:rgb(40,40,40)}
#brand {width:80vw; box-sizing:border-box; margin-top:20px; padding:20px; background:rgb(200,30,30)}
@media (prefers-color-scheme: light) {
  html, body {color:rgb(20,20,20)}
  #page {background:rgb(232,237,240)}
  #module, .crate {background:rgb(255,255,255)}
  .teaser {background:rgb(252,252,252)}
  #notice {background:rgb(246,246,246)}
}
</style></head><body><div id="page">
<div id="module"><h2>Meistgelesen</h2>
<div id="promo"><img src="%s" alt=""><div><h3>Promotion</h3><p>A report beside its photo.</p></div></div>
<ol>""" % dk.PHOTO + "".join('<li><a href="#">Article %d</a> <span>%d00 Abrufe</span></li>' % (i, i) for i in range(6)) + """</ol>
</div>
<div class="row">""" + "".join(
    '<a class="crate" id="crate%d" href="#"><h3>crate%d</h3><p>A crate of the registry.</p></a>' % (i, i)
    for i in range(3)) + """</div>
<div class="row">""" + "".join(
    '<div class="hero"><img src="%s" alt=""><div class="teaser" id="teaser%d"><h3>Teaser %d</h3>'
    '<p>Its text pulled up over the photo.</p></div></div>' % (dk.PHOTO, i, i) for i in range(2)) + """</div>
<div id="notice"><h3>A notice</h3><p>Alone on the page in its colour.</p></div>
<div id="brand"><h3>Subscribe</h3><p>A band in the brand's colour.</p></div>
""" + dk.TEXT + """</div></body></html>"""
# A light page under its light theme (PyPI's project page): a grey band
# across the window holding the page's tab menu (#tabs,
# div.horizontal-section--grey), and sidebar cards painted in a colour the
# page mixes in CSS, computed as color(srgb ...) (#side0, #side1, its
# tinted data blocks), text alone in them. Both are panels of the page.
# The band lies between the rows markCanvas samples (0.1 and 0.3 of the
# window), so the text on it leads to it (markBands). Its other sidebar
# cards are drawn in two faces in a box painting nothing (#src0, #src1
# tinted, #ver0, #ver1 grey): a source line (a <details>, 23 px, its pill
# label pulled 10 px up over it) over a data block it overlaps by 10 px,
# #ver0's block 49 px high with one link (63 px together), #ver1's with
# five, #src1's holding an avatar; and its grey code blocks are outlined, one alone in view, one a
# single line (#code0, #code1).
GREY_BAND_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#top {height:16vh; padding:0 20px; box-sizing:border-box}
#tabs {background:rgb(236,236,236); border-top:1px solid rgb(220,220,220); height:58px; padding:0 20px}
#tabs nav {display:flex; gap:20px; line-height:58px}
#tabs a {color:inherit}
#main {display:flex; gap:40px; padding:20px}
#side {width:250px; flex:none}
.side {padding:16px; margin-bottom:20px; background:color(srgb 0.95 0.971373 0.983922)}
.side h3, .side p {margin:0}
.src {margin-bottom:30px}
.strip {margin:15px 0 -10px; border:1px solid rgb(204,226,239); border-bottom:0;
  background:color(srgb 0.95 0.971373 0.983922)}
.strip summary {display:inline-block; position:relative; transform:translateY(-10px); margin-left:5px;
  padding:1px 8px; border:1px solid rgb(204,226,239); border-radius:1rem; font-size:13px; line-height:18px;
  list-style:none; background:color(srgb 0.95 0.971373 0.983922)}
.block {border:1px solid rgb(204,226,239); border-top:0; padding:10px; line-height:22px;
  background:color(srgb 0.95 0.971373 0.983922)}
.block p {margin:0}
.ver .strip, .ver .strip summary, .ver .block {background:color(srgb 0.962745 0.962745 0.962745);
  border-color:rgb(221,221,221)}
.ver .block {padding:0}
.ver ul {margin:0; padding:8px 0; list-style:none}
.ver li a {display:block; padding:5px 10px; line-height:22px}
pre {background:rgb(249,249,249); border:1px solid rgb(210,210,210); margin:30px 0 0; padding:15px;
  line-height:20px}
#main {min-height:200vh}
</style></head><body><main>
<div id="top"><h1>project 1.0</h1></div>
<div id="project"><div id="tabs"><div><nav><a href="#">Description</a><a href="#">History</a><a href="#">Files</a></nav></div></div>
<div id="main"><div id="side">""" + "".join(
    '<div class="side" id="side%d"><h3>Key dates</h3><p>Released on a day of the year.</p><p>Python 3</p></div>' % i
    for i in range(2)) + "".join(
    '<div class="src" id="src%d"><details class="strip" id="strip%d"><summary>PyPI data</summary></details>'
    '<div class="block" id="block%d"><p>Released: May 14</p><p>%s</p></div></div>'
    % (i, i, i, ('<img src="%s" width="34" height="34" alt=""> maintainer' % dk.PHOTO) if i else "Latest release")
    for i in range(2)) + "".join(
    '<div class="src ver" id="ver%d"><details class="strip" id="vstrip%d"><summary>Data verified</summary>'
    '</details><div class="block" id="vblock%d"><ul>%s</ul></div></div>'
    % (i, i, i, "".join('<li><a href="#">Link %d</a></li>' % j for j in range(n)))
    for i, n in enumerate((1, 5))) + """</div><div>
<pre id="code0">&gt;&gt;&gt; import project
&gt;&gt;&gt; r = project.get('https://example.org')
&gt;&gt;&gt; r.status
200</pre>
<pre id="code1">$ python -m pip install project</pre>
""" + dk.TEXT + """</div></div></div>
</main></body></html>"""
# A light page with a row of white product tiles (ldlc.com's Univers
# populaires): each holds a caption link and a product picture with a
# see-through background, lazy, its size unset until it loads, served
# PRODUCT_DELAY s late; a row of white text cards as a witness. The tiles
# keep their fill once the pictures are in.
PRODUCT_DELAY = 2.5
PRODUCT_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
               '<rect x="40" y="60" width="120" height="80" rx="6" fill="rgb(30,40,60)"/></svg>').encode("utf-8")
PRODUCT_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:rgb(20,20,20)}
#page {background:rgb(245,245,245); min-height:200vh; padding:20px}
.row {display:flex; gap:20px; margin-bottom:20px}
.tile {position:relative; width:300px; height:260px; padding-top:12px; box-sizing:border-box;
  text-align:center; background:rgb(255,255,255); border-radius:8px}
.tile a {color:inherit}
.tile a::after {content:""; position:absolute; inset:0}
.tile span.pic {display:block; margin:8px auto 0; width:max-content}
.tile img {display:block}
.note {width:300px; height:140px; padding:12px; box-sizing:border-box; background:rgb(255,255,255); color:inherit}
</style></head><body><div id="page">
<div class="row">""" + "".join(
    '<div class="tile" id="tile%d"><a href="#">Product %d</a>'
    '<span class="pic"><img loading="lazy" src="/product%d.svg" alt=""></span></div>' % (i, i, i)
    for i in range(4)) + """</div>
<div class="row">""" + "".join(
    '<a class="note" id="note%d" href="#"><h3>Guide %d</h3><p>How to choose a laptop.</p></a>' % (i, i)
    for i in range(2)) + """</div>
""" + dk.TEXT + """</div></body></html>"""
# A page that falls back to an error notice on any error (crates.io): its
# window.onerror, set first in its head, records each one; a short text
# (the tone not settled, the body watched) whose body grows during the
# load, a line every 40 ms. Work done right inside a ResizeObserver's
# callback (marks, observing the layers) makes Firefox report its loop
# error to the page.
RESIZE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><script>
window.onerror = window.onunhandledrejection = (e) => {
  const errors = JSON.parse(document.documentElement.getAttribute("data-errors") || "[]");
  errors.push(String(e && e.message || e && e.reason || e));
  document.documentElement.setAttribute("data-errors", JSON.stringify(errors));
};
</script><style>
html, body {margin:0; background:rgb(255,255,255); color:rgb(20,20,20)}
#hero {height:40vh; background:rgb(230,230,240)}
</style></head><body><div id="hero">Rust</div><p>Short.</p></body></html>"""
GROW = ("let n = 0; const t = setInterval(() => {"
        " const d = document.createElement('div'); d.style.height = (20 + n * 7) + 'px'; d.textContent = 'Row ' + n;"
        " document.body.append(d); document.getElementById('hero').style.height = (40 + n) + 'vh';"
        " if (++n >= 25) { clearInterval(t); document.documentElement.setAttribute('data-grown', ''); } }, 40);")
# A feed column built of rows (Watson): the root, the body and the column
# (74vw, centred) see-through, the column a stack of sibling rows each in
# the page's colour (the site's own dark theme), none tall enough alone,
# one only 3vh high between the points of markCanvas; a card of another
# colour in the first, a blue row further down. The rows are framed by
# 16px borders in their colour (#col along its top, each row down its
# sides). A photo in a row of the first screen carries white bylines
# laid over it (#byline), which vote on the picture, not the page, once
# that row is above the window; the page's own heading above (#head)
# carries the vote. With `page`, `card` and `text` the
# colours of the rows, the card and the text.
PHOTO = ("data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='60'%%3E"
         "%%3Crect width='80' height='60' fill='rgb(90,60,40)'/%%3E%%3C/svg%%3E")


def rows_page(page, card, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:%(text)s}
#col {width:74vw; margin:0 auto; border-top:16px solid %(page)s}
.row {background:%(page)s; border:solid %(page)s; border-width:0 16px 16px}
.row p {margin:0; padding:1em 0}
#r1 {height:32vh} #r2 {height:22vh} #r3 {height:3vh} #r4 {height:24vh} #r5, #r6 {height:60vh} #r7 {height:70vh}
#blue {height:40vh; background:rgb(20,95,228); color:rgb(255,255,255)}
#rowcard {width:40%%; height:12vh; background:%(card)s}
#teaser {position:relative; width:50%%} #teaser img {display:block; width:100%%; height:40vh}
#byline {position:absolute; left:8px; right:8px; bottom:8px; color:rgb(255,255,255)} #byline p {margin:0}
#head {margin:0; padding:8px 13vw; font-size:16px}
</style></head><body><h1 id="head">The news of the day from Switzerland and the world, in brief</h1>
<div id="col"><div class="row" id="r1"><div id="rowcard">A card</div></div>
<div class="row" id="r2"><p>Top stories</p></div><div class="row" id="r3"></div>
<div class="row" id="r4"><p>Switzerland</p></div><div class="row" id="r5"><p>Sport</p>
<div id="teaser"><img alt="" src="%(photo)s"><div id="byline"><p>by Anna Example, Zurich correspondent</p>
<p>by Bernard Example, Geneva desk editor</p><p>by Carla Example, sports reporter</p>
<p>by Daniel Example, culture writer</p></div></div></div>
<div id="blue">Promotion</div><div class="row" id="r6"><p>Culture</p></div>
<div class="row" id="r7"><p>Life</p></div></div></body></html>""" % {"page": page, "card": card, "text": text,
                                                                  "photo": PHOTO}


DARK_ROWS_PAGE = rows_page("rgb(0,0,0)", "rgb(40,40,48)", "rgb(235,235,235)")
LIGHT_ROWS_PAGE = rows_page("rgb(255,255,255)", "rgb(225,225,232)", "rgb(20,20,20)")
# The same feed column with no text of the page's own above it: each row
# below the first screen carries a kicker in a mid-grey colour of the
# other side (Watson's pink section titles, right on the rows), every row
# teasers, links holding a photo
# and a headline in the rows' colour, which hold the page's text. The
# rows turned glass at load, the kickers are the only text on no box:
# the teasers, in the rows' colour, are the page, not cards, and the page
# keeps its tone. With `page`, `kicker` and `text` the colours of the
# rows (and teasers), the kickers and the headlines.


def teaser_rows_page(page, kicker, text):
    teaser = ('<a class="teaser" href="#"><img alt="" src="%s"><p>A long headline of the day about'
              ' the news from Switzerland and the world</p></a>' % PHOTO)
    rows = "".join('<div class="row" id="t%d">%s%s</div>' % (i, "<h2>Section %d</h2>" % i if i >= 3 else "",
                                                           teaser * 3)
                   for i in range(8))
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:%(text)s}
#col {width:74vw; margin:0 auto}
.row {background:%(page)s; padding:16px; display:flex; flex-wrap:wrap; gap:8px}
.row h2 {width:100%%; margin:0; color:%(kicker)s; font-size:18px}
.teaser {display:block; width:30%%; background:%(page)s; color:%(text)s; text-decoration:none}
.teaser img {display:block; width:100%%; height:30vh} .teaser p {margin:4px}
</style></head><body><div id="col">%(rows)s</div></body></html>""" % {
        "page": page, "kicker": kicker, "text": text, "rows": rows}


DARK_TEASER_PAGE = teaser_rows_page("rgb(0,0,0)", "rgb(50,105,235)", "rgb(235,235,235)")
LIGHT_TEASER_PAGE = teaser_rows_page("rgb(255,255,255)", "rgb(244,15,151)", "rgb(20,20,20)")
# Boxes in the page's colour (Heise): a band across the window gives the
# page's colour (`page`), cards of their own (`card`) hold the text; an
# empty ad slot in the page's colour beside them, holding a label hidden
# until an ad loads and an empty frame (#slot), and one in a section of
# the page's colour across the window (#inslot) are glass. Kept: a box in
# that colour outlined by a border (#framed), one holding a picture
# (#pic), one with text of its own (#note), a grey ad box (#micro).
def boxes_page(page, card, text):
    return """<!doctype html><html><head><meta charset="utf-8"><style>
html, body {margin:0; background:transparent; color:%(text)s}
#band {height:15vh; background:%(page)s} #band p {margin:0}
#grid, #grid2 {display:flex; gap:2vw; margin:2vh 10vw; align-items:flex-start}
#grid > *, #grid2 > *, #sect > * {flex:none}
.card {width:18vw; height:40vh; background:%(card)s} #story2 {width:14vw}
#slot, #inslot, #framed, #pic, #note {position:relative; width:22vw; height:45vh; background:%(page)s}
#slot {width:24vw} #framed {width:18vw; border:1px solid rgb(120,120,120)} #note {height:20vh}
.label {display:none; position:absolute; left:0; right:0; top:8px}
#micro {width:22vw; height:30vh; background:rgb(70,70,70)}
#sect {margin-top:60vh; padding:5vh 10vw; height:120vh; display:flex; gap:2vw; background:%(page)s}
#sect .card {width:22vw}
</style></head><body><div id="band"><p>News</p></div>
<div id="grid"><div class="card"><p>A story</p></div><div id="slot"><div class="label">Ad</div><div class="frame"></div></div>
<div id="framed"><p>Framed</p></div><div class="card" id="story2"><p>Another story</p></div></div>
<div id="grid2"><div id="pic"><img width="80" height="80"
src="data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%%3E%%3Crect width='80'
height='80' fill='red'/%%3E%%3C/svg%%3E"></div><div id="note">Ad note</div><div id="micro"><p>Microsites</p></div></div>
<div id="sect"><div class="card"><p>In the section</p></div><div id="inslot"><div class="label">Ad</div></div></div>
</body></html>""" % {"page": page, "card": card, "text": text}


DARK_BOXES_PAGE = boxes_page("rgb(32,32,32)", "rgb(50,50,50)", "rgb(224,224,224)")
LIGHT_BOXES_PAGE = boxes_page("rgb(232,237,240)", "rgb(255,255,255)", "rgb(20,20,20)")
BLOCK = bg.ATTR_BLOCK
# the page's tone measured again after a switch of the colour scheme
# (the veil's colour follows it; the marks may be judged before it)
TONE_IS = "return document.documentElement.getAttribute(arguments[0]) === arguments[1];"
# An element in the shadow trees of the hosts given in turn: has it the
# attribute given, or its background colour.
IN_SHADOW = ("let tree = document; for (const host of arguments[0]) tree = tree.getElementById(host).shadowRoot;"
             "const el = tree.getElementById(arguments[1]);"
             "return arguments[2] ? el.hasAttribute(arguments[2]) : getComputedStyle(el).backgroundColor;")


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

    def fade_of(self, b, element_id):
        return b.js("return getComputedStyle(document.getElementById(arguments[0]), '::before').backgroundImage;",
                    element_id)

    def test_icons(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_icons(binary)

    def check_icons(self, binary):
        svg = "image/svg+xml"
        routes = {"/wordmark.svg": (svg, WORDMARK, CORS), "/picto.svg": (svg, PICTO, CORS),
                  "/shaded.svg": (svg, SHADED, CORS), "/shot.svg": (svg, dk.SHOT_SVG), "/closed.svg": (svg, WORDMARK),
                  "/accent.svg": (svg, ACCENT), "/badge.svg": (svg, BADGE, CORS),
                  "/mascot.svg": (svg, MASCOT, CORS)}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            srv.routes["/i.html"] = ("text/html; charset=utf-8",
                                     (ICON_PAGE % {"far": srv.url("", "light.test")}).encode("utf-8"))
            tone.set_scheme(b, True)
            b.navigate(srv.url("/i.html", "dark.test"))
            self.assertTrue(b.wait_for(dk.LOADED), "pictures not loaded")
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "header not marked")
            self.assertTrue(b.wait_for("return document.getElementById('menu').getAttribute(arguments[0]) === 'light';",
                                       mn.WAIT_TIMEOUT, INK), "the bar's dark label not marked")
            # an icon drawn in its text colour follows the readable colour
            for name in ("chevron", "search"):
                self.assertTrue(b.wait_for("return document.getElementById(arguments[0]).getAttribute(arguments[1])"
                                           " === 'light';", mn.WAIT_TIMEOUT, name, INK),
                                name + ": dark currentColor icon not marked")
                self.assertEqual(b.js("return getComputedStyle(document.querySelector('#' + arguments[0] + ' path'))"
                                      ".stroke;", name), LIGHT_INK, name)
            # dark ink of one tone, from another origin (CORS), an icon
            # with a red accent, an inline caret in a dark colour of its
            # own beside a label made light: inverted to light ink, no tile
            for name in ("brand", "accent", "picto", "caret"):
                self.assertTrue(b.wait_for(dk.TILED + " === 'invert';", mn.WAIT_TIMEOUT, name, TILE),
                                name + ": dark ink on the glass not inverted: %r" % b.js(dk.TILED, name, TILE))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('accent')).filter;"),
                             "invert(%s) hue-rotate(180deg)" % bg.TILE_INVERT)
            # left alone: on the site's own dark card, with a filter of its
            # own or under one (Wikipedia's inverted logo), a shaded picture of another origin, one not allowed, an
            # illustrated badge (its dark sky flat, the rest in many tones),
            # an opaque photo shot on white, a mascot mostly readable
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            for name in ("cardmark", "own", "under", "photo", "closed", "badge", "mascot", "shot"):
                self.assertFalse(self.marked(b, name, TILE), "%s tiled: %r" % (name, b.js(dk.TILED, name, TILE)))

    def test_light_bar_icons(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_light_bar_icons(binary)

    def check_light_bar_icons(self, binary):
        svg = "image/svg+xml"
        routes = {"/b.html": ("text/html; charset=utf-8", LIGHT_BAR_PAGE.encode("utf-8")),
                  "/white.svg": (svg, WHITE_ICON), "/black.svg": (svg, BLACK_ICON), "/color.svg": (svg, COLOR_LOGO)}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/b.html", "dark.test"))
            self.assertTrue(b.wait_for(dk.LOADED), "pictures not loaded")
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "the dark header not marked")
            self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "info", INK),
                            "the header's white link not inked dark on the light veil")
            # white artwork of one tone follows the links: a word mark
            # painting #fff and a white icon inverted, the hues turned back
            # (a white caret an empty span paints too: its background
            # picture, its background colour through a mask)
            for name in ("mark", "white", "caret", "masked"):
                self.assertTrue(b.wait_for(dk.TILED + " === 'invert';", mn.WAIT_TIMEOUT, name, TILE),
                                name + ": white ink on the light veil not inverted: %r" % b.js(dk.TILED, name, TILE))
                self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0])).filter;", name),
                                 "invert(%s) hue-rotate(180deg)" % bg.TILE_INVERT)
            # a black icon the site whitens with its filter: the filter goes
            self.assertTrue(b.wait_for(dk.TILED + " === 'plain';", mn.WAIT_TIMEOUT, "whitened", TILE),
                            "an icon whitened by the site's filter kept white: %r" % b.js(dk.TILED, "whitened", TILE))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('whitened')).filter;"), "none")
            # a colour logo, a white icon on its own red button and a
            # colour toggle icon stay
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            for name in ("logo", "onred", "toggle"):
                self.assertFalse(self.marked(b, name, TILE), "%s tiled: %r" % (name, b.js(dk.TILED, name, TILE)))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('whitened')).filter;"), "none")

    def test_cleared_header(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_cleared_header(binary)

    def check_cleared_header(self, binary):
        sites = bg.Sites({"light.test.css": {"glass": HEAD_CSS}}, {})
        routes = {"/h.html": ("text/html; charset=utf-8", HEAD_PAGE.encode("utf-8")),
                  "/pylogo.svg": ("image/svg+xml", PY_LOGO)}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/h.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            # the cleared header in the flow still gets the bar's veil
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR), "the cleared header not veiled")
            self.assertEqual(self.bg_of(b, "head"), "rgba(%d, %d, %d, 0.65)" % bg.surface_rgb(None, "light"))
            for name in ("headlink", "title"):
                self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, name, INK),
                                name + ": white text not inked dark on the light glass")
            # the hero's shadow, drawn for white text, goes with the ink
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('title')).textShadow;"), "none")
            # an icon-font glyph is inked as its link's text is
            self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "glyph", INK),
                            "an icon-font glyph not inked: %r" % b.js(dk.TILED, "glyph", INK))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('glyph'), '::before').color;"),
                             "rgb(%d, %d, %d)" % bg.surface_rgb(None, "dark"))
            # the white word mark follows the header's links
            self.assertTrue(b.wait_for(dk.TILED + " === 'invert';", mn.WAIT_TIMEOUT, "wordmark", TILE),
                            "white word mark on the cleared header not inverted: %r"
                            % b.js(dk.TILED, "wordmark", TILE))
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('wordmark')).filter;"),
                             "invert(%s) hue-rotate(180deg)" % bg.TILE_INVERT)
            # one on its own blue button stays white
            b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
            self.assertFalse(self.marked(b, "ownmark", TILE), "a white mark on its own button inverted")
            self.assertFalse(self.marked(b, "pylogo", TILE), "a colour logo on the cleared header inverted: %r"
                             % b.js(dk.TILED, "pylogo", TILE))

    def test_accent_link(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_accent_link(binary)

    def check_accent_link(self, binary):
        routes = {"/a.html": ("text/html; charset=utf-8", ACCENT_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/a.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR), "header not marked")
            # the grey link, lost over a light section, is inked light
            self.assertTrue(b.wait_for(dk.TILED + " === 'light';", mn.WAIT_TIMEOUT, "de", INK),
                            "the grey link on the dark veil not inked light")
            # the pink one, near 4.5:1 on the veil over the worst
            # wallpaper: never inked to the tone, at most shaded, its hue kept
            self.assertIn(b.js(dk.TILED, "fr", INK), (None, "soft"), "the pink accent link re-inked")
            r, g, b_, _ = tone.rgba(b.js("return getComputedStyle(document.getElementById('fr')).color;"))
            self.assertTrue(r > b_ > g, "the pink accent link lost its hue: %r" % ((r, g, b_),))

    def test_sections(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_sections(binary)

    def check_sections(self, binary):
        routes = {"/s.html": ("text/html; charset=utf-8", SECTIONS_PAGE.encode("utf-8")),
                  "/scrim.html": ("text/html; charset=utf-8", SCRIM_PAGE.encode("utf-8")),
                  "/edge.html": ("text/html; charset=utf-8", EDGE_PAGE.encode("utf-8"))}
        image = "return getComputedStyle(document.getElementById(arguments[0])).backgroundImage"
        clear = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"
        to = "window.scrollTo(0, document.getElementById(arguments[0]).offsetTop);"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            # a band showing only along the window's bottom edge, no scroll
            b.navigate(srv.url("/edge.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "edge"), "a band at the bottom edge left opaque")
            self.assertEqual(b.js("return window.scrollY;"), 0)
            self.assertEqual(self.bg_of(b, "masthead"), "rgb(29, 29, 33)", "a header in the flow made see-through")
            b.navigate(srv.url("/s.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            # the hero's solid top in a colour near the page's: see-through
            self.assertTrue(b.wait_for(image + ".startsWith('linear-gradient(rgba(0, 0, 0, 0) 0px');",
                                       mn.WAIT_TIMEOUT, "hero"), "the hero's top left opaque: %r" % b.js(image, "hero"))
            self.assertIn("rgb(20, 95, 228) 70%", b.js(image, "hero"))
            # bands below the first screen, once scrolled to
            for name in ("band", "outer", "inner"):
                b.js(to, name)
                self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, name), name + ": a band in the page's colour left opaque")
            for name, color in (("island", "rgb(255, 255, 255)"), ("blue", "rgb(20, 95, 228)")):
                b.js(to, name)
                b.js("return new Promise((resolve) => setTimeout(resolve, 300));")
                self.assertEqual(self.bg_of(b, name), color, name + " made see-through")
            b.js(to, "card")
            self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "last"), "the band holding a card left opaque")
            self.assertEqual(self.bg_of(b, "card"), "rgb(60, 61, 68)", "a card in a band made see-through")

            b.navigate(srv.url("/scrim.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "crumbs", CANVAS), "the band not marked")
            self.assertTrue(b.wait_for(image + " === 'none';", mn.WAIT_TIMEOUT, "scrim"),
                            "the sidebar's scrim left in the page's colour: %r" % b.js(image, "scrim"))
            # a link's underline drawn with a gradient in that colour stays
            self.assertFalse(self.marked(b, "line", "data-browserglass-fade"), "a link's underline faded")
            self.assertTrue(b.js(image, "line").startswith("linear-gradient(rgb(24, 25, 27)"))
            # the sidebar's scrollbar: a light thumb, no white track
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('side')).scrollbarColor;"),
                             "rgba(%d, %d, %d, %s) rgba(0, 0, 0, 0)" % (bg.surface_rgb(None, "light")
                                                                   + (bg.SCROLL_THUMB_OPACITY,)))

    def test_white_sections(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_white_sections(binary)

    def check_white_sections(self, binary):
        routes = {"/w.html": ("text/html; charset=utf-8", WHITE_SECTIONS_PAGE.encode("utf-8"))}
        image = "return getComputedStyle(document.getElementById(arguments[0])).backgroundImage"
        clear = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"
        to = "window.scrollTo(0, document.getElementById(arguments[0]).offsetTop);"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/w.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the white page layer not marked")
            self.assertTrue(b.wait_for(image + ".startsWith('linear-gradient(rgba(0, 0, 0, 0) 0px');",
                                       mn.WAIT_TIMEOUT, "hero"), "the hero's dark top left opaque: %r" % b.js(image, "hero"))
            self.assertTrue(self.marked(b, "hero", "data-browserglass-fade"))
            for name in ("band", "outer", "inner"):
                b.js(to, name)
                self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, name), name + ": a band in the tone's colour left opaque")
            b.js(to, "blue")
            b.js("return new Promise((resolve) => setTimeout(resolve, 300));")
            self.assertEqual(self.bg_of(b, "blue"), "rgb(20, 95, 228)", "a blue band made see-through")
            b.js(to, "card")
            self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "last"), "the band holding a card left opaque")
            self.assertEqual(self.bg_of(b, "card"), "rgb(60, 61, 68)", "a card in a band made see-through")

    def test_light_glass(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_light_glass(binary)

    def check_light_glass(self, binary):
        routes = {"/g.html": ("text/html; charset=utf-8", LIGHT_GLASS_PAGE.encode("utf-8")),
                  "/d.html": ("text/html; charset=utf-8", DARK_FADE_PAGE.encode("utf-8"))}
        after = "return getComputedStyle(document.getElementById(arguments[0]), '::after').backgroundImage"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/g.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            # the strip near the page's white along the top: glass
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "strip", CANVAS),
                            "the top strip near the page's white left opaque: %r" % self.bg_of(b, "strip"))
            # the list's fade into the page's white paints nothing, the
            # fade into blue stays
            self.assertTrue(b.wait_for(after + " === 'none';", mn.WAIT_TIMEOUT, "list"),
                            "the list's fade into the page's white left: %r" % b.js(after, "list"))
            self.assertIn("rgb(20, 95, 228)", b.js(after, "blue"))
            # a pale grey straight on the light glass is inked, on its own
            # white card it reads
            self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "crumb", INK),
                            "a pale grey on the light glass not inked")
            self.assertTrue(b.wait_for(dk.TILED + " === 'dark';", mn.WAIT_TIMEOUT, "slate", INK),
                            "a pale slate grey tinted blue on the light glass not inked")
            # on its own white card (2.5:1 there) it is shaded on the card,
            # never inked to the tone
            self.assertTrue(b.wait_for(dk.TILED + " === 'soft';", mn.WAIT_TIMEOUT, "cardgrey", INK),
                            "a pale grey on its own white card not shaded")
            self.assertGreaterEqual(wg.ratio(b.js("return getComputedStyle(document.getElementById('cardgrey')).color;"),
                                             (255.0, 255.0, 255.0)), 4.5)
            # an orange link (2.9:1 on the light glass): never inked to the
            # tone, shaded to 4.5:1, still an orange
            self.check_soft(b, "orange", None)
            r, g, b_, _ = tone.rgba(b.js("return getComputedStyle(document.getElementById('orange')).color;"))
            self.assertTrue(r > g > b_, "the orange link lost its hue: %r" % ((r, g, b_),))
            # the shop's grey meta line, readable but under 4.5:1, lifted
            # to 4.5:1, still greyer than the text inked dark
            self.check_soft(b, "meta", "crumb")

            # the same fade on a dark page into its own colour
            tone.set_scheme(b, True)
            b.navigate(srv.url("/d.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the dark page's layer not marked")
            self.assertTrue(b.wait_for(after + " === 'none';", mn.WAIT_TIMEOUT, "list"),
                            "the list's fade into the dark page's colour left: %r" % b.js(after, "list"))
            # a slate caption (2.8:1 on the dark glass) neither inked nor
            # keeping its section an opaque panel
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "sect", CANVAS), "the section not glass")
            b.js("return new Promise((resolve) => setTimeout(resolve, 1000));")
            self.assertFalse(self.marked(b, "sect", bg.ATTR_OWN), "the section kept opaque for its caption")
            # lifted to 4.5:1 instead, a grey lighter than the light ink
            self.assertNotEqual(b.js(dk.TILED, "credit", INK), "light", "a slate caption on the dark glass inked light")
            self.check_soft(b, "credit", None)

    def check_soft(self, b, element_id, inked):
        """`element_id`'s grey text reads 4.5:1 at least on the glass (its
        tint over a black and a white wallpaper), and less than `inked`'s
        (text inked to the tone), if given."""
        self.assertTrue(b.wait_for(dk.TILED + " === 'soft';", mn.WAIT_TIMEOUT, element_id, INK),
                        "a grey under 4.5:1 on the glass not lifted: %r" % b.js(dk.TILED, element_id, INK))
        r, g, b_, _ = tone.rgba(b.js("return getComputedStyle(document.documentElement)"
                                     ".getPropertyValue('--browserglass-glass').trim();"))
        tint = b.js("return getComputedStyle(document.documentElement).getPropertyValue(arguments[0]).trim();",
                    bg.TINT_VAR)
        glass = "rgba(%d, %d, %d, %s)" % (r, g, b_, tint)
        color = "return getComputedStyle(document.getElementById(arguments[0])).color;"
        ratio = tone.contrast(b.js(color, element_id), glass)
        self.assertGreaterEqual(ratio, 4.5, "%s reads %.2f:1 on the glass" % (element_id, ratio))
        self.assertLess(ratio, 7, "%s lifted past a secondary grey: %.2f:1" % (element_id, ratio))
        if inked:
            self.assertLess(ratio, tone.contrast(b.js(color, inked), glass), "the soft grey as dark as the inked text")

    def test_page_pseudos(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_page_pseudos(binary)

    def check_page_pseudos(self, binary):
        routes = {"/d.html": ("text/html; charset=utf-8", DARK_PSEUDOS_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LIGHT_PSEUDOS_PAGE.encode("utf-8"))}
        for darken in (False, True):
            with mn.TestServer(routes) as srv, \
                    mn.Browser(content_css=dk.stylesheet(darken), prefs=tone.browser_prefs(), firefox=binary) as b:
                # the site's own dark and light themes, then a light page
                # Dark Reader darkens
                cases = [("/l.html", True)] if darken else [("/d.html", True), ("/l.html", False)]
                for page, dark in cases:
                    with self.subTest(page=page, darken=darken):
                        tone.set_scheme(b, dark)
                        b.navigate(srv.url(page, "dark.test" if dark else "light.test"))
                        if darken:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [], True)
                            self.assertTrue(b.wait_for(dk.DARKENED, mn.WAIT_TIMEOUT), "not darkened")
                        else:
                            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                        self.check_pseudos(b)

    def check_pseudos(self, b):
        pseudo = ("return getComputedStyle(document.getElementById(arguments[0]), '::' + arguments[1])"
                  "[arguments[2]];")
        clear = pseudo[:-1] + " === arguments[3];"
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
        b.js("window.scrollTo(0, 100);")
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "top", BAR), "the header not a bar")
        # the gutters down the lead story's sides: see-through
        for side in ("before", "after"):
            self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "lead", side, "backgroundColor", "rgba(0, 0, 0, 0)"),
                            "the lead's ::%s gutter left opaque: %r"
                            % (side, b.js(pseudo, "lead", side, "backgroundColor")))
        # the scroll fade in the bar, into the page's colour: nothing left
        self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "right", "after", "backgroundImage", "none"),
                        "the bar's fade into the page's colour left: %r"
                        % b.js(pseudo, "right", "after", "backgroundImage"))
        # the strip in the page's colour on the red card keeps its colour
        self.assertEqual(tone.rgba(b.js(pseudo, "card", "before", "backgroundColor"))[3], 1.0,
                         "the strip on the red card made see-through")
        # an empty div across the lead's top in the page's colour: see-through;
        # one on the red card and one hiding a red box keep their colour
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "strip", CANVAS),
                        "the lead's strip in the page's colour left opaque: %r" % self.bg_of(b, "strip"))
        self.assertEqual(self.bg_of(b, "strip"), "rgba(0, 0, 0, 0)")
        # a strip in the page's colour over a backdrop in that colour (a
        # sibling, a layer of the page's background): see-through too
        self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "deckstrip", CANVAS),
                        "the strip over the page's backdrop left opaque: %r" % self.bg_of(b, "deckstrip"))
        for name in ("cardstrip", "cover"):
            self.assertFalse(self.marked(b, name, CANVAS), name + " made see-through")
            self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)

    def test_panel(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_panel_layer(binary)

    def check_panel_layer(self, binary):
        routes = {"/panel.html": ("text/html; charset=utf-8", PANEL_PAGE.encode("utf-8"))}
        before = ("const tree = document.getElementById('main').shadowRoot;"
                  "return getComputedStyle(tree.getElementById('panel'), '::before').backgroundColor;")
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/panel.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["main", "view"], "bg", CANVAS),
                            "the view's background not marked")
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["main"], "panel", CANVAS),
                            "the panel painting the page by its ::before not marked")
            self.assertEqual(b.js(before), "rgba(0, 0, 0, 0)", "the panel's ::before left opaque")

    def test_shadow(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_shadow(binary)

    def check_shadow(self, binary):
        routes = {"/shadow.html": ("text/html; charset=utf-8", SHADOW_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/shadow.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["app"], "page", CANVAS),
                            "the page's layer in a shadow tree not marked")
            self.assertEqual(b.js("const tree = document.getElementById('app').shadowRoot;"
                                  "return getComputedStyle(tree.getElementById('page'), '::before').backgroundColor;"),
                             "rgba(0, 0, 0, 0)", "the page's colour painted by its ::before left opaque")
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["app"], "band", CANVAS),
                            "a band in the page's colour in a shadow tree not marked")
            self.assertEqual(b.js(IN_SHADOW, ["app"], "band", None), "rgba(0, 0, 0, 0)")
            # the fixed header of the tree and the bottom bar of a nested
            # one: bars, veiled in the page's tone, the veil in their tree
            for hosts, name in ((["app"], "top"), (["app", "dock"], "dockbar")):
                self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, hosts, name, BAR),
                                name + ": a fixed bar in a shadow tree not marked")
                self.assertEqual(b.js(IN_SHADOW, hosts, name, None), DARK_SURFACE, name)
                self.assertEqual(b.js("let tree = document; for (const host of arguments[0])"
                                      " tree = tree.getElementById(host).shadowRoot;"
                                      "return getComputedStyle(tree.getElementById(arguments[1]), '::before').backdropFilter;",
                                      hosts, name), BLUR, name)
            self.assertTrue(b.js("const tree = document.getElementById('app').shadowRoot;"
                                 "return !!tree.getElementById('browserglass-veil');"), "no veil in the shadow tree")
            # dark text over the tree's white card, in a fixed see-through
            # layer, and the page's label on the tree's red button: no ink
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertFalse(b.js(IN_SHADOW, ["app"], "dark", INK), "dark text over a shadow tree's white card inked")
            self.assertFalse(self.marked(b, "label", INK), "a label on a shadow tree's red button inked")
            # the dark page under a light theme: its bars keep the dark veil
            tone.set_scheme(b, False)
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["app"], "top", BAR))
            self.assertEqual(b.js(IN_SHADOW, ["app"], "top", None), DARK_SURFACE,
                             "a shadow tree's bar not in the page's tone")

    def test_shadow_band(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_shadow_band(binary)

    def check_shadow_band(self, binary):
        routes = {"/band.html": ("text/html; charset=utf-8", SHADOW_BAND_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/band.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(IN_SHADOW, mn.WAIT_TIMEOUT, ["box"], "band", CANVAS),
                            "a white band in a shadow tree between the grid's rows not marked: %r"
                            % b.js(IN_SHADOW, ["box"], "band", None))
            self.assertEqual(b.js(IN_SHADOW, ["box"], "band", None), "rgba(0, 0, 0, 0)",
                             "the white band in a shadow tree left opaque")

    def test_masthead(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_masthead(binary)

    def check_masthead(self, binary):
        routes = {"/masthead.html": ("text/html; charset=utf-8", MASTHEAD_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/masthead.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "plain", CANVAS),
                            "a band of the page between the grid's rows not marked: %r" % self.bg_of(b, "plain"))
            self.assertEqual(self.bg_of(b, "plain"), "rgba(0, 0, 0, 0)")
            self.assertTrue(self.marked(b, "utility", CANVAS),
                            "a grey bar of the site lighter than the dark glass left opaque: %r"
                            % self.bg_of(b, "utility"))
            self.assertEqual(self.bg_of(b, "utility"), "rgba(0, 0, 0, 0)")
            for name in ("masthead", "menu", "foot"):
                self.assertFalse(self.marked(b, name, CANVAS), name + ": the site's bar taken as a band of the page")
                self.assertEqual(self.bg_of(b, name), MASTHEAD, name + " lost its colour")

    def test_bar_rows(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_bar_rows(binary)

    def check_bar_rows(self, binary):
        routes = {"/row.html": ("text/html; charset=utf-8", ROW_BAR_PAGE.encode("utf-8")),
                  "/rownotice.html": ("text/html; charset=utf-8", ROW_NOTICE_PAGE.encode("utf-8")),
                  "/skip.html": ("text/html; charset=utf-8", SKIP_BAR_PAGE.encode("utf-8"))}
        opacity = "return getComputedStyle(document.getElementById(arguments[0])).opacity;"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            # the header's top row in the page's colour: see-through under
            # the veil once the header is a bar
            b.navigate(srv.url("/row.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "crumbs", CANVAS), "the breadcrumbs not a band")
            b.js("window.scrollTo(0, 600);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "rowbar", BAR), "the stuck header not marked")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('row')).backgroundColor"
                                       " === 'rgba(0, 0, 0, 0)';", mn.WAIT_TIMEOUT),
                            "the header's row in the page's colour left opaque over the veil")
            self.assertFalse(b.js(dk.MARKED, "drop", CANVAS), "a hidden menu in the row filled")
            b.js("document.getElementById('drop').style.display = 'block'; window.scrollTo(0, 650);")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('drop')).backgroundColor"
                                       " === 'rgb(24, 25, 27)';", mn.WAIT_TIMEOUT), "an opened menu made see-through")
            # the same row glass before (a band across the window, under a
            # notice): the header still gets its veil once stuck
            b.navigate(srv.url("/rownotice.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "row", CANVAS), "the row not a band")
            b.js("window.scrollTo(0, 600);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "rowbar", BAR),
                            "a stuck header whose row is glass left without its veil")
            self.assertEqual(self.bg_of(b, "rowbar"), DARK_SURFACE)

            # the layer backing the bar hides the skip links it holds; the
            # list of links in the bar's colour is see-through, the button
            # keeps its colour; the skip links show once focused
            b.navigate(srv.url("/skip.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "skipbar", BAR), "the sticky bar not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "skip", UNDER),
                            "the layer of skip links behind the bar's content not marked")
            self.assertEqual(b.js(opacity, "skip"), "0")
            for row in ("links", "list", "item", "lang"):
                self.assertTrue(b.wait_for("return document.getElementById(arguments[0])"
                                           ".getAttribute(arguments[1]) === 'fill';",
                                           mn.WAIT_TIMEOUT, row, CANVAS), row + " in the bar's colour not filled")
                self.assertEqual(self.bg_of(b, row), "rgba(0, 0, 0, 0)")
            self.assertEqual(self.bg_of(b, "cta"), "rgb(255, 255, 255)")
            b.js("document.getElementById('skiplink').focus();")
            self.assertEqual(b.js(opacity, "skip"), "1")

    def test_stacked_bars(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_stacked_bars(binary)

    def check_stacked_bars(self, binary):
        routes = {"/stack.html": ("text/html; charset=utf-8", STACK_PAGE.encode("utf-8")),
                  "/side.html": ("text/html; charset=utf-8", SIDE_PAGE.encode("utf-8")),
                  "/barside.html": ("text/html; charset=utf-8", BAR_SIDE_PAGE.encode("utf-8")),
                  "/navside.html": ("text/html; charset=utf-8", NAV_SIDE_PAGE.encode("utf-8"))}
        filled = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === 'fill';"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            # the sub-navigation held under the masthead: a bar, veiled,
            # not an opaque band; the tabs below it in the flow are not
            b.navigate(srv.url("/stack.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "mast", BAR), "the masthead not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "sub", BAR),
                            "a sticky row held under the masthead not marked")
            self.assertFalse(self.marked(b, "tabs", BAR), "a sticky row in the flow under the bars marked")
            b.js("window.scrollTo(0, 600);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertTrue(self.marked(b, "sub", BAR), "the stacked row lost its veil once scrolled")
            self.assertFalse(self.marked(b, "sub", bg.ATTR_TUCK), "a row stacked under the masthead cut")
            self.assertEqual(self.bg_of(b, "sub"), DARK_SURFACE)
            # its wrapper's ::before painting it again: see-through too
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('subwrap'), '::before')"
                                  ".backgroundColor;"), "rgba(0, 0, 0, 0)",
                             "the stacked row's ::before left an opaque band under its veil")
            # the shadow its ::after cast under that paint: no seam across the veil
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('subwrap'), '::after')"
                                  ".boxShadow;"), "none", "the shadow under the stacked row's paint left a seam")
            # the side column under the header, in a colour near the page's
            # or one of its own: a bar, never a page layer; its block of
            # links in its colour see-through
            for page in ("/side.html", "/barside.html"):
                b.navigate(srv.url(page, "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR),
                                "the side column not a bar (%s)" % page)
                self.assertFalse(self.marked(b, "side", CANVAS), "the side column a page layer (%s)" % page)
                self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "links", CANVAS),
                                "the block of links in the column's colour left opaque (%s)" % page)
                self.assertEqual(self.bg_of(b, "links"), "rgba(0, 0, 0, 0)")
            # a light page: its sticky navigation sidebar under the sticky
            # header a bar, veiled, also scrolled; the content a page layer
            tone.set_scheme(b, False)
            b.navigate(srv.url("/navside.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "main", CANVAS), "the content column not glass")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "top", BAR), "the sticky header not a bar")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "side", BAR),
                            "the sticky navigation sidebar not a bar")
            self.assertFalse(self.marked(b, "side", CANVAS), "the sticky navigation sidebar a page layer")
            b.js("window.scrollTo(0, 700);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertTrue(self.marked(b, "side", BAR), "the sticky navigation sidebar lost its bar once scrolled")
            self.assertFalse(self.marked(b, "side", CANVAS), "the sticky navigation sidebar a page layer once scrolled")

    def test_tucked_bars(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_tucked_bars(binary)

    def check_tucked_bars(self, binary):
        routes = {"/tuck.html": ("text/html; charset=utf-8", TUCK_PAGE.encode("utf-8"))}
        # a rect of the window, in the page's coordinates
        rect = "return [scrollX + arguments[0], scrollY + arguments[1], arguments[2], arguments[3]];"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/tuck.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "mast", BAR), "the masthead not marked")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "row", BAR), "the row under the masthead not marked")
            # side by side at load: the row whole
            self.assertGreater(b.chrome_js(REDDEST, *b.js(rect, 20, 64 + 34, 200, 20)), 150, "the stacked row cut")
            # slid up under the masthead: its upper part hidden, not
            # printed through the masthead's veil; the part below it stays
            b.js("document.getElementById('row').style.top = '-24px'; window.scrollTo(0, 600);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertTrue(self.marked(b, "row", BAR), "the tucked row lost its veil")
            self.assertEqual(b.js("return document.getElementById('row').getBoundingClientRect().top;"), -24)
            self.assertLess(b.chrome_js(REDDEST, *b.js(rect, 20, 0, 200, 60)), 20,
                            "the row under the masthead shows through its veil")
            self.assertGreater(b.chrome_js(REDDEST, *b.js(rect, 20, 70, 200, 24)), 150,
                               "the row's part below the masthead hidden")
            # back at the top, side by side again: whole
            b.js("document.getElementById('row').style.top = '64px'; window.scrollTo(0, 0);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertGreater(b.chrome_js(REDDEST, *b.js(rect, 20, 64 + 34, 200, 20)), 150,
                               "the row stays cut once out from under the masthead")

    def test_tucked_row(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_tucked_row(binary)

    def check_tucked_row(self, binary):
        routes = {"/row.html": ("text/html; charset=utf-8", TUCK_ROW_PAGE.encode("utf-8"))}
        rect = "return [scrollX + arguments[0], scrollY + arguments[1], arguments[2], arguments[3]];"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/row.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR), "the header not marked")
            # in the flow below the header at load: whole
            self.assertGreater(b.chrome_js(REDDEST, *b.js(rect, 20, 141, 200, 20)), 150, "the row below the header cut")
            # stuck under the header: hidden, not printed through its veil
            b.js("window.scrollTo(0, 600);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertEqual(b.js("return document.getElementById('cats').getBoundingClientRect().top;"), 74)
            self.assertLess(b.chrome_js(REDDEST, *b.js(rect, 20, 74, 200, 40)), 20,
                            "the row tucked under the header shows through its veil")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "cats", bg.ATTR_TUCK), "the tucked row not cut")
            # no bar: no blur of its own (a full-window scrim tucked so would blur the page)
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('cats')).backdropFilter;"), "none",
                             "the tucked row that is no bar blurred")
            # back at the top, below the header again: whole
            b.js("window.scrollTo(0, 0);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            self.assertGreater(b.chrome_js(REDDEST, *b.js(rect, 20, 141, 200, 20)), 150,
                               "the row stays cut once out from under the header")

    def test_cards(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_cards(binary)

    def check_cards(self, binary):
        routes = {"/cards.html": ("text/html; charset=utf-8", CARDS_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/cards.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            for dark in (True, False):
                if not dark:
                    tone.set_scheme(b, False)
                    self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "tone not light")
                # the row of link cards: a light veil of the tone's surface,
                # their border kept; the text box see-through, the photo's
                # frame and the photo as the site paints them
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "card0", BLOCK, "veil"),
                                "a link card left a full panel (dark %s): %r" % (dark, self.bg_of(b, "card0")))
                for i in range(3):
                    self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "card%d" % i, BLOCK, "veil"))
                    card = tone.rgba(self.bg_of(b, "card%d" % i))
                    self.assertEqual(card[3], bg.BLOCK_VEIL_OPACITY)
                    self.assertEqual(tone.luminance(card) > 0.5, not dark, card)
                    self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0]))"
                                          ".borderTopWidth;", "card%d" % i), "1px")
                    self.assertEqual(b.js(dk.TILED, "text%d" % i, BLOCK), "glass")
                    self.assertEqual(self.bg_of(b, "text%d" % i), "rgba(0, 0, 0, 0)")
                    self.assertIsNone(b.js(dk.TILED, "frame%d" % i, BLOCK))
                    self.assertEqual(tone.rgba(self.bg_of(b, "frame%d" % i))[3], 1.0)
                    self.assertEqual(b.js("return getComputedStyle(document.getElementById(arguments[0])).filter;",
                                          "photo%d" % i), "none")
                # left alone: the lone notice and the lone link card
                for name in ("notice", "lone"):
                    self.assertIsNone(b.js(dk.TILED, name, BLOCK), "%s veiled (dark %s)" % (name, dark))
                    self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)

    def test_modules(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_modules(binary)

    def check_modules(self, binary):
        routes = {"/modules.html": ("text/html; charset=utf-8", MODULES_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/modules.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            for dark in (True, False):
                if not dark:
                    tone.set_scheme(b, False)
                    self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "tone not light")
                # the module alone in its colour and the low link cards: a
                # light veil of the tone's surface
                for name in ("module", "crate0", "crate1", "crate2", "teaser0", "teaser1"):
                    self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, name, BLOCK, "veil"),
                                    "%s left a full panel (dark %s): %r" % (name, dark, self.bg_of(b, name)))
                    paint = tone.rgba(self.bg_of(b, name))
                    self.assertEqual(paint[3], bg.BLOCK_VEIL_OPACITY, name)
                    self.assertEqual(tone.luminance(paint) > 0.5, not dark, (name, paint))
                # left alone: the lone notice, the brand's band
                for name in ("notice", "brand"):
                    self.assertIsNone(b.js(dk.TILED, name, BLOCK), "%s veiled (dark %s)" % (name, dark))
                    self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)

    def test_grey_band(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_grey_band(binary)

    def check_grey_band(self, binary):
        routes = {"/sections.html": ("text/html; charset=utf-8", GREY_BAND_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/sections.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "tone not light")
            # the grey band of the tab menu: a layer of the page, glass
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "tabs", CANVAS),
                            "grey band left opaque: %r" % self.bg_of(b, "tabs"))
            self.assertLess(tone.rgba(self.bg_of(b, "tabs"))[3], 1.0)
            # the cards in a color(srgb ...) fill: a light veil
            for name in ("side0", "side1"):
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, name, BLOCK, "veil"),
                                "%s left a full panel: %r" % (name, self.bg_of(b, name)))
                self.assertEqual(tone.rgba(self.bg_of(b, name))[3], bg.BLOCK_VEIL_OPACITY, name)
            # a card in two faces: one veil on the box round them, the
            # source line glass with its data block (no two-tone strip),
            # the low grey card too; the outlined code blocks veiled
            for name in ("src0", "src1", "ver0", "ver1", "code0", "code1"):
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, name, BLOCK, "veil"),
                                "%s left as painted: %r" % (name, self.bg_of(b, name)))
                self.assertEqual(tone.rgba(self.bg_of(b, name))[3], bg.BLOCK_VEIL_OPACITY, name)
            for name in ("strip0", "block0", "strip1", "block1", "vstrip0", "vblock0", "vstrip1", "vblock1"):
                self.assertEqual(b.js(dk.TILED, name, BLOCK), "glass", name)
                self.assertEqual(self.bg_of(b, name), "rgba(0, 0, 0, 0)", name)

    def test_card_parts(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_card_parts(binary)

    def check_card_parts(self, binary):
        routes = {"/parts.html": ("text/html; charset=utf-8", CARD_PARTS_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/parts.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "page", CANVAS), "the page's layer not marked")
            for dark in (True, False):
                if not dark:
                    tone.set_scheme(b, False)
                    self.assertTrue(b.wait_for(TONE_IS, mn.WAIT_TIMEOUT, tone.TONE, "light"), "tone not light")
                # the box painted round a link is the card: the light veil
                # of the tone's surface; a face filling a frame see-through
                for card in ("offer0", "offer1", "service0", "service1", "service2"):
                    self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, card, BLOCK, "veil"),
                                    "%s left a full panel (dark %s): %r" % (card, dark, self.bg_of(b, card)))
                    fill = tone.rgba(self.bg_of(b, card))
                    self.assertEqual(fill[3], bg.BLOCK_VEIL_OPACITY)
                    self.assertEqual(tone.luminance(fill) > 0.5, not dark, fill)
                for i in range(3):
                    self.assertEqual(b.js(dk.TILED, "face%d" % i, BLOCK), "glass")
                    self.assertEqual(self.bg_of(b, "face%d" % i), "rgba(0, 0, 0, 0)")
                # left as painted: pills, boxes of links, photo cards,
                # product tiles, boxes outlined round a link, a lone card
                for name in ("pill0", "pill1", "list0", "list1", "pic0", "pic1", "mat0", "mat1",
                             "framed0", "framed1", "lone"):
                    self.assertIsNone(b.js(dk.TILED, name, BLOCK), "%s veiled (dark %s)" % (name, dark))
                    self.assertEqual(tone.rgba(self.bg_of(b, name))[3], 1.0, name)

    def test_product_tiles(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_product_tiles(binary)

    def check_product_tiles(self, binary):
        routes = {"/tiles.html": ("text/html; charset=utf-8", PRODUCT_PAGE.encode("utf-8"))}
        routes.update({"/product%d.svg" % i: ("image/svg+xml", PRODUCT_SVG) for i in range(4)})
        late = lambda path, headers: PRODUCT_DELAY if path.endswith(".svg") else 0  # noqa: E731
        loaded = "return [...document.images].every((img) => img.complete && img.naturalWidth > 0);"
        with mn.TestServer(routes, delay=late) as srv, \
                mn.Browser(content_css=dk.stylesheet(True), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/tiles.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            # the witness: a row of white text cards gets the veil while
            # the pictures are still on their way
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "note0", BLOCK, "veil"),
                            "the row of text cards not veiled: %r" % self.bg_of(b, "note0"))
            self.assertFalse(b.js(loaded), "the product pictures came in before the first pass")
            self.assertTrue(b.wait_for(loaded, mn.WAIT_TIMEOUT), "the product pictures never loaded")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            # the tiles keep their white: product pictures sit on them
            for i in range(4):
                tile = "tile%d" % i
                self.assertIsNone(b.js(dk.TILED, tile, BLOCK), "%s veiled: %r" % (tile, self.bg_of(b, tile)))
                self.assertEqual(self.bg_of(b, tile), "rgb(255, 255, 255)", tile)

    def test_stuck_header(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_stuck_header(binary)

    def check_stuck_header(self, binary):
        routes = {"/stuck.html": ("text/html; charset=utf-8", STUCK_PAGE.encode("utf-8"))}
        filled = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === 'fill';"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/stuck.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            # stuck from load, nothing under it yet: one veil already, its
            # row in the page's colour see-through under it
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "stuck", BAR),
                            "a header stuck at the top from load, its row painted, not a bar")
            self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "first", CANVAS), "the header's row left opaque")
            # the drawer down the page in a colour near the page's: glass
            # under its sticky list
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "drawer", CANVAS),
                            "a side panel in the page's colour holding a bar left opaque")
            self.assertEqual(self.bg_of(b, "drawer"), "rgba(0, 0, 0, 0)")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "list", BAR), "the drawer's sticky list not a bar")
            # the search field and the toggle keep their box, also scrolled
            b.js("window.scrollTo(0, 700);")
            b.js("return new Promise((resolve) => setTimeout(resolve, 800));")
            for name in ("field", "toggle"):
                self.assertFalse(self.marked(b, name, CANVAS), name + ": a field in the bar's row filled")
                self.assertEqual(self.bg_of(b, name), "rgb(27, 30, 33)", name)

    def test_risen_header(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_risen_header(binary)

    def check_risen_header(self, binary):
        routes = {"/riser.html": ("text/html; charset=utf-8", RISER_PAGE.encode("utf-8"))}
        filled = "return document.getElementById(arguments[0]).getAttribute(arguments[1]) === 'fill';"
        clear = "rgba(0, 0, 0, 0)"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            b.navigate(srv.url("/riser.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "band", CANVAS), "the header band not marked")
            # the band's row holding an icon: one glass with the band
            self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "row", CANVAS),
                            "a row of the header band in its colour left opaque: %r" % self.bg_of(b, "row"))
            self.assertEqual(self.bg_of(b, "row"), clear)
            # the sticky row in the flow: the page's header, glass, its
            # arrow too; the button in a colour of its own keeps it
            self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "nav", CANVAS),
                            "a sticky row not stuck yet left opaque: %r" % self.bg_of(b, "nav"))
            self.assertEqual(self.bg_of(b, "nav"), clear)
            self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "next", CANVAS),
                            "the row's arrow left an opaque square: %r" % self.bg_of(b, "next"))
            self.assertEqual(self.bg_of(b, "go"), "rgb(200, 60, 60)", "a button of its own colour cleared")
            # the arrow's fade into the row's colour: see-through with it
            self.assertTrue(b.wait_for(NO_FADE, mn.WAIT_TIMEOUT, "next"),
                            "the arrow's fade a dark band on the glass: %r" % self.fade_of(b, "next"))
            # the ticker's icon button in the page's colour: see-through
            self.assertTrue(b.wait_for(filled, mn.WAIT_TIMEOUT, "more", CANVAS),
                            "an icon button in the page's colour left an opaque square: %r" % self.bg_of(b, "more"))
            self.assertEqual(self.bg_of(b, "more"), clear)
            # stuck: a bar, one veil, the arrow see-through on it
            b.js("window.scrollTo(0, document.getElementById('nav').offsetTop + 300);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "nav", BAR), "the row stuck at the top not a bar")
            self.assertEqual(self.bg_of(b, "nav"), DARK_SURFACE)
            self.assertEqual(self.bg_of(b, "next"), clear, "the arrow opaque on the bar's veil")
            self.assertTrue(b.wait_for(NO_FADE, mn.WAIT_TIMEOUT, "next"),
                            "the arrow's fade a dark band on the bar's veil: %r" % self.fade_of(b, "next"))
            # back in the flow: glass again, no bar
            b.js("window.scrollTo(0, 0);")
            self.assertTrue(b.wait_for("return !document.getElementById(arguments[0]).hasAttribute(arguments[1]);",
                                       mn.WAIT_TIMEOUT, "nav", BAR), "the row back in the flow still a bar")
            self.assertEqual(self.bg_of(b, "nav"), clear)

    def test_resize_loop(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_resize_loop(binary)

    def check_resize_loop(self, binary):
        routes = {"/grow.html": ("text/html; charset=utf-8", RESIZE_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, True)
            for _ in range(3):
                b.navigate(srv.url("/grow.html", "light.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                b.js(GROW)
                self.assertTrue(b.wait_for("return document.documentElement.hasAttribute('data-grown');",
                                           mn.WAIT_TIMEOUT), "the page did not grow")
                b.js("return new Promise((resolve) => setTimeout(resolve, 500));")
                self.assertTrue(b.js("return document.documentElement.hasAttribute(arguments[0]);", tone.LIVE))
                self.assertIsNone(b.js("return document.documentElement.getAttribute('data-errors');"),
                                  "the page saw an error while it grew")

    def test_page_rows(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_page_rows(binary)

    def check_page_rows(self, binary):
        routes = {"/d.html": ("text/html; charset=utf-8", DARK_ROWS_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LIGHT_ROWS_PAGE.encode("utf-8"))}
        clear = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"
        seamless = ("const s = getComputedStyle(document.getElementById(arguments[0]));"
                    "return ['Top', 'Right', 'Bottom', 'Left'].every((k) => !parseFloat(s['border' + k + 'Width'])"
                    " || s['border' + k + 'Color'] === 'rgba(0, 0, 0, 0)');")
        to = "window.scrollTo(0, document.getElementById(arguments[0]).offsetTop);"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            for page, dark, card in (("/d.html", True, "rgb(40, 40, 48)"), ("/l.html", False, "rgb(225, 225, 232)")):
                with self.subTest(page=page):
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(page, "dark.test" if dark else "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    # every row of the column in view, the thin one too
                    for name in ("r1", "r2", "r3", "r4", "r5"):
                        self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, name),
                                        "%s: a row of the page's colour left opaque (%s): %r"
                                        % (name, page, self.bg_of(b, name)))
                    self.assertEqual(self.bg_of(b, "rowcard"), card, "a card on a row made see-through")
                    # the borders in the rows' colour see-through too
                    for name in ("col", "r1", "r5"):
                        self.assertTrue(b.wait_for(seamless, mn.WAIT_TIMEOUT, name),
                                        "%s: a border in the rows' colour left opaque (%s): %r"
                                        % (name, page, self.border_of(b, name)))
                    b.js(to, "r6")
                    self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "r6"), "a row below a blue one left opaque")
                    self.assertTrue(b.wait_for(seamless, mn.WAIT_TIMEOUT, "r6"), "a row's border below left opaque")
                    b.js("return new Promise((resolve) => setTimeout(resolve, 300));")
                    self.assertEqual(self.bg_of(b, "blue"), "rgb(20, 95, 228)", "a blue row made see-through")
                    # the white bylines on the photo above the window vote
                    # on the picture: the light page stays light
                    b.js("window.dispatchEvent(new Event('resize'));"
                         "return new Promise((resolve) => setTimeout(resolve, 500));")
                    self.assertEqual(b.js("return document.documentElement.getAttribute(arguments[0]);",
                                          bg.ATTR_TONE), "dark" if dark else "light",
                                     "the bylines on a photo above the window counted as the page's text")

    def test_page_teasers(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_page_teasers(binary)

    def check_page_teasers(self, binary):
        routes = {"/d.html": ("text/html; charset=utf-8", DARK_TEASER_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LIGHT_TEASER_PAGE.encode("utf-8"))}
        clear = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            for page, dark in (("/d.html", True), ("/l.html", False)):
                with self.subTest(page=page):
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(page, "dark.test" if dark else "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    for name in ("t0", "t1", "t7"):
                        self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, name),
                                        "%s: a row of the page's colour left opaque (%s)" % (name, page))
                    # measured again with the rows glass (the passes after
                    # a load or a navigation, twice): the teasers'
                    # headlines carry the vote
                    for _ in range(2):
                        b.js("window.dispatchEvent(new Event('popstate'));"
                             "return new Promise((resolve) => setTimeout(resolve, 800));")
                        self.assertEqual(b.js("return document.documentElement.getAttribute(arguments[0]);",
                                              bg.ATTR_TONE), "dark" if dark else "light",
                                         "the kickers on the glass rows outvoted the teasers in the page's colour")

    def border_of(self, b, element_id):
        return b.js("const s = getComputedStyle(document.getElementById(arguments[0]));"
                    "return [s.borderTopColor, s.borderLeftColor];", element_id)

    def test_page_boxes(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_page_boxes(binary)

    def check_page_boxes(self, binary):
        routes = {"/d.html": ("text/html; charset=utf-8", DARK_BOXES_PAGE.encode("utf-8")),
                  "/l.html": ("text/html; charset=utf-8", LIGHT_BOXES_PAGE.encode("utf-8"))}
        clear = "return getComputedStyle(document.getElementById(arguments[0])).backgroundColor === 'rgba(0, 0, 0, 0)';"
        to = "window.scrollTo(0, document.getElementById(arguments[0]).offsetTop);"
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(False), prefs=tone.browser_prefs(), firefox=binary) as b:
            for page, dark, color in (("/d.html", True, "rgb(32, 32, 32)"), ("/l.html", False, "rgb(232, 237, 240)")):
                with self.subTest(page=page):
                    tone.set_scheme(b, dark)
                    b.navigate(srv.url(page, "dark.test" if dark else "light.test"))
                    b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                    self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "band", CANVAS), "the band not marked")
                    self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "slot"),
                                    "an empty slot in the page's colour left opaque (%s): %r"
                                    % (page, self.bg_of(b, "slot")))
                    b.js("return new Promise((resolve) => setTimeout(resolve, 300));")
                    for name in ("framed", "pic", "note"):
                        self.assertEqual(self.bg_of(b, name), color, name + ": a kept box made see-through")
                    self.assertEqual(self.bg_of(b, "micro"), "rgb(70, 70, 70)", "a grey box made see-through")
                    b.js(to, "sect")
                    self.assertTrue(b.wait_for(clear, mn.WAIT_TIMEOUT, "inslot"),
                                    "a slot in a section of the page's colour left opaque (%s)" % page)

    def test_late_banner(self):
        for name, binary in tone.browsers():
            with self.subTest(browser=name):
                self.check_late_banner(binary)

    def check_late_banner(self, binary):
        real = bg.sites_load(os.path.join(tone.REPO, "data"))
        sites = bg.Sites({bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY]}, {})
        routes = {"/cookie.html": ("text/html; charset=utf-8", COOKIE_PAGE.encode("utf-8"))}
        with mn.TestServer(routes) as srv, \
                mn.Browser(content_css=dk.stylesheet(True, sites), prefs=tone.browser_prefs(), firefox=binary) as b:
            tone.set_scheme(b, False)
            b.navigate(srv.url("/cookie.html", "light.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            # past the passes of the load: the banner meets the text first
            b.js("return new Promise((resolve) => setTimeout(resolve, 3500));")
            b.js(COOKIE)
            b.js(PICTURE, dk.svg(1, 1, ""))
            # then a pass of the layers: the banner a bar, the light veil
            # its one surface: its dark section, kept before, is not any
            # more (no dark slab in the light veil), its light title inked
            b.js("window.scrollTo(0, 50);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "prompt", BAR), "the cookie banner not a bar")
            self.assertTrue(b.wait_for("return !document.getElementById('notice').hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, bg.ATTR_OWN), "the banner's dark section kept in the veil")
            self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "title", INK, "dark"),
                            "the banner's light title not inked on the light veil")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('notice')).backgroundColor"
                                       " === 'rgba(0, 0, 0, 0)';", mn.WAIT_TIMEOUT),
                            "the banner's dark section left opaque")

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
                # the row of panels on it: a light veil, as cards get
                self.assertTrue(b.wait_for(dk.TILED_IS, mn.WAIT_TIMEOUT, "panel", BLOCK, "veil"),
                                "a panel on the surface left a full panel: %r" % self.bg_of(b, "panel"))
                self.assertEqual(tone.rgba(self.bg_of(b, "panel"))[3], bg.BLOCK_VEIL_OPACITY)
                # the menu over nothing, its scrim at opacity 0: a sidebar
                # holding the site's menus, veiled all the same
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "menu", BAR), "the app's side menu not veiled")
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
                  "/layer.html": ("text/html; charset=utf-8", LAYER_BAR_PAGE.encode("utf-8")),
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
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('bar'), '::before').backdropFilter;"),
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

            # a tall see-through header at the top: a header holding the
            # site's links, veiled before any scroll, and still once content
            # lies under its lower row only (its middle line on its own notice)
            b.navigate(srv.url("/tall.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "tall", BAR), "a see-through header at the top not marked")
            b.js("window.scrollTo(0, 110);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "tall", BAR),
                            "a tall see-through header over content under its lower row not marked")
            self.assertFalse(b.wait_for(dk.MARKED, 2.0, "marks", BAR), "a thin see-through strip marked")

            # a cookie banner over the text gets the bar's veil (a floating
            # layer), and a modal
            b.navigate(srv.url("/banner.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                       mn.WAIT_TIMEOUT, tone.LIVE))
            b.js("document.getElementById('modal').style.display = 'block'; window.dispatchEvent(new Event('resize'));")
            self.assertFalse(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']');",
                                        2.0, CANVAS), "a fixed layer over the text marked as the background")
            self.assertTrue(b.wait_for("return getComputedStyle(document.getElementById('consent')).backgroundColor"
                                       " === arguments[0];", mn.WAIT_TIMEOUT, DARK_SURFACE),
                            "the cookie banner not veiled")

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

            # a sticky header painted by an empty layer behind its content,
            # filled below the notice: a bar once stuck over the hero, the
            # layer still see-through under the veil
            b.navigate(srv.url("/layer.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.getElementById('paint')"
                                       ".getAttribute(arguments[0]) === 'fill';",
                                       mn.WAIT_TIMEOUT, CANVAS), "the header's layer not filled")
            self.assertFalse(self.marked(b, "bar", BAR), "marked below the notice")
            b.js("window.scrollTo(0, 300);")
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "bar", BAR),
                            "a stuck header painted by its filled layer not marked")
            self.assertEqual(b.js(BAR_COLOR), DARK_SURFACE)
            self.assertEqual(b.js("return getComputedStyle(document.getElementById('paint')).backgroundColor;"),
                             "rgba(0, 0, 0, 0)")

            # an app shell: its header at the top gets the bar's veil (a
            # header in the flow), its other parts in the flow keep their look
            for page in ("/shell.html", "/rows.html"):
                b.navigate(srv.url(page, "dark.test"))
                b.js(dk.RUN, self.content_js, self.darkreader_js, [])
                self.assertTrue(b.wait_for("return document.documentElement.hasAttribute(arguments[0]);",
                                           mn.WAIT_TIMEOUT, tone.LIVE))
                self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "top", BAR), "the shell's header not veiled")
                self.assertEqual(b.js("return getComputedStyle(document.getElementById('top')).backgroundColor;"),
                                 DARK_SURFACE)
                self.assertFalse(b.wait_for("return !!document.querySelector('[' + arguments[0] + ']:not(#top)');",
                                            2.0, BAR), "a part of the shell marked (%s)" % page)

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
            # the header in the flow at the top: the veil of a header (heads)
            self.assertTrue(b.wait_for(dk.MARKED, mn.WAIT_TIMEOUT, "head", BAR), "the header not veiled under a scroll lock")
            self.assertEqual(self.bg_of(b, "head"), DARK_SURFACE)

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
            # clipped to them: shaded in their own hue, the fill drawn over
            # the gradient
            tone.set_scheme(b, False)
            b.navigate(srv.url("/ink.html", "dark.test"))
            b.js(dk.RUN, self.content_js, self.darkreader_js, [])
            self.assertTrue(b.wait_for("return document.getElementById('clip').getAttribute(arguments[0]) === 'soft';",
                                       mn.WAIT_TIMEOUT, INK), "light gradient text on the light glass not marked")
            r, g, b_, _ = tone.rgba(b.js("return getComputedStyle(document.getElementById('clip')).color;"))
            self.assertGreater(r, b_ + 40, "the gradient text lost its hue")
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

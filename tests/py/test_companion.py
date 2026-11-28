"""companion: the add-on sources in extension/, the xpi built from them, the
native messaging manifest and the host wrapper (section companion).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from fakehome import REPO, load_script

bg = load_script()
EXT = REPO / bg.EXTENSION_DIR


def read(name):
    return (EXT / name).read_text(encoding="utf-8")


def strip_comments(js):
    return "\n".join(line for line in js.splitlines() if not line.lstrip().startswith("//"))


class ExtensionSourcesTest(unittest.TestCase):

    def setUp(self):
        self.manifest = json.loads(read("manifest.json"))

    def test_version_follows_plugin(self):
        # The add-on version moves with plugin.json, at release time (the
        # hello message then sends the new version).
        plugin = json.loads((REPO / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["version"], plugin["version"])

    def test_manifest_as_amo_writes_it(self):
        # AMO rewrites manifest.json as json.dumps(indent=2), no final
        # newline; the signed xpi must match the sources byte for byte.
        text = read("manifest.json")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2))

    def test_manifest(self):
        gecko =self.manifest["browser_specific_settings"]["gecko"]
        self.assertEqual(gecko["id"], bg.COMPANION_ID)
        # CSS nesting, which the gated stylesheets need, came with Firefox 117.
        self.assertEqual(gecko["strict_min_version"], "117.0")
        # AMO asks for it: the add-on talks only to the local native host.
        self.assertEqual(gecko["data_collection_permissions"], {"required": ["none"]})
        self.assertEqual(self.manifest["manifest_version"], 2)
        self.assertEqual(self.manifest["permissions"],
                         ["nativeMessaging", "tabs", "storage", "*://*/*"])
        # Never in a private window, whatever about:addons says.
        self.assertEqual(self.manifest["incognito"], "not_allowed")
        scripts = self.manifest["content_scripts"]
        self.assertEqual(len(scripts), 2)
        # frame.js in every frame, to keep the glass styles off the embedded
        # pages (1.3.1)
        self.assertEqual(scripts[0]["js"], ["frame.js"])
        self.assertEqual(scripts[0]["run_at"], "document_start")
        self.assertIs(scripts[0]["all_frames"], True)
        # Dark Reader first: content.js uses its global
        self.assertEqual(scripts[1]["js"], ["vendor/darkreader.js", "theme.js", "content.js"])
        self.assertEqual(scripts[1]["run_at"], "document_start")
        self.assertNotIn("all_frames", scripts[1])  # main document only (v1.1)
        for script in scripts:
            self.assertEqual(script["matches"], ["http://*/*", "https://*/*"])
        self.assertEqual(self.manifest["background"]["scripts"], ["background.js"])
        self.assertEqual(sorted(p.name for p in EXT.iterdir()),
                         ["background.js", "content.js", "frame.js", "manifest.json", "theme.js",
                          "vendor"])
        self.assertEqual(sorted(p.name for p in (EXT / "vendor").iterdir()),
                         ["darkreader-LICENSE.txt", "darkreader.js"])

    def test_vendored_dark_reader(self):
        # The npm build of Dark Reader, unmodified, with its MIT licence.
        js = read("vendor/darkreader.js")
        self.assertTrue(js.startswith("/**\n * Dark Reader v4.9.135\n * https://darkreader.org/\n"))
        self.assertIn("exports.enable = enable;", js)
        self.assertIn("exports.setFetchMethod = setFetchMethod;", js)
        lic = read("vendor/darkreader-LICENSE.txt")
        self.assertTrue(lic.startswith("MIT License"))
        self.assertIn("Dark Reader Ltd.", lic)

    def test_content_names_each_function_once(self):
        # a second declaration of a name silently replaces the first in the
        # whole script (an image loader named like the tone's page layer
        # test turned every dark card into a page layer)
        names = re.findall(r"^function\s+(\w+)", read("content.js"), re.M)
        twice = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual(twice, [])

    def test_content_watches_only_the_root_attributes(self):
        # Fix F: no subtree observer (it would wake on every DOM insertion);
        # the attributes of <html>, and the document's own children (a
        # replaced <html>). One exception: while the page is darkened (Dark
        # Reader watches the whole tree then anyway), new frames, to give
        # them their colour scheme before they are drawn.
        js = strip_comments(read("content.js"))
        self.assertEqual(js.count("subtree"), 1)
        schemes = js[js.index("const newFrames"):js.index("function up(el)")]
        self.assertIn('el.localName === "iframe" || el.firstElementChild && el.querySelector("iframe")', schemes)
        self.assertIn("newFrames.observe(document, {childList: true, subtree: true});", schemes)
        self.assertIn("newFrames.disconnect();", schemes)
        self.assertLess(schemes.index("if (!darkened)"), schemes.index("newFrames.observe("))
        observes = re.findall(r"\.observe\(([^;]*)\);", js)
        self.assertEqual(sorted(observes), sorted([
            "document, {childList: true}",
            # the body's size (not its DOM), while the tone is unsettled
            "document.body",
            "root, {attributes: true}",
            # the layers: the size of the document, the body, its children
            # and the marked elements; the body's children (not its subtree)
            "document.documentElement",
            "document.body",
            "el",
            "el",
            "el",
            "document.body, {childList: true}",
            # each canvas once, to judge a backdrop shown or grown later
            "canvas",
            # the style sheets of <head> (its children only) and the
            # attributes of <body>: the page's own colours changing late
            "head, {childList: true}",
            "body, {attributes: true}",
            # new frames, while the page is darkened
            "document, {childList: true, subtree: true}",
        ]))
        self.assertIn('const LIVE = "%s";' % bg.ATTR_LIVE, js)
        self.assertIn('const OFF = "%s";' % bg.ATTR_OFF, js)

    def test_content_measures_the_tone(self):
        # the tone of the page, from the colour of its text, in
        # ATTR_TONE; measured again on a change of the root attributes that
        # are not ours (so setting ours never loops), of the colour scheme,
        # and on load. Nothing is sent: no runtime message from here.
        js = strip_comments(read("content.js"))
        self.assertIn('const TONE = "%s";' % bg.ATTR_TONE, js)
        self.assertIn('const OWN = "data-browserglass-";', js)
        for name in (bg.ATTR_LIVE, bg.ATTR_OFF, bg.ATTR_TONE):
            self.assertTrue(name.startswith("data-browserglass-"))
        measure = js[js.index("function measure()"):js.index("function update()")]
        self.assertIn("document.body || document.documentElement", measure)
        self.assertIn("getComputedStyle(el).color", measure)
        self.assertIn('"dark" : "light"', measure)
        self.assertNotIn("setAttribute", measure)
        # computed colours keep the page's colour space (oklch() for
        # Tailwind v4, color() for wide gamut)
        lum = js[js.index("function luminance("):js.index("function measure()")]
        for space in ("rgb", "oklch", "oklab", "lab", "lch", "srgb", "display-p3", "xyz"):
            self.assertIn('case "%s":' % space, lum)
        self.assertIn('m[1] === "color"', lum)
        # the visible text votes (not the body's colour alone: YouTube),
        # the body's colour only without visible text
        self.assertIn("createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,", measure)
        self.assertIn("tally(document.body, menus);", measure)
        self.assertIn("read < SAMPLE_NODES", measure)
        self.assertIn("checkVisibility(", measure)
        # text this script inked votes with the colour the page gave it
        self.assertIn("y = luminance(ownColor(p));", measure)
        self.assertIn("return el.hasAttribute(INK) && inkFrom.has(el) ? inkFrom.get(el)"
                      " : getComputedStyle(el).color;", js)
        self.assertIn("sampled ? light > dark : isLight(getComputedStyle(el).color)", measure)
        # the text outside the site's menus and the mid-grey band decides
        # first (Hacker News' grey meta lines, a portal's long dark menu),
        # then the rest; the menus are skipped whole (Le Monde's header
        # holds more text nodes than SAMPLE_WALK) and read only on a page
        # with no other text; the text on the page's own background votes
        # before the text on cards painting a background of their own
        # (a news site's dark video cards on its white page) or drawn over
        # pictures (a shop's banners); a band like the page's background
        # that starts below the first screen (a shop's dark footer) is a card
        self.assertIn("const isFirm = y <= MID_LOW || y >= MID_HIGH;", measure)
        self.assertIn("if (menus && (siteChrome(node) || overlay(node))) {", measure)
        self.assertIn("return NodeFilter.FILTER_REJECT;", measure)
        self.assertIn("if (main[0] + main[1] === 0)\n      for (const m of menus)\n        tally(m, null);", measure)
        self.assertIn("const levels = [pageFirm, page, mainFirm, main, firm, all];", measure)
        # a level decides with enough text (a lone short line gives way
        # to the next one), else the first with any; text out of sight
        # (a skip link above the page, a clipped label) does not vote
        self.assertIn("const decides = (t) => t[2] >= VOTE_NODES || t[0] + t[1] >= VOTE_CHARS;", measure)
        self.assertIn("levels.find(decides) || levels.find((t) => t[0] + t[1] > 0) || all", measure)
        # without text on the page's background, a drawing board (a canvas
        # filling the window, painted opaque, unfiltered: Excalidraw) gives
        # the tone by its pixels, before the cards and pictures vote; then
        # the body's own opaque colour, read past the page rules (a white
        # portal whose sections are hidden until scrolled to: Swisscom)
        # first under a modal dialog (the page under it out of the hit tests)
        self.assertIn('const modal = document.querySelector(":modal") !== null;', measure)
        self.assertIn("const board = document.body && (modal || !decides(page)) ? boardTone() || paintTone() : null;",
                      measure)
        paint = js[js.index("function paintTone("):js.index("function measure()")]
        self.assertIn("const fill = unstyled(document.body);", paint)
        self.assertIn("alpha(fill) >= SOLID ? isLight(fill) : null", paint)
        board = js[js.index("function boardTone("):js.index("function measure()")]
        self.assertIn("seen < BOARD_COVER * w * h", board)
        self.assertIn('getComputedStyle(c).filter !== "none"', board)
        self.assertIn("s && s.clear <= BOARD_CLEAR", board)
        self.assertIn('s.inks[INK_STEPS / 2] > 0.179 ? "light" : "dark"', board)
        self.assertIn("&& !unseen(p)", measure)
        hidden = js[js.index("function unseen("):js.index("function measure()")]
        self.assertIn("style.overflow !== \"visible\"", hidden)
        self.assertIn("style.clip", hidden)
        self.assertIn("style.clipPath", hidden)
        # nor text whose middle lies beside the window (a carousel's next slide)
        self.assertIn("x < 0 || x >= window.innerWidth", hidden)
        self.assertIn("if (!onCard(p, cards) && !onPicture(p, pictures)) {", measure)
        card = js[js.index("function onCard("):js.index("function measure()")]
        self.assertIn("const color = getComputedStyle(el).backgroundColor;\n"
                      "  const value = alpha(color) >= OWN_BG", card)
        # a box painting the colour of the page layer it lies on is the
        # page (Watson's white teasers in its white rows, once those rows
        # are glass), that layer's colour read as it paints it now
        self.assertIn("? !backdrop(el) && !onLayer(el, color) : onCard(el.parentElement, cards);", card)
        self.assertIn("layerFills.set(e, unmarked(e, CANVAS));", card)
        self.assertIn("return layerFills.get(e) === color;", card)
        self.assertIn("(el.hasAttribute(CANVAS) || large(el) || panel(el))\n"
                      "    && el.getBoundingClientRect().top + window.scrollY < window.innerHeight;", card)
        # a page panel not yet marked (ch.ch's white left half): wide, tall,
        # down to the bottom of the window
        self.assertIn("const PANEL_WIDE = 0.4;", card)
        self.assertIn("r.width >= PANEL_WIDE * document.documentElement.clientWidth && tall(el)", card)
        self.assertIn('const PICTURES = new Set(["img", "picture", "video", "canvas", "svg"]);', card)
        self.assertIn("pictures.size < PICTURE_TESTS", card)
        self.assertIn("const stack = stackAt(x, y);", card)
        # what is painted over the text (a dialog's scrim) is skipped
        self.assertIn("&& (holds(el, e) || holds(e, el)));", card)
        self.assertIn("for (const e of at > 0 ? stack.slice(at) : stack)", card)
        self.assertIn("walked < SAMPLE_WALK", measure)
        self.assertIn("sampled = all[0] + all[1];", measure)
        chrome = js[js.index("function siteChrome("):js.index("function measure()")]
        self.assertIn('if (name === "nav")', chrome)
        self.assertIn('role === "navigation" || role === "banner" || role === "contentinfo"', chrome)
        self.assertIn('closest("article, aside, main, nav, section")', chrome)
        # a dialog over the page votes as the menus do
        self.assertIn('el.localName === "dialog" || role === "dialog" || role === "alertdialog"', chrome)
        self.assertIn('el.getAttribute("aria-modal") === "true"', chrome)
        # a page still rendering: each resize of the body measures again,
        # until the text settles the tone or RESIZE_MEASURES
        upd = js[js.index("const sizes = new ResizeObserver"):js.index("function paint()")]
        self.assertIn("++resizeMeasures > RESIZE_MEASURES", upd)
        self.assertIn("sampled >= ENOUGH_TEXT || resizeMeasures >= RESIZE_MEASURES", upd)
        self.assertIn("sizes.observe(document.body)", upd)
        observer = js[js.index("new MutationObserver"):js.index("function watch()")]
        self.assertIn('r.attributeName !== "style" && !r.attributeName.startsWith(OWN)', observer)
        self.assertIn("measure()", observer)
        # the tone of the text shown: measured again once set (the site
        # styles may recolour the text), at most twice
        paint_ = js[js.index("function paint()"):js.index("function apply(")]
        self.assertIn("pass < 2", paint_)
        self.assertLess(paint_.index("setAttribute(TONE"), paint_.index("measure()"))
        self.assertIn('matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {',
                      js)
        scheme = js[js.index('addEventListener("change", () => {'):]
        scheme = scheme[:scheme.index("});")]
        self.assertIn("themeRun(themeCfg, false);", scheme)
        self.assertIn("update();", scheme)
        self.assertIn('addEventListener("DOMContentLoaded", update)', js)
        self.assertIn('addEventListener("load", update)', js)
        self.assertNotIn("sendMessage", js)
        # one timer only: the judgment of a theme written early (theme.js)
        self.assertEqual(js.count("setTimeout"), 1)
        self.assertIn("if (typeof themeState !== \"undefined\" && themeState.early)\n"
                      "    setTimeout(update, THEME_JUDGE_MS + 50);", js)
        self.assertNotIn("setInterval", js)
        # ATTR_TONE only once the list is known, as LIVE.
        paint = js[js.index("function paint()"):js.index("function apply(")]
        self.assertLess(paint.index("off === null"), paint.index("setAttribute(TONE"))
        self.assertEqual(js.count("setAttribute(TONE"), 1)

    def test_content_opens_shadow_trees(self):
        # the layer passes and the ink's look beneath a fixed layer hit test
        # through the open shadow trees of the hosts at a point (a web
        # component's header, band, button), at most SHADOW_HOSTS a point,
        # and walk up across them (holds, outer: up)
        js = strip_comments(read("content.js"))
        self.assertIn("const SHADOW_HOSTS = 8;", js)
        stack = js[js.index("function stackAt("):js.index("function holds(")]
        self.assertIn("opened.size < SHADOW_HOSTS", stack)
        self.assertIn("tree.elementsFromPoint(x, y)", stack)
        self.assertIn("shadows.add(tree);", stack)
        self.assertIn("merged.lastIndexOf(el) === i", stack)
        self.assertIn("for (let e = b; e; e = up(e))", js[js.index("function holds("):js.index("function outer(")])
        for name in ("markCanvas()", "over(", "markBars()", "markFills()", "beneath(", "onPicture("):
            body = js[js.index("function " + name):]
            body = body[:body.index("\n}\n")]
            self.assertIn("stackAt(", body, name)
            self.assertNotIn("document.elementsFromPoint", body, name)
        # their bars are found again, filled, veiled in their own tree;
        # the passes over icons, pictures and glyphs read the trees met
        bars = js[js.index("function markBars()"):js.index("function markFills()")]
        self.assertIn('marked("[" + BAR + "]")', bars)
        self.assertIn("veil(el.getRootNode());", bars)
        self.assertIn("(root instanceof ShadowRoot ? root : document).getElementById(VEIL)", js)
        self.assertIn("const kids = inside(bar);", js)
        self.assertIn("const kids = inside(holder);", js)
        for part in ('everywhere("svg:not([" + DR_INVERT + "])")', 'everywhere("img, svg, canvas")',
                     'everywhere("svg[" + DR_INVERT + "]")', 'everywhere(":empty")'):
            self.assertIn(part, js)
        self.assertIn("for (const tree of shadows)", js[js.index("function everywhere("):js.index("function stackAt(")])
        # the bar's colour reaches a shadow tree as a custom property
        self.assertIn("background: var(%s) !important;" % bg.NAV_BAR_VAR, bg._CONTENT_LAYERS)
        # a see-through layer painted by an empty ::before or ::after of its
        # own (a web component's panel) is a layer of the page, see-through
        paint = js[js.index("function underPaint("):js.index("function sections(")]
        self.assertIn("for (const pseudo of PSEUDOS)", paint)
        self.assertIn(">= FILL_COVER * r.width * r.height", paint)
        canvas = js[js.index("function markCanvas()"):js.index("function sections(")]
        self.assertLess(canvas.index("if (clear(el)) {"), canvas.index("if (painter(el)) {"))
        self.assertIn("const paint = underPaint(el);", canvas)
        self.assertIn("layer(el, paint.color);", canvas)
        # and so are a layer's see-through ancestors painted that way (a
        # panel's fixed ::before over a view background at a negative
        # z-index, listed under it)
        self.assertIn("const under = (el) => {", canvas)
        self.assertIn("for (let p = up(el); p && p !== root && p !== document.body && clear(p); p = up(p))", canvas)
        self.assertIn("under(el);\n    sections(stack, n - 1, el);", canvas)
        self.assertIn("el.removeAttribute(FILLED);", canvas)

    def test_content_marks_page_layers(self):
        # navigation bars along a window edge get ATTR_BAR, the page's own
        # background ATTR_CANVAS (_CONTENT_LAYERS), looked for again as the
        # page changes, without a subtree observer nor a timer
        js = strip_comments(read("content.js"))
        self.assertIn('const BAR = "%s";' % bg.ATTR_BAR, js)
        self.assertTrue(bg.ATTR_BAR.startswith("data-browserglass-"))
        self.assertIn("[" + bg.ATTR_BAR + "]", bg._CONTENT_LAYERS)
        self.assertIn("[" + bg.ATTR_CANVAS + "]", bg._CONTENT_LAYERS)
        bars = js[js.index("function markBars()"):js.index("let layerFrame")]
        self.assertIn("off !== false", bars)
        # fixed or sticky only, with a background of its own, the outermost
        # one then (1.3.1: no more app shell bars in the flow)
        self.assertIn('position === "fixed" || position === "sticky"', bars)
        self.assertIn("if (along(el) && pinned(el))", bars)
        self.assertIn("alpha(getComputedStyle(el).backgroundColor) >= OWN_BG", bars)
        self.assertIn('if (outer(el, "[" + BAR + "]"))\n      el.removeAttribute(BAR);', bars)
        self.assertIn("const OWN_BG = 0.5;", js)
        for gone in ("inFlow", "shell", "scrollHeight"):
            self.assertNotIn(gone, bars[:bars.index("\nfunction ", 1)])
        # headers and bottom bars, sidebars, on all four edges
        self.assertIn("r.top <= EDGE || r.bottom >= h - EDGE", bars)
        self.assertIn("r.left <= SIDE_GUTTER || r.right >= w - SIDE_GUTTER", js[js.index("function sideBar("):])
        self.assertIn("[[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y],\n"
                      "      [SIDE_GUTTER + EDGE, y], [w - SIDE_GUTTER - EDGE, y]]", bars)
        # a sidebar holding the site's menus: a bar though see-through
        self.assertIn("backed(el) || (!blank(el) && (over(el, w, h) || navSide(el, w, h)))", bars)
        # an empty see-through positioner is no bar, nor stays one
        self.assertIn("(blank(el) && !(barColors.get(el) || new Set()).size)", bars)
        self.assertIn("return sideBar(el.getBoundingClientRect(), w, h) && (siteChrome(el) || siteMenus(el));", js)
        self.assertIn("removeAttribute(BAR)", bars)
        self.assertIn("mark(el, BAR)", bars)
        mark = js[js.index("function markCanvas()"):js.index("function markBars()")]
        # a colour still fading (Dark Reader just off) is no layer's yet
        self.assertIn("if (alpha(color) >= SOLID && (large(el) || column(el, color)) && !fading(el)) {\n"
                      "          for (const row of pile(el).rows)\n"
                      "            if (row === el || plain(row, color))\n"
                      "              layer(row, color);", mark)
        # a column built of rows (Watson's clusters): siblings in its
        # colour, as wide, each starting where the one above ends, judged
        # as one box
        tall_ = js[js.index("function tall("):js.index("function wide(")]
        self.assertIn("const run = pile(el);\n  return run.bottom - run.top >= COLUMN_TALL * window.innerHeight;", tall_)
        for part in ("Math.abs(b.left - r.left) <= SECTION_EDGE && Math.abs(b.right - r.right) <= SECTION_EDGE",
                     "Math.abs(b.bottom - run.top) > SECTION_EDGE", "Math.abs(b.top - run.bottom) > SECTION_EDGE",
                     "queueMicrotask(() => piles.clear());", "!LAID_OVER.has(s.position)",
                     "rowColor(e, s) === color", "const color = rowColor(el, style);"):
            self.assertIn(part, tall_)
        self.assertIn("tall(el) && pile(el).bottom >= (1 - COLUMN_GAP) * h",
                      js[js.index("function column("):js.index("function stuckSide(")])
        # a box of the page's colour of any size (Heise's empty ad slots),
        # off the page's layer or on it: glass, unless it is outlined,
        # holds text of its own or a picture, or covers something else
        self.assertIn("} else if (pageBox(el, stack, n)) {\n          el.setAttribute(CANVAS, FILL);\n"
                      "          sections(stack, n - 1, el);", mark)
        box = js[js.index("function pageBox("):js.index("function spans(")]
        for part in ("!pageColors.has(style.backgroundColor)", 'style.boxShadow !== "none"',
                     'CORNERS.some((c) => parseFloat(style["border" + c + "Radius"]) > 0)',
                     "node.nodeType === Node.TEXT_NODE && node.data.trim()", "el.querySelector(BOX_MEDIA)",
                     "stack.slice(n + 1).every((under) => holds(under, el)) && overOwn(el, r)",
                     "k.width * k.height >= FILL_COVER * r.width * r.height"):
            self.assertIn(part, box)
        self.assertIn("if (pageBox(el, stack, n)) {\n      el.setAttribute(CANVAS, FILL);\n      continue;",
                      js[js.index("function sections("):js.index("function pageBox(")])
        self.assertIn("pageColors.add(color);\n    layerColors.set(el, color);\n    mark(el, CANVAS);", mark)
        # a row more along each edge of the window: a band in view only
        # below the grid's last row (impots.gouv.fr) is found unscrolled
        self.assertIn(".concat(h - GRID_EDGE);", mark)
        # what a fixed or sticky element holds is left to the bars there
        # (a sticky header's row of links, at the top edge)
        self.assertIn("const stack = j < GRID ? at : at.filter((el) => !held(el));", mark)
        self.assertIn('if (/^(fixed|sticky)$/.test(getComputedStyle(e).position))', mark)
        # a surface kept for its text (KEPT) ends the walk: never a layer
        self.assertIn("if (el.hasAttribute(KEPT))\n          break;", mark)
        self.assertLess(mark.index("if (el.hasAttribute(KEPT))"), mark.index("if (el.hasAttribute(CANVAS))"))
        # a page column or an app's surface, a band across the window: a
        # plain colour on the page's side, no picture filling it, not fixed
        column = js[js.index("function column("):js.index("function markCanvas()")]
        self.assertIn("COLUMN_CHROMA", column)
        self.assertIn('tone === "dark" ? y <= COLUMN_DARK : y >= COLUMN_LIGHT', column)
        self.assertIn("if (!toned(color, most) || (lines ? picture(style) : style.backgroundImage !== \"none\"))",
                      column)
        # a lone card may draw its frame with thin gradient lines (lines)
        self.assertIn("function plain(el, color, most = COLUMN_CHROMA, lines = false)", column)
        # any colour space the page computes (color(srgb ...)), read in sRGB
        self.assertIn("const c = channels(color), y = luminance(color);", column)
        self.assertIn("(Math.max(...c) - Math.min(...c)) / 255 <= most", column)
        self.assertIn('style.backgroundImage !== "none"', column)
        self.assertIn("el.querySelectorAll(COLUMN_MEDIA)", column)
        self.assertIn('getComputedStyle(e).position === "fixed"', column)
        self.assertIn('wide(el) && getComputedStyle(el).position !== "sticky"', column)
        # a header across the page column it stays in, painted by its child
        self.assertIn('outer(el, "[" + CANVAS + "]")', bars)
        self.assertIn("if (!el.hasAttribute(BAR) && (backed(el) || (!blank(el) && (over(el, w, h) || navSide(el, w, h)))))", bars)
        # a child faded out (a drawer's scrim at opacity 0) paints nothing
        self.assertIn("kid.checkVisibility({visibilityProperty: true, opacityProperty: true})", bars)
        # any child covering it, one filled too (an empty layer behind the
        # content, in the page's colour, filled before the header stuck)
        self.assertIn("for (const kid of layered(el))", bars)
        self.assertIn("kid.getAttribute(CANVAS) === FILL", bars)
        self.assertIn("const SOLID = 0.99;", js)
        watch = js[js.index("let layerFrame"):js.index("function apply(")]
        self.assertIn("requestAnimationFrame(", watch)
        self.assertIn("for (const el of document.body.children)", watch)
        self.assertIn("bodyKids.observe(document.body, {childList: true})", watch)
        self.assertIn("const SETTLE_MS = [100, 500, 1500, 3000];", watch)
        for line in ('for (const type of ["scroll", "transitionend"])',
                     'for (const type of ["scrollend", "resize", "load"])',
                     'for (const type of ["click", "submit"])',
                     'for (const type of ["popstate", "hashchange", "load"])'):
            self.assertIn(line, js)
        # the settle passes measure the tone again (a page styled after its
        # load), not on a darkened page
        tick = js[js.index("function settleTick("):js.index("function apply(")]
        self.assertIn("if (!darkened) {\n      measure();\n      darken();\n      paint();", tick)
        for fn in ("function update()", "function apply("):
            body = js[js.index(fn):]
            body = body[:body.index("\n}")]
            self.assertIn("watchLayers();", body)
            self.assertIn("markBars();", body)
            self.assertIn("ink();", body)

    def test_content_marks_fills(self):
        # inside a fixed or sticky element, an empty scrim or the panel that
        # covers a bar, painted with the page's colour, turns to glass too
        js = strip_comments(read("content.js"))
        self.assertIn('const FILL = "fill";', js)
        self.assertIn("const pageColors = new Set();", js)
        fills = js[js.index("function markFills()"):js.index("const INK_RATIO")]
        self.assertIn("off !== false", fills)
        self.assertIn("!pageColors.size", fills)
        self.assertIn('position === "fixed" || position === "sticky"', fills)
        self.assertIn("!pageColors.has(style.backgroundColor)", fills)
        self.assertIn("NOT_FILLS.has(el.localName)", fills)
        self.assertIn("i < kids.length && i < FILL_NODES", fills)
        self.assertIn("bar && r.width * r.height >= FILL_COVER * box.width * box.height", fills)
        # a panel as wide as a sticky page layer, in its colour: filled
        self.assertIn('const layer = holder.getAttribute(CANVAS) === "";', fills)
        self.assertIn("(layer && r.width >= FILL_COVER * box.width && r.height > 0)", fills)
        self.assertIn("el.setAttribute(CANVAS, FILL)", fills)
        # an empty ::before or ::after of the holder in the page's colour:
        # FILLED names it, the glass styles clear it, gone with the layers
        self.assertIn('const FILLED = "%s";' % bg.ATTR_FILLED, js)
        self.assertIn('const PSEUDOS = ["before", "after"];', js)
        pseudo = js[js.index("function pageFill("):js.index("function markFills()")]
        self.assertIn('getComputedStyle(el, "::" + pseudo)', pseudo)
        self.assertIn('style.content === "\\"\\""', pseudo)
        self.assertIn("pageColors.has(style.backgroundColor)", pseudo)
        self.assertIn("holder.setAttribute(FILLED, ", fills)
        for p in ("before", "after"):
            self.assertIn('[%s~="%s"]::%s' % (bg.ATTR_FILLED, p, p), bg._CONTENT_LAYERS)
        self.assertIn("removeAttribute(FILLED)", js[js.index("function markCanvas()"):js.index("function markBars()")])
        self.assertIn("removeAttribute(FILLED)", js[js.index("function darken()"):js.index("function frameSchemes()")])
        for name in ('"img"', '"video"', '"canvas"', '"iframe"', '"input"'):
            self.assertIn(name, js[js.index("const NOT_FILLS"):js.index("function markFills()")])
        # fills keep their mark while small, and go with the page's layers
        mark = js[js.index("function markCanvas()"):js.index("function markFills()")]
        self.assertIn("if (!glass || (!large(el) && !tall(el) && !wide(el) && el.getAttribute(CANVAS) !== FILL))", mark)
        # every pass that marks the bars marks the fills after them
        for at in [i for i in range(len(js)) if js.startswith("markBars();", i)]:
            self.assertTrue(js[at:].split("\n", 2)[1].strip() == "markFills();", js[at - 80:at + 40])

    def test_content_fills_bar_rows(self):
        # a row of a marked bar in the bar's colour or the page's turns to
        # glass under the veil; a layer behind the bar's content holding
        # text (skip links) is hidden instead (UNDER), not cleared
        js = strip_comments(read("content.js"))
        self.assertIn('const UNDER = "%s";' % bg.ATTR_UNDER, js)
        self.assertIn("[" + bg.ATTR_UNDER + "]:not(:focus-within) {{ opacity: 0 !important; }}", bg._CONTENT_LAYERS)
        bars = js[js.index("function markBars()"):js.index("function markFills()")]
        self.assertIn("barColors.set(el, new Set([...(barColors.get(el) || []), ...painted(el), ...rowColors(el)]));\n"
                      "      mark(el, BAR);\n      rows.push(el.getBoundingClientRect());", bars)
        # a row held right against a marked bar joins the stack
        self.assertIn("(r.top <= EDGE || r.bottom >= h - EDGE || stacked(el, r))", bars)
        self.assertIn("for (const py of [rows[k].bottom + EDGE, rows[k].top - EDGE])", bars)
        self.assertIn("if (glassPage)\n    for (const el of bars)\n      if (el.hasAttribute(BAR))\n"
                      "        fillBar(el);", bars)
        self.assertIn("const BAR_SHARE = 0.3;", js)
        self.assertIn("const BAR_NEAR = 16;", js)
        fill = js[js.index("function fillBar("):js.index("function markFills()")]
        self.assertIn("[...pageColors, ...(barColors.get(bar) || [])]", fill)
        self.assertIn("colors.some((c) => near(c, paint.color))", fill)
        # a menu hidden in a row keeps its colour once opened
        self.assertIn("!r.width || !r.height", fill)
        self.assertIn("!el.checkVisibility({visibilityProperty: true, opacityProperty: true})", fill)
        self.assertIn("const band = barRow(r, box) || r.height >= FILL_COVER * box.height"
                      " || r.width >= FILL_COVER * box.width;", fill)
        self.assertIn("const row = band\n"
                      "      || (holds(bar, outer(el, \"[\" + CANVAS + \"]\")) && !el.matches(FIELD_BOXES)"
                      " && !el.querySelector(FIELD_BOXES));", fill)
        # a row painted by an empty pseudo-element of its own: that one
        # see-through (FILLED), the bar's colours read through it too
        self.assertIn("alpha(color) >= SOLID ? {pseudo: null, color} : band ? underPaint(el) : null;", fill)
        self.assertIn("el.setAttribute(FILLED, (had + \" \" + names.join(\" \")).trim());", fill)
        # the shadow its other pseudo-element cast under that paint goes too
        self.assertIn("[paint.pseudo, shadowUnder(el, paint.pseudo)]", fill)
        self.assertIn("&& alpha(style.backgroundColor) < CLEAR && z(style) < z(top) ? other : null;", js)
        self.assertIn("return alpha(color) >= SOLID ? {pseudo: null, color} : underPaint(el);", js)
        self.assertIn("!within(r, box)", fill)
        # a field's box or a control in a filled row keeps its box
        self.assertIn('const FIELD_BOXES = "input:not([type=hidden]), button, [role=button], select, textarea";', js)
        helpers = js[js.index("function barRow("):js.index("function underlay(")]
        self.assertIn("return r.width * r.height >= BAR_SHARE * box.width * box.height;", helpers)
        # a header stuck from load is backed by a row in the page's colour
        self.assertIn("(el.getAttribute(CANVAS) === FILL || (alpha(color) >= SOLID && pageColor(color)))", helpers)
        self.assertIn("return pageRow(el);", bars)
        self.assertIn("} else if (underlay(el))\n      el.setAttribute(UNDER, \"\");\n    else\n"
                      "      el.setAttribute(CANVAS, FILL);", fill)
        under = js[js.index("function underlay("):js.index("function fillBar(")]
        self.assertIn("parseInt(style.zIndex, 10) < 0", under)
        self.assertIn("el.textContent.trim()", under)
        # a layer hidden so still backs the bar
        self.assertIn("kid.hasAttribute(UNDER)", bars)
        # a row of the bar glass already (a band) is the bar's own
        over = js[js.index("function over("):js.index("function markBars()")]
        self.assertLess(over.index("if (holds(bar, el))"), over.index("if (el.hasAttribute(CANVAS))"))

    def test_content_sections_fades(self):
        # over a layer of the page's background, the bands across the window
        # in a colour near the page's are layers too, on scroll as well; a
        # linear gradient of the page's colour (a hero's top, a sticky
        # scrim) is painted with that colour see-through (FADE)
        js = strip_comments(read("content.js"))
        self.assertIn('const FADE = "%s";' % bg.ATTR_FADE, js)
        self.assertIn('const FADE_IMAGE = "%s";' % bg.FADE_IMAGE, js)
        self.assertIn("[%s] {{ background-image: var(%s) !important; }}" % (bg.ATTR_FADE, bg.FADE_IMAGE),
                      bg._CONTENT_LAYERS)
        # an empty ::before or ::after fading text out into the page's
        # colour (a list's foot), followed up from the text, cleared with
        # the page's layers
        self.assertIn('const FADE_PSEUDO = "%s";' % bg.ATTR_FADE_PSEUDO, js)
        for p in ("before", "after"):
            self.assertIn('[%s~="%s"]::%s {{ background-image: var(%s-%s) !important; }}'
                          % (bg.ATTR_FADE_PSEUDO, p, p, bg.FADE_IMAGE, p), bg._CONTENT_LAYERS)
        self.assertIn("fadePseudos(el, fadesSeen);", js[js.index("function markInk()"):js.index("function markIcons(")])
        # an empty element beside the way up painting the page's colour on
        # the glass, over nothing but its ancestors: the page's layer too
        strips = js[js.index("function fadePseudos("):js.index("function unfade()")]
        for part in ("clearStrips(p);", "glass = onGlass(p);", "if (glass && (icon || overOwn(el, r)))",
                     "el.setAttribute(CANVAS, FILL);",
                     "return stack.slice(n + 1).every((under) => ancestors.has(under) || under.hasAttribute(CANVAS));"):
            self.assertIn(part, strips)
        # a flat icon button in the page's colour there too (Heise's ticker
        # arrow), over content: a control, not a cover; no round or
        # shadowed one (a carousel's arrow over photos)
        self.assertIn('const ICON_BUTTONS = "button, [role=button]";', strips)
        self.assertIn('style.boxShadow === "none"', strips[strips.index("function iconButton("):])
        # in a bar and in a sticky row glass in the flow (risers), a fade
        # into the bar's colour, a cleared arrow's included (NZZ's)
        bars = strips[strips.index("function barPseudos("):strips.index("function clearPseudos(")]
        for part in ('[...marked("[" + BAR + "]"), ...risers]', "colors.some((c) => near(c, color))",
                     "el.getAttribute(CANVAS) === FILL", "clearPseudos(el, ours);"):
            self.assertIn(part, bars)
        self.assertIn("fades(style, ours)", strips[strips.index("function clearPseudos("):])
        unfade = js[js.index("function unfade()"):js.index("function markBars()")]
        self.assertIn('el.style.removeProperty(FADE_IMAGE + "-" + pseudo);', unfade)
        # a light page Dark Reader leaves alone: a row along the top edge
        self.assertIn('if (tone === "light" && !darkened)\n    rows.push(GRID_EDGE);',
                      js[js.index("function markCanvas()"):js.index("function sections(")])
        canvas = js[js.index("function markCanvas()"):js.index("function sections(")]
        self.assertEqual(canvas.count("found(stack, n, el);"), 3)
        self.assertEqual(canvas.count("sections(stack, n - 1, el);"), 2)
        self.assertEqual(canvas.count("unfade();"), 1)
        self.assertIn("unfade();", js[js.index("function darken()"):js.index("function frameSchemes()")])
        self.assertIn("const SECTION_WIDE = 0.9;", js)
        # across the window, or edge to edge across a page's column: a
        # panel inset on an app's surface stays a card
        self.assertIn("r.width >= w || (r.left <= box.left + SECTION_EDGE && r.right >= box.right - SECTION_EDGE)", js)
        self.assertIn("const w = SECTION_WIDE * document.documentElement.clientWidth;", js)
        walk = js[js.index("function sections("):js.index("function pageColor(")]
        self.assertIn('style.position === "fixed" || style.position === "sticky"', walk)
        # a page column on the layer (a shop's drawer beside the feed) too
        self.assertIn("!(spans(el.getBoundingClientRect(), box, w) || (pageColor(color) && column(el, color)))", walk)
        # on a layer whose own colour is not the tone's (1Password's white
        # wrapper under a dark tone) a plain colour of the tone is the
        # page's too; a kept surface ends the walk
        self.assertIn("const hidden = own !== undefined && !toned(own);", walk)
        self.assertIn("const ours = (color) => pageColor(color) || (hidden && toned(color));", walk)
        self.assertIn("if (el.hasAttribute(KEPT))\n      break;", walk)
        self.assertNotIn("pageColors.add", walk)
        fills = js[js.index("function markFills()"):js.index("const INK_RATIO")]
        self.assertIn("fade(holder, getComputedStyle(holder));", fills)
        self.assertIn("fade(el, style);", fills)
        # a gradient sized to a line (an underline in the text colour) is no fade
        self.assertIn("split(style.backgroundSize).every((s) => COVERS.test(s))", js)
        # scrollbars follow the page's tone over a see-through track, the
        # page's own scrollbar-color winning (not !important, on the root)
        for tone, ink in (("dark", "light"), ("light", "dark")):
            self.assertIn('html:root[%s="%s"] {{ scrollbar-color: rgba({%s}, %s) transparent; }}'
                          % (bg.ATTR_TONE, tone, ink, bg.SCROLL_THUMB_OPACITY), bg._CONTENT_LAYERS)
        # gone with the page's layers
        self.assertIn("glassPage = glass;", js[js.index("function markCanvas()"):js.index("function markBars()")])
        self.assertIn("removeAttribute(UNDER)", js[js.index("function markCanvas()"):js.index("function markBars()")])
        self.assertIn("removeAttribute(UNDER)", js[js.index("function darken()"):js.index("function frameSchemes()")])

    def test_content_marks_seams(self):
        # a border painted in the colour of the see-through layer it frames
        # (a column of rows framed in the page colour) turns see-through
        # with it (SEAM), gone with the page's layers
        js = strip_comments(read("content.js"))
        self.assertIn('const SEAM = "%s";' % bg.ATTR_SEAM, js)
        self.assertIn("[" + bg.ATTR_SEAM + "] {{ border-color: transparent !important; }}", bg._CONTENT_LAYERS)
        seams = js[js.index("function seamed("):js.index("function markSeams()") + 1200]
        self.assertIn('if (style["border" + side + "Color"] !== color)', seams)
        self.assertIn("if (el.hasAttribute(SEAM))\n    return true;", seams)
        self.assertIn("const color = layerColors.get(el);", seams)
        for fn, end in (("function markCanvas()", "function seamed("), ("function markBands(", "function markInk(")):
            self.assertIn("markSeams();", js[js.index(fn):js.index(end)])
        self.assertIn("removeAttribute(SEAM)", js[js.index("function markCanvas()"):js.index("function seamed(")])
        self.assertIn("removeAttribute(SEAM)", js[js.index("function darken()"):js.index("function frameSchemes()")])

    def test_content_marks_ink(self):
        # text left without contrast on the glass gets ATTR_INK, coloured by
        # _CONTENT_LAYERS with the glass colours, which the root hands over
        js = strip_comments(read("content.js"))
        self.assertIn('const INK = "%s";' % bg.ATTR_INK, js)
        self.assertIn('const GLASS = "--browserglass-glass";', js)
        self.assertTrue(bg.ATTR_INK.startswith("data-browserglass-"))
        self.assertIn("--browserglass-glass: rgb({dark})", bg._CONTENT_LAYERS)
        self.assertIn('[%s="dark"]' % bg.ATTR_INK, bg._CONTENT_LAYERS)
        self.assertIn('[%s="light"]' % bg.ATTR_INK, bg._CONTENT_LAYERS)
        mark = js[js.index("function markInk()"):js.index("function ink()")]
        self.assertIn("off !== false", mark)
        self.assertIn("removeAttribute(INK)", mark)
        self.assertIn("contrast(fg, bg) < INK_RATIO", mark)
        self.assertIn("const texts = shownText(near);", mark)
        self.assertIn("for (const el of texts)", mark)
        # the text near the window: blank nodes, and text hidden or far
        # away, do not count against the elements read
        shown = js[js.index("function shownText("):js.index("function contrast(")]
        self.assertIn("i < INK_NODES && shown.length < INK_ELEMENTS", shown)
        self.assertLess(shown.index("if (!n.data.trim())"), shown.index("i++;"))
        self.assertIn("if (near(el) && el.checkVisibility(", shown)
        # a mark taken off with the page's transitions held, the style
        # attribute put back after one flush, once the marks are set
        self.assertIn('el.style.setProperty("transition", "none", "important");', mark)
        self.assertLess(mark.index('setProperty("transition"'), mark.index("el.removeAttribute(INK);"))
        self.assertIn("getComputedStyle(held[0][0]).color;", mark)
        self.assertIn('style === null ? el.removeAttribute("style") : el.setAttribute("style", style);', mark)
        # each text and icon-font glyph inked (inkText) before the flush
        text = js[js.index("function inkText("):js.index("function fontGlyphs(")]
        self.assertIn("el.setAttribute(INK,", text)
        self.assertLess(mark.index("inkText(el, style);"), mark.index("getComputedStyle(held[0][0])"))
        self.assertLess(mark.index("for (const el of [...fontGlyphs(near), ...maskGlyphs(near), ...shownSelects(near), ...typed])\n"
                                   "    inkText(el, getComputedStyle(el));"),
                        mark.index("getComputedStyle(held[0][0])"))
        # a drop-down field near the window, shown, inked as text is
        selects = js[js.index("function shownSelects("):js.index("function markIcons(")]
        self.assertIn('everywhere("select").filter((el) => near(el)', selects)
        self.assertIn(".slice(0, INK_ELEMENTS)", selects)
        # an icon-font glyph: an empty <i> or <span> whose ::before or
        # ::after draws a string in its colour
        glyphs = js[js.index("function fontGlyphs("):js.index("function markIcons(")]
        self.assertIn('const GLYPH_TAGS = "i, span";', js)
        for part in ("found.length < INK_ELEMENTS", "el.firstElementChild || el.textContent.trim() || !near(el)",
                     "DRAWN_STRING.test(s.content) && s.color === color"):
            self.assertIn(part, glyphs)
        self.assertIn("const INK_RATIO = 2;", js)
        # a text drawn with a gradient clipped to it (its fill transparent):
        # every stop must contrast, and what is behind it is its parent's
        self.assertIn("const low = (fg) => contrast(fg, bare) < INK_RATIO || contrast(fg, worst) < INK_RATIO", text)
        # lost is judged on the bare surface, the soft grey over the worst wallpaper
        self.assertIn("const bare = behind(el);", text)
        self.assertIn("const bg = bare === null ? null : behind(el, true, false, true);", text)
        self.assertIn("seen.every(low)", text)
        # straight on the glass, a floor for the wallpaper its tint lets
        # through (a site's pale grey on the light glass)
        self.assertIn("const GLASS_RATIO = 3;", js)
        self.assertIn("|| (grey && bare > DARK_BG && contrast(fg, bare) < GLASS_RATIO && onGlass(el));", text)
        # grey text on the light glass only: a brand colour keeps its own;
        # in a bar, only a grey label is read on the veil over white (an
        # accent colour reading on the veil keeps its own)
        self.assertIn("const grey = inks(style).every((c) => chroma(c) < GLASS_CHROMA);", text)
        self.assertIn("const worst = bare !== null && grey && inBar(el) ? behind(el, true, true, true) : bare;", text)
        self.assertIn("const style = getComputedStyle(el);", mark)
        self.assertIn("inks(style)", text)
        self.assertLess(text.index("inkFrom.set(el, style.color);"), text.index("el.setAttribute(INK,"))
        # a label in the colour of the page layer under it goes with it
        self.assertIn("if (label(el, style))\n      el.setAttribute(CANVAS, FILL);", mark)
        self.assertIn("LAID_OVER.has(style.position)", js[js.index("function label("):js.index("function ownColor(")])
        inks = js[js.index("function clipped("):js.index("function behind(el, follow = true, worst = false, ink = false)")]
        for part in ('split(style.backgroundClip).includes("text")',
                     "style.webkitTextFillColor || style.color",
                     "split(style.backgroundImage).every((image) => GRADIENT.test(image))"):
            self.assertIn(part, inks)
        self.assertIn("if (clipped(getComputedStyle(el)))\n    el = up(el) || root;",
                      js[js.index("function behind(el, follow = true, worst = false, ink = false)"):js.index("function markInk()")])
        self.assertIn("const GRADIENT = /^(repeating-)?(linear|radial|conic)-gradient\\(/;", js)
        # the ink's colour is the fill too (a gradient is drawn under it)
        self.assertIn("-webkit-text-fill-color: currentcolor !important;", bg._CONTENT_LAYERS)
        # without the site's text-shadow, drawn for the colour it had
        self.assertIn("text-shadow: none !important;", bg._CONTENT_LAYERS)

    def test_content_marks_uninverted(self):
        # an inline SVG logo Dark Reader inverts though its shapes paint
        # light (a style sheet it lightened) gets ATTR_UNINVERT, no filter,
        # in the pass of the tiles; the mark goes with the invert, with the
        # darkening and with the page's marks
        js = strip_comments(read("content.js"))
        self.assertIn('const UNINVERT = "%s";' % bg.ATTR_UNINVERT, js)
        self.assertTrue(bg.ATTR_UNINVERT.startswith("data-browserglass-"))
        self.assertIn("[%s]:not(#browserglass-a):not(#browserglass-b) { filter: none !important; }"
                      % bg.ATTR_UNINVERT, bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1))
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertIn("el.removeAttribute(UNINVERT);", ink)
        self.assertLess(ink.index("markTiles(near);"), ink.index("markUninverted(near);"))
        mark = js[js.index("function markUninverted("):js.index("function sample(")]
        for part in ("if (!darkened || !el.hasAttribute(DR_INVERT))",
                     'everywhere("svg[" + DR_INVERT + "]")',
                     "if (r.width * r.height > INVERT_LARGE)",
                     "if (bg === null || bg > DARK_BG)",
                     "if (shape.closest(UNPAINTED))",
                     "[style.fill, style.stroke]",
                     "y > bg && contrast(y, bg) >= INK_RATIO",
                     "ys.length > 0 && read >= UNINVERT_READ * ys.length"):
            self.assertIn(part, mark)
        # Dark Reader's own mark, which this one undoes
        self.assertIn('const DR_INVERT = "data-darkreader-inline-invert";', js)
        self.assertIn('"[data-darkreader-inline-invert] {"', read("vendor/darkreader.js"))

    def test_content_marks_glyphs(self):
        # a glyph drawn with a background (a menu button's bars) left
        # without contrast gets ATTR_GLYPH naming its parts, painted in the
        # text colour, in the pass of the tiles; the marks go with the
        # page's marks
        js = strip_comments(read("content.js"))
        self.assertIn('const GLYPH = "%s";' % bg.ATTR_GLYPH, js)
        self.assertTrue(bg.ATTR_GLYPH.startswith("data-browserglass-"))
        layers = bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1)
        for part, pseudo in (("self", ""), ("before", "::before"), ("after", "::after")):
            self.assertIn('[%s~="%s"]:not(#browserglass-a):not(#browserglass-b)%s'
                          % (bg.ATTR_GLYPH, part, pseudo), layers)
        self.assertIn("::after { background-color: currentcolor !important; }", layers)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertIn("el.removeAttribute(GLYPH)", ink)
        self.assertLess(ink.index("markUninverted(near);"), ink.index("markGlyphs(near);"))
        mark = js[js.index("function markGlyphs("):js.index("function sample(")]
        for part in ('everywhere(":empty")',
                     "r.width > GLYPH_BOX || r.height > GLYPH_BOX",
                     "!el.closest(CONTROLS)",
                     "Math.min(w, h) > THIN || Math.max(w, h) > GLYPH_BOX",
                     "contrast(paint, bg) < INK_RATIO && contrast(text, bg) >= INK_RATIO"):
            self.assertIn(part, mark)

    def test_content_marks_rules(self):
        # a thin rule in a neutral colour Dark Reader left without contrast
        # (a separator) gets ATTR_RULE, painted a light neutral, after the
        # glyphs; only on a darkened page, the marks sticky till then
        js = strip_comments(read("content.js"))
        self.assertIn('const RULE = "%s";' % bg.ATTR_RULE, js)
        self.assertTrue(bg.ATTR_RULE.startswith("data-browserglass-"))
        layers = bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1)
        self.assertIn('[%s]:not(#browserglass-a):not(#browserglass-b) '
                      '{ background-color: rgba(255, 255, 255, %s) !important; }'
                      % (bg.ATTR_RULE, bg.RULE_OPACITY), layers)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertIn("el.removeAttribute(RULE)", ink)
        self.assertLess(ink.index("markGlyphs(near);"), ink.index("markRules(near);"))
        mark = js[js.index("function markRules("):js.index("function sample(")]
        for part in ("if (!darkened) {",
                     ':empty:not([" + RULE + "]):not([" + GLYPH + "])',
                     "Math.min(r.width, r.height) > RULE_THIN || Math.max(r.width, r.height) < RULE_LONG",
                     "chroma(paint) >= MONO_CHROMA",
                     "behind(el.parentElement || document.documentElement)",
                     "bg <= DARK_BG && contrast(y, bg) < RULE_READ"):
            self.assertIn(part, mark)

    def test_content_keeps_brand_buttons(self):
        # a small button in a saturated colour gets ATTR_BRAND naming the
        # part that paints its fill, and its fill and label colours inline,
        # read just before Dark Reader runs, which is told to leave that
        # inline style alone; the glass styles paint them back, under a
        # site style (no ids); the marks and the colours go with Dark Reader
        js = strip_comments(read("content.js"))
        self.assertIn('const BRAND = "%s";' % bg.ATTR_BRAND, js)
        self.assertIn('const BRAND_FILL = "%s";' % bg.BRAND_FILL, js)
        self.assertIn('const BRAND_INK = "%s";' % bg.BRAND_INK, js)
        self.assertIn('const DR_FIXES = {ignoreInlineStyle: ["[" + BRAND + "]"]};', js)
        darken = js[js.index("function darken()"):js.index("function markBrands(")]
        self.assertLess(darken.index("markBrands();"), darken.index("DarkReader.enable(theme, DR_FIXES);"))
        self.assertLess(darken.index("DarkReader.disable();"), darken.index("unmarkBrands();"))
        layers = bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1)
        self.assertIn('[%s~="before"]::before' % bg.ATTR_BRAND, layers)
        self.assertIn("{ background-color: var(%s) !important; }" % bg.BRAND_FILL, layers)
        inked = '[%s]:not([%s~="clear"])' % ((bg.ATTR_BRAND,) * 2)
        self.assertIn("%s * { color: var(%s) !important; }" % (inked, bg.BRAND_INK), layers)
        self.assertLess(layers.index(bg.ATTR_BRAND), layers.index(bg.ATTR_INK))
        # a control Dark Reader filled though it painted none is see-through
        self.assertIn('[%s~="clear"] { background-color: transparent !important; }' % bg.ATTR_BRAND, layers)
        # no ring nor border of the add-on's round any button or field
        self.assertNotIn("box-shadow: inset", layers)
        self.assertNotIn('~="lift"', layers)
        self.assertNotIn('~="edge"', layers)
        for gone in ("function markEdges(", "function markFields(", "LIFT", "EDGED", "FIELD_EDGE"):
            self.assertNotIn(gone, js)
        mark = js[js.index("function markBrands("):js.index("function unmarkBrands(")]
        for part in ("r.width > BRAND_W || r.height > BRAND_H",
                     "alpha(fill) >= SOLID ? fill : null",
                     "contrast(y, fg) < BRAND_READ",
                     "c >= BRAND_CHROMA || c >= BRAND_PASTEL && fg < y",
                     "y < BRAND_DARK && fg > y || null",
                     "controlState(el) !== state",
                     "text.length > BRAND_TEXT"):
            self.assertIn(part, mark)
        # the clears are looked at in the pass of the text, before the blocks
        ink = js[js.index("function markInk("):js.index("function markIcons(")]
        self.assertLess(ink.index("markClears(near);"), ink.index("markBlocks(near, texts);"))
        # a colour in another space (oklch()) is read in sRGB through a canvas
        channels = js[js.index("function channels("):js.index("function near(")]
        self.assertIn('document.createElement("canvas").getContext("2d")', channels)
        # the inline style of an ignored element is left as it is
        self.assertIn("shouldIgnoreInlineStyle(element, ignoreInlineSelectors)", read("vendor/darkreader.js"))

    def test_content_marks_blocks(self):
        # a block Dark Reader turned into an opaque near-black panel (a
        # white card) gets ATTR_BLOCK: the outermost a light veil, those
        # inside it see-through; one across the window or down a column is
        # a layer of the page (CANVAS); only on a darkened page, in the
        # pass of the text, before the ink; the marks go with Dark Reader
        js = strip_comments(read("content.js"))
        self.assertIn('const BLOCK = "%s";' % bg.ATTR_BLOCK, js)
        self.assertTrue(bg.ATTR_BLOCK.startswith("data-browserglass-"))
        layers = bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1)
        self.assertLess(bg.BLOCK_VEIL_OPACITY, bg.NAV_BAR_OPACITY)
        self.assertIn('[%s~="veil"]:not(#browserglass-a):not(#browserglass-b) '
                      '{ background-color: var(%s) !important; }'
                      % (bg.ATTR_BLOCK, bg.BLOCK_VAR), layers)
        # the veil is in the tone's surface: the dark one on a darkened
        # page, the light one on a page in its own light theme
        # (the light one never on a page declaring its dark version)
        for scheme, rgb in (("dark", "0, 0, 0"), ("light", "255, 255, 255")):
            where = ":not(%s)" % bg._DARK_PAGE_WHERE if scheme == "light" else ""
            self.assertIn('html:root[%s="%s"]%s { %s: rgba(%s, %s); }'
                          % (bg.ATTR_TONE, scheme, where, bg.BLOCK_VAR, rgb, bg.BLOCK_VEIL_OPACITY), layers)
        self.assertIn('[%s~="glass"]:not(#browserglass-a):not(#browserglass-b) '
                      '{ background-color: transparent !important; }' % bg.ATTR_BLOCK, layers)
        # its empty pseudo-elements in its colour, named, are cleared; a
        # block over a picture ("solid") has no rule: Dark Reader's fill
        self.assertIn('[%s~="before"]:not(#browserglass-a):not(#browserglass-b)::before, '
                      '[%s~="after"]:not(#browserglass-a):not(#browserglass-b)::after '
                      '{ background-color: transparent !important; }' % (bg.ATTR_BLOCK, bg.ATTR_BLOCK), layers)
        self.assertNotIn('"solid"', layers)
        self.assertIn('const VEILED = "veil";', js)
        self.assertIn('const SEE_THROUGH = "glass";', js)
        self.assertIn('const OPAQUE = "solid";', js)
        blocks = js[js.index("function markBlocks("):js.index("const FILL_NODES")]
        for part in ("if (!darkened)",
                     "alpha(color) < SOLID || floats(el) || !plain(el, color, BLOCK_CHROMA)",
                     "if (!column(el, color))",
                     "mark(el, CANVAS);",
                     "const outermost = j === blocks.length - 1 && !b.matches(FIELDS);",
                     "outermost ? (overs.get(b) ? OPAQUE : VEILED) : b.matches(FIELDS) ? VEILED : SEE_THROUGH",
                     "overs.set(b, overPicture(b, stop, media) || overBand(b));",
                     "[role, ...bands(b)].join(\" \")",
                     "!holds(block, m) && overlap(r, shownBox(m)) >= OVER_SHARE * r.width * r.height",
                     'const x = style.overflowX !== "visible", y = style.overflowY !== "visible";',
                     "near(style.backgroundColor, color)",
                     # over a saturated band: the first element painting
                     # behind it, opaque, saturated, under part of it
                     "const OVER_CHROMA = 0.4;",
                     "at.elementsFromPoint(r.left + r.width / 2, r.top + y * r.height)",
                     "stack.slice(i + 1).find(",
                     "chroma(style.backgroundColor) >= OVER_CHROMA"):
            self.assertIn(part, blocks)
        # the text of markInk, read as far into the page
        self.assertIn("for (const el of texts)", blocks)
        self.assertIn("const BLOCK_CHROMA = 0.12;", js)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertLess(ink.index("markBlocks(near, texts);"), ink.index("const held = [];"))
        self.assertIn("el.removeAttribute(BLOCK), el.removeAttribute(KEPT);", ink)
        self.assertIn("el.removeAttribute(BLOCK)", js[js.index("function darken()"):js.index("function frameSchemes()")])
        # column is a shape on plain()'s colour
        self.assertIn("&& plain(el, color) && !stuckSide(el);", js[js.index("function column("):js.index("function plain(")])
        # a sticky side column (or one in it) is the window's bar, never a
        # page layer, whichever pass meets it first
        stuck = js[js.index("function stuckSide("):js.index("function plain(")]
        self.assertIn('getComputedStyle(e).position === "sticky" && sideBar(e.getBoundingClientRect(), w, h)', stuck)
        self.assertIn("|| sideBar(r, w, h));", js[js.index("function markBars()"):js.index("let layerFrame")])

    def test_content_marks_cards(self):
        # a row of link cards a site paints itself, opaque in the tone's
        # plain colour, on a see-through page (its own dark or light
        # theme) gets the block veil; its boxes in the same colour are
        # see-through, a box holding a picture is left; a lone one or a
        # floating one stays; not on a darkened page (markBlocks); the
        # marks are judged again on a change of tone. The card is the link
        # or the box painted round it, out to the same box painted round
        # that (its faces see-through); a box of a list of links, a photo's
        # card, a product tile (a photo set in it, not side to side) and a
        # box outlined round a link stay
        js = strip_comments(read("content.js"))
        cards = js[js.index("function markCards("):js.index("function afloat(")]
        for part in ("const on = !darkened && glassPage && tone !== null;",
                     "if (!on || tone !== cardTone)",
                     'everywhere("a[href]")',
                     "const [el, faces] = cardOf(links[i]);",
                     "card = i < CARD_DEPTH ? up(card) : null;",
                     "faces.push(card), card = p;",
                     "face.setAttribute(BLOCK, SEE_THROUGH);",
                     "(code || Math.min(r.width, r.height) >= CARD_LOW) && Math.max(r.width, r.height) >= CARD_SIDE",
                     "&& !wide(el) && !large(el) && alpha(color) >= SOLID && plain(el, color, BLOCK_CHROMA, true) && !afloat(el)",
                     "&& cardLike(el, r, link ? CARD_LINKS : Infinity) && (code || !framed(el, link)) && !overBand(el);",
                     # a card in faces of one colour: the box round them
                     "const [box, size, parts] = cardFaces(el, color);",
                     "card = box, r = size, faces = [...faces, ...parts];",
                     "if (fits(box, size, color, link))",
                     "if (parts.length < 2 || covered < MERGE_SHARE * r.width * r.height)",
                     "box.children.length > CARD_FACES",
                     "return [box, {...u, width: u.right - u.left, height: u.bottom - u.top}, parts];",
                     # a code block alone
                     "code || rows.get(color) >= CARD_ROW || module(el.getBoundingClientRect())",
                     "if (links > most)",
                     "shown >= CARD_PICTURE * area",
                     "shown >= CARD_MAT * area && m.left > r.left + EDGE && m.right < r.right - EDGE",
                     "Math.abs(m.left - r.left - (r.right - m.right)) <= MAT_CENTRE * r.width",
                     # text not in a link leads to the panel under it
                     'if (!el.closest("a[href]"))',
                     "judge(panelOf(el, outer), null, []);",
                     "const across = MODULE_WIDE * document.documentElement.clientWidth;",
                     "p.hasAttribute(BAR) || p.hasAttribute(BLOCK) || p.hasAttribute(KEPT) || cards.has(p)",
                     "&& !wide(way[i]) && !large(way[i])",
                     "return el !== link && style.borderTopStyle !== \"none\" && parseFloat(style.borderTopWidth) > 0;",
                     "rows.get(color) >= CARD_ROW",
                     "card.setAttribute(BLOCK, VEILED);",
                     "el.querySelector(CARD_MEDIA)",
                     "el.setAttribute(BLOCK, SEE_THROUGH);"):
            self.assertIn(part, cards)
        self.assertIn("const CARD_ROW = 2;", js)
        self.assertIn("const CARD_LOW = 64;", js)
        self.assertIn("const CARD_FACES = 8;", js)
        self.assertIn("const MODULE_WIDE = 0.7;", js)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertLess(ink.index("markClears(near);"), ink.index("markCards(near, texts);"))
        self.assertLess(ink.index("markCards(near, texts);"), ink.index("markBlocks(near, texts);"))
        # the page's bands first: a card is on a layer, never one
        self.assertLess(ink.index("markBands(texts);"), ink.index("markCards(near, texts);"))
        self.assertIn("const module = (r) => r.width >= across && r.height < low;", cards)
        self.assertIn("cards = new Map();", ink)

    def test_content_keeps_own_surfaces(self):
        # a surface the generic style cleared though the text on it was
        # drawn for it gets ATTR_OWN, which the generic style skips (live
        # gating only), tried before the text is inked, not on a darkened
        # page; the text of open shadow trees is read, their marks found
        js = strip_comments(read("content.js"))
        self.assertIn('const KEPT = "%s";' % bg.ATTR_OWN, js)
        self.assertTrue(bg.ATTR_OWN.startswith("data-browserglass-"))
        self.assertEqual(bg._GATE_KEEP, ":where(:not([%s]))" % bg.ATTR_OWN)
        self.assertEqual(bg._Nest(bg.GATE_NORMAL_ROOT, True, True).amp, ":where(&,& *)" + bg._GATE_KEEP)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertIn("const lost = bare !== null && seen.every(low) && !kept(el, seen);", ink)
        # a colour of its own on the glass is shaded, its hue kept
        self.assertIn("if (lost && !(own && glass) && (op === 1 || !backed))", ink)
        keep = js[js.index("function kept("):js.index("function markInk()")]
        for part in ('if (darkened || fading(document.documentElement) || (tone === "light" && inBar(el)))',
                     "p.setAttribute(KEPT, \"\");", "el.removeAttribute(KEPT);",
                     "a instanceof CSSTransition && FADED.test(a.transitionProperty)", "a.cancel();"):
            self.assertIn(part, keep)
        # under a light tone, a bar's veil is the chrome's surface (nothing
        # kept in it, even kept before it was a bar) and a wide fill on the
        # light side is the glass's colour: neither is kept
        self.assertIn('if (!reads(fill) || (tone === "light" && toned(fill) && wide(p)))', keep)
        self.assertIn("if (inBar(el))\n      el.removeAttribute(KEPT);", keep)
        self.assertIn("unkeepChrome();", ink)
        # a dark row of text across a light floating layer goes see-through
        # whatever its height (MDN's navy title row in its mega menu)
        self.assertIn("(r.height >= SECTION_MIN || darkRow(el, style))", js)
        self.assertIn('return tone === "light" && isLight(style.backgroundColor) === false', js)
        shown = js[js.index("function shownText("):js.index("function contrast(")]
        self.assertIn("shadows.add(n.shadowRoot);", shown)
        self.assertIn("walkers.push(document.createTreeWalker(n.shadowRoot, show));", shown)
        self.assertIn("return el.assignedSlot || el.parentElement || (el.parentNode && el.parentNode.host) || null;", js)
        self.assertIn('for (const el of marked("[" + CANVAS + "], [" + FILLED + "], [" + BLOCK + "], [" + UNDER + "], [" + SEAM + "]"))',
                      js[js.index("function darken()"):js.index("function frameSchemes()")])
        # judged again once the tone changes (a page measured dark while it
        # loads) or the page is darkened
        self.assertIn('for (const el of marked("[" + KEPT + "]"))\n    el.removeAttribute(KEPT);', keep)
        self.assertIn("root.setAttribute(TONE, tone);\n    unkeep();",
                      js[js.index("function paint()"):js.index("function paint()") + 2000])
        self.assertIn("darkened = true;\n    darkMarks = ownDark();\n    unkeep();",
                      js[js.index("function darken()"):js.index("function frameSchemes()")])
        # a page layer off the tone's side and shorter than the page is a
        # section of the site's own (a dark section that made the layer of
        # a page measured dark while it loaded, MeteoSuisse): kept when its
        # text reads on it, its layer mark and colour taken off
        own = js[js.index("function ownLayer("):js.index("function unkeep(")]
        for part in ('el.getAttribute(CANVAS) === ""', "!el.hasAttribute(FILLED)", "!toned(color)",
                     "el.getBoundingClientRect().height < document.documentElement.scrollHeight - SECTION_EDGE"):
            self.assertIn(part, own)
        self.assertIn("if (ownLayer(p)) {\n      if (!reads(layerColors.get(p)))\n        return false;\n"
                      "      p.removeAttribute(CANVAS);\n      pageColors.delete(layerColors.get(p));\n"
                      "      p.setAttribute(KEPT, \"\");", keep)
        self.assertLess(keep.index("if (ownLayer(p))"), keep.index("if (MARKS.some((m) => p.hasAttribute(m)))"))

    def test_content_marks_tiles(self):
        # a picture made for a white page on a background now dark gets
        # ATTR_TILE (a white tile; dark monochrome ink "invert": light ink,
        # no tile), in the same throttled pass as the text, and loses it
        # with the page's marks
        js = strip_comments(read("content.js"))
        self.assertIn('const TILE = "%s";' % bg.ATTR_TILE, js)
        self.assertTrue(bg.ATTR_TILE.startswith("data-browserglass-"))
        rule = bg._TILE_RULE.format(dark="0, 0, 0")
        for part in ('[%s]:not([%s="invert"]):not([%s="plain"]):not([%s="back"]):not(#browserglass-a):not(#browserglass-b) {'
                     % (bg.ATTR_TILE, bg.ATTR_TILE, bg.ATTR_TILE, bg.ATTR_TILE),
                     # a logo whose white part is lost on the light veil: a dark backing
                     '[%s="back"]:not(#browserglass-a):not(#browserglass-b) {' % bg.ATTR_TILE,
                     "background-color: rgb(0, 0, 0) !important;",
                     "filter: none !important; mix-blend-mode: normal !important;",
                     "background-color: rgb(255, 255, 255) !important;",
                     # square inside (no seam at the picture's corners),
                     # rounded outside by the clip-path
                     "border-radius: 0 !important;",
                     "box-shadow: 0 0 0 %dpx rgb(255, 255, 255) !important;" % bg.TILE_PAD,
                     # brought in to a fitted picture as shown (the
                     # sides the add-on sets), else around its box
                     "clip-path: inset(%s round %dpx) !important;"
                     % (" ".join("calc(var(%s, 0px) - %dpx)" % (side, bg.TILE_PAD) for side in bg.TILE_SIDES),
                        bg.TILE_RADIUS)):
            self.assertIn(part, rule)
        self.assertIn(bg._TILE_RULE, bg._CONTENT_LAYERS)
        # the sides around a fitted picture, set by content.js by the
        # same names, in the same order
        self.assertIn('const TILE_SIDES = ["top", "right", "bottom", "left"].map((side) => '
                      '"--browserglass-tile-" + side);', js)
        self.assertEqual(bg.TILE_SIDES, tuple("--browserglass-tile-" + side
                                               for side in ("top", "right", "bottom", "left")))
        # no longer inverted whole; monochrome ink inverted to light ink,
        # without a background of its own (the filter would light it up)
        self.assertNotIn("invert(1)", bg._CONTENT_LAYERS)
        self.assertIn('[%s="invert"]:not(#browserglass-a):not(#browserglass-b) '
                      '{ filter: invert(%s) hue-rotate(180deg) !important; mix-blend-mode: normal !important;'
                      ' background-color: transparent !important; }'
                      % (bg.ATTR_TILE, bg.TILE_INVERT),
                      bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1))
        self.assertGreater(bg.TILE_INVERT, 0.5)
        # on a bar veiled light, white ink follows the labels' dark ink
        # (inverted), and a picture the site whitened loses its filter
        self.assertIn('[%s="plain"]:not(#browserglass-a):not(#browserglass-b) { filter: none !important; }'
                      % bg.ATTR_TILE, bg._CONTENT_LAYERS.format(dark="0, 0, 0", light="255, 255, 255", nav=1))
        light = js[js.index("function inkedBar("):js.index("function round(")]
        # a header in the flow the glass cleared, once its labels are inked
        self.assertIn('const HEADS = "header, [role=banner]";', js)
        self.assertIn('const DARK_INK = "[" + INK + "=\\"dark\\"]";', js)
        for part in ("if (p.hasAttribute(BAR) || p.matches(HEADS) && p.querySelector(DARK_INK))",
                     "return !!p.querySelector(DARK_INK);",
                     "if (bg <= DARK_BG && filter === \"none\")",
                     'if (el.getAttribute(TILE) === "plain")\n    return "plain";',
                     "return s && s.clear >= TILE_CLEAR ? {inks: s.inks, tints: s.tints} : null;",
                     '|| inColor(el))',
                     "const shown = shownInk(raw.inks, filter);",
                     # a colour logo (PyPI's blue and yellow, a white knob on a blue
                     # toggle: the whole drawing read) is not inverted
                     'return oneHue(raw.tints) ? "invert" : backed(el, raw, lost);',
                     "return c.length <= 2 * MONO_EDGE || c[c.length - 1 - MONO_EDGE] - c[MONO_EDGE] < MONO_CHROMA;",
                     "const FILTER_STEPS = /(invert|brightness)\\(([\\d.]+)(%?)\\)/g;"):
            self.assertIn(part, light)
        # its light fill attribute, darkened by Dark Reader, one tone
        refill = js[js.index("function refilled("):js.index("function rawInk(")]
        self.assertIn('const DR_FILL = "data-darkreader-inline-fill";', js)
        for part in ("!shape.hasAttribute(DR_FILL)",
                     "if (bg === null || bg > DARK_BG)",
                     "y < bg || contrast(y, bg) < INK_RATIO",
                     "|| contrast(shown, bg) >= INK_RATIO)",
                     "return own.length > 0 && oneTone(own.sort((a, b) => a - b));"):
            self.assertIn(part, refill)
        ink = js[js.index("function markInk()"):js.index("function markTiles(")]
        self.assertIn("removeAttribute(TILE)", ink)
        self.assertIn("markTiles(near);", ink)
        mark = js[js.index("function markTiles("):js.index("function sample(")]
        for part in ("i < pictures.length && i < TILE_ELEMENTS",
                     # nor a picture shown through a mask (a logo wall's
                     # logos painted in the text colour)
                     "if (r.width >= TILE_WIDE * window.innerWidth || masked && PICTURES.has(el.localName))",
                     "if (inkedBar(el))\n    return lightInk(el, true);",
                     # a picture straight on the glass read the same way,
                     # whatever its labels (the tone the glass ends up with)
                     "const light = r.height <= LOGO_SIDE && onGlass(el.parentElement || document.documentElement) ? lightInk(el) : null;",
                     "if (light === \"back\" || light !== null && grey(el))\n    return light;",
                     # a light logo Dark Reader darkened on its dark page
                     'if (darkened && refilled(el))\n    return "invert";',
                     "if (masked)\n    return null;",
                     # a small icon painted as a background picture or
                     # through a mask in an inked bar
                     '[...everywhere("img, svg, canvas"), ...barIcons()]',
                     # an icon is never tiled nor blended
                     "const icon = r.width <= ICON_SIDE && r.height <= ICON_SIDE;",
                     '!icon && (el.getAttribute(TILE) === "blend" || DARKENING.has(getComputedStyle(el).mixBlendMode))',
                     "const parent = el.parentElement || document.documentElement;",
                     # off Dark Reader's pages, only on the glass
                     "bg === null || bg > DARK_BG || !blended && !darkened && !onGlass(parent)",
                     "if (dark.length < TILE_INK * s.inks.length)",
                     # dark ink of one tone inverted, else tiled but an
                     # icon's or one of another origin
                     "if (oneTone(dark) && oneTone(rest) && rest.length <= dark.length)",
                     "contrast(ys[ys.length - 1 - MONO_EDGE], ys[MONO_EDGE]) < MONO_FLAT",
                     'return icon || s.far || laidOver(el, r) ? null : "ink";',
                     # laid over a larger picture: that picture is behind it
                     'const BACKDROPS = "img, video, canvas";',
                     "other !== el && o.width * o.height > r.width * r.height",
                     # read on a dark page, a site's own filter left alone,
                     # on the picture or an element above it (Wikipedia's
                     # inverted night logo)
                     'if (tone !== "dark" || filtered(el))',
                     'if (!el.hasAttribute(TILE) && getComputedStyle(el).filter !== "none")',
                     "for (let i = 0; p && i < FILTER_DEPTH; i++, p = p.parentElement)",
                     "if (p.hasAttribute(BAR))\n      return true;"):
            self.assertIn(part, mark)
        # never taken off and set again in the same pass
        self.assertIn("else if (el.getAttribute(TILE) !== kind)", mark)
        pixels = js[js.index("function sample("):js.index("function ink()")]
        # a picture loaded after the last pass (a lazy one, no width till
        # then) is looked at again: one load listener for the document
        self.assertIn('if (off === false && e.target.localName === "img")\n    ink();', pixels)
        self.assertIn('document.addEventListener("load", loaded, {capture: true, passive: true});', js)
        for part in ("if (samples.size >= SAMPLES_MAX)",
                     # drawn SAMPLE_SIDE px long, a small icon larger
                     "const k = SAMPLE_SIDE / Math.max(r.width, r.height, 1);",
                     # another origin: an anonymous copy, read if allowed
                     'copy.crossOrigin = "anonymous";',
                     "samples.set(src, s && {...s, far: true});"):
            self.assertIn(part, pixels)
        # an inline icon in its text colour is read as text is
        icons = js[js.index("function markIcons("):js.index("function markTiles(")]
        for part in ("all.every((paint) => paint === color)",
                     "contrast(fg, bg) < INK_RATIO",
                     'svg.setAttribute(INK, bg > 0.179 ? "dark" : "light");'):
            self.assertIn(part, icons)
        behind = js[js.index("function behind(el, follow = true, worst = false, ink = false)"):js.index("function markInk()")]
        # an image behind the text: no guess
        self.assertIn("if (picture(style))\n      return underTints(null, tints);", behind)
        self.assertIn("const glass = glassOver(null);", behind)
        # a translucent root over the glass, mixed in sRGB as the browser does
        self.assertIn("linear(a * encoded(own) + (1 - a) * encoded(g))", behind)
        # under a see-through fixed or sticky layer, what is painted there
        self.assertIn("beneath(p, el) : null;", behind)
        self.assertIn("return underTints(behind(under, false, worst, ink), tints);", behind)
        # a see-through backing (a faint box, a card at 0.6) over what is under it
        self.assertIn("tints.push([luminance(style.backgroundColor), a]);", behind)
        self.assertIn("tints.reduceRight((under, [t, a]) => mixed(t, a, under), y)", behind)
        # a bar's dark veil over white, the worst under it, for its labels
        self.assertIn("ink && p.hasAttribute(BAR) ? veiled(style.backgroundColor, worst)", behind)
        veil = js[js.index("function veiled("):js.index("function beneath(")]
        self.assertIn("return mixed(y, a, worst ? 1 : glass === null ? y : glass);", veil)
        # a light veil over black, the worst under it
        self.assertIn("return mixed(y, a, 0);", veil)
        # the glass over the worst wallpaper (the tint's opacity)
        self.assertIn('const TINT = "%s";' % bg.TINT_VAR, js)
        self.assertIn("getPropertyValue(TINT)", js)
        self.assertIn("for (let p = el; p; p = up(p))\n    if (p.hasAttribute(BAR))", veil)
        # a face of its own (a ::before, or a covering absolute child, as
        # buttons often are) comes before the element's own background
        self.assertLess(behind.index("face(p)"), behind.index("picture(style)"))
        # a thin gradient that does not repeat across (an underline) is no
        # picture; anything else in a background image is
        pic = js[js.index("const THIN = "):js.index("function paints(")]
        self.assertIn("const THIN = 4;", pic)
        for part in ('if (style.backgroundImage === "none")\n    return false;',
                     "if (!GRADIENT.test(image))\n      return !icon(w, h, rx, ry, box);",
                     # an icon drawn once, small, in a share of its box:
                     # no picture (YouTube's chevron in a settings row)
                     'rx === "no-repeat" && ry === "no-repeat" && small(w) && small(h)',
                     "parseFloat(w) * parseFloat(h) < ICON_SHARE * box",
                     'v.endsWith("px") && parseFloat(v) <= THIN',
                     'thin(h) && ry === "no-repeat" || thin(w) && rx === "no-repeat"',
                     'else if (c === "," && depth === 0)'):
            self.assertIn(part, pic)
        self.assertIn("if (picture(style))\n    return null;",
                      js[js.index("function paints("):js.index("function covers(")])
        faces = js[js.index("const FACE = "):js.index("function behind(el, follow = true, worst = false, ink = false)")]
        for part in ('for (const pseudo of ["::before", "::after"])',
                     '(position === "absolute" || position === "fixed") && covers(r, kid)',
                     "p.childElementCount <= FACE_KIDS", "faces.set(p, value);",
                     "if (MEDIA.has(el.localName))\n    return null;",
                     # a layer at opacity 0 (a hover state) is no face
                     'parseFloat(s.opacity) < CLEAR',
                     "if (parseFloat(style.opacity) < CLEAR || style.visibility !== \"visible\")\n    return undefined;"):
            self.assertIn(part, faces)
        # looked for again on every pass
        self.assertIn("faces = new Map();", js[js.index("function markInk()"):js.index("function markTiles(")])
        throttle = js[js.index("function ink()"):]
        throttle = throttle[:throttle.index("\n}")]
        self.assertIn("requestAnimationFrame(", throttle)
        self.assertIn("now - inkAt < INK_MS", throttle)
        self.assertNotIn("setTimeout", throttle)

    def test_theme_writer_static(self):
        # theme.js: synchronous, guarded, loadable twice; the record goes
        # in before the value; a restore only takes back our own value;
        # the generic rule never touches a cookie
        raw = read("theme.js")
        js = strip_comments(raw)
        for word in ("setTimeout", "setInterval", "sendMessage", "browser.", "MutationObserver",
                     ".observe(", "fetch("):
            self.assertNotIn(word, js)
        for line in js.splitlines():
            self.assertFalse(re.match(r"(const|let|class)\b", line), line)
        self.assertIn('var THEME_RECORD = "browserGlass.theme";', js)
        self.assertIn('var THEME_MARK = "data-browserglass-theme";', js)
        self.assertTrue("data-browserglass-theme".startswith("data-browserglass-"))  # OWN: unwatched
        run = js[js.index("function themeRun("):js.index("function themeFailed(")]
        self.assertLess(run.index("themeSaveRecord(rec)"), run.index("themeWrite(themeTarget(id, entry), value)"))
        self.assertIn('window.matchMedia("(prefers-color-scheme: dark)").matches', js)
        ours = js[js.index("function themeOurs("):js.index("function themeTarget(")]
        self.assertIn("cur === entry.wrote", ours)
        restore = js[js.index("function themeRestoreAll("):js.index("function themeMark(")]
        self.assertIn("if (themeOurs(entry, cur))", restore)
        self.assertIn("rec.declined.push(id)", restore)
        generic = js[js.index("var gen = themes && themes.generic;"):js.index("function themeOurs(")]
        self.assertNotIn("cookie", generic)
        self.assertIn('store: "local"', generic)
        self.assertNotIn("document.cookie", generic)
        # a reload: early only, once per origin and session, never with a hash
        self.assertIn("if (reload && early && !location.hash)", run)
        self.assertIn("location.replace(location.href)", run)
        self.assertEqual(js.count("location.replace("), 1)
        self.assertTrue(js.rstrip().endswith('if (typeof BG_THEME !== "undefined")\n  themeRun(BG_THEME, true);'))

    def test_native_marks_match_the_dark_markers(self):
        # content.js's marks are the class and attribute markers the glass
        # styles read as a page with a dark version (_DARK_PAGE_MARKERS),
        # minus the color-scheme meta and pdf.js
        js = read("content.js")
        classes = json.loads(re.search(r"const NATIVE_CLASSES = (\[[^\]]*\]);", js).group(1))
        attrs = re.search(r"const NATIVE_ATTRS = (\[.*?\]\]);", js, re.S).group(1)
        attrs = json.loads(re.sub(r"\s+", " ", attrs))
        want_classes, want_attrs = [], []
        for m in bg._DARK_PAGE_MARKERS:
            if m.startswith(":"):
                continue
            c = re.fullmatch(r"\.([a-z-]+)", m)
            a = re.fullmatch(r'\[([a-z-]+)(?:~?="([a-z]+)" i)?\]', m)
            if c:
                want_classes.append(c.group(1))
            elif a:
                want_attrs.append([a.group(1), a.group(2) or ""])
            else:
                self.fail("unknown marker " + m)
        self.assertEqual(sorted(classes), sorted(want_classes))
        self.assertEqual(sorted(map(tuple, attrs)), sorted(map(tuple, want_attrs)))
        # a dark theme tried and taken back goes with the transitions held:
        # the colours the brand buttons are read in are the page's own
        native = strip_comments(js)
        native = native[native.index("function nativeDark("):native.index("function darken(")]
        self.assertIn("steady(() => {\n    nativeRestore();\n    measure();\n  });\n  return false;", native)

    def test_frame_keeps_embedded_pages_off(self):
        # an embedded page keeps its own look: <html> of every frame but the
        # top one carries the OFF mark, put back if the page takes it off or
        # replaces <html>
        js = strip_comments(read("frame.js"))
        self.assertIn("if (window !== window.top)", js)
        self.assertIn('const OFF = "%s";' % bg.ATTR_OFF, js)
        self.assertIn("root.setAttribute(OFF, \"\")", js)
        self.assertIn("attributeFilter: [OFF]", js)
        self.assertIn("observe(document, {childList: true})", js)
        for word in ("sendMessage", "storage", "setTimeout", "setInterval"):
            self.assertNotIn(word, js)

    def test_content_darkens_light_pages(self):
        # darkPages: the glass styles hand the colours over on the root
        # (_CONTENT_DARKEN), the add-on darkens a light page with them,
        # stickily, and marks its large background elements (ATTR_CANVAS).
        js = strip_comments(read("content.js"))
        self.assertIn('const CANVAS = "%s";' % bg.ATTR_CANVAS, js)
        self.assertTrue(bg.ATTR_CANVAS.startswith("data-browserglass-"))
        for var in ("--browserglass-darken-bg", "--browserglass-darken-fg"):
            self.assertIn('"%s"' % var, js)
            self.assertIn(var + ":", bg._CONTENT_DARKEN)
        self.assertIn("[" + bg.ATTR_CANVAS + "]", bg._CONTENT_LAYERS)
        theme = js[js.index("function darkTheme()"):js.index("function darken()")]
        # never before the list is known, nor on an excluded page, nor
        # unless the helper says so: the variables alone (which a page can
        # set itself) never darken
        self.assertIn("off !== false", theme)
        self.assertIn("|| !helperDark ||", theme)
        self.assertIn("let helperDark = false;", js)
        apply_ = js[js.index("function apply("):js.index("function load()")]
        self.assertIn("helperDark = dark === true;", apply_)
        self.assertLess(apply_.index("helperDark ="), apply_.index("darken()"))
        load = js[js.index("function load()"):js.index("let watched")]
        self.assertIn('browser.storage.local.get(["excluded", "darken", "themes"])', load)
        self.assertIn("apply(s.excluded, s.darken, s.themes)", load)
        self.assertIn("apply(msg.domains, msg.darken, msg.themes)", js)
        # the site's own stored theme: run again once the list is known
        # (a restore, a late write), before the marks and Dark Reader
        self.assertIn("themeRun(themeCfg, false);", apply_)
        self.assertLess(apply_.index("themeRun(themeCfg, false);"), apply_.index("darken()"))
        self.assertIn('typeof DarkReader === "undefined"', theme)
        # their saturation capped (Dark Reader gives grey text the text
        # colour's: #f7f9ff turned Hacker News' grey lines bright blue)
        self.assertIn("darkSchemeBackgroundColor: muted(bg), darkSchemeTextColor: muted(fg)", theme)
        mute = js[js.index("const POLE_SAT"):js.index("function darken()")]
        self.assertIn("const POLE_SAT = 0.1;", mute)
        self.assertIn("if (!m)\n    return color;", mute)
        self.assertIn("const k = POLE_SAT / s;", mute)
        self.assertIn("(l + (v - l) * k)", mute)
        # a page can set the colours itself: never under a light theme
        self.assertIn('!window.matchMedia("(prefers-color-scheme: dark)").matches', theme)
        darken = js[js.index("function darken()"):js.index("const GRID")]
        self.assertIn("darkened && (!theme || own && own !== darkMarks)", darken)
        # a kept own dark theme taken back with the transitions held, before
        # the brand buttons are read
        self.assertIn("matches)) {\n    steady(() => {\n      nativeRestore();\n      measure();\n    });\n  }", darken)
        # off when the page turns its own dark theme on late (DSFR's
        # data-fr-theme), back at once if it still shows light
        self.assertIn("const own = darkened && theme ? ownDark() : \"\";", darken)
        self.assertIn("steady(measure);\n  }\n  if (!darkened && theme", darken)
        self.assertIn("/^data-(?!darkreader-|browserglass-)([\\w-]+-)?(theme|scheme)$/", js)
        # frames keep their colour scheme while darkened (Dark Reader's
        # iframe rule gave a light frame from another site a backdrop)
        self.assertLess(darken.index("DarkReader.disable();"), darken.index("frameSchemes();"))
        self.assertLess(darken.index("DarkReader.enable(theme, DR_FIXES);"), darken.rindex("frameSchemes();"))
        schemes = js[js.index("function frameSchemes()"):js.index("function alpha(")]
        self.assertIn('const frames = document.getElementsByTagName("iframe");', js)
        self.assertIn('el.style.setProperty("color-scheme", value || "normal", "important");', schemes)
        self.assertIn('value ? el.style.setProperty("color-scheme", value, priority) : el.style.removeProperty("color-scheme");', schemes)
        self.assertIn("schemed = new Map();", schemes)
        layers_ = js[js.index("function layers()"):js.index("const layerSizes")]
        self.assertLess(layers_.index("frameSchemes();"), layers_.index("markCanvas();"))
        # the darkening stopped by the helper takes the page's own dark
        # theme marks back too
        self.assertIn("native && (off !== false || !helperDark ||", darken)
        self.assertIn('tone === "light"', darken)
        self.assertIn('sampled >= ENOUGH_TEXT || document.readyState === "complete"', darken)
        # an early write that left the page light is taken back first,
        # then the marks, then Dark Reader (still once)
        self.assertIn("themeState.early && tone === \"light\"", darken)
        self.assertLess(darken.index("themeFailed()"), darken.index("nativeTried"))
        # once there, and once in restyle() (a restart, see below)
        self.assertEqual(js.count("DarkReader.enable("), 2)
        # the add-on's fetch, which the page can read through Dark Reader's
        # copies: no credentials or referrer, stylesheets only
        self.assertIn("DarkReader.setFetchMethod(fetchStylesheet)", darken)
        self.assertNotIn("setFetchMethod(fetch)", js)
        self.assertEqual(js.count("fetch("), 1)
        fetcher = js[js.index("function fetchStylesheet("):]
        fetcher = fetcher[:fetcher.index("\n}")]
        for opt in ('credentials: "omit"', 'cache: "force-cache"',
                    'referrerPolicy: "no-referrer"',
                    "!r.ok", r"/^text\/css\b/i", 'r.headers.get("Content-Type")', "throw "):
            self.assertIn(opt, fetcher)
        self.assertIn("DarkReader.disable()", darken)
        # a shadow tree's sheet adopted once Dark Reader met the tree (its
        # watcher cannot call the page's array methods from here): Dark
        # Reader restarted on a pass of settle(), a capped number of times,
        # each sheet once, the trees read by index, never by their methods
        restyle = js[js.index("const DR_OVERRIDE"):js.index("function markBrands(")]
        self.assertIn('const DR_OVERRIDE = "#__darkreader__adoptedOverride";', restyle)
        self.assertIn("darkened && restarts < RESTARTS", restyle)
        self.assertIn("restyled.add(sheet)", restyle)
        # never while a sheet Dark Reader asked for is still being fetched:
        # the stopped run would put its style back once the fetch ends
        self.assertIn("if (fetching) {\n    restyleWaits = true;\n    return;\n  }", restyle)
        self.assertIn("if (!fetching && restyleWaits) {", fetcher)
        self.assertIn("adoptedStyleSheets.wrappedJSObject", restyle)
        for method in (".filter(", ".find(", ".forEach(", ".map("):
            self.assertNotIn(method, restyle[restyle.index("function undarkened("):])
        self.assertLess(restyle.index("DarkReader.disable();"), restyle.index("DarkReader.enable(theme, DR_FIXES);"))
        self.assertLess(restyle.index("DarkReader.enable(theme, DR_FIXES);"), restyle.rindex("settle();"))
        self.assertIn("settle();", darken)
        tick = js[js.index("function settleTick("):]
        tick = tick[:tick.index("\n}")]
        self.assertIn("restyle();", tick)
        self.assertIn("removeAttribute(CANVAS)", darken)
        # a darkened page shows light text: tone "dark", not measured
        measure = js[js.index("function measure()"):js.index("function update()")]
        self.assertLess(measure.index("if (darkened)"), measure.index("readyState"))
        mark = js[js.index("function markCanvas()"):js.index("function markBars()")]
        # the lowest opaque large layer once the root and body are clear;
        # every large non-fixed one on a darkened page
        self.assertIn("off !== false", mark)
        self.assertIn("(clear(root) || tinted(root)) && clear(document.body)", mark)
        # the root under the tone tint (a dark app under a light theme)
        # counts as see-through: translucent, the tone not the theme's
        tinted = js[js.index("function tinted("):js.index("function markCanvas()")]
        self.assertIn("root.getAttribute(TONE)", tinted)
        self.assertIn('(measured === "dark") !== window.matchMedia("(prefers-color-scheme: dark)").matches', tinted)
        self.assertIn("alpha(getComputedStyle(root).backgroundColor) < SOLID", tinted)
        self.assertIn("stack.length - 1", mark)
        self.assertIn("if (!darkened)", mark)
        self.assertIn('position !== "fixed"', mark)
        self.assertIn("stackAt(", mark)
        self.assertIn("new Set([root, document.body])", mark)
        # a fixed layer over the page's content (a cookie banner) is not the
        # page's background, a fixed full-window container is
        self.assertIn("if (below.some((b) => !holds(b, el)) && pinned(el))\n          break;", mark)
        self.assertIn('for (let e = el; e && e !== root; e = up(e))\n      if (getComputedStyle(e).position === "fixed")', mark)
        self.assertLess(mark.index("&& pinned(el))\n          break;"), mark.index("layer(row, color);\n          found("))
        # decided before the tone attribute is painted (no flash of tint)
        upd = js[js.index("function update()"):js.index("function paint()")]
        self.assertLess(upd.index("darken()"), upd.index("paint()"))
        apply_ = js[js.index("function apply("):js.index("function load()")]
        self.assertLess(apply_.index("darken()"), apply_.index("paint()"))

    def test_content_sets_live_with_off(self):
        # Fixes A and E: nothing is set before the list is known, then OFF
        # and LIVE together in paint().
        js = strip_comments(read("content.js"))
        self.assertIn("let off = null;", js)
        paint = js[js.index("function paint()"):js.index("function apply(")]
        self.assertIn("off === null", paint)
        self.assertLess(paint.index("off === null"), paint.index("setAttribute(LIVE"))
        self.assertEqual(js.count("setAttribute(LIVE"), 1)

    def test_content_waits_for_a_stored_list(self):
        # Fix E on a fresh install: a missing stored list is not an empty
        # one, or LIVE would come on for a site excluded at sync.
        js = strip_comments(read("content.js"))
        load = js[js.index("function load()"):js.index("let watched")]
        self.assertIn("Array.isArray(s.excluded)", load)
        self.assertNotIn("s.excluded ||", js)
        # the host is matched lowercased, without the dot of a full FQDN
        self.assertIn('hostExcluded(location.hostname.toLowerCase()'
                      '.replace(/\\.$/, ""), domains)', js)
        bjs = strip_comments(read("background.js"))
        self.assertIn("stored = Array.isArray(s.excluded);", bjs)
        self.assertIn("const first = !stored;", bjs)
        self.assertIn("if (!same || first)", bjs)

    def test_background_theme_keys(self):
        # the add-on keeps the helper's key rules: "/" in a localStorage
        # key only, never in a cookie name
        js = read("background.js")
        self.assertIn("const THEME_KEY = /^%s$/;" % bg._THEME_KEY.pattern, js)
        self.assertIn("const THEME_LOCAL_KEY = /^%s$/;" % bg._THEME_LOCAL_KEY.pattern, js)
        self.assertIn('!(r.store === "local" ? THEME_LOCAL_KEY : THEME_KEY).test(r.key)', js)
        self.assertIn("/", bg._THEME_LOCAL_KEY.pattern)
        self.assertNotIn("/", bg._THEME_KEY.pattern)

    def test_background_protocol(self):
        js = strip_comments(read("background.js"))
        self.assertIn('const HOST_APP = "%s";' % bg.NATIVE_HOST_NAME, js)
        self.assertIn('const OFF = "%s";' % bg.ATTR_OFF, js)
        self.assertIn("const PROTO = 1;", js)
        self.assertIn("const RETRY_MAX_MS = 60000;", js)
        # One busy tab never holds "applied" past the helper's wait: each
        # tab's sendMessage races TAB_WAIT_MS.
        wait = int(re.search(r"const TAB_WAIT_MS = (\d+);", js).group(1))
        self.assertLess(wait / 1000.0, bg.LIVE_ACK_TIMEOUT / 2)
        self.assertRegex(js, r"Promise\.race\(\[\s*browser\.tabs\.sendMessage\(tab\.id, "
                             r"\{type: \"excluded\", domains, darken: dark, themes: theme\}\)\.catch\(\(\) => \{\}\),\s*"
                             r"new Promise\(\(resolve\) => setTimeout\(resolve, TAB_WAIT_MS\)\)")
        # Fix B: lists are applied one at a time.
        self.assertIn("queue = queue.then(job)", js)
        # A private tab is never reported, and only the newest report is.
        self.assertIn("|| tab.incognito)", js)
        self.assertIn("const gen = ++reportGen;\n  const tabs = await browser.tabs.query", js)
        self.assertEqual(js.count("++reportGen"), 1)
        # "applied" goes back only on the port the list came on.
        self.assertIn("applyList(cleanList(msg.domains), msg.darken === true, "
                      "cleanThemes(msg.themes), msg.seq, self)", js)
        self.assertIn("&& from === port)", js)
        # darken (the darkPages setting) is stored with the list and read
        # back at startup: only true counts.
        self.assertIn("browser.storage.local.set({excluded: domains, darken: dark, themes: theme})", js)
        self.assertIn('browser.storage.local.get(["excluded", "darken", "themes"])', js)
        self.assertIn("themes = cleanThemes(s.themes);", js)
        self.assertIn("darken = s.darken === true;", js)
        # a failed write is retried by the next list, even an identical one:
        # storage must not keep an old darken the helper switched off
        self.assertIn("let saved = false;", js)
        self.assertIn("if (changed || !saved)", js)
        self.assertIn("saved = await browser.storage.local.set({excluded: domains, darken: dark, themes: theme})"
                      "\n      .then(() => true, () => false);", js)
        # the theme payload: data for theme.js before the page's scripts,
        # registered again when the list, darken or the recipes change
        reg = js[js.index("async function replaceThemeRegistration()"):js.index("async function replaceRegistration(")]
        self.assertIn('matches: ["http://*/*", "https://*/*"]', reg)
        self.assertIn('runAt: "document_start"', reg)
        self.assertIn("JSON.stringify({dark: darken, excluded, themes})", reg)
        self.assertIn('"var BG_THEME = " + cfg + ";typeof themeRun === \'function\' && themeRun(BG_THEME, true);"', reg)
        self.assertIn("const key = JSON.stringify([domains, dark, theme.rev]);", js)
        self.assertIn("if (key !== themeKey || !themeRegistered)", js)
        self.assertIn("stored = stored || saved;", js)
        self.assertIn("saved = stored;", js)
        self.assertNotIn("() => stored)", js)
        self.assertNotIn("all_frames", js)


class XpiTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def copy_ext(self, name="ext"):
        dst = os.path.join(self.tmp, name)
        shutil.copytree(str(EXT), dst)
        return dst

    def test_deterministic(self):
        one = bg.companion_xpi(str(EXT))
        self.assertEqual(one, bg.companion_xpi(str(EXT)))
        # Another folder with other dates and modes gives the same bytes.
        other = self.copy_ext()
        for top, _dirs, files in os.walk(other):
            for name in files:
                path = os.path.join(top, name)
                os.utime(path, (1234567890, 1234567890))
                os.chmod(path, 0o600)
        self.assertEqual(bg.companion_xpi(other), one)

    def test_layout(self):
        data = bg.companion_xpi(str(EXT))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIsNone(zf.testzip())
            names = zf.namelist()
            self.assertEqual(names, ["background.js", "content.js", "frame.js", "manifest.json",
                                     "theme.js", "vendor/darkreader-LICENSE.txt", "vendor/darkreader.js"])
            self.assertIn("manifest.json", names)  # at the root, no folder prefix
            for info in zf.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.external_attr >> 16, 0o100644)
                self.assertEqual(zf.read(info), (EXT / info.filename).read_bytes())

    def test_sorted_subfolders_and_skipped_entries(self):
        ext = self.copy_ext()
        os.makedirs(os.path.join(ext, "icons"))
        os.makedirs(os.path.join(ext, ".git"))
        for rel in ("icons/b.svg", "icons/a.svg", ".hidden", ".git/config", "a.txt"):
            with open(os.path.join(ext, rel), "w") as f:
                f.write(rel)
        os.symlink("/etc/passwd", os.path.join(ext, "link.txt"))
        os.symlink(os.path.join(ext, "icons"), os.path.join(ext, "linked-dir"))
        with zipfile.ZipFile(io.BytesIO(bg.companion_xpi(ext))) as zf:
            self.assertEqual(zf.namelist(), ["a.txt", "background.js", "content.js", "frame.js",
                                             "icons/a.svg", "icons/b.svg", "manifest.json", "theme.js",
                                             "vendor/darkreader-LICENSE.txt", "vendor/darkreader.js"])

    def test_missing_manifest(self):
        ext = self.copy_ext()
        os.remove(os.path.join(ext, "manifest.json"))
        with self.assertRaises(ValueError):
            bg.companion_xpi(ext)
        os.makedirs(os.path.join(ext, "sub"))
        shutil.copy(str(EXT / "manifest.json"), os.path.join(ext, "sub", "manifest.json"))
        with self.assertRaises(ValueError):
            bg.companion_xpi(ext)  # only at the root

    def test_missing_folder(self):
        with self.assertRaises(OSError):
            bg.companion_xpi(os.path.join(self.tmp, "nope"))

    def test_xpi_name_is_the_gecko_id(self):
        self.assertEqual(bg.COMPANION_XPI, bg.COMPANION_ID + ".xpi")


class NativeManifestTest(unittest.TestCase):

    def test_valid(self):
        path = "/opt/u/.local/state/dms/browserGlass/" + bg.HOST_WRAPPER
        text = bg.native_manifest_text(path)
        self.assertTrue(text.endswith("\n"))
        doc = json.loads(text)
        self.assertEqual(sorted(doc), ["allowed_extensions", "description", "name", "path", "type"])
        self.assertRegex(doc["name"], r"^\w+(\.\w+)*$")
        self.assertEqual(doc["name"], bg.NATIVE_HOST_NAME)
        self.assertEqual(bg.NATIVE_MANIFEST_NAME, doc["name"] + ".json")
        self.assertTrue(os.path.isabs(doc["path"]))
        self.assertEqual(doc["path"], path)
        self.assertEqual(doc["type"], "stdio")
        self.assertEqual(doc["allowed_extensions"], [bg.COMPANION_ID])
        self.assertEqual(text, bg.native_manifest_text(path))

    def test_odd_path_round_trips(self):
        path = "/tmp/it's a \"dir\"/été/native-host"
        self.assertEqual(json.loads(bg.native_manifest_text(path))["path"], path)

    def test_relative_path_refused(self):
        for bad in ("native-host", "./x", "", None):
            with self.assertRaises(ValueError):
                bg.native_manifest_text(bad)

    def test_location(self):
        # Read by Firefox and LibreWolf; ~/.config/mozilla/... is not.
        self.assertEqual(bg.NATIVE_MANIFEST_REL, ".mozilla/native-messaging-hosts")


class HostWrapperTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        # A fake python3 that prints its arguments, NUL-separated.
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "python3")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nprintf '%s\\0' \"$@\"\n")
        os.chmod(fake, 0o755)

    def run_wrapper(self, plugin_dir):
        wrapper = os.path.join(self.tmp, bg.HOST_WRAPPER)
        with open(wrapper, "w", encoding="utf-8") as f:
            f.write(bg.host_wrapper_text(plugin_dir))
        os.chmod(wrapper, 0o755)
        env = {"PATH": self.bin + os.pathsep + "/usr/bin:/bin"}
        out = subprocess.run([wrapper, "/m/" + bg.NATIVE_MANIFEST_NAME, bg.COMPANION_ID],
                             env=env, stdout=subprocess.PIPE, check=True).stdout
        return out.decode("utf-8").split("\0")[:-1]

    def expected(self, plugin_dir):
        return ["-I", "-B", plugin_dir + "/browserglass.py", "native-host",
                "--data", plugin_dir + "/data",
                "/m/" + bg.NATIVE_MANIFEST_NAME, bg.COMPANION_ID]

    def test_shape(self):
        text = bg.host_wrapper_text("/opt/plugins/browserGlass")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertTrue(text.endswith("\n"))
        self.assertIn("exec python3 -I -B ", text)
        self.assertIn('"$@"', text)

    def test_quotes_and_spaces(self):
        for plugin in ("/tmp/it's my plugins/browserGlass",
                       "/tmp/a b/$HOME `id` \"q\" ; rm -rf x/browserGlass",
                       "/tmp/été \\ back/browserGlass"):
            self.assertEqual(self.run_wrapper(plugin), self.expected(plugin), plugin)

    def test_trailing_slash(self):
        self.assertEqual(self.run_wrapper("/tmp/p q/"), self.expected("/tmp/p q"))

    def test_sh_syntax(self):
        text = bg.host_wrapper_text("/tmp/it's here/browserGlass")
        subprocess.run(["sh", "-n"], input=text.encode("utf-8"), check=True)

    def test_relative_refused(self):
        for bad in ("browserGlass", "", None):
            with self.assertRaises(ValueError):
                bg.host_wrapper_text(bad)


class ConstsTest(unittest.TestCase):

    def test_names(self):
        self.assertEqual(bg.EXTENSION_DIR, "extension")
        self.assertEqual(bg.NATIVE_HOST_NAME, "browserglass")
        self.assertEqual(bg.HOST_WRAPPER, "native-host")
        self.assertEqual(bg.RUNTIME_DIR_NAME, "browserGlass")
        self.assertEqual(bg.PREF_SIGNATURES, "xpinstall.signatures.required")
        self.assertEqual(bg.PREF_AUTODISABLE, "extensions.autoDisableScopes")
        self.assertEqual(bg.PREF_STARTUP_SCAN, "extensions.startupScanScopes")

    def test_live_control_setting(self):
        self.assertIs(bg.SETTINGS_DEFAULTS["liveControl"], False)
        self.assertIs(bg.settings_from_json('{"liveControl": false}')["liveControl"], False)
        self.assertIs(bg.settings_from_json('{"liveControl": "garbage"}')["liveControl"], False)
        self.assertIs(bg.settings_from_json('{"liveControl": true}')["liveControl"], True)


if __name__ == "__main__":
    unittest.main()

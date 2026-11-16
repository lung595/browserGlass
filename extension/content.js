// Browser Glass companion, in every web page. The glass styles skip a page
// whose <html> carries data-browserglass-off, and apply the styles of a
// domain excluded when the browser started (and since put back) only while
// <html> carries data-browserglass-live: this script sets both, together,
// as soon as the exclusion list is known and whenever it changes. It also
// sets data-browserglass-tone to the tone of the page ("light": dark text,
// "dark": light text), measured here and never sent anywhere: the glass
// styles then treat the page as one with a dark version, and tint a light
// page under a dark theme (and a dark one under a light theme). Under a
// dark theme, the glass styles give the root of a page without a dark
// version two colours (--browserglass-darken-*). When the helper says so
// (darken: true with the exclusion list, the darkPages setting; never the
// variables alone, which a page can set itself), a light page first gets
// the usual dark-theme marks on <html> (a "dark"
// class, data-theme="dark"...), kept if its own dark theme then shows,
// and is otherwise turned dark with those colours by Dark Reader (vendor/,
// loaded before this script), and the large elements that paint its background
// get data-browserglass-canvas, which makes them glass, as does the lowest
// layer that paints the background of any page whose root and body are
// see-through (an empty ::before or ::after of a fixed or sticky element
// painting that background gets data-browserglass-filled, naming it). A
// navigation bar fixed or stuck along an edge of the window
// (a header, a bottom bar, a sidebar) with a background of its own gets
// data-browserglass-bar: the same near-opaque blurred surface on every
// site (its rows in its own colour or the page's get
// data-browserglass-canvas too, a layer behind its content holding skip
// links data-browserglass-under, hidden, as is a backdrop drawn in a
// canvas stretched over the page: YouTube's ambient mode). Its blur ends with VEIL, a
// filter this script puts in the page:
// Firefox lays the blurred backdrop over what scrolls under the bar, so
// on the glass (a see-through page) a thin line of text, blurred into a
// faint haze, still showed sharp through it, unlike a picture; VEIL lays
// that haze on the glass's colour, as on a page with a background of its
// own: the text under the bar is blurred like a picture. Text left
// without contrast once its background went (dark text on
// the dark glass) gets data-browserglass-ink, a readable colour (an inline
// SVG icon drawn in its text colour too), and a picture made for a white
// page on a background now dark (a product photo whose white a site wipes
// out with mix-blend-mode, one shot on white on a page Dark Reader
// darkens, a black logo on such a page or on a bar the glass cleared)
// gets data-browserglass-tile: a white tile,
// or light ink for dark ink of one tone and for an icon. On a bar veiled
// light whose labels got dark ink (a site's dark header under a light
// theme), white ink of one tone (a logo painting #fff) gets dark ink the
// same way, and an icon the site whitens with a filter loses the filter.
// An inline SVG logo Dark Reader inverts though its shapes already paint
// light gets data-browserglass-uninvert: no filter. A glyph drawn with a
// background (the bars of a menu button) left without contrast gets
// data-browserglass-glyph, naming its parts: they are painted in the text
// colour. A thin rule in a neutral colour (a separator) Dark Reader left
// without contrast gets data-browserglass-rule: a light neutral.
// A block Dark Reader turns into an opaque near-black panel (a white
// card, a strip) gets data-browserglass-block: a light veil, or glass. So
// does a row of link cards a site paints itself on a see-through page
// (its own dark theme or its light one: SRF's teasers), in the tone's
// surface.
// A small button in a saturated colour gets data-browserglass-brand,
// before Dark Reader dulls it: it keeps its fill and its label's colour.
// A small control Dark Reader darkens to the tone behind it gets the
// mark's "edge": a thin light ring.
// A surface the generic style cleared though the text on it was drawn for
// it (a dark section holding white text on a light page) gets
// data-browserglass-own, which the generic style skips: its colour stays.
// A section across the window painted in the page's colour over a layer
// of its background is one more such layer (canvas), and a linear
// gradient in that colour (a scrim under a sticky header, the solid top
// of a hero) gets data-browserglass-fade: the same gradient, see-through
// where it painted that colour; an empty ::before or ::after fading text
// out into that colour (a list's foot) gets it through
// data-browserglass-fade-pseudo, naming it.
// The text of open shadow trees is read as the page's.
// Before all that, theme.js (loaded before this script) sets the site's
// own stored theme to dark at document_start: this script runs it again
// once the list is known (a restore under a light theme, a late write),
// and gives the values back when the page stayed light (themeFailed).
"use strict";

const LIVE = "data-browserglass-live";
const OFF = "data-browserglass-off";
const TONE = "data-browserglass-tone";
const OWN = "data-browserglass-";
const CANVAS = "data-browserglass-canvas";
const BAR = "data-browserglass-bar";
const INK = "data-browserglass-ink";
const TILE = "data-browserglass-tile";
const UNINVERT = "data-browserglass-uninvert";
const FILLED = "data-browserglass-filled";
const GLYPH = "data-browserglass-glyph";
const BLOCK = "data-browserglass-block";
const RULE = "data-browserglass-rule";
const BRAND = "data-browserglass-brand";
const UNDER = "data-browserglass-under";
const KEPT = "data-browserglass-own";
const FADE = "data-browserglass-fade";
const FADE_IMAGE = "--browserglass-fade";
const FADE_PSEUDO = "data-browserglass-fade-pseudo";
const GLASS = "--browserglass-glass";
const DARKEN_BG = "--browserglass-darken-bg";
const DARKEN_FG = "--browserglass-darken-fg";

function hostExcluded(host, domains) {
  return domains.some((d) => host === d || host.endsWith("." + d));
}

// null until the list is known: the document_start script the background
// registers for excluded domains may run before or after this one, and its
// OFF must not be undone in the meantime. LIVE waits too: set alone, it
// would turn on the live styles of a domain still excluded before OFF
// arrives (a flash of glass).
let off = null;
let fromMessage = false;
// Whether the helper darkens light pages (darken, sent and stored with the
// list): false until it says true, and anything but true is false.
let helperDark = false;
// null until measured (once the document is parsed).
let tone = null;
// true while Dark Reader darkens the page: sticky until the glass styles
// take the colours back (an excluded page, a light theme, a page that
// switched to its own dark version), whatever the tone it then shows.
let darkened = false;
// The page's own dark theme: tried once per dark theme (nativeTried), on
// while it shows (native: {classes, attrs}, what was added, to take back).
let nativeTried = false;
let native = null;
// The marks of the page's own dark theme (ownDark) when Dark Reader
// started, or when it was last taken off for them.
let darkMarks = "";
// What theme.js gets here: the list, the helper's darken and the themes.
let themeCfg = null;
// A page whose own dark value theme.js set before its scripts ran is
// judged THEME_JUDGE_MS after its load event (an app may apply its theme
// late; a failure is remembered for the site), Dark Reader waiting.
const THEME_JUDGE_MS = 1400;
let loadedAt = 0;

// sRGB channel (0-1) to linear light.
function linear(c) {
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function rgbLuminance(r, g, b) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// The relative luminance (0-1) of a computed colour, null if unknown. The
// computed value keeps the page's colour space: rgb(), or oklch(),
// oklab(), lab(), lch() (from their lightness) and color() (wide-gamut
// channels taken as sRGB: close enough for a tone).
function luminance(color) {
  const m = /^([a-z0-9-]+)\(([^)]*)\)/.exec(color);
  if (!m)
    return null;
  const args = m[2].trim().split(/[\s,/]+/);
  const space = m[1] === "color" ? args.shift() : m[1];
  const [a, b, c] = args.map((v) => parseFloat(v) || 0);  // "none" is 0
  switch (space) {
    case "rgb": case "rgba":
      return rgbLuminance(linear(a / 255), linear(b / 255), linear(c / 255));
    case "srgb": case "display-p3": case "a98-rgb": case "prophoto-rgb": case "rec2020":
      return rgbLuminance(linear(a), linear(b), linear(c));
    case "srgb-linear":
      return rgbLuminance(a, b, c);
    case "xyz": case "xyz-d50": case "xyz-d65":
      return b;
    case "oklab": case "oklch":
      return a ** 3;
    case "lab": case "lch":
      return a > 8 ? ((a + 16) / 116) ** 3 : a / 903.3;
  }
  return null;
}

// A text lighter than 0.179 in relative luminance (as far from white as
// from black in contrast) is on a dark page.
function isLight(color) {
  const y = luminance(color);
  return y === null ? null : y > 0.179;
}

// The sRGB value (0-1) of a linear one: the inverse of linear().
function encoded(y) {
  return y <= 0.0031308 ? y * 12.92 : 1.055 * y ** (1 / 2.4) - 0.055;
}

// Grey text between these two luminances (#666 to #aaa: Hacker News'
// #828282 meta lines, a dark theme's muted labels) reads on both a light
// and a dark page: it votes only when no other text does.
const MID_LOW = 0.15;
const MID_HIGH = 0.4;

// The site's own menus: a nav, the page's header and footer (not those of
// an article or a section), and their ARIA roles. A portal's dark header
// can hold hundreds of links before the light content: they vote only when
// no other text does.
function siteChrome(el) {
  const name = el.localName;
  if (name === "nav")
    return true;
  const role = el.getAttribute("role");
  if (role === "navigation" || role === "banner" || role === "contentinfo")
    return true;
  return (name === "header" || name === "footer")
    && !(el.parentElement && el.parentElement.closest("article, aside, main, nav, section"));
}

// A dialog laid over the page (a <dialog>, the roles dialog and
// alertdialog, aria-modal), shown or not: a promotion's white headline on
// its black backdrop tells the dialog's tone, not the page's under it. Its
// text votes as the site's menus do, only when no other text does.
function overlay(el) {
  const role = el.getAttribute("role");
  return el.localName === "dialog" || role === "dialog" || role === "alertdialog"
    || el.getAttribute("aria-modal") === "true";
}

// The text nodes read per measure, at most.
const SAMPLE_NODES = 400;
// The text nodes walked per measure (hidden and empty ones included), at
// most.
const SAMPLE_WALK = 2000;
// Characters of visible text that settle the tone; until then (a
// single-page app still rendering), each resize of the body measures again,
// at most RESIZE_MEASURES times.
const ENOUGH_TEXT = 200;
const RESIZE_MEASURES = 20;
let sampled = 0;
let resizeMeasures = 0;

// Text on a card: inside an element below the body that paints an opaque
// background colour of its own and is not a layer of the page's
// background (backdrop), as a news site's dark video cards on its white
// page. That text is read on its card, whatever the glass behind the page
// shows: it tells the card's tone, not the page's. The root, the body and
// <main> are the page. Looked up once per element and measure.
function onCard(el, cards) {
  if (!el || el === document.body || el === document.documentElement || el.localName === "main")
    return false;
  if (cards.has(el))
    return cards.get(el);
  const value = alpha(getComputedStyle(el).backgroundColor) >= OWN_BG
    ? !backdrop(el) : onCard(el.parentElement, cards);
  cards.set(el, value);
  return value;
}

// A layer of the page's background (CANVAS, or large and not yet marked)
// starts within the first screen of the document: a band as wide and
// almost as tall that starts below it is a card, as a shop's dark footer
// under its light page. A page panel not yet marked is one too: a column
// at least PANEL_WIDE of the window wide, as tall as most of it and down
// to its bottom (COLUMN_TALL, COLUMN_GAP), as ch.ch's white left half
// beside its see-through right one; column() cannot mark it before the
// tone is known, and its text is the page's.
const PANEL_WIDE = 0.4;

function backdrop(el) {
  return (el.hasAttribute(CANVAS) || large(el) || panel(el))
    && el.getBoundingClientRect().top + window.scrollY < window.innerHeight;
}

function panel(el) {
  const r = el.getBoundingClientRect();
  return r.width >= PANEL_WIDE * document.documentElement.clientWidth && tall(el)
    && r.bottom >= (1 - COLUMN_GAP) * window.innerHeight;
}

// Text drawn over a picture (an <img>, a <video>, a <canvas>, an <svg> or
// a background image sized to cover its box, not a texture nor an icon,
// under its middle: a shop's white headlines on its banners) is read on
// the picture, as on a card, a dialog's scrim laid over both aside. One hit test per element in the window, at
// most PICTURE_TESTS elements per measure; text out of the window is on
// the page.
const PICTURES = new Set(["img", "picture", "video", "canvas", "svg"]);
const PICTURE_TESTS = 200;

function onPicture(el, pictures) {
  if (pictures.has(el))
    return pictures.get(el);
  let value = false;
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (r.width && pictures.size < PICTURE_TESTS
      && x >= 0 && y >= 0 && x < window.innerWidth && y < window.innerHeight) {
    const stack = stackAt(x, y);
    // what lies above the text is painted over it, not behind it (a
    // cookie dialog and its scrim): the walk starts at the text, or at
    // what it holds or what holds it below the body (text the pointer
    // passes through is not listed, nor are its parents: the whole stack)
    const at = stack.findIndex((e) => e !== document.body && e !== document.documentElement
      && (holds(el, e) || holds(e, el)));
    for (const e of at > 0 ? stack.slice(at) : stack) {
      if (e === document.body || e === document.documentElement || e.hasAttribute(CANVAS))
        break;
      if (holds(el, e))
        continue;
      const style = getComputedStyle(e);
      if ((/url\(/.test(style.backgroundImage) && /cover|contain/.test(style.backgroundSize))
          || (!holds(e, el) && PICTURES.has(e.localName))) {
        value = true;
        break;
      }
      // a card under the text: onCard's
      if (alpha(style.backgroundColor) >= OWN_BG)
        break;
    }
  }
  pictures.set(el, value);
  return value;
}

// Text out of sight that checkVisibility still counts: the "visually
// hidden" pattern of a skip link or a label for screen readers, clipped
// to nothing (clip, clip-path inset(50%)), in a box of a pixel that hides
// its overflow, or placed above or left of the page until focused, on the
// element or up to HIDDEN_DEPTH - 1 of its parents. A dark app's black
// "Skip to main content" link does not vote. Nor does text whose middle
// lies left or right of the window: a carousel's next slide, laid beside
// the one shown (its white headline, meant for a picture not yet hit
// tested by onPicture, would make a white page dark).
const HIDDEN_DEPTH = 2;

function unseen(el) {
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  if (r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0 || x < 0 || x >= window.innerWidth)
    return true;
  for (let e = el, i = 0; e && e !== document.body && i < HIDDEN_DEPTH; e = e.parentElement, i++) {
    const style = getComputedStyle(e);
    const box = e === el ? r : e.getBoundingClientRect();
    if ((box.width <= 1 || box.height <= 1) && style.overflow !== "visible")
      return true;
    const [top, right, bottom, left] = (/^rect\((.*)\)/.exec(style.clip) || ["", ""])[1]
      .split(/[\s,]+/).map(parseFloat);
    if (right - left <= 1 || bottom - top <= 1)  // NaN (auto) is not
      return true;
    const inset = /^inset\(([\d.]+)%/.exec(style.clipPath);
    if (inset && parseFloat(inset[1]) >= 50)
      return true;
  }
  return false;
}

// A drawing board (Excalidraw): a <canvas> filling the window
// (BOARD_COVER of it at least) paints the page's background itself, its
// white not seen in any style; what text the app shows lies over it (on a
// picture: its welcome screen's pale grey hints) or on its toolbars
// (cards). When no text on the page's background decides, the board's
// pixels do: one painted opaque (BOARD_CLEAR of its pixels see-through at
// most, not an app's empty top layer), unfiltered, gives the tone of its
// median luminance. Its pixels are read again at each measure (a board is
// redrawn without a mutation), on a canvas SAMPLE_SIDE px at most.
const BOARD_COVER = 0.8;
const BOARD_CLEAR = 0.1;

function boardTone() {
  const w = window.innerWidth, h = window.innerHeight;
  for (const c of document.body.getElementsByTagName("canvas")) {
    const r = c.getBoundingClientRect();
    const seen = Math.max(0, Math.min(r.right, w) - Math.max(r.left, 0))
      * Math.max(0, Math.min(r.bottom, h) - Math.max(r.top, 0));
    if (seen < BOARD_COVER * w * h || getComputedStyle(c).filter !== "none"
        || !c.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      continue;
    const s = pixels(c, r);
    if (s && s.clear <= BOARD_CLEAR)
      return s.inks[INK_STEPS / 2] > 0.179 ? "light" : "dark";
  }
  return null;
}

// The page's own colour, when no text on the page's background decides
// (a portal whose sections fade in once scrolled to, at opacity 0 until
// then, its carousel's text over pictures): the opaque background colour
// the body paints without the add-on's styles (unstyled: the generic page
// rules skip KEPT), null when it paints none. A white body is a light
// page, whatever its cards and pictures hold. The root is not read: the
// tone's tint lies on it once measured.
function paintTone() {
  const fill = unstyled(document.body);
  const light = fill !== null && alpha(fill) >= SOLID ? isLight(fill) : null;
  return light === null ? null : light ? "light" : "dark";
}

// A level of the vote decides with VOTE_NODES text nodes or VOTE_CHARS
// characters: a lone short line (a loading message left under the app,
// a skip link) gives way to the next level, the text on cards included.
const VOTE_NODES = 2;
const VOTE_CHARS = 40;

// The tone from the colour of the text shown, the site styles included:
// the visible text of the body votes, each node by its length (capped, so
// one long paragraph does not outweigh the page); the text on the page's
// background (not on a card nor a picture, onCard, onPicture), outside
// the site's menus and its dialogs (overlay), decides
// first, the mid-grey band aside (siteChrome, MID_LOW), then the text
// outside the menus, cards included (VOTE_NODES, VOTE_CHARS). Text out of
// sight does not vote (unseen). Text this script inked (INK, set as soon
// as the page renders, before its tone is known: dark text read on the
// dark glass of a dark theme) votes with the colour the page gave it
// (ownColor), not the readable one: else a light page's navy text, inked
// light, would make it a dark page. Without text on the page's background, a
// drawing board's pixels come before the other levels (boardTone), then
// the colour the body paints (paintTone): the text left on
// cards and pictures tells their tone, not the page's. They come first
// while a modal dialog is open (:modal).
// Many pages leave the body's own colour at the default black and colour
// their text through classes (YouTube's dark theme): the body alone would
// read as light. A
// page without visible text falls back to the body's colour (the root's
// before there is a body); an unknown colour keeps the last tone.
function measure() {
  // a darkened page shows light text on dark (Dark Reader's styles may
  // still be on their way)
  if (darkened) {
    tone = "dark";
    return;
  }
  if (document.readyState === "loading")
    return;
  const el = document.body || document.documentElement;
  if (!el)
    return;
  // [light text, dark text] in characters: all of it, the text outside
  // the mid-grey band, the same outside the site's menus, and the same
  // outside the menus, the cards and the pictures
  const all = [0, 0, 0], firm = [0, 0, 0], main = [0, 0, 0], mainFirm = [0, 0, 0];
  const page = [0, 0, 0], pageFirm = [0, 0, 0];
  // the length on its side, one node more
  const add = (t, side, len) => {
    t[side] += len;
    t[2]++;
  };
  if (document.body) {
    const parents = new Map(), cards = new Map(), pictures = new Map();
    let read = 0, walked = 0;
    // tallies the text under root; with menus, the site's menus and the
    // dialogs (overlay) met on the way are skipped whole (a portal's
    // header can hold thousands of text nodes before the content) and
    // listed there
    const tally = (root, menus) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
        (node) => {
          if (node.nodeType === Node.TEXT_NODE)
            return NodeFilter.FILTER_ACCEPT;
          if (menus && (siteChrome(node) || overlay(node))) {
            menus.push(node);
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_SKIP;
        });
      for (let n = walker.nextNode(); n && read < SAMPLE_NODES && walked < SAMPLE_WALK;
           walked++, n = walker.nextNode()) {
        const p = n.parentElement;
        const len = Math.min(n.data.trim().length, 80);
        if (!len || !p)
          continue;
        if (!parents.has(p)) {
          let y = null;
          if (p.checkVisibility({visibilityProperty: true, opacityProperty: true}) && !unseen(p))
            y = luminance(ownColor(p));
          parents.set(p, y);
        }
        const y = parents.get(p);
        if (y === null)
          continue;
        const side = y > 0.179 ? 0 : 1;
        const isFirm = y <= MID_LOW || y >= MID_HIGH;
        add(all, side, len);
        if (isFirm)
          add(firm, side, len);
        if (menus) {
          add(main, side, len);
          if (isFirm)
            add(mainFirm, side, len);
          if (!onCard(p, cards) && !onPicture(p, pictures)) {
            add(page, side, len);
            if (isFirm)
              add(pageFirm, side, len);
          }
        }
        read++;
      }
    };
    const menus = [];
    tally(document.body, menus);
    // the menus vote only on a page with no other text
    if (main[0] + main[1] === 0)
      for (const m of menus)
        tally(m, null);
  }
  const levels = [pageFirm, page, mainFirm, main, firm, all];
  const decides = (t) => t[2] >= VOTE_NODES || t[0] + t[1] >= VOTE_CHARS;
  sampled = all[0] + all[1];
  // no text on the page's background: a drawing board under the app, or
  // the page's own colour; the same first under a modal dialog, which
  // takes the page under it out of the hit tests (inert): its text over
  // pictures would count as on the page's background (onPicture)
  const modal = document.querySelector(":modal") !== null;
  const board = document.body && (modal || !decides(page)) ? boardTone() || paintTone() : null;
  if (board !== null) {
    tone = board;
    return;
  }
  const votes = levels.find(decides) || levels.find((t) => t[0] + t[1] > 0) || all;
  const [light, dark] = votes;
  const v = sampled ? light > dark : isLight(getComputedStyle(el).color);
  if (v !== null)
    tone = v ? "dark" : "light";
}

const sizes = new ResizeObserver(() => {
  if (++resizeMeasures > RESIZE_MEASURES)
    sizes.disconnect();
  else
    update();
});

function update() {
  measure();
  darken();
  paint();
  watchLayers();
  markCanvas();
  markBars();
  markFills();
  ink();
  if (darkened || sampled >= ENOUGH_TEXT || resizeMeasures >= RESIZE_MEASURES)
    sizes.disconnect();
  else if (document.body && document.readyState !== "loading")
    sizes.observe(document.body);
}

function paint() {
  const root = document.documentElement;
  if (!root || off === null)
    return;
  if (off !== root.hasAttribute(OFF))
    off ? root.setAttribute(OFF, "") : root.removeAttribute(OFF);
  if (!root.hasAttribute(LIVE))
    root.setAttribute(LIVE, "");
  // A page with a tone gets the site styles under a dark theme, and some
  // recolour its text (white on the glass): the tone is measured again at
  // once, so it is that of the text shown. They depend on the tone being
  // set, not on its value, so a second pass never changes it back.
  for (let pass = 0; pass < 2 && tone !== null && root.getAttribute(TONE) !== tone; pass++) {
    root.setAttribute(TONE, tone);
    unkeep();
    measure();
  }
}

// The Dark Reader theme the glass styles give this page, null when it
// stays as it is. The page's own CSS can set these colours too: the dark
// theme, which it cannot fake here, is checked as well.
function darkTheme() {
  const root = document.documentElement;
  if (!root || off !== false || !helperDark || typeof DarkReader === "undefined"
      || !window.matchMedia("(prefers-color-scheme: dark)").matches)
    return null;
  const style = getComputedStyle(root);
  const bg = style.getPropertyValue(DARKEN_BG).trim();
  const fg = style.getPropertyValue(DARKEN_FG).trim();
  return bg && fg ? {darkSchemeBackgroundColor: muted(bg), darkSchemeTextColor: muted(fg)} : null;
}

// Dark Reader gives grey text (and grey backgrounds) the hue and
// saturation of its two colours: a near-white with a hint of blue
// (#f7f9ff, a saturation of 100%) turns mid-grey text bright blue. Their
// saturation is capped at POLE_SAT (that of Dark Reader's own text
// colour, #e8e6e3), hue and lightness kept (a near-white stays one).
const POLE_SAT = 0.1;
function muted(color) {
  const m = /^#([0-9a-f]{6})$/i.exec(color);
  if (!m)
    return color;
  const c = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255);
  const hi = Math.max(...c), lo = Math.min(...c), l = (hi + lo) / 2;
  const s = hi === lo ? 0 : (hi - lo) / (1 - Math.abs(2 * l - 1));
  if (s <= POLE_SAT)
    return color;
  // each channel drawn towards the lightness: the chroma, so the
  // saturation, scales by k, the hue and the lightness stay
  const k = POLE_SAT / s;
  return "#" + c.map((v) => Math.round((l + (v - l) * k) * 255).toString(16).padStart(2, "0")).join("");
}

// Dark Reader reads the page's cross-origin stylesheets with this script's
// fetch (the add-on's host permission), and the page can read what it
// copies: no cookies, no referrer, and only a stylesheet. The fetches in
// flight, their text read too, are counted (fetching): a restart of Dark
// Reader waits for none (restyle).
let fetching = 0;

function fetchStylesheet(url) {
  fetching++;
  return fetch(url, {credentials: "omit", cache: "force-cache", referrerPolicy: "no-referrer"})
    .then((r) => {
      if (!r.ok || !/^text\/css\b/i.test(r.headers.get("Content-Type") || ""))
        throw new Error("not a stylesheet");
      return r.text().then((text) => new Response(text, {headers: r.headers}));
    })
    .finally(() => {
      fetching--;
      if (!fetching && restyleWaits) {
        restyleWaits = false;
        settle();
      }
    });
}

// The marks of a page's own dark theme set on <html> (the ones the glass
// styles read as a page with a dark version: _DARK_PAGE_MARKERS).
const NATIVE_CLASSES = ["dark", "dark-mode", "theme-dark"];
const NATIVE_ATTRS = [["data-theme", "dark"], ["data-bs-theme", "dark"], ["data-color-mode", "dark"],
  ["data-theme-mode", "dark"], ["data-mode", "dark"], ["dark", ""]];
const NO_TRANSITIONS = "*, *::before, *::after { transition: none !important; }";

// The marks of a dark theme the page set on <html> itself, while Dark
// Reader runs: a mark of NATIVE_CLASSES or NATIVE_ATTRS, or any attribute
// data-*-theme or data-*-scheme holding dark (DSFR's data-fr-theme, set
// by a module script run once the page is parsed); Dark Reader's own and
// ours aside. Their names, "" when none.
const OWN_DARK = /^data-(?!darkreader-|browserglass-)([\w-]+-)?(theme|scheme)$/;

function ownDark() {
  const root = document.documentElement;
  if (!root || native)
    return "";
  const names = NATIVE_CLASSES.filter((c) => root.classList.contains(c));
  for (const {name, value} of root.attributes)
    if (OWN_DARK.test(name) ? value.toLowerCase().split(/\s+/).includes("dark")
        : NATIVE_ATTRS.some(([n, v]) => n === name && v === value))
      names.push(name);
  return names.join(" ");
}

// Runs fn with the page's transitions held, so the colours it measures
// are the final ones.
function steady(fn) {
  const hold = document.createElement("style");
  hold.textContent = NO_TRANSITIONS;
  (document.head || document.documentElement).append(hold);
  fn();
  hold.remove();
}

// Takes back what nativeDark() added, leaving alone what the page changed
// since (a class of its own, a value it set).
function nativeRestore() {
  const root = document.documentElement;
  if (native && root) {
    root.classList.remove(...native.classes);
    for (const [name, value] of native.attrs)
      if (root.getAttribute(name) === NATIVE_ATTRS.find(([n]) => n === name)[1])
        value === null ? root.removeAttribute(name) : root.setAttribute(name, value);
  }
  native = null;
}

// Turns on the page's own dark theme if it has one: the marks are set, the
// tone measured at once (transitions held, so the colours are the final
// ones), and kept only if the text turned light; true then. Else they go
// with the transitions held too: the page's colours are back at once, not
// easing back from those of its dark theme while the brand buttons are
// read (markBrands: a crimson button kept coral).
function nativeDark() {
  const root = document.documentElement;
  native = {classes: NATIVE_CLASSES.filter((c) => !root.classList.contains(c)),
    attrs: NATIVE_ATTRS.map(([name]) => [name, root.getAttribute(name)])};
  steady(() => {
    root.classList.add(...NATIVE_CLASSES);
    for (const [name, value] of NATIVE_ATTRS)
      root.setAttribute(name, value);
    measure();
  });
  if (tone === "dark")
    return true;
  steady(() => {
    nativeRestore();
    measure();
  });
  return false;
}

// A light page is darkened once its tone is settled (enough text, or the
// page loaded): a single-page app still rendering may show little text.
// Its own dark theme is tried first; the marks are taken back with a light
// theme, once the page is excluded or once the helper stops the darkening.
// A page that turns its own dark theme on while darkened (new ownDark
// marks) gets Dark Reader off, and back at once if it still shows light.
function darken() {
  // the site's own stored theme was set before its scripts ran and the
  // page still shows light once loaded: the values go back, then the
  // marks or Dark Reader below
  let themeWait = false;
  if (typeof themeState !== "undefined" && themeState.early && tone === "light") {
    if (loadedAt && performance.now() - loadedAt >= THEME_JUDGE_MS)
      themeFailed();
    else
      themeWait = true;
  }
  // a light theme, an excluded page, the darkening stopped, or the page
  // took its dark theme back (it shows dark text again): taken back with
  // the transitions held, the brand buttons read below being the page's
  // own colours, not those of its dark theme it eases back from
  if (native && (off !== false || !helperDark || tone === "light"
      || !window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    steady(() => {
      nativeRestore();
      measure();
    });
  }
  if (off !== false || !helperDark || !window.matchMedia("(prefers-color-scheme: dark)").matches)
    nativeTried = false;
  const theme = darkTheme();
  const own = darkened && theme ? ownDark() : "";
  if (darkened && (!theme || own && own !== darkMarks)) {
    darkMarks = own;
    darkened = false;
    DarkReader.disable();
    frameSchemes();
    for (const el of marked("[" + CANVAS + "], [" + FILLED + "], [" + BLOCK + "], [" + UNDER + "]"))
      el.removeAttribute(CANVAS), el.removeAttribute(FILLED), el.removeAttribute(BLOCK), el.removeAttribute(UNDER);
    unfade();
    unmarkBrands();
    steady(measure);
  }
  if (!darkened && theme && tone === "light" && !themeWait
      && (sampled >= ENOUGH_TEXT || document.readyState === "complete")) {
    if (!nativeTried) {
      nativeTried = true;
      if (nativeDark())
        return;
    }
    darkened = true;
    darkMarks = ownDark();
    unkeep();
    markBrands();
    DarkReader.setFetchMethod(fetchStylesheet);
    DarkReader.enable(theme, DR_FIXES);
    frameSchemes();
    measure();
    settle();
  }
}

// Dark Reader darkens the style sheets a shadow tree adopts when it first
// meets the tree, and follows later changes through the page's array
// methods, which Firefox does not let a content script call back from
// ("Permission denied to access object"): a sheet adopted once the tree
// was met stays light (a Stencil component attaches its tree, then adopts
// its styles once its code is in: Swiss Post's header, nested trees of
// links and widgets). On a pass of settle() while darkened, an open shadow
// tree adopting a sheet with no override of Dark Reader after it (whose
// first rule is DR_OVERRIDE) restarts Dark Reader, which meets every tree
// again and darkens it, then gets passes of its own (the trees inside
// may adopt theirs later still): at most RESTARTS times a page, and a
// sheet seen once (restyled) never restarts it again. Not while Dark
// Reader fetches a stylesheet (fetching): a sheet whose fetch ends once
// its manager is gone is drawn all the same, by a manager no disable()
// reaches, which puts an empty style back in the page after the switch
// to light (Swiss Post); the restart waits (restyleWaits) for the last
// fetch, which settles the page again.
const DR_OVERRIDE = "#__darkreader__adoptedOverride";
const RESTARTS = 4;
const restyled = new WeakSet();
let restarts = 0, restyleWaits = false;

// Whether `sheet` is an override Dark Reader adopted.
function drOverride(sheet) {
  return !!sheet && sheet.cssRules.length > 0 && sheet.cssRules[0].selectorText === DR_OVERRIDE;
}

// The sheets adopted in the open shadow trees under `root` (the trees in
// them too) that Dark Reader left as they are, not seen before. The page's
// own array is read (wrappedJSObject: its items, by index), never its
// methods.
function undarkened(root, found = []) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
  for (let el = walker.nextNode(); el; el = walker.nextNode()) {
    const tree = el.shadowRoot;
    if (!tree)
      continue;
    const list = tree.adoptedStyleSheets.wrappedJSObject || tree.adoptedStyleSheets;
    for (let i = 0; i < list.length; i++)
      if (!drOverride(list[i]) && !drOverride(list[i + 1]) && !restyled.has(list[i]) && list[i].cssRules.length)
        found.push(list[i]);
    undarkened(tree, found);
  }
  return found;
}

function restyle() {
  const theme = darkened && restarts < RESTARTS ? darkTheme() : null;
  const left = theme ? undarkened(document) : [];
  if (!left.length)
    return;
  if (fetching) {
    restyleWaits = true;
    return;
  }
  for (const sheet of left)
    restyled.add(sheet);
  restarts++;
  DarkReader.disable();
  DarkReader.enable(theme, DR_FIXES);
  measure();
  settle();
}

// A saturated button keeps its colours: Dark Reader darkens every fill,
// a brand colour too (a yellow turns olive, its petrol label light grey:
// 2.8:1; a violet goes dull). Just before Dark Reader runs (the page's
// colours still its own), a control (BRANDS) at most BRAND_W by BRAND_H
// px, with a label (BRAND_TEXT characters at most), whose opaque fill
// (SOLID; its own, or that of a ::before or ::after covering FACE of it,
// no background image) reads against its label (BRAND_READ) and has
// BRAND_CHROMA of chroma at least, or BRAND_PASTEL under a darker label
// (a pastel teal, which Dark Reader turns olive-black), gets BRAND naming
// that part, and both colours inline (BRAND_FILL, BRAND_INK; Dark Reader
// leaves the inline style of a marked element alone: DR_FIXES): the glass
// styles paint them back, the label's on the whole control. A dark plain
// fill (luminance under BRAND_DARK) under a lighter label is kept too,
// LIFT named with the part: Dark Reader leaves it dark, the same as the
// dark glass or a dark bar's veil, and the glass styles give it a thin
// light ring (it read as plain text). At most BRAND_ELEMENTS are looked
// at. A button drawn once the page is darkened is not seen (Dark Reader
// has its colours by then); the marks go with the darkening.
// A control at most BRAND_W by BRAND_H px painting no fill of its own
// (see-through, no background image) is remembered with its classes and
// states (clears): one that Dark Reader then fills opaque (CLEAR), those
// the same (controlState) and neither hovered nor focused, gets BRAND
// "clear" (markClears, on each pass of the ink): see-through again. Dark
// Reader fills a background-color: var(--x) whose --x the page never sets
// (a text button of a design system) with its own background colour, a
// solid pill.
const BRAND_FILL = "--browserglass-brand-fill";
const BRAND_INK = "--browserglass-brand-ink";
const BRANDS = "button, a[href], [role=button], input[type=submit], input[type=button]";
const BRAND_W = 480;
const BRAND_H = 96;
const BRAND_TEXT = 60;
const BRAND_CHROMA = 0.4;
const BRAND_PASTEL = 0.25;
const BRAND_DARK = 0.05;
const BRAND_READ = 3;
const BRAND_ELEMENTS = 1000;
const LIFT = "lift";
const UNFILLED = "clear";
const EDGED = "edge";
const DR_FIXES = {ignoreInlineStyle: ["[" + BRAND + "]:not([" + BRAND + "=\"" + EDGED + "\"])"]};
let clears = new Map();

function markBrands() {
  clears = new Map();
  const controls = document.body ? document.body.querySelectorAll(BRANDS) : [];
  for (let i = 0; i < controls.length && i < BRAND_ELEMENTS; i++) {
    const el = controls[i];
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || r.width > BRAND_W || r.height > BRAND_H)
      continue;
    const style = getComputedStyle(el);
    if (alpha(style.backgroundColor) === 0 && style.backgroundImage === "none")
      clears.set(el, controlState(el));
    const ink = labelColor(el);
    if (!ink)
      continue;
    for (const part of [...PSEUDOS, "self"]) {
      const fill = brandFill(el, r, part);
      const kind = fill && brandKind(fill, ink);
      if (kind) {
        el.setAttribute(BRAND, kind === LIFT ? part + " " + LIFT : part);
        el.style.setProperty(BRAND_FILL, fill);
        el.style.setProperty(BRAND_INK, ink);
        break;
      }
    }
  }
}

// Whether a fill and its label are kept: null, true (a saturated or a
// pastel fill), or LIFT (a dark plain one).
function brandKind(fill, ink) {
  const y = luminance(fill), fg = luminance(ink);
  if (y === null || fg === null || contrast(y, fg) < BRAND_READ)
    return null;
  const c = chroma(fill);
  if (c >= BRAND_CHROMA || c >= BRAND_PASTEL && fg < y)
    return true;
  return y < BRAND_DARK && fg > y ? LIFT : null;
}

// The controls painting no fill of their own before Dark Reader ran that
// it fills opaque, near the window: see-through again (BRAND "clear"),
// any block mark taken off (a veil of its own would stay).
function markClears(near) {
  if (!darkened)
    return;
  for (const [el, state] of clears) {
    if (!el.isConnected || el.hasAttribute(BRAND) || !near(el) || controlState(el) !== state
        || el.matches(":hover, :focus-within") || alpha(getComputedStyle(el).backgroundColor) < CLEAR)
      continue;
    el.setAttribute(BRAND, UNFILLED);
    el.removeAttribute(BLOCK);
  }
}

// A control Dark Reader leaves without an edge: its fill and what holds
// it end up a few luminance steps apart, both dark, though they were
// not (a white button on a site's own black panel, which Dark Reader
// leaves black, darkened to near-black: Zalando's consent banner, in a
// shadow tree; a black button on a white card, the card darkened around
// it: a popover shown once the page is darkened, which markBrands never
// sees). On each pass of the ink while darkened, a control (BRANDS) near
// the window, at most BRAND_W by BRAND_H px, not marked otherwise nor
// one see-through before Dark Reader ran (clears), whose own opaque
// fill reads against its label (BRAND_READ) and against what is behind
// it (behind, from its parent) under EDGE_RATIO but not the same (an
// equal fill: a button the page drew flat on its card), what is behind
// it dark (DARK_BG), and that draws no border or shadow of its own that
// reads there, gets BRAND "edge": the glass styles give it the thin
// light ring of LIFT, its colours Dark Reader's. A mark whose control no
// longer is such goes; all go with the darkening.
const EDGE_RATIO = 1.25;

function markEdges(near) {
  for (const el of marked("[" + BRAND + "=\"" + EDGED + "\"]"))
    if (!darkened || !edgeless(el))
      el.removeAttribute(BRAND);
  if (!darkened)
    return;
  const controls = everywhere(BRANDS);
  for (let i = 0; i < controls.length && i < BRAND_ELEMENTS; i++) {
    const el = controls[i];
    if (!el.hasAttribute(BRAND) && !clears.has(el) && near(el) && edgeless(el))
      el.setAttribute(BRAND, EDGED);
  }
}

function edgeless(el) {
  const r = el.getBoundingClientRect();
  if (!(r.width > 0 && r.height > 0) || r.width > BRAND_W || r.height > BRAND_H)
    return false;
  const fill = brandFill(el, r, "self"), ink = labelColor(el);
  const y = fill && luminance(fill), fg = ink && luminance(ink);
  const bg = fill && up(el) ? behind(up(el)) : null;
  if (y === null || fg === null || bg === null || bg > DARK_BG || contrast(y, fg) < BRAND_READ)
    return false;
  const apart = contrast(y, bg);
  return apart > 1 && apart < EDGE_RATIO && !outlined(el, bg);
}

// Whether a control draws an edge of its own that shows on `bg`: a
// border side (a px at least) or a shadow of its own (not the ring of an
// edge mark) in a colour EDGE_RATIO from it at least. An edge in the
// fill's colour (Zalando's black button, ringed by an inset shadow in
// its black) shows on the light card it was drawn for, not on the dark.
function outlined(el, bg) {
  const style = getComputedStyle(el);
  const shows = (color) => {
    const y = luminance(color);
    return alpha(color) >= CLEAR && y !== null && contrast(y, bg) >= EDGE_RATIO;
  };
  if (el.getAttribute(BRAND) !== EDGED && (style.boxShadow.match(PAINT) || []).some(shows))
    return true;
  return ["Top", "Right", "Bottom", "Left"].some((side) =>
    parseFloat(style["border" + side + "Width"]) >= 1 && shows(style["border" + side + "Color"]));
}

// What a page restyles a control by: its classes and its ARIA states (a
// tab selected, a toggle pressed).
const CONTROL_STATES = ["class", "aria-selected", "aria-pressed", "aria-current", "aria-expanded", "aria-checked"];

function controlState(el) {
  return CONTROL_STATES.map((a) => el.getAttribute(a)).join("\n");
}

// The colour of a control's label (that of its first text), null when it
// has none or a long one (a card, not a button).
function labelColor(el) {
  if (el.localName === "input") {
    const text = el.value.trim();
    return text && text.length <= BRAND_TEXT ? getComputedStyle(el).color : null;
  }
  const text = el.textContent.trim();
  if (!text || text.length > BRAND_TEXT)
    return null;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode())
    if (node.data.trim() && node.parentElement)
      return getComputedStyle(node.parentElement).color;
  return null;
}

// The opaque fill a part of `el` ("self", "before", "after") paints over
// it, null if none.
function brandFill(el, r, part) {
  const style = getComputedStyle(el, part === "self" ? null : "::" + part);
  if (part !== "self" && (style.content === "none" || style.display === "none"
      || parseFloat(style.width) * parseFloat(style.height) < FACE * r.width * r.height))
    return null;
  const fill = style.backgroundColor;
  return style.backgroundImage === "none" && alpha(fill) >= SOLID ? fill : null;
}

// The chroma (0-1) of a computed colour, in sRGB (channels), 0 if unknown.
function chroma(color) {
  const c = channels(color);
  return c ? (Math.max(...c) - Math.min(...c)) / 255 : 0;
}

function unmarkBrands() {
  clears = new Map();
  for (const el of document.querySelectorAll("[" + BRAND + "]")) {
    el.removeAttribute(BRAND);
    el.style.removeProperty(BRAND_FILL);
    el.style.removeProperty(BRAND_INK);
    if (el.getAttribute("style") === "")
      el.removeAttribute("style");
  }
}

// Dark Reader gives every frame a dark colour scheme; a frame from another
// site is not darkened and its light page then gets an opaque backdrop (a
// white box, a consent dialog's grey veil over the whole page): frames
// keep the scheme they had while the page is darkened, on their own style
// (Dark Reader's rule, in a cascade layer, beats any style sheet of the
// page), looked at on each pass of the layers; taken off after. A frame
// added while the page is darkened gets it at once, before it is drawn
// (newFrames): the next pass may be seconds away for one added deep in
// the page (a sign-in prompt), whose white box shows until then.
const frames = document.getElementsByTagName("iframe");
let schemed = new Map();
let framesWatched = false;

const newFrames = new MutationObserver((records) => {
  for (const r of records)
    for (const el of r.addedNodes)
      if (el.localName === "iframe" || el.firstElementChild && el.querySelector("iframe"))
        return frameSchemes();
});

function frameSchemes() {
  if (!darkened) {
    for (const [el, [value, priority]] of schemed)
      value ? el.style.setProperty("color-scheme", value, priority) : el.style.removeProperty("color-scheme");
    schemed = new Map();
    newFrames.disconnect();
    framesWatched = false;
    return;
  }
  if (!framesWatched) {
    framesWatched = true;
    newFrames.observe(document, {childList: true, subtree: true});
  }
  for (const el of frames)
    if (el.style.getPropertyPriority("color-scheme") !== "important" || !schemed.has(el)) {
      const value = el.style.getPropertyValue("color-scheme");
      if (!schemed.has(el))
        schemed.set(el, [value, el.style.getPropertyPriority("color-scheme")]);
      el.style.setProperty("color-scheme", value || "normal", "important");
    }
}

// The alpha (0-1) of a computed colour; 1 when unknown.
// The parent an element is drawn in: the slot it is assigned to in a
// shadow tree, its parent, or the host at the top of a shadow tree.
function up(el) {
  return el.assignedSlot || el.parentElement || (el.parentNode && el.parentNode.host) || null;
}

// The open shadow trees met by shownText, so that their marks are found
// and taken off again (marked).
const shadows = new Set();

// The elements matching `selector` in the document and in the shadow
// trees met, those of hosts gone from the page forgotten.
function marked(selector) {
  const found = [...document.querySelectorAll(selector)];
  for (const tree of shadows)
    tree.host.isConnected ? found.push(...tree.querySelectorAll(selector)) : shadows.delete(tree);
  return found;
}

// The elements matching `selector` in the body and in the shadow trees
// met (the passes over icons, pictures and glyphs: their budgets count
// them all).
function everywhere(selector) {
  const found = [...document.body.querySelectorAll(selector)];
  for (const tree of shadows)
    if (tree.host.isConnected)
      found.push(...tree.querySelectorAll(selector));
  return found;
}

// The elements at a point, the topmost first, as elementsFromPoint lists
// them, with the open shadow trees of the hosts there opened (at most
// SHADOW_HOSTS a point): a web component's header, band or button in its
// place, above its host, rather than the host alone (the document's list
// stops at the host). Its trees are met (shadows). A host listed twice
// (its own box, and a fixed part of its tree on top) is kept at its last
// place, under its tree.
const SHADOW_HOSTS = 8;

function stackAt(x, y) {
  let stack = document.elementsFromPoint(x, y);
  const opened = new Set();
  for (let n = 0; n < stack.length && opened.size < SHADOW_HOSTS; n++) {
    const host = stack[n], tree = host.shadowRoot;
    if (!tree || opened.has(host))
      continue;
    opened.add(host);
    shadows.add(tree);
    // the tree's own elements, laid above the next element of the stack
    // its list shows, or above the host (Firefox lists the tree's alone)
    const merged = [...stack];
    let held = [];
    for (const el of tree.elementsFromPoint(x, y)) {
      if (el.getRootNode() === tree) {
        held.push(el);
        continue;
      }
      const at = merged.indexOf(el);
      if (at >= 0 && held.length) {
        merged.splice(at, 0, ...held);
        held = [];
      }
    }
    merged.splice(merged.indexOf(host), 0, ...held);
    stack = merged.filter((el, i) => merged.lastIndexOf(el) === i);
    n = -1;
  }
  return stack;
}

// Whether `b` is drawn inside `a`, across shadow trees and slots (up).
function holds(a, b) {
  for (let e = b; e; e = up(e))
    if (e === a)
      return true;
  return false;
}

// The nearest element up from `el` (itself not included), across shadow
// trees and slots, that matches `selector`, or null.
function outer(el, selector) {
  for (let e = up(el); e; e = up(e))
    if (e.matches(selector))
      return e;
  return null;
}

// The elements inside `el`, those of its own open shadow tree too (a web
// component painting itself).
function inside(el) {
  const kids = [...el.querySelectorAll("*")];
  if (el.shadowRoot)
    kids.push(...el.shadowRoot.querySelectorAll("*"));
  return kids;
}

// The children `el` is drawn with: its own, and those of its shadow tree.
function layered(el) {
  return el.shadowRoot ? [...el.children, ...el.shadowRoot.children] : [...el.children];
}

function alpha(color) {
  if (color === "transparent")
    return 0;
  const m = /\(([^)]*)\)/.exec(color);
  if (!m)
    return 1;
  const args = m[1].trim().split(/[\s,/]+/);
  const last = args[/^color\(/.test(color) ? 4 : 3];
  return last === undefined ? 1 : last.endsWith("%") ? parseFloat(last) / 100 : parseFloat(last);
}

// The page's own background: when the root and the body are see-through
// (the generic style; the root under the tone tint counts, tinted), the
// lowest layer under a grid of points that paints an opaque background
// colour (not a dialog's dimming) and covers most of
// the window (often a fixed full-window container) gets CANVAS, unless it
// is fixed, or inside a fixed element, over other content of the page (a
// dialog, a cookie banner): the glass styles make that colour transparent;
// the cards and panels drawn over it keep theirs. On a darkened page every
// such large layer does, except fixed ones (dialogs). A layer loses CANVAS
// once smaller, and all do once the root or the body paints a background
// again. The colours of the layers marked are the page's colours
// (pageColors, for markFills).
// Such a layer need not span the window's width: a page column (a feed
// centred in the window, the pane right of an app's menu, a side panel
// down to the bottom) is one too (column).
// The grid has a row more along the window's bottom edge, GRID_EDGE px
// in: a band in view only below the grid's last row (a section just under
// the first screen) is found before any scroll. On that row, what a fixed
// or sticky element holds is left to the bars (a cookie banner, a bottom
// bar). None along the top edge of a dark page: a band above the first
// row at the top of the page is the site's header (GitHub's), solid as
// the site drew it. On a light page Dark Reader leaves alone, a row
// along the top edge too: a strip there near the page's white (Zalando's
// service links in rgb(241, 241, 241)) is a band of the page, now glass,
// as Dark Reader's darkened strips are (markBlocks), not an opaque grey
// band over the light glass.
const GRID = 5;
const GRID_EDGE = 2;
const CLEAR = 0.5;
const SOLID = 0.99;
const FILL = "fill";
const pageColors = new Set();
const layerColors = new WeakMap();

// A marked element is watched: its size changes (or its removal, a view
// swapped) look again.
function mark(el, attr) {
  el.setAttribute(attr, "");
  layerSizes.observe(el);
}

// Whether an element covers most of the window: a layer of the page's
// background, not a card or a panel drawn over it.
function large(el) {
  const r = el.getBoundingClientRect();
  return r.width >= 0.9 * document.documentElement.clientWidth && r.height >= 0.6 * window.innerHeight;
}

// A page column or an app's surface: as tall as most of the window
// (COLUMN_TALL) and down to its bottom (COLUMN_GAP), though narrower, or
// a band across the window's width, though low (a site's second menu
// row), in
// a plain colour (at most COLUMN_CHROMA of chroma: not a coloured band)
// on the page's side (darker than COLUMN_DARK on a dark page, lighter
// than COLUMN_LIGHT on a light one), with no picture filling it (a
// background image, a player, a map: COLUMN_MEDIA over half its visible
// part). The cards and panels laid on it keep their colours. It keeps
// the mark while it stays that tall or wide (tall, wide), as large()
// layers do.
const COLUMN_TALL = 0.75;
const COLUMN_GAP = 0.05;
const COLUMN_CHROMA = 0.1;
const COLUMN_DARK = 0.05;
const COLUMN_LIGHT = 0.6;
const COLUMN_MEDIA = "video, canvas, iframe, embed, object";

function tall(el) {
  return el.getBoundingClientRect().height >= COLUMN_TALL * window.innerHeight;
}

function wide(el) {
  return el.getBoundingClientRect().width >= 0.9 * document.documentElement.clientWidth;
}

// The part of a box inside the window, in px².
function seen(r, w, h) {
  return Math.max(0, Math.min(r.right, w) - Math.max(r.left, 0))
    * Math.max(0, Math.min(r.bottom, h) - Math.max(r.top, 0));
}

function column(el, color) {
  const h = window.innerHeight;
  const r = el.getBoundingClientRect();
  // a sticky band is a bar once stuck (markBars), solid until then
  const band = wide(el) && getComputedStyle(el).position !== "sticky";
  return (band || (tall(el) && r.bottom >= (1 - COLUMN_GAP) * h)) && plain(el, color);
}

// A plain colour on the page's side (COLUMN_CHROMA, COLUMN_DARK,
// COLUMN_LIGHT), no picture filling the element (COLUMN_MEDIA), outside
// anything fixed.
function plain(el, color) {
  const w = document.documentElement.clientWidth, h = window.innerHeight;
  const r = el.getBoundingClientRect();
  if (!toned(color) || getComputedStyle(el).backgroundImage !== "none")
    return false;
  // a fixed side panel is the window's bar (markBars), not the page's
  for (let e = el; e && e !== document.body; e = up(e))
    if (getComputedStyle(e).position === "fixed")
      return false;
  const area = seen(r, w, h);
  for (const media of el.querySelectorAll(COLUMN_MEDIA))
    if (seen(media.getBoundingClientRect(), w, h) >= 0.5 * area)
      return false;
  return true;
}

// A plain colour on the page's side: at most COLUMN_CHROMA of chroma,
// darker than COLUMN_DARK on a dark page, lighter than COLUMN_LIGHT on a
// light one.
function toned(color) {
  const m = /^rgba?\(([^)]*)\)/.exec(color);
  if (tone === null || !m)
    return false;
  const c = m[1].split(/[\s,/]+/).slice(0, 3).map(parseFloat);
  const y = luminance(color);
  return (Math.max(...c) - Math.min(...c)) / 255 <= COLUMN_CHROMA
    && (tone === "dark" ? y <= COLUMN_DARK : y >= COLUMN_LIGHT);
}

// The root painted by the tone tint only (the glass of a page whose tone
// is not the theme's: a dark app under a light theme): see-through glass
// of the other mode, not a background of the page's own.
function tinted(root) {
  const measured = root.getAttribute(TONE);
  return measured !== null && (measured === "dark") !== window.matchMedia("(prefers-color-scheme: dark)").matches
    && alpha(getComputedStyle(root).backgroundColor) < SOLID;
}

function markCanvas() {
  const root = document.documentElement;
  if (off !== false || !root || !document.body)
    return;
  const w = root.clientWidth, h = window.innerHeight;
  const clear = (el) => alpha(getComputedStyle(el).backgroundColor) < CLEAR;
  const pinned = (el) => {
    for (let e = el; e && e !== root; e = up(e))
      if (getComputedStyle(e).position === "fixed")
        return true;
    return false;
  };
  const held = (el) => {
    for (let e = el; e && e !== root; e = up(e))
      if (/^(fixed|sticky)$/.test(getComputedStyle(e).position))
        return true;
    return false;
  };
  const glass = (clear(root) || tinted(root)) && clear(document.body);
  glassPage = glass;
  for (const el of marked("[" + CANVAS + "]"))
    if (!glass || (!large(el) && !tall(el) && !wide(el) && el.getAttribute(CANVAS) !== FILL)) {
      el.removeAttribute(CANVAS);
      // its pseudo-element painted it (underPaint); markFills' are on bars
      if (!/^(fixed|sticky)$/.test(getComputedStyle(el).position))
        el.removeAttribute(FILLED);
    }
  if (!glass) {
    for (const el of marked("[" + FILLED + "], [" + UNDER + "]"))
      el.removeAttribute(FILLED), el.removeAttribute(UNDER);
    unfade();
    pageColors.clear();
    return;
  }
  hideBackdrops();
  const layer = (el, color) => {
    pageColors.add(color);
    layerColors.set(el, color);
    mark(el, CANVAS);
  };
  // a see-through element painted by a pseudo-element of its own
  // (underPaint): a layer, that pseudo-element see-through (FILLED)
  const painter = (el) => {
    if (!(large(el) || wide(el) || tall(el)) || pinned(el))
      return false;
    const paint = underPaint(el);
    if (!paint || !(large(el) || column(el, paint.color)))
      return false;
    layer(el, paint.color);
    const had = el.getAttribute(FILLED) || "";
    if (!had.includes(paint.pseudo))
      el.setAttribute(FILLED, (had + " " + paint.pseudo).trim());
    return true;
  };
  // the see-through ancestors of a layer painted that way: over the layer
  // in the stack, never reached by the walk the layer ends (Home
  // Assistant's view background at a negative z-index, under its panel
  // painting the page by a fixed ::before)
  const under = (el) => {
    for (let p = up(el); p && p !== root && p !== document.body && clear(p); p = up(p))
      if (!p.hasAttribute(CANVAS))
        painter(p);
  };
  const found = (stack, n, el) => {
    under(el);
    sections(stack, n - 1, el);
  };
  const seen = new Set([root, document.body]);
  const rows = Array.from({length: GRID}, (_, j) => (j + 0.5) * h / GRID).concat(h - GRID_EDGE);
  if (tone === "light" && !darkened)
    rows.push(GRID_EDGE);
  for (let i = 0; i < GRID; i++) {
    for (let j = 0; j < rows.length; j++) {
      const at = stackAt((i + 0.5) * w / GRID, rows[j]);
      const stack = j < GRID ? at : at.filter((el) => !held(el));
      const below = [];
      for (let n = stack.length - 1; n >= 0; n--) {
        const el = stack[n];
        if (el === root || el === document.body)
          continue;
        // a surface of the site's own the text on it was drawn for (kept)
        if (el.hasAttribute(KEPT))
          break;
        if (el.hasAttribute(CANVAS)) {
          if (layerColors.has(el))
            pageColors.add(layerColors.get(el));
          found(stack, n, el);
          break;
        }
        if (clear(el)) {
          if (painter(el)) {
            found(stack, n, el);
            break;
          }
          below.push(el);
          continue;
        }
        // a fixed layer over the page's own content: a dialog, a cookie
        // banner, never the page's background
        if (below.some((b) => !holds(b, el)) && pinned(el))
          break;
        const color = getComputedStyle(el).backgroundColor;
        if (alpha(color) >= SOLID && (large(el) || column(el, color))) {
          layer(el, color);
          found(stack, n, el);
        }
        break;
      }
      if (!darkened)
        continue;
      for (const el of stack) {
        if (seen.has(el))
          continue;
        seen.add(el);
        if (el.hasAttribute(CANVAS) || !large(el))
          continue;
        if (getComputedStyle(el).position !== "fixed" && !clear(el))
          mark(el, CANVAS);
      }
    }
  }
}

// A backdrop drawn in a canvas: one that takes no pointer events (a
// decoration, nothing to play with), at least BACKDROP_SIZE of the window
// wide and high, its pixels stretched BACKDROP_STRETCH times or more
// each way (a wash of colour, a blur, not a picture). YouTube's ambient
// mode is one: a canvas of about 110x75 pixels, scaled over the header,
// the player and the video's details, fading in to an opaque #0f0f0f
// over the glass. The walks of markCanvas never meet it (elementsFromPoint
// skips what takes no pointer events), so the canvases are looked at
// here, on a see-through page only (markCanvas calls this): a backdrop
// gets UNDER, hidden, and loses it once it no longer is one. Each canvas
// is watched once (layerSizes, canvasesWatched: observing again would
// report it again, a pass each frame): one shown later, or grown, is
// judged again.
const BACKDROP_SIZE = 0.5;
const BACKDROP_STRETCH = 4;
let canvasesWatched = new WeakSet();

function canvasBackdrop(canvas) {
  const r = canvas.getBoundingClientRect();
  return canvas.width > 0 && canvas.height > 0
    && r.width >= BACKDROP_SIZE * document.documentElement.clientWidth
    && r.height >= BACKDROP_SIZE * window.innerHeight
    && r.width >= BACKDROP_STRETCH * canvas.width && r.height >= BACKDROP_STRETCH * canvas.height
    && getComputedStyle(canvas).pointerEvents === "none";
}

function hideBackdrops() {
  for (const canvas of everywhere("canvas")) {
    if (!canvasesWatched.has(canvas)) {
      canvasesWatched.add(canvas);
      layerSizes.observe(canvas);
    }
    if (canvasBackdrop(canvas))
      canvas.setAttribute(UNDER, "");
    else if (canvas.hasAttribute(UNDER))
      canvas.removeAttribute(UNDER);
  }
}

// The other pseudo-element of a row painted by one (fillBar), empty and
// see-through, laid under it (a lower z-index) and casting a shadow (SRF's
// sub-navigation, its wrapper's ::after): that shadow showed only past the
// row's paint, a seam across the veil once that paint is see-through. It
// is FILLED too, its shadow taken off with its background.
function shadowUnder(el, pseudo) {
  const other = pseudo === "before" ? "after" : "before";
  const top = getComputedStyle(el, "::" + pseudo), style = getComputedStyle(el, "::" + other);
  const z = (s) => parseInt(s.zIndex, 10) || 0;
  return style.content === "\"\"" && style.display !== "none" && style.boxShadow !== "none"
    && alpha(style.backgroundColor) < CLEAR && z(style) < z(top) ? other : null;
}

// A see-through layer painted by an empty ::before or ::after of its own
// covering it (FILL_COVER) in an opaque plain colour (Home Assistant's
// panel, MeteoSuisse's header band): {pseudo, color}, or null. Marked, it
// is a layer of the page's background, its pseudo-element see-through
// (FILLED).
function underPaint(el) {
  const r = el.getBoundingClientRect();
  for (const pseudo of PSEUDOS) {
    const style = getComputedStyle(el, "::" + pseudo);
    if (style.content !== "\"\"" || style.display === "none" || style.backgroundImage !== "none"
        || alpha(style.backgroundColor) < SOLID)
      continue;
    if (clipArea(style) >= FILL_COVER * r.width * r.height)
      return {pseudo, color: style.backgroundColor};
  }
  return null;
}

// Sections laid on a layer of the page's background (`layer`, below
// stack[n], the topmost element first): up from it, an element at least
// SECTION_WIDE as wide as the window, or edge to edge across a narrower
// layer (a page's column; not a panel inset on an app's surface), or a
// page column of its own near the page's colour itself (column: a
// shop's drawer down the page, beside the feed, holding a sticky list;
// not a card of the tone's colour on a hidden layer), in the
// flow (not fixed nor sticky: a bar, a dialog), painting a colour near
// one of the page's (pageColors, BAR_NEAR), or a linear gradient of it
// (fade), is one more layer of that background, below the first screen
// too (markCanvas runs on scroll): CANVAS, its gradient see-through where
// it painted the page's colour (FADE): 1Password's bands in
// rgb(29, 29, 33) on its rgb(18, 20, 22) page, the solid top of its hero.
// Their colours are not added to the page's: a band near a band near the
// page is a card. The way up ends at the first element painting anything
// else (a white island, a blue band, a card).
const SECTION_WIDE = 0.9;
const SECTION_EDGE = 1;

function sections(stack, n, layer) {
  const box = layer.getBoundingClientRect();
  const w = SECTION_WIDE * document.documentElement.clientWidth;
  const own = layerColors.get(layer);
  const hidden = own !== undefined && !toned(own);
  const ours = (color) => pageColor(color) || (hidden && toned(color));
  for (; n >= 0; n--) {
    const el = stack[n];
    if (el.hasAttribute(KEPT))
      break;
    const style = getComputedStyle(el);
    const color = style.backgroundColor;
    const bare = style.backgroundImage === "none";
    if (alpha(color) < CLEAR && bare)
      continue;
    const gradient = !bare && (el.hasAttribute(FADE) || fades(style, ours));
    const page = alpha(color) < CLEAR || (alpha(color) >= SOLID && ours(color));
    if (!page || !(bare || gradient) || !(spans(el.getBoundingClientRect(), box, w) || (pageColor(color) && column(el, color)))
        || style.position === "fixed" || style.position === "sticky")
      break;
    if (gradient)
      fade(el, style, ours);
    if (alpha(color) >= CLEAR)
      mark(el, CANVAS);
  }
}

function spans(r, box, w) {
  return r.width >= w || (r.left <= box.left + SECTION_EDGE && r.right >= box.right - SECTION_EDGE);
}

function pageColor(color) {
  return [...pageColors].some((c) => near(c, color));
}

// A linear gradient of the page's colour: a background image of linear
// gradients only, each sized to fill the box (COVERS: not a line drawn
// with one, such as a link's underline in its text colour), one of their
// colours at least near one of the page's (pageColor). It gets FADE, the same gradient with the page's colours
// see-through in FADE_IMAGE (none when nothing else is left), inline: the
// glass styles paint it instead. Taken off with the page's layers.
const LINEAR = /^(repeating-)?linear-gradient\(/;
const PAINT = /rgba?\([^)]*\)/g;
const COVERS = /^(auto|cover|100%)( (auto|100%))?$/;

function fades(style, ours = pageColor) {
  const image = style.backgroundImage;
  return split(image).every((part) => LINEAR.test(part)) && split(style.backgroundSize).every((s) => COVERS.test(s))
    && (image.match(PAINT) || []).some(ours);
}

function fade(el, style, ours = pageColor) {
  if (el.hasAttribute(FADE) || !fades(style, ours))
    return;
  el.style.setProperty(FADE_IMAGE, faded(style.backgroundImage, ours));
  el.setAttribute(FADE, "");
}

// A gradient with the page's colours see-through, none when nothing else
// is left.
function faded(image, ours) {
  const left = image.replace(PAINT, (c) => ours(c) ? "transparent" : c);
  return (left.match(PAINT) || []).some((c) => alpha(c) > 0) ? left : "none";
}

// A fade drawn by an empty ::before or ::after over text (a list fading
// out into the page's white at its foot, under its last item: Le Figaro's
// news flash): a linear gradient of the page's colour (fades), drawn for
// a page now glass, where it paints a band of that colour. The text near
// the window (markInk) is followed up to the page's layer (CANVAS) or a
// bar, each element once per pass (`seen`): a pseudo-element that fades
// is named in FADE_PSEUDO, its gradient see-through where it painted the
// page's colour in FADE_IMAGE and its name (--browserglass-fade-after),
// inline: the glass styles paint it instead. Taken off with the page's
// layers (unfade).
function fadePseudos(el, seen) {
  if (!pageColors.size)
    return;
  for (let p = el; p && p !== document.body && p !== document.documentElement && !seen.has(p); p = up(p)) {
    seen.add(p);
    const had = p.getAttribute(FADE_PSEUDO) || "";
    for (const pseudo of PSEUDOS) {
      const style = getComputedStyle(p, "::" + pseudo);
      if (had.includes(pseudo) || style.content === "none" || style.display === "none" || !fades(style))
        continue;
      p.style.setProperty(FADE_IMAGE + "-" + pseudo, faded(style.backgroundImage, pageColor));
      p.setAttribute(FADE_PSEUDO, ((p.getAttribute(FADE_PSEUDO) || "") + " " + pseudo).trim());
    }
    if (p.hasAttribute(CANVAS) || p.hasAttribute(BAR))
      break;
  }
}

function unfade() {
  for (const el of marked("[" + FADE + "]")) {
    el.removeAttribute(FADE);
    el.style.removeProperty(FADE_IMAGE);
  }
  for (const el of marked("[" + FADE_PSEUDO + "]")) {
    el.removeAttribute(FADE_PSEUDO);
    for (const pseudo of PSEUDOS)
      el.style.removeProperty(FADE_IMAGE + "-" + pseudo);
  }
}

// Navigation bars: fixed or stuck along an edge of the window, a header or
// a bottom bar (most of its width, short, touching the top or the bottom)
// or a sidebar (most of its height, narrow, touching the left or the
// right), that paints a background of its own, or a see-through one with
// content of the page under it (a header over the posters it was scrolled
// past: its text on theirs). Under points along the four edges, the
// first such element gets BAR: one look on every site. A row stuck right
// under a header already marked (or right above a bottom bar), as wide and
// as short, joins the stack: points along that bar's other edge find it,
// and it gets BAR too (SRF's sub-navigation under its masthead, one veil
// down both rows rather than an opaque band). A bar laid in the
// flow of a page that does not scroll is left alone: in a web app (a chat,
// a mail client) that is as often the message box or a footer line, whose
// shape the site draws itself, as a navigation bar. A strip thinner than
// BAR_MIN on its short side (the marks of a find in the page down the
// scrollbar, a progress line) holds no navigation: no bar. A header
// across a page column (a layer of the page's background, CANVAS)
// rather than the window, the feed's own sticky title row, is one too;
// a bar's background may be painted by a child that covers it
// (FILL_COVER: the layout box inside a sticky header, or an empty layer
// behind its content, absolute, inset 0, at a negative z-index), one
// shown (not a drawer's scrim at opacity 0), even once that child is
// filled (FILL, markFills: the page's colour, now glass, as it was
// marked before the header stuck), or by a row of it in the page's
// colour (pageRow: a shop's header stuck at the top from load, its first
// row painted, the nav row below see-through; not a notice of a colour of
// its own).
const EDGE = 2;
const BAR_MIN = 24;
const OWN_BG = 0.5;
// The bar's backdrop-filter refers to it (url(#VEIL)); without it, the
// bar gets no blur at all, hence its check before every pass. Two cheap
// steps on the GPU after the blur: a flood of the glass's colour (GLASS)
// at VEIL_FLOOD, and the blurred backdrop over it.
const VEIL = "browserglass-veil";
const VEIL_FLOOD = "0.9";
const SVG_NS = "http://www.w3.org/2000/svg";

function veil(root) {
  if ((root instanceof ShadowRoot ? root : document).getElementById(VEIL))
    return;
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("style", "position:absolute!important;width:0!important;height:0!important;overflow:hidden!important");
  const filter = document.createElementNS(SVG_NS, "filter");
  filter.id = VEIL;
  filter.setAttribute("color-interpolation-filters", "sRGB");
  const flood = document.createElementNS(SVG_NS, "feFlood");
  flood.setAttribute("style", "flood-color:var(" + GLASS + ",transparent)");
  flood.setAttribute("flood-opacity", VEIL_FLOOD);
  flood.setAttribute("result", "glass");
  const merge = document.createElementNS(SVG_NS, "feMerge");
  for (const input of ["glass", "SourceGraphic"]) {
    const node = document.createElementNS(SVG_NS, "feMergeNode");
    node.setAttribute("in", input);
    merge.appendChild(node);
  }
  filter.append(flood, merge);
  svg.appendChild(filter);
  root.appendChild(svg);
}

// Whether page content lies under a see-through bar: along OVER_LINES
// lines across its height (a tall header whose top row is a notice of its
// own, its links in the row below, over the content), an element below it
// that is neither its own (a row of it glass too, CANVAS: a band across
// the window before it stuck), one of its ancestors, a layer of the
// page's background (CANVAS) nor a wrapper the size of the window. Runs
// on scroll (layers) only while such a bar is still unmarked: at most
// GRID * OVER_LINES hit tests per bar.
const OVER_LINES = 3;

function over(bar, w, h) {
  const r = bar.getBoundingClientRect();
  for (let j = 0; j < OVER_LINES; j++) {
    const y = Math.min(Math.max(r.top + (j + 0.5) * r.height / OVER_LINES, 0), h - 1);
    for (let i = 0; i < GRID; i++) {
      for (const el of stackAt(r.left + (i + 0.5) * r.width / GRID, y)) {
        if (el === document.documentElement || el === document.body)
          break;
        if (holds(bar, el))
          continue;
        if (el.hasAttribute(CANVAS))
          break;
        if (holds(el, bar))
          continue;
        const e = el.getBoundingClientRect();
        if (e.width >= 0.9 * w && e.height >= 0.6 * h)
          continue;
        return true;
      }
    }
  }
  return false;
}

function markBars() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  veil(root);
  const w = root.clientWidth, h = window.innerHeight;
  // as wide as the window, or as the page column it stays in
  const across = (el, r) => {
    if (r.width >= 0.6 * w)
      return true;
    const page = outer(el, "[" + CANVAS + "]");
    return !!page && r.width >= 0.9 * page.getBoundingClientRect().width;
  };
  // the boxes of the bars marked: a row against one of them, held there
  // (its top or bottom offset; not a sticky row the flow put there before
  // it sticks elsewhere), is stacked
  const rows = [];
  const stacked = (el, r) => {
    const style = getComputedStyle(el);
    return rows.some((b) => (Math.abs(r.top - b.bottom) <= EDGE && Math.abs(parseFloat(style.top) - r.top) <= EDGE)
      || (Math.abs(r.bottom - b.top) <= EDGE && Math.abs(parseFloat(style.bottom) - (h - r.bottom)) <= EDGE));
  };
  const along = (el) => {
    const r = el.getBoundingClientRect();
    return Math.min(r.width, r.height) >= BAR_MIN
      && ((across(el, r) && r.height <= 0.35 * h && (r.top <= EDGE || r.bottom >= h - EDGE || stacked(el, r)))
        || (r.height >= 0.6 * h && r.width <= 0.4 * w && (r.left <= EDGE || r.right >= w - EDGE)));
  };
  const backed = (el) => {
    if (alpha(getComputedStyle(el).backgroundColor) >= OWN_BG)
      return true;
    const r = el.getBoundingClientRect();
    for (const kid of layered(el)) {
      const k = kid.getBoundingClientRect();
      // a scrim faded out (opacity 0, a drawer's) paints nothing
      if (k.width * k.height >= FILL_COVER * r.width * r.height && (kid.hasAttribute(UNDER)
          || ((kid.getAttribute(CANVAS) === FILL || alpha(getComputedStyle(kid).backgroundColor) >= OWN_BG)
            && kid.checkVisibility({visibilityProperty: true, opacityProperty: true}))))
        return true;
    }
    return pageRow(el);
  };
  const pinned = (el) => {
    const position = getComputedStyle(el).position;
    return position === "fixed" || position === "sticky";
  };
  const probe = (px, py) => {
    for (const el of stackAt(px, py)) {
      if (el === root || el === document.body)
        break;
      if (!along(el) || !pinned(el))
        continue;
      if (!el.hasAttribute(BAR) && (backed(el) || over(el, w, h))) {
        barColors.set(el, new Set([...(barColors.get(el) || []), ...painted(el)]));
        mark(el, BAR);
        rows.push(el.getBoundingClientRect());
      }
      break;
    }
  };
  // a marked bar shows the veil, not its own background: only its place
  // is checked again
  const kept = marked("[" + BAR + "]");
  rows.push(...kept.map((el) => el.getBoundingClientRect()));
  for (const el of kept)
    if (!pinned(el) || !along(el))
      el.removeAttribute(BAR);
  rows.length = 0;
  rows.push(...marked("[" + BAR + "]").map((el) => el.getBoundingClientRect()));
  for (let i = 0; i < GRID; i++) {
    const x = (i + 0.5) * w / GRID, y = (i + 0.5) * h / GRID;
    for (const [px, py] of [[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y]])
      probe(px, py);
  }
  // the rows stacked against a bar, then against those (the list grows)
  for (let k = 0; k < rows.length; k++)
    for (let i = 0; i < GRID; i++) {
      const x = rows[k].left + (i + 0.5) * rows[k].width / GRID;
      for (const py of [rows[k].bottom + EDGE, rows[k].top - EDGE])
        if (py > EDGE && py < h - EDGE)
          probe(x, py);
    }
  // one veil per bar: an inner one marked before its outer one was in place
  const bars = marked("[" + BAR + "]");
  for (const el of bars)
    if (outer(el, "[" + BAR + "]"))
      el.removeAttribute(BAR);
  // a bar in a shadow tree refers to a veil of its own tree
  for (const el of bars)
    if (el.getRootNode() !== document && el.hasAttribute(BAR))
      veil(el.getRootNode());
  if (glassPage)
    for (const el of bars)
      if (el.hasAttribute(BAR))
        fillBar(el);
}

// The rows of a bar in its own colour: a marked bar shows the veil, not
// its background, but a child painting that colour over BAR_SHARE of it,
// or as tall as it (a cell: ARTE's language menu), or as wide as it (a
// block of links at the top of a side column: Docker's docs), inside it
// (not a menu dropping out of it), stays an opaque band over the veil
// (MDN's row of links above the breadcrumbs, a list of links across the
// middle of ARTE's), and so do the parts of such a row in that colour,
// small as they are (each link of ARTE's list), if shown: a menu hidden
// in the row (MDN's panels, 0 by 0 until opened) keeps its colour, and so
// does a field's box or a control (FIELD_BOXES, or holding one: a search
// field, a toggle's track), its own box kept on the veil. Its colour is
// that of the bar, read before the veil (painted: its own, or that of the
// layer backing it), or the page's (pageColors), within BAR_NEAR on each
// channel (MDN's rows, two dark greys 11 apart): the child gets CANVAS
// (FILL), see-through. A row painted by an empty pseudo-element of its
// own (underPaint: SRF's sub-navigation, its wrapper's ::before at a
// negative z-index) gets FILLED instead, that pseudo-element see-through.
// A layer laid behind the bar's content (a negative z-index) that holds
// text and that a sibling covers (underlay) hid that text by design:
// ARTE's skip links, under a header the glass styles clear. Cleared, it would show them over the bar's links: it gets UNDER
// instead, hidden until the focus enters it (the site brings it forward,
// opaque, to show a skip link). Only on a see-through page (glassPage),
// as the fills of markFills.
const BAR_SHARE = 0.3;
const BAR_NEAR = 16;
const FIELD_BOXES = "input:not([type=hidden]), button, [role=button], select, textarea";
const barColors = new WeakMap();
let glassPage = false;

// The colours a bar paints itself: its own, that of a child covering it,
// or of an empty pseudo-element covering either (paintOf).
function painted(bar) {
  const colors = [];
  const r = bar.getBoundingClientRect();
  for (const el of [bar, ...layered(bar)]) {
    const k = el.getBoundingClientRect();
    const paint = paintOf(el);
    if (paint && k.width * k.height >= FILL_COVER * r.width * r.height)
      colors.push(paint.color);
  }
  return colors;
}

// What paints an element: its own opaque colour ({pseudo: null, color}),
// or an empty ::before or ::after of its own covering it (underPaint:
// SRF's sub-navigation, painted by its wrapper's ::before at z-index -1),
// or null.
function paintOf(el) {
  const color = getComputedStyle(el).backgroundColor;
  return alpha(color) >= SOLID ? {pseudo: null, color} : underPaint(el);
}

// The sRGB channels (0-255) of a computed colour, null if unknown. The
// computed value keeps the page's colour space (oklch() design tokens):
// one other than rgb() is read through a canvas, whose fill comes back in
// sRGB (#rrggbb, or rgba() when see-through).
let palette = null;

function channels(color) {
  let m = /^rgba?\(([^)]*)\)/.exec(color);
  if (m)
    return m[1].split(/[\s,/]+/).slice(0, 3).map(parseFloat);
  if (!/^[a-z-]+\(/.test(color))
    return null;
  palette = palette || document.createElement("canvas").getContext("2d");
  palette.fillStyle = "rgba(0, 0, 0, 0)";
  palette.fillStyle = color;
  const fill = palette.fillStyle;
  if ((m = /^#(..)(..)(..)$/.exec(fill)))
    return m.slice(1).map((h) => parseInt(h, 16));
  return fill === "rgba(0, 0, 0, 0)" ? null : channels(fill);
}

function near(a, b) {
  const x = channels(a), y = channels(b);
  return !!x && !!y && x.every((c, i) => Math.abs(c - y[i]) <= BAR_NEAR);
}

function barRow(r, box) {
  return r.width * r.height >= BAR_SHARE * box.width * box.height;
}

function within(r, box) {
  return r.top >= box.top - EDGE && r.bottom <= box.bottom + EDGE
    && r.left >= box.left - EDGE && r.right <= box.right + EDGE;
}

// Whether a row of a see-through bar (BAR_SHARE of it, inside it, shown)
// paints the page's colour, or did before it was filled.
function pageRow(bar) {
  const box = bar.getBoundingClientRect();
  const kids = inside(bar);
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    const r = el.getBoundingClientRect();
    if (NOT_FILLS.has(el.localName) || !barRow(r, box) || !within(r, box))
      continue;
    const color = getComputedStyle(el).backgroundColor;
    if ((el.getAttribute(CANVAS) === FILL || (alpha(color) >= SOLID && pageColor(color)))
        && el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      return true;
  }
  return false;
}

function underlay(el) {
  const style = getComputedStyle(el);
  if (style.position === "static" || !(parseInt(style.zIndex, 10) < 0) || !el.textContent.trim())
    return false;
  const r = el.getBoundingClientRect();
  for (const sib of (el.parentElement || el.parentNode).children) {
    const s = sib.getBoundingClientRect();
    if (sib !== el && s.width * s.height >= FILL_COVER * r.width * r.height)
      return true;
  }
  return false;
}

function fillBar(bar) {
  const colors = [...pageColors, ...(barColors.get(bar) || [])];
  if (!colors.length)
    return;
  const box = bar.getBoundingClientRect();
  const kids = inside(bar);
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    if (el.hasAttribute(CANVAS) || el.closest("[" + UNDER + "]") || NOT_FILLS.has(el.localName))
      continue;
    const r = el.getBoundingClientRect();
    const band = barRow(r, box) || r.height >= FILL_COVER * box.height || r.width >= FILL_COVER * box.width;
    // a row painted by a pseudo-element of its own: that one see-through
    const color = getComputedStyle(el).backgroundColor;
    const paint = alpha(color) >= SOLID ? {pseudo: null, color} : band ? underPaint(el) : null;
    if (!paint || !colors.some((c) => near(c, paint.color)))
      continue;
    // a part of a filled row, unless a field's box or a control
    const row = band
      || (holds(bar, outer(el, "[" + CANVAS + "]")) && !el.matches(FIELD_BOXES) && !el.querySelector(FIELD_BOXES));
    if (!row || !r.width || !r.height || !within(r, box)
        || !el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      continue;
    const had = el.getAttribute(FILLED) || "";
    if (paint.pseudo) {
      const names = [paint.pseudo, shadowUnder(el, paint.pseudo)].filter((p) => p && !had.includes(p));
      if (names.length)
        el.setAttribute(FILLED, (had + " " + names.join(" ")).trim());
    } else if (underlay(el))
      el.setAttribute(UNDER, "");
    else
      el.setAttribute(CANVAS, FILL);
  }
}

// Blocks Dark Reader darkens: the white cards, panels and strips of a light
// page turn into opaque near-black panels on the glass. On a page it
// darkens, the text near the window is followed up to the page's
// background (CANVAS, the body): the elements on the way that paint an
// opaque plain colour on the page's side (plain: low chroma, dark, no
// picture, no player over half of it) and do not float (floats: fixed,
// sticky, a popup) are its blocks; any other element painting something
// (a coloured button, a brand block, a picture) ends the way up, keeping
// its colours. A block as wide as the window or down a page column
// (column) is a layer of the page's background: CANVAS, as markCanvas
// marks them. Of the others, the outermost gets BLOCK "veil", a light
// veil of the glass's colour (lighter than a bar's), its border kept; the
// blocks inside it BLOCK "glass", see-through: veils do not stack, but a
// button or a field (FIELDS) keeps a veil of its own. An outermost block
// laid over a picture (overPicture: a teaser's caption card over the foot
// of its photo) gets BLOCK "solid" instead: no rule, Dark Reader's opaque
// fill stays, since its text was drawn on an opaque card, not on a photo.
// An empty ::before or ::after of a block painting its colour (a band
// along the top of a card: bands) is named in BLOCK too, and cleared, or
// it stays an opaque dark band on the veil. The
// marks stay while Dark Reader darkens the page (a block marked reads as
// see-through: nothing to measure again) and go with it. The text is
// that of markInk (shownText).
const VEILED = "veil";
const SEE_THROUGH = "glass";
const OPAQUE = "solid";
const FIELDS = "button, [role=button], select, textarea";

function markBlocks(near) {
  if (!darkened)
    return;
  const kinds = new Map(), floating = new Map();
  // fixed, sticky, or a popup (absolute over the page, a z-index set),
  // itself or an ancestor
  const floats = (el) => {
    if (!el || el === document.body)
      return false;
    if (!floating.has(el)) {
      const style = getComputedStyle(el);
      floating.set(el, style.position === "fixed" || style.position === "sticky"
        || (style.position === "absolute" && style.zIndex !== "auto") || floats(up(el)));
    }
    return floating.get(el);
  };
  // true for a block, null for an element that paints nothing, false for
  // one that ends the way up
  const fill = (el) => {
    const style = getComputedStyle(el);
    const color = style.backgroundColor;
    if (alpha(color) < CLEAR && style.backgroundImage === "none")
      return null;
    if (MEDIA.has(el.localName) || alpha(color) < SOLID || floats(el) || !plain(el, color))
      return false;
    if (!column(el, color))
      return true;
    pageColors.add(color);
    mark(el, CANVAS);
    return false;
  };
  const kind = (el) => {
    if (!kinds.has(el))
      kinds.set(el, el.hasAttribute(BLOCK) || (el.hasAttribute(CANVAS) ? false : fill(el)));
    return kinds.get(el);
  };
  const overs = new Map();
  let pictures = null;
  const media = () => pictures || (pictures = everywhere(OVER_MEDIA).filter((m) => {
    const r = m.getBoundingClientRect();
    return near(m) && r.width > ICON_SIDE && r.height > ICON_SIDE;
  }));
  for (const el of shownText(near)) {
    const blocks = [];
    let stop = null;
    for (let p = el; p && p !== document.body; p = up(p)) {
      const value = kind(p);
      if (value === false) {
        stop = p;
        break;
      }
      if (value)
        blocks.push(p);
    }
    blocks.forEach((b, j) => {
      const outermost = j === blocks.length - 1 && !b.matches(FIELDS);
      if (outermost && !overs.has(b))
        overs.set(b, overPicture(b, stop, media));
      // a button keeps a veil of its own, on its card's
      const role = outermost ? (overs.get(b) ? OPAQUE : VEILED) : b.matches(FIELDS) ? VEILED : SEE_THROUGH;
      const value = [role, ...bands(b)].join(" ");
      if (b.getAttribute(BLOCK) !== value)
        b.setAttribute(BLOCK, value);
    });
  }
}

// Whether a block lies over a picture: the element that ends its way up
// paints a background picture sized to its box (as onPicture reads one: a
// hero's photo), or an <img> or a <video> near the window, larger than an
// icon (ICON_SIDE) and not inside it, lies under OVER_SHARE of it at least
// (media), by the part of it shown (shownBox): what its ancestors clip
// (overflow) is not under the block (a cover image cut down to its card,
// its box running over the cards above and below).
const OVER_SHARE = 0.1;
const OVER_MEDIA = "img, video";

function overPicture(block, stop, media) {
  if (stop) {
    const style = getComputedStyle(stop);
    if (/url\(/.test(style.backgroundImage) && /cover|contain/.test(style.backgroundSize))
      return true;
  }
  const r = block.getBoundingClientRect();
  return media().some((m) => !holds(block, m) && overlap(r, shownBox(m)) >= OVER_SHARE * r.width * r.height);
}

function overlap(a, b) {
  return Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left))
    * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
}

// The part of an element's box its ancestors leave shown: each one hiding
// its overflow (along either axis) cuts it to its own box.
function shownBox(el) {
  const r = el.getBoundingClientRect();
  let {left, top, right, bottom} = r;
  for (let p = up(el); p && p !== document.body; p = up(p)) {
    const style = getComputedStyle(p);
    const x = style.overflowX !== "visible", y = style.overflowY !== "visible";
    if (!x && !y)
      continue;
    const box = p.getBoundingClientRect();
    if (x)
      left = Math.max(left, box.left), right = Math.min(right, box.right);
    if (y)
      top = Math.max(top, box.top), bottom = Math.min(bottom, box.bottom);
  }
  return {left, top, right, bottom};
}

// The empty ::before and ::after of a block painting its colour, opaque,
// no picture (a white band along the top of a card, darkened with it),
// read once: a block marked keeps those it named (its colour is the
// veil's then, and theirs cleared).
function bands(block) {
  const had = block.getAttribute(BLOCK);
  if (had !== null)
    return PSEUDOS.filter((p) => had.split(" ").includes(p));
  const color = getComputedStyle(block).backgroundColor;
  return PSEUDOS.filter((p) => {
    const style = getComputedStyle(block, "::" + p);
    return style.content === "\"\"" && style.display !== "none" && style.backgroundImage === "none"
      && alpha(style.backgroundColor) >= SOLID && near(style.backgroundColor, color);
  });
}

// Link cards a site paints itself: on a see-through page Dark Reader
// leaves alone (the site's own dark theme, or its light one), a row of
// teasers or link cards in an opaque colour sits on the glass as full
// panels (SRF's teasers, the Docker docs' link cards). A link near the
// window at least CARD_SIDE px each way, not a layer of the page (wide,
// large), painting an opaque plain colour on the page's side (plain), not
// in anything floating over the page (afloat), and one of CARD_ROW links
// at least in that colour (a row of cards, not a lone panel: YouTube's
// notice card keeps its own fill) gets BLOCK "veil" as Dark Reader's
// darkened cards do: the surface of the page's tone at
// BLOCK_VEIL_OPACITY, its border kept. A box inside it in its colour gets
// "glass" (veils do not stack), unless it holds a picture (CARD_MEDIA: a
// photo's frame keeps its colour behind it). At most BRAND_ELEMENTS links
// and FILL_NODES boxes in a card are looked at. The marks are judged
// again once the tone changes (a site following the system's scheme
// repaints its cards), and go when the page is darkened or not glass.
const CARD_SIDE = 120;
const CARD_ROW = 2;
const CARD_MEDIA = "img, picture, video, canvas";
let cards = new Map(), cardTone = null;

function markCards(near) {
  const on = !darkened && glassPage && tone !== null;
  if (!on || tone !== cardTone) {
    for (const el of cards.keys())
      el.removeAttribute(BLOCK);
    cards = new Map();
    cardTone = tone;
  }
  if (!on)
    return;
  const rows = new Map();
  for (const color of cards.values())
    if (color !== null)
      rows.set(color, (rows.get(color) || 0) + 1);
  const found = [];
  const links = everywhere("a[href]");
  for (let i = 0; i < links.length && i < BRAND_ELEMENTS; i++) {
    const el = links[i];
    if (cards.has(el) || el.hasAttribute(BLOCK) || el.hasAttribute(CANVAS) || !near(el))
      continue;
    const r = el.getBoundingClientRect();
    if (r.width < CARD_SIDE || r.height < CARD_SIDE || wide(el) || large(el))
      continue;
    const color = getComputedStyle(el).backgroundColor;
    if (alpha(color) < SOLID || !plain(el, color) || afloat(el))
      continue;
    found.push([el, color]);
    rows.set(color, (rows.get(color) || 0) + 1);
  }
  for (const [el, color] of found)
    if (rows.get(color) >= CARD_ROW)
      veilCard(el, color);
}

function veilCard(card, color) {
  cards.set(card, color);
  card.setAttribute(BLOCK, VEILED);
  const boxes = card.getElementsByTagName("*");
  for (let i = 0; i < boxes.length && i < FILL_NODES; i++) {
    const el = boxes[i];
    if (NOT_FILLS.has(el.localName) || el.hasAttribute(BLOCK) || el.querySelector(CARD_MEDIA)
        || getComputedStyle(el).backgroundColor !== color)
      continue;
    cards.set(el, null);
    el.setAttribute(BLOCK, SEE_THROUGH);
  }
}

// Whether an element floats over the page: fixed, sticky, or a popup
// (absolute over the page, a z-index set), itself or an ancestor.
function afloat(el) {
  for (let p = el; p && p !== document.body; p = up(p)) {
    const style = getComputedStyle(p);
    if (style.position === "fixed" || style.position === "sticky"
        || (style.position === "absolute" && style.zIndex !== "auto"))
      return true;
  }
  return false;
}

// Text without contrast: with the backgrounds of the page gone (the generic
// style, a site style, Dark Reader), some text is left on a colour close to
// its own, dark text on the dark glass (a notice banner) or light text on
// a light button. The text shown in the window (and a window above and
// below) is checked: the colour behind it is that of the first ancestor
// painting a background of its own, else the root's over the glass
// (GLASS, the tint's colour, set by the glass styles), unknown over a
// picture. Text in a see-through fixed or sticky element (a footer fixed
// over a white page column) is read on what is painted under it there
// (beneath), not on its ancestors: the glass under the footer is not
// what shows. Text whose contrast with it is below INK_RATIO gets INK,
// and grey text (below GLASS_CHROMA) straight on the light glass
// (onGlass) below GLASS_RATIO, a floor for the wallpaper its tint lets
// through (Tailwind's gray-400, drawn for a white page, on the light
// glass over a mid-tone wallpaper; a brand colour, an orange link, and
// a caption on the dark glass keep theirs):
// "dark" or "light": the glass styles give it a readable colour (its own
// kept, inkFrom, for the tone). Its marks are
// taken off before it is checked again, so a page that changes its colours
// (a theme switch) gets them right. At most once per INK_MS. Before that,
// a label of a single line or two (LABEL_H px tall at most, its text
// alone) painting the colour of the page layer it is on (pageColors: a
// white page column made glass, the white behind its tagline) is
// see-through with it (CANVAS, FILL), not a white strip left on the glass.
// Fills in the page's colour inside what stays on screen (a fixed or
// sticky element under the points of markCanvas and markBars): an empty
// element (a scrim that fades the content into the page's colour, often
// with a gradient mask, and that clicks pass through), or the panel that
// covers a bar and paints its background in its place (a sidebar drawn by
// its child), or one as wide as a page layer it lies in (a sticky side
// column made glass, its block of links at the top in its colour: Docker's
// docs). They show the page's colour, now glass: they get CANVAS too
// (FILL), or they stay as dark or light bands over the glass. They lose it
// with the page's layers (markCanvas), not when they shrink. The same for
// an empty ::before or ::after of such an element painting the page's
// colour (a strip under a sticky header's rounded corners, hiding the
// posts scrolled past): FILLED, the pseudo-elements by name. A linear
// gradient of the page's colour on such an element or inside it (a scrim
// fading the page's colour out under a sticky header: MDN's sidebar
// filter) is see-through where it painted that colour (fade).
const FILL_NODES = 400;
const FILL_COVER = 0.9;
const NOT_FILLS = new Set(["img", "video", "canvas", "svg", "iframe", "embed", "object", "picture",
  "input", "textarea", "select", "button", "hr"]);
const PSEUDOS = ["before", "after"];

function pageFill(el, pseudo) {
  const style = getComputedStyle(el, "::" + pseudo);
  return style.content === "\"\"" && style.display !== "none" && pageColors.has(style.backgroundColor);
}

function markFills() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  if (!pageColors.size || !marked("[" + CANVAS + "]:not([" + CANVAS + "=\"" + FILL + "\"])").length)
    return;
  const w = root.clientWidth, h = window.innerHeight;
  const points = [];
  for (let i = 0; i < GRID; i++) {
    const x = (i + 0.5) * w / GRID, y = (i + 0.5) * h / GRID;
    points.push([x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y]);
    for (let j = 0; j < GRID; j++)
      points.push([x, (j + 0.5) * h / GRID]);
  }
  const holders = new Set();
  for (const [x, y] of points)
    for (const el of stackAt(x, y)) {
      if (el === root || el === document.body)
        break;
      const position = getComputedStyle(el).position;
      if (position === "fixed" || position === "sticky")
        holders.add(el);
    }
  for (const holder of holders) {
    const had = holder.getAttribute(FILLED) || "";
    const pseudos = PSEUDOS.filter((p) => !had.includes(p) && pageFill(holder, p));
    if (pseudos.length)
      holder.setAttribute(FILLED, (had + " " + pseudos.join(" ")).trim());
    fade(holder, getComputedStyle(holder));
    const box = holder.getBoundingClientRect();
    const bar = holder.hasAttribute(BAR);
    const layer = holder.getAttribute(CANVAS) === "";
    const kids = inside(holder);
    for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
      const el = kids[i];
      if (NOT_FILLS.has(el.localName))
        continue;
      const style = getComputedStyle(el);
      fade(el, style);
      if (el.hasAttribute(CANVAS) || !pageColors.has(style.backgroundColor))
        continue;
      const r = el.getBoundingClientRect();
      if (!el.firstElementChild && !el.textContent.trim() ? r.width > 0 && r.height > 0
          : (bar && r.width * r.height >= FILL_COVER * box.width * box.height)
            || (layer && r.width >= FILL_COVER * box.width && r.height > 0))
        el.setAttribute(CANVAS, FILL);
    }
  }
}

const INK_RATIO = 2;
const GLASS_RATIO = 3;
const GLASS_CHROMA = 0.15;
const INK_MS = 300;
const INK_NODES = 4000;
const INK_ELEMENTS = 1000;
let inkAt = -Infinity, inkFrame = 0;

// The elements holding text shown near the window, in the page's order:
// at most INK_NODES text nodes with text and INK_ELEMENTS elements near
// the window. The blank nodes between tags, and the text hidden (a closed
// menu of a thousand links) or far away, are skipped without counting
// against the elements: a page that holds them before its content (a
// right-hand column, late in the page's order) still gets it read. The
// text of an open shadow tree is read where its host is (shadows).
function shownText(near) {
  const shown = [], looked = new Set();
  const show = NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT;
  const walkers = [document.createTreeWalker(document.body, show)];
  for (let i = 0; walkers.length && i < INK_NODES && shown.length < INK_ELEMENTS;) {
    const n = walkers[walkers.length - 1].nextNode();
    if (!n) {
      walkers.pop();
      continue;
    }
    if (n.nodeType === Node.ELEMENT_NODE) {
      if (n.shadowRoot) {
        shadows.add(n.shadowRoot);
        walkers.push(document.createTreeWalker(n.shadowRoot, show));
      }
      continue;
    }
    const el = n.parentElement;
    if (!n.data.trim())
      continue;
    i++;
    if (!el || looked.has(el))
      continue;
    looked.add(el);
    if (near(el) && el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      shown.push(el);
  }
  return shown;
}

function contrast(a, b) {
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

// The luminance behind `el`, null when unknown (a picture, a gradient).
// An element's face may be drawn by a layer of its own that covers most
// of it, the element itself see-through: a ::before or ::after, or an
// absolutely positioned child (and that child's covering children), as
// buttons often are. The text over it sits on that face, not on what is
// behind the element. Faces are looked for once per element and pass.
const FACE = 0.8;
const FACE_KIDS = 16;
const FACE_DEPTH = 2;
const MEDIA = new Set(["img", "picture", "video", "canvas", "iframe", "svg", "embed", "object"]);
let faces = new Map();

// Whether a style's background image is a picture: anything but
// gradients drawn as thin lines (THIN px at most across) that do not
// repeat across them, as links are underlined with a gradient 2px high.
const THIN = 4;
const GRADIENT = /^(repeating-)?(linear|radial|conic)-gradient\(/;

function split(value) {
  const parts = [];
  let depth = 0, start = 0;
  for (let i = 0; i < value.length; i++) {
    const c = value[i];
    if (c === "(")
      depth++;
    else if (c === ")")
      depth--;
    else if (c === "," && depth === 0) {
      parts.push(value.slice(start, i).trim());
      start = i + 1;
    }
  }
  parts.push(value.slice(start).trim());
  return parts;
}

function picture(style) {
  if (style.backgroundImage === "none")
    return false;
  const sizes = split(style.backgroundSize), repeats = split(style.backgroundRepeat);
  const thin = (v) => v.endsWith("px") && parseFloat(v) <= THIN;
  return split(style.backgroundImage).some((image, i) => {
    if (!GRADIENT.test(image))
      return true;
    const [w, h = "auto"] = sizes[i % sizes.length].split(/\s+/);
    const r = repeats[i % repeats.length].split(/\s+/);
    const [rx, ry] = r[0] === "repeat-x" ? ["repeat", "no-repeat"]
      : r[0] === "repeat-y" ? ["no-repeat", "repeat"] : [r[0], r[1] || r[0]];
    return !(thin(h) && ry === "no-repeat" || thin(w) && rx === "no-repeat");
  });
}

// What a style paints: a luminance, null for a picture, undefined for
// nothing opaque.
function paints(style) {
  if (picture(style))
    return null;
  if (alpha(style.backgroundColor) >= OWN_BG)
    return luminance(style.backgroundColor);
  return undefined;
}

function covers(r, el) {
  const c = el.getBoundingClientRect();
  return c.width * c.height >= FACE * r.width * r.height;
}

function layerPaints(el, r, depth) {
  const style = getComputedStyle(el);
  if (parseFloat(style.opacity) < CLEAR)
    return undefined;
  if (MEDIA.has(el.localName))
    return null;
  const own = paints(style);
  if (own !== undefined || depth === 0)
    return own;
  for (const kid of el.children)
    if (covers(r, kid)) {
      const value = layerPaints(kid, r, depth - 1);
      if (value !== undefined)
        return value;
    }
  return undefined;
}

function face(p) {
  if (faces.has(p))
    return faces.get(p);
  let value;
  const r = p.getBoundingClientRect();
  if (r.width > 0 && r.height > 0) {
    for (const pseudo of ["::before", "::after"]) {
      const s = getComputedStyle(p, pseudo);
      if (s.content === "none" || s.display === "none" || parseFloat(s.opacity) < CLEAR
          || clipArea(s) < FACE * r.width * r.height)
        continue;
      value = paints(s);
      if (value !== undefined)
        break;
    }
    if (value === undefined && p !== document.body && p.childElementCount <= FACE_KIDS)
      for (const kid of p.children) {
        const position = getComputedStyle(kid).position;
        if ((position === "absolute" || position === "fixed") && covers(r, kid)) {
          value = layerPaints(kid, r, FACE_DEPTH);
          if (value !== undefined)
            break;
        }
      }
  }
  faces.set(p, value);
  return value;
}

// The area a pseudo-element's background colour paints, in px²: its box
// cut to its background-clip, the padding box or the content box (a
// ::before covering a section, its colour clipped by a padding to a band
// across the middle, GitLab's: the heading above it is on the section's
// own background, not on that face, and the band paints no layer).
function clipArea(s) {
  const px = (name) => parseFloat(s[name]) || 0;
  const pad = (a, b) => px("padding" + a) + px("padding" + b);
  const border = (a, b) => px("border" + a + "Width") + px("border" + b + "Width");
  const clip = split(s.backgroundClip).pop();
  const side = (size, a, b) => {
    const content = px(size) - (s.boxSizing === "border-box" ? pad(a, b) + border(a, b) : 0);
    return Math.max(0, content + (clip === "content-box" ? 0 : pad(a, b)) + (clip === "border-box" ? border(a, b) : 0));
  };
  return side("width", "Left", "Right") * side("height", "Top", "Bottom");
}

function clipped(style) {
  return split(style.backgroundClip).includes("text");
}

// The colours a text is drawn with: its fill (-webkit-text-fill-color,
// its colour unless set), or, the fill transparent, the colours of a
// gradient clipped to the text (background-clip: text, a headline's
// highlighted words); none when unknown (a picture clipped to the text).
function inks(style) {
  const fill = style.webkitTextFillColor || style.color;
  if (alpha(fill) >= CLEAR)
    return [fill];
  if (clipped(style) && style.backgroundImage !== "none"
      && split(style.backgroundImage).every((image) => GRADIENT.test(image)))
    return (style.backgroundImage.match(/rgba?\([^)]*\)/g) || []).filter((c) => alpha(c) >= CLEAR);
  return [];
}

function behind(el, follow = true, worst = false) {
  const root = document.documentElement;
  // a background clipped to the text is the text's colour, not behind it
  if (clipped(getComputedStyle(el)))
    el = up(el) || root;
  for (let p = el; p && p !== root; p = up(p)) {
    const style = getComputedStyle(p);
    const own = face(p);
    if (own !== undefined)
      return own;
    if (picture(style))
      return null;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return worst && p.hasAttribute(BAR) ? veiled(style.backgroundColor) : luminance(style.backgroundColor);
    const field = follow && style.position === "absolute" ? fieldUnder(p) : null;
    if (field)
      return behind(field, false, worst);
    const under = follow && (style.position === "fixed" || style.position === "sticky") && !large(p)
      ? beneath(p, el) : null;
    if (under)
      return behind(under, false, worst);
  }
  const style = getComputedStyle(root);
  const glass = luminance(style.getPropertyValue(GLASS).trim());
  const a = alpha(style.backgroundColor);
  const own = a > 0 ? luminance(style.backgroundColor) : null;
  if (glass === null)
    return a >= OWN_BG ? own : null;
  // the browser mixes the root's colour over the glass in sRGB
  return own === null ? glass : linear(a * encoded(own) + (1 - a) * encoded(glass));
}

// The form field a box laid over the page lies on, beside it in its
// parent (a floating label, absolutely positioned over its input: Swiss
// Post's tracking field): the field's box holds its middle, null if
// none. The label is drawn over the field, on that box, not on what
// holds them both (a yellow form Dark Reader turns olive, its input
// near-black: the label was inked dark on that black).
const FIELDS_UNDER = "input:not([type=hidden]):not([type=checkbox]):not([type=radio]), textarea, select";

function fieldUnder(el) {
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  for (const f of el.parentElement ? el.parentElement.children : []) {
    if (f === el || !f.matches(FIELDS_UNDER))
      continue;
    const b = f.getBoundingClientRect();
    if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom)
      return f;
  }
  return null;
}

// The luminance of a bar's dark veil (BAR, the surface at
// NAV_BAR_OPACITY) over the worst of what scrolls under it, white, mixed
// in sRGB (behind with `worst`). A label in a bar reads on the veil alone
// and on this too: a site's mid-grey links, drawn for its white header
// over a light section, are inked light on the dark veil of a dark page.
// A light veil holds dark labels drawn for it: it is read alone.
function veiled(color) {
  const y = luminance(color), a = alpha(color);
  if (y === null || a >= SOLID || y > 0.179)
    return y;
  return linear(a * encoded(y) + (1 - a));
}

// Whether `el` lies in a bar (BAR), shadow hosts included.
function inBar(el) {
  for (let p = el; p; p = up(p))
    if (p.hasAttribute(BAR))
      return true;
  return false;
}

// What is painted under a see-through fixed or sticky layer at the middle
// of `el` (in it): the topmost element there below the layer, not one of
// its ancestors (their background is the walk's next step), null if none
// or out of the window.
function beneath(layer, el) {
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight)
    return null;
  let passed = false;
  for (const e of stackAt(x, y)) {
    if (holds(layer, e))
      passed = true;
    else if (passed)
      return holds(e, layer) ? null : e;
  }
  return null;
}

// A label in the colour of the page layer under it (markInk), in the
// flow of that layer: a box laid over the page (a popup menu) is no label.
const LABEL_H = 48;
const LAID_OVER = new Set(["absolute", "fixed", "sticky"]);

function label(el, style) {
  if (el.hasAttribute(CANVAS) || el.firstElementChild || NOT_FILLS.has(el.localName)
      || LAID_OVER.has(style.position) || alpha(style.backgroundColor) < SOLID || !pageColors.has(style.backgroundColor)
      || el.getBoundingClientRect().height > LABEL_H)
    return false;
  const layer = el.parentElement && el.parentElement.closest("[" + CANVAS + "]");
  return !!layer && layer.getAttribute(CANVAS) !== FILL;
}

// The colour the page gives a text, read before INK changed it (inkFrom).
const inkFrom = new WeakMap();

function ownColor(el) {
  return el.hasAttribute(INK) && inkFrom.has(el) ? inkFrom.get(el) : getComputedStyle(el).color;
}

// A surface the generic style cleared though the text on it was drawn for
// it (a dark section holding white text on a light page, MeteoSuisse's
// forecast): before a text without contrast is inked, its see-through
// ancestors up to the first that paints (not the body) are tried with
// KEPT, which the generic style skips (ownFill). The first showing a
// background colour of its own keeps it, KEPT staying, if every colour of
// the text reads on it opaque; else the text is inked. Not on a darkened
// page: the colours there are Dark Reader's. A surface the add-on marked
// (a page layer, a bar, a block) is the add-on's, but for a page layer
// off the tone's side shorter than the page (that dark section filling
// the window, the lowest layer met): a section of the site's own, kept
// the same way, no layer any more.
const MARKS = [CANVAS, BAR, BLOCK, FILLED];

function kept(el, fgs) {
  if (darkened)
    return false;
  const reads = (fill) => {
    const y = luminance(fill);
    return alpha(fill) >= SOLID && y !== null && fgs.every((fg) => contrast(fg, y) >= INK_RATIO);
  };
  for (let p = up(el); p && p !== document.body && p !== document.documentElement; p = up(p)) {
    if (ownLayer(p)) {
      if (!reads(layerColors.get(p)))
        return false;
      p.removeAttribute(CANVAS);
      pageColors.delete(layerColors.get(p));
      p.setAttribute(KEPT, "");
      return true;
    }
    if (MARKS.some((m) => p.hasAttribute(m)))
      return false;
    const style = getComputedStyle(p);
    if (alpha(style.backgroundColor) >= CLEAR || picture(style) || face(p) !== undefined)
      return false;
    const fill = ownFill(p);
    if (fill === null)
      continue;
    if (!reads(fill))
      return false;
    p.setAttribute(KEPT, "");
    return true;
  }
  return false;
}

function ownLayer(el) {
  const color = layerColors.get(el);
  return color !== undefined && el.getAttribute(CANVAS) === "" && !el.hasAttribute(FILLED) && !toned(color)
    && el.getBoundingClientRect().height < document.documentElement.scrollHeight - SECTION_EDGE;
}

// The surfaces kept are judged again once the tone changes (a page judged
// dark while it loaded: its yellow column kept for the navy text the dark
// glass hid, ch.ch) or the page is darkened (the colours are Dark
// Reader's then).
function unkeep() {
  for (const el of marked("[" + KEPT + "]"))
    el.removeAttribute(KEPT);
}

// The background colour an element shows without the generic style, null
// when see-through or a picture (a photo behind white text is not kept),
// read once per element (owns) with KEPT set for the time of a style read
// (unstyled), its transitions held: once KEPT goes, the generic style's
// fade back to see-through is cancelled.
const FADED = /^(background|border|box-shadow)/;
let owns = new WeakMap();

function ownFill(el) {
  if (!owns.has(el))
    owns.set(el, unstyled(el));
  return owns.get(el);
}

function unstyled(el) {
  if (el.hasAttribute(KEPT))
    return fillOf(getComputedStyle(el));
  const style = el.getAttribute("style");
  el.style.setProperty("transition", "none", "important");
  el.setAttribute(KEPT, "");
  const fill = fillOf(getComputedStyle(el));
  el.removeAttribute(KEPT);
  style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  getComputedStyle(el).backgroundColor;
  for (const a of el.getAnimations())
    if (a instanceof CSSTransition && FADED.test(a.transitionProperty))
      a.cancel();
  return fill;
}

function fillOf(style) {
  return alpha(style.backgroundColor) < CLEAR || style.backgroundImage !== "none" ? null : style.backgroundColor;
}

function markInk() {
  const root = document.documentElement;
  if (!root || !document.body)
    return;
  if (off !== false) {
    for (const el of marked("[" + INK + "], [" + TILE + "], [" + UNINVERT + "]")) {
      el.removeAttribute(INK), el.removeAttribute(TILE), el.removeAttribute(UNINVERT);
      setSides(el);
    }
    for (const el of marked("[" + GLYPH + "], [" + RULE + "]"))
      el.removeAttribute(GLYPH), el.removeAttribute(RULE);
    for (const el of marked("[" + BLOCK + "], [" + KEPT + "]"))
      el.removeAttribute(BLOCK), el.removeAttribute(KEPT);
    owns = new WeakMap();
    cards = new Map();
    return;
  }
  const h = window.innerHeight;
  const near = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > -h && r.top < 2 * h;
  };
  // the blocks first: the text on them is then read on the glass, after
  // the controls made see-through again
  markClears(near);
  markCards(near);
  markBlocks(near);
  // a mark taken off would fade the text back to its colour when the page
  // gives it a transition (the colour read halfway, the mark set and taken
  // off in turn): it is taken off with transitions held, its style
  // attribute put back once the marks are set
  const held = [];
  for (const el of marked("[" + INK + "]"))
    if (near(el)) {
      held.push([el, el.getAttribute("style")]);
      el.style.setProperty("transition", "none", "important");
      el.removeAttribute(INK);
    }
  faces = new Map();
  const fadesSeen = new Set();
  for (const el of shownText(near)) {
    const style = getComputedStyle(el);
    if (label(el, style))
      el.setAttribute(CANVAS, FILL);
    fadePseudos(el, fadesSeen);
    const fgs = inks(style).map(luminance).filter((y) => y !== null);
    if (!fgs.length)
      continue;
    const bg = behind(el);
    // in a bar, the veil over what scrolls under it too (veiled)
    const worst = bg !== null && inBar(el) ? behind(el, true, true) : bg;
    const grey = bg > DARK_BG && inks(style).every((c) => chroma(c) < GLASS_CHROMA);
    const low = (fg) => contrast(fg, bg) < INK_RATIO || contrast(fg, worst) < INK_RATIO
      || (grey && contrast(fg, bg) < GLASS_RATIO && onGlass(el));
    if (bg !== null && fgs.every(low) && !kept(el, fgs)) {
      inkFrom.set(el, style.color);
      el.setAttribute(INK, bg > 0.179 ? "dark" : "light");
    }
  }
  markEdges(near);
  markIcons(near);
  if (held.length)
    getComputedStyle(held[0][0]).color;
  for (const [el, style] of held)
    style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  markTiles(near);
  markUninverted(near);
  markGlyphs(near);
  markRules(near);
}

// Inline SVG icons drawn in the text colour (their shapes paint
// currentColor: a menu's chevron, a search button's magnifier) are read as
// text is: an <svg> near the window whose painted shapes (not in <defs>
// and the like) all paint its colour, under INK_RATIO against what is
// behind it, gets INK, and its shapes follow the readable colour like the
// labels beside it. One Dark Reader inverts is left to markUninverted; at
// most TILE_ELEMENTS are looked at.
function markIcons(near) {
  const svgs = everywhere("svg:not([" + DR_INVERT + "])");
  for (let i = 0; i < svgs.length && i < TILE_ELEMENTS; i++) {
    const svg = svgs[i];
    if (!near(svg) || svg.parentElement && svg.parentElement.closest("svg") || !inColor(svg))
      continue;
    const fg = luminance(getComputedStyle(svg).color);
    const bg = behind(up(svg) || document.documentElement);
    if (fg !== null && bg !== null && contrast(fg, bg) < INK_RATIO)
      svg.setAttribute(INK, bg > 0.179 ? "dark" : "light");
  }
}

// The paints of an svg's shapes: their computed fill and stroke, shown
// (not none, not see-through), outside <defs> and the like.
function shapePaints(svg) {
  const all = [];
  for (const shape of svg.querySelectorAll(SHAPES)) {
    if (shape.closest(UNPAINTED))
      continue;
    const style = getComputedStyle(shape);
    for (const paint of [style.fill, style.stroke])
      if (paint !== "none" && alpha(paint) >= CLEAR)
        all.push(paint);
  }
  return all;
}

// Whether an svg is an icon in its text colour: ICON_SHAPES shapes at
// most (not a chart), all painted with it.
const ICON_SHAPES = 40;

function inColor(svg) {
  if (svg.querySelectorAll(SHAPES).length > ICON_SHAPES)
    return false;
  const color = getComputedStyle(svg).color;
  const all = shapePaints(svg);
  return all.length > 0 && all.every((paint) => paint === color);
}

// Pictures made for a white page, on a background now dark, are shown on
// a white tile (TILE), as shops show product photos in a dark theme: a
// white background and a white margin TILE_PAD wide drawn by a shadow
// (the layout stays), round corners, no blending, no filter. Two kinds,
// checked as the text is, at most TILE_ELEMENTS pictures near the window:
// - a picture blended with multiply (or darken) into its background: a
//   site wipes out the white of a product photo or a logo that way, and on
//   a dark background the picture turns dark or black on black;
// - on a dark page (Dark Reader's, or one whose tone is dark: the glass
//   is), an <img> with see-through parts whose ink (its opaque pixels)
//   reads under INK_RATIO against the background for at least TILE_INK of
//   it: a black logo or line drawing. Its pixels are read on a small
//   canvas (sample), which only a picture of the page's origin (or a data:
//   URL) allows; one from another origin is read from a copy loaded
//   anonymously, which its server may allow (a CDN serving logos to any
//   site), else it stays as it is. Dark ink of one tone, the rest of one
//   tone too (oneTone, its unreadable and its readable part: a black word
//   mark, a navy pictogram, the black lines of an icon beside its red
//   accent), is inverted instead ("invert": light ink, no tile, the hues
//   turned back, so a coloured part keeps its hue); shaded dark ink (a
//   black product cut out of its photo) or a picture in many tones (an
//   illustrated badge) keeps the tile, which keeps its shading (one from
//   another origin stays as it is: a shop's photos);
// - on a page Dark Reader darkens, an opaque <img> shot on white: its
//   outer ring of pixels near white (WHITE_Y) for at least TILE_FRAME of
//   it, as a shop's product photos are (a JPEG whose white is baked in),
//   "photo", from another origin too (read from the copy); an editorial
//   photo filling its frame, and a round picture (its own corners rounded
//   a quarter of its side at least: an avatar), are left alone, and so is
//   any opaque picture on a page dark by its own theme (it shows its
//   photos as it means to: Galaxus tiles its own).
// On a page Dark Reader did not darken, only a picture on the glass (no
// background of the site's own behind it up to the root, or a bar) and
// with no filter of its own is looked at: the site drew its own dark
// surfaces with their pictures. An icon (ICON_SIDE px at most both ways)
// is never tiled nor blended: inverted as above, else left as it is. An
// inline <svg> whose shapes paint dark colours of their own (not its text
// colour, see markIcons), in a control whose label got light INK, is
// inverted the same way. A picture nearly as wide as the window (a
// full-bleed photo) is left alone, and so is one shown through a mask
// (mask-image: a logo wall paints each logo in its text colour, which Dark
// Reader lightens, through the logo as a mask, the picture's own pixels
// pushed out of its box). See-through shaded ink laid over a larger
// picture (a line drawing peeking over a product screenshot) is not tiled
// either: that picture is what is behind it, not the dark page, and a
// white tile would hide it.
const TILE_ELEMENTS = 500;
const ICON_SIDE = 32;
const TILE_WIDE = 0.9;
const TILE_INK = 0.4;
const TILE_CLEAR = 0.1;
const TILE_FRAME = 0.8;
const WHITE_Y = 0.8;
const ROUND = 0.25;
const DARK_BG = 0.179;
const DARKENING = new Set(["multiply", "darken"]);
const MONO_CHROMA = 0.1;
const MONO_EDGE = 2;
const MONO_FLAT = 1.5;

function markTiles(near) {
  const pictures = [...everywhere("img, svg, canvas"), ...barIcons()];
  for (let i = 0; i < pictures.length && i < TILE_ELEMENTS; i++) {
    const el = pictures[i];
    if (!near(el))
      continue;
    const kind = tile(el);
    if (kind === null)
      el.removeAttribute(TILE);
    else if (el.getAttribute(TILE) !== kind)
      el.setAttribute(TILE, kind);
    setSides(el);
  }
}

// The icons a bar with dark INK paints on an empty element at most
// ICON_SIDE px, as its background picture or as its background colour
// through a mask (SRF's chevrons: a white caret in a span), tiled as its
// pictures are (lightInk: the filter comes before the mask), and the
// elements of that kind marked before (their mark taken off once they no
// longer are).
const URL_IMAGE = /^url\("?([^"]+)"?\)$/;

function barIcons() {
  const found = marked("[" + TILE + "]").filter((el) => !PICTURES.has(el.localName));
  for (const bar of marked("[" + BAR + "]")) {
    if (!bar.querySelector("[" + INK + "=\"dark\"]"))
      continue;
    for (const el of bar.querySelectorAll("*")) {
      if (PICTURES.has(el.localName) || el.firstElementChild || el.textContent.trim() || found.includes(el))
        continue;
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (r.width && r.width <= ICON_SIDE && r.height <= ICON_SIDE
          && (URL_IMAGE.test(style.backgroundImage) || URL_IMAGE.test(style.maskImage)))
        found.push(el);
    }
  }
  return found;
}

// A photo shot on white ("photo") fitted inside a box of another shape
// (object-fit contain or scale-down: a shop's photos in square boxes)
// leaves the box's edges empty, the card's colour, where a site may lay a
// label: its tile is drawn around the photo as shown, not around its box,
// by the space left on each side, inline in TILE_SIDES (none for a photo
// filling its box). A multiplied picture's tile stays its box: the white
// card it was blended into.
const TILE_SIDES = ["top", "right", "bottom", "left"].map((side) => "--browserglass-tile-" + side);
const FITTED = new Set(["contain", "scale-down"]);

function setSides(el) {
  const kind = el.getAttribute(TILE);
  const sides = kind === "photo" ? fitted(el) : null;
  TILE_SIDES.forEach((name, i) => {
    const value = sides ? sides[i] + "px" : "";
    if (el.style.getPropertyValue(name) !== value)
      value ? el.style.setProperty(name, value) : el.style.removeProperty(name);
  });
}

// The space [top, right, bottom, left] around an <img> fitted in its box,
// in whole px, or null.
function fitted(el) {
  const style = getComputedStyle(el);
  const nw = el.naturalWidth, nh = el.naturalHeight;
  if (el.localName !== "img" || !nw || !nh || !FITTED.has(style.objectFit))
    return null;
  const w = el.clientWidth, h = el.clientHeight;
  let k = Math.min(w / nw, h / nh);
  if (style.objectFit === "scale-down")
    k = Math.min(k, 1);
  const dw = w - nw * k, dh = h - nh * k;
  if (dw < 1 && dh < 1)
    return null;
  const [x, y] = style.objectPosition.split(" ").map((v, i) => placed(v, i ? dh : dw));
  return [y, dw - x, dh - y, x].map((v) => Math.max(0, Math.round(v)));
}

// An object-position value along a side with `room` px to spare.
function placed(value, room) {
  const n = parseFloat(value);
  if (isNaN(n))
    return room / 2;
  return value.endsWith("%") ? n / 100 * room : n;
}

// How a picture is tiled: "blend" (multiplied), "ink" (dark ink),
// "invert" (dark ink of one tone, an icon; light ink on a bar veiled
// light), "plain" (its filter gone, see lightInk), "photo" (shot on white)
// or null.
// A tile changes the picture's own background and blending: what is behind
// it is read from its parent, and a picture tiled for its blending stays
// so (its blending is the tile's now). Never taken off and set again in
// turn: a site's transition would read the tile's white halfway. Pixels
// are read before what is behind (most pictures are opaque photos).
function tile(el) {
  const r = el.getBoundingClientRect();
  const masked = getComputedStyle(el).maskImage !== "none";
  if (r.width >= TILE_WIDE * window.innerWidth || masked && PICTURES.has(el.localName))
    return null;
  if (inkedBar(el))
    return lightInk(el);
  if (masked)
    return null;
  const icon = r.width <= ICON_SIDE && r.height <= ICON_SIDE;
  const blended = !icon && (el.getAttribute(TILE) === "blend" || DARKENING.has(getComputedStyle(el).mixBlendMode));
  const s = blended ? null : drawn(el);
  const shot = darkened && !icon && s !== null && s.clear < TILE_CLEAR && s.white >= TILE_FRAME
    && !round(el, r);
  if (!blended && !shot && !(s && s.clear >= TILE_CLEAR))
    return null;
  const parent = el.parentElement || document.documentElement;
  const bg = behind(parent);
  if (bg === null || bg > DARK_BG || !blended && !darkened && !onGlass(parent))
    return null;
  if (blended)
    return "blend";
  if (shot)
    return "photo";
  const dark = s.inks.filter((y) => contrast(y, bg) < INK_RATIO);
  if (dark.length < TILE_INK * s.inks.length)
    return null;
  if (oneTone(dark) && oneTone(s.inks.slice(dark.length)))
    return "invert";
  return icon || s.far || laidOver(el, r) ? null : "ink";
}

// Whether a larger picture (BACKDROPS) shares more than a pixel each way
// of a picture's box `r`: the picture it is laid over.
const BACKDROPS = "img, video, canvas";

function laidOver(el, r) {
  return everywhere(BACKDROPS).some((other) => {
    const o = other.getBoundingClientRect();
    return other !== el && o.width * o.height > r.width * r.height
      && Math.min(r.right, o.right) - Math.max(r.left, o.left) > 1
      && Math.min(r.bottom, o.bottom) - Math.max(r.top, o.top) > 1;
  });
}

// Light ink on a bar veiled light. A site's dark header (rtbf.be, Docker's
// docs) is a bar like any other: under a light theme its veil is light and
// its white labels get dark INK, but the white logos and icons drawn for
// it stayed white on the veil (a word mark painting fill="#fff", not its
// text colour; a black icon the site whitens with a filter of its own).
// In a bar holding a label with dark INK (inkedBar), a picture on a light
// background whose ink, as shown, reads under INK_RATIO against it for
// TILE_INK of it, of one tone and the rest of one tone (oneTone), follows
// the labels: "invert", the filter that turns dark ink light turns light
// ink dark (the hues turned back); one the site's own filter whitened gets
// "plain" instead when its ink reads without it (no filter: a black icon
// shows black), kept from pass to pass (its filter is gone then). A colour
// logo (most of its ink readable, or in many tones) and an opaque picture
// (a photo, an avatar) are left alone. Its ink: the paints of an inline
// <svg> not drawn in its text colour (markIcons inks those), the pixels
// of an <img> with see-through parts or of an icon's background picture
// (sample, barIcons), shown through the site's
// filter as far as its invert() and brightness() go (shownInk).
function inkedBar(el) {
  for (let p = up(el); p; p = up(p))
    if (p.hasAttribute(BAR))
      return !!p.querySelector("[" + INK + "=\"dark\"]");
  return false;
}

function lightInk(el) {
  const bg = behind(el.parentElement || document.documentElement);
  if (bg === null || bg <= DARK_BG)
    return null;
  if (el.getAttribute(TILE) === "plain")
    return "plain";
  const raw = rawInk(el);
  if (!raw)
    return null;
  const filter = el.hasAttribute(TILE) ? "none" : getComputedStyle(el).filter;
  const shown = shownInk(raw, filter);
  const light = shown.filter((y) => contrast(y, bg) < INK_RATIO);
  if (light.length < TILE_INK * shown.length || !oneTone(light)
      || !oneTone(shown.filter((y) => contrast(y, bg) >= INK_RATIO)))
    return null;
  if (filter === "none")
    return "invert";
  return raw.filter((y) => contrast(y, bg) < INK_RATIO).length < TILE_INK * raw.length ? "plain" : null;
}

// The ink of a picture as drawn, before any filter: the sample of an
// <img> with see-through parts, or of the background picture of an
// element (barIcons, loaded apart: backImage), the colour of a masked one,
// the paints of a top inline <svg> not in its text colour, sorted; null
// for anything else.
function rawInk(el) {
  const style = getComputedStyle(el);
  if (!PICTURES.has(el.localName) && style.maskImage !== "none") {
    const y = luminance(style.backgroundColor);
    return style.backgroundImage === "none" && y !== null && alpha(style.backgroundColor) >= CLEAR ? [y] : null;
  }
  const url = el.localName === "img" ? null : style.backgroundImage.match(URL_IMAGE);
  if (el.localName === "img" || url) {
    const s = url ? sample(backImage(url[1]), el.getBoundingClientRect()) : sample(el);
    return s && s.clear >= TILE_CLEAR ? s.inks : null;
  }
  if (el.localName !== "svg" || el.parentElement && el.parentElement.closest("svg") || inColor(el))
    return null;
  const ys = shapePaints(el).map(luminance).filter((y) => y !== null);
  return ys.length ? quantiles(ys.sort((a, b) => a - b)) : null;
}

// Luminances through a computed filter, sorted: its invert() and
// brightness() steps, in turn, on the sRGB values (the others, a sepia or
// a hue-rotate, hardly move a grey).
const FILTER_STEPS = /(invert|brightness)\(([\d.]+)(%?)\)/g;

function shownInk(ys, filter) {
  let values = ys.map(encoded);
  for (const [, step, n, percent] of filter.matchAll(FILTER_STEPS)) {
    const k = parseFloat(n) / (percent ? 100 : 1);
    values = values.map((v) => step === "invert" ? k * (1 - v) + (1 - k) * v : Math.min(1, k * v));
  }
  return values.map(linear).sort((a, b) => a - b);
}

// Whether a picture's own corners are rounded ROUND of its side at least
// (an avatar's circle).
function round(el, r) {
  const radius = getComputedStyle(el).borderTopLeftRadius;
  const side = Math.min(r.width, r.height);
  const px = radius.endsWith("%") ? parseFloat(radius) / 100 * side : parseFloat(radius);
  return px >= ROUND * side;
}

// Whether sorted luminances are of one tone: MONO_EDGE steps in from each
// end (pixels where two colours meet), under MONO_FLAT apart.
function oneTone(ys) {
  return ys.length <= 2 * MONO_EDGE || contrast(ys[ys.length - 1 - MONO_EDGE], ys[MONO_EDGE]) < MONO_FLAT;
}

// The ink of a picture to tile: the sample of an <img>, the paints of an
// inline <svg> in a control whose label got light INK (as see-through
// all through), null for anything else or off a dark page. A picture with
// a filter of its own (not ours) is the site's to show.
function drawn(el) {
  if (tone !== "dark" || filtered(el))
    return null;
  if (el.localName === "img")
    return sample(el);
  if (el.localName !== "svg" || el.hasAttribute(DR_INVERT) || el.hasAttribute(INK)
      || el.parentElement && el.parentElement.closest("svg"))
    return null;
  const control = el.closest(CONTROLS);
  if (!control || !control.querySelector("[" + INK + "=\"light\"]") || inColor(el))
    return null;
  const ys = shapePaints(el).map(luminance).filter((y) => y !== null);
  return ys.length ? {clear: 1, inks: quantiles(ys.sort((a, b) => a - b)), far: true} : null;
}

// Whether the site filters a picture: a filter of its own (not ours), or
// one on an element up to FILTER_DEPTH above it (Wikipedia's night theme
// inverts its logo's container: inverted again, the word mark is black).
const FILTER_DEPTH = 8;

function filtered(el) {
  if (!el.hasAttribute(TILE) && getComputedStyle(el).filter !== "none")
    return true;
  let p = el.parentElement;
  for (let i = 0; p && i < FILTER_DEPTH; i++, p = p.parentElement)
    if (getComputedStyle(p).filter !== "none")
      return true;
  return false;
}

// Whether what is behind `el` is the glass's: no background of the site's
// own up to the root (a layer the glass cleared paints none), or a bar
// (the glass styles paint it).
function onGlass(el) {
  for (let p = el; p && p !== document.documentElement; p = p.parentElement) {
    if (p.hasAttribute(BAR))
      return true;
    const style = getComputedStyle(p);
    if (face(p) !== undefined || picture(style) || alpha(style.backgroundColor) >= OWN_BG)
      return false;
  }
  return true;
}

// Dark Reader inverts an inline <svg> logo (DR_INVERT) whose markup alone
// draws dark ink on nothing: it reads the svg as a picture, with the
// colours of its attributes. But a style sheet of the page may paint its
// shapes (.logo path { fill: var(--text) }), and Dark Reader lightens
// that rule too: the ink is light already, and the invert turns it dark
// again, a dark logo on the dark background. Such an svg, on a dark
// background, whose shapes' paint (their computed fill and stroke, not
// in <defs> and the like) is lighter and reads against it (INK_RATIO) as
// it is for at least UNINVERT_READ of it, gets UNINVERT: no filter. One over
// INVERT_LARGE px (a large light picture, which Dark Reader dims on
// purpose) stays as it is. The mark goes with the invert, with the
// darkening (a light theme) and with the page's marks.
const DR_INVERT = "data-darkreader-inline-invert";
const UNINVERT_READ = 0.6;
const INVERT_LARGE = 512 * 512;
const SHAPES = "path, rect, circle, ellipse, line, polyline, polygon, text";
const UNPAINTED = "defs, clipPath, mask, symbol, pattern, marker";

function markUninverted(near) {
  for (const el of marked("[" + UNINVERT + "]"))
    if (!darkened || !el.hasAttribute(DR_INVERT))
      el.removeAttribute(UNINVERT);
  if (!darkened)
    return;
  for (const svg of everywhere("svg[" + DR_INVERT + "]"))
    if (near(svg))
      uninverted(svg) ? svg.setAttribute(UNINVERT, "") : svg.removeAttribute(UNINVERT);
}

function uninverted(svg) {
  const r = svg.getBoundingClientRect();
  if (r.width * r.height > INVERT_LARGE)
    return false;
  const bg = behind(svg.parentElement || document.documentElement);
  if (bg === null || bg > DARK_BG)
    return false;
  const ys = [];
  for (const shape of svg.querySelectorAll(SHAPES)) {
    if (shape.closest(UNPAINTED))
      continue;
    const style = getComputedStyle(shape);
    for (const paint of [style.fill, style.stroke]) {
      const y = luminance(paint);
      if (y !== null && alpha(paint) >= CLEAR)
        ys.push(y);
    }
  }
  const read = ys.filter((y) => y > bg && contrast(y, bg) >= INK_RATIO).length;
  return ys.length > 0 && read >= UNINVERT_READ * ys.length;
}

// Glyphs drawn with a background, not with text or a picture: the bars of
// a menu button (an empty <span> and its ::before and ::after, a few px
// thick, painted in the site's text colour), the strokes of a close
// button's cross. Dark Reader takes them for backgrounds and darkens them
// (a navy bar turns near black), and on the dark glass they vanish. An
// empty element near the window, GLYPH_BOX px at most both ways, inside a
// button or a link (or in a box that small: a menu button made of a <div>),
// whose parts (itself, its ::before, its ::after) paint a plain colour
// THIN px thick at most and GLYPH_BOX long at most, are ink: a part that
// reads under INK_RATIO against what is behind, while the text colour
// would read, is named in GLYPH and painted in the text colour. A thin rule
// of the page (a separator, wider, outside any control) and a coloured
// pill (thicker) are left alone. The marks stay once set (the text colour
// reads in every theme) and go with the page's (an excluded page); at most
// GLYPH_ELEMENTS empty elements are looked at.
const GLYPH_BOX = 48;
const GLYPH_ELEMENTS = 2000;
const CONTROLS = "button, a[href], [role=button], summary, label";

function markGlyphs(near) {
  const empty = everywhere(":empty");
  for (let i = 0; i < empty.length && i < GLYPH_ELEMENTS; i++) {
    const el = empty[i];
    const r = el.getBoundingClientRect();
    if (r.width > GLYPH_BOX || r.height > GLYPH_BOX || MEDIA.has(el.localName) || !near(el))
      continue;
    const box = el.parentElement && el.parentElement.getBoundingClientRect();
    if (!el.closest(CONTROLS) && !(box && box.width <= GLYPH_BOX && box.height <= GLYPH_BOX))
      continue;
    const had = el.getAttribute(GLYPH) || "";
    const parts = ["self", ...PSEUDOS].filter((part) => !had.includes(part) && glyph(el, r, part));
    if (parts.length)
      el.setAttribute(GLYPH, (had + " " + parts.join(" ")).trim());
  }
}

// Whether a part of `el` ("self", "before", "after") is a glyph without
// contrast. A thin element's ::before and ::after (the other bars) sit
// beside it, on what is behind it.
function glyph(el, r, part) {
  const style = getComputedStyle(el, part === "self" ? null : "::" + part);
  if (part !== "self" && (style.content === "none" || style.display === "none"))
    return false;
  const w = part === "self" ? r.width : parseFloat(style.width);
  const h = part === "self" ? r.height : parseFloat(style.height);
  if (!(w > 0 && h > 0) || Math.min(w, h) > THIN || Math.max(w, h) > GLYPH_BOX
      || style.backgroundImage !== "none" || alpha(style.backgroundColor) < OWN_BG
      || parseFloat(style.opacity) < CLEAR)
    return false;
  const thin = Math.min(r.width, r.height) <= THIN;
  const bg = behind(thin ? el.parentElement || document.documentElement : el);
  const paint = luminance(style.backgroundColor), text = luminance(style.color);
  return bg !== null && paint !== null && text !== null && alpha(style.color) >= CLEAR
    && contrast(paint, bg) < INK_RATIO && contrast(text, bg) >= INK_RATIO;
}

// Thin rules: on a page Dark Reader darkens, a separator painted in a
// light grey (admin.ch's 1 px line between its logo and its title) turns
// a dark grey, lost on the dark glass. An empty element near the window,
// not a glyph, RULE_THIN px thick at most and RULE_LONG px long at least,
// painting a plain neutral colour (under MONO_CHROMA of chroma) that
// reads under RULE_READ against what is behind it (its parent's) on a dark
// background, gets RULE: a light neutral, as fine separators are drawn in
// a dark theme. The marks stay once set (the rule then reads) and go with
// the darkening and the page's marks; at most GLYPH_ELEMENTS are looked at.
const RULE_THIN = 2;
const RULE_LONG = 8;
const RULE_READ = 1.6;

function markRules(near) {
  if (!darkened) {
    for (const el of marked("[" + RULE + "]"))
      el.removeAttribute(RULE);
    return;
  }
  const empty = everywhere(":empty:not([" + RULE + "]):not([" + GLYPH + "])");
  for (let i = 0; i < empty.length && i < GLYPH_ELEMENTS; i++) {
    const el = empty[i];
    if (!MEDIA.has(el.localName) && near(el) && rule(el))
      el.setAttribute(RULE, "");
  }
}

function rule(el) {
  const r = el.getBoundingClientRect();
  if (Math.min(r.width, r.height) > RULE_THIN || Math.max(r.width, r.height) < RULE_LONG)
    return false;
  const style = getComputedStyle(el);
  const paint = style.backgroundColor;
  if (style.backgroundImage !== "none" || alpha(paint) < OWN_BG || chroma(paint) >= MONO_CHROMA
      || parseFloat(style.opacity) < CLEAR)
    return false;
  const bg = behind(el.parentElement || document.documentElement);
  const y = luminance(paint);
  return bg !== null && y !== null && bg <= DARK_BG && contrast(y, bg) < RULE_READ;
}

// A picture's pixels, read once per source on a canvas SAMPLE_SIDE px on
// its long side (a small icon drawn larger, so that its thin lines
// count): {clear: the share of see-through pixels (alpha under CLEAR),
// inks: the luminance of the others at INK_STEPS quantiles, white: the
// share of the outer ring that is opaque and near white (WHITE_Y), far:
// read from a copy}. null when they cannot be read (an empty picture); a
// picture still loading is read once loaded (a new pass, see loaded). One
// of another origin taints the canvas: a copy is loaded anonymously
// (CORS), read if its server allows it, then a new pass runs; null
// meanwhile and if refused.
const SAMPLE_SIDE = 96;
const INK_STEPS = 20;
const SAMPLES_MAX = 1000;
const samples = new Map();

function sample(img, r = img.getBoundingClientRect()) {
  const src = img.currentSrc;
  if (!src)
    return null;
  if (samples.has(src))
    return samples.get(src);
  if (!img.complete)
    return null;
  if (samples.size >= SAMPLES_MAX)
    samples.clear();
  try {
    samples.set(src, pixels(img, r));
  } catch (e) {
    samples.set(src, null);  // another origin (SecurityError), or not decodable
    if (!/^(data|blob):/.test(src))
      borrow(src, r);
  }
  return samples.get(src);
}

// The image of a background picture's URL, loaded once (at most
// SAMPLES_MAX kept), a new pass run once it is in: sampled at the size
// of the element painting it. Not backdrop(), the page layer test.
const backImages = new Map();

function backImage(src) {
  if (!backImages.has(src)) {
    if (backImages.size >= SAMPLES_MAX)
      backImages.clear();
    const img = new Image();
    img.onload = () => ink();
    img.src = src;
    backImages.set(src, img);
  }
  return backImages.get(src);
}

function borrow(src, r) {
  const copy = new Image();
  copy.crossOrigin = "anonymous";
  copy.onload = () => {
    try {
      const s = pixels(copy, r);
      samples.set(src, s && {...s, far: true});
    } catch (e) {
      return;
    }
    ink();
  };
  copy.src = src;
}

function pixels(img, r) {
  const k = SAMPLE_SIDE / Math.max(r.width, r.height, 1);
  const w = Math.max(1, Math.round(r.width * k)), h = Math.max(1, Math.round(r.height * k));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const g = canvas.getContext("2d", {willReadFrequently: true});
  g.drawImage(img, 0, 0, w, h);
  const data = g.getImageData(0, 0, w, h).data;
  const white = whiteRing(data, w, h);
  const ys = [];
  for (let i = 0; i < data.length; i += 4)
    if (data[i + 3] >= CLEAR * 255)
      ys.push(rgbLuminance(linear(data[i] / 255), linear(data[i + 1] / 255), linear(data[i + 2] / 255)));
  if (!ys.length)
    return null;
  ys.sort((a, b) => a - b);
  return {clear: 1 - ys.length / (w * h), inks: quantiles(ys), white, far: false};
}

// The share of a sample's outer ring of pixels that is opaque and near
// white.
function whiteRing(data, w, h) {
  let ring = 0, white = 0;
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x += y === 0 || y === h - 1 ? 1 : Math.max(1, w - 1)) {
      const i = (y * w + x) * 4;
      ring++;
      if (data[i + 3] >= CLEAR * 255
          && rgbLuminance(linear(data[i] / 255), linear(data[i + 1] / 255), linear(data[i + 2] / 255)) >= WHITE_Y)
        white++;
    }
  return white / ring;
}

// INK_STEPS quantiles of sorted values.
function quantiles(ys) {
  const inks = [];
  for (let q = 0; q < INK_STEPS; q++)
    inks.push(ys[Math.floor((q + 0.5) * ys.length / INK_STEPS)]);
  return inks;
}

// A picture loaded after the last pass is looked at again: a lazy one
// (no width, so not near, until it is in: a shop's product photos
// scrolled into view), a source swapped, pixels not there to read. One
// listener for the document (load does not bubble, it is caught on its
// way down), nothing watched per picture.
function loaded(e) {
  if (off === false && e.target.localName === "img")
    ink();
}

function ink() {
  if (!inkFrame)
    inkFrame = requestAnimationFrame(function tick(now) {
      if (now - inkAt < INK_MS) {
        inkFrame = requestAnimationFrame(tick);
        return;
      }
      inkFrame = 0;
      inkAt = now;
      markInk();
    });
}

// The layers are looked for again, once per frame at most: when the page
// scrolls (a header sticks, or turns fixed), is resized, has loaded, ends a
// transition (a bar fading in), when the size of the document, the body,
// one of its children or a marked element changes, and when the body gets
// or loses a child. A single-page app swaps its view once its data is in:
// after a click, a form sent, a navigation or the page's load, a few more
// passes, the last SETTLE_MS[SETTLE_MS.length - 1] ms later (animation
// frames, no timer). They measure the tone again too: an app's text may
// get its colours only once its components are drawn, after the load
// (YouTube's dark theme starts as black text), and a view may have
// another tone. Dark Reader starting gets these passes too, which look
// for shadow trees it left light (restyle).
let layerFrame = 0;

function layers() {
  if (!layerFrame)
    layerFrame = requestAnimationFrame(() => {
      layerFrame = 0;
      frameSchemes();
      markCanvas();
      markBars();
      markFills();
      ink();
    });
}

const layerSizes = new ResizeObserver(layers);

function watchLayers() {
  if (off !== false || !document.body)
    return;
  layerSizes.disconnect();
  canvasesWatched = new WeakSet();
  layerSizes.observe(document.documentElement);
  layerSizes.observe(document.body);
  for (const el of document.body.children)
    layerSizes.observe(el);
  for (const el of marked("[" + CANVAS + "], [" + BAR + "]"))
    layerSizes.observe(el);
  if (bodyKids.body !== document.body) {
    bodyKids.disconnect();
    bodyKids.body = document.body;
    bodyKids.observe(document.body, {childList: true});
  }
}

const bodyKids = new MutationObserver(() => {
  watchLayers();
  layers();
});

const SETTLE_MS = [100, 500, 1500, 3000];
let settleStart = 0, settleStep = 0, settleFrame = 0;

function settle() {
  if (off !== false)
    return;
  settleStart = performance.now();
  settleStep = 0;
  if (!settleFrame)
    settleFrame = requestAnimationFrame(settleTick);
}

function settleTick(now) {
  settleFrame = 0;
  if (now - settleStart >= SETTLE_MS[settleStep]) {
    settleStep++;
    if (!darkened) {
      measure();
      darken();
      paint();
    } else {
      restyle();
    }
    markCanvas();
    markBars();
    markFills();
    ink();
  }
  if (settleStep < SETTLE_MS.length && !settleFrame)
    settleFrame = requestAnimationFrame(settleTick);
}

function apply(domains, dark, themes) {
  helperDark = dark === true;
  off = Array.isArray(domains) && hostExcluded(location.hostname.toLowerCase().replace(/\.$/, ""), domains);
  themeCfg = {dark: helperDark, excluded: Array.isArray(domains) ? domains : [], themes: themes || {}};
  if (typeof themeRun === "function")
    themeRun(themeCfg, false);
  darken();
  paint();
  watchLayers();
  markCanvas();
  markBars();
  markFills();
  ink();
}

// Storage has no list until the helper sent its first one (a fresh
// install): off then stays null, so LIVE waits for that first list instead
// of turning on the live styles of a site excluded at sync. darken is
// stored with it (no darken stored: an older add-on's list, false).
function load() {
  browser.storage.local.get(["excluded", "darken", "themes"]).then((s) => {
    if (!fromMessage && Array.isArray(s.excluded))
      apply(s.excluded, s.darken, s.themes);
  }, () => {});
}

// A page that rewrites the attributes of <html>, or replaces <html> itself,
// gets them back. Only those two things are watched: the attributes of the
// root element, and the children of the document (not its subtree), so DOM
// insertions inside the page never wake this script. A change other than
// to our own attributes (a theme switch: a class, data-theme...) measures
// the tone again; ours only repaint, so setting them never loops. Inline
// style is not a theme switch: pages rewrite it on scroll or pointer
// moves (CSS variables), and measuring forces a style flush.
let watched = null;
const observer = new MutationObserver((records) => {
  watch();
  if (records.some((r) => r.type === "childList"
      || (r.attributeName !== "style" && !r.attributeName.startsWith(OWN)))) {
    measure();
    darken();
    watchLayers();
    layers();
  }
  paint();
});

function watch() {
  const root = document.documentElement;
  if (root && root !== watched) {
    watched = root;
    observer.observe(root, {attributes: true});
  }
}

observer.observe(document, {childList: true});
watch();

browser.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "excluded") {
    fromMessage = true;
    apply(msg.domains, msg.darken, msg.themes);
  }
});

// A page restored from the back/forward cache missed the messages sent
// while it was hidden.
window.addEventListener("pageshow", (e) => {
  if (e.persisted) {
    fromMessage = false;
    load();
  }
});

// The tone is measured once the document is parsed and loaded, when the
// colour scheme changes (a page following it), and at the end of a
// transition of the text colour of the root or the body (a theme switch
// that animates).
document.addEventListener("DOMContentLoaded", update);
window.addEventListener("load", () => {
  loadedAt = performance.now();
  // a page whose theme was written early is judged once, a little later
  if (typeof themeState !== "undefined" && themeState.early)
    setTimeout(update, THEME_JUDGE_MS + 50);
});
window.addEventListener("load", update);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (themeCfg && typeof themeRun === "function")
    themeRun(themeCfg, false);
  update();
});
document.addEventListener("transitionend", (e) => {
  if (e.propertyName === "color"
      && (e.target === document.body || e.target === document.documentElement))
    update();
}, {capture: true, passive: true});
for (const type of ["scroll", "transitionend"])
  document.addEventListener(type, layers, {capture: true, passive: true});
document.addEventListener("load", loaded, {capture: true, passive: true});
for (const type of ["scrollend", "resize", "load"])
  window.addEventListener(type, layers, {passive: true});
for (const type of ["click", "submit"])
  document.addEventListener(type, settle, {capture: true, passive: true});
for (const type of ["popstate", "hashchange", "load"])
  window.addEventListener(type, settle, {passive: true});

if (document.documentElement && document.documentElement.hasAttribute(OFF))
  off = true;
update();
load();

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
// canvas stretched over the page: YouTube's ambient mode); so does a
// layer floating over the page (a menu, a drawer, a dialog, a cookie
// banner: markFloats). Its blur ends with VEIL, a
// filter this script puts in the page:
// Firefox lays the blurred backdrop over what scrolls under the bar, so
// on the glass (a see-through page) a thin line of text, blurred into a
// faint haze, still showed sharp through it, unlike a picture; VEIL lays
// that haze on the glass's colour, as on a page with a background of its
// own: the text under the bar is blurred like a picture. Text left
// without contrast once its background went (dark text on
// the dark glass) gets data-browserglass-ink, a readable colour without
// the site's text-shadow (an inline SVG icon drawn in its text colour and
// an icon-font glyph too), and a picture made for a white
// page on a background now dark (a product photo whose white a site wipes
// out with mix-blend-mode, one shot on white on a page Dark Reader
// darkens, a black logo on such a page or on a bar the glass cleared)
// gets data-browserglass-tile: a white tile,
// or light ink for dark ink of one tone and for an icon. On a bar veiled
// light whose labels got dark ink (a site's dark header under a light
// theme), or on a header in the flow the glass cleared, white ink of one
// tone (a logo painting #fff) gets dark ink the same way, and an icon the
// site whitens with a filter loses the filter. A light logo of one tone
// Dark Reader darkens on its dark page gets its light ink back (inverted).
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
// out into that colour (a list's foot, a bar's row of links) gets it
// through data-browserglass-fade-pseudo, naming it, and one painting that
// colour straight on the glass (the gutters down a section's sides)
// data-browserglass-filled.
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
const UNFADE = "data-browserglass-unfade";
const TILE = "data-browserglass-tile";
const UNINVERT = "data-browserglass-uninvert";
const FILLED = "data-browserglass-filled";
const GLYPH = "data-browserglass-glyph";
const BLOCK = "data-browserglass-block";
const RULE = "data-browserglass-rule";
const BRAND = "data-browserglass-brand";
const UNDER = "data-browserglass-under";
const SEAM = "data-browserglass-seam";
const TUCK = "data-browserglass-tuck";
const FLAT = "data-browserglass-flat";
const KEPT = "data-browserglass-own";
const FADE = "data-browserglass-fade";
const FADE_IMAGE = "--browserglass-fade";
const FADE_PSEUDO = "data-browserglass-fade-pseudo";
const GLASS = "--browserglass-glass";
const TINT = "--browserglass-tint";
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
// shows: it tells the card's tone, not the page's. A box painting the
// colour of the page layer it lies on (onLayer) is the page, not a card:
// Watson's teasers, white in its white rows, hold the page's text once
// the rows are glass (else only the pink section titles left on the rows
// would vote, and make the white page dark). The root, the body and
// <main> are the page. Looked up once per element and measure.
function onCard(el, cards) {
  if (!el || el === document.body || el === document.documentElement || el.localName === "main")
    return false;
  if (cards.has(el))
    return cards.get(el);
  const color = getComputedStyle(el).backgroundColor;
  const value = alpha(color) >= OWN_BG
    ? !backdrop(el) && !onLayer(el, color) : onCard(el.parentElement, cards);
  cards.set(el, value);
  return value;
}

// Whether the first element painting anything above `el` is a page layer
// (CANVAS) whose own colour is `color`: the colour it paints now, read
// with the mark off (a page switching its theme repaints its layers).
// Read once per layer and pass (layerFills, emptied once the pass is done).
const layerFills = new Map();

function onLayer(el, color) {
  for (let e = el.parentElement; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
    if (e.hasAttribute(CANVAS)) {
      if (!layerFills.size)
        queueMicrotask(() => layerFills.clear());
      if (!layerFills.has(e))
        layerFills.set(e, unmarked(e, CANVAS));
      return layerFills.get(e) === color;
    }
    if (alpha(getComputedStyle(e).backgroundColor) >= OWN_BG)
      return false;
  }
  return false;
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
// most PICTURE_TESTS elements per measure. Text out of the window cannot
// be hit tested: it is on a picture when, up to PICTURE_DEPTH parents up
// (not past a layer of the page or a card), a parent shows a background
// image sized to cover or holds a picture whose box takes in the text's
// (Watson's white bylines on the photos of the rows above the window,
// once those rows are glass); else it is on the page.
const PICTURES = new Set(["img", "picture", "video", "canvas", "svg"]);
const PICTURE_TESTS = 200;
const PICTURE_DEPTH = 4;

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
  } else if (r.width && pictures.size < PICTURE_TESTS) {
    value = pictureUnder(el, r);
  }
  pictures.set(el, value);
  return value;
}

function pictureUnder(el, r) {
  const covers = (b) => b.left <= r.left && b.right >= r.right && b.top <= r.top && b.bottom >= r.bottom;
  for (let e = el.parentElement, i = 0; e && e !== document.body && i < PICTURE_DEPTH;
       e = e.parentElement, i++) {
    if (e.hasAttribute(CANVAS))
      return false;
    const style = getComputedStyle(e);
    if (/url\(/.test(style.backgroundImage) && /cover|contain/.test(style.backgroundSize))
      return true;
    for (const p of e.querySelectorAll([...PICTURES].join(", ")))
      if (!holds(p, el) && !holds(el, p) && covers(p.getBoundingClientRect()))
        return true;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return false;
  }
  return false;
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

// Under a light theme, a body painting an opaque light colour of its own
// is a light page before the text votes, unless the page shows a dark
// version of its own (ownDark): the white text on its photos, its black
// cards and its brand sections that the page rules made see-through
// (frame.work's hero lines, rust-lang's coloured bands) tells their tone,
// not the page's. The colour is the body's without the generic style
// (unstyled), or, a site style clearing it whatever the marks (rust-lang's),
// without any of the add-on's styles (nativeBody). Under a dark theme the
// text decides, as before.
function lightBody() {
  if (window.matchMedia("(prefers-color-scheme: dark)").matches || ownDark())
    return false;
  const fill = unstyled(document.body) || nativeBody();
  return fill !== null && alpha(fill) >= SOLID && isLight(fill) === true;
}

// The body's background colour with the add-on's styles off (OFF on the
// root for the read, the transitions held), null when it paints none. The
// transitions the styles start once back (a site style fading backgrounds
// in) are cancelled. Read again only once the classes of the root or the
// body, or the number of style sheets, change.
let nativeKey = null, nativeFill = null;

function nativeBody() {
  const root = document.documentElement, body = document.body;
  const key = root.className + "|" + body.className + "|" + document.styleSheets.length;
  if (key === nativeKey)
    return nativeFill;
  if (root.hasAttribute(OFF))
    return fillOf(getComputedStyle(body));
  const before = new Set(document.getAnimations());
  steady(() => {
    root.setAttribute(OFF, "");
    nativeFill = fillOf(getComputedStyle(body));
    root.removeAttribute(OFF);
    getComputedStyle(body).backgroundColor;
  });
  for (const a of document.getAnimations())
    if (a instanceof CSSTransition && !before.has(a))
      a.cancel();
  nativeKey = key;
  return nativeFill;
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
  if (lightBody()) {
    tone = "light";
    return;
  }
  const votes = levels.find(decides) || levels.find((t) => t[0] + t[1] > 0) || all;
  const [light, dark] = votes;
  const v = sampled ? light > dark : isLight(getComputedStyle(el).color);
  if (v !== null)
    tone = v ? "dark" : "light";
}

// A resize of the body measures again in the next frame, never inside the
// observer's callback: marks, styles and the layers observed there change
// sizes the browser is still delivering, and Firefox reports its loop
// error to the page (crates.io shows an error notice on any error).
let sizesFrame = 0;

const sizes = new ResizeObserver(() => {
  if (sizesFrame)
    return;
  if (++resizeMeasures > RESIZE_MEASURES)
    sizes.disconnect();
  else
    sizesFrame = requestAnimationFrame(() => {
      sizesFrame = 0;
      update();
    });
});

function update() {
  watchSheets();
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
  const marks = ownMarks();
  return marks.classes.concat(marks.attrs.map(([name]) => name)).join(" ");
}

// Those marks: {classes, attrs: [[name, value]]}, none while ours are set.
function ownMarks() {
  const root = document.documentElement;
  const marks = {classes: [], attrs: []};
  if (!root || native)
    return marks;
  marks.classes = NATIVE_CLASSES.filter((c) => root.classList.contains(c));
  for (const {name, value} of root.attributes)
    if (OWN_DARK.test(name) ? value.toLowerCase().split(/\s+/).includes("dark")
        : NATIVE_ATTRS.some(([n, v]) => n === name && v === value))
      marks.attrs.push([name, value]);
  return marks;
}

// Under a light theme, a page showing a dark version of its own on <html>
// (ownMarks: html.dark set by its own toggle) is tried without those
// marks, the mirror of nativeDark: they are taken off with the transitions
// held, the tone measured at once, and left off only if the text turned
// dark (the page has a light version); else they go back at once. Each
// set of marks is tried once (liftTried): a page setting them again keeps
// them, its own toggle followed. They are put back once the theme turns
// dark or the page is excluded.
let liftedMarks = null, liftTried = "";

function lighten() {
  const root = document.documentElement;
  if (!root || off !== false || window.matchMedia("(prefers-color-scheme: dark)").matches) {
    liftTried = "";
    if (liftedMarks)
      steady(() => {
        liftRestore();
        measure();
      });
    return;
  }
  const marks = ownMarks(), key = ownDark();
  if (darkened || tone !== "dark" || !key || key === liftTried)
    return;
  liftTried = key;
  liftedMarks = marks;
  steady(() => {
    if (marks.classes.length)
      root.classList.remove(...marks.classes);
    for (const [name] of marks.attrs)
      root.removeAttribute(name);
    measure();
  });
  if (tone === "light")
    return;
  steady(() => {
    liftRestore();
    measure();
  });
}

// Puts back the marks lighten() took off, the ones the page did not set
// again itself.
function liftRestore() {
  const root = document.documentElement;
  if (liftedMarks && root) {
    if (liftedMarks.classes.length)
      root.classList.add(...liftedMarks.classes);
    for (const [name, value] of liftedMarks.attrs)
      if (!root.hasAttribute(name))
        root.setAttribute(name, value);
  }
  liftedMarks = null;
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
  lighten();
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
    for (const el of marked("[" + CANVAS + "], [" + FILLED + "], [" + BLOCK + "], [" + UNDER + "], [" + SEAM + "]"))
      el.removeAttribute(CANVAS), el.removeAttribute(FILLED), el.removeAttribute(BLOCK), el.removeAttribute(UNDER),
      el.removeAttribute(SEAM);
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
    markPictured();
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
// (a pastel teal, which Dark Reader turns olive-black), or a light plain
// one on a band of BRAND_CHROMA (bandColor), gets BRAND naming
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
const BRAND_LIGHT = 0.5;
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
    const band = bandColor(el);
    for (const part of [...PSEUDOS, "self"]) {
      const fill = brandFill(el, r, part);
      const kind = fill && brandKind(fill, ink, band);
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
// pastel fill, or a light plain one, BRAND_LIGHT at least, on a band of
// BRAND_CHROMA: a white "Sign up" on an indigo call to action, which Dark
// Reader turns into a dark button), or LIFT (a dark plain one).
function brandKind(fill, ink, band) {
  const y = luminance(fill), fg = luminance(ink);
  if (y === null || fg === null || contrast(y, fg) < BRAND_READ)
    return null;
  const c = chroma(fill);
  if (c >= BRAND_CHROMA || c >= BRAND_PASTEL && fg < y || y >= BRAND_LIGHT && band && chroma(band) >= BRAND_CHROMA)
    return true;
  return y < BRAND_DARK && fg > y ? LIFT : null;
}

// The opaque plain colour a control sits on (that of its first ancestor
// painting one), null over a picture or a gradient, or on the page itself.
function bandColor(el) {
  for (let p = up(el); p && p !== document.body && p !== document.documentElement; p = up(p)) {
    const style = getComputedStyle(p);
    if (style.backgroundImage !== "none")
      return null;
    if (alpha(style.backgroundColor) >= SOLID)
      return style.backgroundColor;
  }
  return null;
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

// Fields and secondary buttons left opaque on the glass: on a see-through
// page Dark Reader leaves alone (glassPage), the site's own dark version
// included, a field (VEIL_FIELDS, any width) or a button (VEIL_BUTTONS, at
// most BRAND_W by BRAND_H px) near the window painting an opaque light plain
// fill of its own (BRAND_LIGHT of luminance at least, under BLOCK_CHROMA of
// chroma: a white search field, GitHub's #f6f8fa "Reject all"; a brand
// fill keeps its colour), not marked otherwise (a card's face, a bar), and
// right on the glass or a bar (onGlass under it: a white "Sign up" on a
// dark or a coloured band, or on a photo, is the site's call to action; a
// white button on a white card the page keeps opaque needs no veil, but
// for a framed light card itself on the glass under a light tone:
// onLightCard), gets
// BLOCK "veil": the surface of the page's tone at BLOCK_VEIL_OPACITY,
// its border kept; "veil edge" when it draws no border nor shadow of its
// own: a thin ring in its text colour too, or it is lost on the glass. The
// pill holding a control (pillOf: a low box painting a few controls, or
// its empty layers under them) is veiled first, as a field's box. A
// field's own text is inked as text is (markInk: the black of a native
// field on a dark veil). A mark is kept as long as the tone (a field marked
// reads as see-through), judged again once it changes, and goes when the
// page is darkened or not glass. It goes too once the control's own fill,
// read with the mark off, is no longer one to veil (veilable): a
// framework's button taking its variant's fill late, after hydration or a
// late style sheet (GitHub's green "Code", judged while still white).
const VEIL_FIELDS = "input:not([type=hidden], [type=checkbox], [type=radio], [type=range], [type=color],"
  + " [type=file], [type=image], [type=submit], [type=button], [type=reset]), textarea, select";
// the fields typed in (a select's text is shownSelects')
const TYPED = VEIL_FIELDS.replace(", select", "");
const VEIL_BUTTONS = "button, [role=button], input[type=submit], input[type=button], input[type=reset]";
const FIELD_EDGE = "edge";
let fields = new Set(), fieldTone = null;

function markFields(near) {
  const on = !darkened && glassPage && tone !== null;
  if (!on || tone !== fieldTone) {
    for (const el of fields)
      el.removeAttribute(BLOCK);
    fields = new Set();
    fieldTone = tone;
  }
  if (!on)
    return;
  // a mark another pass took off (a header made a bar strips the block
  // veils in it) is judged again
  for (const el of fields)
    if (!el.isConnected || !el.hasAttribute(BLOCK))
      fields.delete(el);
    else if (near(el) && !veilable(unmarked(el, BLOCK))) {
      el.removeAttribute(BLOCK);
      fields.delete(el);
    }
  const controls = everywhere(VEIL_FIELDS + ", " + VEIL_BUTTONS);
  for (let i = 0; i < controls.length && i < BRAND_ELEMENTS; i++) {
    const field = controls[i].matches(VEIL_FIELDS);
    // the pill holding it first: the control is then on that veil
    const pill = pillOf(controls[i]);
    for (const layer of pill ? pill.layers : [])
      veilField(layer, true, near, up(pill.box) || pill.box);
    const el = field ? fieldBox(controls[i]) : controls[i];
    veilField(el, field, near, up(el) || el);
  }
}

// Veils one box of markFields: a field's (any width) or a button's, laid
// on `under`.
function veilField(el, field, near, under) {
  // a colour still fading in (a framework's button taking its variant's
  // fill after hydration: GitHub's green "Code") is judged by a later pass
  if (fields.has(el) || el.hasAttribute(BLOCK) || el.hasAttribute(BRAND) || el.hasAttribute(BAR) || !near(el)
      || fading(el))
    return;
  const r = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  if (!field && (r.width > BRAND_W || r.height > BRAND_H || style.backgroundImage !== "none"))
    return;
  if (large(el) || !veilable(style.backgroundColor) || picture(style) || !(onGlass(under) || onLightCard(under)))
    return;
  el.setAttribute(BLOCK, edged(style) ? VEILED : VEILED + " " + FIELD_EDGE);
  fields.add(el);
}

// Whether a box draws an edge of its own: a border or a shadow.
function edged(style) {
  return style.boxShadow !== "none" || ["Top", "Right", "Bottom", "Left"].some((side) =>
    parseFloat(style["border" + side + "Width"]) > 0 && style["border" + side + "Style"] !== "none");
}

// Whether what a control lies on (`under` and up) is, under a light tone,
// a light card the page keeps opaque (framed: a white card with a border,
// in the page or in a shadow tree), the card itself right on the glass:
// the control is veiled too, the card showing through it, as on a card
// the glass veils.
function onLightCard(under) {
  if (tone !== "light")
    return false;
  for (let p = under; p && p !== document.body && p !== document.documentElement; p = up(p)) {
    const style = getComputedStyle(p);
    if (picture(style) || style.backgroundImage !== "none")
      return false;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return veilable(style.backgroundColor) && onGlass(up(p) || p);
  }
  return false;
}

// The pill a control sits in: the first box up from it painting
// something, PILL_DEPTH levels at most, not past a bar nor a block
// marked, at most BRAND_H tall and holding several controls, or, round a
// field, no taller than FIELD_WRAP_TALL times it (a white search form round
// its white field and button, kept opaque in a bar: ArchWiki's; Airbnb's
// three-part search bar; never a lone button's wrapper, YouTube's hidden
// white touch fill in its icon buttons). It paints with a fill of its own, or with empty
// layers laid under its content (pillLayers): the box and those layers.
// Null when that first box is no pill.
const PILL_DEPTH = 6;
const PILL_CONTROLS = 2;

function pillOf(el) {
  const h = el.getBoundingClientRect().height;
  for (let p = up(el), i = 0; p && i < PILL_DEPTH && p !== document.body; i++, p = up(p)) {
    if (p.hasAttribute(BAR) || p.hasAttribute(BLOCK))
      return null;
    const style = getComputedStyle(p);
    const layers = alpha(style.backgroundColor) >= OWN_BG || style.backgroundImage !== "none" ? [p] : pillLayers(p);
    if (!layers.length)
      continue;
    const tall = p.getBoundingClientRect().height;
    const controls = p.querySelectorAll(VEIL_FIELDS + ", " + VEIL_BUTTONS).length;
    const field = el.matches(VEIL_FIELDS) && tall <= FIELD_WRAP_TALL * h;
    return tall <= BRAND_H && (controls >= PILL_CONTROLS || field) ? {box: p, layers} : null;
  }
  return null;
}

// The empty layers a box paints with: absolute children covering it,
// holding no text nor any picture or control, and the boxes in them, in an
// opaque colour (Airbnb's search bar: a white layer holding a grey one
// shown while a field is open).
const PILL_CONTENT = "img, svg, picture, video, canvas, " + VEIL_FIELDS + ", " + VEIL_BUTTONS;

function pillLayers(p) {
  const r = p.getBoundingClientRect();
  const empty = (kid) => getComputedStyle(kid).position === "absolute" && !kid.textContent.trim()
    && !kid.querySelector(PILL_CONTENT) && covers(r, kid);
  return [...p.children].filter(empty).flatMap((kid) => [kid, ...kid.querySelectorAll("*")])
    .filter((el) => covers(r, el) && alpha(getComputedStyle(el).backgroundColor) >= OWN_BG);
}

// Whether a control's fill is one markFields veils: opaque, light (BRAND_LIGHT
// of luminance at least) and plain (under BLOCK_CHROMA of chroma).
function veilable(color) {
  const y = luminance(color);
  return alpha(color) >= SOLID && y !== null && y >= BRAND_LIGHT && chroma(color) < BLOCK_CHROMA;
}

// The box that paints a field: the field, or, the field see-through
// (under OWN_BG), the first box up from it painting a fill of its own,
// FIELD_WRAP_DEPTH levels up at most and not past a bar, holding no other
// field and at most FIELD_WRAP_TALL times its height (YouTube's search
// box: a white bordered box round a transparent input).
const FIELD_WRAP_DEPTH = 3;
const FIELD_WRAP_TALL = 2;

function fieldBox(el) {
  if (alpha(getComputedStyle(el).backgroundColor) >= OWN_BG)
    return el;
  const h = el.getBoundingClientRect().height;
  let p = up(el);
  for (let i = 0; p && i < FIELD_WRAP_DEPTH && !p.hasAttribute(BAR); i++, p = up(p)) {
    const style = getComputedStyle(p);
    if (alpha(style.backgroundColor) >= OWN_BG || style.backgroundImage !== "none")
      return p.getBoundingClientRect().height <= FIELD_WRAP_TALL * h && p.querySelectorAll(VEIL_FIELDS).length === 1
        ? p : el;
  }
  return el;
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

// Text drawn over a picture of the page's own (a dark headline on a light
// photo, a background image or a gradient) keeps the colour the page gave
// it: Dark Reader lightens the text and leaves a large light photo as it
// is (1.07:1). Just before Dark Reader runs, a text shown (shownText, the
// whole page) whose first ancestor up to the body painting anything paints
// a picture, that ancestor no page layer and at most PICTURE_H windows
// tall (not a page-wide texture), gets BRAND "text" and its colour inline
// (BRAND_INK): the glass styles paint it back. The picture's background
// image and filter are remembered (pictured): once Dark Reader changes
// them (a large light picture hidden, a small one inverted), the mark goes
// (unpicture, on each pass of the ink) and the text is inked as any. The
// marks go with the darkening.
const PICTURED = "text";
const PICTURE_H = 1.5;
let pictured = new Map();

function markPictured() {
  pictured = new Map();
  const shown = (el) => el.getBoundingClientRect().width > 0;
  for (const el of document.body ? shownText(shown) : []) {
    const owner = pictureOwner(el);
    if (!owner || el.hasAttribute(BRAND))
      continue;
    el.setAttribute(BRAND, PICTURED);
    el.style.setProperty(BRAND_INK, getComputedStyle(el).color);
    pictured.set(el, [owner, pictureLook(owner)]);
  }
}

// The ancestor painting a picture a text sits on, null if it sits on a
// plain colour first.
function pictureOwner(el) {
  const start = clipped(getComputedStyle(el)) ? up(el) : el;
  for (let p = start; p && p !== document.body && p !== document.documentElement; p = up(p)) {
    const style = getComputedStyle(p);
    if (picture(style))
      return p.hasAttribute(CANVAS) || p.getBoundingClientRect().height > PICTURE_H * window.innerHeight ? null : p;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return null;
  }
  return null;
}

function pictureLook(el) {
  const style = getComputedStyle(el);
  return style.backgroundImage + "\n" + style.filter;
}

function unpicture() {
  for (const [el, [owner, look]] of pictured) {
    if (el.isConnected && owner.isConnected && pictureLook(owner) === look)
      continue;
    pictured.delete(el);
    if (el.getAttribute(BRAND) !== PICTURED)
      continue;
    el.removeAttribute(BRAND);
    el.style.removeProperty(BRAND_INK);
    if (el.getAttribute("style") === "")
      el.removeAttribute("style");
  }
}

function unmarkBrands() {
  clears = new Map();
  pictured = new Map();
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
// down to the bottom) is one too (column), and so is a column built of
// rows of one colour (pile: Watson's clusters), every row marked. Off
// such a layer, a box of a page colour (pageBox: Heise's empty ad slots,
// narrower than the window) is glass too, CANVAS (FILL).
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

// Whether an element's background colour is still fading (a transition
// running: the site's own colour coming back once Dark Reader is off): a
// colour in between, no page layer's yet; a later pass decides.
function fading(el) {
  return el.getAnimations().some((a) => a instanceof CSSTransition && a.transitionProperty === "background-color"
    && a.playState === "running");
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
  const run = pile(el);
  return run.bottom - run.top >= COLUMN_TALL * window.innerHeight;
}

// A column built of rows: the siblings stacked with `el` in the flow
// (Watson's clusters, each a row of the feed in the page's colour, edge
// to edge down its see-through column), each painting its opaque colour
// with no picture, as wide and at the same place (within SECTION_EDGE),
// starting where the one above ends. The run is judged as one box (tall,
// column): {rows, top, bottom}, one row for an element on its own. Read
// once per pass (piles, emptied once the pass is done). A row already
// made glass counts with the colour it painted (layerColors), so the
// pile it was marked with keeps it marked.
const piles = new Map();

function rowColor(el, style) {
  return el.hasAttribute(CANVAS) && layerColors.has(el) ? layerColors.get(el) : style.backgroundColor;
}

function pile(el) {
  if (piles.has(el))
    return piles.get(el);
  if (!piles.size)
    queueMicrotask(() => piles.clear());
  const style = getComputedStyle(el), r = el.getBoundingClientRect();
  const run = {rows: [el], top: r.top, bottom: r.bottom};
  const color = rowColor(el, style);
  if (alpha(color) >= SOLID && style.backgroundImage === "none" && !LAID_OVER.has(style.position)) {
    const row = (e) => {
      const s = getComputedStyle(e), b = e.getBoundingClientRect();
      if (s.display === "none")
        return null;
      return rowColor(e, s) === color && s.backgroundImage === "none" && !LAID_OVER.has(s.position)
        && Math.abs(b.left - r.left) <= SECTION_EDGE && Math.abs(b.right - r.right) <= SECTION_EDGE ? b : false;
    };
    for (let e = el.previousElementSibling; e; e = e.previousElementSibling) {
      const b = row(e);
      if (b === false || (b && Math.abs(b.bottom - run.top) > SECTION_EDGE))
        break;
      if (b)
        run.rows.unshift(e), run.top = b.top;
    }
    for (let e = el.nextElementSibling; e; e = e.nextElementSibling) {
      const b = row(e);
      if (b === false || (b && Math.abs(b.top - run.bottom) > SECTION_EDGE))
        break;
      if (b)
        run.rows.push(e), run.bottom = b.bottom;
    }
  }
  for (const e of run.rows)
    piles.set(e, run);
  return run;
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
  // a sticky band is a bar once stuck (markBars), solid until then, or
  // glass in a plain colour (markBands: risers)
  const band = wide(el) && getComputedStyle(el).position !== "sticky";
  return (band || (tall(el) && pile(el).bottom >= (1 - COLUMN_GAP) * h)) && plain(el, color) && !stuckSide(el);
}

// Whether an element is, or is in, a sticky side column along the
// window's left or right edge (sideBar): the window's bar (markBars:
// Docker's docs' navigation under its header), never a layer of the
// page, whichever of the two passes meets it first.
function stuckSide(el) {
  const w = document.documentElement.clientWidth, h = window.innerHeight;
  for (let e = el; e && e !== document.body; e = up(e))
    if (getComputedStyle(e).position === "sticky" && sideBar(e.getBoundingClientRect(), w, h))
      return true;
  return false;
}

// A plain colour on the page's side (COLUMN_CHROMA, COLUMN_DARK,
// COLUMN_LIGHT), no picture filling the element (COLUMN_MEDIA), outside
// anything fixed. A panel on a layer (a block, a card) may be tinted a
// little more, up to `most` of chroma (BLOCK_CHROMA). With `lines`, a
// background image of thin lines only (picture: the gradients a design
// system draws its borders with, the French state's DSFR tiles) is no
// picture.
function plain(el, color, most = COLUMN_CHROMA, lines = false) {
  const w = document.documentElement.clientWidth, h = window.innerHeight;
  const r = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  if (!toned(color, most) || (lines ? picture(style) : style.backgroundImage !== "none"))
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

// A plain colour on the page's side: at most COLUMN_CHROMA of chroma (or
// `most`), darker than COLUMN_DARK on a dark page, lighter than
// COLUMN_LIGHT on a light one. The colour may be in any space the page
// computes (channels: PyPI's color(srgb ...) cards, mixed in CSS).
// Panels on a layer (markBlocks, markCards) may be tinted up to
// BLOCK_CHROMA: PyPI's #f2f8fb cards, rgb(12, 30, 39) once Dark Reader
// darkens them.
const BLOCK_CHROMA = 0.12;

function toned(color, most = COLUMN_CHROMA) {
  const c = channels(color), y = luminance(color);
  if (tone === null || !c || y === null)
    return false;
  return (Math.max(...c) - Math.min(...c)) / 255 <= most
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
  // a root or body still fading (the generic style's transition once the
  // scheme switched: the glass tint easing out) keeps the last judgement,
  // or the marks far from the window go with it; its transitionend decides
  const glass = fading(root) || fading(document.body) ? glassPage
    : (clear(root) || tinted(root)) && clear(document.body);
  glassPage = glass;
  for (const el of marked("[" + CANVAS + "]"))
    if (!glass || (!large(el) && !tall(el) && !wide(el) && el.getAttribute(CANVAS) !== FILL)) {
      el.removeAttribute(CANVAS);
      // its pseudo-element painted it (underPaint); markFills' are on bars
      if (!/^(fixed|sticky)$/.test(getComputedStyle(el).position))
        el.removeAttribute(FILLED);
    }
  if (!glass) {
    for (const el of marked("[" + FILLED + "], [" + UNDER + "], [" + SEAM + "]"))
      el.removeAttribute(FILLED), el.removeAttribute(UNDER), el.removeAttribute(SEAM);
    unfade();
    pageColors.clear();
    return;
  }
  hideBackdrops();
  const layer = (el, color) => {
    pageColors.add(color);
    layerColors.set(el, color);
    mark(el, CANVAS);
    // a faint gradient over its colour (Python's content wrapper): glass too
    fade(el, getComputedStyle(el));
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
        if (alpha(color) >= SOLID && (large(el) || column(el, color)) && !fading(el)) {
          // the other rows of its column too (pile), in view or not
          for (const row of pile(el).rows)
            if (row === el || plain(row, color))
              layer(row, color);
          found(stack, n, el);
        } else if (pageBox(el, stack, n)) {
          el.setAttribute(CANVAS, FILL);
          sections(stack, n - 1, el);
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
  markSeams();
}

// A layer's seams: a border, its own or a parent's up to the first card,
// whose every side drawn is in the layer's colour (Watson's clusters,
// 16px of the page's white down their sides, their wrapper 16px along
// its top). Drawn into the page's colour, it was as unseen as the page
// around it; on the glass it would stand as opaque strips beside the
// see-through layer: SEAM, the border see-through. Judged again after
// each pass that marks layers (markCanvas, markBands), from the layers
// marked then; a seam marked stays one while on a layer's way (its
// border reads see-through since).
const SIDES = ["Top", "Right", "Bottom", "Left"];

function seamed(el, color) {
  if (el.hasAttribute(SEAM))
    return true;
  const style = getComputedStyle(el);
  let drawn = false;
  for (const side of SIDES) {
    if (/^(none|hidden)$/.test(style["border" + side + "Style"]) || !parseFloat(style["border" + side + "Width"]))
      continue;
    if (style["border" + side + "Color"] !== color)
      return false;
    drawn = true;
  }
  return drawn;
}

function markSeams() {
  const seams = new Set();
  for (const el of marked("[" + CANVAS + "]")) {
    const color = layerColors.get(el);
    if (color === undefined)
      continue;
    for (let e = el; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      if (e !== el && alpha(rowColor(e, getComputedStyle(e))) >= CLEAR)
        break;
      if (seamed(e, color))
        seams.add(e);
    }
  }
  for (const el of marked("[" + SEAM + "]"))
    if (!seams.has(el))
      el.removeAttribute(SEAM);
  for (const el of seams)
    if (!el.hasAttribute(SEAM))
      el.setAttribute(SEAM, "");
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
// else (a white island, a blue band, a card); a box of a page colour on
// the way (pageBox: an empty ad slot) is glass, CANVAS (FILL), and the
// walk goes on above it.
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
    if (pageBox(el, stack, n)) {
      el.setAttribute(CANVAS, FILL);
      continue;
    }
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

// A box of the page's colour, of any size (Heise's empty ad slots, in the
// page's grey round a label hidden until an ad loads): an element (not a
// link, a control nor a picture: NOT_FILLS; no web component) painting
// exactly one of the page's colours (pageColors) with no picture, no edge
// (a border, a shadow, a rounded corner: a card the site outlines in the
// page's colour), no text of its own (text nodes right in it: a label, a
// heading; its children may hold some), nothing showing a picture
// (BOX_MEDIA: a product tile, an ad loaded), in the flow (not in a fixed
// or sticky element: a bar's), over nothing but its own ancestors (below
// stack[n] and at its middle: overOwn, not a cover hiding the site's
// content), its colour showing (no child filling FILL_COVER of it with
// an opaque colour: the frame of IKEA's grey service card, which is the
// card markBlocks veils). It gets CANVAS (FILL), see-through as the
// page's layer; its children keep their colours.
const BOX_MEDIA = "img, picture, video, canvas, iframe, embed, object";
const CORNERS = ["TopLeft", "TopRight", "BottomRight", "BottomLeft"];

function pageBox(el, stack, n) {
  if (el.hasAttribute(KEPT) || el.hasAttribute(CANVAS) || el.shadowRoot || NOT_FILLS.has(el.localName)
      || el.localName === "a")
    return false;
  const style = getComputedStyle(el);
  if (style.backgroundImage !== "none" || alpha(style.backgroundColor) < SOLID || !pageColors.has(style.backgroundColor)
      || style.boxShadow !== "none" || CORNERS.some((c) => parseFloat(style["border" + c + "Radius"]) > 0)
      || ["Top", "Right", "Bottom", "Left"].some((side) => style["border" + side + "Style"] !== "none"
        && parseFloat(style["border" + side + "Width"]) > 0))
    return false;
  for (const node of el.childNodes)
    if (node.nodeType === Node.TEXT_NODE && node.data.trim())
      return false;
  if (el.querySelector(BOX_MEDIA))
    return false;
  const r = el.getBoundingClientRect();
  for (const kid of el.children) {
    const k = kid.getBoundingClientRect();
    if (alpha(getComputedStyle(kid).backgroundColor) >= SOLID && k.width * k.height >= FILL_COVER * r.width * r.height)
      return false;
  }
  for (let e = el; e && e !== document.body; e = up(e))
    if (/^(fixed|sticky)$/.test(getComputedStyle(e).position))
      return false;
  return stack.slice(n + 1).every((under) => holds(under, el)) && overOwn(el, r);
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
// A colour in a computed value: rgb(), or a colour space the page computes
// (Discourse's fade to color(srgb 1 1 1), an oklch() design token).
const PAINT = /\b(?:rgba?|color|hsla?|oklch|oklab|lch|lab)\([^)]*\)/g;
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
// bar, each element once per pass (`seen`), and so are the elements in a
// bar (FILL_NODES each), whose fades hold no text (a row of links fading
// out under its scroll button: Tages-Anzeiger's): a pseudo-element that
// fades is named in FADE_PSEUDO, its gradient see-through where it
// painted the page's colour in FADE_IMAGE and its name
// (--browserglass-fade-after), inline: the glass styles paint it instead.
// Taken off with the page's layers (unfade). In a bar, and in a sticky
// row glass in the flow (risers), a fade into the bar's colour (barColors)
// is see-through too, a button fillBar cleared included (the arrow of
// NZZ's row of sections, fading the links out under it into black on its
// grey page), read again in the bar's colours when the text in it was
// read on the way up. One painting an opaque
// colour near the page's (pageColor) straight on the glass (onGlass: no
// background of the site's own under it) is a strip of the page's
// background left over the glass (the gutters a section draws down its
// sides in the page's colour: Tages-Anzeiger's lead story) and gets
// FILLED, see-through, as a fixed element's (markFills); one on a card or
// a band of another colour keeps its colour. So does an empty element
// beside the way up (clearStrips).
function fadePseudos(el, seen) {
  if (!pageColors.size)
    return;
  for (let p = el; p && p !== document.body && p !== document.documentElement && !seen.has(p); p = up(p)) {
    seen.add(p);
    clearPseudos(p);
    clearStrips(p);
    if (p.hasAttribute(CANVAS) || p.hasAttribute(BAR))
      break;
  }
}

function barPseudos() {
  if (!pageColors.size)
    return;
  for (const bar of [...marked("[" + BAR + "]"), ...risers]) {
    const colors = [...(barColors.get(bar) || [])];
    const ours = (color) => pageColor(color) || colors.some((c) => near(c, color));
    const kids = inside(bar);
    for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
      const el = kids[i];
      if (!NOT_FILLS.has(el.localName) || el.getAttribute(CANVAS) === FILL)
        clearPseudos(el, ours);
    }
  }
}

function clearPseudos(p, ours = pageColor) {
  const fading = p.getAttribute(FADE_PSEUDO) || "", filling = p.getAttribute(FILLED) || "";
  for (const pseudo of PSEUDOS) {
    if (fading.includes(pseudo) && filling.includes(pseudo))
      continue;
    const style = getComputedStyle(p, "::" + pseudo);
    if (style.content === "none" || style.display === "none")
      continue;
    if (!fading.includes(pseudo) && fades(style, ours)) {
      p.style.setProperty(FADE_IMAGE + "-" + pseudo, faded(style.backgroundImage, ours));
      p.setAttribute(FADE_PSEUDO, ((p.getAttribute(FADE_PSEUDO) || "") + " " + pseudo).trim());
    }
    const color = style.backgroundColor;
    if (!filling.includes(pseudo) && alpha(color) >= SOLID && ours(color) && onGlass(p))
      p.setAttribute(FILLED, ((p.getAttribute(FILLED) || "") + " " + pseudo).trim());
  }
}

// An empty element (no element in it, no text) among the first
// FILL_NODES children of `p`, painting an opaque colour near the page's
// (pageColor) with nothing else, straight on the glass (onGlass: no
// background of the site's own under `p`) and over nothing but its own
// ancestors and the page's layers at its middle (overOwn: not a cover
// hiding the site's content) is a strip of the page's background left
// over the glass (the band a section draws over its top in the page's
// colour: Tages-Anzeiger's whitecover above each story). It gets CANVAS (FILL), see-through as a
// label on the page's layer is (label), and loses it with the page's
// layers. So does a flat icon button there (iconButton: the arrow of
// Heise's news ticker, over the headlines scrolling under it, an opaque
// square of the page's colour on the glass), its icon kept, over the
// site's content too: a control, not a cover.
function clearStrips(p) {
  const kids = layered(p);
  let glass = null;
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    if (el.shadowRoot || el.textContent.trim() || el.hasAttribute(CANVAS))
      continue;
    const style = getComputedStyle(el);
    const icon = iconButton(el, style);
    if (!icon && (el.firstElementChild || NOT_FILLS.has(el.localName)))
      continue;
    if (style.backgroundImage !== "none" || alpha(style.backgroundColor) < SOLID || !pageColor(style.backgroundColor))
      continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0)
      continue;
    if (glass === null)
      glass = onGlass(p);
    if (glass && (icon || overOwn(el, r)))
      el.setAttribute(CANVAS, FILL);
  }
}

// A flat icon button: a button with no text (an icon, or nothing), no
// shadow and no rounded corner (a round or shadowed one floats over the
// content on purpose: a carousel's arrow over its photos).
const ICON_BUTTONS = "button, [role=button]";

function iconButton(el, style) {
  return el.matches(ICON_BUTTONS) && !el.textContent.trim() && style.boxShadow === "none"
    && CORNERS.every((c) => !(parseFloat(style["border" + c + "Radius"]) > 0));
}

// Whether `el` lies over nothing but its own ancestors and layers of the
// page's background (CANVAS: a backdrop sibling in the page's colour,
// Spiegel's band under its headlines) at the middle of its box `r`; false
// when that is out of the window (read once there).
function overOwn(el, r) {
  const x = (r.left + r.right) / 2, y = (r.top + r.bottom) / 2;
  if (x < 0 || y < 0 || x >= window.innerWidth || y >= window.innerHeight)
    return false;
  const stack = stackAt(x, y), n = stack.indexOf(el);
  if (n < 0)
    return false;
  const ancestors = new Set();
  for (let a = up(el); a; a = up(a))
    ancestors.add(a);
  return stack.slice(n + 1).every((under) => ancestors.has(under) || under.hasAttribute(CANVAS));
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
// its own). A sidebar holding the site's menus (siteChrome, siteMenus:
// YouTube's guide, a docs site's navigation) is a bar see-through too, over
// nothing: the chrome's one veil, never bare glass beside the content.
const EDGE = 2;
// how far off the window's edge a sidebar may stand (the margin of a docs
// site's page: Python's sticky navigation 16px in)
const SIDE_GUTTER = 24;
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
  if (!root || off !== false || !document.body) {
    liftHeads();
    return;
  }
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
        || sideBar(r, w, h));
  };
  const backed = (el) => {
    if (alpha(getComputedStyle(el).backgroundColor) >= OWN_BG || risers.has(el))
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
  // a pinned bar along an edge
  const take = (el) => {
    // a bar markFloats took as a layer before the bar it is stacked
    // against was marked (Apple's nav under its locale banner): a bar
    if (floats.delete(el))
      rows.push(el.getBoundingClientRect());
    if (!el.hasAttribute(BAR) && (backed(el) || (!blank(el) && (over(el, w, h) || navSide(el, w, h))))) {
      barColors.set(el, new Set([...(barColors.get(el) || []), ...painted(el), ...rowColors(el)]));
      mark(el, BAR);
      rows.push(el.getBoundingClientRect());
    }
  };
  // a pinned bar along an edge at a point; under a side drawer taken
  // there, the page's own fixed sidebar it covers too (its links would
  // show through the drawer's veil bare)
  const probe = (px, py) => {
    let drawer = null;
    for (const el of stackAt(px, py)) {
      if (el === root || el === document.body)
        break;
      if (drawer) {
        if (!holds(el, drawer) && !holds(drawer, el) && pinned(el)
            && sideBar(el.getBoundingClientRect(), w, h) && along(el)) {
          take(el);
          break;
        }
      } else if (along(el) && pinned(el)) {
        take(el);
        if (!sideBar(el.getBoundingClientRect(), w, h))
          break;
        drawer = el;
      }
    }
  };
  // a marked bar shows the veil, not its own background: only its place
  // is checked again
  const kept = marked("[" + BAR + "]").filter((el) => !floats.has(el));
  rows.push(...kept.map((el) => el.getBoundingClientRect()));
  for (const el of kept)
    if (!(((pinned(el) || (heads.has(el) && headShape(el, w, h, false))) && along(el))
        || (heads.has(el) && (underHead(el, w, h) || el === slotHead(w, h))))
        || (blank(el) && !(barColors.get(el) || new Set()).size)) {
      el.removeAttribute(BAR);
      heads.delete(el);
    }
  rows.length = 0;
  const covers = new Map();
  // a modal makes the page inert: no hit test reaches its bars, they are
  // looked for by their style too (inertBars)
  const under = pageInert(w) ? inertBars(pinned) : [];
  for (const el of under)
    markHead(el, w, h, pinned);
  for (let i = 0; i < GRID; i++)
    markHead(unwalled(stackAt((i + 0.5) * w / GRID, EDGE), w, h, covers), w, h, pinned);
  // a header inside a bar (Galaxus's, in its sticky wrapper) has the
  // bar's veil already: marked on each pass, it would strip its fields'
  const low = slotHead(w, h);
  if (low && !inBar(low) && !floats.has(low))
    markHeadAs(low);
  underHeads(w, h, covers);
  rows.push(...marked("[" + BAR + "]").map((el) => el.getBoundingClientRect()));
  for (const el of under)
    if (pinned(el) && along(el))
      take(el);
  for (let i = 0; i < GRID; i++) {
    const x = (i + 0.5) * w / GRID, y = (i + 0.5) * h / GRID;
    // a sidebar may stand in a gutter (SIDE_GUTTER) off the window's edge
    for (const [px, py] of [[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y],
      [SIDE_GUTTER + EDGE, y], [w - SIDE_GUTTER - EDGE, y]])
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
  // and under the pinned bars found then
  underHeads(w, h, covers);
  // one veil per bar: an inner one marked before its outer one was in place
  const bars = marked("[" + BAR + "]").filter((el) => !floats.has(el));
  for (const el of bars)
    if (outer(el, "[" + BAR + "]"))
      el.removeAttribute(BAR);
  // a bar in a shadow tree refers to a veil of its own tree
  for (const el of bars)
    if (el.getRootNode() !== document && el.hasAttribute(BAR))
      veil(el.getRootNode());
  const shown = bars.filter((el) => el.hasAttribute(BAR));
  tuckBars(shown, tuckedRows(shown, pinned), w, h);
  if (glassPage)
    for (const el of bars)
      if (el.hasAttribute(BAR))
        fillBar(el);
  // a side drawer's sections in a colour of their own
  if (glassPage)
    for (const el of bars)
      if (el.hasAttribute(BAR) && sideBar(el.getBoundingClientRect(), w, h))
        fillSections(el);
  settleRisers();
  markFloats();
}

// Whether the page is inert under a modal, left out of every hit test
// (elementsFromPoint lists the modal and the root alone): a modal dialog
// (showModal) is open, or an inert element across the window at its top
// (Booking's page root, made inert under its own sheet).
// shortcut: a modal dialog in a shadow tree is not seen; look in shadows
// if a site opens one there.
function pageInert(w) {
  if (document.querySelector("dialog:modal"))
    return true;
  for (const el of document.querySelectorAll("[inert]")) {
    const r = el.getBoundingClientRect();
    if (r.width >= 0.6 * w && r.top <= EDGE && r.bottom > EDGE)
      return true;
  }
  return false;
}

// The page's bars under a modal, found by their style instead of a hit
// test: its fixed or sticky elements and its headers (HEAD_BLOCKS), in
// the INERT_SCAN first elements of the body at most, none in a dialog.
const INERT_SCAN = 4000;

function inertBars(pinned) {
  const found = [];
  const all = document.body.getElementsByTagName("*");
  for (let i = 0; i < all.length && i < INERT_SCAN; i++) {
    const el = all[i];
    if (!el.closest("dialog, [role=dialog], [aria-modal=true]") && (el.matches(HEAD_BLOCKS) || pinned(el)))
      found.push(el);
  }
  return found;
}

// A bar's blur is painted by its ::before (the content layers), which
// needs the bar positioned: a static one (a header in the flow, a dialog's
// box in its backdrop) is made relative while marked. A header in the flow
// given the veil (heads) becomes a stacking context of its own (isolated),
// at the page's level: what it holds floating at a z-index of its own
// (IKEA's search suggestions) would paint under the page's positioned
// content after it (IKEA's row of category pills). Such a header, with no
// z-index, is lifted to the highest z-index of what it holds (headZ: its
// fixed header and menus at 25 stay over a hero at 10, Figma), HEAD_Z at
// least. A static bar holding an absolute part placed by an element outside
// it (Apple's nav, 100% of the window wide) is left static, that part not
// shrunk to the bar (FLAT): it keeps the veil's colour, its blur left out
// (a ::before would be placed by that outside element, a backdrop-filter
// on the bar would place that part again).
// Inline; their own values come back once they are no bar any more, or the
// add-on is off.
const HEAD_Z = 1;
const lifts = new Map();

// The highest z-index of the positioned elements an element holds, HEAD_Z
// at least.
function headZ(el) {
  let z = HEAD_Z;
  for (const part of el.querySelectorAll("*")) {
    const style = getComputedStyle(part);
    if (style.position !== "static")
      z = Math.max(z, parseInt(style.zIndex, 10) || 0);
  }
  return String(z);
}

// Whether an element holds an absolute part placed by an element outside
// it: making it relative would move or resize that part.
function escapes(el) {
  for (const part of el.querySelectorAll("*"))
    if (getComputedStyle(part).position === "absolute" && part.offsetParent && !el.contains(part.offsetParent))
      return true;
  return false;
}

function liftHeads() {
  for (const [el, was] of lifts)
    if (off !== false || !el.isConnected || !el.hasAttribute(BAR)) {
      for (const [name, value, priority] of was)
        value ? el.style.setProperty(name, value, priority) : el.style.removeProperty(name);
      lifts.delete(el);
    }
  for (const el of marked("[" + FLAT + "]"))
    if (off !== false || !el.hasAttribute(BAR))
      el.removeAttribute(FLAT);
  if (off !== false)
    return;
  for (const el of marked("[" + BAR + "]")) {
    // a lifted header's z-index follows what it holds now: a sheet or a
    // flyout the site adds later at a higher one stays over the page
    if (lifts.has(el) && heads.has(el) && el.style.getPropertyValue("z-index")) {
      const z = headZ(el);
      if (el.style.getPropertyValue("z-index") !== z)
        el.style.setProperty("z-index", z, "important");
    }
    if (lifts.has(el) || el.hasAttribute(FLAT))
      continue;
    const style = getComputedStyle(el);
    const head = heads.has(el) && /^(static|relative)$/.test(style.position) && style.zIndex === "auto";
    if (style.position !== "static" && !head)
      continue;
    if (style.position === "static" && escapes(el)) {
      el.setAttribute(FLAT, "");
      continue;
    }
    lifts.set(el, ["position", "z-index"].map((name) =>
      [name, el.style.getPropertyValue(name), el.style.getPropertyPriority(name)]));
    if (style.position === "static")
      el.style.setProperty("position", "relative", "important");
    if (head)
      el.style.setProperty("z-index", headZ(el), "important");
  }
}

// The site's header at the top of the page (heads): in the flow, or
// sticky (or fixed) before anything scrolls under it, it gets the bar's
// veil too, even see-through, never bare glass at the top and a veil only
// once scrolled. Up from the element on top at a point of the top edge,
// the outermost element shaped as a header (headShape) holding the site's
// menus (siteMenus: its own header or nav, or one inside it, a web
// component's in its shadow tree), shown. Its rows across it in a colour
// of their own (a promo strip, a brand row, a white nav row) are
// see-through with the bar's (rowColors, fillBar): one veil; its buttons
// and logos keep their colours.
const heads = new Set();

function markHead(top, w, h, pinned) {
  let pick = null, menus = false;
  for (let el = top; el && el !== document.body && el !== document.documentElement; el = up(el)) {
    menus = menus || siteChrome(el);
    if (headShape(el, w, h, pinned(el)))
      pick = el;
  }
  if (!pick || pick.hasAttribute(BAR) || floats.has(pick) || !(menus || siteMenus(pick) || linkRow(pick))
      || !pick.checkVisibility({visibilityProperty: true, opacityProperty: true}))
    return;
  markHeadAs(pick);
}

// The site's header in the flow under a slot at the top of the page (NZZ's:
// an ad's placeholder 258px high, empty or not, above it): the page's
// first header (HEAD_BLOCKS) outside its main content and its dialogs,
// across the window, low (BAND_LOW), holding the site's menus, shown, its
// top HEAD_SLOT of the window's height at most from the page's top. It
// gets the veil itself, its white container's colour see-through
// (rowColors), never that container's lighter block veil alone.
const HEAD_SLOT = 0.5;

function slotHead(w, h) {
  const el = [...document.querySelectorAll(HEAD_BLOCKS)]
    .find((e) => !e.closest("main, article, [role=main], dialog, [role=dialog], [aria-modal=true]"));
  if (!el)
    return null;
  const r = el.getBoundingClientRect();
  const fits = r.width >= 0.6 * w && r.height >= BAR_MIN && r.height <= BAND_LOW * h
    && r.top + window.scrollY <= HEAD_SLOT * h && /^(static|relative)$/.test(getComputedStyle(el).position);
  return fits && siteMenus(el) && el.checkVisibility({visibilityProperty: true, opacityProperty: true}) ? el : null;
}

// The headers and rows in the flow under a bar at the top (underHead).
function underHeads(w, h, covers) {
  for (const el of document.querySelectorAll(HEAD_BLOCKS))
    if (!el.hasAttribute(BAR) && underHead(el, w, h))
      markHeadAs(el);
  markUnder(w, h, covers);
}

// A header given the veil: its rows' colours see-through (rowColors), the
// lighter veils Dark Reader's blocks got in it gone (markBlocks leaves
// what a bar holds alone, as in a pinned bar).
function markHeadAs(el) {
  // the fields' veils (markFields) stay: a field is veiled in a bar too, and
  // a header under a bar is marked again on each pass (underHeads)
  for (const b of [el, ...el.querySelectorAll("[" + BLOCK + "]")])
    if (!fields.has(b))
      b.removeAttribute(BLOCK);
  barColors.set(el, new Set([...(barColors.get(el) || []), ...painted(el), ...rowColors(el)]));
  mark(el, BAR);
  heads.add(el);
}

// A row of the site's links with no nav around them (Arch Linux's
// archnavbar: a list of LINK_ROW links at least).
const LINK_ROW = 3;

function linkRow(el) {
  return el.querySelectorAll("li a[href]").length >= LINK_ROW;
}

// The element on top in a stack once what lies in a wrapper over the
// whole window (windowCover, fixed: a consent wall, a dialog's backdrop)
// is set aside: the header under it. `covers` caches the verdicts.
function unwalled(stack, w, h, covers) {
  const covered = (el) => {
    if (!el || el === document.body || el === document.documentElement)
      return false;
    if (!covers.has(el)) {
      const style = getComputedStyle(el);
      covers.set(el, (style.position === "fixed" && windowCover(el, style, w, h)) || covered(up(el)));
    }
    return covers.get(el);
  };
  return stack.find((el) => !covered(el));
}

// A row in the flow right under a bar at the top of the window, or a
// header under it (the
// mega-menu row under Swissinfo's sticky header, GitHub's repository
// header under its top bar), near the page's top: a header too
// (underHead). Up from the element on top just under the bar, the
// outermost one whose top is the bar's bottom, BAND_LOW low at most.
function markUnder(w, h, covers) {
  for (const bar of marked("[" + BAR + "]")) {
    const b = bar.getBoundingClientRect();
    if (floats.has(bar) || (b.top > EDGE && !heads.has(bar)) || b.bottom + EDGE >= h)
      continue;
    for (let i = 0; i < GRID; i++) {
      let pick = null;
      const top = unwalled(stackAt(b.left + (i + 0.5) * b.width / GRID, b.bottom + EDGE), w, h, covers);
      for (let el = top; el && el !== document.body && el !== document.documentElement && !holds(el, bar); el = up(el)) {
        const r = el.getBoundingClientRect();
        if (Math.abs(r.top - b.bottom) <= EDGE && r.height <= BAND_LOW * h && r.top + window.scrollY <= BAND_LOW * h)
          pick = el;
      }
      if (pick && !pick.hasAttribute(BAR) && !floats.has(pick) && underHead(pick, w, h))
        markHeadAs(pick);
    }
  }
}

// The shape of a header at the top: across the window, low (BAND_LOW),
// its top at the top of the page, or at the window's top edge when held
// there (fixed, sticky).
function headShape(el, w, h, held) {
  const r = el.getBoundingClientRect();
  return r.width >= 0.6 * w && r.height >= BAR_MIN && r.height <= BAND_LOW * h && r.top <= EDGE
    && (held || r.top + window.scrollY <= EDGE);
}

// A header in the flow right under the header at the top (heads), as
// wide, holding the site's menus, at most the window's height, outside
// the page's main content (Python's: a strip of site links, then its
// brand header holding the main menu and a hero): the bar's veil too, one
// chrome. Its hero's own panels keep their fills (not rows of it).
// shortcut: compared in the window, so a header under a sticky one loses
// the veil once scrolled under it; fine for headers in the flow.
const HEAD_BLOCKS = "header, [role=banner]";

function underHead(el, w, h) {
  const r = el.getBoundingClientRect();
  if (r.width < 0.6 * w || r.height < BAR_MIN || r.height > h || el.closest("main, article, [role=main]")
      || !/^(static|relative)$/.test(getComputedStyle(el).position) || !siteMenus(el))
    return false;
  for (const bar of marked("[" + BAR + "]"))
    if (bar !== el && !floats.has(bar) && !holds(el, bar) && Math.abs(bar.getBoundingClientRect().bottom - r.top) <= EDGE)
      return true;
  return false;
}

function siteMenus(el) {
  return !!(el.querySelector(BAND_MENUS) || (el.shadowRoot && el.shadowRoot.querySelector(BAND_MENUS)));
}

// The colours of a bar's rows: an element inside it across FILL_COVER of
// its width, or ROW_COVER of it and as tall as the bar (a page column's
// row: Swissinfo's mega-menu row, 86 % of its row; not a hero's panel),
// opaque, shown, neither a control nor kept for its text.
const ROW_COVER = 0.8;

function rowColors(bar) {
  const box = bar.getBoundingClientRect();
  const colors = [];
  const kids = inside(bar);
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    if (NOT_FILLS.has(el.localName) || el.matches(BRANDS) || el.hasAttribute(KEPT))
      continue;
    const r = el.getBoundingClientRect();
    const color = getComputedStyle(el).backgroundColor;
    const across = r.width >= FILL_COVER * box.width
      || (r.width >= ROW_COVER * box.width && r.height >= FILL_COVER * box.height);
    if (across && r.height > 0 && within(r, box) && alpha(color) >= SOLID
        && el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      colors.push(color);
  }
  return colors;
}

// Floating layers: a menu, a mega menu, a popover, a drawer, a dialog, a
// cookie banner laid over the page get the bar's veil too (BAR), never
// bare glass (their text printed over the page's) nor the site's opaque
// panel. One is found at FLOAT_GRID by FLOAT_GRID points over the window:
// up from the element on top there, the outermost one lifted over the
// page (lifted), shown, holding text, FLOAT_AREA large at least, not one
// a bar would take (fixed along an edge: markBars). A wrapper lifted over
// the whole window (a dialog's, a z-index above the page) is skipped for
// its panel on the way down to the point. A scrim holds no text and is
// left alone, and so are the cards of the page (not lifted). The layer's
// rows in its colour are see-through (fillBar): one veil. A layer no
// longer shown loses the mark. Also run on pointerover (hover menus).
const FLOAT_GRID = 8;
const FLOAT_AREA = 96 * 96;
const FLOAT_WINDOW = 0.9;
const FLOAT_ROLES = "[role=dialog], [role=alertdialog], [role=menu], [role=listbox], [aria-modal=true]";
const floats = new Set();

function markFloats() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  const w = root.clientWidth, h = window.innerHeight;
  for (const el of floats)
    if (!el.isConnected || !el.hasAttribute(BAR) || !shownFloat(el)) {
      el.removeAttribute(BAR);
      floats.delete(el);
    }
  overs.clear();
  const found = new Set(tips());
  for (let i = 0; i < FLOAT_GRID; i++)
    for (let j = 0; j < FLOAT_GRID; j++) {
      const top = stackAt((i + 0.5) * w / FLOAT_GRID, (j + 0.5) * h / FLOAT_GRID)[0];
      const layer = top && floatOf(top, w, h);
      if (layer)
        found.add(layer);
    }
  const all = [...floats, ...found];
  for (const el of all) {
    // one veil per layer: the outermost, but a panel of it laid mostly
    // beside its box (python.org's side panel by its menu) gets its own:
    // the layer's veil stops at its box
    if (all.some((o) => o !== el && holds(o, el) && !beside(el, o))) {
      if (floats.delete(el))
        el.removeAttribute(BAR);
      continue;
    }
    if (!floats.has(el)) {
      // made see-through as a row of the bar it hangs from: the veil now
      el.removeAttribute(CANVAS);
      barColors.set(el, new Set([...(barColors.get(el) || []), ...painted(el)]));
      mark(el, BAR);
      floats.add(el);
      if (el.getRootNode() !== document)
        veil(el.getRootNode());
    }
    fillBar(el);
    fillSections(el);
    clearBacking(el);
  }
  liftHeads();
}

// Whether a part of a layer lies mostly (BESIDE of its area) out of the
// layer's box.
const BESIDE = 0.5;

function beside(part, layer) {
  const a = part.getBoundingClientRect(), b = layer.getBoundingClientRect();
  const x = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const y = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return x * y < (1 - BESIDE) * a.width * a.height;
}

// A layer's backing: an empty panel the site lays apart behind it (no
// text, often inert: Digitec's white search panel behind its suggestion
// list, across the window), absolute or fixed, opaque, covering the
// layer, in one of its FLOAT_BACKING nearest parents. It is see-through
// (CANVAS FILL): the layer's veil is the one surface there, not a veil
// over the site's opaque slab.
const FLOAT_BACKING = 3;

function clearBacking(layer) {
  const box = layer.getBoundingClientRect();
  let p = up(layer);
  for (let n = 0; n < FLOAT_BACKING && p && p !== document.body; n++, p = up(p))
    for (const el of layered(p)) {
      if (holds(el, layer) || el.hasAttribute(CANVAS) || el.hasAttribute(BAR) || texted(el)
          || !/^(absolute|fixed)$/.test(getComputedStyle(el).position))
        continue;
      const paint = paintOf(el);
      if (paint && !paint.pseudo && within(box, el.getBoundingClientRect()) && !scrim(el)
          && el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
        el.setAttribute(CANVAS, FILL);
    }
}

// A scrim: the site's dimming layer, over the whole window, faded
// (opacity) or in a see-through colour; it keeps its colour.
function scrim(el) {
  const style = getComputedStyle(el), r = el.getBoundingClientRect();
  const root = document.documentElement;
  return parseFloat(style.opacity) < 1 || alpha(style.backgroundColor) < SOLID
    || (r.width >= FLOAT_WINDOW * root.clientWidth && r.height >= FLOAT_WINDOW * window.innerHeight);
}

function shownFloat(el) {
  const r = el.getBoundingClientRect();
  return r.width * r.height >= (tipped.has(el) ? TIP_AREA : FLOAT_AREA)
    && el.checkVisibility({visibilityProperty: true, opacityProperty: true}) && textShown(el);
}

// Toasts and tooltips: too small for the grid (FLOAT_AREA), laid in the
// body (one of its children, or theirs, or in their shadow trees), fixed
// or absolute at a z-index of TIP_Z at least (over the page's own panels
// laid at 10) or with a tooltip's or a status' role, TIP_AREA large at
// least, holding
// text and painted in an opaque plain colour of their own (at most
// BLOCK_CHROMA: not a brand's chat button, not a control). Each one is a
// floating layer (tipped).
const TIP_AREA = 40 * BAR_MIN;
const TIP_Z = 20;
const TIP_ROLES = "[role=tooltip], [role=status], [role=alert]";
const tipped = new WeakSet();

function tips() {
  const found = [];
  const look = (el, depth) => {
    for (const kid of layered(el)) {
      if (tip(kid)) {
        tipped.add(kid);
        found.push(kid);
      } else if (depth)
        look(kid, depth - 1);
    }
  };
  look(document.body, 1);
  return found;
}

function tip(el) {
  if (el.hasAttribute(BAR) && !floats.has(el))
    return false;
  const style = getComputedStyle(el);
  const z = parseInt(style.zIndex, 10);
  if (!/^(absolute|fixed)$/.test(style.position) || !(z >= TIP_Z || (z > 0 && el.matches(TIP_ROLES)))
      || style.backgroundImage !== "none" || alpha(style.backgroundColor) < SOLID
      || chroma(style.backgroundColor) > BLOCK_CHROMA || el.matches(FIELD_BOXES + ", a"))
    return false;
  const r = el.getBoundingClientRect();
  return r.width * r.height >= TIP_AREA && r.width * r.height < FLOAT_AREA && r.bottom > 0 && r.right > 0
    && el.checkVisibility(SHOWN) && texted(el) && textShown(el);
}

// Whether some text in an element is shown: a menu its site hides by its
// content's opacity or visibility (Shopify's mega menu, its wrapper left
// as it was) is closed. Text in a shadow tree counts as shown.
const SHOWN = {visibilityProperty: true, opacityProperty: true};

function textShown(el) {
  if (el.shadowRoot)
    return true;
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let node = walk.nextNode(); node; node = walk.nextNode())
    if (node.data.trim() && node.parentElement.checkVisibility(SHOWN))
      return true;
  // the text a slot of it shows (Reddit's user menu, slotted from the page)
  return slotted(el).some((node) => node.nodeType === Node.TEXT_NODE
    ? !!node.data.trim() && !!node.parentElement && node.parentElement.checkVisibility(SHOWN)
    : node.nodeType === Node.ELEMENT_NODE && textShown(node));
}

// The nodes the slots in a shadow tree's element show, from the page.
function slotted(el) {
  if (el.getRootNode() === document)
    return [];
  const slots = [...el.querySelectorAll("slot")];
  if (el.localName === "slot")
    slots.push(el);
  return slots.flatMap((slot) => slot.assignedNodes({flatten: true}));
}

// The floating layer the element on top at a point lies in, null if none.
// The way up ends at a bar (markBars): a flyout hanging out of it (Apple's
// search under its nav) is a layer of its own, the bar never one; a list
// lying within the bar's box is on the bar's veil already, none, unless it
// covers the bar's own text (Discourse's "More" menu over its sidebar).
function floatOf(el, w, h) {
  const chain = [];
  let bar = null;
  for (let p = el; p && p !== document.body && p !== document.documentElement; p = up(p)) {
    if (p.hasAttribute(BAR) && !floats.has(p)) {
      bar = p;
      break;
    }
    chain.push(p);
  }
  let pick = null;
  chain.forEach((p, k) => {
    const style = getComputedStyle(p);
    // a painted layer holding a panel laid mostly beside its box: the panel
    // stays a layer of its own (markFloats gives it its own veil)
    if (!lifted(p, style) || (pick && painting(p) && beside(pick, p)))
      return;
    const r = p.getBoundingClientRect();
    // the panel in it: the outermost one large and less than the window
    // that paints itself (GitLab's search box, not the see-through column
    // around it as tall as the window), else the outermost one so large
    const panels = chain.slice(0, k).reverse().filter((q) => {
      const b = q.getBoundingClientRect();
      return b.width * b.height >= FLOAT_AREA && (b.width < FLOAT_WINDOW * w || b.height < FLOAT_WINDOW * h);
    });
    const paints = panels.find(painting);
    // a see-through panel holding a painted one is left to that one
    const holder = (q) => !painting(q) && layered(q).some((kid) => {
      const b = kid.getBoundingClientRect();
      return b.width * b.height >= FLOAT_AREA && painting(kid);
    });
    const panel = () => paints || panels.find((q) => !holder(q)) || pick;
    if (r.width >= FLOAT_WINDOW * w && r.height >= FLOAT_WINDOW * h) {
      if (windowCover(p, style, w, h) || (paints && seeThroughCover(chain.slice(0, k + 1))))
        pick = panel();
      // a drawer its expanded button shows, in the flow of the header
      // and taller than the window (admin.ch)
      else if (style.position === "static" && painting(p))
        pick = p;
      return;
    }
    // a positioner smaller than what it holds (Galaxus' header popovers)
    if (r.width * r.height < FLOAT_AREA) {
      pick = panel();
      return;
    }
    // left to markBars, unless a see-through positioner shaped as a bar
    // holding its painted panel (Galaxus' popovers, at the window's right)
    if (style.position === "fixed" && edgeBar(r, w, h) && !(paints && holder(p)))
      return;
    // a see-through positioner around its painted box (a popover's, a
    // popup's in a shadow tree): the box
    const b = paints && paints.getBoundingClientRect();
    if (!painting(p) && b && b.width * b.height >= FILL_COVER * r.width * r.height)
      pick = paints;
    else if (!holder(p))
      pick = p;
    // a see-through positioner holding its painted panel, in the flow
    // itself (Galaxus' header popovers, the French state's DSFR mega
    // menus): the panel, never left opaque
    else if (paints)
      pick = paints;
  });
  if (pick && bar && within(pick.getBoundingClientRect(), bar.getBoundingClientRect()) && !overText(pick, bar))
    return null;
  return pick && shownFloat(pick) && texted(pick) ? pick : null;
}

// Whether a layer lies over text of the bar it is in, its own aside.
// The parts not rendered (the closed menus of a long nav, python.org's)
// are skipped whole, and only the text counts against FILL_NODES: the
// text under the layer (a hero the bar holds) is reached.
function overText(layer, bar) {
  const r = layer.getBoundingClientRect();
  const skip = (node) => node.nodeType === Node.ELEMENT_NODE && (node === layer || !node.checkVisibility())
    ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
  const walk = document.createTreeWalker(bar, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, skip);
  const range = document.createRange();
  for (let n = 0, node = walk.nextNode(); node && n < FILL_NODES; node = walk.nextNode()) {
    if (node.nodeType !== Node.TEXT_NODE || !node.data.trim())
      continue;
    n++;
    range.selectNodeContents(node);
    const t = range.getBoundingClientRect();
    if (t.width && t.height && t.left < r.right && t.right > r.left && t.top < r.bottom && t.bottom > r.top)
      return true;
  }
  return false;
}

// Whether an element paints a panel: in an opaque colour of its own
// (paintOf), or did before it was made see-through (CANVAS: a layer of
// the page's colour, a row of a bar) or given the veil (a float).
function painting(el) {
  return floats.has(el) || el.hasAttribute(CANVAS) || !!paintOf(el);
}

// Whether an element is lifted over the page: fixed, an open modal
// <dialog>, absolute with a floating role, laid over the page (overPage)
// or hanging BAR_MIN out of the site's chrome it is in (a menu dropping
// from a header), or a painted drawer in that chrome its button shows.
function lifted(el, style) {
  if (style.position === "fixed" || el.matches("dialog:modal"))
    return true;
  const position = style.position;
  if (position === "static" ? !revealedBy(el) || !painting(el) : position !== "absolute")
    return false;
  if (position === "absolute" && (el.matches(FLOAT_ROLES) || revealed(el) || overPage(el, style)))
    return true;
  let chrome = up(el);
  while (chrome && chrome !== document.body && !siteChrome(chrome)
         && !(chrome.hasAttribute(BAR) && !floats.has(chrome)))
    chrome = up(chrome);
  if (!chrome || chrome === document.body)
    return false;
  // a painted drawer in the site's chrome its button names expanded, laid
  // in the flow of the header (admin.ch's authorities drawer)
  if (position === "static")
    return true;
  const r = el.getBoundingClientRect(), c = chrome.getBoundingClientRect();
  return r.bottom > c.bottom + BAR_MIN || r.top < c.top - BAR_MIN
    || r.right > c.right + BAR_MIN || r.left < c.left - BAR_MIN;
}

// A wrapper over the whole window around a floating layer: lifted over
// the page (a z-index), a <dialog>, a floating role (Ars Technica's
// consent wall), or a scrim (a see-through colour of its own: GitHub's
// dialog backdrop). Not an app's shell in the page's colour.
function windowCover(el, style, w, h) {
  const r = el.getBoundingClientRect();
  if (r.width < FLOAT_WINDOW * w || r.height < FLOAT_WINDOW * h)
    return false;
  const a = alpha(style.backgroundColor);
  return parseInt(style.zIndex, 10) > 0 || el.localName === "dialog" || el.matches(FLOAT_ROLES)
    || (a > 0 && a < SOLID);
}

// A panel its menu button shows: the button naming it (aria-controls)
// expanded, or a popup toggle beside it expanded or checked (Vector's
// dropdowns: the language menu in a wiki's title bar).
const SHOWN_BY = ":scope > [aria-expanded=true], :scope > [aria-haspopup]:checked";

function revealed(el) {
  return revealedBy(el) || !!(el.parentElement && el.parentElement.querySelector(SHOWN_BY));
}

function revealedBy(el) {
  return !!el.id && !!document.querySelector("[aria-expanded=true][aria-controls~=\"" + CSS.escape(el.id) + "\"]");
}

// Whether a wrapper over the whole window, see-through (a web component's
// host: SBB's navigation, no z-index), dims the page under its panel: a
// scrim of its own or of what it holds on the way down (`chain`, the
// wrapper last), a see-through colour on an empty ::before or ::after, or
// on a child over the whole window.
function seeThroughCover(chain) {
  const top = chain[chain.length - 1];
  if (alpha(getComputedStyle(top).backgroundColor) > 0)
    return false;
  const dim = (color) => alpha(color) > 0 && alpha(color) < SOLID;
  return chain.some((q) => PSEUDOS.some((pseudo) => {
    const style = getComputedStyle(q, "::" + pseudo);
    return /^["']/.test(style.content) && style.display !== "none" && dim(style.backgroundColor);
  }) || layered(q).some((kid) => !chain.includes(kid) && dim(getComputedStyle(kid).backgroundColor) && scrim(kid)));
}

// An absolute layer laid over the page's content, not in its flow: a
// popover a portal put in the body (placed from it, not from a box of
// the page: a player's control bar) at a z-index of FLOAT_Z at least
// (Discourse's menus at 1400; a page's own panel at 10 is no such
// layer), or a side panel along the window's left or right
// edge (SIDE_GUTTER) at a z-index of its own, painted, SIDE_PANEL of the
// window's height at least (OpenStreetMap's sidebar over its map). What lies under its middle is no ancestor of it
// (the page laid out absolutely) and not a box of its own size (its
// wrapper), and under a popover no picture (a caption over a teaser's
// photo). Asked once per element and pass (overs).
const FLOAT_Z = 100;
const SIDE_PANEL = 0.5;
const overs = new Map();

function overPage(el, style) {
  if (!overs.has(el))
    overs.set(el, overContent(el, style));
  return overs.get(el);
}

function overContent(el, style) {
  const z = parseInt(style.zIndex, 10), w = document.documentElement.clientWidth;
  const r = el.getBoundingClientRect();
  if (!(z > 0) || r.width * r.height < FLOAT_AREA)
    return false;
  const side = (r.left <= SIDE_GUTTER || r.right >= w - SIDE_GUTTER) && r.height >= SIDE_PANEL * window.innerHeight
    && painting(el);
  const portal = z >= FLOAT_Z && (!el.offsetParent || el.offsetParent === document.body);
  if (!portal && !side)
    return false;
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  if (x < 0 || y < 0 || x >= w || y >= window.innerHeight)
    return false;
  for (const under of stackAt(x, y)) {
    if (holds(el, under))
      continue;
    if (holds(under, el))
      return false;
    const u = under.getBoundingClientRect();
    if (Math.abs(u.width - r.width) <= EDGE && Math.abs(u.height - r.height) <= EDGE)
      return false;
    return side || !(PICTURES.has(under.localName) || getComputedStyle(under).backgroundImage !== "none");
  }
  return false;
}

// The shape of a bar (markBars): across the window and low, along its
// top or its bottom edge, or a sidebar.
function edgeBar(r, w, h) {
  return (r.width >= 0.6 * w && r.height <= 0.35 * h && (r.top <= EDGE || r.bottom >= h - EDGE)) || sideBar(r, w, h);
}

// Whether a see-through box holds nothing to read: no text, no picture,
// no control. An empty positioner the site leaves fixed for its popovers
// (Galaxus', sidebar-shaped) is no bar, nor stays one once emptied or
// once its popover is closed (display:none, its text and buttons still in
// the DOM): only what is shown counts.
const SHOWN_PARTS = "img, svg, video, canvas, picture, iframe, input, select, textarea, button";

function blank(el) {
  return !(texted(el) && textShown(el))
    && ![...el.querySelectorAll(SHOWN_PARTS)].some((part) => part.checkVisibility(SHOWN))
    && !(el.shadowRoot && el.shadowRoot.querySelector(SHOWN_PARTS));
}

function texted(el) {
  return !!(el.textContent.trim() || (el.shadowRoot && el.shadowRoot.textContent.trim())
    || slotted(el).some((node) => node.textContent.trim()));
}

// The sticky rows markBands made glass before they stuck (risers): one
// stuck and a bar now shows the veil; one stuck where it is no bar (not
// along an edge, nor against a bar) would be a see-through row over what
// scrolls under it, and paints its colour again, until it is in the flow
// again (markBands).
function settleRisers() {
  for (const el of risers) {
    if (!el.isConnected || el.getAttribute(CANVAS) !== FILL || !glassPage) {
      risers.delete(el);
      continue;
    }
    if (el.hasAttribute(BAR))
      continue;
    if (stuck(el)) {
      el.removeAttribute(CANVAS);
      risers.delete(el);
    } else
      fillBar(el);
  }
}

// Whether a sticky element sits at its top offset (stuck there), not
// below it in the flow; one without a top offset counts as stuck.
function stuck(el) {
  const top = parseFloat(getComputedStyle(el).top);
  return !Number.isFinite(top) || el.getBoundingClientRect().top <= top + EDGE;
}

// A sidebar's box `r` in a window `w` by `h`: most of its height, narrow,
// along its left or its right edge, at most SIDE_GUTTER off it.
function sideBar(r, w, h) {
  return r.height >= 0.6 * h && r.width <= 0.4 * w && (r.left <= SIDE_GUTTER || r.right >= w - SIDE_GUTTER);
}

// Whether a pinned element shaped as a sidebar holds the site's menus (a
// nav, role=navigation, on it or in it): chrome, veiled though see-through.
function navSide(el, w, h) {
  return sideBar(el.getBoundingClientRect(), w, h) && (siteChrome(el) || siteMenus(el));
}

// A bar tucked under a higher one (BBC's row of sections, slid up under
// its compact masthead once scrolled): the site hid it behind that bar's
// opaque fill, which the veil made see-through, so its links printed over
// the masthead's logo in a second veil band. The part the higher bar
// covers is clipped away (TUCK, the px cut from its top or its bottom
// inline in TUCK_SIDES), what hangs out of its box below the cut (a menu
// dropping from it) kept. Covered: the higher bar spans the row's width
// and its shown top (or bottom) edge, more than EDGE into it; the higher
// one is the first of the two hit at the middle of their overlap (a row
// clipped there already is not hit). Rows stacked side by side (SRF's,
// MDN's) do not overlap: they stay whole.
const TUCK_SIDES = ["--browserglass-tuck-top", "--browserglass-tuck-bottom"];

function tuckBars(bars, rows, w, h) {
  const cuts = new Map();
  for (const low of bars.concat(rows)) {
    const r = low.getBoundingClientRect();
    const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, h);
    const cut = [0, 0];
    for (const high of bars) {
      const a = high.getBoundingClientRect();
      if (high === low || a.left > Math.max(r.left, 0) + EDGE || a.right < Math.min(r.right, w) - EDGE)
        continue;
      const fromTop = a.top <= top + EDGE && a.bottom > top + EDGE;
      if (!(fromTop || (a.bottom >= bottom - EDGE && a.top < bottom - EDGE)) || !above(high, low, a, r, w, h))
        continue;
      if (fromTop)
        cut[0] = Math.max(cut[0], Math.ceil(a.bottom - r.top));
      else
        cut[1] = Math.max(cut[1], Math.ceil(r.bottom - a.top));
    }
    if (cut[0] || cut[1])
      cuts.set(low, cut);
  }
  for (const el of marked("[" + TUCK + "]"))
    if (!cuts.has(el))
      el.removeAttribute(TUCK), cutSides(el, [0, 0]);
  for (const [el, cut] of cuts) {
    cutSides(el, cut);
    el.setAttribute(TUCK, "");
  }
}

// The sticky rows that are no bar tucked under one (Ricardo's category
// row, stuck at 74px under a 131px header, see-through): the site hid
// them behind that bar's opaque fill, and their text now prints over the
// bar's search field through the veil. Under OVER_LINES lines across each
// bar, the first element held there (sticky or fixed) under the bar, not
// its own nor one of its ancestors, is cut as a tucked bar is (tuckBars);
// one cut already is kept while held, as clipped it is hit no more.
function tuckedRows(bars, pinned) {
  const rows = new Set(marked("[" + TUCK + "]").filter((el) => !el.hasAttribute(BAR) && pinned(el)));
  for (const bar of bars) {
    const r = bar.getBoundingClientRect();
    for (let j = 0; j < OVER_LINES; j++)
      for (let i = 0; i < GRID; i++) {
        const y = Math.max(r.top + (j + 0.5) * r.height / OVER_LINES, 0);
        let under = false;
        for (const el of stackAt(r.left + (i + 0.5) * r.width / GRID, y)) {
          if (el === document.documentElement || el === document.body || (under && holds(el, bar)))
            break;
          if (holds(bar, el)) {
            under = true;
            continue;
          }
          if (!under)
            continue;
          const row = heldRow(el, bar, pinned);
          if (row && row.getBoundingClientRect().top >= r.top - EDGE)
            rows.add(row);
          break;
        }
      }
  }
  return [...rows];
}

// The element held (sticky or fixed) that `el` is in, short of the
// ancestors of `bar`; none for a bar.
function heldRow(el, bar, pinned) {
  for (let e = el; e && e !== document.body && !holds(e, bar); e = up(e))
    if (pinned(e))
      return e.hasAttribute(BAR) ? null : e;
  return null;
}

// Whether bar `a` (box `ra`) is drawn over bar `b` (box `rb`) where they
// overlap: the first of the two hit there, or `b` not hit at all once cut.
function above(a, b, ra, rb, w, h) {
  const x = (Math.max(ra.left, rb.left, 0) + Math.min(ra.right, rb.right, w)) / 2;
  const y = (Math.max(ra.top, rb.top, 0) + Math.min(ra.bottom, rb.bottom, h)) / 2;
  for (const el of stackAt(x, Math.min(Math.max(y, 0), h - 1))) {
    if (holds(a, el))
      return true;
    if (holds(b, el))
      return false;
  }
  return b.hasAttribute(TUCK);
}

function cutSides(el, cut) {
  TUCK_SIDES.forEach((name, i) => {
    const value = cut[i] ? cut[i] + "px" : "";
    if (el.style.getPropertyValue(name) !== value)
      value ? el.style.setProperty(name, value) : el.style.removeProperty(name);
  });
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
// opaque, to show a skip link). A button as tall as the bar (BAR_BUTTON
// of its height: a slider's arrow at the end of NZZ's row of sections)
// painting that colour is cleared too: its icon and its border keep its
// shape, not an opaque square of the bar's colour on the veil. A low band
// of the page's background (a layer as wide as the window, at most
// BAND_LOW of its height: Heise's header) is filled the same way, in its
// own colour (markBands: a row in it, holding an icon, which the grid of
// markCanvas leaves as a box), and so is a row stuck later (risers). Only
// on a see-through page (glassPage),
// as the fills of markFills. A surface kept for the text on it (KEPT:
// BBC's dark cookie banner, its light text read before the box it covers
// was a bar, a banner inserted late) is the site's own, not the bar's
// paint: neither filled nor read as the bar's colour (painted), or it
// turns see-through and its text is inked over what scrolls under it.
const BAR_SHARE = 0.3;
const BAR_NEAR = 16;
const FIELD_BOXES = "input:not([type=hidden]), button, [role=button], select, textarea";
const BAR_BUTTON = 0.9;
const BAND_LOW = 0.35;
const barColors = new WeakMap();
const risers = new Set();
let glassPage = false;

// The colours a bar paints itself: its own, that of a child covering it
// (not one kept for its text), or of an empty pseudo-element covering
// either (paintOf).
function painted(bar) {
  const colors = [];
  const r = bar.getBoundingClientRect();
  for (const el of [bar, ...layered(bar)]) {
    if (el.hasAttribute(KEPT))
      continue;
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

function fillBar(bar, colors = [...pageColors, ...(barColors.get(bar) || [])]) {
  const box = bar.getBoundingClientRect();
  const kids = drawnIn(bar);
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    if (el.hasAttribute(KEPT) || el.closest("[" + UNDER + "]"))
      continue;
    const r = el.getBoundingClientRect();
    const band = barRow(r, box) || r.height >= FILL_COVER * box.height || r.width >= FILL_COVER * box.width;
    if (el.hasAttribute(CANVAS)) {
      // a row see-through already: what its gradient left goes too
      if (band && within(r, box) && fades(getComputedStyle(el), () => true))
        clearGradient(el);
      continue;
    }
    if (NOT_FILLS.has(el.localName) && !(el.localName === "button" && r.height >= BAR_BUTTON * box.height))
      continue;
    // a row painted by a pseudo-element of its own: that one see-through
    const style = getComputedStyle(el), color = style.backgroundColor;
    const paint = alpha(color) >= SOLID ? {pseudo: null, color} : band ? underPaint(el) : null;
    // a row across it painted by a linear gradient alone (its colour
    // cleared by a style), as rowColors takes an opaque one: see-through
    if (!paint && r.width >= FILL_COVER * box.width && within(r, box) && !el.matches(BRANDS)
        && fades(style, () => true))
      clearGradient(el);
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

// The elements drawn inside `el` (inside), those the slots of its shadow
// tree show from the page too (a popup's list, slotted into its card).
function drawnIn(el) {
  const kids = inside(el);
  for (const node of [el, ...kids].flatMap(slotted))
    if (node.nodeType === Node.ELEMENT_NODE)
      kids.push(node, ...inside(node));
  return kids;
}

// A floating layer's or a side drawer's sections in a colour of their own
// (NZZ's navy sections in its white drawer): across it (FILL_COVER of its
// width), SECTION_MIN tall at least, in an opaque colour, no picture, not
// a control nor a link, their top in its box (the rest may scroll on
// below it). They are see-through (CANVAS FILL): one veil, not the
// site's slab on it. Under a light tone, a dark row of text across it, of
// any height (MDN's navy title row in its light mega menu), is one too.
const SECTION_MIN = 96;

function fillSections(layer) {
  const box = layer.getBoundingClientRect();
  const kids = drawnIn(layer);
  for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
    const el = kids[i];
    if (el.hasAttribute(CANVAS) || el.hasAttribute(KEPT) || NOT_FILLS.has(el.localName)
        || el.matches(FIELD_BOXES + ", a"))
      continue;
    const r = el.getBoundingClientRect();
    if (r.width < FILL_COVER * box.width || !r.height || r.left < box.left - EDGE
        || r.right > box.right + EDGE || r.top < box.top - EDGE || r.top > box.bottom)
      continue;
    const style = getComputedStyle(el);
    if (style.backgroundImage === "none" && alpha(style.backgroundColor) >= SOLID
        && (r.height >= SECTION_MIN || darkRow(el, style)) && el.checkVisibility(SHOWN))
      el.setAttribute(CANVAS, FILL);
  }
}

// A row painting a dark colour of its own, holding text, under a light tone.
function darkRow(el, style) {
  return tone === "light" && isLight(style.backgroundColor) === false && !!el.textContent.trim();
}

// A row of a bar made see-through: its linear gradient over its colour
// goes too (Python's menu row, a lighter blue fading into its header's),
// one veil. Taken off with the page's layers (unfade).
function clearGradient(el) {
  el.style.setProperty(FADE_IMAGE, "none");
  el.setAttribute(FADE, "");
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
// button or a field (FIELDS) keeps a veil of its own; sibling blocks whose
// veils would overlap give theirs to their parent (mergeVeils). An
// outermost block laid over a picture (overPicture: a teaser's caption
// card over the foot of its photo) gets BLOCK "solid" instead: no rule,
// Dark Reader's opaque fill stays, since its text was drawn on an opaque
// card, not on a photo.
// So does one laid over a band of a saturated colour (overBand).
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

function markBlocks(near, texts) {
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
      floating.set(el, style.position === "fixed" || style.position === "sticky" || el.hasAttribute(BAR)
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
    if (MEDIA.has(el.localName) || alpha(color) < SOLID || floats(el) || !plain(el, color, BLOCK_CHROMA))
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
  const overs = new Map(), veiled = new Set();
  let pictures = null;
  const media = () => pictures || (pictures = nearMedia(near));
  for (const el of texts) {
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
        overs.set(b, overPicture(b, stop, media) || overBand(b));
      // a button keeps a veil of its own, on its card's
      const role = outermost ? (overs.get(b) ? OPAQUE : VEILED) : b.matches(FIELDS) ? VEILED : SEE_THROUGH;
      if (role === VEILED && outermost)
        veiled.add(b);
      // a control veiled with no border nor shadow of its own: a thin ring
      // too, as markFields gives it (judged once: the ring is a shadow)
      const had = b.getAttribute(BLOCK);
      const ringed = had === null ? !edged(getComputedStyle(b)) : had.split(" ").includes(FIELD_EDGE);
      const edge = role === VEILED && b.matches(FIELDS) && ringed ? [FIELD_EDGE] : [];
      const value = [role, ...edge, ...bands(b)].join(" ");
      if (b.getAttribute(BLOCK) !== value)
        b.setAttribute(BLOCK, value);
    });
  }
  mergeVeils(veiled, (el) => kind(el) === null && !floats(el));
}

// Sibling blocks whose veils overlap (PyPI's "verified" source above its
// data block, which a negative margin pulls up 10 px under it) would stack
// two veils into a darker strip where they meet. Their parent, painting
// nothing and not floating (bare), gets the one veil instead and they
// "glass" in it, when their boxes together cover MERGE_SHARE of its box
// at least (no veil spread over what else it holds). Marked, the parent is
// a block of its own on the next pass: the outermost one.
const MERGE_SHARE = 0.9;

function mergeVeils(veiled, bare) {
  const siblings = new Map();
  for (const b of veiled) {
    const p = up(b);
    if (p && p !== document.body)
      siblings.set(p, [...(siblings.get(p) || []), b]);
  }
  for (const [parent, blocks] of siblings) {
    const boxes = blocks.map((b) => b.getBoundingClientRect());
    if (!boxes.some((r, i) => boxes.slice(i + 1).some((o) => crosses(r, o))) || !bare(parent))
      continue;
    const r = parent.getBoundingClientRect();
    if (overlap(r, union(boxes)) < MERGE_SHARE * r.width * r.height)
      continue;
    parent.setAttribute(BLOCK, VEILED);
    for (const b of blocks)
      b.setAttribute(BLOCK, [SEE_THROUGH, ...bands(b)].join(" "));
  }
}

// Whether two boxes share more than a pixel each way.
function crosses(a, b) {
  return Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1
    && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
}

// The box round boxes.
function union(boxes) {
  return {
    left: Math.min(...boxes.map((o) => o.left)), top: Math.min(...boxes.map((o) => o.top)),
    right: Math.max(...boxes.map((o) => o.right)), bottom: Math.max(...boxes.map((o) => o.bottom)),
  };
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

function nearMedia(near) {
  return everywhere(OVER_MEDIA).filter((m) => {
    const r = m.getBoundingClientRect();
    return near(m) && r.width > ICON_SIDE && r.height > ICON_SIDE;
  });
}

function overPicture(block, stop, media) {
  if (stop) {
    const style = getComputedStyle(stop);
    if (/url\(/.test(style.backgroundImage) && /cover|contain/.test(style.backgroundSize))
      return true;
  }
  const r = block.getBoundingClientRect();
  return media().some((m) => !holds(block, m) && overlap(r, shownBox(m)) >= OVER_SHARE * r.width * r.height);
}

// Whether a block lies over a band of a saturated colour (SBB's journey
// form, a white card pulled up half over the red band of its hero, a
// sibling before it): at one of OVER_POINTS points down the middle of its
// box, the first element behind it painting anything paints an opaque
// colour of OVER_CHROMA at least, no picture, under OVER_SHARE of the
// block at least. A veil would take the band's colour (a dark red box,
// its grey text lost on it).
const OVER_CHROMA = 0.4;
const OVER_POINTS = [0.25, 0.5, 0.75];

function overBand(block) {
  const r = block.getBoundingClientRect();
  const root = block.getRootNode();
  const at = root.elementsFromPoint ? root : document;
  for (const y of OVER_POINTS) {
    const stack = at.elementsFromPoint(r.left + r.width / 2, r.top + y * r.height);
    const i = stack.indexOf(block);
    const behind = i < 0 ? null : stack.slice(i + 1).find((el) => {
      const style = getComputedStyle(el);
      return alpha(style.backgroundColor) >= CLEAR || style.backgroundImage !== "none";
    });
    if (behind && saturatedBand(behind, r))
      return true;
  }
  return false;
}

function saturatedBand(el, r) {
  const style = getComputedStyle(el);
  return style.backgroundImage === "none" && alpha(style.backgroundColor) >= SOLID
    && chroma(style.backgroundColor) >= OVER_CHROMA
    && overlap(r, el.getBoundingClientRect()) >= OVER_SHARE * r.width * r.height;
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
// panels (SRF's teasers, the Docker docs' link cards, crates.io's crate
// cards, 72 px high). A link near the window leads to its card (cardOf):
// the link itself or the box painted round it. So does text near the
// window not in a link (panelOf): the outermost box painted under it on
// its layer (a module of Heise's in its card colour, a heading over a
// list of links; PyPI's tinted sidebar cards), a box of links alone
// staying a menu. A card drawn in faces of one colour (cardFaces: PyPI's
// source line over its data block) is the box round them, if that box
// reads as a card. A card at least CARD_LOW px each way and CARD_SIDE px
// one way, not a layer of the page (wide, large), painting an opaque
// colour on the page's side, tinted BLOCK_CHROMA at most (plain; thin
// gradient lines framing it allowed: the French state's DSFR tiles), not in
// anything floating over the page (afloat), holding at most CARD_LINKS
// links (a link's: not a box of a list of links) and no picture over
// CARD_PICTURE of it (a photo's card: the photo is the card) nor one set
// on it as on a mat (cardLike: a shop's product tile), not laid over a
// saturated band (overBand), and
// one of CARD_ROW cards at least in that colour (a row of cards, not a
// lone panel: YouTube's notice card keeps its own fill, unless light and
// right on the glass: lone) or a module
// across MODULE_WIDE of the window at least and lower than a page column
// (COLUMN_TALL: Heise's promotion, alone in view; a section's card taller
// than the window keeps its fill), and not a box outlined by a border
// (framed), gets BLOCK "veil"; a code block (pre) gets it at any height,
// outlined or alone (PyPI's grey code blocks, a one-line command too)
// as Dark Reader's darkened cards do: the surface of the page's tone at
// BLOCK_VEIL_OPACITY, its border kept. A
// box inside it in its colour gets "glass" (veils do not stack), unless
// it holds a picture (CARD_MEDIA: a photo's frame keeps its colour behind
// it); so do the faces cardOf found filling it. At most BRAND_ELEMENTS
// links and FILL_NODES boxes in a card are looked at, and each element on
// the way up from the text once (panelOf). The marks are
// judged again once the tone changes (a site following the system's
// scheme repaints its cards), and go when the page is darkened or not
// glass.
const CARD_SIDE = 120;
const CARD_LOW = 64;
const CARD_ROW = 2;
const CARD_LINKS = 4;
const CARD_PICTURE = 0.9;
const CARD_MEDIA = "img, picture, video, canvas";
const MODULE_WIDE = 0.7;
let cards = new Map(), cardTone = null;

function markCards(near, texts) {
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
  // a box is looked at once from its links and once from its text (a
  // module holding more links than a link's card may)
  const found = new Map(), byLink = new Set(), byText = new Set();
  // whether a box (`r` its size) in `color` reads as a card; a code block
  // (pre) does at any height, outlined or not, and alone
  const fits = (el, r, color, link) => {
    const code = el.localName === "pre";
    return (code || Math.min(r.width, r.height) >= CARD_LOW) && Math.max(r.width, r.height) >= CARD_SIDE
      && !wide(el) && !large(el) && alpha(color) >= SOLID && plain(el, color, BLOCK_CHROMA, true) && !afloat(el)
      && cardLike(el, r, link ? CARD_LINKS : Infinity) && (code || !framed(el, link)) && !overBand(el);
  };
  const judge = (el, link, faces) => {
    const looked = link ? byLink : byText;
    if (!el || looked.has(el) || found.has(el))
      return;
    looked.add(el);
    const color = getComputedStyle(el).backgroundColor;
    // the box round the card's faces (cardFaces), or the face alone when
    // that box reads as no card
    const [box, size, parts] = cardFaces(el, color);
    if (found.has(box))
      return;
    let card = el, r = el.getBoundingClientRect();
    if (box !== el && !looked.has(box)) {
      looked.add(box);
      if (fits(box, size, color, link))
        card = box, r = size, faces = [...faces, ...parts];
    }
    if (card === el && !fits(el, r, color, link)) {
      if (lone(el, r, color))
        lones.set(el, color);
      return;
    }
    found.set(card, [color, faces, card.localName === "pre"]);
    rows.set(color, (rows.get(color) || 0) + 1);
  };
  const lones = new Map();
  const links = everywhere("a[href]");
  for (let i = 0; i < links.length && i < BRAND_ELEMENTS; i++)
    if (near(links[i])) {
      const [el, faces] = cardOf(links[i]);
      judge(el, links[i], faces);
    }
  const outer = new Map();
  for (const el of texts)
    if (!el.closest("a[href]"))
      judge(panelOf(el, outer), null, []);
  const across = MODULE_WIDE * document.documentElement.clientWidth;
  const low = COLUMN_TALL * window.innerHeight;
  const module = (r) => r.width >= across && r.height < low;
  for (const [el, [color, faces, code]] of found)
    if (code || rows.get(color) >= CARD_ROW || module(el.getBoundingClientRect())) {
      veilCard(el, color);
      for (const face of faces)
        cards.set(face, null), face.setAttribute(BLOCK, SEE_THROUGH);
    } else if (lone(el, el.getBoundingClientRect(), color)) {
      lones.set(el, color);
    }
  for (const [el, color] of lones)
    if (!cards.has(el))
      veilCard(el, color);
}

// A panel alone on the glass in the page's tone: a box that reads as
// no card or is one alone in its colour (lower than CARD_LOW, outlined,
// narrower than a module: GitHub's #f6f8fa header of a file list, 54 px
// high; the French state's lone grey "France services" panel) but paints an opaque plain colour of the tone (under a light
// tone BRAND_LIGHT of luminance at least; under a dark one under LONE_DARK
// and lower than CARD_LOW, a strip rather than a card: GitHub's dark
// rgb(21, 27, 35) box of the latest commit, 54 px high, where YouTube's
// dark notice card and GitHub's dark pinned repositories keep their fill;
// BLOCK_CHROMA of
// chroma at most, thin lines allowed: plain) right
// on the glass (onGlass under it, no page layer, CANVAS, round it), a tint
// of its own (not white nor black, nor one of the page's colours, pageColors: a white
// card or a box in the page's colour left on the glass keeps its fill, as
// YouTube's sign-in nudge does), LONE_LOW px each way and CARD_SIDE one
// way at least, not a layer of the page (wide, large), floating (afloat),
// a picture's mat (cardLike) nor laid over a saturated band (overBand):
// it stands as a solid slab on the glass, and is veiled as cards are.
const LONE_LOW = 40;
const LONE_DARK = 0.05;

function lone(el, r, color) {
  const y = luminance(color);
  const toned = tone === "light" ? y >= BRAND_LIGHT && y < 1 : tone === "dark" && y !== null && y > 0 && y < LONE_DARK
    && Math.min(r.width, r.height) < CARD_LOW;
  return toned && Math.min(r.width, r.height) >= LONE_LOW && Math.max(r.width, r.height) >= CARD_SIDE
    && !wide(el) && !large(el) && alpha(color) >= SOLID && !pageColors.has(color) && !el.closest("[" + CANVAS + "]")
    && plain(el, color, BLOCK_CHROMA, true) && !afloat(el) && onGlass(up(el) || el)
    && cardLike(el, r, Infinity) && !overBand(el);
}

// The outermost element painting anything from an element up to the
// layer of the page under it (CANVAS) or the body, itself included, not
// a layer itself (wide, large: a wrapper in the page's colour markBands
// has not marked yet): the panel its text is drawn on; null when none,
// or when the way meets a bar, a block or a surface kept (the text is on
// those). Read once per element and pass (`outer`: that element, or
// false past such a mark).
function panelOf(el, outer) {
  const way = [];
  let p = el, found = null;
  for (; p && p !== document.body && !p.hasAttribute(CANVAS); p = up(p)) {
    if (outer.has(p)) {
      found = outer.get(p);
      break;
    }
    if (p.hasAttribute(BAR) || p.hasAttribute(BLOCK) || p.hasAttribute(KEPT) || cards.has(p)) {
      found = false;
      break;
    }
    way.push(p);
  }
  for (let i = way.length - 1; i >= 0; i--) {
    if (found === null) {
      const style = getComputedStyle(way[i]);
      if ((alpha(style.backgroundColor) >= CLEAR || style.backgroundImage !== "none")
          && !wide(way[i]) && !large(way[i]))
        found = way[i];
    }
    outer.set(way[i], found);
  }
  return found || null;
}

// A card drawn in several faces of one colour: PyPI's sidebar card, its
// source line (a pill label pulled up over its top edge) over its data
// block, in a box painting nothing. The box round them is the card, one
// veil for both (as mergeVeils gives on a darkened page), when two of its
// children at least paint the colour and cover MERGE_SHARE of it; its
// size is that of all it paints in the colour (FILL_NODES boxes, the pill
// included); its faces go see-through in it, a face holding a picture too
// (PyPI's maintainers and their avatars). A box of more than CARD_FACES
// children is a list, not a card's faces. [the element, its box, []]
// otherwise.
const CARD_FACES = 8;

function cardFaces(el, color) {
  const own = [el, el.getBoundingClientRect(), []];
  const box = up(el);
  if (!box || box === document.body || box.children.length > CARD_FACES)
    return own;
  const style = getComputedStyle(box);
  if (alpha(style.backgroundColor) >= CLEAR || style.backgroundImage !== "none")
    return own;
  const r = box.getBoundingClientRect();
  const parts = [...box.children].filter((child) => getComputedStyle(child).backgroundColor === color);
  const covered = parts.reduce((sum, child) => sum + overlap(r, child.getBoundingClientRect()), 0);
  if (parts.length < 2 || covered < MERGE_SHARE * r.width * r.height)
    return own;
  const boxes = [r], inside = box.getElementsByTagName("*");
  for (let i = 0; i < inside.length && i < FILL_NODES; i++)
    if (getComputedStyle(inside[i]).backgroundColor === color)
      boxes.push(inside[i].getBoundingClientRect());
  const u = union(boxes);
  return [box, {...u, width: u.right - u.left, height: u.bottom - u.top}, parts];
}

// The card a link is drawn on, and the faces filling it: the link, or the
// first of CARD_DEPTH elements up from it that paints anything (SBB's
// link stretched over its card from the shadow tree of a component in
// it, IKEA's title link in its card's text), then the outermost box of
// the same size (EDGE) round it painting an opaque colour (IKEA's grey
// service card filling a frame of another grey): that box is the card,
// the boxes painted inside it its faces. [null, []] when the way meets a
// layer of the page or a block marked, or nothing painting.
const CARD_DEPTH = 4;

function cardOf(link) {
  const taken = (el) => el.hasAttribute(CANVAS) || el.hasAttribute(BLOCK) || cards.has(el);
  const paints = (el) => alpha(getComputedStyle(el).backgroundColor) >= CLEAR
    || getComputedStyle(el).backgroundImage !== "none";
  let card = link;
  for (let i = 0; card && card !== document.body && !taken(card) && !paints(card); i++)
    card = i < CARD_DEPTH ? up(card) : null;
  if (!card || card === document.body || taken(card))
    return [null, []];
  const faces = [], r = card.getBoundingClientRect();
  for (let p = up(card); p && p !== document.body && !taken(p); p = up(p)) {
    const a = p.getBoundingClientRect();
    if (Math.abs(a.left - r.left) > EDGE || Math.abs(a.top - r.top) > EDGE
        || Math.abs(a.right - r.right) > EDGE || Math.abs(a.bottom - r.bottom) > EDGE)
      break;
    if (alpha(getComputedStyle(p).backgroundColor) >= SOLID)
      faces.push(card), card = p;
    else if (paints(p))
      break;
  }
  return [card, faces];
}

// Whether a box round a link, not the link itself, draws a border of its
// own: a panel the site outlines (GitHub's pinned repositories, in the
// page's colour), kept as painted; a link card painting itself keeps the
// veil with its border (Docker's tutorial cards).
function framed(el, link) {
  const style = getComputedStyle(el);
  return el !== link && style.borderTopStyle !== "none" && parseFloat(style.borderTopWidth) > 0;
}

// Whether a box painted round links reads as a card: at most `most`
// links in it (its own shadow tree too), no picture over CARD_PICTURE of
// its box `r`, and none over CARD_MAT of it set in from both its sides
// (more than EDGE) and centred in it (MAT_CENTRE of its width: a shop's
// product photo on the tile's colour, its white baked in, LDLC's; the
// tile is the photo's mat and keeps its fill, where a teaser's photo
// spans its card from side to side, SRF's, and a module's sits on one
// side of its text, Heise's promotion). A picture
// not in yet (pending) has no size to judge by (LDLC's lazy product
// photos, sized once loaded), and a veil once set stays: the box is left
// as painted until it loads (its load runs a new pass).
const CARD_MAT = 0.2;
const MAT_CENTRE = 0.1;

function cardLike(el, r, most) {
  let links = el.querySelectorAll("a[href]").length;
  if (el.shadowRoot)
    links += el.shadowRoot.querySelectorAll("a[href]").length;
  if (links > most)
    return false;
  const area = r.width * r.height;
  for (const media of el.querySelectorAll(CARD_MEDIA)) {
    if (pending(media))
      return false;
    const m = media.getBoundingClientRect(), shown = overlap(r, m);
    if (shown >= CARD_PICTURE * area
        || (shown >= CARD_MAT * area && m.left > r.left + EDGE && m.right < r.right - EDGE
          && Math.abs(m.left - r.left - (r.right - m.right)) <= MAT_CENTRE * r.width))
      return false;
  }
  return true;
}

// Whether a picture laid out in the page (not display:none) is still on
// its way: loading (a lazy one near the window), or no picture yet (a
// script's lazy loader not run, a broken one).
function pending(media) {
  return media.localName === "img" && media.getClientRects().length > 0
    && (!media.complete || !media.naturalWidth);
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

// Bands of the page's background the grid of markCanvas steps over (SBB's
// white band under its hero, in the open shadow tree of a component,
// between two rows of the grid): on a see-through page Dark Reader leaves
// alone (glassPage), the text near the window is followed up to the body,
// as markBlocks follows it on a darkened page (shownText reads open shadow
// trees too), and the outermost element painting anything on the way is
// looked at, as the grid looks at the lowest of its stack: one painting an
// opaque plain colour on the page's side, covering the window or as wide
// as it or down a page column (large, column), not a picture (MEDIA) and
// not floating (afloat), is a layer of the page's background: CANVAS, its
// colour one of the page's. A card or a header on a layer stays (the
// layer is the outermost), as does a layer marked or a surface kept, and
// a band that is the site's own bar (siteBand). A low band among those
// (BAND_LOW) has its rows in its colour filled (fillBar). A sticky row the
// text is in, in the flow still (not stuck: NZZ's row of sections under
// its masthead, an ad above it) and as a bar would be (across RISE_WIDE of
// the window, BAR_MIN to BAND_LOW of its height), painting a plain colour
// on the page's side (plain, not offGlass: NZZ's black row on its grey
// page) and in nothing else floating, is the page's header until it
// sticks: CANVAS (FILL), glass, its colour the bar's (barColors, for
// fillBar), and one of the risers, which markBars veils once stuck (a
// bar) or paints again (settleRisers).
const RISE_WIDE = 0.6;

function markBands(texts) {
  if (darkened || !glassPage)
    return;
  // a layer marked reads as see-through, but is one
  const paints = (el) => {
    const style = getComputedStyle(el);
    return el.hasAttribute(CANVAS) || alpha(style.backgroundColor) >= CLEAR || style.backgroundImage !== "none";
  };
  // the outermost element painting something from an element up to the
  // body, itself included (null: none), read once per element
  const outer = new Map();
  const lowest = (el) => {
    const way = [];
    let p = el;
    for (; p && p !== document.body && !outer.has(p); p = up(p))
      way.push(p);
    let found = p && outer.has(p) ? outer.get(p) : null;
    for (let i = way.length - 1; i >= 0; i--) {
      if (found === null && paints(way[i]))
        found = way[i];
      outer.set(way[i], found);
    }
    return found;
  };
  const layers = new Set(texts.map(lowest));
  for (const el of layers) {
    if (!el || el.hasAttribute(CANVAS) || el.hasAttribute(KEPT) || MEDIA.has(el.localName))
      continue;
    const color = getComputedStyle(el).backgroundColor;
    if (alpha(color) >= SOLID && (large(el) || (column(el, color) && !siteBand(el, color))) && !afloat(el)) {
      pageColors.add(color);
      layerColors.set(el, color);
      mark(el, CANVAS);
    }
  }
  const h = window.innerHeight;
  for (const el of marked("[" + CANVAS + "=\"\"]"))
    if (layerColors.has(el) && wide(el) && el.getBoundingClientRect().height <= BAND_LOW * h)
      fillBar(el, [layerColors.get(el)]);
  // the sticky element an element is in, null for none, read once each
  const pins = new Map();
  const pin = (el) => {
    if (!el || el === document.body)
      return null;
    if (!pins.has(el))
      pins.set(el, getComputedStyle(el).position === "sticky" ? el : pin(up(el)));
    return pins.get(el);
  };
  for (const el of new Set(texts.map(pin)))
    if (el && rising(el, h)) {
      barColors.set(el, new Set([...(barColors.get(el) || []), getComputedStyle(el).backgroundColor]));
      el.setAttribute(CANVAS, FILL);
      risers.add(el);
      fillBar(el);
    }
  markSeams();
}

function rising(el, h) {
  if (MARKS.some((m) => el.hasAttribute(m)) || el.hasAttribute(KEPT) || stuck(el) || afloat(up(el)))
    return false;
  const color = getComputedStyle(el).backgroundColor;
  const r = el.getBoundingClientRect();
  return alpha(color) >= SOLID && plain(el, color) && !offGlass(color)
    && r.width >= RISE_WIDE * document.documentElement.clientWidth && r.height >= BAR_MIN && r.height <= BAND_LOW * h;
}

// Whether a band lower than a page column is the site's own bar, solid as
// the site drew it, not a band of the page: one along the top or the
// bottom edge of the page (GitHub's dark masthead in the flow, a footer),
// within EDGE px, or one holding the site's menus (BAND_MENUS, in its own
// shadow tree too) or in them (siteChrome). Only a bar as deep as the
// glass, or deeper on the page's side, stays: one off the glass towards
// the other side by more than BAND_GLASS of contrast (IKEA's grey utility
// bar in its dark theme, lighter than the dark glass; PyPI's grey tab band
// under its project header, darker than the light glass) would stand as an
// opaque slab on it, and is a band of the page.
const BAND_MENUS = "nav, header, footer, [role=navigation], [role=banner], [role=contentinfo]";
const BAND_GLASS = 1.1;

function siteBand(el, color) {
  if (tall(el) || offGlass(color))
    return false;
  const r = el.getBoundingClientRect(), y = window.scrollY;
  if (r.top + y <= EDGE || r.bottom + y >= document.documentElement.scrollHeight - EDGE)
    return true;
  if (el.querySelector(BAND_MENUS) || (el.shadowRoot && el.shadowRoot.querySelector(BAND_MENUS)))
    return true;
  for (let p = el; p && p !== document.body; p = up(p))
    if (siteChrome(p))
      return true;
  return false;
}

// Whether a colour lies off the glass (GLASS) towards the other side of the
// page's tone, by more than BAND_GLASS of contrast: lighter on a dark page,
// darker on a light one.
function offGlass(color) {
  const glass = luminance(getComputedStyle(document.documentElement).getPropertyValue(GLASS).trim());
  const y = luminance(color);
  if (glass === null || y === null)
    return false;
  return (tone === "dark" ? y > glass : y < glass) && contrast(y, glass) > BAND_GLASS;
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
// and grey text (below GLASS_CHROMA, a slate grey tinted blue included:
// Docker's breadcrumb) straight on the light glass (onGlass) below
// GLASS_RATIO, a floor for the wallpaper its tint lets through
// (Tailwind's gray-400, drawn for a white page, on the light glass over a
// mid-tone wallpaper; a brand colour, an orange link, and a caption on
// the dark glass keep theirs):
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
// (FILL), or they stay as dark or light bands over the glass (one kept
// for its text, KEPT, stays the site's: fillBar). They lose it
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
      if (el.hasAttribute(CANVAS) || el.hasAttribute(KEPT) || !pageColors.has(style.backgroundColor))
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
const GLASS_CHROMA = 0.2;
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
// text of an open shadow tree is read where its host is (shadows). The
// veiled layers are read first: a menu the site appends at the end of a
// long page (Wikipedia's language list, after an article of thousands of
// text nodes) is past INK_NODES in the page's order.
function shownText(near) {
  const shown = [], looked = new Set();
  const show = NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT;
  // a stack: the last walker is walked first
  const walkers = [document.body, ...marked("[" + BAR + "]")]
    .map((root) => document.createTreeWalker(root, show));
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
// repeat across them, as links are underlined with a gradient 2px high,
// and icons: an image drawn once, ICON_IMAGE px at most each way and less
// than ICON_SHARE of its box (YouTube's 18px chevron at the end of a
// settings row: the value beside it is on the row's backing, not on a
// picture).
const THIN = 4;
const ICON_IMAGE = 32;
const ICON_SHARE = 0.25;
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
  const box = (parseFloat(style.width) || 0) * (parseFloat(style.height) || 0);
  return split(style.backgroundImage).some((image, i) => {
    // a layer of "none" in a list (DSFR's buttons: "none, none") paints nothing
    if (image === "none")
      return false;
    const [w, h = "auto"] = sizes[i % sizes.length].split(/\s+/);
    const r = repeats[i % repeats.length].split(/\s+/);
    const [rx, ry] = r[0] === "repeat-x" ? ["repeat", "no-repeat"]
      : r[0] === "repeat-y" ? ["no-repeat", "repeat"] : [r[0], r[1] || r[0]];
    if (!GRADIENT.test(image))
      return !icon(w, h, rx, ry, box);
    return !(thin(h) && ry === "no-repeat" || thin(w) && rx === "no-repeat");
  });
}

function icon(w, h, rx, ry, box) {
  const small = (v) => v.endsWith("px") && parseFloat(v) <= ICON_IMAGE;
  return rx === "no-repeat" && ry === "no-repeat" && small(w) && small(h)
    && parseFloat(w) * parseFloat(h) < ICON_SHARE * box;
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

// Whether `el` lies over most of the box `r`: over it, not beside it (a
// search field's suggestion list, open under its wrapper and larger than it).
function covers(r, el) {
  return overlap(r, el.getBoundingClientRect()) >= FACE * r.width * r.height;
}

function layerPaints(el, r, depth) {
  const style = getComputedStyle(el);
  // a closed overlay kept in place, hidden (frame.work's dark scrim over
  // the whole window, round its menu button), paints nothing
  if (parseFloat(style.opacity) < CLEAR || style.visibility !== "visible")
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

// Whether `kid`, laid in a box `r` smaller than the window, is the site's
// scrim: a see-through layer over the whole window (Galaxus' open search,
// its rgba(0, 0, 0, 0.5) dimming layer kept in the field's wrapper, under
// the form). It dims the page round the box, it is no backing of the box:
// the field's black text, read on that black, was inked light on the light
// veil.
function dimsWindow(kid, r) {
  const w = document.documentElement.clientWidth, h = window.innerHeight;
  const k = kid.getBoundingClientRect();
  return (r.width < FLOAT_WINDOW * w || r.height < FLOAT_WINDOW * h)
    && k.width >= FLOAT_WINDOW * w && k.height >= FLOAT_WINDOW * h
    && alpha(getComputedStyle(kid).backgroundColor) < SOLID;
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
        if ((position === "absolute" || position === "fixed") && covers(r, kid) && !dimsWindow(kid, r)) {
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
// highlighted words), or those of its text-shadow (a text drawn by its
// shadow alone); none when unknown (a picture clipped to the text).
function inks(style) {
  const fill = style.webkitTextFillColor || style.color;
  const shown = (colors) => (colors || []).filter((c) => alpha(c) >= CLEAR);
  if (alpha(fill) >= CLEAR)
    return [fill];
  if (!clipped(style))
    return shown(style.textShadow.match(PAINT));
  if (style.backgroundImage !== "none" && split(style.backgroundImage).every((image) => GRADIENT.test(image)))
    return shown(style.backgroundImage.match(PAINT));
  return [];
}

// The luminance behind `el`; with `ink` (text), the glass and a bar's veil
// as they show over the worst wallpaper (glassOver, veiled), and each
// see-through backing on the way (a description box in
// rgba(0, 0, 0, 0.05), a card in rgba(255, 255, 255, 0.6)) mixed over
// what is under it (seen); else the bare surface and the veil's own colour.
function behind(el, follow = true, worst = false, ink = false) {
  const root = document.documentElement;
  // a background clipped to the text is the text's colour, not behind it
  if (clipped(getComputedStyle(el)))
    el = up(el) || root;
  const tints = [];
  for (let p = el, kid = null; p && p !== root; kid = p, p = up(p)) {
    if (tableCaption(kid))
      continue;
    const style = getComputedStyle(p);
    const own = face(p);
    if (own !== undefined)
      return underTints(own, tints);
    if (picture(style))
      return underTints(null, tints);
    const a = alpha(style.backgroundColor);
    if (a >= OWN_BG && !(ink && a < SOLID && !p.hasAttribute(BAR)))
      return underTints(ink && p.hasAttribute(BAR) ? veiled(style.backgroundColor, worst)
        : luminance(style.backgroundColor), tints);
    if (ink && a > 0 && luminance(style.backgroundColor) !== null)
      tints.push([luminance(style.backgroundColor), a]);
    const field = follow && style.position === "absolute" ? fieldUnder(p) : null;
    if (field)
      return underTints(behind(field, false, worst, ink), tints);
    if (follow && style.position === "absolute" && layerOverPicture(p, el))
      return underTints(null, tints);
    const under = follow && (style.position === "fixed" || style.position === "sticky") && !large(p)
      ? beneath(p, el) : null;
    if (under)
      return underTints(behind(under, false, worst, ink), tints);
  }
  return underTints(glassUnder(ink), tints);
}

// Whether `kid` is a table's caption (display: table-caption: Wikipedia's
// figure captions, the figure in display: table): the table paints its
// fill on its own box only, the caption lies beside it, on what holds the
// table. A walk up from the caption skips the table.
function tableCaption(kid) {
  return kid !== null && getComputedStyle(kid).display === "table-caption";
}

// The see-through backings `tints` ([luminance, alpha], the nearest the
// text first) over `y`; under a picture (null) the nearest of them
// painting OWN_BG at least, as if opaque, else null.
function underTints(y, tints) {
  if (y === null) {
    const own = tints.find(([, a]) => a >= OWN_BG);
    return own ? own[0] : null;
  }
  return tints.reduceRight((under, [t, a]) => mixed(t, a, under), y);
}

// The luminance of the page under its layers: the root's colour over the
// glass (with `ink`, over the worst wallpaper), null if neither.
function glassUnder(ink) {
  const style = getComputedStyle(document.documentElement);
  const glass = glassOver(null);
  const a = alpha(style.backgroundColor);
  const own = a > 0 ? luminance(style.backgroundColor) : null;
  if (glass === null)
    return a >= OWN_BG ? own : null;
  // the browser mixes the root's colour over the glass in sRGB
  const over = (g) => own === null ? g : linear(a * encoded(own) + (1 - a) * encoded(g));
  const y = over(glass);
  if (!ink)
    return y;
  // over the worst wallpaper: black under a light page, white under a
  // dark one, kept on its side of DARK_BG
  return y > DARK_BG ? Math.max(over(glassOver(0)), Math.min(y, GLASS_LIGHT_MIN))
    : Math.min(over(glassOver(1)), Math.max(y, GLASS_DARK_MAX));
}

// Whether a see-through box laid over the page shows a picture under the
// middle of `el` (in it): an <img>, <video>, <canvas> or <picture> beside
// it in the stack (frame.work's hero, its headline in a layer over the
// photo), or a video player's: a box holding a <video> as large as it
// (YouTube's control bar, laid in the player; the video is moved out of
// the box until it plays, its poster set late). The text was drawn for
// that picture, not for the glass.
function layerOverPicture(layer, el) {
  const under = beneath(layer, el);
  return under !== null && (PICTURES.has(under.localName) || picture(getComputedStyle(under)))
    || inPlayer(layer);
}

function inPlayer(layer) {
  const box = layer.parentElement;
  if (!box)
    return false;
  const b = box.getBoundingClientRect();
  return [...box.getElementsByTagName("video")].some((v) => {
    const r = v.getBoundingClientRect();
    return !holds(layer, v) && r.width * r.height >= FACE * b.width * b.height;
  });
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

// `top` (a luminance) at `a` over `under`, mixed in sRGB as the browser does.
function mixed(top, a, under) {
  return linear(a * encoded(top) + (1 - a) * encoded(under));
}

// The luminance of the page glass over a wallpaper of luminance `wall`
// (0 black, 1 white): the theme's surface (GLASS) at the tint's opacity
// (TINT); the bare surface for null, or with no tint. The light tint over
// a dark wallpaper is a mid grey, #6b7280 reading 2.9:1 on it, not 4.6:1.
// A worst case kept on the bare value's side of DARK_BG (a tint so thin
// the glass would turn tone) by GLASS_LIGHT_MIN and GLASS_DARK_MAX: the
// side picks the ink, the value how far a grey must go.
const GLASS_LIGHT_MIN = 0.2;
const GLASS_DARK_MAX = 0.16;

function glassOver(wall) {
  const style = getComputedStyle(document.documentElement);
  const y = luminance(style.getPropertyValue(GLASS).trim());
  const a = parseFloat(style.getPropertyValue(TINT));
  return y === null || wall === null || !(a >= 0 && a < 1) ? y : mixed(y, a, wall);
}

// The luminance of a bar's veil (BAR, the surface at NAV_BAR_OPACITY)
// over what is under it. A light veil shows over black, the worst of what
// can sit under it: a red thumbnail, a site's dark code window, a playing
// video, a site's scrim, the glass over a dark wallpaper (its blur keeps
// their tone). A dark veil shows over the page glass over the worst
// wallpaper (glassOver: white under it), or, with `worst`, over white: the
// worst of what scrolls under it (behind with `worst`). A label in a bar
// reads on the veil and on this too: a site's mid-grey links, drawn for its
// white header over a light section, are inked light on the dark veil of a
// dark page.
function veiled(color, worst) {
  const y = luminance(color), a = alpha(color);
  if (y === null || a >= SOLID)
    return y;
  if (y > DARK_BG)
    return mixed(y, a, 0);
  const glass = glassOver(1);
  return mixed(y, a, worst ? 1 : glass === null ? y : glass);
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
// flow of that layer: a box laid over the page (a popup menu) is no label,
// nor one on a band of another colour between it and the layer (a white
// button on an indigo call to action).
const LABEL_H = 48;
const LAID_OVER = new Set(["absolute", "fixed", "sticky"]);

function label(el, style) {
  if (el.hasAttribute(CANVAS) || el.firstElementChild || NOT_FILLS.has(el.localName)
      || LAID_OVER.has(style.position) || alpha(style.backgroundColor) < SOLID || !pageColors.has(style.backgroundColor)
      || el.getBoundingClientRect().height > LABEL_H)
    return false;
  const band = bandColor(el);
  if (band && !pageColors.has(band))
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
// page: the colours there are Dark Reader's. Nor while the root's
// background fades (the glass tint easing in or out once the scheme
// switched): the text is read on a tint not there yet, and a white
// wrapper of dark text would stay kept as a solid slab. A surface the
// add-on marked (a page layer, a bar, a block) is the add-on's, but for a page layer
// off the tone's side shorter than the page (that dark section filling
// the window, the lowest layer met): a section of the site's own, kept
// the same way, no layer any more. Under a light tone, a bar's light veil
// is its one surface (chrome): a section of the site's own in it (BBC's
// dark cookie section, Le Monde's dark nav in its header) is not kept, its
// text is inked on the veil (unkeepChrome); nor is a wide fill on the
// light side (Aftership's near-white hero): the glass is that colour
// already, the text is inked for it.
const MARKS = [CANVAS, BAR, BLOCK, FILLED];

function kept(el, fgs) {
  if (darkened || fading(document.documentElement) || (tone === "light" && inBar(el)))
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
    if (!reads(fill) || (tone === "light" && toned(fill) && wide(p)))
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

// Under a light tone, the surfaces kept before their box became a bar (a
// cookie banner inserted late, its text met first) are not kept any more:
// the bar's veil is their surface (kept).
function unkeepChrome() {
  if (tone !== "light")
    return;
  for (const el of marked("[" + KEPT + "]"))
    if (inBar(el))
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
  return readWith(el, () => el.setAttribute(KEPT, ""), () => el.removeAttribute(KEPT), fillOf);
}

// The background colour `el` paints with the mark `attr` off for the read.
function unmarked(el, attr) {
  const value = el.getAttribute(attr);
  return readWith(el, () => el.removeAttribute(attr), () => el.setAttribute(attr, value), (s) => s.backgroundColor);
}

// Reads `el`'s style with `change` made for the time of the read (`read`),
// its transitions held, then cancelled once `undo` puts it back.
function readWith(el, change, undo, read) {
  const style = el.getAttribute("style");
  el.style.setProperty("transition", "none", "important");
  change();
  const value = read(getComputedStyle(el));
  undo();
  style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  getComputedStyle(el).backgroundColor;
  for (const a of el.getAnimations())
    if (a instanceof CSSTransition && FADED.test(a.transitionProperty))
      a.cancel();
  return value;
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
      el.removeAttribute(UNFADE);
      el.style.removeProperty(SOFT_INK);
      el.style.removeProperty(UNFADE_OPACITY);
      setSides(el);
    }
    for (const el of marked("[" + GLYPH + "], [" + RULE + "]"))
      el.removeAttribute(GLYPH), el.removeAttribute(RULE);
    for (const el of marked("[" + HOLDER + "], [" + RING + "]"))
      unmarkPaint(el, HOLDER, HOLDER_INK), unmarkPaint(el, RING, RING_INK);
    for (const el of marked("[" + BLOCK + "], [" + KEPT + "]"))
      el.removeAttribute(BLOCK), el.removeAttribute(KEPT);
    owns = new WeakMap();
    cards = new Map();
    fields = new Set();
    return;
  }
  if (darkened)
    unpicture();
  unkeepChrome();
  const h = window.innerHeight;
  const near = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > -h && r.top < 2 * h;
  };
  // the blocks first: the text on them is then read on the glass, after
  // the controls made see-through again
  markClears(near);
  // the page's bands before the cards: a card is on a layer, never one
  const texts = shownText(near);
  markBands(texts);
  markCards(near, texts);
  markFields(near);
  markBlocks(near, texts);
  // a mark taken off would fade the text back to its colour when the page
  // gives it a transition (the colour read halfway, the mark set and taken
  // off in turn): it is taken off with transitions held, its style
  // attribute put back once the marks are set
  const held = [];
  softs = new Map();
  unfades = new Map();
  for (const el of marked("[" + INK + "]"))
    if (near(el)) {
      el.style.removeProperty(SOFT_INK);
      el.style.removeProperty(UNFADE_OPACITY);
      el.removeAttribute(UNFADE);
      held.push([el, el.getAttribute("style")]);
      el.style.setProperty("transition", "none", "important");
      el.removeAttribute(INK);
    }
  faces = new Map();
  const fadesSeen = new Set();
  for (const el of texts) {
    const style = getComputedStyle(el);
    if (label(el, style))
      el.setAttribute(CANVAS, FILL);
    fadePseudos(el, fadesSeen);
    inkText(el, style);
  }
  // a field's own text is no text node: the fields veiled are inked too,
  // and the see-through ones (on a bar's veil: a mega menu's search field)
  const typed = everywhere(TYPED).filter((el) => near(el)
    && (fields.has(el) || alpha(getComputedStyle(el).backgroundColor) < OWN_BG)).slice(0, INK_ELEMENTS);
  for (const el of [...fontGlyphs(near), ...maskGlyphs(near), ...shownSelects(near), ...typed])
    inkText(el, getComputedStyle(el));
  markHolders(near);
  markRing();
  barPseudos();
  markEdges(near);
  markIcons(near);
  if (held.length)
    getComputedStyle(held[0][0]).color;
  for (const [el, style] of held)
    style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  for (const [el, color] of softs)
    el.style.setProperty(SOFT_INK, color);
  for (const [el, op] of unfades) {
    el.style.setProperty(UNFADE_OPACITY, String(op));
    el.setAttribute(UNFADE, "");
  }
  markTiles(near);
  markUninverted(near);
  markGlyphs(near);
  markRules(near);
}

// INK on a text without contrast (markInk). In a bar, the veil over what
// scrolls under it counts too (veiled), but not for a colour of its own
// (GLASS_CHROMA at least: watson.ch's pink language link, its active
// state) that reads on the veil: only grey labels, drawn for a white
// header, are lost over a light section. A colour of its own on the glass
// is shaded (shadeInk), never inked to the tone.
function inkText(el, style) {
  if (!inks(style).some((c) => luminance(c) !== null))
    return;
  // lost is judged on the bare surface (behind without ink): a grey
  // readable there but not over the worst wallpaper (bg) is lifted
  // (soft), not inked to the tone
  const bare = behind(el);
  const bg = bare === null ? null : behind(el, true, false, true);
  const op = shownOpacity(el);
  const shown = (under) => inks(style).map((c) => inkOn(c, under, op)).filter((y) => y !== null);
  const fgs = shown(bg), seen = shown(bare);
  const grey = inks(style).every((c) => chroma(c) < GLASS_CHROMA);
  const worst = bare !== null && grey && inBar(el) ? behind(el, true, true, true) : bare;
  // a grey in a bar is shaded for the worst under its veil too (a dark
  // veil over a white section of the page): the back it reads least on
  const judged = worst === bare || worst === null || bg === null ? bg : leastOn(fgs, bg, worst);
  const low = (fg) => contrast(fg, bare) < INK_RATIO || contrast(fg, worst) < INK_RATIO
    || (grey && bare > DARK_BG && contrast(fg, bare) < GLASS_RATIO && onGlass(el));
  const fill = style.webkitTextFillColor || style.color;
  // a colour of its own (a gradient clipped to the text too) on the
  // glass, even lost there, is shaded, not inked
  const gradient = alpha(fill) < CLEAR && clipped(style);
  const own = !grey && (inks(style).length === 1 && inks(style)[0] === fill || gradient);
  // the gradient clipped to the text is no backing: its parent's is
  const host = clipped(style) ? up(el) || el : el;
  const glass = onGlass(host);
  const lost = bare !== null && seen.every(low) && !kept(el, seen);
  // a colour of its own reads SOFT_RATIO whichever side of the glass it is
  // on (the light end of a gradient); a grey on the far side is inked
  // a grey label on the far side of its button's fill (white on a mid
  // violet "Sign in", 3.2:1) is shaded to the other side of it
  const label = onButton(el);
  const dim = own ? fgs.some((fg) => contrast(fg, judged) < SOFT_RATIO)
    : fgs.every((fg) => muddy(fg, judged) || label && contrast(fg, judged) < SOFT_RATIO);
  // a faded text inked to the tone stays faded: on the glass or a fill of
  // its own it is shaded to read instead
  const backed = glass || onFill(host);
  if (lost && !(own && glass) && (op === 1 || !backed)) {
    inkFrom.set(el, style.color);
    el.setAttribute(INK, bare > 0.179 ? "dark" : "light");
  } else if (bg !== null && (lost || dim) && backed) {
    const soft = grey && op === 1 && !gradient ? softInk(judged)
      : grey || own ? shadeInk(faintest(style, judged, op), judged, op) : null;
    if (soft === null)
      return;
    inkFrom.set(el, style.color);
    softs.set(el, soft);
    el.setAttribute(INK, "soft");
    const lift = op < 1 ? unfaded(el, soft, judged, op) : null;
    if (lift !== null)
      unfades.set(el, lift);
  }
}

// Whether a text is the label of a control (BRANDS) painting an opaque
// fill of its own.
function onButton(el) {
  const control = el.closest(BRANDS);
  return control !== null && alpha(getComputedStyle(control).backgroundColor) >= SOLID;
}

// Of the backs `a` and `b`, the one the inks `fgs` read least on.
function leastOn(fgs, a, b) {
  const least = (back) => Math.min(...fgs.map((fg) => contrast(fg, back)));
  return least(b) < least(a) ? b : a;
}

// A faded text whose ink, even shaded to the end (white on the dark glass
// over a light wallpaper, at opacity 0.6: 4.48:1), does not read
// SOFT_RATIO and SOFT_MARGIN on `bg` at the opacity `op` it shows with:
// the opacity its own box needs for it, raised by UNFADE_STEP, 1 at most;
// null if it reads, or if its own opacity cannot help (an ancestor's).
// It gets UNFADE and that opacity in UNFADE_OPACITY inline.
const UNFADE_OPACITY = "--browserglass-unfade";
const UNFADE_STEP = 0.02;
let unfades = new Map();

function unfaded(el, ink, bg, op) {
  const y = luminance(ink), ratio = SOFT_RATIO + SOFT_MARGIN;
  let shown = op;
  while (shown < 1 && contrast(mixed(y, shown, bg), bg) < ratio)
    shown = Math.min(1, shown + UNFADE_STEP);
  const own = parseFloat(getComputedStyle(el).opacity);
  const lifted = Math.min(1, own * shown / op);
  return shown > op && lifted > own ? Math.round(lifted * 100) / 100 : null;
}

// The luminance of a text colour as it shows on `bg`: a see-through one
// (rgba(0, 0, 0, 0.57), a site's muted black) or one under an opacity
// (`op`, shownOpacity) mixed over it.
function inkOn(color, bg, op = 1) {
  const y = luminance(color), a = alpha(color) * op;
  return y === null || bg === null || a >= SOLID ? y : mixed(y, a, bg);
}

// The opacity a text shows with over what backs it: the product of its
// own and its ancestors' below the first painting a background of its own
// (OWN_BG) or a bar, which fade with the text. Under OPACITY_FLOOR (a text
// fading in, a hidden one) it counts as 1: that text is not judged faded.
const OPACITY_FLOOR = 0.4;

function shownOpacity(el) {
  let op = 1;
  for (let p = el; p && p !== document.documentElement; p = up(p)) {
    const style = getComputedStyle(p);
    if (p !== el && (alpha(style.backgroundColor) >= OWN_BG || p.hasAttribute(BAR)))
      break;
    op *= parseFloat(style.opacity);
  }
  return op < OPACITY_FLOOR ? 1 : op;
}

// The ink of a text reading least against `bg` (the lighter end of a
// gradient on a light glass), as it shows.
function faintest(style, bg, op) {
  const all = inks(style).filter((c) => luminance(c) !== null);
  const reads = (c) => contrast(inkOn(c, bg, op), bg);
  return all.reduce((a, c) => reads(c) < reads(a) ? c : a);
}

// Whether a text sits on a plain colour of its own (a grey count on a
// white card, a late box, a card in rgba(255, 255, 255, 0.6) over the
// glass, read with the glass under it: behind): no picture, its first
// ancestor painting a background paints it OWN_BG at least, not a page
// layer the glass cleared.
function onFill(el) {
  for (let p = el, kid = null; p && p !== document.documentElement; kid = p, p = up(p)) {
    if (tableCaption(kid))
      continue;
    const style = getComputedStyle(p);
    if (picture(style) || p.hasAttribute(CANVAS))
      return false;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return true;
  }
  return false;
}

// Secondary text in a grey (GLASS_CHROMA at most: a shop's #7a7a7a meta
// line, a dark theme's slate caption) readable on the glass, on the tone's
// side of it, but under SOFT_RATIO (WCAG's 4.5:1) against it gets INK
// "soft": the grey just dark (or light) enough to reach SOFT_RATIO, in
// SOFT_INK inline, still greyer than the text inked to the tone. A
// colour of its own (a link, a price, a red timer) keeps its hue, shaded
// just enough (shadeInk).
const SOFT_RATIO = 4.5;
const SOFT_MARGIN = 0.1;
const SOFT_INK = "--browserglass-soft-ink";
let softs = new Map();

function muddy(fg, bg) {
  return (bg > 0.179 ? fg < bg : fg > bg) && contrast(fg, bg) < SOFT_RATIO;
}

// The grey reading SOFT_RATIO (and SOFT_MARGIN) against `bg`, rounded away
// from it.
function softInk(bg) {
  const ratio = SOFT_RATIO + SOFT_MARGIN;
  const dark = bg > 0.179;
  const y = dark ? (bg + 0.05) / ratio - 0.05 : ratio * (bg + 0.05) - 0.05;
  const v = encoded(Math.min(1, Math.max(0, y))) * 255;
  const c = dark ? Math.floor(v) : Math.ceil(v);
  return "rgb(" + c + ", " + c + ", " + c + ")";
}

// A colour of its own (a site's blue link, a red label) under SOFT_RATIO on
// the glass keeps its hue: mixed towards black on a light glass (towards
// white on a dark one), SHADE_STEPS steps at most, until it reads `ratio`
// (SOFT_RATIO and SOFT_MARGIN) against `bg` as it shows at the opacity
// `op`; null if it never does, black (white) under an opacity that keeps
// any colour from reaching it (the closest there is).
const SHADE_STEPS = 50;

function shadeInk(color, bg, op = 1, ratio = SOFT_RATIO + SOFT_MARGIN) {
  const c = channels(color);
  if (!c)
    return null;
  const light = bg > DARK_BG;
  let rgb = c;
  for (let i = 1; i <= SHADE_STEPS; i++) {
    const t = i / SHADE_STEPS;
    rgb = c.map((v) => Math.round(light ? v * (1 - t) : v + (255 - v) * t));
    const y = rgbLuminance(...rgb.map((v) => linear(v / 255)));
    if (contrast(op < 1 ? mixed(y, op, bg) : y, bg) >= ratio)
      return "rgb(" + rgb.join(", ") + ")";
  }
  return op < 1 ? "rgb(" + rgb.join(", ") + ")" : null;
}

// A placeholder (::placeholder, which the walk of text nodes never meets)
// reading under SOFT_RATIO against its field, as it shows (its colour at
// its opacity over the field's own fill, or over the glass), gets HOLDER
// and, in HOLDER_INK inline, its colour shaded to read SOFT_RATIO
// (shadeInk); the glass styles paint it, opaque. Fields near the window,
// at most INK_ELEMENTS.
const HOLDER = "data-browserglass-holder";
const HOLDER_INK = "--browserglass-holder-ink";
const HOLDERS = "input[placeholder], textarea[placeholder]";

function markHolders(near) {
  const fields = marked(HOLDERS).filter(near).slice(0, INK_ELEMENTS);
  for (const el of marked("[" + HOLDER + "]"))
    unmarkPaint(el, HOLDER, HOLDER_INK);
  for (const el of fields) {
    const ph = getComputedStyle(el, "::placeholder");
    const op = parseFloat(ph.opacity);
    // the back it reads least on
    const backs = fieldBacks(el).filter((b) => b !== null);
    const reads = (b) => contrast(inkOn(ph.color, b, op), b);
    const bg = backs.reduce((a, b) => a === null || reads(b) < reads(a) ? b : a, null);
    const y = inkOn(ph.color, bg, op);
    // soft on its back, or of the wrong tone, lost on every back (a white
    // placeholder on a light veil)
    const lost = bg !== null && y !== null && (muddy(y, bg) || backs.every((b) => reads(b) < SOFT_RATIO));
    const ink = lost ? shadeInk(ph.color, bg) : null;
    if (ink) {
      el.setAttribute(HOLDER, "");
      el.style.setProperty(HOLDER_INK, ink);
    }
  }
}

// The luminances a field may show behind its text: the first fill met
// from it up, when see-through (a field the glass styles veil, GitHub's
// wrapper of its input) mixed over what is behind that box, that too and
// the glass (a veil drawn thinner than its colour says); behind() else.
function fieldBacks(el) {
  for (let p = el; p && p !== document.documentElement && !p.hasAttribute(BAR); p = up(p)) {
    const style = getComputedStyle(p);
    const a = alpha(style.backgroundColor), y = luminance(style.backgroundColor);
    if (picture(style) || face(p) !== undefined)
      break;
    if (a >= OWN_BG && a < SOLID && y !== null) {
      const under = behind(up(p) || document.documentElement, true, false, true);
      // the glass under it all too, the worst wallpaper's (a veiled
      // panel holding the field shows lighter than its colour says)
      const glass = under === null ? null : glassOver(under > DARK_BG ? 0 : 1);
      return under === null ? [y] : [mixed(y, a, under), under, glass];
    }
    if (a >= OWN_BG)
      break;
  }
  return [behind(el, false, false, true)];
}

// The focus ring of the focused element (:focus-visible, an outline of
// its own) reading under RING_RATIO (WCAG's 3:1 for what is not text)
// against what is around it (behind its parent, over the worst
// wallpaper) gets RING and, in RING_INK inline, its colour shaded to read
// RING_RATIO and SOFT_MARGIN (shadeInk); the glass styles paint it while
// it is focused. Read on each pass of the ink (focusin starts one).
const RING = "data-browserglass-ring";
const RING_INK = "--browserglass-ring-ink";
const RING_RATIO = 3;

function markRing() {
  for (const el of marked("[" + RING + "]"))
    unmarkPaint(el, RING, RING_INK);
  let el = document.activeElement;
  while (el && el.shadowRoot && el.shadowRoot.activeElement)
    el = el.shadowRoot.activeElement;
  if (!el || el === document.body || !el.matches(":focus-visible"))
    return;
  const style = getComputedStyle(el);
  const around = up(el);
  const bg = around ? behind(around, true, false, true) : null;
  const y = luminance(style.outlineColor);
  if (style.outlineStyle === "none" || !(parseFloat(style.outlineWidth) > 0) || bg === null || y === null
      || contrast(y, bg) >= RING_RATIO)
    return;
  const ink = shadeInk(style.outlineColor, bg, 1, RING_RATIO + SOFT_MARGIN);
  if (ink) {
    el.setAttribute(RING, "");
    el.style.setProperty(RING_INK, ink);
  }
}

// Takes off a mark painting a colour set inline (`prop`), and the style
// attribute it leaves empty.
function unmarkPaint(el, mark, prop) {
  if (!el.hasAttribute(mark))
    return;
  el.removeAttribute(mark);
  el.style.removeProperty(prop);
  if (el.getAttribute("style") === "")
    el.removeAttribute("style");
}

// Icon-font glyphs: an empty <i> or <span> near the window whose ::before
// or ::after draws a string in the element's colour (Font Awesome's
// i.fa-language in PyPI's header: content "\f1ab" in its font) is text the
// walk of text nodes never meets. It is inked as text is, the glyph
// following its colour. At most INK_ELEMENTS.
const GLYPH_TAGS = "i, span";
const DRAWN_STRING = /^"(.+)"$/;

function fontGlyphs(near) {
  const found = [];
  const els = everywhere(GLYPH_TAGS);
  for (let i = 0; i < els.length && found.length < INK_ELEMENTS; i++) {
    const el = els[i];
    if (el.firstElementChild || el.textContent.trim() || !near(el)
        || !el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      continue;
    const color = getComputedStyle(el).color;
    if (PSEUDOS.some((p) => {
      const s = getComputedStyle(el, "::" + p);
      return s.display !== "none" && DRAWN_STRING.test(s.content) && s.color === color;
    }))
      found.push(el);
  }
  return found;
}

// Mask icons: a control's ::before or ::after, ICON_SIDE px at most,
// painting the control's colour through a mask (MDN's chevrons and menu
// icons, white for its dark hero, beside labels inked dark), is drawn in
// its text colour. The control is inked as text is, and the part is named
// in GLYPH, so that it paints the ink (currentcolor) whatever colour the
// site wrote for it. At most INK_ELEMENTS.
function maskGlyphs(near) {
  const found = [];
  const els = everywhere(CONTROLS);
  for (let i = 0; i < els.length && found.length < INK_ELEMENTS; i++) {
    const el = els[i];
    if (!near(el) || !el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      continue;
    // its label may be inked already, this pass: the colour it had
    const color = ownColor(el);
    const parts = PSEUDOS.filter((p) => {
      const s = getComputedStyle(el, "::" + p);
      return s.content !== "none" && s.display !== "none" && URL_IMAGE.test(s.maskImage)
        && s.backgroundColor === color && parseFloat(s.width) <= ICON_SIDE && parseFloat(s.height) <= ICON_SIDE;
    });
    if (!parts.length)
      continue;
    const had = (el.getAttribute(GLYPH) || "").split(" ");
    const all = [...new Set([...had, ...parts])].filter(Boolean).join(" ");
    if (all !== had.join(" "))
      el.setAttribute(GLYPH, all);
    found.push(el);
  }
  return found;
}

// Drop-down fields (<select>): the option they show is drawn in the
// field's colour, its text in an <option> the walk of text nodes passes
// by (no box of its own). A field near the window is inked as text is
// (admin.ch's white "FR" on its top bar, the bar's dark band cleared under
// a light theme); its list's options keep the system's colours
// (browserglass.py). At most INK_ELEMENTS.
function shownSelects(near) {
  return everywhere("select").filter((el) => near(el)
    && el.checkVisibility({visibilityProperty: true, opacityProperty: true})).slice(0, INK_ELEMENTS);
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
//   turned back, so a coloured part keeps its hue), its readable part
//   no larger than its dark ink (an accent: a mascot's black head round
//   its large pink face is a picture, inverted the face turns maroon);
//   shaded dark ink (a black product cut out of its photo), a picture in
//   many tones (an illustrated badge) or one mostly readable (the
//   mascot) keeps the tile, which keeps its shading (one from
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
const BACK_INK = 0.5;
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
// light), "plain" (its filter gone, see lightInk), "back" (a dark backing,
// see backed), "photo" (shot on white) or null.
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
  if (darkened && refilled(el))
    return "invert";
  if (inkedBar(el))
    return lightInk(el, true);
  const light = r.height <= LOGO_SIDE && onGlass(el.parentElement || document.documentElement) ? lightInk(el) : null;
  if (light === "back" || light !== null && grey(el))
    return light;
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
  const rest = s.inks.slice(dark.length);
  if (oneTone(dark) && oneTone(rest) && rest.length <= dark.length)
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
// filter as far as its invert() and brightness() go (shownInk). A header
// in the flow (HEADS) the glass cleared is read the same way once its
// labels got dark INK (booking.com's blue header, cleared by its site
// style: its white word mark on the light glass). A picture straight on
// the glass or a veil (onGlass: no fill of the site's under it) is read
// the same way, whatever its labels: what decides is the tone the glass
// ends up with, not the wallpaper under it nor the scroll (GNOME's
// Discourse, its white logo in a header with no label of its own; a white
// svg drawn on a light page). Only a picture LOGO_SIDE px tall at most
// (a logo, an icon: no photo sampled for it) whose ink is grey (under
// MONO_CHROMA each): a yellow or a pale blue logo is a colour logo, left
// alone. Lost ink of many tones is inverted too when all of the ink is
// lost, in a bar with dark labels or grey (MDN's pale blue and white word
// mark, Le Monde's grey and white account icon): its hues turned back,
// nothing readable is lost. A colour logo whose lost part is light grey
// gets a dark backing instead (backed). An icon (ICON_SIDE px at most both
// ways) is lost under GLASS_RATIO, as a graphic needs 3:1. On a dark
// background only a picture the site's own filter darkened is looked at
// (frame.work's white word mark its invert(1) turns black, on a page Dark
// Reader darkens): "plain" when its ink reads without the filter.
const HEADS = "header, [role=banner]";
const DARK_INK = "[" + INK + "=\"dark\"]";
const LOGO_SIDE = 96;

function grey(el) {
  const raw = rawInk(el);
  return raw !== null && raw.tints.every((c) => c < MONO_CHROMA);
}

function inkedBar(el) {
  for (let p = up(el); p; p = up(p))
    if (p.hasAttribute(BAR) || p.matches(HEADS) && p.querySelector(DARK_INK))
      return !!p.querySelector(DARK_INK);
  return false;
}

function lightInk(el, bar = false) {
  const bg = behind(el.parentElement || document.documentElement);
  if (bg === null)
    return null;
  if (el.getAttribute(TILE) === "plain")
    return "plain";
  const filter = el.hasAttribute(TILE) ? "none" : getComputedStyle(el).filter;
  // on a dark background, only the site's own filter is looked at
  if (bg <= DARK_BG && filter === "none")
    return null;
  const raw = rawInk(el);
  if (!raw)
    return null;
  const r = el.getBoundingClientRect();
  const ratio = r.width <= ICON_SIDE && r.height <= ICON_SIDE ? GLASS_RATIO : INK_RATIO;
  const lost = (y) => contrast(y, bg) < ratio;
  const shown = shownInk(raw.inks, filter);
  const light = shown.filter(lost);
  if (light.length < TILE_INK * shown.length)
    return null;
  if (filter === "none" && light.length === shown.length && (bar || raw.tints.every((c) => c < MONO_CHROMA)))
    return "invert";
  if (!oneTone(light) || !oneTone(shown.filter((y) => !lost(y))))
    return null;
  if (filter === "none")
    return oneHue(raw.tints) ? "invert" : backed(el, raw, lost);
  return raw.inks.filter(lost).length < TILE_INK * raw.inks.length ? "plain" : null;
}

// A colour logo whose light grey part is lost on the light veil
// (python.org's white word mark beside its blue and yellow snake, made
// for a dark header): BACK_INK of its ink at least, light grey (under
// MONO_CHROMA) and lost, gets "back", a dark backing; its colours stay.
// A picture is read by its pixels, and a colour logo whose white is a
// smaller part (PyPI's) stays as it is. An inline svg is read by the
// boxes of its shapes (svgBacked).
function backed(el, raw, lost) {
  if (el.localName === "svg")
    return svgBacked(el, lost);
  if (el.localName !== "img")
    return null;
  const grey = raw.inks.filter((y, i) => lost(y) && raw.tints[i] < MONO_CHROMA);
  return grey.length >= BACK_INK * raw.inks.length ? "back" : null;
}

// An inline svg logo in two colours whose light grey shapes are lost
// (Ars Technica's white "TECHNICA" beside its orange disc): "back" when
// those shapes cover TILE_INK of the area of its painted shapes' boxes.
// A lost shape whose box lies within another painted shape's (a toggle's
// white knob on its blue pill, a white tick on a badge) sits on that
// shape, not on the glass: not counted lost.
function svgBacked(svg, lost) {
  const shapes = [];
  for (const shape of svg.querySelectorAll(SHAPES)) {
    if (shape.closest(UNPAINTED))
      continue;
    const style = getComputedStyle(shape);
    const paint = style.fill !== "none" && alpha(style.fill) >= CLEAR ? style.fill : style.stroke;
    const box = shape.getBoundingClientRect();
    if (paint !== "none" && alpha(paint) >= CLEAR && box.width * box.height > 0)
      shapes.push({paint, box});
  }
  const within = (a, b) => a !== b && a.box.left >= b.box.left && a.box.right <= b.box.right
    && a.box.top >= b.box.top && a.box.bottom <= b.box.bottom;
  let all = 0, grey = 0;
  for (const s of shapes) {
    const area = s.box.width * s.box.height;
    all += area;
    const y = luminance(s.paint);
    if (y !== null && lost(y) && chroma(s.paint) < MONO_CHROMA && !shapes.some((o) => within(s, o)))
      grey += area;
  }
  return all > 0 && grey >= TILE_INK * all ? "back" : null;
}

// Whether a picture is of one colour as well as its light ink of one
// tone: the chromas of all its pixels (its readable ink too), MONO_EDGE
// steps in from each end, under MONO_CHROMA apart. PyPI's logo, white and
// yellow on its blue, and The Verge's privacy toggle, a white knob on a
// saturated blue pill, are colour logos, left alone; a white word mark is
// inverted.
function oneHue(tints) {
  const c = [...tints].sort((a, b) => a - b);
  return c.length <= 2 * MONO_EDGE || c[c.length - 1 - MONO_EDGE] - c[MONO_EDGE] < MONO_CHROMA;
}

// Light ink Dark Reader turned dark. It reads the fill attribute of a
// shape larger than a small icon as a background colour and darkens it:
// a white word mark drawn for a brand header (booking.com's, its path
// fill="#fff") goes near-black on the dark glass. An inline <svg> on a
// dark background whose painted shapes all carry Dark Reader's fill
// (DR_FILL), their own fill attribute light (written) and of one tone,
// reading against that background while the fill shown does not, gets
// "invert": its ink light again.
const DR_FILL = "data-darkreader-inline-fill";

function refilled(el) {
  if (el.localName !== "svg" || el.hasAttribute(DR_INVERT) || el.parentElement && el.parentElement.closest("svg"))
    return false;
  const bg = behind(el.parentElement || document.documentElement);
  if (bg === null || bg > DARK_BG)
    return false;
  const own = [];
  for (const shape of el.querySelectorAll(SHAPES)) {
    if (shape.closest(UNPAINTED))
      continue;
    const style = getComputedStyle(shape);
    if (style.stroke !== "none" && alpha(style.stroke) >= CLEAR)
      return false;
    if (style.fill === "none" || alpha(style.fill) < CLEAR)
      continue;
    const y = luminance(written(shape.getAttribute("fill"))), shown = luminance(style.fill);
    if (!shape.hasAttribute(DR_FILL) || y === null || shown === null || y < bg || contrast(y, bg) < INK_RATIO
        || contrast(shown, bg) >= INK_RATIO)
      return false;
    own.push(y);
  }
  return own.length > 0 && oneTone(own.sort((a, b) => a - b));
}

// An opaque colour as a page writes it ("#fff", "white"), as rgb(), null
// for anything else.
function written(value) {
  palette = palette || document.createElement("canvas").getContext("2d");
  palette.fillStyle = "rgba(0, 0, 0, 0)";
  palette.fillStyle = value || "";
  const m = /^#(..)(..)(..)$/.exec(palette.fillStyle);
  return m ? "rgb(" + m.slice(1).map((h) => parseInt(h, 16)).join(", ") + ")" : null;
}

// The ink of a picture as drawn, before any filter: the sample of an
// <img> with see-through parts, or of the background picture of an
// element (barIcons, loaded apart: backImage), the colour of a masked one,
// the paints of a top inline <svg> not in its text colour, sorted:
// {inks, tints}, the luminances and the chromas beside them; null for
// anything else.
function rawInk(el) {
  const style = getComputedStyle(el);
  if (!PICTURES.has(el.localName) && style.maskImage !== "none") {
    const y = luminance(style.backgroundColor);
    return style.backgroundImage === "none" && y !== null && alpha(style.backgroundColor) >= CLEAR
      ? {inks: [y], tints: [chroma(style.backgroundColor)]} : null;
  }
  const url = el.localName === "img" ? null : style.backgroundImage.match(URL_IMAGE);
  if (el.localName === "img" || url) {
    const s = url ? sample(backImage(url[1]), el.getBoundingClientRect()) : sample(el);
    return s && s.clear >= TILE_CLEAR ? {inks: s.inks, tints: s.tints} : null;
  }
  if (el.localName !== "svg" || el.parentElement && el.parentElement.closest("svg") || inColor(el))
    return null;
  const paints = shapePaints(el).map((p) => [luminance(p), chroma(p)]).filter(([y]) => y !== null);
  if (!paints.length)
    return null;
  const steps = quantiles(paints.sort((a, b) => a[0] - b[0]));
  return {inks: steps.map(([y]) => y), tints: steps.map(([, c]) => c)};
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
  for (let p = el, kid = null; p && p !== document.documentElement; kid = p, p = p.parentElement) {
    if (tableCaption(kid))
      continue;
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
// inks: the luminance of the others at INK_STEPS quantiles, tints: the
// chroma of the pixel at each of those, white: the
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
  // [luminance, chroma] of each opaque pixel
  const px = [];
  for (let i = 0; i < data.length; i += 4)
    if (data[i + 3] >= CLEAR * 255) {
      const [r, g, b] = [data[i], data[i + 1], data[i + 2]];
      px.push([rgbLuminance(linear(r / 255), linear(g / 255), linear(b / 255)),
        (Math.max(r, g, b) - Math.min(r, g, b)) / 255]);
    }
  if (!px.length)
    return null;
  const steps = quantiles(px.sort((a, b) => a[0] - b[0]));
  return {clear: 1 - px.length / (w * h), inks: steps.map(([y]) => y), tints: steps.map(([, c]) => c), white,
    far: false};
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

// A picture loaded after the last pass is looked at again (a style sheet
// loaded reads the tone again, recoloured): a lazy one
// (no width, so not near, until it is in: a shop's product photos
// scrolled into view), a source swapped, pixels not there to read. One
// listener for the document (load does not bubble, it is caught on its
// way down), nothing watched per picture.
function loaded(e) {
  if (off === false && e.target.localName === "img")
    ink();
  else if (sheetNode(e.target))
    recoloured();
}

// Menus shown on hover: the floating layers looked for again, once per
// INK_MS at most.
let floatFrame = 0, floatsAt = -Infinity;

// A menu opening a while after the pointer came (a hover delay, an
// animation) with no other event: the pass runs again FLOAT_LATE_MS after
// the last hover (frames, no timer).
const FLOAT_LATE_MS = 500;
let lateFrame = 0, lateAt = 0;

function hovered() {
  lateAt = performance.now() + FLOAT_LATE_MS;
  if (off === false && !lateFrame)
    lateFrame = requestAnimationFrame(function tick(now) {
      if (now < lateAt) {
        lateFrame = requestAnimationFrame(tick);
        return;
      }
      lateFrame = 0;
      passFloats();
    });
  passFloats();
}

function passFloats() {
  if (off === false && !floatFrame)
    floatFrame = requestAnimationFrame(function tick(now) {
      if (now - floatsAt < INK_MS) {
        floatFrame = requestAnimationFrame(tick);
        return;
      }
      floatFrame = 0;
      floatsAt = now;
      markFloats();
      ink();
    });
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

// The layers are looked for again, once per INK_MS at most (each pass runs
// hit-test grids and style reads, too much for every frame of a long
// scroll; the last request is still served): when the page
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
let layerFrame = 0, layersAt = -Infinity;

function layers() {
  if (!layerFrame)
    layerFrame = requestAnimationFrame(function tick(now) {
      if (now - layersAt < INK_MS) {
        layerFrame = requestAnimationFrame(tick);
        return;
      }
      layerFrame = 0;
      layersAt = now;
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

// The page's own colours change without a reload and without touching
// <html>: a single-page app's style sheets land in <head> after its text
// was first measured (YouTube's black text, then its dark theme), a sheet
// finishes loading (loaded), or a theme class lands on <body>. The tone
// is read again in the next frame, and the bars, their veils and the ink
// follow it (layers): a bar never keeps the veil of the other tone. Dark
// Reader's own style elements are not the page's, nor is the inline style
// of the body (rewritten on scroll); a darkened page stays dark.
const SHEET_NODES = "style, link[rel~=stylesheet i]";
let recolouredFrame = 0;

function recoloured() {
  if (darkened || off === true || recolouredFrame)
    return;
  recolouredFrame = requestAnimationFrame(() => {
    recolouredFrame = 0;
    measure();
    darken();
    paint();
    layers();
  });
}

function sheetNode(node) {
  return node.nodeType === Node.ELEMENT_NODE && node.matches(SHEET_NODES) && !node.classList.contains("darkreader");
}

const sheets = new MutationObserver((records) => {
  if (records.some((r) => r.type === "childList"
      ? [...r.addedNodes, ...r.removedNodes].some(sheetNode)
      : r.attributeName !== "style" && !r.attributeName.startsWith(OWN)))
    recoloured();
});

function watchSheets() {
  const head = document.head, body = document.body;
  if (head === sheets.head && body === sheets.body)
    return;
  sheets.disconnect();
  sheets.head = head;
  sheets.body = body;
  if (head)
    sheets.observe(head, {childList: true});
  if (body)
    sheets.observe(body, {attributes: true});
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
for (const type of ["pointerover", "focusin"])
  document.addEventListener(type, hovered, {capture: true, passive: true});
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

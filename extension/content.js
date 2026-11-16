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
// site. Its blur ends with VEIL, a filter this script puts in the page:
// Firefox lays the blurred backdrop over what scrolls under the bar, so
// on the glass (a see-through page) a thin line of text, blurred into a
// faint haze, still showed sharp through it, unlike a picture; VEIL lays
// that haze on the glass's colour, as on a page with a background of its
// own: the text under the bar is blurred like a picture. Text left
// without contrast once its background went (dark text on
// the dark glass) gets data-browserglass-ink, a readable colour, and a
// picture made for a white page on a background now dark (a product photo
// whose white a site wipes out with mix-blend-mode, a black logo on a
// page Dark Reader darkens) gets data-browserglass-tile: a white tile, or
// light ink for a monochrome one.
// An inline SVG logo Dark Reader inverts though its shapes already paint
// light gets data-browserglass-uninvert: no filter. A glyph drawn with a
// background (the bars of a menu button) left without contrast gets
// data-browserglass-glyph, naming its parts: they are painted in the text
// colour. A thin rule in a neutral colour (a separator) Dark Reader left
// without contrast gets data-browserglass-rule: a light neutral.
// A block Dark Reader turns into an opaque near-black panel (a white
// card, a strip) gets data-browserglass-block: a light veil, or glass.
// A small button in a saturated colour gets data-browserglass-brand,
// before Dark Reader dulls it: it keeps its fill and its label's colour.
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
// under its light page.
function backdrop(el) {
  return (el.hasAttribute(CANVAS) || large(el))
    && el.getBoundingClientRect().top + window.scrollY < window.innerHeight;
}

// Text drawn over a picture (an <img>, a <video>, a <canvas>, an <svg> or
// a background image sized to cover its box, not a texture nor an icon,
// under its middle: a shop's white headlines on its banners) is read on
// the picture, as on a card. One hit test per element in the window, at
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
    for (const e of document.elementsFromPoint(x, y)) {
      if (e === document.body || e === document.documentElement || e.hasAttribute(CANVAS))
        break;
      if (el.contains(e))
        continue;
      const style = getComputedStyle(e);
      if ((/url\(/.test(style.backgroundImage) && /cover|contain/.test(style.backgroundSize))
          || (!e.contains(el) && PICTURES.has(e.localName))) {
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
// "Skip to main content" link does not vote.
const HIDDEN_DEPTH = 2;

function unseen(el) {
  const r = el.getBoundingClientRect();
  if (r.right + window.scrollX <= 0 || r.bottom + window.scrollY <= 0)
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
    const s = pixels(c);
    if (s && s.clear <= BOARD_CLEAR)
      return s.inks[INK_STEPS / 2] > 0.179 ? "light" : "dark";
  }
  return null;
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
// the site's menus, decides
// first, the mid-grey band aside (siteChrome, MID_LOW), then the text
// outside the menus, cards included (VOTE_NODES, VOTE_CHARS). Text out of
// sight does not vote (unseen). Without text on the page's background, a
// drawing board's pixels come before the other levels (boardTone).
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
    // tallies the text under root; with menus, the site's menus met on the
    // way are skipped whole (a portal's header can hold thousands of text
    // nodes before the content) and listed there
    const tally = (root, menus) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
        (node) => {
          if (node.nodeType === Node.TEXT_NODE)
            return NodeFilter.FILTER_ACCEPT;
          if (menus && siteChrome(node)) {
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
            y = luminance(getComputedStyle(p).color);
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
  // no text on the page's background: a drawing board under the app
  const board = document.body && !decides(page) ? boardTone() : null;
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
// copies: no cookies, no referrer, and only a stylesheet.
function fetchStylesheet(url) {
  return fetch(url, {credentials: "omit", cache: "force-cache", referrerPolicy: "no-referrer"})
    .then((r) => {
      if (!r.ok || !/^text\/css\b/i.test(r.headers.get("Content-Type") || ""))
        throw new Error("not a stylesheet");
      return r;
    });
}

// The marks of a page's own dark theme set on <html> (the ones the glass
// styles read as a page with a dark version: _DARK_PAGE_MARKERS).
const NATIVE_CLASSES = ["dark", "dark-mode", "theme-dark"];
const NATIVE_ATTRS = [["data-theme", "dark"], ["data-bs-theme", "dark"], ["data-color-mode", "dark"],
  ["data-theme-mode", "dark"], ["data-mode", "dark"], ["dark", ""]];
const NO_TRANSITIONS = "*, *::before, *::after { transition: none !important; }";

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
// ones), and kept only if the text turned light; true then.
function nativeDark() {
  const root = document.documentElement;
  native = {classes: NATIVE_CLASSES.filter((c) => !root.classList.contains(c)),
    attrs: NATIVE_ATTRS.map(([name]) => [name, root.getAttribute(name)])};
  const hold = document.createElement("style");
  hold.textContent = NO_TRANSITIONS;
  (document.head || root).append(hold);
  root.classList.add(...NATIVE_CLASSES);
  for (const [name, value] of NATIVE_ATTRS)
    root.setAttribute(name, value);
  measure();
  hold.remove();
  if (tone === "dark")
    return true;
  nativeRestore();
  measure();
  return false;
}

// A light page is darkened once its tone is settled (enough text, or the
// page loaded): a single-page app still rendering may show little text.
// Its own dark theme is tried first; the marks are taken back with a light
// theme, once the page is excluded or once the helper stops the darkening.
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
  // took its dark theme back
  if (native && (off !== false || !helperDark || tone === "light"
      || !window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    nativeRestore();
    measure();
  }
  if (off !== false || !helperDark || !window.matchMedia("(prefers-color-scheme: dark)").matches)
    nativeTried = false;
  const theme = darkTheme();
  if (darkened && !theme) {
    darkened = false;
    DarkReader.disable();
    frameSchemes();
    for (const el of document.querySelectorAll("[" + CANVAS + "], [" + FILLED + "], [" + BLOCK + "]"))
      el.removeAttribute(CANVAS), el.removeAttribute(FILLED), el.removeAttribute(BLOCK);
    unmarkBrands();
    measure();
  } else if (!darkened && theme && tone === "light" && !themeWait
      && (sampled >= ENOUGH_TEXT || document.readyState === "complete")) {
    if (!nativeTried) {
      nativeTried = true;
      if (nativeDark())
        return;
    }
    darkened = true;
    markBrands();
    DarkReader.setFetchMethod(fetchStylesheet);
    DarkReader.enable(theme, DR_FIXES);
    frameSchemes();
    measure();
  }
}

// A saturated button keeps its colours: Dark Reader darkens every fill,
// a brand colour too (a yellow turns olive, its petrol label light grey:
// 2.8:1; a violet goes dull). Just before Dark Reader runs (the page's
// colours still its own), a control (BRANDS) at most BRAND_W by BRAND_H
// px, with a label (BRAND_TEXT characters at most), whose opaque fill
// (SOLID; its own, or that of a ::before or ::after covering FACE of it,
// no background image) has BRAND_CHROMA of chroma at least and reads
// against its label (BRAND_READ) gets BRAND naming that part, and both
// colours inline (BRAND_FILL, BRAND_INK; Dark Reader leaves the inline
// style of a marked element alone: DR_FIXES): the glass styles paint them
// back, the label's on the whole control. At most BRAND_ELEMENTS are
// looked at. A button drawn once the page is darkened is not seen (Dark
// Reader has its colours by then); the marks go with the darkening.
const BRAND_FILL = "--browserglass-brand-fill";
const BRAND_INK = "--browserglass-brand-ink";
const BRANDS = "button, a[href], [role=button], input[type=submit], input[type=button]";
const BRAND_W = 480;
const BRAND_H = 96;
const BRAND_TEXT = 60;
const BRAND_CHROMA = 0.4;
const BRAND_READ = 3;
const BRAND_ELEMENTS = 1000;
const DR_FIXES = {ignoreInlineStyle: ["[" + BRAND + "]"]};

function markBrands() {
  const controls = document.body ? document.body.querySelectorAll(BRANDS) : [];
  for (let i = 0; i < controls.length && i < BRAND_ELEMENTS; i++) {
    const el = controls[i];
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || r.width > BRAND_W || r.height > BRAND_H)
      continue;
    const ink = labelColor(el);
    if (!ink)
      continue;
    for (const part of [...PSEUDOS, "self"]) {
      const fill = brandFill(el, r, part);
      if (fill && contrast(luminance(fill), luminance(ink)) >= BRAND_READ) {
        el.setAttribute(BRAND, part);
        el.style.setProperty(BRAND_FILL, fill);
        el.style.setProperty(BRAND_INK, ink);
        break;
      }
    }
  }
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

// The saturated fill a part of `el` ("self", "before", "after") paints
// over it, null if none.
function brandFill(el, r, part) {
  const style = getComputedStyle(el, part === "self" ? null : "::" + part);
  if (part !== "self" && (style.content === "none" || style.display === "none"
      || parseFloat(style.width) * parseFloat(style.height) < FACE * r.width * r.height))
    return null;
  const fill = style.backgroundColor;
  return style.backgroundImage === "none" && alpha(fill) >= SOLID && chroma(fill) >= BRAND_CHROMA ? fill : null;
}

// The chroma (0-1) of an rgb() colour, 0 for another space.
function chroma(color) {
  const m = /^rgba?\(([^)]*)\)/.exec(color);
  if (!m)
    return 0;
  const c = m[1].split(/[\s,/]+/).slice(0, 3).map(parseFloat);
  return (Math.max(...c) - Math.min(...c)) / 255;
}

function unmarkBrands() {
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
// page), looked at on each pass of the layers; taken off after.
const frames = document.getElementsByTagName("iframe");
let schemed = new Map();

function frameSchemes() {
  if (!darkened) {
    for (const [el, [value, priority]] of schemed)
      value ? el.style.setProperty("color-scheme", value, priority) : el.style.removeProperty("color-scheme");
    schemed = new Map();
    return;
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
const GRID = 5;
const CLEAR = 0.5;
const SOLID = 0.99;
const FILL = "fill";
const pageColors = new Set();

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
  if (tone === null)
    return false;
  const m = /^rgba?\(([^)]*)\)/.exec(color);
  if (!m)
    return false;
  const c = m[1].split(/[\s,/]+/).slice(0, 3).map(parseFloat);
  const y = luminance(color);
  if ((Math.max(...c) - Math.min(...c)) / 255 > COLUMN_CHROMA
      || (tone === "dark" ? y > COLUMN_DARK : y < COLUMN_LIGHT))
    return false;
  if (getComputedStyle(el).backgroundImage !== "none")
    return false;
  // a fixed side panel is the window's bar (markBars), not the page's
  for (let e = el; e && e !== document.body; e = e.parentElement)
    if (getComputedStyle(e).position === "fixed")
      return false;
  const area = seen(r, w, h);
  for (const media of el.querySelectorAll(COLUMN_MEDIA))
    if (seen(media.getBoundingClientRect(), w, h) >= 0.5 * area)
      return false;
  return true;
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
    for (let e = el; e && e !== root; e = e.parentElement)
      if (getComputedStyle(e).position === "fixed")
        return true;
    return false;
  };
  const glass = (clear(root) || tinted(root)) && clear(document.body);
  for (const el of document.querySelectorAll("[" + CANVAS + "]"))
    if (!glass || (!large(el) && !tall(el) && !wide(el) && el.getAttribute(CANVAS) !== FILL))
      el.removeAttribute(CANVAS);
  if (!glass) {
    for (const el of document.querySelectorAll("[" + FILLED + "]"))
      el.removeAttribute(FILLED);
    pageColors.clear();
    return;
  }
  const seen = new Set([root, document.body]);
  for (let i = 0; i < GRID; i++) {
    for (let j = 0; j < GRID; j++) {
      const stack = document.elementsFromPoint((i + 0.5) * w / GRID, (j + 0.5) * h / GRID);
      const below = [];
      for (let n = stack.length - 1; n >= 0; n--) {
        const el = stack[n];
        if (el === root || el === document.body)
          continue;
        if (el.hasAttribute(CANVAS))
          break;
        if (clear(el)) {
          below.push(el);
          continue;
        }
        // a fixed layer over the page's own content: a dialog, a cookie
        // banner, never the page's background
        if (below.some((b) => !b.contains(el)) && pinned(el))
          break;
        const color = getComputedStyle(el).backgroundColor;
        if (alpha(color) >= SOLID && (large(el) || column(el, color))) {
          pageColors.add(color);
          mark(el, CANVAS);
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

// Navigation bars: fixed or stuck along an edge of the window, a header or
// a bottom bar (most of its width, short, touching the top or the bottom)
// or a sidebar (most of its height, narrow, touching the left or the
// right), that paints a background of its own, or a see-through one with
// content of the page under it (a header over the posters it was scrolled
// past: its text on theirs). Under points along the four edges, the
// first such element gets BAR: one look on every site. A bar laid in the
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
// marked before the header stuck).
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
  if (document.getElementById(VEIL))
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
// that is neither its own, one of its ancestors, a layer of the page's
// background (CANVAS) nor a wrapper the size of the window. Runs on scroll
// (layers) only while such a bar is still unmarked: at most
// GRID * OVER_LINES hit tests per bar.
const OVER_LINES = 3;

function over(bar, w, h) {
  const r = bar.getBoundingClientRect();
  for (let j = 0; j < OVER_LINES; j++) {
    const y = Math.min(Math.max(r.top + (j + 0.5) * r.height / OVER_LINES, 0), h - 1);
    for (let i = 0; i < GRID; i++) {
      for (const el of document.elementsFromPoint(r.left + (i + 0.5) * r.width / GRID, y)) {
        if (el === document.documentElement || el === document.body || el.hasAttribute(CANVAS))
          break;
        if (bar.contains(el) || el.contains(bar))
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
    const page = el.parentElement && el.parentElement.closest("[" + CANVAS + "]");
    return !!page && r.width >= 0.9 * page.getBoundingClientRect().width;
  };
  const along = (el) => {
    const r = el.getBoundingClientRect();
    return Math.min(r.width, r.height) >= BAR_MIN
      && ((across(el, r) && r.height <= 0.35 * h && (r.top <= EDGE || r.bottom >= h - EDGE))
        || (r.height >= 0.6 * h && r.width <= 0.4 * w && (r.left <= EDGE || r.right >= w - EDGE)));
  };
  const backed = (el) => {
    if (alpha(getComputedStyle(el).backgroundColor) >= OWN_BG)
      return true;
    const r = el.getBoundingClientRect();
    for (const kid of el.children) {
      const k = kid.getBoundingClientRect();
      // a scrim faded out (opacity 0, a drawer's) paints nothing
      if (k.width * k.height >= FILL_COVER * r.width * r.height
          && (kid.getAttribute(CANVAS) === FILL || alpha(getComputedStyle(kid).backgroundColor) >= OWN_BG)
          && kid.checkVisibility({visibilityProperty: true, opacityProperty: true}))
        return true;
    }
    return false;
  };
  const pinned = (el) => {
    const position = getComputedStyle(el).position;
    return position === "fixed" || position === "sticky";
  };
  // a marked bar shows the veil, not its own background: only its place
  // is checked again
  for (const el of document.querySelectorAll("[" + BAR + "]"))
    if (!pinned(el) || !along(el))
      el.removeAttribute(BAR);
  for (let i = 0; i < GRID; i++) {
    const x = (i + 0.5) * w / GRID, y = (i + 0.5) * h / GRID;
    for (const [px, py] of [[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y]]) {
      for (const el of document.elementsFromPoint(px, py)) {
        if (el === root || el === document.body)
          break;
        if (!along(el) || !pinned(el))
          continue;
        if (!el.hasAttribute(BAR) && (backed(el) || over(el, w, h)))
          mark(el, BAR);
        break;
      }
    }
  }
  // one veil per bar: an inner one marked before its outer one was in place
  for (const el of document.querySelectorAll("[" + BAR + "] [" + BAR + "]"))
    el.removeAttribute(BAR);
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
// button or a field (FIELDS) keeps a veil of its own. The
// marks stay while Dark Reader darkens the page (a block marked reads as
// see-through: nothing to measure again) and go with it. The text is
// that of markInk (shownText).
const VEILED = "veil";
const SEE_THROUGH = "glass";
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
        || (style.position === "absolute" && style.zIndex !== "auto") || floats(el.parentElement));
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
  for (const el of shownText(near)) {
    const blocks = [];
    for (let p = el; p && p !== document.body; p = p.parentElement) {
      const value = kind(p);
      if (value === false)
        break;
      if (value)
        blocks.push(p);
    }
    blocks.forEach((b, j) => {
      // a button keeps a veil of its own, on its card's
      const value = j === blocks.length - 1 || b.matches(FIELDS) ? VEILED : SEE_THROUGH;
      if (b.getAttribute(BLOCK) !== value)
        b.setAttribute(BLOCK, value);
    });
  }
}

// Text without contrast: with the backgrounds of the page gone (the generic
// style, a site style, Dark Reader), some text is left on a colour close to
// its own, dark text on the dark glass (a notice banner) or light text on
// a light button. The text shown in the window (and a window above and
// below) is checked: the colour behind it is that of the first ancestor
// painting a background of its own, else the root's over the glass
// (GLASS, the tint's colour, set by the glass styles), unknown over a
// picture. Text whose contrast with it is below INK_RATIO gets INK, "dark"
// or "light": the glass styles give it a readable colour. Its marks are
// taken off before it is checked again, so a page that changes its colours
// (a theme switch) gets them right. At most once per INK_MS.
// Fills in the page's colour inside what stays on screen (a fixed or
// sticky element under the points of markCanvas and markBars): an empty
// element (a scrim that fades the content into the page's colour, often
// with a gradient mask, and that clicks pass through), or the panel that
// covers a bar and paints its background in its place (a sidebar drawn by
// its child). They show the page's colour, now glass: they get CANVAS too
// (FILL), or they stay as dark or light bands over the glass. They lose it
// with the page's layers (markCanvas), not when they shrink. The same for
// an empty ::before or ::after of such an element painting the page's
// colour (a strip under a sticky header's rounded corners, hiding the
// posts scrolled past): FILLED, the pseudo-elements by name.
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
  if (!pageColors.size || !document.querySelector("[" + CANVAS + "]:not([" + CANVAS + "=\"" + FILL + "\"])"))
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
    for (const el of document.elementsFromPoint(x, y)) {
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
    const box = holder.getBoundingClientRect();
    const bar = holder.hasAttribute(BAR);
    const kids = holder.querySelectorAll("*");
    for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
      const el = kids[i];
      if (el.hasAttribute(CANVAS) || NOT_FILLS.has(el.localName)
          || !pageColors.has(getComputedStyle(el).backgroundColor))
        continue;
      const r = el.getBoundingClientRect();
      if (!el.firstElementChild && !el.textContent.trim() ? r.width > 0 && r.height > 0
          : bar && r.width * r.height >= FILL_COVER * box.width * box.height)
        el.setAttribute(CANVAS, FILL);
    }
  }
}

const INK_RATIO = 2;
const INK_MS = 300;
const INK_NODES = 4000;
const INK_ELEMENTS = 1000;
let inkAt = -Infinity, inkFrame = 0;

// The elements holding text shown near the window, in the page's order:
// at most INK_NODES text nodes with text and INK_ELEMENTS elements near
// the window. The blank nodes between tags, and the text hidden (a closed
// menu of a thousand links) or far away, are skipped without counting
// against the elements: a page that holds them before its content (a
// right-hand column, late in the page's order) still gets it read.
function shownText(near) {
  const shown = [], looked = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let i = 0, n = walker.nextNode(); n && i < INK_NODES && shown.length < INK_ELEMENTS;
       n = walker.nextNode()) {
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
          || parseFloat(s.width) * parseFloat(s.height) < FACE * r.width * r.height)
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

function behind(el) {
  const root = document.documentElement;
  // a background clipped to the text is the text's colour, not behind it
  if (clipped(getComputedStyle(el)))
    el = el.parentElement || root;
  for (let p = el; p && p !== root; p = p.parentElement) {
    const style = getComputedStyle(p);
    const own = face(p);
    if (own !== undefined)
      return own;
    if (picture(style))
      return null;
    if (alpha(style.backgroundColor) >= OWN_BG)
      return luminance(style.backgroundColor);
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

function markInk() {
  const root = document.documentElement;
  if (!root || !document.body)
    return;
  if (off !== false) {
    for (const el of document.querySelectorAll("[" + INK + "], [" + TILE + "], [" + UNINVERT + "]"))
      el.removeAttribute(INK), el.removeAttribute(TILE), el.removeAttribute(UNINVERT);
    for (const el of document.querySelectorAll("[" + GLYPH + "], [" + RULE + "]"))
      el.removeAttribute(GLYPH), el.removeAttribute(RULE);
    for (const el of document.querySelectorAll("[" + BLOCK + "]"))
      el.removeAttribute(BLOCK);
    return;
  }
  const h = window.innerHeight;
  const near = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > -h && r.top < 2 * h;
  };
  // the blocks first: the text on them is then read on the glass
  markBlocks(near);
  // a mark taken off would fade the text back to its colour when the page
  // gives it a transition (the colour read halfway, the mark set and taken
  // off in turn): it is taken off with transitions held, its style
  // attribute put back once the marks are set
  const held = [];
  for (const el of document.querySelectorAll("[" + INK + "]"))
    if (near(el)) {
      held.push([el, el.getAttribute("style")]);
      el.style.setProperty("transition", "none", "important");
      el.removeAttribute(INK);
    }
  faces = new Map();
  for (const el of shownText(near)) {
    const fgs = inks(getComputedStyle(el)).map(luminance).filter((y) => y !== null);
    if (!fgs.length)
      continue;
    const bg = behind(el);
    if (bg !== null && fgs.every((fg) => contrast(fg, bg) < INK_RATIO))
      el.setAttribute(INK, bg > 0.179 ? "dark" : "light");
  }
  if (held.length)
    getComputedStyle(held[0][0]).color;
  for (const [el, style] of held)
    style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  markTiles(near);
  markUninverted(near);
  markGlyphs(near);
  markRules(near);
}

// Pictures made for a white page, on a background now dark, are shown on
// a white tile (TILE), as shops show product photos in a dark theme: a
// white background and a white margin TILE_PAD wide drawn by a shadow
// (the layout stays), round corners, no blending, no filter. Two kinds,
// checked as the text is, at most TILE_ELEMENTS pictures near the window:
// - a picture blended with multiply (or darken) into its background: a
//   site wipes out the white of a product photo or a logo that way, and on
//   a dark background the picture turns dark or black on black;
// - on a page Dark Reader darkens, an <img> with see-through parts whose
//   ink (its opaque pixels) reads under INK_RATIO against the background
//   for at least TILE_INK of it: a black logo or line drawing. Its pixels
//   are read on a small canvas (sample), which only a picture of the
//   page's origin (or a data: URL) allows: one from another origin stays
//   as it is. Flat grey ink (MONO_SHARE of its pixels at most with
//   MONO_CHROMA of chroma, its quantiles MONO_EDGE steps in from each end
//   under MONO_FLAT apart: a black word mark) is inverted instead
//   ("invert": light ink, no tile), which keeps a logo whole beside its
//   coloured parts; coloured ink, and shaded ink (a black product cut out
//   of its photo), keeps the tile, which keeps its colours and shading.
// Neither a picture under TILE_MIN px both ways (an icon) nor one nearly
// as wide as the window (a full-bleed photo) is tiled.
const TILE_ELEMENTS = 500;
const TILE_MIN = 24;
const TILE_WIDE = 0.9;
const TILE_INK = 0.4;
const TILE_CLEAR = 0.1;
const DARK_BG = 0.179;
const DARKENING = new Set(["multiply", "darken"]);
const MONO_CHROMA = 0.1;
const MONO_SHARE = 0.05;
const MONO_EDGE = 2;
const MONO_FLAT = 1.5;

function markTiles(near) {
  const pictures = document.body.querySelectorAll("img, svg, canvas");
  for (let i = 0; i < pictures.length && i < TILE_ELEMENTS; i++) {
    const el = pictures[i];
    if (!near(el))
      continue;
    const kind = tile(el);
    if (kind === null)
      el.removeAttribute(TILE);
    else if (el.getAttribute(TILE) !== kind)
      el.setAttribute(TILE, kind);
  }
}

// How a picture is tiled: "blend" (multiplied), "ink" (dark ink),
// "invert" (dark monochrome ink) or null.
// A tile changes the picture's own background and blending: what is behind
// it is read from its parent, and a picture tiled for its blending stays
// so (its blending is the tile's now). Never taken off and set again in
// turn: a site's transition would read the tile's white halfway. Pixels
// are read before what is behind (most pictures are opaque photos).
function tile(el) {
  const r = el.getBoundingClientRect();
  if (r.width < TILE_MIN && r.height < TILE_MIN || r.width >= TILE_WIDE * window.innerWidth)
    return null;
  const blended = el.getAttribute(TILE) === "blend" || DARKENING.has(getComputedStyle(el).mixBlendMode);
  const s = blended || !darkened || el.localName !== "img" ? null : sample(el);
  if (!blended && !(s && s.clear >= TILE_CLEAR))
    return null;
  const bg = behind(el.parentElement || document.documentElement);
  if (bg === null || bg > DARK_BG)
    return null;
  if (blended)
    return "blend";
  const unread = s.inks.filter((y) => contrast(y, bg) < INK_RATIO).length;
  if (unread < TILE_INK * s.inks.length)
    return null;
  const flat = contrast(s.inks[INK_STEPS - 1 - MONO_EDGE], s.inks[MONO_EDGE]) < MONO_FLAT;
  return flat && s.colored <= MONO_SHARE ? "invert" : "ink";
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
  for (const el of document.querySelectorAll("[" + UNINVERT + "]"))
    if (!darkened || !el.hasAttribute(DR_INVERT))
      el.removeAttribute(UNINVERT);
  if (!darkened)
    return;
  for (const svg of document.body.querySelectorAll("svg[" + DR_INVERT + "]"))
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
  const empty = document.body.querySelectorAll(":empty");
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
    for (const el of document.querySelectorAll("[" + RULE + "]"))
      el.removeAttribute(RULE);
    return;
  }
  const empty = document.body.querySelectorAll(":empty:not([" + RULE + "]):not([" + GLYPH + "])");
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

// A picture's pixels, read once per source on a canvas SAMPLE_SIDE px at
// most: {clear: the share of see-through pixels (alpha under CLEAR),
// inks: the luminance of the others at INK_STEPS quantiles, colored: the
// share of them with MONO_CHROMA of chroma at least}. null when
// they cannot be read (a picture of another origin, an empty one); a
// picture still loading is read once loaded (a new pass, see loaded).
const SAMPLE_SIDE = 96;
const INK_STEPS = 20;
const SAMPLES_MAX = 1000;
const samples = new Map();

function sample(img) {
  const src = img.currentSrc;
  if (!src)
    return null;
  if (samples.has(src))
    return samples.get(src);
  if (!img.complete)
    return null;
  if (samples.size >= SAMPLES_MAX)
    samples.clear();
  samples.set(src, pixels(img));
  return samples.get(src);
}

function pixels(img) {
  const r = img.getBoundingClientRect();
  const k = Math.min(1, SAMPLE_SIDE / Math.max(r.width, r.height));
  const w = Math.max(1, Math.round(r.width * k)), h = Math.max(1, Math.round(r.height * k));
  let data;
  try {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext("2d", {willReadFrequently: true});
    g.drawImage(img, 0, 0, w, h);
    data = g.getImageData(0, 0, w, h).data;
  } catch (e) {
    return null;  // another origin (SecurityError), or not decodable
  }
  const ys = [];
  let colored = 0;
  for (let i = 0; i < data.length; i += 4)
    if (data[i + 3] >= CLEAR * 255) {
      ys.push(rgbLuminance(linear(data[i] / 255), linear(data[i + 1] / 255), linear(data[i + 2] / 255)));
      const spread = Math.max(data[i], data[i + 1], data[i + 2]) - Math.min(data[i], data[i + 1], data[i + 2]);
      if (spread >= MONO_CHROMA * 255)
        colored++;
    }
  if (!ys.length)
    return null;
  ys.sort((a, b) => a - b);
  const inks = [];
  for (let q = 0; q < INK_STEPS; q++)
    inks.push(ys[Math.floor((q + 0.5) * ys.length / INK_STEPS)]);
  return {clear: 1 - ys.length / (w * h), inks, colored: colored / ys.length};
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
// another tone.
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
  layerSizes.observe(document.documentElement);
  layerSizes.observe(document.body);
  for (const el of document.body.children)
    layerSizes.observe(el);
  for (const el of document.querySelectorAll("[" + CANVAS + "], [" + BAR + "]"))
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
    }
    markCanvas();
    markBars();
    markFills();
    ink();
  }
  if (settleStep < SETTLE_MS.length)
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

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
// see-through. A navigation bar fixed or stuck along an edge of the window
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
// picture multiplied into a background now dark (a black logo whose white
// a site wipes out with mix-blend-mode) gets data-browserglass-blend.
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
const BLEND = "data-browserglass-blend";
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

// The tone from the colour of the text shown, the site styles included:
// the visible text of the body votes, each node by its length (capped, so
// one long paragraph does not outweigh the page); the text outside the
// site's menus and the mid-grey band decides first (siteChrome, MID_LOW).
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
  // the mid-grey band, and the same outside the site's menus
  const all = [0, 0], firm = [0, 0], main = [0, 0], mainFirm = [0, 0];
  if (document.body) {
    const parents = new Map();
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
          if (p.checkVisibility({visibilityProperty: true, opacityProperty: true}))
            y = luminance(getComputedStyle(p).color);
          parents.set(p, y);
        }
        const y = parents.get(p);
        if (y === null)
          continue;
        const side = y > 0.179 ? 0 : 1;
        const isFirm = y <= MID_LOW || y >= MID_HIGH;
        all[side] += len;
        if (isFirm)
          firm[side] += len;
        if (menus) {
          main[side] += len;
          if (isFirm)
            mainFirm[side] += len;
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
  const votes = [mainFirm, main, firm, all].find((t) => t[0] + t[1] > 0) || all;
  const [light, dark] = votes;
  sampled = all[0] + all[1];
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
    for (const el of document.querySelectorAll("[" + CANVAS + "]"))
      el.removeAttribute(CANVAS);
    measure();
  } else if (!darkened && theme && tone === "light" && !themeWait
      && (sampled >= ENOUGH_TEXT || document.readyState === "complete")) {
    if (!nativeTried) {
      nativeTried = true;
      if (nativeDark())
        return;
    }
    darkened = true;
    DarkReader.setFetchMethod(fetchStylesheet);
    DarkReader.enable(theme);
    frameSchemes();
    measure();
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
// (the generic style), the lowest layer under a grid of points that paints
// an opaque background colour (not a dialog's dimming) and covers most of
// the window (often a fixed full-window container) gets CANVAS, unless it
// is fixed, or inside a fixed element, over other content of the page (a
// dialog, a cookie banner): the glass styles make that colour transparent;
// the cards and panels drawn over it keep theirs. On a darkened page every
// such large layer does, except fixed ones (dialogs). A layer loses CANVAS
// once smaller, and all do once the root or the body paints a background
// again. The colour of the last layer marked is the page's colour
// (pageColor, for markFills).
const GRID = 5;
const CLEAR = 0.5;
const SOLID = 0.99;
const FILL = "fill";
let pageColor = null;

// A marked element is watched: its size changes (or its removal, a view
// swapped) look again.
function mark(el, attr) {
  el.setAttribute(attr, "");
  layerSizes.observe(el);
}

function markCanvas() {
  const root = document.documentElement;
  if (off !== false || !root || !document.body)
    return;
  const w = root.clientWidth, h = window.innerHeight;
  const large = (el) => {
    const r = el.getBoundingClientRect();
    return r.width >= 0.9 * w && r.height >= 0.6 * h;
  };
  const clear = (el) => alpha(getComputedStyle(el).backgroundColor) < CLEAR;
  const pinned = (el) => {
    for (let e = el; e && e !== root; e = e.parentElement)
      if (getComputedStyle(e).position === "fixed")
        return true;
    return false;
  };
  const glass = clear(root) && clear(document.body);
  for (const el of document.querySelectorAll("[" + CANVAS + "]"))
    if (!glass || (!large(el) && el.getAttribute(CANVAS) !== FILL))
      el.removeAttribute(CANVAS);
  if (!glass)
    return;
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
        if (large(el) && alpha(color) >= SOLID) {
          pageColor = color;
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
// shape the site draws itself, as a navigation bar.
const EDGE = 2;
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

// Whether page content lies under a see-through bar: along its middle
// line, an element below it that is neither its own, one of its
// ancestors, a layer of the page's background (CANVAS) nor a wrapper the
// size of the window. Runs on scroll (layers) only while such a bar is
// still unmarked: at most GRID hit tests per bar.
function over(bar, w, h) {
  const r = bar.getBoundingClientRect();
  const y = r.top + r.height / 2;
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
  return false;
}

function markBars() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  veil(root);
  const w = root.clientWidth, h = window.innerHeight;
  const along = (el) => {
    const r = el.getBoundingClientRect();
    return (r.width >= 0.6 * w && r.height <= 0.35 * h && (r.top <= EDGE || r.bottom >= h - EDGE))
      || (r.height >= 0.6 * h && r.width <= 0.4 * w && (r.left <= EDGE || r.right >= w - EDGE));
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
        if (!el.hasAttribute(BAR)
            && (alpha(getComputedStyle(el).backgroundColor) >= OWN_BG || over(el, w, h)))
          mark(el, BAR);
        break;
      }
    }
  }
  // one veil per bar: an inner one marked before its outer one was in place
  for (const el of document.querySelectorAll("[" + BAR + "] [" + BAR + "]"))
    el.removeAttribute(BAR);
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
// with the page's layers (markCanvas), not when they shrink.
const FILL_NODES = 400;
const FILL_COVER = 0.9;
const NOT_FILLS = new Set(["img", "video", "canvas", "svg", "iframe", "embed", "object", "picture",
  "input", "textarea", "select", "button", "hr"]);

function markFills() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  if (pageColor === null || !document.querySelector("[" + CANVAS + "]:not([" + CANVAS + "=\"" + FILL + "\"])"))
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
    const box = holder.getBoundingClientRect();
    const bar = holder.hasAttribute(BAR);
    const kids = holder.querySelectorAll("*");
    for (let i = 0; i < kids.length && i < FILL_NODES; i++) {
      const el = kids[i];
      if (el.hasAttribute(CANVAS) || NOT_FILLS.has(el.localName)
          || getComputedStyle(el).backgroundColor !== pageColor)
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
    if (!/^(repeating-)?(linear|radial|conic)-gradient\(/.test(image))
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

function behind(el) {
  const root = document.documentElement;
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
    for (const el of document.querySelectorAll("[" + INK + "], [" + BLEND + "]"))
      el.removeAttribute(INK), el.removeAttribute(BLEND);
    return;
  }
  const h = window.innerHeight;
  const near = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > -h && r.top < 2 * h;
  };
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
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let i = 0, n = walker.nextNode(); n && i < INK_NODES && seen.size < INK_ELEMENTS;
       i++, n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || seen.has(el) || !n.data.trim())
      continue;
    seen.add(el);
    if (!near(el) || !el.checkVisibility({visibilityProperty: true, opacityProperty: true}))
      continue;
    const color = getComputedStyle(el).color;
    const fg = luminance(color);
    if (fg === null || alpha(color) < CLEAR)
      continue;
    const bg = behind(el);
    if (bg !== null && contrast(fg, bg) < INK_RATIO)
      el.setAttribute(INK, bg > 0.179 ? "dark" : "light");
  }
  if (held.length)
    getComputedStyle(held[0][0]).color;
  for (const [el, style] of held)
    style === null ? el.removeAttribute("style") : el.setAttribute("style", style);
  markBlend(near);
}

// A picture blended with multiply (or darken) into its background: a site
// shows a black logo on a white card that way, its white wiped out. On a
// background now dark it turns black on black. Over a dark background
// (DARK_BG at most), it gets BLEND: inverted and blended with screen, the
// same logo, light, its black wiped out. Checked as the text is, at most
// BLEND_ELEMENTS pictures, near the window.
const BLEND_ELEMENTS = 500;
const DARK_BG = 0.179;
const DARKENING = new Set(["multiply", "darken"]);

function markBlend(near) {
  for (const el of document.querySelectorAll("[" + BLEND + "]"))
    if (near(el))
      el.removeAttribute(BLEND);
  const pictures = document.body.querySelectorAll("img, svg, canvas");
  for (let i = 0; i < pictures.length && i < BLEND_ELEMENTS; i++) {
    const el = pictures[i];
    if (!DARKENING.has(getComputedStyle(el).mixBlendMode) || !near(el))
      continue;
    const bg = behind(el);
    if (bg !== null && bg <= DARK_BG)
      el.setAttribute(BLEND, "");
  }
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

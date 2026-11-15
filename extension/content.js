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
// (a header, a bottom bar, a sidebar), or laid along one in a page that does
// not scroll (a web app's shell), gets data-browserglass-bar: the same
// near-opaque blurred surface on every site.
"use strict";

const LIVE = "data-browserglass-live";
const OFF = "data-browserglass-off";
const TONE = "data-browserglass-tone";
const OWN = "data-browserglass-";
const CANVAS = "data-browserglass-canvas";
const BAR = "data-browserglass-bar";
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

// The text nodes read per measure, at most.
const SAMPLE_NODES = 400;
// Characters of visible text that settle the tone; until then (a
// single-page app still rendering), each resize of the body measures again,
// at most RESIZE_MEASURES times.
const ENOUGH_TEXT = 200;
const RESIZE_MEASURES = 20;
let sampled = 0;
let resizeMeasures = 0;

// The tone from the colour of the text shown, the site styles included:
// the visible text of the body votes, each node by its length (capped, so
// one long paragraph does not outweigh the page). Many pages leave the
// body's own colour at the default black and colour their text through
// classes (YouTube's dark theme): the body alone would read as light. A
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
  let light = 0, dark = 0;
  if (document.body) {
    const parents = new Map();
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let i = 0, n = walker.nextNode(); n && i < SAMPLE_NODES; i++, n = walker.nextNode()) {
      const p = n.parentElement;
      const len = Math.min(n.data.trim().length, 80);
      if (!len || !p)
        continue;
      if (!parents.has(p))
        parents.set(p, p.checkVisibility({visibilityProperty: true, opacityProperty: true})
          ? isLight(getComputedStyle(p).color) : null);
      const v = parents.get(p);
      if (v === true)
        dark += len;
      else if (v === false)
        light += len;
    }
  }
  sampled = light + dark;
  const v = sampled ? dark > light : isLight(getComputedStyle(el).color);
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
  return bg && fg ? {darkSchemeBackgroundColor: bg, darkSchemeTextColor: fg} : null;
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
    for (const el of document.querySelectorAll("[" + CANVAS + "]"))
      el.removeAttribute(CANVAS);
    measure();
  } else if (!darkened && theme && tone === "light"
      && (sampled >= ENOUGH_TEXT || document.readyState === "complete")) {
    if (!nativeTried) {
      nativeTried = true;
      if (nativeDark())
        return;
    }
    darkened = true;
    DarkReader.setFetchMethod(fetchStylesheet);
    DarkReader.enable(theme);
    measure();
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
// the window (often a fixed
// full-window container) gets CANVAS: the glass styles make that colour
// transparent; the cards and panels drawn over it keep theirs. On a
// darkened page every such large layer does, except fixed ones (dialogs).
// A layer loses CANVAS once smaller, and all do once the root or the body
// paints a background again.
const GRID = 5;
const CLEAR = 0.5;
const SOLID = 0.99;

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
  const glass = clear(root) && clear(document.body);
  for (const el of document.querySelectorAll("[" + CANVAS + "]"))
    if (!glass || !large(el))
      el.removeAttribute(CANVAS);
  if (!glass)
    return;
  const seen = new Set([root, document.body]);
  for (let i = 0; i < GRID; i++) {
    for (let j = 0; j < GRID; j++) {
      const stack = document.elementsFromPoint((i + 0.5) * w / GRID, (j + 0.5) * h / GRID);
      for (let n = stack.length - 1; n >= 0; n--) {
        const el = stack[n];
        if (el === root || el === document.body)
          continue;
        if (el.hasAttribute(CANVAS))
          break;
        if (clear(el))
          continue;
        if (large(el) && alpha(getComputedStyle(el).backgroundColor) >= SOLID)
          mark(el, CANVAS);
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

// Navigation bars: along an edge of the window, a header or a bottom bar
// (most of its width, short, touching the top or the bottom) or a sidebar
// (most of its height, narrow, touching the left or the right), either fixed
// or sticky, or in the flow of a page that does not scroll: a web app's
// shell (a mail client, a chat) keeps its sidebar and header in place and
// scrolls a pane inside. One in the flow is taken only when it is navigation
// (a nav, header, aside or footer, a navigation role, or links or buttons
// inside), shows no picture (the bar's background replaces it), lies inside
// the window and is not in a pane that scrolls (a row of a list). A body
// fixed to lock the scroll (a dialog open) is not a shell. Under points
// along the four edges, the first fixed or sticky one gets BAR, else the
// outermost one in the flow (the whole sidebar, not a list inside it),
// whatever its own background: one look on every site.
const EDGE = 2;
const NAV_LIKE = "nav, header, aside, footer, [role=navigation], [role=banner], [role=complementary]";
const NAV_ITEMS = "a[href], button, [role=button], [role=link]";

// An ancestor below <body> that scrolls its content.
function inPane(el) {
  for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
    const style = getComputedStyle(p);
    if ((/auto|scroll/.test(style.overflowY) && p.scrollHeight > p.clientHeight)
        || (/auto|scroll/.test(style.overflowX) && p.scrollWidth > p.clientWidth))
      return true;
  }
  return false;
}

function markBars() {
  const root = document.documentElement;
  if (!root || off !== false || !document.body)
    return;
  const w = root.clientWidth, h = window.innerHeight;
  const scroller = document.scrollingElement || root;
  const shell = scroller.scrollHeight <= scroller.clientHeight + 1
    && getComputedStyle(document.body).position !== "fixed";
  const along = (el) => {
    const r = el.getBoundingClientRect();
    return (r.width >= 0.6 * w && r.height <= 0.35 * h && (r.top <= EDGE || r.bottom >= h - EDGE))
      || (r.height >= 0.6 * h && r.width <= 0.4 * w && (r.left <= EDGE || r.right >= w - EDGE));
  };
  const pinned = (el) => {
    const position = getComputedStyle(el).position;
    return position === "fixed" || position === "sticky";
  };
  const inFlow = (el) => {
    const style = getComputedStyle(el);
    if (style.position !== "static" && style.position !== "relative")
      return false;
    const r = el.getBoundingClientRect();
    return r.top >= -EDGE && r.bottom <= h + EDGE && r.left >= -EDGE && r.right <= w + EDGE
      && (el.matches(NAV_LIKE) || el.querySelector(NAV_ITEMS) !== null)
      && style.backgroundImage === "none"
      && !inPane(el);
  };
  const bar = (el) => (pinned(el) || (shell && inFlow(el))) && along(el);
  for (const el of document.querySelectorAll("[" + BAR + "]"))
    if (!bar(el))
      el.removeAttribute(BAR);
  for (let i = 0; i < GRID; i++) {
    const x = (i + 0.5) * w / GRID, y = (i + 0.5) * h / GRID;
    for (const [px, py] of [[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y]]) {
      let found = null;
      for (const el of document.elementsFromPoint(px, py)) {
        if (el === root || el === document.body)
          break;
        if (!along(el))
          continue;
        if (pinned(el)) {
          found = el;
          break;
        }
        if (shell && inFlow(el))
          found = el;
      }
      if (found && !found.hasAttribute(BAR))
        mark(found, BAR);
    }
  }
  // one veil per bar: an inner one marked before its outer one was in place
  for (const el of document.querySelectorAll("[" + BAR + "] [" + BAR + "]"))
    el.removeAttribute(BAR);
}

// The layers are looked for again, once per frame at most: when the page
// scrolls (a header sticks, or turns fixed), is resized, has loaded, ends a
// transition (a bar fading in), when the size of the document, the body,
// one of its children or a marked element changes, and when the body gets
// or loses a child. A single-page app swaps its view once its data is in:
// after a click, a form sent or a navigation, a few more passes, the last
// SETTLE_MS[SETTLE_MS.length - 1] ms later (animation frames, no timer).
let layerFrame = 0;

function layers() {
  if (!layerFrame)
    layerFrame = requestAnimationFrame(() => {
      layerFrame = 0;
      markCanvas();
      markBars();
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
    markCanvas();
    markBars();
  }
  if (settleStep < SETTLE_MS.length)
    settleFrame = requestAnimationFrame(settleTick);
}

function apply(domains, dark) {
  helperDark = dark === true;
  off = Array.isArray(domains) && hostExcluded(location.hostname.toLowerCase().replace(/\.$/, ""), domains);
  darken();
  paint();
  watchLayers();
  markCanvas();
  markBars();
}

// Storage has no list until the helper sent its first one (a fresh
// install): off then stays null, so LIVE waits for that first list instead
// of turning on the live styles of a site excluded at sync. darken is
// stored with it (no darken stored: an older add-on's list, false).
function load() {
  browser.storage.local.get(["excluded", "darken"]).then((s) => {
    if (!fromMessage && Array.isArray(s.excluded))
      apply(s.excluded, s.darken);
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
    apply(msg.domains, msg.darken);
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
window.addEventListener("load", update);
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", update);
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
for (const type of ["popstate", "hashchange"])
  window.addEventListener(type, settle, {passive: true});

if (document.documentElement && document.documentElement.hasAttribute(OFF))
  off = true;
update();
load();

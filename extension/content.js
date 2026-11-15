// Browser Glass companion, in every web page. The glass styles skip a page
// whose <html> carries data-browserglass-off, and apply the styles of a
// domain excluded when the browser started (and since put back) only while
// <html> carries data-browserglass-live: this script sets both, together,
// as soon as the exclusion list is known and whenever it changes. It also
// sets data-browserglass-tone to the tone of the page ("light": dark text,
// "dark": light text), measured here and never sent anywhere: the glass
// styles then treat the page as one with a dark version, and tint a light
// page under a dark theme (and a dark one under a light theme).
"use strict";

const LIVE = "data-browserglass-live";
const OFF = "data-browserglass-off";
const TONE = "data-browserglass-tone";
const OWN = "data-browserglass-";

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
// null until measured (once the document is parsed).
let tone = null;

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

// The tone from the colour of the page's text (the body's, the root's
// before there is a body), as shown, the site styles included: a text
// lighter than 0.179 in relative luminance (as far from white as from
// black in contrast) is on a dark page. An unknown colour keeps the last
// tone.
function measure() {
  if (document.readyState === "loading")
    return;
  const el = document.body || document.documentElement;
  if (!el)
    return;
  const y = luminance(getComputedStyle(el).color);
  if (y !== null)
    tone = y > 0.179 ? "dark" : "light";
}

function update() {
  measure();
  paint();
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

function apply(domains) {
  off = Array.isArray(domains) && hostExcluded(location.hostname.toLowerCase(), domains);
  paint();
}

// Storage has no list until the helper sent its first one (a fresh
// install): off then stays null, so LIVE waits for that first list instead
// of turning on the live styles of a site excluded at sync.
function load() {
  browser.storage.local.get("excluded").then((s) => {
    if (!fromMessage && Array.isArray(s.excluded))
      apply(s.excluded);
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
      || (r.attributeName !== "style" && !r.attributeName.startsWith(OWN))))
    measure();
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
    apply(msg.domains);
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

if (document.documentElement && document.documentElement.hasAttribute(OFF))
  off = true;
update();
load();

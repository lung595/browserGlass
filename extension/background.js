// Browser Glass companion: the link between the browser and the local
// Browser Glass helper (native messaging host "browserglass", run from the
// DMS plugin). Protocol version PROTO; only these messages cross it:
//   helper -> browser  {type: "hello", proto}
//                      {type: "excluded", seq, domains: [host], darken, themes}
//                       the excluded sites, and whether light pages are
//                       darkened (the darkPages setting; anything but true,
//                       or no darken at all, is false). darken is the only
//                       switch of the darkening: content.js takes just the
//                       colours from the style file, whose variables a page
//                       could set itself. themes: the site theme recipes
//                       (data/themes.json, see theme.js), {} without.
//   browser -> helper  {type: "hello", proto, version}          on connect
//                      {type: "active", host, title_hash}         the site in the
//                       focused window (host only, "" for a non-web page) and
//                       the first 16 hex digits of the SHA-256 of its title
//                       (tab.title as is: the window title niri shows ends
//                       with a dash and the browser's localized name, e.g.
//                       "Mozilla Firefox", which the helper must strip
//                       before it hashes that title)
//                      {type: "applied", seq}                     a list is in place
"use strict";

const HOST_APP = "browserglass";
const PROTO = 1;
const OFF = "data-browserglass-off";
const RETRY_MIN_MS = 2000;
const RETRY_MAX_MS = 60000;
// How long a list waits for each open tab before "applied" goes out (the
// helper waits LIVE_ACK_TIMEOUT, 1 s, for it)
const TAB_WAIT_MS = 200;
// The helper only sends plain host names (normalize_domain in
// browserglass.py); anything else is dropped here too, so that a bad entry
// can never reach contentScripts.register.
const PLAIN_HOST = /^[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})*$/;

let excluded = [];
let darken = false;
let themes = {};
// Whether storage holds a list: the first list from the helper is written
// even when it is empty, so that content.js, which waits for a stored list,
// finds one.
let stored = false;
// Whether storage holds `excluded` and `darken` as they are here. A failed
// write leaves the previous ones there (or none) while this side already
// moved on: the next list then writes again even when it changes nothing,
// or new tabs would keep reading, say, an old darken: true.
let saved = false;
let registered = null;
let themeRegistered = null;
let themeKey = null;
let port = null;
let retryMs = RETRY_MIN_MS;
let lastSent = null;
let reportGen = 0;
let connectedAt = 0;

// A host may come with a final dot (example.org.), which `*://*.example.org/*`
// does not match: without the second pattern such a page paints glass first.
function patterns(domains) {
  return domains.flatMap((d) => /^[0-9.]+$/.test(d) ? ["*://" + d + "/*"]
    : ["*://*." + d + "/*", "*://*." + d + "./*"]);
}

function cleanList(domains) {
  if (!Array.isArray(domains))
    return [];
  const out = [];
  for (const d of domains) {
    const v = typeof d === "string" ? d.toLowerCase() : "";
    if (v.length <= 253 && PLAIN_HOST.test(v) && !out.includes(v))
      out.push(v);
  }
  return out;
}

// The themes as theme.js reads them: the same shape as the helper sends,
// every string short and plain; anything else is dropped.
const THEME_KEY = /^[A-Za-z0-9_.:-]{1,64}$/;
// a localStorage key may also hold "/"; a cookie name may not
const THEME_LOCAL_KEY = /^[A-Za-z0-9_./:-]{1,64}$/;
const THEME_BAD = /[;,\u0000-\u001f\u007f]/;
// a localStorage value may hold ";" and "," (JSON: '{"theme":"default"}')
const THEME_BAD_LOCAL = /[\u0000-\u001f\u007f]/;

function themeValue(v, store) {
  return typeof v === "string" && v.length <= 64
    && !(store === "local" ? THEME_BAD_LOCAL : THEME_BAD).test(v);
}

function cleanRecipe(r) {
  if (!r || typeof r !== "object" || (r.store !== "local" && r.store !== "cookie")
      || (r.op !== "set" && r.op !== "swap") || typeof r.key !== "string"
      || !(r.store === "local" ? THEME_LOCAL_KEY : THEME_KEY).test(r.key)
      || !themeValue(r.to, r.store) || !r.to || !Array.isArray(r.from) || !r.from.length
      || !r.from.every((f) => f === null || themeValue(f, r.store)))
    return null;
  const out = {store: r.store, key: r.key, op: r.op, from: r.from.slice(), to: r.to};
  if (r.store === "cookie") {
    out.path = themeValue(r.path) && r.path.startsWith("/") ? r.path : "/";
    if (typeof r.domain === "string" && PLAIN_HOST.test(r.domain.replace(/^\./, "")))
      out.domain = r.domain;
    if (r.reload === true)
      out.reload = true;
  }
  if (typeof r.skipIfCookie === "string" && THEME_KEY.test(r.skipIfCookie))
    out.skipIfCookie = r.skipIfCookie;
  return out;
}

function cleanThemes(t) {
  if (!t || typeof t !== "object" || Array.isArray(t))
    return {};
  const g = t.generic && typeof t.generic === "object" ? t.generic : {};
  const keys = Array.isArray(g.keys) ? g.keys.filter((k) => typeof k === "string" && THEME_KEY.test(k)) : [];
  const map = {};
  if (g.map && typeof g.map === "object")
    for (const [a, b] of Object.entries(g.map))
      if (themeValue(a) && themeValue(b) && a && b)
        map[a] = b;
  const sites = {};
  if (t.sites && typeof t.sites === "object")
    for (const [host, list] of Object.entries(t.sites)) {
      if (!PLAIN_HOST.test(host) || !Array.isArray(list))
        continue;
      const clean = list.map(cleanRecipe).filter(Boolean);
      if (clean.length)
        sites[host] = clean;
    }
  const rev = typeof t.rev === "string" && /^[0-9a-f]{1,64}$/.test(t.rev) ? t.rev : "";
  return {rev, generic: {keys, map}, sites};
}

// theme.js gets its data before the page's scripts run: a payload that
// defines BG_THEME and calls themeRun (theme.js, a manifest script, runs
// first in the same sandbox; its last line covers the other order).
async function replaceThemeRegistration() {
  if (themeRegistered) {
    const old = themeRegistered;
    themeRegistered = null;
    await old.unregister().catch(() => {});
  }
  const cfg = JSON.stringify({dark: darken, excluded, themes});
  themeRegistered = await browser.contentScripts.register({
    matches: ["http://*/*", "https://*/*"],
    js: [{code: "var BG_THEME = " + cfg + ";typeof themeRun === 'function' && themeRun(BG_THEME, true);"}],
    runAt: "document_start",
  }).catch(() => null);
}

// Excluded pages get OFF before their first paint: content.js only learns
// the list asynchronously.
async function replaceRegistration(domains) {
  if (registered) {
    const old = registered;
    registered = null;
    await old.unregister().catch(() => {});
  }
  if (!domains.length)
    return;
  registered = await browser.contentScripts.register({
    matches: patterns(domains),
    js: [{code: "document.documentElement && document.documentElement.setAttribute('" + OFF + "', '');"}],
    runAt: "document_start",
  }).catch(() => null);
}

// Lists are applied one at a time, in arrival order: two lists arriving back
// to back would otherwise both register (the first registration would never
// be unregistered), or reach the pages in the wrong order. A failed step
// never blocks the lists after it.
let queue = Promise.resolve();

function enqueue(job) {
  queue = queue.then(job).catch(() => {});
  return queue;
}

// `from` is the port the list came on: "applied" is only sent back on it.
// Each connection runs a new helper whose seq starts over, so a list of a
// dropped connection must never confirm one of the next. darken is stored
// with the list (content.js reads both back), and a change of darken
// alone needs no new registration of OFF; the themes payload carries the
// list, darken and the themes, and is registered again when one changes.
async function applyList(domains, dark, theme, seq, from) {
  const same = domains.length === excluded.length && domains.every((d, i) => d === excluded[i]);
  const first = !stored;
  const changed = !same || dark !== darken || theme.rev !== themes.rev;
  excluded = domains;
  darken = dark;
  themes = theme;
  if (changed || !saved) {
    saved = await browser.storage.local.set({excluded: domains, darken: dark, themes: theme})
      .then(() => true, () => false);
    stored = stored || saved;
  }
  if (!same || first)
    await replaceRegistration(domains);
  const key = JSON.stringify([domains, dark, theme.rev]);
  if (key !== themeKey || !themeRegistered) {
    themeKey = key;
    await replaceThemeRegistration();
  }
  // Each tab gets TAB_WAIT_MS to answer: one busy tab must not hold the ack
  // past the helper's wait, which would report a live change as "applies
  // after a restart" (the message still reaches that tab later).
  const tabs = await browser.tabs.query({url: ["http://*/*", "https://*/*"]}).catch(() => []);
  await Promise.all(tabs.map((tab) => Promise.race([
    browser.tabs.sendMessage(tab.id, {type: "excluded", domains, darken: dark, themes: theme}).catch(() => {}),
    new Promise((resolve) => setTimeout(resolve, TAB_WAIT_MS)),
  ])));
  if (Number.isInteger(seq) && from === port)
    send({type: "applied", seq});
}

function hostOf(url) {
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.hostname.toLowerCase() : "";
  } catch (e) {
    return "";
  }
}

async function titleHash(title) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(title || ""));
  return Array.from(new Uint8Array(digest).slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
}

function send(msg) {
  if (port)
    try {
      port.postMessage(msg);
    } catch (e) {}
}

// The active tab of the focused window (of the last focused one while no
// window of this browser has the focus, e.g. while the DMS launcher is
// open). A private window is never reported: the manifest refuses private
// windows ("incognito": "not_allowed") and a private tab is dropped here
// too, so the helper side, which compares title_hash with the title niri
// shows, never trusts it. `gen` is taken before the tab query: only the
// newest report is sent.
async function reportTab(tab, gen) {
  if (gen !== reportGen || !tab || !port || tab.incognito)
    return;
  const host = hostOf(tab.url || "");
  const hash = await titleHash(tab.title).catch(() => "");
  if (gen !== reportGen)
    return;  // a newer report started meanwhile
  const key = host + "\n" + hash;
  if (key === lastSent)
    return;
  lastSent = key;
  send({type: "active", host, title_hash: hash});
}

async function reportFocused(windowId) {
  const query = windowId === undefined ? {active: true, lastFocusedWindow: true} : {active: true, windowId};
  const gen = ++reportGen;
  const tabs = await browser.tabs.query(query).catch(() => []);
  await reportTab(tabs[0], gen);
}

// The backoff starts again only after a connection that lasted: a helper
// that answers and then exits at once is not respawned every 2 s.
function retry() {
  port = null;
  if (Date.now() - connectedAt > RETRY_MAX_MS)
    retryMs = RETRY_MIN_MS;
  setTimeout(connect, retryMs);
  retryMs = Math.min(retryMs * 2, RETRY_MAX_MS);
}

function connect() {
  lastSent = null;
  connectedAt = Date.now();
  try {
    port = browser.runtime.connectNative(HOST_APP);
  } catch (e) {
    retry();
    return;
  }
  const self = port;
  port.onMessage.addListener((msg) => {
    if (msg && msg.type === "excluded")
      enqueue(() => applyList(cleanList(msg.domains), msg.darken === true, cleanThemes(msg.themes), msg.seq, self));
  });
  port.onDisconnect.addListener(() => {
    if (port === self)
      retry();
  });
  send({type: "hello", proto: PROTO, version: browser.runtime.getManifest().version});
  reportFocused();
}

browser.windows.onFocusChanged.addListener((windowId) => {
  if (windowId !== browser.windows.WINDOW_ID_NONE)
    reportFocused(windowId);
});
browser.tabs.onActivated.addListener(() => reportFocused());
browser.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (tab.active)
    reportFocused();
}, {properties: ["url", "title"]});

browser.storage.local.get(["excluded", "darken", "themes"]).then((s) => {
  stored = Array.isArray(s.excluded);
  saved = stored;
  excluded = cleanList(s.excluded);
  darken = s.darken === true;
  themes = cleanThemes(s.themes);
  themeKey = JSON.stringify([excluded, darken, themes.rev]);
  return enqueue(() => replaceRegistration(excluded).then(replaceThemeRegistration));
}).catch(() => {}).then(connect);

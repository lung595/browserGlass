// Browser Glass companion: each site's own dark mode. Under a dark theme
// (the helper's darken, the page not excluded, prefers-color-scheme dark),
// the value a site reads to pick its theme is set to its dark one before
// the page's scripts run, and the prior value is put back once that no
// longer holds (a light theme, the site excluded, Dark pages or the glass
// off). The background registers a document_start payload that defines
// BG_THEME ({dark, excluded, themes}) and calls themeRun(BG_THEME, true);
// it runs after this file (the manifest's scripts come first), and the
// last line covers the other order. content.js calls themeRun(cfg, false)
// again once it knows the list (a late run: it never reloads, and a page
// whose early run already marked <html> gets no new write).
//
// What is written comes from the helper (data/themes.json, "themes"):
//   - the generic rule: page localStorage keys that already exist (never
//     created, never a cookie), a value of the map (light -> dark) changed
//     to its pair;
//   - per-site recipes (the host or a parent of it): a localStorage key or
//     a cookie, "set" (a value of `from`, null for absent, becomes `to`)
//     or "swap" (the substring from[0] of a composite value becomes `to`),
//     optional `reload` (the server renders the theme from the cookie:
//     one reload, at document_start, after the first write), optional
//     `skipIfCookie` (a cookie that means a signed-in account: no write).
// The record of what was written lives in the page's own localStorage
// under RECORD (the only store readable synchronously here), written
// before the value itself:
//   {v: 1, rev, keys: {"local:theme": {prior, wrote, swap?, domain?, path?}},
//    failed: rev (the page stayed light after a write: no write until the
//    recipes change), declined: [id] (a value the user or the site changed
//    after our write: never written again)}.
// A value is put back only while it still holds what was written. A value
// already dark without a record is the user's own choice: left alone.
// This file runs synchronously and does nothing else: no timer, no
// observer, no message; everything is guarded (localStorage can throw).
// One exception, on the reloaded load only: a capture listener for the
// "error" of a stylesheet <link>, fetched once more (the reload cancels
// the first load's requests still in flight, and Gecko can hand that
// cancel to the same sheet of the new page, which then stays empty).
// Function and var declarations only, so that it can be loaded twice.
"use strict";

var THEME_RECORD = "browserGlass.theme";
var THEME_MARK = "data-browserglass-theme";
var THEME_RELOADED = "browserGlass.reloaded";
// One-shot: set just before the reload, removed by the reloaded load.
var THEME_RELOADING = "browserGlass.reloading";
var THEME_RETRIED = "data-browserglass-retried";
var THEME_COOKIE_AGE = 31536000;
// This load: whether an early run wrote or kept a value (only then is a
// light page a failed write), and the rev of the recipes it used.
var themeState = {early: false, rev: ""};

function themeHost() {
  return location.hostname.toLowerCase().replace(/\.$/, "");
}

function themeHostIn(host, domains) {
  return Array.isArray(domains) && domains.some(function (d) {
    return host === d || host.endsWith("." + d);
  });
}

function themeWanted(cfg) {
  try {
    return !!cfg && cfg.dark === true && !themeHostIn(themeHost(), cfg.excluded)
      && window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch (e) {
    return false;
  }
}

function themeReadRecord() {
  try {
    var r = JSON.parse(localStorage.getItem(THEME_RECORD));
    if (r && r.v === 1 && typeof r.keys === "object" && r.keys && Array.isArray(r.declined))
      return r;
  } catch (e) {}
  return {v: 1, rev: "", keys: {}, declined: []};
}

function themeSaveRecord(rec) {
  try {
    if (!Object.keys(rec.keys).length && !rec.declined.length && !rec.failed)
      localStorage.removeItem(THEME_RECORD);
    else
      localStorage.setItem(THEME_RECORD, JSON.stringify(rec));
    return true;
  } catch (e) {
    return false;
  }
}

function themeCookie(name) {
  try {
    var parts = document.cookie.split(";");
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].trim();
      var eq = p.indexOf("=");
      if (eq > 0 && p.slice(0, eq) === name)
        return p.slice(eq + 1);
    }
  } catch (e) {}
  return null;
}

// The current value of a key ({store, key}), null when absent.
function themeRead(c) {
  if (c.store === "cookie")
    return themeCookie(c.key);
  try {
    return localStorage.getItem(c.key);
  } catch (e) {
    return null;
  }
}

// Writes `value` (null: removes), with the cookie's own domain and path.
function themeWrite(c, value) {
  try {
    if (c.store === "cookie") {
      var tail = "; path=" + (c.path || "/") + (c.domain ? "; domain=" + c.domain : "")
        + "; SameSite=Lax" + (location.protocol === "https:" ? "; Secure" : "");
      document.cookie = value === null ? c.key + "=; max-age=0" + tail
        : c.key + "=" + value + "; max-age=" + THEME_COOKIE_AGE + tail;
    } else if (value === null) {
      localStorage.removeItem(c.key);
    } else {
      localStorage.setItem(c.key, value);
    }
    return true;
  } catch (e) {
    return false;
  }
}

// The recipes of the host or its closest parent; null when none.
function themeRecipes(themes, host) {
  var sites = themes && themes.sites;
  if (!sites || typeof sites !== "object")
    return null;
  var labels = host.split(".");
  for (var i = 0; i < labels.length; i++) {
    var h = labels.slice(i).join(".");
    if (Object.prototype.hasOwnProperty.call(sites, h) && Array.isArray(sites[h]))
      return sites[h];
  }
  return null;
}

// The candidates, grouped by id ("local:theme"): the host's recipes, or
// else the generic rule for the keys that exist with a light value.
function themeCandidates(themes, host) {
  var out = {};
  var recipes = themeRecipes(themes, host);
  if (recipes) {
    recipes.forEach(function (r) {
      if (!r || (r.store !== "local" && r.store !== "cookie") || typeof r.key !== "string"
          || typeof r.to !== "string" || !Array.isArray(r.from))
        return;
      if (r.skipIfCookie && themeCookie(r.skipIfCookie) !== null)
        return;
      var id = r.store + ":" + r.key;
      (out[id] = out[id] || []).push(r);
    });
    return out;
  }
  var gen = themes && themes.generic;
  if (!gen || !Array.isArray(gen.keys) || !gen.map || typeof gen.map !== "object")
    return out;
  gen.keys.forEach(function (key) {
    var c = {store: "local", key: key};
    var cur = themeRead(c);
    if (typeof key === "string" && cur !== null
        && Object.prototype.hasOwnProperty.call(gen.map, cur) && typeof gen.map[cur] === "string")
      out["local:" + key] = [{store: "local", key: key, op: "set", from: [cur], to: gen.map[cur]}];
  });
  return out;
}

// Whether the value still holds what was written.
function themeOurs(entry, cur) {
  return entry.swap ? cur !== null && cur.indexOf(entry.wrote) >= 0 : cur === entry.wrote;
}

function themeTarget(id, entry) {
  var at = id.indexOf(":");
  return {store: id.slice(0, at), key: id.slice(at + 1), domain: entry.domain, path: entry.path};
}

// Puts back every value that still holds what was written; a value
// changed since is the user's or the site's: declined. Returns the record.
function themeRestoreAll(rec) {
  Object.keys(rec.keys).forEach(function (id) {
    var entry = rec.keys[id];
    var c = themeTarget(id, entry);
    var cur = themeRead(c);
    if (themeOurs(entry, cur))
      themeWrite(c, entry.swap ? cur.replace(entry.wrote, entry.prior) : entry.prior);
    else if (rec.declined.indexOf(id) < 0)
      rec.declined.push(id);
  });
  rec.keys = {};
  return rec;
}

function themeMark(value) {
  var root = document.documentElement;
  if (!root)
    return;
  if (value)
    root.setAttribute(THEME_MARK, value);
  else
    root.removeAttribute(THEME_MARK);
}

// The load after our reload: a stylesheet that fails is fetched again,
// once (a fresh <link>, the failed one removed).
function themeHealSheets() {
  try {
    if (sessionStorage.getItem(THEME_RELOADING) !== "1")
      return;
    sessionStorage.removeItem(THEME_RELOADING);
    document.addEventListener("error", themeRetrySheet, true);
  } catch (e) {}
}

function themeRetrySheet(e) {
  try {
    var link = e.target;
    if (!link || link.localName !== "link" || link.hasAttribute(THEME_RETRIED)
        || !/(^|\s)stylesheet(\s|$)/i.test(link.rel || ""))
      return;
    var copy = link.cloneNode(false);
    copy.setAttribute(THEME_RETRIED, "1");
    link.after(copy);
    link.remove();
  } catch (err) {}
}

// One run: writes (dark) or restores (anything else). `early`: called at
// document_start, before the page's scripts.
function themeRun(cfg, early) {
  if (early)
    themeHealSheets();
  try {
    var themes = (cfg && cfg.themes) || {};
    var rev = typeof themes.rev === "string" && themes.rev ? themes.rev : "-";
    var rec = themeReadRecord();
    var root = document.documentElement;
    if (!themeWanted(cfg) || rec.failed === rev) {
      if (Object.keys(rec.keys).length) {
        themeSaveRecord(themeRestoreAll(rec));
        themeMark(null);
      }
      themeState.early = false;
      return;
    }
    if (rec.failed && rec.failed !== rev)
      delete rec.failed;
    var marked = root && root.hasAttribute(THEME_MARK);
    var cands = themeCandidates(themes, themeHost());
    var wrote = false, kept = false, reload = false;
    var ids = Object.keys(rec.keys);
    Object.keys(cands).forEach(function (id) {
      if (ids.indexOf(id) < 0)
        ids.push(id);
    });
    ids.forEach(function (id) {
      if (rec.declined.indexOf(id) >= 0)
        return;
      var entry = rec.keys[id];
      if (entry) {
        if (themeOurs(entry, themeRead(themeTarget(id, entry)))) {
          kept = true;
        } else {
          delete rec.keys[id];
          rec.declined.push(id);
        }
        return;
      }
      if (!early && marked)
        return;
      var group = cands[id] || [];
      for (var i = 0; i < group.length; i++) {
        var r = group[i];
        var cur = themeRead(r);
        var value = null;
        if (r.op === "swap") {
          if (cur !== null && typeof r.from[0] === "string" && r.from[0]
              && cur.indexOf(r.from[0]) >= 0 && cur.indexOf(r.to) < 0)
            value = cur.replace(r.from[0], r.to);
        } else if (r.from.indexOf(cur) >= 0 && cur !== r.to) {
          value = r.to;
        }
        if (value === null)
          continue;
        entry = r.op === "swap" ? {swap: true, prior: r.from[0], wrote: r.to} : {prior: cur, wrote: value};
        if (r.store === "cookie") {
          entry.path = r.path || "/";
          if (r.domain)
            entry.domain = r.domain;
        }
        rec.keys[id] = entry;
        rec.rev = rev;
        // write-ahead: the record before the value
        if (!themeSaveRecord(rec)) {
          delete rec.keys[id];
          return;
        }
        if (!themeWrite(themeTarget(id, entry), value)) {
          delete rec.keys[id];
          themeSaveRecord(rec);
          return;
        }
        wrote = true;
        reload = reload || r.reload === true;
        return;
      }
    });
    themeSaveRecord(rec);
    if (wrote || kept) {
      // a late run keeps the early run's mark ("wrote" on this load)
      if (early || !marked)
        themeMark(wrote ? "wrote" : "kept");
      if (early) {
        themeState.early = true;
        themeState.rev = rev;
      }
    }
    if (reload && early && !location.hash) {
      var again = false;
      try {
        again = sessionStorage.getItem(THEME_RELOADED) === "1";
        if (!again)
          sessionStorage.setItem(THEME_RELOADED, "1");
      } catch (e) {
        again = true;
      }
      if (!again) {
        try {
          sessionStorage.setItem(THEME_RELOADING, "1");
        } catch (e) {}
        location.replace(location.href);
      }
    }
  } catch (e) {}
}

// The page stayed light after an early write: every value goes back, and
// the recipes of this rev are not tried again on this site.
function themeFailed() {
  try {
    var rec = themeRestoreAll(themeReadRecord());
    rec.failed = themeState.rev || "-";
    themeSaveRecord(rec);
  } catch (e) {}
  themeState.early = false;
  themeMark(null);
}

if (typeof BG_THEME !== "undefined")
  themeRun(BG_THEME, true);

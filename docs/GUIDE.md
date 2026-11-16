# Browser Glass user guide

This guide explains what Browser Glass does to your browsers and to niri, how to control it, and how it cleans up after itself. To install the plugin and get started, see the [README](../README.md).

- [How it works](#how-it-works)
  - [The style files](#the-style-files)
  - [The preferences](#the-preferences)
  - [The niri rule](#the-niri-rule)
  - [Colours and opacity from DMS](#colours-and-opacity-from-dms)
  - [When Browser Glass acts](#when-browser-glass-acts)
- [What is written where](#what-is-written-where)
- [Sites](#sites)
  - [Light pages under a dark theme](#light-pages-under-a-dark-theme)
- [Live control](#live-control)
- [Restart detection](#restart-detection)
- [Status and report](#status-and-report)
- [Warnings](#warnings)
- [Backups](#backups)
- [Coming from the script version (v0)](#coming-from-the-script-version-v0)
- [Glass off, disabling and uninstalling](#glass-off-disabling-and-uninstalling)
- [Uninstalling](#uninstalling)
- [FAQ](#faq)
- [For developers](#for-developers)

## How it works

Firefox-family browsers can paint a see-through window themselves: their interface and pages are styled with CSS, and the compositor shows whatever is behind the window. Browser Glass uses this in three layers:

1. **Style files** in each browser profile make the browser's interface and the page backgrounds see-through, tinted with the DMS surface colour at the chosen opacity.
2. **Preferences** in each profile's `user.js` let the browser load those files and draw a transparent window.
3. **A niri window rule** keeps the browser window itself at full opacity, so niri does not fade the whole window (video and text included) a second time. The DMS blur behind the window does the rest.

All of it is done by one helper script, `browserglass.py` (Python standard library only), that the plugin runs in the background. The plugin itself only watches for changes and shows the status.

### The style files

Each profile gets two files of its own in its `chrome/` folder:

| File | Loaded by | What it holds |
| --- | --- | --- |
| `chrome/dms-glass-chrome.css` | `userChrome.css` | The browser interface: a `body` background in the DMS tint at the glass opacity, and see-through tabs, toolbars and sidebars. With **Glass private windows** off, private windows get a solid background |
| `chrome/dms-glass-content.css` | `userContent.css` | The pages: transparent `html` and `body` backgrounds on web pages (except the excluded sites), then reader view, the new tab, home and private browsing pages, the site styles, and the PDF viewer |

Each file is loaded by a single line, `@import "dms-glass-chrome.css";` or `@import "dms-glass-content.css";`, added at the top of your `userChrome.css` and `userContent.css` (after a `@charset` line if there is one). Everything else in those files stays yours and stays untouched.

In the content file, only **backgrounds** are made transparent. Text, images and video keep their own colours, which is why they stay solid on glass.

When the glass is off (switched off, blur off, opacity 100%), the two files are rewritten as neutral files: a comment and no rule. The `@import` lines stay until you uninstall, so turning the glass back on is just a rewrite.

With **Glass web pages** off, the content file is neutral too: only the interface is glass.

### The preferences

Browser Glass keeps a marked block in each profile's `user.js`. With the default settings (**Follow DMS**, **Live control** on) and a profile that still has the browser's default add-on preferences, it reads:

```js
// >>> browserGlass v1 managed block (generated, do not edit)
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("browser.tabs.allow_transparent_browser", true);
user_pref("layout.css.prefers-color-scheme.content-override", 2);
user_pref("xpinstall.signatures.required", false);
user_pref("extensions.autoDisableScopes", 14);
user_pref("extensions.startupScanScopes", 1);
// <<< browserGlass v1
```

| Preference | Value |
| --- | --- |
| `toolkit.legacyUserProfileCustomizations.stylesheets` | Always `true`: the browser must load `userChrome.css` and `userContent.css` |
| `browser.tabs.allow_transparent_browser` | `true` only while the glass is on with **Glass web pages**, `false` otherwise |
| `layout.css.prefers-color-scheme.content-override` | The scheme websites are asked for. **Follow DMS**: `2` (automatic: websites get the browser's light or dark theme, which follows the system scheme live). **Always dark**: `0`. **Leave as is**: not written, and your own value comes back |
| `xpinstall.signatures.required` | `false`, only with **Live control** on and the unsigned add-on (as in 1.3.0), where the browser can load it. Not written with a signed add-on (see [Live control](#live-control)) |
| `extensions.autoDisableScopes` | With **Live control**: your value with the profile bit (`1`) cleared, so the add-on placed in the profile loads without a prompt |
| `extensions.startupScanScopes` | With **Live control**: your value with the profile bit (`1`) set, so a profile that already exists picks the add-on up at its next start |

The browser copies `user.js` values into `prefs.js` when it runs, so Browser Glass records each preference's original value the first time it meets a profile, and puts it back in `prefs.js` when the preference is no longer needed. `prefs.js` belongs to the browser while it runs, so that clean-up waits until the browser is closed (see [Uninstalling](#uninstalling)). A `user.js` created by Browser Glass is readable by you only (mode 600); an existing one keeps its permissions.

### The niri rule

niri applies the DMS window opacity to every window. On a glass browser that would fade everything twice, text and video included. So Browser Glass writes `~/.config/niri/dms-browser-glass.kdl`:

```kdl
window-rule {
    match app-id=r#"^(firefox|firefox-esr|librewolf|zen|...)$"#
    opacity 1.0
}
```

and adds one line at the end of `~/.config/niri/config.kdl`:

```kdl
include optional=true "dms-browser-glass.kdl"
```

Because the include comes last, its rule wins over the DMS window rules for these browsers only. `optional=true` means niri still starts if the file is missing. If the `~/.config/niri` folder does not exist, nothing is written there.

The rule matches these app IDs: `firefox`, `firefox-esr`, `librewolf`, `zen`, `zen-browser`, `zen-beta`, `floorp`, `waterfox`, and the Flatpak IDs `org.mozilla.firefox`, `io.gitlab.librewolf-community`, `app.zen_browser.zen`, `one.ablaze.floorp`, `net.waterfox.waterfox`. Snap's `firefox_firefox` is not included, as it could not be tested; if `niri msg windows` shows it, add your own rule at the end of `~/.config/niri/config.kdl`, after the DMS includes (a later rule wins).

The rule covers **every** window of those browsers, including a profile Browser Glass did not style (a profile started with `-profile` from a folder it does not know, say). Such a window shows at full opacity, not faded.

**When the glass goes off**, the rule is not dropped at once: a browser that is still running has the glass styles loaded, and without the rule it would turn into a faded, see-through window. The rule stays (the status shows *The niri rule stays until the running browsers restart*) until every such browser has restarted. Browser Glass notices that and removes the rule by itself. A profile whose lock cannot be read is treated as running, so it also holds the rule.

### Colours and opacity from DMS

| What | Where it comes from |
| --- | --- |
| **Tint** | The DMS `surface` colour of the current mode, from `~/.cache/dms/dms-colors.json`. Without that file: `#101418` in dark mode, `#f7f9ff` in light mode |
| **Mode** | DMS light or dark mode |
| **Opacity** | The first global window rule (a `window-rule` with no `match`) that sets an `opacity` in `~/.config/niri/dms/windowrules.kdl`, the file DMS writes from **Settings → Applications → Window rules**. 100% if there is none. With **Override** on, the **Browser opacity** slider instead |
| **Blur** | **Settings → Interface style → Background blur**. With blur off, the glass stays off |

The status shows where the opacity comes from: *from the DMS window rules*, *set by the override*, or *forced* (from the command line).

The glass is on only when all of these hold, checked in this order:

| Status | Why the glass is off |
| --- | --- |
| *Glass is forced off* | The helper was run with `--off` |
| *Glass is turned off* | You switched **Glass** off |
| *DMS blur is off* | DMS blur is off |
| *Window opacity is 100%* | The opacity in use is 100% |
| *Glass is on* | All good |

### When Browser Glass acts

Browser Glass writes again (after waiting 0.8 s for things to settle) when:

- a plugin setting changes;
- DMS blur is turned on or off;
- DMS switches between light and dark mode;
- the DMS window rules file changes;
- the DMS colours change (a new wallpaper, say).

It also writes once when DMS starts, and at once, without the wait, for a launcher command. At rest there is no timer and no process: the only polling is a status check every 10 s **while a browser needs a restart**, which stops as soon as none does. With **Live control**, each running browser has its helper, which waits without doing anything until a sync talks to it (see [Live control](#live-control)).

Each write only touches files whose content actually changes, so a write with nothing new costs nothing and does not ask for a restart.

## What is written where

| Where | What | Removed by uninstall |
| --- | --- | --- |
| Each profile, `chrome/dms-glass-chrome.css` and `chrome/dms-glass-content.css` | The glass styles | Yes |
| Each profile, `chrome/userChrome.css` and `chrome/userContent.css` | One `@import` line each (the files are created if missing) | The line, or the whole file if Browser Glass created it |
| Each profile, `user.js` | The marked block | Yes |
| Each profile, `prefs.js` | The preferences of the block, put back to their original values | Restored once the browser is closed |
| `~/.config/niri/dms-browser-glass.kdl` | The niri rule | Yes |
| `~/.config/niri/config.kdl` | One `include` line at the end | Yes |
| `~/.local/state/dms/browserGlass/` (`$XDG_STATE_HOME/dms/browserGlass/`) | `state.json`, `state.lock`, `backup/<profile>/`, `state-dirs.json` (the folders made for the state folder, kept so they survive a lost or corrupt `state.json`, with or without **Live control**), `native-dirs.json` (with **Live control**: the folders made for the native manifest) and, during a deferred clean-up, `pending/` | Yes |
| Each profile, `extensions/browserglass@companion.xpi` | With **Live control**: the companion add-on | Yes (the browser forgets it at its next start) |
| `~/.mozilla/native-messaging-hosts/browserglass.json` | With **Live control**: the manifest that lets the companion, and only it, start the helper. Firefox and LibreWolf both read this one. Folders it had to create are recorded | Yes, with the folders it created |
| `~/.local/state/dms/browserGlass/native-host` | With **Live control**: a two-line script the browser runs to start the helper | Yes |
| `$XDG_RUNTIME_DIR/browserGlass/` | While a browser runs with the companion: `host-<pid>.sock` (the helper's socket), `active-<pid>.json` (the active tab's host and title hash) and `ack-<pid>.json` (the last list applied). Memory only, readable by you only, removed when the browser closes | Yes |
| `$XDG_RUNTIME_DIR/browserGlass-sync-settings.json` | Before each sync: the settings it applies (excluded sites included), so they stay out of the process list. The sync reads it and deletes it | Yes |

Profiles are found in the standard places of each browser, for example `~/.mozilla/firefox`, `~/.config/mozilla/firefox`, `~/.librewolf`, `~/.config/librewolf/librewolf`, `~/.zen`, `~/.floorp`, `~/.waterfox`, their Flatpak versions under `~/.var/app/`, and the Snap Firefox under `~/snap/firefox/common/`. Every profile listed in `profiles.ini` is styled, and so are profiles of Firefox's profile groups found next to them.

Never touched: your DMS window rules (`~/.config/niri/dms/windowrules.kdl`), `~/.config/dms/firefox.css`, and anything outside the files above.

## Sites

The content file builds the page glass in layers:

1. **The page rule.** With **Glass web pages** on, every `http` and `https` page gets a transparent `html` and `body` background, except the excluded sites.
2. **Dedicated site styles.** About 650 styles from [my-internet](https://github.com/sameerasw/my-internet) teach well-known sites to be see-through where a transparent `body` is not enough (sites that paint their own backgrounds on inner blocks). Only their transparency features are kept (the parts whose names mention transparency, glass or translucency); the rest of their restyling is left out. They ship with the plugin: nothing is downloaded.
3. **The generic style.** With **Generic style for other sites** on, every site without a dedicated style gets my-internet's generic transparency style. It removes background colours only: a background image, such as the photo behind a page's banner, stays.

A dedicated style for `example.org` covers `example.org` and its subdomains, except those another style claims for itself (`docs.example.org` with its own style). A few styles cover a name under any domain ending, and some cover extra hosts listed by my-internet.

**Excluded sites** get none of the three: they keep their normal background. An exclusion covers the domain as entered and its subdomains: excluding `example.org` also excludes `docs.example.org`, while excluding `www.example.org` leaves `example.org` alone. **Exclude copied URL** takes the host of the address in your clipboard and drops a leading `www.`, so it excludes the whole site. It answers with a toast: *Site excluded from glass*, *Site already excluded*, or *The clipboard holds no web address*.

**From the launcher** (`gs blist`, see the [README](../README.md#launcher)), the exclusion is the *registrable domain* of the open page: the name you could register, found with the bundled [Public Suffix List](https://publicsuffix.org). `account.example.org` gives `example.org` and `a.b.co.uk` gives `b.co.uk`. A site under a shared hosting suffix such as `user.github.io` is excluded as it is, never every site under `github.io`. A host that is itself a public suffix (`github.io`) is refused with *Address not supported*, since excluding it would exclude every site under it. Addresses such as `localhost` and IPv4 addresses are taken as they are; IPv6 addresses are not supported either. The toast names what was excluded. `gs unblist` removes every exclusion that covers the open page, so it removes `example.org` as well as `account.example.org`; its line and toast name the exclusions it removes (`account.example.org` for one made with **Exclude copied URL**). **Exclude copied URL** keeps the host you copied, as before: you chose it yourself.

**Switching a dedicated style off** in **Dedicated site styles** removes that site's tailored style; the site still counts as having one, so the generic style does not take its place. It keeps the plain page rule of step 1.

**Reader view, PDF, new tab, private windows.** With **Opaque reader view and PDF** on (default), reader view and the PDF viewer stay solid for reading; off, reader view and the PDF viewer turn glass too. **Glass new tab** covers the new tab, home and private browsing pages.

### Light pages under a dark theme

Many sites have a light version only: dark text on a white page. On the dark tint that text would be unreadable. So under a dark theme, the page rule, the generic style **and every dedicated site style** (my-internet's and Browser Glass's own fixes) apply only to pages that declare a dark version: a `color-scheme` meta naming `dark`, or a dark-mode marker such as `data-theme="dark"` or `class="dark"` on `<html>`. A light-only page keeps its own background and stays readable. Under a light theme nothing changes: every page is glass.

**With Live control**, the companion add-on does better: it measures the page's text colour (dark text means a light page; text on cards painting a background of their own or drawn over a picture, the site's menus and mid-grey text count only when there is nothing else; a dark band that starts below the first screen, such as a shop's tall footer, is a card too) and marks the page as light or dark. The site styles then apply whatever the theme, and the tint follows the page: a light page under a dark theme gets a **light** glass (the DMS light surface at 88 %, opaque enough for text over a dark wallpaper), a dark page under a light theme a dark one (the dark surface at 88 %). The add-on measures again when the page has loaded, when the page switches its own theme on `<html>` (a class or a `data-theme` attribute, for instance) and when the system switches between light and dark. Nothing is sent anywhere: the measure stays in the page. Only the main page is measured: frames inside it keep their own background. The measure is that of the text as shown: a site style that makes the text white counts as a dark page, and keeps the dark glass behind it. Parts of a page drawn in a shadow DOM cannot see these marks (see [Known limits](../ROADMAP.md#known-limits)). Without the add-on (a private window, a Firefox release build), the page keeps its own background as above.

**Dark pages** (**Sites → Dark pages**, on by default, with Live control): under a dark theme, rather than a light glass, the add-on turns a light page dark. It tries, in order: the page's own answer to the system scheme, the site's own dark theme stored in its settings (see the next paragraph), the marks on `<html>`, then Dark Reader. For the marks: many sites keep one behind a mark on `<html>` rather than following the system (a `dark`, `dark-mode` or `theme-dark` class, `data-theme="dark"`, `data-bs-theme`, `data-color-mode`, `data-theme-mode`, `data-mode` or a `dark` attribute). The add-on sets these marks, and keeps them if the page's text turns light; a light theme or excluding the site takes them back. Otherwise it removes them and darkens the page with the [Dark Reader](https://darkreader.org) engine it bundles and the DMS colours (the dark surface for the backgrounds, the light one for the text, their tint muted so grey text stays grey). It does so once the page has loaded (or shows enough text), so a light page may flash white first. The page then counts as a dark one: its background is glass, and so are the large elements that paint it (a wrapper as wide as the window and most of its height, found under a grid of points when the page loads, grows, is resized or scrolled): the add-on marks them `data-browserglass-canvas`, and the style file makes their background colour transparent. Smaller parts (cards, menus, a cookie banner) stay solid, dark. Pages that declare a dark version, excluded sites and a light theme are left alone (a page that names both schemes in its `color-scheme` meta but marks `<html>` light, `data-color-mode="light"`, `data-theme="light"` or a `light` class, counts as light); switching to a light theme, excluding the site or a page switching to its own dark version gives the page back as it was, at once. Dark Reader runs in the page; what it fetches across origins is limited to the stylesheets the page already uses, sent without cookies or referrer. The helper tells the add-on whether to darken (the **Dark pages** setting, sent with the excluded sites), so a page cannot switch the darkening on by itself. Turning **Dark pages** off gives darkened pages back at once, with no restart asked once the add-on has answered; turning it on applies after a browser restart. With **Dark pages** off, a light page gets the light glass above.

**Sites with their own theme menu** show their light theme to a visitor whatever the system says, and keep the choice in their own settings: a value in the page's storage (`localStorage`) or a cookie. Under a dark theme, with **Dark pages** on, the add-on writes that value before the page's scripts run, so the site starts in its own dark theme: neither the marks nor Dark Reader are needed. It knows two kinds of values. The generic rule covers a few common storage keys (`theme`, `color-mode`, `colorScheme`, `appearance` and the like) that already exist with a value meaning light (`light`, `Light`, `LIGHT`): it is changed to its dark pair, never created, never written to a cookie. Recipes for given sites (`data/themes.json`, sent by the helper with the excluded sites; Wikipedia, for one) name the exact key or cookie, and the values to change; a cookie recipe may reload the page once, when the server draws the theme from the cookie. What the add-on wrote is recorded in the page's own storage (`browserGlass.theme`), and put back as it was under a light theme, once the site is excluded, or with **Dark pages** or the glass off. A value that was already dark is your own choice and is left alone; a value changed after the add-on wrote it (your choice in the site's theme menu, or the site writing its own default back) wins, and is never written again on that site. If the page stays light after the write (the site does not have a dark theme after all), the value goes back, Dark Reader darkens the page as before, and the write is not tried again on that site until the recipes change. A cookie the site keeps out of reach of scripts (`HttpOnly`, as Galaxus does once you pick a theme in its menu) cannot be replaced: the page reloads once, and if it stays light, Dark Reader takes over the same way. A page already open when the setting changes gets its theme on its next load. Once signed in, a site may keep the theme in your account instead: a recipe can then skip the write, and your account settings decide. Uninstalling the add-on leaves the written values in place (the site then shows its dark theme until you change it in its menu); turning **Dark pages** off first puts them back.

**Page layers** (with Live control, whatever the theme): on a page whose root and body are already see-through, the add-on also marks the lowest layer that still paints the page's background over most of the window, often a fixed full-window container in a web app (Jellyfin, for example), `data-browserglass-canvas`: that background becomes glass, while the cards and panels drawn over it keep theirs (a translucent layer, such as the dimming behind a dialog, is left alone). It looks again as the page changes: a click, a page rendered late, a resize, a scroll. Every navigation bar fixed or stuck along an edge of the window, a header, a bottom bar or a sidebar, gets `data-browserglass-bar` and the same look on every site, whatever its own colours, the DMS surface at 65 % over a blur laid on the glass's colour, so what scrolls under it, text included, is blurred like a picture and does not show through the bar's text, the dark one on a dark (or darkened) page, the light one on a light page. A sticky bar is marked only while it is stuck to the edge, and only a bar with an opaque background of its own, or a see-through one with the page's content under any part of it (a transparent header over posters, as in Jellyfin, or the row of links below a notice at the top of a tall header); a see-through bar over nothing but the page's background is left alone, and inside a bar only the outermost element is marked. A sidebar or header laid in the page's flow, neither fixed nor sticky, keeps its own colours: it cannot be told from the page's panels (a chat composer, a card). Inside fixed and sticky elements, the parts painted with the page's own background colour, an empty fade layer or a panel that covers a bar, become glass too (`data-browserglass-canvas="fill"`), so they do not leave black bands on the glass.

**Readable text** (with Live control): the add-on checks the visible text against what is now behind it (the first opaque background up the page, or the glass). Text that reads under a 2:1 ratio, dark text left on the dark glass for example, gets `data-browserglass-ink` and the DMS light surface as its colour (the dark one on the light glass). Words drawn with a gradient clipped to the text are judged by that gradient's colours, and a readable colour gets drawn over it. Text over a picture is left alone (a thin gradient line, such as an underline, is no picture), and a layer kept invisible (a hover state) is no face. **Pictures on a white tile**: a picture made for a white page shows on a white tile once the background behind it is dark, as shops show product photos in their own dark theme: a white background, a white margin of 6 px drawn around it (the layout does not move), round outer corners, no blending and no filter. The add-on marks it `data-browserglass-tile`. Two kinds get one: a picture blended into the page with `multiply` or `darken` (a product photo or a logo whose white background the site wipes out that way, which turns dark or invisible on a dark background), and, on a page the add-on darkens with Dark Reader, a picture on a transparent background whose ink mostly reads under 2:1 against the dark background (a black logo or line drawing). For the second kind the add-on reads the picture's pixels, which the browser allows only for a picture of the page's own site or one embedded in the page: a picture from another site stays as it is. Icons under 24 px, photos nearly as wide as the window, pictures on a light background, CSS background pictures and inline SVG drawings are left alone, and so is everything on a page shown in its own dark theme, apart from blended pictures. **Frames** inside a page (a captcha, an embedded video or form) keep their own background: the add-on marks them excluded, and on a darkened page they keep their own colour scheme (Dark Reader's dark one would give a light frame an opaque backdrop).

You no longer need a site fix just because a site is light only.

## Live control

The browser reads its style files only when it starts, so an exclusion would normally wait for a restart. **Live control** (**Settings → Plugins → Browser Glass → Advanced & help**, on by default) removes that wait for exclusions, with a small companion add-on in each profile.

**How it works.**

1. At each sync, Browser Glass writes the style file with every rule ready to be switched off, plus the rules that bring the glass back to a site that was excluded when the browser started.
2. It places the add-on `browserglass@companion.xpi` in each profile's `extensions/` folder, and the manifest `~/.mozilla/native-messaging-hosts/browserglass.json`. The browser loads the add-on at its next start.
3. The add-on starts the Browser Glass helper (`browserglass.py native-host`, through the script `~/.local/state/dms/browserGlass/native-host`). The helper lives as long as the browser and waits, doing nothing, on a socket in `$XDG_RUNTIME_DIR/browserGlass/`.
4. Every sync sends the list of excluded domains, with the **Dark pages** setting and the site theme recipes (a few kilobytes at most, never the CSS), to every running helper. When you exclude a site or put it back, the add-on marks the pages of the excluded sites, and the style file already loaded does the rest: the page changes at once. The add-on answers when it is done, so Browser Glass knows the change is live and does not ask for a restart; the same goes for turning **Dark pages** off.
5. The add-on also tells the helper the host of the active tab of the window in focus, which is how the launcher knows the current site.

Only the main page is concerned: frames inside a page keep their own background (the add-on marks them excluded). Private windows do not run the add-on (it does not ask for them), so they behave as without Live control.

**What it changes in the browser.** Up to three preferences go into the marked `user.js` block (see [The preferences](#the-preferences)): the profile bit of `extensions.autoDisableScopes` and `extensions.startupScanScopes`, so the add-on placed in the profile loads without a prompt, and, while the add-on is unsigned (as in 1.3.0), `xpinstall.signatures.required` set to `false` so it can load. Their original values are recorded and put back like the others.

**Signed or unsigned add-on.** Browser Glass can use an add-on signed by Mozilla, kept as `companion/browserglass@companion.xpi`; 1.3.0 to 1.3.3 do not ship that file yet (the signed add-on is planned for a later version). A sync places it only when it holds exactly the files of `extension/` and Mozilla's signature. Otherwise, as in 1.3.0, it places the unsigned add-on built from `extension/`, as 1.2 did: it then also sets `xpinstall.signatures.required` to `false`, which LibreWolf, Firefox Developer Edition and Nightly follow, and writes nothing for the companion on Firefox release, ESR and Beta (`signing_enforced`). A signed file that cannot be read or is damaged gives a warning, and the unsigned add-on is used.

**Updating from 1.1 or 1.2.** Those versions wrote `xpinstall.signatures.required = false`, and 1.3.0 keeps it with the unsigned add-on. Only once the signed add-on is used does it leave the `user.js` block, and its original value goes back in `prefs.js` once the browser is closed. Until then the block holds the original value (or the browser default, `true`), so the browser does not keep `false` at its next start.

**States.** The *Live control* line in **Status** comes from `companion.state` in `status --json`:

| `state` | Status line | Meaning |
| --- | --- | --- |
| `connected` | *Live control: connected* | A browser runs the add-on of this version and its helper is listening |
| `waiting_restart` | *Live control: waiting for a browser restart* | The add-on is in place; the browser loads it at its next start. After a plugin update, also while the browser still runs the older add-on |
| `disabled` | *Live control: the add-on is disabled in the browser; enable it in about:addons* | The add-on is in place, but disabled in `about:addons` in every profile that has it. Browser Glass leaves it there: enable it again in `about:addons` |
| `removed` | *Live control: the add-on was removed in the browser; turn Live control off and on to add it back* | No profile has the add-on, and it was removed in the browser (`about:addons`) in at least one profile. Browser Glass leaves it out until Live control is turned off and on again |
| `unavailable` | *Live control: not available for these browsers; changes apply at the next restart* | No profile has the add-on: Flatpak or Snap browsers, browsers that refused it, or Firefox release, ESR or Beta builds while the add-on is unsigned (see below). Changes apply at the next restart |
| `off` | *Live control: off* | Live control is turned off |

`companion` also has `enabled` (the setting at the last sync), `hosts` (how many helpers are running) and `manifest` (the native messaging manifest is in place). Each profile in `browsers[].profiles[]` has its own `companion` state:

| Profile state | Meaning |
| --- | --- |
| `installed` | The add-on is in the profile, and the browser lists it as enabled |
| `disabled` | The add-on is in the profile, but disabled in `about:addons`: enable it again there |
| `pending_restart` | The add-on is in the profile; the browser has not loaded it yet |
| `outdated` | The browser runs an add-on from an older version: restart it once more |
| `signing_enforced` | The unsigned add-on (no matching signed add-on, as in 1.3.0) on a Firefox release, ESR or Beta build: they only load add-ons signed by Mozilla, so nothing is written for the companion |
| `signing_required` | The browser deleted the add-on at start-up (it wants signed add-ons; the signed add-on should never get this). Browser Glass takes the add-on's preferences back and stops trying until the browser is updated |
| `removed_by_user` | The add-on was removed in `about:addons`: LibreWolf, Firefox Nightly and Developer Edition never delete it themselves; on other browsers Browser Glass saw it loaded first (otherwise the removal reads as `signing_required`). Browser Glass takes the add-on's preferences back and does not place it again, even after a browser update, until Live control is turned off and on again (or the plugin is disabled and enabled again) |
| `unsupported_variant` | A Flatpak or Snap browser: the helper would have to run inside their sandbox |
| `no_plugin_dir` | A `sync` run by hand without `--plugin-dir`, or a profile the add-on has not been placed in yet: the add-on is left as it is, and the next sync from the plugin places it |
| `off` | Live control is turned off |

With the unsigned add-on, a Firefox profile that has never been started follows the channel of the installed Firefox: `signing_enforced` when that build enforces signing. Any other profile whose channel cannot be read gets the add-on; if Firefox then drops it at start-up, the profile turns `signing_required`.

**Turning it off.** At the next sync the add-on, its preferences, the manifest and the helper script are removed, and the style file goes back to the same rules as without Live control. A helper still running goes away with its browser.

**Uninstalling** also removes all of it: the add-on of each profile, the manifest (and the folders created for it), the helper script, `$XDG_RUNTIME_DIR/browserGlass/`, and its preferences come back to their original values. Once the browser is closed, the clean-up also removes the add-on's own leftovers in the profile: its storage folder, its entry in `extensions.webextensions.uuids` (only that entry; the other add-ons keep theirs) and its storage-migration preference. The browser removes the add-on from its own list, `extensions.json`, at its next start.

## Restart detection

The browser reads its style files and `user.js` only when it starts. Browser Glass tells you when a running browser is behind:

- For each profile, it checks whether a browser is running on it, from the profile's lock (the `.parentlock` file, or the `lock` link as a fallback). This also works for Flatpak and Snap browsers.
- If one is, and one of its glass files (the two style files, `userChrome.css`, `userContent.css` or `user.js`) changed after that browser started, the profile needs a restart.
- Except for exclusions applied live: when the only change is the list of excluded sites and that browser's companion add-on confirmed it applied the new list (see [Live control](#live-control)), no restart is needed.

The widget then shows a dot, its menu says *Restart Firefox to see the change* (with the right browser name), and the status lists it. A toast *Restart your browser to apply Browser Glass* also shows when a write changes a running browser, again when the glass opacity changes before that restart (the DMS window rule edited), and says what a restart is: every window of the browser closed, then the browser opened again. Closing one window of several, or opening the browser again from the launcher while one of its windows is still open, only hands a new window to the browser already running, which keeps the styles it read when it started. While any browser needs a restart, the plugin checks again every 10 s, so the dot goes away soon after you restart it. The check stops after three failed reads in a row.

## Status and report

**Settings → Plugins → Browser Glass → Status** shows the status in words. The same status comes as JSON:

```sh
dms ipc call browserGlass status
python3 -I ~/.config/dms/plugins/browserGlass/browserglass.py status --json
```

```json
{"version": "1.1.0",
 "glass": {"active": true, "reason": "active", "opacity": 0.85, "opacity_source": "dms",
           "surface": "#101418", "mode": "dark", "dms_opacity": 0.85},
 "niri": {"config": true, "include": true, "rule": true},
 "companion": {"enabled": true, "state": "connected", "hosts": 1, "manifest": true},
 "restart_needed": false,
 "browsers": [{"family": "firefox", "variant": "native", "root": "~/.mozilla/firefox",
               "running": false, "restart_needed": false,
               "profiles": [{"id": "...", "name": "default-release", "default": true,
                             "running": false, "restart_needed": false, "applied": true,
                             "companion": "installed", ...}]}],
 "warnings": []}
```

The **IPC** call answers with the last status the plugin has, and asks for a fresh one. The **script** reads everything now. The status JSON holds paths and profile names, so do not paste it in public as is.

**The anonymous report** is made for bug reports. Get it with **Copy report**, with `dms ipc call browserGlass report` (both copy it to the clipboard), or in a terminal:

```sh
python3 -I ~/.config/dms/plugins/browserGlass/browserglass.py report
```

```text
browserGlass report
version: 1.1.0
python: 3.12.4
dms: 2.0.0
browsers: firefox native 128.0
glass: active (reason active, opacity 0.85, source dms, mode dark)
niri: config yes, include yes, rule yes
companion: connected (hosts 1, manifest yes, profiles installed 1)
restart needed: no
applied: 1 of 1 profiles
profiles:
  firefox native: 1 (0 running, 0 restart needed)
settings: glassEnabled=true opacityOverride=false siteTheme=follow pagesTransparent=true genericStyle=true excluded=0 disabledStyles=0 newTabGlass=true readerOpaque=true privateGlass=true liveControl=true darkPages=true
warnings: none
```

It holds versions, counts, your settings (lists as counts only), the Live control state with its profile states counted, and warning codes: no path, no profile name, no site, no address. It is never sent anywhere; you paste it yourself.

## Warnings

Warnings show in the status. The ones you can act on also show once as a toast.

| Warning | What it means | What to do |
| --- | --- | --- |
| *A browser file is read-only: it was left unchanged* | A profile file cannot be written | Make it writable, then **Re-sync** |
| *A browser file is a broken link: it was left unchanged* | A profile file is a symbolic link to nothing | Fix or remove the link |
| *A file could not be written* | A write failed (disk full, permissions) | Check the disk and permissions |
| *A browser profile was skipped: a file could not be read* | A profile file could not be read | Check its permissions |
| *A browser profile was skipped: no backup could be taken* | The original could not be saved, so nothing was changed | Check `~/.local/state` |
| *A browser profile folder was not found* | A profile listed in `profiles.ini` has no folder | Nothing, or tidy `profiles.ini` |
| *A browser file was edited since its backup: the original was kept* | At uninstall, a file had changed since its backup | See [Backups](#backups) |
| *The site styles could not be read* | The plugin's `data/` files are missing or damaged | Reinstall the plugin |
| *A site style was skipped: it is not valid* | One style failed the safety checks | Nothing: the other styles work |
| *The plugin's saved state was unusable: it starts afresh* | `state.json` was damaged | Nothing: it is rebuilt |
| *The plugin's saved state could not be used* | The state folder cannot be used | Check `~/.local/state/dms/browserGlass/` |
| *The clean-up after the browser closes could not start* | The background `prefs.js` clean-up could not start | Run the uninstall command again once the browser is closed |
| *Zen transparency mod detected: it may stack with Browser Glass* | A Zen mod or Zen setting about transparency is on | Keep only one of the two |
| *The niri rule stays until the running browsers restart* | See [The niri rule](#the-niri-rule) | Restart the browsers |

**Zen.** Zen keeps its mods in `zen-themes.json` in each profile folder. Browser Glass reads it (and `chrome/zen-themes.json` if present) and warns when an enabled mod's name or tags mention transparency, glass, blur, acrylic or mica, or when a `zen.` preference about transparency is on in `user.js` or `prefs.js`. Zen support follows Zen's documented layout but has not been tested on a live Zen yet.

## Backups

The first time Browser Glass changes a profile, it saves the originals of `userChrome.css`, `userContent.css` and `user.js` (or notes that they did not exist), with the original values of its preferences, in `~/.local/state/dms/browserGlass/backup/<profile>/`. The folder name is a short hash of the profile path, not the profile name. It never takes a second backup over the first one.

At uninstall:

- a file you have not touched since is put back **byte for byte**, permissions included, or removed if Browser Glass created it;
- a file you edited since keeps your edits: only the `@import` line or the marked block is taken out, the backup stays in the state folder, and the uninstall reports a `backup_kept` warning (*A browser file was edited since its backup: the original was kept*). Compare the two and keep what you want, then delete the backup folder.

## Coming from the script version (v0)

If you used the earlier script version of Browser Glass (v0), v1 takes over without any step from you:

- the same `@import` lines and niri `include` line are reused, not doubled;
- the old marked block of `user.js` is recognised and replaced by the v1 block;
- the old cache of site styles in `~/.cache/dms/browserGlass/` is deleted (v1 ships the styles and needs no cache);
- your **Glass web pages** setting and your excluded sites are kept;
- the backups are taken from your files **without** the v0 additions, so an uninstall gives back the files as they were before any version of Browser Glass.

## Glass off, disabling and uninstalling

| You do | Result |
| --- | --- |
| Switch **Glass** off (widget, settings, `gs off` in the launcher, `dms ipc call browserGlass toggle`) | The style files turn neutral and the browsers follow the DMS window opacity again after a restart. Everything stays installed, ready to turn back on |
| Disable the plugin in **Settings → Plugins** | Full uninstall: everything restored (toast *Browser Glass disabled: restoring the browsers*) |
| Delete the plugin folder while DMS runs | The same full uninstall, started on its own |

## Uninstalling

**Disable the plugin** in **Settings → Plugins**. That is all: Browser Glass shows *Browser Glass disabled: restoring the browsers* and runs its uninstall. The browsers can stay open. A sync that was already starting when you disabled the plugin sees it is disabled and writes nothing. Then delete `~/.config/dms/plugins/browserGlass` if you want.

The uninstall:

1. removes the two style files and the `@import` lines, and the `chrome/` folder if Browser Glass created it;
2. removes the marked block from `user.js`, or the whole file if it created it;
3. restores the files you did not edit from their [backups](#backups), byte for byte;
4. removes the niri file and the `include` line;
5. removes the companion add-on of each profile, the native messaging manifest, the helper script and `$XDG_RUNTIME_DIR/browserGlass/` (see [Live control](#live-control));
6. puts the original preference values back in `prefs.js` (see below);
7. removes its state folder and the old v0 cache.

**`prefs.js` and running browsers.** A running browser rewrites `prefs.js` when it closes, so Browser Glass cannot fix it while the browser is open. For each running profile, it starts a small background clean-up that checks every 5 s whether the browser has closed, and then restores the original preference values. At a logout or shutdown, the browser and the clean-up are stopped together: the clean-up then checks five times a second for a few seconds, so it usually finishes as the browser closes. For the same reason, a shell restart while a clean-up is waiting can take a few seconds longer. The job is written down in `~/.local/state/dms/browserGlass/pending/` first, so the note survives a crash or a logout that stops the clean-up too early, and the next sync or uninstall picks it up. If the browser stays open for more than **7 days**, the clean-up gives up and leaves its note in `pending/` the same way. While the plugin stays disabled, nothing runs the job again: run the uninstall command below once the browser is closed (or enable the plugin again), and it finishes the job.

**Deleting the plugin folder** while DMS runs also cleans up: when DMS sees the plugin gone, it runs the uninstall from a copy of the script kept in memory, after a 4 s grace period. If the folder comes back within that time (an update that replaces the folder), nothing is done. Otherwise a toast says *Browser Glass removed: browsers restored*, and the plugin's settings entry is removed from DMS.

**By hand.** Disable the plugin first (or quit DMS), then run:

```sh
python3 -I ~/.config/dms/plugins/browserGlass/browserglass.py uninstall
```

It prints what it did as JSON. If the plugin folder is already gone (deleted while DMS was not running), get `browserglass.py` again from the repository: it needs no other file. Run it from wherever it is with `python3 -I browserglass.py uninstall`, or feed it on standard input:

```sh
python3 -I -c "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))" uninstall < browserglass.py
```

Running the uninstall twice is harmless.

## FAQ

**Why does almost every change need a browser restart?**
Firefox reads `userChrome.css`, `userContent.css` and `user.js` only at start-up. Browser Glass writes the change at once and tells you which browser to restart.
Two changes need no restart. Switching DMS between light and dark: the style files hold both tints, and the browser follows the system light/dark scheme live. DMS writes its mode to the system scheme only with **Settings → Theme → Portal & terminals → Sync with portal** on; the settings page says so when it is off. And, with [Live control](#live-control), excluding a site or putting it back.

**Why does `gs off` still ask for a restart?**
Turning the glass on or off changes the browser's own bars, which the browser reads only at start-up, so it is not live. The window follows at once (niri's rule changes), and the browser's bars and pages follow at its next restart, as with the widget's switch.

**Why does a light website stay white in dark mode?**
Without the companion add-on, under a dark theme, only pages that declare a dark version become see-through, dedicated site styles included; a light-only page keeps its own background, since its dark text would be unreadable on the dark tint. With **Live control**, such a page gets a light glass instead. See [Light pages under a dark theme](#light-pages-under-a-dark-theme). A site that stays hard to read can be excluded (see [Sites](#sites)).

**Does Live control work on Firefox release?**
Not yet. Firefox release, ESR and Beta builds only load add-ons signed by Mozilla, and they ignore `xpinstall.signatures.required`. The companion is not signed yet (planned for a later version, see the [roadmap](../ROADMAP.md#planned)), so on those builds Browser Glass does not install it, and the launcher's changes apply at the next restart. Firefox Developer Edition and Nightly accept the unsigned add-on.

**Does Live control work with LibreWolf?**
Yes: LibreWolf loads unsigned add-ons. Its add-ons page shows the companion as *could not be verified*, as it does for every unsigned add-on; this is normal and does not stop it.

**What about private windows?**
The companion does not run in private windows, and the browser does not record them in its session either. Browser Glass tells a private window by its title. So `gs blist` refuses there (*Private window: site not detected*), and a private window shows a change of the excluded sites only after a restart. Glass itself works there as usual.

**And frames inside a page?**
With Live control, frames (a captcha, an embedded video or form) keep their own background, so their text stays readable on the glass. Without it they follow the generic rule.

**Why is the current site sometimes late without the companion?**
Without the add-on, Browser Glass reads the browser's saved session (`sessionstore-backups/recovery.jsonlz4` in the profile). The browser saves it about every 15 s, and only once an hour after the computer has been idle for 3 minutes. Right after you open a page, the launcher may still see the previous one; the toast says how old the session is when it is more than 10 s old. With the companion the site is always current.

**Why are video and pictures not see-through?**
On purpose: only backgrounds are made transparent, and the niri rule keeps the window itself at full opacity. What you read and watch stays sharp.

**A site is hard to read on glass.**
Copy its address and use **Exclude copied URL**. If it has a dedicated style that misbehaves, you can also switch that style off in **Dedicated site styles**.

**Can I have glass in one browser and not another?**
Not in v1: every Firefox-family profile found is styled. You can exclude sites, or turn the glass off for all.

**Can I use my own `userChrome.css`?**
Yes. Browser Glass only adds one `@import` line at the top and leaves the rest alone. Your rules come after it, so they win where they overlap.

**Does it work with Chromium, Chrome or Brave?**
No. Only the Firefox family can be styled this way.

**Does it work without niri?**
The browser styles do, but without the niri rule the DMS window opacity also fades text and video. Browser Glass is made for niri.

**I changed the wallpaper and the browser did not change colour.**
Restart the browser: the new tint is already written.

**Where does it keep its settings?**
In DMS's plugin settings, with the other plugins. Its own state and backups are in `~/.local/state/dms/browserGlass/`.

**Does it send anything anywhere?**
No. It makes no network request at all; the site styles ship with it. The companion add-on talks only to the local helper, which keeps the active tab's host in `$XDG_RUNTIME_DIR/browserGlass/` until the browser closes.

## For developers

After changing a QML file or `components/logic.js`, run `dms restart`: `dms ipc call plugins reload browserGlass` reloads the plugin but keeps its components cached, and a new root QML file (such as `BrowserGlassLauncher.qml`) is only picked up by a restart. Architecture, tests and the release process are in [CONTRIBUTING.md](../CONTRIBUTING.md).

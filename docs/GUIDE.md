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

Browser Glass keeps a marked block in each profile's `user.js`:

```js
// >>> browserGlass v1 managed block (generated, do not edit)
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("browser.tabs.allow_transparent_browser", true);
user_pref("layout.css.prefers-color-scheme.content-override", 0);
// <<< browserGlass v1
```

| Preference | Value |
| --- | --- |
| `toolkit.legacyUserProfileCustomizations.stylesheets` | Always `true`: the browser must load `userChrome.css` and `userContent.css` |
| `browser.tabs.allow_transparent_browser` | `true` only while the glass is on with **Glass web pages**, `false` otherwise |
| `layout.css.prefers-color-scheme.content-override` | The scheme websites are asked for. **Follow DMS**: `1` in light mode, `0` in dark mode. **Always dark**: `0`. **Leave as is**: not written, and your own value comes back |

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

It also writes once when DMS starts. At rest there is no timer and no process: the only polling is a status check every 10 s **while a browser needs a restart**, which stops as soon as none does.

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
| `~/.local/state/dms/browserGlass/` (`$XDG_STATE_HOME/dms/browserGlass/`) | `state.json`, `state.lock`, `backup/<profile>/` and, during a deferred clean-up, `pending/` | Yes |

Profiles are found in the standard places of each browser, for example `~/.mozilla/firefox`, `~/.config/mozilla/firefox`, `~/.librewolf`, `~/.config/librewolf/librewolf`, `~/.zen`, `~/.floorp`, `~/.waterfox`, their Flatpak versions under `~/.var/app/`, and the Snap Firefox under `~/snap/firefox/common/`. Every profile listed in `profiles.ini` is styled, and so are profiles of Firefox's profile groups found next to them.

Never touched: your DMS window rules (`~/.config/niri/dms/windowrules.kdl`), `~/.config/dms/firefox.css`, and anything outside the files above.

## Sites

The content file builds the page glass in layers:

1. **The page rule.** With **Glass web pages** on, every `http` and `https` page gets a transparent `html` and `body` background, except the excluded sites.
2. **Dedicated site styles.** About 650 styles from [my-internet](https://github.com/sameerasw/my-internet) teach well-known sites to be see-through where a transparent `body` is not enough (sites that paint their own backgrounds on inner blocks). Only their transparency features are kept (the parts whose names mention transparency, glass or translucency); the rest of their restyling is left out. They ship with the plugin: nothing is downloaded.
3. **The generic style.** With **Generic style for other sites** on, every site without a dedicated style gets my-internet's generic transparency style.

A dedicated style for `example.org` covers `example.org` and its subdomains, except those another style claims for itself (`docs.example.org` with its own style). A few styles cover a name under any domain ending, and some cover extra hosts listed by my-internet.

**Excluded sites** get none of the three: they keep their normal background. An exclusion covers the domain as entered and its subdomains: excluding `example.org` also excludes `docs.example.org`, while excluding `www.example.org` leaves `example.org` alone. **Exclude copied URL** takes the host of the address in your clipboard and drops a leading `www.`, so it excludes the whole site. It answers with a toast: *Site excluded from glass*, *Site already excluded*, or *The clipboard holds no web address*.

**Switching a dedicated style off** in **Dedicated site styles** removes that site's tailored style; the site still counts as having one, so the generic style does not take its place. It keeps the plain page rule of step 1.

**Reader view, PDF, new tab, private windows.** With **Opaque reader view and PDF** on (default), reader view and the PDF viewer stay solid for reading; off, reader view and the PDF viewer turn glass too. **Glass new tab** covers the new tab, home and private browsing pages.

## Restart detection

The browser reads its style files and `user.js` only when it starts. Browser Glass tells you when a running browser is behind:

- For each profile, it checks whether a browser is running on it, from the profile's lock (the `.parentlock` file, or the `lock` link as a fallback). This also works for Flatpak and Snap browsers.
- If one is, and one of its glass files (the two style files, `userChrome.css`, `userContent.css` or `user.js`) changed after that browser started, the profile needs a restart.

The widget then shows a dot, its menu says *Restart Firefox to see the change* (with the right browser name), and the status lists it. A toast *Restart your browser to apply Browser Glass* also shows when a write changes a running browser. While any browser needs a restart, the plugin checks again every 10 s, so the dot goes away soon after you restart it. The check stops after three failed reads in a row.

## Status and report

**Settings → Plugins → Browser Glass → Status** shows the status in words. The same status comes as JSON:

```sh
dms ipc call browserGlass status
python3 -I ~/.config/dms/plugins/browserGlass/browserglass.py status --json
```

```json
{"version": "1.0.0",
 "glass": {"active": true, "reason": "active", "opacity": 0.85, "opacity_source": "dms",
           "surface": "#101418", "mode": "dark", "dms_opacity": 0.85},
 "niri": {"config": true, "include": true, "rule": true},
 "restart_needed": false,
 "browsers": [{"family": "firefox", "variant": "native", "root": "~/.mozilla/firefox",
               "running": false, "restart_needed": false,
               "profiles": [{"id": "...", "name": "default-release", "default": true,
                             "running": false, "restart_needed": false, "applied": true, ...}]}],
 "warnings": []}
```

The **IPC** call answers with the last status the plugin has, and asks for a fresh one. The **script** reads everything now. The status JSON holds paths and profile names, so do not paste it in public as is.

**The anonymous report** is made for bug reports. Get it with **Copy report**, with `dms ipc call browserGlass report` (both copy it to the clipboard), or in a terminal:

```sh
python3 -I ~/.config/dms/plugins/browserGlass/browserglass.py report
```

```text
browserGlass report
version: 1.0.0
python: 3.12.4
dms: 2.0.0
browsers: firefox native 128.0
glass: active (reason active, opacity 0.85, source dms, mode dark)
niri: config yes, include yes, rule yes
restart needed: no
applied: 1 of 1 profiles
profiles:
  firefox native: 1 (0 running, 0 restart needed)
settings: glassEnabled=true opacityOverride=false siteTheme=follow pagesTransparent=true genericStyle=true excluded=0 disabledStyles=0 newTabGlass=true readerOpaque=true privateGlass=true
warnings: none
```

It holds versions, counts, your settings (lists as counts only) and warning codes: no path, no profile name, no site, no address. It is never sent anywhere; you paste it yourself.

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

The first time Browser Glass changes a profile, it saves the originals of `userChrome.css`, `userContent.css` and `user.js` (or notes that they did not exist), with the original values of its three preferences, in `~/.local/state/dms/browserGlass/backup/<profile>/`. The folder name is a short hash of the profile path, not the profile name. It never takes a second backup over the first one.

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
| Switch **Glass** off (widget, settings, `dms ipc call browserGlass toggle`) | The style files turn neutral and the browsers follow the DMS window opacity again after a restart. Everything stays installed, ready to turn back on |
| Disable the plugin in **Settings → Plugins** | Full uninstall: everything restored (toast *Browser Glass disabled: restoring the browsers*) |
| Delete the plugin folder while DMS runs | The same full uninstall, started on its own |

## Uninstalling

**Disable the plugin** in **Settings → Plugins**. That is all: Browser Glass shows *Browser Glass disabled: restoring the browsers* and runs its uninstall. The browsers can stay open. Then delete `~/.config/dms/plugins/browserGlass` if you want.

The uninstall:

1. removes the two style files and the `@import` lines, and the `chrome/` folder if Browser Glass created it;
2. removes the marked block from `user.js`, or the whole file if it created it;
3. restores the files you did not edit from their [backups](#backups), byte for byte;
4. removes the niri file and the `include` line;
5. puts the original preference values back in `prefs.js` (see below);
6. removes its state folder and the old v0 cache.

**`prefs.js` and running browsers.** A running browser rewrites `prefs.js` when it closes, so Browser Glass cannot fix it while the browser is open. For each running profile, it starts a small background clean-up that checks every 5 s whether the browser has closed, and then restores the original preference values. The job is written down in `~/.local/state/dms/browserGlass/pending/` first, so it survives a crash or a logout. If the browser stays open for more than **7 days**, the clean-up gives up and leaves its note in `pending/`: run the uninstall command below once the browser is closed, and it finishes the job.

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

**Why does every change need a browser restart?**
Firefox reads `userChrome.css`, `userContent.css` and `user.js` only at start-up. Browser Glass writes the change at once and tells you which browser to restart.

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
No. It makes no network request at all; the site styles ship with it.

## For developers

After changing a QML file or `components/logic.js`, run `dms restart`: `dms ipc call plugins reload browserGlass` reloads the plugin but keeps its components cached, and a new root QML file is only picked up by a restart. Architecture, tests and the release process are in [CONTRIBUTING.md](../CONTRIBUTING.md).

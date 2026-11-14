# Spike: special-page CSS on Firefox 160.0 (Marionette, headless)

Harness: `tests/e2e/marionette.py` (`python3 tests/e2e/marionette.py [--dump out.json]`).
3 runs of a throwaway profile (fake HOME/XDG, black-hole proxy, 127.0.0.1 server):
`baseline` (no CSS), `glass` (generic + reader glass + newtab glass), `opaque`
(generic + my-internet-like generic + PDF opaque + private opaque + plan's original newtab rule).
Result: **24/24 checks passed** (1 informational row).

| Area | Result | Verified |
|---|---|---|
| (a) generic web page | ✅ | `regexp("https?://.*")` → html+body `rgba(0,0,0,0)` (baseline white) |
| (b) private window attr | ✅ | private window: `privatebrowsingmode="temporary"` (isWindowPrivate=true); normal window: attribute **absent** (null) |
| (b) private opaque rule | ✅ | private body `rgb(16,20,24)`, normal stays `rgba(16,20,24,0.8)`; without the rule both 0.8 |
| (c) reader: generic does not apply | ✅ | about:reader body stays `rgb(28,27,34)` with the generic rule present → opaque needs no CSS |
| (c) reader glass | ✅ | html+body transparent, `--main-background` = transparent |
| (d) PDF URL / ids / var | ✅ | `document.URL` = the PDF URL, contentType application/pdf; `#outerContainer`, `#viewerContainer`, `body:has(> #outerContainer #viewerContainer)` match; `--body-bg-color` on :root = `light-dark(#e3e2e7, #131215)` |
| (d) generic hits pdf.js | ✅ | body transparent with generic only |
| (d) opaque after generic wins | ✅ | body back to baseline `rgb(19,18,21)`, also over a my-internet-style `background: none !important` generic |
| (e) about:newtab / about:home | ✅ | plan rule works: html+body transparent, img none, `--newtab-background-color: transparent` |
| (e) about:privatebrowsing (plan rule) | ❌ | body-only rule leaves **html** opaque `rgb(19,18,21)` (page paints on `<html>`) |
| (e) about:privatebrowsing (fixed rule) | ✅ | `:root, body` → transparent, in a normal and in a private window |
| (e) newtab wallpaper | ✅ | feature exists on 160 (`newtabWallpapers.enabled=true`); painted as body `background-image: var(--newtab-wallpaper), linear-gradient(var(--newtab-wallpaper-color)…)`; simulated wallpaper is reset to `none` by the shorthand `background: transparent !important`; no separate wallpaper element |
| (f) Snap app-id `firefox_firefox` | not verifiable | snapd not installed (no /snap, /var/lib/snapd, no `snap`); libxul only shows SNAP_NAME/SNAP_INSTANCE_NAME strings, not the app-id → **exclude** |

## Verified CSS

userChrome (glass active, v0 rule, works):
```css
body { background: rgba(R, G, B, OPACITY) !important; }
:root, #main-window, #browser, #appcontent, #navigator-toolbox,
#TabsToolbar, #nav-bar, #PersonalToolbar,
#tabbrowser-tabbox, #tabbrowser-tabpanels,
.browserContainer, .browserStack, browser { background: transparent !important; border: none !important; }
```
userChrome, `privateGlass=false` (append after the above):
```css
:root[privatebrowsingmode="temporary"] body { background: rgba(R, G, B, 1) !important; }
```
userContent generic (v0):
```css
@-moz-document regexp("https?://.*") { html, body { background: transparent !important; } }
```
userContent, `readerOpaque=false` (reader in glass):
```css
@-moz-document url-prefix("about:reader") {
  :root, body { background: transparent !important; }
  body { --main-background: transparent !important; }
}
```
(`--main-background` is set on `body` / `body.dark|.sepia|.gray|.contrast|.custom`, not `:root`.
`.toolbar` has no background of its own on 160, only border + shadow, so a `.toolbar` rule changes nothing. Drop it or keep it as a harmless guard. Popups use `--popup-background` and stay opaque.)

userContent, `readerOpaque=true` → reader needs nothing. PDF: place **after** the generic block (a bare rule, no @-moz-document):
```css
body:has(> #outerContainer #viewerContainer) { background-color: var(--body-bg-color) !important; }
```
userContent, `newTabGlass=true` (**corrected**, the plan's body-only version fails on about:privatebrowsing):
```css
@-moz-document url("about:newtab"), url("about:home"), url("about:privatebrowsing") {
  :root { --newtab-background-color: transparent !important; }
  :root, body { background: transparent !important; }
}
```

## Fallbacks (not measured on their own)
- Private: none needed. If `privatebrowsingmode` ever changes, the harness's chrome check shows it (it reads `PrivateBrowsingUtils.isWindowPrivate`).
- Reader: if the `--main-background` name changes, `:root, body { background: transparent !important }` alone still wins, because user `!important` beats the author rule.
- PDF: if `:has()` or the ids change, use `#outerContainer { background-color: var(--body-bg-color) !important }`. Note that `#outerContainer` does not cover the canvas.
- New tab: `background` shorthand covers the wallpaper. If a future wallpaper element appears, add `.wallpaper-* { display: none }`.

## Harness findings (for P2/P9)
- Firefox 160 refuses chrome context unless the env has `MOZ_REMOTE_ALLOW_SYSTEM_ACCESS=1`. The `-remote-allow-system-access` flag is passed too.
- `WebDriver:Navigate` refuses `about:reader?...` ("not allowed in this context"). `Browser.navigate` falls back to a chrome-side `gBrowser.selectedBrowser.fixupAndLoadURIString(url, {triggeringPrincipal: system})`.
- Fedora's `firefox-redhat-default-prefs.js` sets a remote homepage. The user.js forces about:blank and uses a black-hole proxy to 127.0.0.1:9; localhost is not proxied. Checked: example.com gives proxyConnectFailure, and no external host appears in the log.
- Reader mode's Narrate spawns speech-dispatcher, which leaves Firefox's process group: the user.js disables `narrate.enabled` and `media.webspeech.synth.enabled`, and cleanup also kills any process whose command line names the throwaway directory.
- Firefox's environment is built from scratch (fake HOME/XDG_*/TMPDIR, PATH without entries in the real home) and checked for real-home paths before launch. Firefox is killed and its directory removed on normal exit, Ctrl-C, SIGTERM and SIGHUP.
- `/usr/bin/firefox` is the Fedora bash wrapper: it runs restorecon on `$MOZ_CONFIG_DIR` and mkdirs under `$HOME`. The harness uses `/usr/lib64/firefox/firefox` directly; `BG_FIREFOX` overrides the binary (exit 2 when it is not an executable).

## Not covered yet
- Light mode (`layout.css.prefers-color-scheme.content-override=1`) for reader and PDF; the runs used dark mode only.
- A real new-tab wallpaper chosen by the user (the spike simulates one with inline custom properties).
- The reader and PDF fallbacks above, measured alone.

# Changelog

All notable changes to Browser Glass are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Dark pages** (*Sites*, on by default, with *Live control*): under a dark theme, the companion add-on turns light pages dark with the bundled [Dark Reader](https://darkreader.org) engine (v4.9.135, MIT, `extension/vendor/`) in the DMS colours, and their background becomes glass, the large elements that paint it included (marked `data-browserglass-canvas`). Pages with a dark version, excluded sites and a light theme are left alone. Off, a light page gets the light glass as before.
- **Page layers** (with *Live control*): the companion add-on makes the lowest layer that paints a page's background glass (a fixed full-window container, as in Jellyfin; marked `data-browserglass-canvas`) when the root and body are see-through already (looked for again after a click or a late render, as in TrueNAS), and gives every navigation bar fixed or stuck along a window edge (a header, a bottom bar, a sidebar) the same look on every site, close to the browser's own toolbar: a light veil of the DMS surface (35 %, over the page's tint) and a strong blur, so what scrolls under it stays unreadable (`data-browserglass-bar`).

### Fixed

- **Background images** on sites with the generic style (the photo behind a banner, as on a WordPress hero `<section>`) are no longer removed: the generic style now clears background colours only.
- **Pages with a dark version** (YouTube and other sites marked dark on `<html>`) never get the light glass, even when the companion measured them before their text appeared; the companion also measures again as a single-page app renders, and reads the colour of the visible text rather than the body's.

### Changed

- **Thicker tone glass**: the glass of a light page under a dark theme (and of a dark page under a light theme) is the DMS surface at 88 % instead of 72 %, so dark text stays crisp over a dark wallpaper instead of sitting on a grey veil.

## [1.1.0] - 2026-11-15

### Changed

- **Live light/dark switch**: the browser tint holds both DMS surfaces and follows the browser's light or dark theme, and *Follow DMS* now writes `content-override = 2` (automatic), so websites follow too. Switching DMS between light and dark no longer needs a browser restart, as long as DMS's *Sync with portal* is on (the settings page says so when it is off).
- **Preferences**: with *Live control* on, the `user.js` block also holds `xpinstall.signatures.required = false` and the profile bit of `extensions.autoDisableScopes` and `extensions.startupScanScopes`, derived from each profile's own values. Their originals are recorded and restored like the other preferences, and the block and its hash are now computed per profile.
- **Gated page CSS**: with *Live control* on, every `http(s)` rule of `dms-glass-content.css` applies only while the page's `<html>` does not carry `data-browserglass-off` (except inside shadow trees, which cannot see it), so the companion can switch it off on an excluded page, and a new section brings the glass back to a site excluded at sync time on pages carrying `data-browserglass-live`, once it is put back. Without the add-on neither mark is set and pages look as before. The gating makes the page stylesheet about 1.9 MB on the bundled styles, against 1.6 MB with *Live control* off, and Firefox 160 parses it in about 23 ms instead of 18. With *Live control* off, none of this gating is written (the page stylesheet differs from v1.0 only by the colour-scheme change under *Fixed*).
- **No restart for a live exclusion**: when the only change is the list of excluded sites and a running browser's companion confirmed it applied the new list, `status` no longer asks that browser for a restart.

### Added

- **Launcher commands**: type `glass` or `gs` in the DMS launcher. `on` and `off` switch the glass, `blist` (alias `fix`) excludes the site open in the browser in front, its whole registrable domain (`account.example.org` -> `example.org`), `unblist` puts it back, and `list` shows the excluded sites (Enter removes one; past ten, the first nine and how many more, narrowed with `gs list <filter>`). The plugin's own view in the launcher (its *Browse* entry) takes the bare words too, and lists the commands when empty. A short toast confirms each action, and says *applies after a restart* when it could not apply at once. New root file `BrowserGlassLauncher.qml`, with its logic in `components/launcher.js`; `plugin.json` gains the `launcher` component and capability.
- **Live control** (*Advanced & help*, on by default): exclusions from the launcher apply to the open pages at once, without a browser restart, through a small companion add-on (`extension/`, `browserglass@companion`) placed in each profile and a native messaging host (`browserglass.py native-host`) that the browser starts. Not available on Firefox release, ESR and Beta builds (they refuse unsigned add-ons), nor on Flatpak and Snap browsers: there, changes apply at the next restart. The *Status* section shows its state, *Files written* lists its files; uninstalling removes the add-on, its preferences, the native manifest and the helper's files.
- **Light pages under a dark theme, with Live control**: the companion measures the page's text colour (in the page, nothing is sent) and marks `<html>` with `data-browserglass-tone`, and the glass follows the page, light glass (the DMS light surface at 72 %) on a light page under a dark theme and dark glass on a dark page under a light theme, for the generic and the dedicated styles alike. It measures again on load, when the page switches its theme on `<html>` and when the colour scheme changes.
- **`active-site --json`**: a new backend command that tells which site a browser window shows, from the companion or else from the browser's saved session (`recovery.jsonlz4`, read with a built-in LZ4 decoder). Its output is in the CLI contract.
- **IPC**: `dms ipc call browserGlass excludeCurrent`, `includeCurrent` and `glass "<command>"` (`on`, `off`, `blist`, `fix`, `unblist`, `list`), for keybindings, on the same path as the launcher and with the same toasts.
- **Status**: a `companion` entry in `status --json` (`enabled`, `state`, `hosts`, `manifest`, and a state per profile), the *Live control* line in the *Status* section and a `companion:` line in the anonymous report; `sync` reports how many browsers received and confirmed a live change.
- **Continuous integration**: the *Tests* workflow (`.github/workflows/tests.yml`) runs the Python tests, the bundled data check and the translation check on every pull request and push to `main`.
- **Site fixes** in `data/sites/`: one CSS file per website, added at the end of its my-internet style (or a new style), with `--browserglass-bar` (the DMS surface at 80 %) for the parts that float over the page. CONTRIBUTING.md explains how to send one.
- **Public Suffix List** in `data/public_suffix_list.dat` (Mozilla, MPL-2.0, see `data/PSL-LICENSE`): the bundled copy that reduces a page host to the site it belongs to (`account.example.org` -> `example.org`), with no network. `tools/update_styles.py` refreshes it, dropping the lines that hold a word of `tools/style-denylist.txt`, and `--check` verifies the bundled copy.
- **Pull request template check**: a pull request keeps the template's sections and shows at least one image of the render; the *PR template* workflow checks it (`tools/check_pr_body.py`), and CONTRIBUTING.md has a "Pull requests" section.

### Fixed

- **Companion removed in about:addons**: an add-on you removed in the browser is no longer taken for a signing refusal (`signing_required`) and placed again, enabled without a prompt, after the next browser update. The profile turns `removed_by_user` (the *Live control* line says the add-on was removed), its preferences are taken back, and nothing is placed until Live control is turned off and on again. LibreWolf, Firefox Nightly and Developer Edition never delete the add-on themselves, so a removal there is always the user's. On other browsers it is told apart once Browser Glass has seen the add-on loaded: the daemon syncs once when a status finds a pending add-on loaded. Turning Live control off or on now syncs at once, so off then on quickly still clears the mark.
- **Excluded sites out of the process list**: the daemon passes the sync settings in a file of `$XDG_RUNTIME_DIR` (`sync --settings-file FILE`, read then deleted) instead of the `--settings` argument, which every local user could read in `/proc/PID/cmdline`. `--settings JSON` still works.
- **Unreadable text**: white toolbar text on the light tint (the tint now follows the browser theme the text colours come from), and dark text on the dark tint on light-only websites: under a dark theme the generic page rule, the generic site style and now every dedicated site style (my-internet's and `data/sites/`) only apply to pages that declare a dark version, so a light-only page with a dedicated style keeps its own, readable background. Each site style is now written once per colour scheme: the page stylesheet grows from about 0.6 MB to 1.6 MB, and takes about 12 ms more to parse when the browser starts.
- **YouTube**: the header, the category chips and the overlay side menu get the glass tint at 80 % with a blur, instead of putting their text straight over the videos.
- **Proton Mail**: messages show on a light card with a light colour scheme, so text the email leaves unstyled is no longer white on the email's own white boxes.
- **Proton Calendar**: the sidebar, top bar and grid let the glass through instead of painting the theme's solid black; the sticky day headings get the glass tint.
- **Uninstall while a browser runs**: the background `prefs.js` clean-up now survives the logout or shutdown that closes the browser (it keeps checking for a few seconds), the add-on's scope preferences get a value back instead of being deleted after a lost `state.json`, and the folders made for the state folder are removed even after a lost `state.json` or a second uninstall.
- **Disabling during a sync**: a sync the plugin started just before it was disabled could take the state lock after the uninstall and write the glass, `user.js`, the companion add-on and the native manifest back, leaving the browsers glassy with the plugin off. `sync --if-plugin` now also refuses, writing nothing, when DMS's `plugin_settings.json` has the plugin disabled, checked under the state lock.

## [1.0.0] - 2026-11-14

First public release: a rewrite of the earlier, unpublished v0 scripts (a bash `browser-glass-sync` that needed jq and awk, a Python `browser-glass-sites` that downloaded the site styles, and a daemon-only plugin). Settings, excluded sites and the files v0 wrote are taken over on the first sync.

### Added

- **One backend, `browserglass.py`**: a single Python file, standard library only (Python 3.9 or later), run as `python3 -I`. Its commands are `sync`, `status --json`, `uninstall`, `report` and `sites --json`, plus the internal `clean-prefs`. `sync`, `status --json`, `uninstall` and `sites --json` each print one JSON line, `report` prints the anonymous plain-text report and the internal `clean-prefs` prints nothing (the contract is frozen in `tests/fixtures/contract/schema.json`). A second identical sync writes nothing.
- **A composite DMS plugin**: a daemon, a DankBar widget and a settings page (`plugin.json` type `composite`).
  - The daemon syncs when the plugin settings, DMS blur, the light or dark mode, DMS's window rules or DMS's colours change. Syncs are debounced and run one at a time, with no timer.
  - The bar widget is an icon only: `blur_on` while the glass is on, `blur_off` when it is off, and a dot while a running browser must restart. Its menu shows the detailed status and has a glass switch (it turns the glass off; it does not uninstall), *Exclude copied URL* and *Open settings*.
  - The settings page has four sections: *Status*, *Appearance*, *Sites* and *Advanced & help*.
  - Toasts for errors, for a restart that is needed (only when a running browser's files changed), for the first run and for the uninstall.
  - `dms ipc call browserGlass sync | status | toggle | excludeClipboard | report` for keybindings and scripts.
- **Opacity in step with DMS**: by default the glass takes the opacity of DMS's first global window rule, and the tint follows DMS's surface colour. An optional override (a switch and a slider) sets the browser's own opacity. The glass needs DMS blur on and an opacity below 1. Otherwise it turns itself off, and the browser follows DMS's global rule again.
- **Site theme**: *Follow DMS* (dark or light), *Always dark* or *Leave as is*. *Leave as is* puts back the browser's own colour-scheme setting.
- **Special pages**: the new tab page, the home page and the private browsing page are glass. Reader view and PDFs stay opaque by default, and private windows are glass by default. Reader view and PDF share one switch, and the new tab page and private windows each have their own. The selectors were checked in a real headless Firefox.
- **Site styles**: about 650 dedicated styles from [sameerasw/my-internet](https://github.com/sameerasw/my-internet) (MIT), bundled in `data/`. Each one can be turned off from a searchable list. A generic style covers the other sites and has its own switch.
- **Per-site exclusions**: a list of domains that keep their own background, and *Exclude copied URL*, which adds the domain of the URL on the clipboard.
- **Status and report**: the *Status* section and the widget menu show whether the glass is on and, if not, why. They also show the opacity and its source, the tint, the niri rule, the browsers and profiles found, a pending restart and the warnings. *Copy report* copies an anonymous text: versions, profile counts per browser and install type, the state and the warnings. The report has no path, no profile name or id and no URL.
- **Browsers**: Firefox, LibreWolf, Zen, Floorp and Waterfox, installed natively, as a Flatpak or as a Snap. Profiles come from `profiles.ini` and from the new profile manager's profile groups. A running browser is detected from the lock on its profile, without touching it.
- **Zen**: a warning when a Zen transparency mod or transparency pref is found. Nothing is changed on Zen's side.
- **Automatic v0 migration**: the v0 `@import` lines and `user.js` block are removed before the one-time backup is taken. The v0 cache (`~/.cache/dms/browserGlass/`) is deleted, and the v0 settings (`pagesTransparent`, `excludedSites`) are kept. The pref values v0 wrote are recognised as the plugin's own. A sync over a v0 install leaves no duplicate.
- **Byte-for-byte uninstall**: disabling the plugin removes everything it wrote. `userChrome.css`, `userContent.css` and `user.js` come back from a backup taken before the first write, with their modes and symlink targets. Each pref gets its original value back instead of being deleted. The niri include file and its line in `config.kdl` go, and so do the state folder and the v0 cache. When a browser is running, a detached cleaner waits for it to close and then cleans `prefs.js`.
- **Sweep**: deleting the plugin folder also uninstalls. The uninstaller runs from the script text held in memory, so no file needs to remain. It waits 4 s and stops if the plugin comes back (an update or a reinstall). Only after that does it remove the plugin's entry from DMS's plugin settings.
- **French translation** (`translations/fr.json`) of every visible string, checked by `tools/check_translations.py`.
- **Tests**: 502 Python tests on a fake home, 7 offscreen QML test files on DMS stand-ins, and an opt-in end-to-end test in a throwaway headless Firefox.
- **Repository tooling**: `tools/update_styles.py` and a weekly GitHub Action that refreshes the bundled styles from my-internet and opens a pull request. There are issue and pull request templates, and `tools/media/` builds the screenshots from made-up data.

### Changed

- **No runtime dependency other than Python 3**: jq, awk and the bash script are gone.
- **No network at runtime**: v0 downloaded the my-internet styles every 6 hours. They are now bundled in `data/` and refreshed by a pull request.
- **No idle work**: v0 ran a 6-hour timer. The daemon now runs nothing until something changes, and it checks the status every 10 s only while a browser must restart.
- **Glass on and off without a double tint**: the niri rule that keeps the browser window opaque stays until no running browser still has the glass CSS loaded. Only then is it removed.
- **Safer file writes**: writes are atomic, keep each file's permissions, follow symlinks to their targets, skip read-only files with a warning and never write a file whose content is unchanged.
- The plugin needs DMS 2.0 or later. It declares the `process` permission, and its code and description are now in English.

### Removed

- `browser-glass-sync` and `browser-glass-sites`, replaced by `browserglass.py`.

[Unreleased]: https://github.com/lung595/browserGlass/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/lung595/browserGlass/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/lung595/browserGlass/releases/tag/v1.0.0

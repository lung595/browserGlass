# Changelog

All notable changes to Browser Glass are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/lung595/browserGlass/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/lung595/browserGlass/releases/tag/v1.0.0

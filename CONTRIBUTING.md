# Contributing

This file has what you need to work on Browser Glass or to take over the project.

## Contents

- [Development setup](#development-setup)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Screenshots](#screenshots)
- [Performance rules](#performance-rules)
- [Conventions](#conventions)
- [Releasing a version](#releasing-a-version)

## Development setup

1. Clone the repository into the DMS plugin folder, then enable the plugin in **Settings → Plugins**:

   ```sh
   git clone https://github.com/lung595/browserGlass ~/.config/dms/plugins/browserGlass
   ```

2. Add the widget to a bar to see the status at a glance.
3. DMS reloads the plugin's root QML files, but it keeps `components/` and `.js` files (`components/logic.js` in particular) cached in the running shell. **Run `dms restart`** after you change them, and also after you add a new root QML file: until the shell restarts, DMS fails to load the new file with "File name case mismatch".
4. To try the backend by hand, run it the way the daemon does: `python3 -I browserglass.py status --json`. It writes only to the places listed in [Architecture](#architecture). Point `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` at a scratch folder to keep your real profiles out of it.

Tools: Python 3.9 or later, Qt 6's `qml` and `qmllint` tools (QML tests), Firefox (the opt-in end-to-end tests), and ffmpeg (screenshots).

## Architecture

`plugin.json` declares a **composite** plugin with two components and a settings page:

| Component | File | Role |
| --- | --- | --- |
| Daemon | `BrowserGlassDaemon.qml` | One instance per shell. It runs `browserglass.py sync` when the plugin data, `SettingsData.blurEnabled` or `SessionData.isLightMode` change, or when a `FileView` sees DMS's `niri/dms/windowrules.kdl` or `dms-colors.json` change. Syncs are debounced by 800 ms and run one at a time through `Proc.runCommand`. The daemon shares the outcome through `PluginGlobalVar`, shows toasts, and serves `IpcHandler { target: "browserGlass" }` (`sync`, `status`, `toggle`, `excludeClipboard`, `report`). When the plugin is disabled (`enabled === false` at destruction), it runs `uninstall`. |
| Logic | `components/logic.js` | Pure functions with no QML object and no I/O. They build the argv lists and the `--settings` JSON, parse `status`, run the debounce bookkeeping, choose the toasts, and hold the reason and warning texts. The QML tests import it directly. |
| Uninstall sweep | `components/UninstallSweep.qml`, `components/keeper.js`, `components/SweepProcess.qml` | When the plugin folder is deleted, the sweep runs `python3 -I -c STDIN_BOOTSTRAP uninstall --if-gone <plugin.json>` and writes the script text it read at load onto the process's stdin. It removes the plugin's entry from `plugin_settings.json` only after the process exits. `keeper.js` creates the process outside the plugin's QML context, so the process outlives the plugin. |
| Bar widget | `BrowserGlassWidget.qml`, `components/WidgetPill.qml`, `components/GlassPopout.qml` | The pill shows `blur_on` or `blur_off`, plus a dot while a restart is needed. The popout shows the status and has the glass switch (pluginData `glassEnabled`), *Exclude copied URL* and *Open settings*. |
| Settings | `BrowserGlassSettings.qml`, `components/SettingsHeader.qml`, `components/StatusBlock.qml`, `components/SiteList.qml` | Four sections: Status, Appearance, Sites, and Advanced & help. `SiteList` is a filtered `ListView` over the cached `sites --json` output, so only the visible rows exist. |
| Backend | `browserglass.py` | A single file, standard library only. Its sections, in order: `consts` (v0 markers copied byte for byte, prefs, profile roots, niri app-ids), `fsio`, `discover`, `lockprobe`, `inputs`, `settings`, `render`, `sites`, `edits`, `state`, then `cmd_*` and `main`. The output contract is `tests/fixtures/contract/schema.json`. |
| Data | `data/styles.json`, `data/css-mapping.json`, `data/MY-INTERNET-LICENSE` | The bundled my-internet styles, read through `--data`. Nothing is downloaded at run time. |

**What the backend writes.** Outside the plugin folder it writes only these:

- in each profile: `chrome/dms-glass-chrome.css`, `chrome/dms-glass-content.css`, one `@import` line in `userChrome.css` and one in `userContent.css`, a marked block in `user.js`, and the clean-up of `prefs.js`;
- `~/.config/niri/dms-browser-glass.kdl` and its `include` line in `config.kdl`;
- `$XDG_STATE_HOME/dms/browserGlass/`: `state.json`, `state.lock`, `backup/<profile hash>/` and `pending/`.

It never writes DMS's own `niri/dms/windowrules.kdl` or `~/.config/dms/firefox.css`. `uninstall` removes all of this, plus the v0 cache `~/.cache/dms/browserGlass/`.

**Running browsers.** Firefox holds a POSIX record lock on `.parentlock` for as long as it runs, and `lockprobe` asks the kernel about it with `F_GETLK`. It opens the file read-only, never creates it and never takes a lock of its own. Glass CSS reaches a running browser only after a restart. The niri rule therefore stays while a running profile still has the glass loaded, `status` reports `restart_needed`, and the daemon polls `status` until a restart clears it.

**Uninstall without files.** The script never looks up its own location (no `__file__`), so it can run from its text alone. The text goes on stdin of `python3 -I -c "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))" uninstall` because it is larger than the 128 KiB Linux allows for one argv string. When the browser is running, `prefs.js` is cleaned by a detached process (`fork` and `setsid`) that waits for the browser to close.

## Project layout

```
browserGlass/
├── plugin.json                  # composite: daemon + widget + settings
├── BrowserGlassDaemon.qml       # sync triggers, status, toasts, IPC, uninstall
├── BrowserGlassWidget.qml       # DankBar pill + popout
├── BrowserGlassSettings.qml     # settings page, four sections
├── browserglass.py              # the backend (single file, stdlib only)
├── components/
│   ├── logic.js                 # pure daemon logic (argv, settings JSON, status, toasts)
│   ├── keeper.js                # creates the sweep process outside the plugin's context
│   ├── UninstallSweep.qml       # uninstall when the plugin folder is deleted
│   ├── SweepProcess.qml         # the sweep's Process
│   ├── StatusBlock.qml          # status (settings page and popout)
│   ├── SiteList.qml             # searchable site styles
│   ├── SettingsHeader.qml       # section title
│   ├── WidgetPill.qml           # bar icon + restart dot
│   └── GlassPopout.qml          # widget menu
├── data/                        # styles.json, css-mapping.json, MY-INTERNET-LICENSE
├── translations/fr.json         # French catalog
├── tests/
│   ├── py/                      # unittest suite, fakehome.py, fixtures/, golden/
│   ├── qml/                     # run.sh, Harness.qml, *.test.qml, stubs/ (Quickshell + qs.*)
│   ├── e2e/                     # marionette.py, test_e2e_glass.py, SPIKE.md, README.md
│   └── fixtures/                # contract/ (CLI output schema + samples), v0/ (v0 scripts)
├── tools/
│   ├── check_translations.py    # every visible string has a French entry
│   ├── update_styles.py         # refreshes data/ from my-internet (CI and by hand)
│   ├── style-denylist.txt       # sha256 denylist of upstream styles and words
│   └── media/                   # gen_wallpaper.sh, capture.sh, compose.sh, restore.sh, demo/, demo-settings.json
├── .github/                     # workflows/update-styles.yml, issue and PR templates
├── screenshots/                 # README media (made-up data only)
├── docs/GUIDE.md                # user guide
├── README.md
├── CHANGELOG.md
├── ROADMAP.md
├── CONTRIBUTING.md
└── LICENSE
```

## Tests

Run these from the plugin root:

```sh
python3 -B -m unittest discover -s tests/py -v      # backend: fake home, v0 round trip, contract, leaks
sh tests/qml/run.sh                                 # QML offscreen on DMS stand-ins; one file: sh tests/qml/run.sh daemon
qmllint-qt6 -I tests/qml/stubs *.qml components/*.qml   # no warning expected (qmllint on some systems)
python3 tools/check_translations.py                 # every visible string is in translations/fr.json
```

These tests are opt-in and need a Firefox binary (`BG_FIREFOX=/path/to/firefox` picks one). Each takes about 20 s:

```sh
BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e*.py'   # sync, Firefox's real pages, uninstall
python3 tests/e2e/marionette.py                                           # the CSS selector spike (SPIKE.md)
```

The tests never touch the real home. `tests/py/fakehome.py` builds a throwaway `HOME` with generated profiles and gives every subprocess its own environment. The QML runner works in a temporary copy, and the end-to-end tests start Firefox with an environment built from scratch, a black-hole proxy and a 127.0.0.1 page server. `tests/py/test_leaks.py` fails when any repository file names a user or a home folder, or one of the real profile ids listed in `BG_LEAK_PROFILE_IDS` (comma-separated; the test is skipped without it). `tests/e2e/README.md` describes the end-to-end checks.

Run them all before every commit. A change to a command's output needs its fixture in `tests/fixtures/contract/` and its spec in `schema.json`.

## Screenshots

The README media come from a throwaway profile, a generated wallpaper and a local demo page. Real profiles never appear. Each script under `tools/media/` explains its usage in its header:

```sh
export MEDIA_DIR="$(mktemp -d)"                     # throwaway folder for everything below
sh tools/media/capture.sh save-state                # record the live session for restore.sh
sh tools/media/restore.sh --dry-run "$MEDIA_DIR/state.env"
sh tools/media/gen_wallpaper.sh "$MEDIA_DIR/wallpapers"   # 3840x2160 ocean, sunset, forest (ffmpeg)
sh tools/media/capture.sh clip                      # fallback video for the demo page
sh tools/media/capture.sh profile                   # throwaway Firefox profile
sh tools/media/capture.sh serve 8765 &              # demo page on 127.0.0.1
MEDIA_SETTINGS=tools/media/demo-settings.json \
  sh tools/media/capture.sh take hero-after - http://localhost:8765/   # sync, restart, place, shoot
sh tools/media/compose.sh "$MEDIA_DIR/shots" "$MEDIA_DIR/wallpapers/wallpaper-ocean.png" screenshots
sh tools/media/restore.sh "$MEDIA_DIR/state.env"    # wallpaper, mode, blur, rules, focus back
```

The full shot list (hero, colours, light and dark, opacities, sites, settings and widget) is in the header of `capture.sh`. `tools/media/demo-settings.json` holds the plugin settings for the run. `take` and `shot` work on the live niri session: set up an empty workspace and turn on *Do not disturb* first. `restore.sh` undoes every step. Check every image and frame for personal data before you commit.

## Performance rules

Browser Glass must cost nothing while nothing changes:

- **No idle process and no idle timer.** The daemon reacts to signals and file watches only. The one exception is the `status` poll every 10 s while a restart is needed, and it stops when the restart is done or after three failures.
- **A sync is cheap**: about 0.1 s of CPU (`/usr/bin/time -v python3 -I browserglass.py sync …`). A sync that changes nothing writes nothing.
- **One sync at a time.** Changes are debounced (800 ms), and a sync that is asked for while another runs waits for it.
- **The script goes through stdin, never argv**, for the file-less uninstall: Linux caps one argv string at 128 KiB (`MAX_ARG_STRLEN`), and `browserglass.py` is larger than that.
- **No network**, ever, at run time.

## Conventions

- **Python**: standard library only, Python 3.9 syntax and APIs (`ast.parse(source, feature_version=(3, 9))` must pass). The script runs as `python3 -I` and never looks up its own location (no `__file__`).
- **Language**: code, comments, identifiers and source strings are in English.
- **Translations**: each visible string goes through `I18n.trFor("browserGlass", "…")` and has an entry in `translations/fr.json` (`{"term": {"term": "translation"}}`). `tools/check_translations.py` checks that.
- **QML**: use DMS 2 widgets (`qs.DCommon.Widgets`), not the deprecated `Dank*` ones (`tests/qml/run.sh` rejects them). A new file goes into `components/`. After you change a QML file or `logic.js`, run `dms restart` to see it live.
- **Privacy**: no telemetry, no network, and no file written outside the paths in [Architecture](#architecture). Tests, fixtures and media use made-up data only.
- **Docs**: user-facing changes go in `docs/GUIDE.md`, and in the README if they change installation or the basics. Every change also gets an entry in `CHANGELOG.md`.

## Releasing a version

1. Bump `version` in `plugin.json` ([Semantic Versioning](https://semver.org/)), together with `VERSION` in `browserglass.py` `version` in `tests/fixtures/contract/status.json` and the `version:` line of `tests/fixtures/contract/report.txt`. `tests/py/test_contract.py` checks that the last two agree. Nothing checks `plugin.json` against them, so compare it by eye.
2. Move the `Unreleased` entries of `CHANGELOG.md` under the new version and date, and add its link at the bottom.
3. Refresh the screenshots if the look changed (see [Screenshots](#screenshots)).
4. Run every test, commit, then tag and publish:

   ```sh
   git tag v1.0.1 && git push origin main v1.0.1
   gh release create v1.0.1 --title v1.0.1 --notes-file <release notes taken from CHANGELOG.md>
   ```

**Site styles.** `.github/workflows/update-styles.yml` runs every week and can also be started by hand. It calls `tools/update_styles.py`, which fetches `styles.json`, `css-mapping.json` and the licence from [sameerasw/my-internet](https://github.com/sameerasw/my-internet). The tool drops the styles listed in `tools/style-denylist.txt` (sha256 digests of style names and words, so the list does not spell them) and then checks the result with `--check data`. When the data changed, the workflow opens or updates a pull request. Squash-merge that pull request yourself. To refresh by hand:

```sh
python3 -I -B tools/update_styles.py              # fetch and rewrite data/
python3 -I -B tools/update_styles.py --check data # offline check
```

The repository setting *Allow GitHub Actions to create and approve pull requests* must be on. GitHub turns scheduled workflows off after 60 days without activity in the repository, so re-enable the workflow from the Actions tab when that happens.

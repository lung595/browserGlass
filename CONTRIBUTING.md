# Contributing

This file has what you need to work on Browser Glass or to take over the project.

## Contents

- [Fixing a website](#fixing-a-website)
- [Pull requests](#pull-requests)
- [Development setup](#development-setup)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Screenshots](#screenshots)
- [Performance rules](#performance-rules)
- [Conventions](#conventions)
- [Releasing a version](#releasing-a-version)

## Fixing a website

A website that looks wrong under the glass (unreadable text, a bar over the
content) is fixed with one CSS file in `data/sites/`, named after the site:
`data/sites/youtube.com.css`. [`data/sites/README.md`](data/sites/README.md)
has the rules. To try it:

1. Edit the file in your plugin folder (`~/.config/dms/plugins/browserGlass/data/sites/`).
2. Run `dms ipc call browserGlass sync`, then restart the browser: it reads the CSS at startup only.
3. Run `python3 -B -m unittest discover -s tests/py` and open a pull request with
   before and after screenshots, in dark and light (see [Pull requests](#pull-requests)).

Do not edit `data/styles.json` or `data/css-mapping.json`: a weekly job copies
them from my-internet and would undo the change. Send those fixes
[upstream](https://github.com/sameerasw/my-internet) instead.

## Pull requests

Every pull request follows [the template](.github/pull_request_template.md),
which GitHub fills in when you open one. Keep its sections and fill them in:

- **What does this change?**: one or two sentences, and the issue it fixes.
- **Screenshots**: required, **at least one image of the render**. Drag the
  files into the description. For a site fix: before and after, in dark and
  light. For a settings, widget or launcher change: the new look in DMS. For a
  change with nothing to see (docs, CI, backend): the browser or DMS with the
  change applied.
- **How was it tested?** and the **Checklist**: tick what you did.

Screenshots follow the same rule as the rest of the project: no personal data
(no real tabs, history, home path, user name or profile id).

The *PR template* check (`.github/workflows/pr-template.yml`) fails while a
section is missing or "Screenshots" has no image, and runs again when you edit
the description. Run it locally on a draft with
`python3 -I tools/check_pr_body.py draft.md`.

## Development setup

1. Clone the repository into the DMS plugin folder, then enable the plugin in **Settings → Plugins**:

   ```sh
   git clone https://github.com/lung595/browserGlass ~/.config/dms/plugins/browserGlass
   ```

2. Add the widget to a bar to see the status at a glance.
3. DMS reloads the plugin's root QML files, but it keeps `components/` and `.js` files (`components/logic.js` in particular) cached in the running shell. **Run `dms restart`** after you change them, and also after you add a new root QML file: until the shell restarts, DMS fails to load the new file with "File name case mismatch".
4. To try the backend by hand, run it the way the daemon does: `python3 -I browserglass.py status --json`. It writes only to the places listed in [Architecture](#architecture). Point `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` at a scratch folder to keep your real profiles out of it, and `XDG_RUNTIME_DIR` at a short scratch folder with mode 700 (socket paths are limited to 108 bytes): otherwise a scratch `sync` pushes to the live-control sockets of your running browsers and a scratch `uninstall` removes them. `tests/py/fakehome.py` builds such an environment for the tests.

Tools: Python 3.9 or later, Qt 6's `qml` and `qmllint` tools (QML tests), Firefox (the opt-in end-to-end tests), and ffmpeg (screenshots).

## Architecture

`plugin.json` declares a **composite** plugin with three components (daemon, bar widget, launcher) and a settings page:

| Component | File | Role |
| --- | --- | --- |
| Daemon | `BrowserGlassDaemon.qml` | One instance per shell. It runs `browserglass.py sync` when the plugin data, `SettingsData.blurEnabled` or `SessionData.isLightMode` change, or when a `FileView` sees DMS's `niri/dms/windowrules.kdl` or `dms-colors.json` change. Syncs are debounced by 800 ms and run one at a time through `Proc.runCommand`; a `liveControl` change syncs at once (`Logic.liveControlChanged()`), so off then on quickly is still a sync with it off, the one that lets a profile `removed_by_user` get the add-on again. When a status finds installed a profile the last sync left `pending_restart` (`Logic.companionLoaded()`), it asks for one sync, which records that the browser loaded the add-on (`seen`), so a later removal in `about:addons` is not read as a signing refusal. The settings go in `$XDG_RUNTIME_DIR/browserGlass-sync-settings.json`, which `sync --settings-file` reads and deletes, so the excluded sites never appear in an argv (any local user can read `/proc/PID/cmdline`); without a runtime dir, or when the file cannot be written, they go in `--settings`. Quickshell's `FileView` skips a text equal to the one it last wrote, so `launchSync()` empties the file before each write; `uninstall` removes a file no sync read. `syncDoneSafe()` catches an error of the result handler, which `Proc` would log with the command, and leaves the sync idle. The daemon shares the outcome through `PluginGlobalVar`, shows toasts, and serves `IpcHandler { target: "browserGlass" }` (`sync`, `status`, `toggle`, `excludeClipboard`, `report`, `excludeCurrent`, `includeCurrent`, `glass`). `launcherAction()` runs the launcher's commands: it writes the setting and syncs at once, without the debounce, then shows its toast once the sync says whether the change went live. `glassCommand()` runs one by name, for the IPC. `siteFor()` gives the launcher the current site: it runs `browserglass.py active-site` for the niri window in focus (or the one focused last), one lookup at a time, keeps the answer 3 s and calls `requestLauncherUpdate` when it comes. While a lookup runs, `siteFor(true)` (the launcher's items) gives the last answer for the same window (same id, pid, app-id and title), marked provisional: it is shown, never acted on. On start it saves the launcher setting `noTrigger: true` when it has no value yet, so a user's choice stays. When the plugin is disabled (`enabled === false` at destruction), it runs `uninstall`. Its syncs pass `--if-plugin <plugin.json>`: the script then refuses with a `plugin_gone:` error, before the state lock and again under it, writing nothing, when `plugin.json` is missing or when `$XDG_CONFIG_HOME/dms/plugin_settings.json` has the plugin's `"enabled": false`. DMS writes that value (synchronously) before it destroys the daemon, so a sync started just before the plugin was disabled, and not killed by `Proc.release`, cannot write everything back after the uninstall. If DMS then fails to unload the plugin (*Failed to disable plugin*), the daemon stays with every sync refused, without a toast: enable the plugin again. |
| Logic | `components/logic.js` | Pure functions with no QML object and no I/O. They build the argv lists, the `--settings` JSON and the path of its file (`settingsFilePath()`), parse `status`, run the debounce bookkeeping, choose the toasts, and hold the reason and warning texts. The QML tests import it directly. |
| Uninstall sweep | `components/UninstallSweep.qml`, `components/keeper.js`, `components/SweepProcess.qml` | When the plugin folder is deleted, the sweep runs `python3 -I -c STDIN_BOOTSTRAP uninstall --if-gone <plugin.json>` and writes the script text it read at load onto the process's stdin. It removes the plugin's entry from `plugin_settings.json` only after the process exits. `keeper.js` creates the process outside the plugin's QML context, so the process outlives the plugin. |
| Launcher | `BrowserGlassLauncher.qml`, `components/launcher.js` | The DMS launcher component (`noTrigger`: it answers in the launcher's *all* mode only when the first word of the query is `glass` or `gs`; `"trigger": "glass"` in `plugin.json` is there because the plugin schema asks for one). In the launcher's plugin view (the *Browse* entry of Browser Glass, the Plugins tab) it also takes the bare words and lists the commands for an empty query: DMS gives `getItems` nothing that tells that view from the global search, so `fromPluginView()` reads the call stack (a `performSearch` call of DMS's `Controller.qml`, not its plugin phase), and an unknown stack keeps the prefix rule. DMS shows at most 10 items of a plugin in its global search, so there `list` shows the first 9 and an item that says how many more; the plugin view shows every site. `normDomain()` reads an excluded entry as `browserglass.py` `normalize_domain()` does (scheme, path, port and `*.` dropped, IDNA). `launcher.js` holds the pure part (`parseQuery`, `commandItems`, `listItems`, `planAction`, `toastFor`), tested like `logic.js`; `tests/qml/Controller.qml` calls `getItems` the way DMS does. `getItems` asks the daemon's `siteFor()` for the current site only for `blist` and `unblist` (the *Browse* view's empty query lists them too), and shows *Finding the current site…* until the answer is back, or meanwhile the last answer for the same window, provisional: such an item carries no `bgSite`, so Enter runs it by name and waits for a fresh answer. DMS's *Browse* view with an empty query ignores `requestLauncherUpdate`, so it keeps its first items. `executeItem` hands the item to the daemon's `launcherAction()` or `glassCommand()`. Its `toggle()` forwards to the daemon, for `dms ipc call plugins toggle browserGlass`. |
| Companion | `extension/` (`manifest.json`, `background.js`, `content.js`, `vendor/darkreader.js`), `browserglass.py native-host` | A WebExtension (`browserglass@companion`, no `all_frames`, never in private windows) that the sync places in each profile when `liveControl` is on: the signed `companion/browserglass@companion.xpi` when it matches `extension/`, else the unsigned xpi it zips from `extension/` (see *What the backend writes*). `content.js` sets `data-browserglass-live` and `data-browserglass-off` (and `data-browserglass-tone`) on `<html>` of web pages; when the helper's `darken` flag is true (the `darkPages` setting, sent with the excluded list) and the root carries `--browserglass-darken-bg` and `-fg` (written by the style file under a dark theme: they only give the colours, since a page can set them itself), it first sets the usual dark-theme marks on `<html>` (`NATIVE_CLASSES`, `NATIVE_ATTRS`: those of `_DARK_PAGE_MARKERS`), kept only if the measured tone turns dark and taken back under a light theme, an exclusion or `darken` turned false, else darkens a light page with the bundled Dark Reader (`vendor/`, the npm build, unmodified: update it by replacing the file and the version in `test_companion.py`) and marks its large background elements `data-browserglass-canvas`; on any page whose root and body are see-through it marks the lowest layer that paints the background (`data-browserglass-canvas`) and every navigation bar fixed or stuck along a window edge, sidebars included, or laid along one in a page that does not scroll (an app shell; the outermost such element) (`data-browserglass-bar`, the DMS surface at `NAV_BAR_OPACITY` over `NAV_BAR_BLUR`: `_CONTENT_LAYERS`), looked for again on resizes of the body's children, clicks and history changes (no subtree observer, no timer); `background.js` talks to the native messaging host, which the browser starts and which lives as long as the browser. The host relays the excluded list and `darken` from the sync's `live_push` (one socket line `{"excluded": [...], "darken": bool}`) to the add-on (`{"type": "excluded", "seq", "domains", "darken"}`; a host starting reads both from `state.json` `last_sync`, `darken` false before any sync; anything but `true` is false, and the protocol stays `NM_PROTO` 1), which stores both in `browser.storage.local`, and writes the active tab's host for `active-site`. |
| Bar widget | `BrowserGlassWidget.qml`, `components/WidgetPill.qml`, `components/GlassPopout.qml` | The pill shows `blur_on` or `blur_off`, plus a dot while a restart is needed. The popout shows the status and has the glass switch (pluginData `glassEnabled`), *Exclude copied URL* and *Open settings*. |
| Settings | `BrowserGlassSettings.qml`, `components/SettingsHeader.qml`, `components/StatusBlock.qml`, `components/SiteList.qml` | Four sections: Status, Appearance, Sites, and Advanced & help. `SiteList` is a filtered `ListView` over the cached `sites --json` output, so only the visible rows exist. |
| Backend | `browserglass.py` | A single file, standard library only. Its sections, in order: `consts` (v0 markers copied byte for byte, prefs, profile roots, niri app-ids), `fsio`, `discover`, `lockprobe`, `inputs`, `settings`, `render`, `sites`, `psl` (registrable domain), `session` (session file, `active-site`), `edits`, `companion` (xpi, companion prefs and states), `native` (native host, `live_push`), `state`, then `cmd_*` and `main`. `tests/py/test_contract.py` checks their order. The output contract is `tests/fixtures/contract/schema.json`. |
| Data | `data/styles.json`, `data/css-mapping.json`, `data/MY-INTERNET-LICENSE`, `data/sites/`, `data/public_suffix_list.dat`, `data/PSL-LICENSE` | The bundled my-internet styles, read through `--data`, Browser Glass's own site fixes (one CSS file per site, added at the end of the style of that name), and Mozilla's Public Suffix List for the registrable domain. Nothing is downloaded at run time. |

**Live flow.** A launcher command goes through the daemon, the backend and, when the companion runs, the browser:

```
DMS launcher --getItems("gs blist")--> BrowserGlassLauncher.qml --siteFor()--> daemon
     |      daemon --active-site --json --pid P --app-id A --window-id W   (title asked of niri, never in the argv)
     |             <-- {host, domain, source: companion | session, age}
     | executeItem --> daemon launcherAction({kind, domain, host, source, age})
     v
BrowserGlassDaemon.qml --savePluginData--> sync --settings-file F --plugin-dir DIR (no debounce)
     |   writes the CSS (gated rules + live section), user.js, xpi, native manifest, wrapper,
     |   then live_push(excluded, darkPages), on every sync, to every $XDG_RUNTIME_DIR/browserGlass/host-<pid>.sock
     |   syncDone: "example.org excluded" when the push was acknowledged, else "... applies after a restart"
     v
browserglass.py native-host (started by the browser, one per browser process)
     |   stdio: 4-byte native-order length + JSON; writes active-<pid>.json and ack-<pid>.json
     v
browserglass@companion: background.js <-> content.js, data-browserglass-live / -off / -tone on <html>
     v
dms-glass-content.css: http(s) rules gated on :root:not([data-browserglass-off]); the live section
     (sites excluded at sync time) gated on :root[data-browserglass-live]:not([data-browserglass-off])
```

Without the add-on neither attribute is ever set, so the page looks exactly as with `liveControl` off and the live section stays inert. With `liveControl` off, the CSS has no gating at all.

**What the backend writes.** Outside the plugin folder it writes only these:

- in each profile: `chrome/dms-glass-chrome.css`, `chrome/dms-glass-content.css`, one `@import` line in `userChrome.css` and one in `userContent.css`, a marked block in `user.js`, and the clean-up of `prefs.js`;
- `~/.config/niri/dms-browser-glass.kdl` and its `include` line in `config.kdl`;
- `$XDG_STATE_HOME/dms/browserGlass/`: `state.json`, `state.lock`, `backup/<profile hash>/`, `pending/`, `state-dirs.json` (the folders made for the state folder, written with or without `liveControl`) and, with `liveControl`, `native-dirs.json` (the folders made for the native manifest);
- `$XDG_RUNTIME_DIR/browserGlass-sync-settings.json`, written by the daemon before each sync (`sync --settings-file`), read then deleted by the sync;
- with `liveControl`: `<profile>/extensions/browserglass@companion.xpi`, more prefs in the `user.js` block (`extensions.autoDisableScopes`, `extensions.startupScanScopes`, plus `xpinstall.signatures.required` with the unsigned xpi only; their originals in `state.json`), `~/.mozilla/native-messaging-hosts/browserglass.json` (folders it creates are tracked), the wrapper `$XDG_STATE_HOME/dms/browserGlass/native-host`, and, written by the native host, `$XDG_RUNTIME_DIR/browserGlass/` (`host-<browser pid>.sock`, `active-<browser pid>.json`, `ack-<browser pid>.json`).

It never writes DMS's own `niri/dms/windowrules.kdl` or `~/.config/dms/firefox.css`. `uninstall` removes all of this, plus the v0 cache `~/.cache/dms/browserGlass/`.

**Signed or unsigned xpi.** The sync deposits the bytes of `companion/browserglass@companion.xpi` as they are when it is a regular file (not a symlink) within a size bound, a valid zip whose entries outside `META-INF/` are byte for byte what `companion_xpi(extension/)` packs (same names), whose `manifest.json` has the id `browserglass@companion`, and whose `META-INF/` holds a signature (`cose.sig` or `mozilla.rsa`). The result is cached in `state.json`, keyed by the signed file's `(mtime_ns, size)` and the `(name, mtime_ns, size)` list of `extension/`, so an unchanged sync opens no zip. Otherwise (a development checkout, or a file that is unreadable, too large or damaged, which gives one warning) it falls back to the unsigned xpi built in memory, and the v1.2 behaviour: `xpinstall.signatures.required = false` in the block, and `signing_enforced` on Firefox release, ESR and Beta (`SIGNED_CHANNELS`). With the signed xpi those channels get the deposit, and `signing_required` stays as the safety net for a browser that deletes it. A block from v1.1 or v1.2 that holds `xpinstall.signatures.required = false` loses it: its original goes back into `prefs.js` by the usual restore once the browser is closed, and until then the companion guard keeps the original value (or the default `true`) in the block. The guard is also written when that restore fails with the browser closed. `companion_registered` reads `extensions.json` (bounded) and reports `disabled` when the entry for `browserglass@companion` is inactive or user- or app-disabled.

**Running browsers.** Firefox holds a POSIX record lock on `.parentlock` for as long as it runs, and `lockprobe` asks the kernel about it with `F_GETLK`. It opens the file read-only, never creates it and never takes a lock of its own. Glass CSS reaches a running browser only after a restart. The niri rule therefore stays while a running profile still has the glass loaded, `status` reports `restart_needed`, and the daemon polls `status` until a restart clears it.

**Uninstall without files.** The script never looks up its own location (no `__file__`), so it can run from its text alone. The text goes on stdin of `python3 -I -c "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))" uninstall` because it is larger than the 128 KiB Linux allows for one argv string. When the browser is running, `prefs.js` is cleaned by a detached process (`fork` and `setsid`) that waits for the browser to close.

## Project layout

```
browserGlass/
├── plugin.json                  # composite: daemon + widget + launcher + settings
├── BrowserGlassDaemon.qml       # sync triggers, status, toasts, IPC, uninstall
├── BrowserGlassWidget.qml       # DankBar pill + popout
├── BrowserGlassLauncher.qml     # launcher component: glass / gs commands
├── BrowserGlassSettings.qml     # settings page, four sections
├── browserglass.py              # the backend (single file, stdlib only)
├── components/
│   ├── logic.js                 # pure daemon logic (argv, settings JSON, status, toasts)
│   ├── launcher.js              # pure launcher logic (query parsing, items, toasts)
│   ├── keeper.js                # creates the sweep process outside the plugin's context
│   ├── UninstallSweep.qml       # uninstall when the plugin folder is deleted
│   ├── SweepProcess.qml         # the sweep's Process
│   ├── StatusBlock.qml          # status (settings page and popout)
│   ├── SiteList.qml             # searchable site styles
│   ├── SettingsHeader.qml       # section title
│   ├── WidgetPill.qml           # bar icon + restart dot
│   └── GlassPopout.qml          # widget menu
├── extension/                   # companion add-on: manifest.json, background.js, content.js, vendor/ (Dark Reader)
├── companion/                   # browserglass@companion.xpi, the same add-on signed by Mozilla (committed at release)
├── data/                        # styles.json, css-mapping.json, MY-INTERNET-LICENSE (my-internet)
│   ├── public_suffix_list.dat   # Mozilla Public Suffix List (PSL-LICENSE, MPL-2.0)
│   └── sites/                   # our own site fixes, one CSS file per site
├── translations/fr.json         # French catalog
├── tests/
│   ├── py/                      # unittest suite, fakehome.py, fixtures/, golden/
│   ├── qml/                     # run.sh, Harness.qml, *.test.qml, stubs/ (Quickshell + qs.*)
│   ├── e2e/                     # marionette.py, companion_home.py, test_e2e_*.py, SPIKE.md, README.md
│   └── fixtures/                # contract/ (CLI output schema + samples), v0/ (v0 scripts)
├── tools/
│   ├── check_translations.py    # every visible string has a French entry
│   ├── check_pr_body.py         # pull request description follows the template
│   ├── update_styles.py         # refreshes data/ from my-internet (CI and by hand)
│   ├── sign_companion.py        # has Mozilla sign the companion add-on (releases, by hand)
│   ├── style-denylist.txt       # sha256 denylist of upstream styles and words
│   └── media/                   # gen_wallpaper.sh, capture.sh, compose.sh, restore.sh, demo/, demo-settings.json
├── .github/                     # workflows (tests, update-styles, pr-template), issue and PR templates
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
BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e*.py'   # sync, Firefox's real pages, uninstall, live gating, page tone, dark pages, active-site, live control, sideload
python3 tests/e2e/marionette.py                                           # the CSS selector spike (SPIKE.md)
```

The tests never touch the real home. `tests/py/fakehome.py` builds a throwaway `HOME` with generated profiles and gives every subprocess its own environment. The QML runner works in a temporary copy, and the end-to-end tests start Firefox with an environment built from scratch, a black-hole proxy and a 127.0.0.1 page server. `tests/py/test_leaks.py` fails when any repository file names a user or a home folder, or one of the real profile ids listed in `BG_LEAK_PROFILE_IDS` (comma-separated; the test is skipped without it). `tests/e2e/README.md` describes the end-to-end checks: the glass on Firefox's real pages and the uninstall, the `liveControl` gating (`test_e2e_gate.py`), light pages under a dark theme (`test_e2e_tone.py`) and darkened (`test_e2e_darken.py`), the page layers (`test_e2e_layers.py`), the session file read by `active-site`, live control through the companion add-on and the real native host (`test_e2e_live.py`), and the add-on as sync deposits it (`test_e2e_sideload.py`: LibreWolf with `BG_LIBREWOLF`, Firefox release for `signing_enforced` and `signing_required`, `disabled` in LibreWolf, and the signed xpi on both with `BG_E2E_SIGNED_XPI`, a Mozilla-signed companion xpi; those are skipped without it). The harness (`marionette.py`) can also start LibreWolf (`BG_LIBREWOLF=/path/to/librewolf`), for tests that need a build that accepts unsigned add-ons; Firefox release removes the unsigned xpi. The native host tests (`tests/py/test_native_host.py`) set their own short `XDG_RUNTIME_DIR`. `tests/py/test_sign_companion.py` runs `tools/sign_companion.py` against a fake AMO server on 127.0.0.1 with made-up keys and a temporary state folder.

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

The full shot list (hero, colours, light and dark, opacities, sites, settings, widget and the launcher GIF) is in the header of `capture.sh`. `tools/media/demo-settings.json` holds the plugin settings for the run. `take` and `shot` work on the live niri session: set up an empty workspace and turn on *Do not disturb* first. `restore.sh` undoes every step. `save-state` also keeps the `browserGlass` entry of DMS's `plugin_settings.json` (mode 600, never printed), and `restore.sh` puts it back JSON-equal, then syncs. Check every image and frame for personal data before you commit.

The launcher GIF (`screenshots/launcher.gif`) drives the real launcher and the real daemon, so it runs only after `save-state`:

```sh
sh tools/media/capture.sh save-state
sh tools/media/launcher_gif.sh                      # writes screenshots/launcher.gif, then runs restore.sh
```

`launcher_gif.sh` switches to an empty workspace on DP-2 with *Do not disturb* and the generated ocean wallpaper, and serves the demo page as `http://news.glass-demo.test:8765/`. A throwaway LibreWolf shows it (`MEDIA_BROWSER=librewolf`: the companion add-on, its prefs and the native messaging manifest go in the fake HOME, while the real `$XDG_RUNTIME_DIR` lets the daemon reach the host). Its `user.js` turns off `dom.security.https_only_mode` and `privacy.resistFingerprinting`, as the e2e tests do: otherwise LibreWolf never loads the plain demo server and forces a light page. Close every real browser first. The ocean wallpaper and dark mode make the daemon rewrite the real profiles' glass CSS, which a running browser only loads on restart, so its restart toast would end up in the GIF. The script waits for a settled `status` before and after the colour change, and stops if a real profile is running. The script types `g`, `gs`, `gs b` and `gs blist` with `dms ipc call launcher openQuery`, runs the item, then `gs unblist`, while `capture.sh frames launcher SECONDS FPS` records the window and the toasts above it with `dms screenshot output`. `compose.sh gif` builds the GIF with `palettegen`/`paletteuse` and keeps it under 8 MB. The toasts are in the shell's language. The script stops if the throwaway window loses focus, because a glass command acts on the focused window, or if `excludedSites` then differs from the saved entry by anything but `glass-demo.test`. It also stops if the steps end less than 2 s before the frames do, which would cut the unblist. A run that stops early deletes its frames. Without `CROP` or `MEDIA_CROP`, `frames` crops to the throwaway window and `MEDIA_CROP_ABOVE` (300) pixels above it, and stays below the bar (`MEDIA_BAR_INSET`, 60 logical px). Two frames come from the real session, so decide on them before you commit: `g` lists your matching apps and other plugins' results, and the `gs` list shows "Excluded: N sites" with your real count (no domain).

## Performance rules

Browser Glass must cost nothing while nothing changes:

- **No idle process and no idle timer.** The daemon reacts to signals and file watches only. The one exception is the `status` poll every 10 s while a restart is needed, and it stops when the restart is done or after three failures.
- **The native host lives and dies with its browser.** The browser starts `browserglass.py native-host` for the companion add-on, and the host exits when the browser closes its stdin or when `$XDG_RUNTIME_DIR/browserGlass/` disappears. In between it blocks in `select()` on stdin and its socket, with no timer and no polling loop, so it costs nothing while nothing happens. A sync's push waits at most 1 s for the acknowledgements.
- **A sync is cheap**: about 0.1 s of CPU, 0.15 s with `liveControl` on (it gates every site style), measured with glass active on the bundled data (`/usr/bin/time -v python3 -I browserglass.py sync …`). A sync that changes nothing writes nothing.
- **The page stylesheet stays small enough to parse at start-up.** Every site style is written once per colour scheme (the dark copy only for pages with a dark version), so `userContent.css` is about 1.6 MB on the bundled data, 1.9 MB with `liveControl` on, and Firefox 160 parses it in about 18 ms (23 ms), against 0.6 MB and 6 ms (0.9 MB and 10 ms) with one copy (`CSSStyleSheet.replaceSync`, median of 9). The shadow-tree branch in the wrapper around a run of gated rules (`GATE_SHADOW_TOP`) tests only the parent, since `& *` tests the wrapper on every ancestor: a branch that climbs to the root there makes the match quadratic in the depth (restyling 14000 elements at depth 80 with a `*` rule: 12.5 ms, 5.5 ungated, 29 with `GATE_SHADOW_TREE` in the wrapper). `test_scheme_size` and `test_growth` in `tests/py/test_gate.py` bound the size; measure the parse time again when a change grows the file.
- **One sync at a time.** Changes are debounced (800 ms), and a sync that is asked for while another runs waits for it. A launcher action skips the debounce.
- **The launcher reads on demand.** `active-site` runs only when a `blist` or `unblist` item is shown or run (which includes the plugin's *Browse* view listing the commands for an empty query), one at a time, its answer kept 3 s; there is no timer. A live push sends only the list of domains, never the CSS, and the xpi is rebuilt deterministically (or the signed one checked once per change of its file or of `extension/`) and written only when its bytes change.
- **The script goes through stdin, never argv**, for the file-less uninstall: Linux caps one argv string at 128 KiB (`MAX_ARG_STRLEN`), and `browserglass.py` is larger than that.
- **No network**, ever, at run time.

## Conventions

- **Python**: standard library only, Python 3.9 syntax and APIs (`ast.parse(source, feature_version=(3, 9))` must pass). The script runs as `python3 -I` and never looks up its own location (no `__file__`).
- **Language**: code, comments, identifiers and source strings are in English.
- **Translations**: each visible string goes through `I18n.trFor("browserGlass", "…")` and has an entry in `translations/fr.json` (`{"term": {"term": "translation"}}`). `tools/check_translations.py` checks that.
- **QML**: use DMS 2 widgets (`qs.DCommon.Widgets`), not the deprecated `Dank*` ones (`tests/qml/run.sh` rejects them). A new file goes into `components/`. After you change a QML file or `logic.js`, run `dms restart` to see it live.
- **Privacy**: no telemetry, no network, and no file written outside the paths in [Architecture](#architecture). Only two development tools use the network: `tools/update_styles.py` and `tools/sign_companion.py`. The plugin never runs them. Tests, fixtures and media use made-up data only.
- **Docs**: user-facing changes go in `docs/GUIDE.md`, and in the README if they change installation or the basics. Every change also gets an entry in `CHANGELOG.md`.

## Releasing a version

1. Freeze `extension/`: the signed add-on is made from it, so any change after signing needs a new version. Bump `version` in `plugin.json` ([Semantic Versioning](https://semver.org/)), together with `version` in `extension/manifest.json` (`tests/py/test_companion.py` checks the two agree), `VERSION` in `browserglass.py`, `version` in `tests/fixtures/contract/status.json` and the `version:` line of `tests/fixtures/contract/report.txt`. `tests/py/test_contract.py` checks that the last two agree. Nothing checks `plugin.json` against them, so compare it by eye.
2. Have Mozilla sign the companion add-on (see *Signing the companion* below). Commit the signed xpi as `companion/browserglass@companion.xpi`, outside `extension/`.
3. Move the `Unreleased` entries of `CHANGELOG.md` under the new version and date, and add its link at the bottom.
4. Refresh the screenshots if the look changed (see [Screenshots](#screenshots)).
5. Run every test, commit, then tag and publish. Attach the signed xpi to the release:

   ```sh
   git tag v1.0.1 && git push origin main v1.0.1
   gh release create v1.0.1 --title v1.0.1 --notes-file <release notes taken from CHANGELOG.md> companion/browserglass@companion.xpi
   ```

**Signing the companion.** `tools/sign_companion.py` has the add-on signed on [addons.mozilla.org](https://addons.mozilla.org) (AMO) in the unlisted channel, through the AMO API v5. It uses the standard library only (no `web-ext`). It is a development tool, and with `tools/update_styles.py` the only part of the repository that uses the network.

Create the API keys on <https://addons.mozilla.org/developers/addon/api/key/> (a Mozilla account is needed). The tool reads them from `WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET` in the environment, or else from `~/.config/browserglass-amo/credentials`, one `NAME=value` line each:

```
WEB_EXT_API_KEY=user:...
WEB_EXT_API_SECRET=...
```

The file must be a regular file of yours with mode 600 (`chmod 600`), or the tool refuses it. `BG_AMO_CREDENTIALS` names another file (the tests use it). Never pass the keys on the command line, and never commit them. Only `sign` and `fetch` read them.

```sh
python3 -I -B tools/sign_companion.py pack                  # build the xpi as browserglass.py does
python3 -I -B tools/sign_companion.py sign                  # upload, wait for the signature, download
python3 -I -B tools/sign_companion.py fetch 1.3.0           # download a version signed later
python3 -I -B tools/sign_companion.py verify <signed xpi>   # same files as extension/, and signed
```

`sign` uploads the version in `extension/manifest.json`, waits for Mozilla to sign it (up to 15 minutes), downloads the signed xpi, checks it with `verify` and writes it to `~/.config/browserglass-amo/signed/`. If the wait times out, the tool prints the AMO version id and exits with status 3: run `fetch <version>` later. Each command prints one JSON line on stdout.

AMO keeps each version number forever, even when the upload is rejected. Never upload the same number twice: the tool records every number it uploads in `~/.config/browserglass-amo/amo-versions.json` and refuses a number that is not greater than the largest one there. Test signings use numbers from `x.y.90` up, in a scratch copy of `extension/`, and are never committed. AMO allows 6 uploads a minute and 20 an hour; the tool never retries, and stops on a rate limit. Any change to `extension/` after signing needs a new version and a new signature.

**Site styles.** `.github/workflows/update-styles.yml` runs every week and can also be started by hand. It calls `tools/update_styles.py`, which fetches `styles.json`, `css-mapping.json` and the licence from [sameerasw/my-internet](https://github.com/sameerasw/my-internet). The tool drops the styles listed in `tools/style-denylist.txt` (sha256 digests of style names and words, so the list does not spell them) and then checks the result with `--check data`. When the data changed, the workflow opens or updates a pull request. Squash-merge that pull request yourself. To refresh by hand:

```sh
python3 -I -B tools/update_styles.py              # fetch and rewrite data/
python3 -I -B tools/update_styles.py --check data # offline check
```

The repository setting *Allow GitHub Actions to create and approve pull requests* must be on. GitHub turns scheduled workflows off after 60 days without activity in the repository, so re-enable the workflow from the Actions tab when that happens.

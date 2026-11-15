# End-to-end tests (headless Firefox)

Both need a Firefox binary (`/usr/lib64/firefox/firefox` and friends, or
`BG_FIREFOX=/path/to/firefox`). They never touch the real home: Firefox and
`browserglass.py` run in a throwaway HOME under `$TMPDIR`, with an environment
built from scratch, a black-hole proxy and a 127.0.0.1 page server. Firefox and
its helpers are killed and the folder removed at the end, also on Ctrl-C.

| Command | What it checks |
|---|---|
| `python3 tests/e2e/marionette.py` | Selector spike: the hand-written CSS rules of `SPIKE.md` on Firefox's real pages (24 checks). |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -v` | Every test file: `test_e2e_glass.py` (`browserglass.py sync --data data --settings …` on a throwaway profile, then the result in Firefox, then `uninstall`), `test_e2e_gate.py`, `test_e2e_tone.py`, `test_e2e_darken.py`, `test_e2e_layers.py`, `test_e2e_live.py` and `test_e2e_sideload.py` (below) and `test_e2e_session.py` (`active-site --pid <firefox pid>` on the session file Firefox writes: `account.proton.test` gives `proton.test`, and the decoded file equals `IOUtils.readJSON(path, {decompress: true})`). |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_gate.py' -v` | `test_e2e_gate.py`: the `liveControl` gating of the page stylesheet, through the five states of `data-browserglass-off` / `data-browserglass-live` on made-up `.test` hosts, against the ungated stylesheet (add `BG_LIBREWOLF=/path/to/librewolf` for LibreWolf too). |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_tone.py' -v` | `test_e2e_tone.py`: light pages under a dark theme. A light page keeps its own background without `data-browserglass-tone`, gets the light tint with `tone="light"` (set by Marionette), a dark page gets the dark tint under a light theme, text contrast at least 4.5 on the effective background; and the add-on's `content.js`, run in the page, measures the tone again when the page or the colour scheme switches (text in `oklch()` and `color(display-p3 …)` too, and the white text of a site style counts as a dark page); under a dark theme the generic style leaves a light page's shadow DOM alone. |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_darken.py' -v` | `test_e2e_darken.py`: dark pages. Dark Reader and `content.js`, run in the page, darken a light page under a dark theme (light text, html and body see-through, the full-page wrapper marked `data-browserglass-canvas` and see-through, a small card dark and solid); a light theme gives the page its colours back (the wrapper, its lowest layer, stays glass), a dark one darkens it again; a page with a dark version, an excluded page and `darkPages` off are left alone. |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_layers.py' -v` | `test_e2e_layers.py`: page layers. On a dark single-page app, the fixed full-window background is marked `data-browserglass-canvas` and see-through (a card over it is not), the fixed header `data-browserglass-bar` in a light veil of the DMS dark surface (35 %) over a strong blur, under a dark theme and a light one, a fixed sidebar with its own colour too; a background rendered late inside an existing element is marked once there; a sticky nav below a hero is marked only while it sticks to the top. |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_live.py' -v` | `test_e2e_live.py`: live control end to end in Firefox, the add-on of `extension/` installed as a temporary add-on, the native messaging manifest of the fake HOME naming this repository's `browserglass.py native-host`, real syncs with `--plugin-dir`: `active` reports on navigation and tab switches, an exclusion pushed by sync turns the open page opaque within 0.5 s of the sync's start and a new excluded page has `data-browserglass-off` from its first script, an un-exclude gives the glass back (live section), two lists back to back (in order: the host serializes lists behind their acks, so this is not the add-on's registration race), no LIVE without OFF on an excluded page (also one open before the add-on is installed), the back/forward cache, the host restarted after a SIGTERM and gone when Firefox quits, a private window as in v1.0, `live.acked` and `restart_needed` false after an exclusion alone, the ack file within 2 s. |
| `BG_E2E=1 BG_LIBREWOLF=/path/to/librewolf BG_E2E_SIGNED_XPI=/path/to/browserglass@companion.xpi python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_sideload.py' -v` | `test_e2e_sideload.py`: the add-on as sync deposits it, from a temporary plugin folder. Unsigned (a copy of `extension/`, no `companion/`): LibreWolf: active at the first start of a fresh profile and at the first restart of an existing one, `disabled` once disabled in the add-on manager (the xpi stays) and `installed` once enabled again, gone after `uninstall` and not back from a stale `extensions.json`; Firefox release: nothing deposited on a profile it ran (`signing_enforced`), and an xpi it deleted at startup gives `signing_required`, no second deposit, prefs restored. Signed (`BG_E2E_SIGNED_XPI`, a Mozilla-signed companion xpi: `extension/` is its entries outside `META-INF/`, `companion/` the file; skipped without it): Firefox release and LibreWolf get the signed bytes, no `xpinstall.signatures.required` in `user.js`, the add-on active at the next start (Firefox: `signedState` > 0 in `extensions.json`), `installed` and `connected`. |

They are skipped unless `BG_E2E=1` and a Firefox binary is found, so the
normal suite (`tests/py`) stays offline and fast. `test_e2e_gate.py` takes
about 15 s per browser; `test_e2e_tone.py` about 10 s; `test_e2e_darken.py` about 10 s; `test_e2e_layers.py` about 10 s; `test_e2e_live.py` about 15 s; `test_e2e_sideload.py`
about 15 s (its LibreWolf cases are skipped without `BG_LIBREWOLF`, its Firefox
cases on a channel that does not require signing, its signed cases without
`BG_E2E_SIGNED_XPI`). `companion_home.py` holds
their shared fixtures (the profile where `browserglass.py` looks for it, the
fake DMS files, the `browserglass.py` subprocesses). `test_e2e_glass.py` takes
about 20 s:

1. **glass** (`readerOpaque=false`, `privateGlass=true`, DMS opacity 0.8 from a
   fake `windowrules.kdl`, surface from a fake `dms-colors.json`): web page,
   reader view, pdf.js, about:newtab, about:home and about:privatebrowsing
   transparent; chrome
   `body` has the tint, `:root`, `#navigator-toolbox`, `#nav-bar`, … are
   transparent; the private window keeps the tint. A second identical sync
   writes nothing.
2. **opaque** (defaults: `readerOpaque=true`, `privateGlass=false`): reader view
   and pdf.js opaque, private window body opaque, the rest unchanged.
3. **off** (`glassEnabled=false`): pages paint their own background, no tint,
   no niri rule.
4. **uninstall** through the stdin bootstrap (no file next to the script):
   every file that existed before the first sync is back byte for byte, mode
   included (`prefs.js`, `profiles.ini` and `installs.ini` excepted: Firefox
   rewrites them), `chrome/` holds only the user's file, the managed prefs are
   back to their original values in `prefs.js`, and no browserGlass file or
   state folder is left.

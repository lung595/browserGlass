# End-to-end tests (headless Firefox)

Both need a Firefox binary (`/usr/lib64/firefox/firefox` and friends, or
`BG_FIREFOX=/path/to/firefox`). They never touch the real home: Firefox and
`browserglass.py` run in a throwaway HOME under `$TMPDIR`, with an environment
built from scratch, a black-hole proxy and a 127.0.0.1 page server. Firefox and
its helpers are killed and the folder removed at the end, also on Ctrl-C.

| Command | What it checks |
|---|---|
| `python3 tests/e2e/marionette.py` | Selector spike: the hand-written CSS rules of `SPIKE.md` on Firefox's real pages (24 checks). |
| `BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -v` | `test_e2e_glass.py`: `browserglass.py sync --data data --settings …` on a throwaway profile, then the result in Firefox, then `uninstall`. |

`test_e2e_glass.py` is skipped unless `BG_E2E=1` and a Firefox binary is found,
so the normal suite (`tests/py`) stays offline and fast. It takes about 20 s:

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

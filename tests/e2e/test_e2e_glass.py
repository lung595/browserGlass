"""End-to-end: browserglass.py sync on a throwaway profile, checked in a real
headless Firefox, then uninstall back to the original bytes.

Opt-in (needs a Firefox binary and takes about a minute):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py,
BG_FIREFOX forces one). Everything lives in one throwaway folder under
$TMPDIR (fake HOME with its XDG folders, a profile in .mozilla/firefox, a
fake DMS opacity rule and colour file); every subprocess gets an environment
built from scratch, Firefox is killed and the folder removed in tearDown.
Zero network: pages come from a 127.0.0.1 server, anything else goes to a
black-hole proxy.

Steps, on the same profile:
  1. glass   sync (readerOpaque=false, privateGlass=true): web page, reader,
             PDF, new tab/home transparent; private window keeps the tint;
             chrome window tinted, toolbox transparent.
  2. opaque  sync (readerOpaque=true, privateGlass=false): reader and PDF
             opaque, private window opaque, the rest unchanged.
  3. off     sync (glassEnabled=false): neutral files, pages opaque, no
             niri rule.
  4. uninstall (stdin bootstrap, no file next to the script): every file
             that existed before is back byte for byte (mode included), the
             prefs are back to their original values, nothing of
             browserGlass is left.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "browserglass.py")
DATA = os.path.join(REPO, "data")
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None

OPACITY = 0.8
SURFACE = (16, 32, 48)  # fake dms-colors.json surface #102030
TINT = "rgba(%d, %d, %d, 0.8)" % SURFACE
TINT_OPAQUE = "rgb(%d, %d, %d)" % SURFACE
ORIGINAL_SCHEME = 2  # content-override already set by the "user" before sync

PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
MANAGED_PREFS = (PREF_STYLESHEETS, PREF_TRANSPARENT, PREF_SCHEME)

PROFILE_ROOT = ".mozilla/firefox"
PROFILE_NAME = "e2etest.default"

USER_CHROME = "/* the user's own chrome tweaks */\n#nav-bar { min-height: 28px; }\n"
NIRI_CONFIG = "// fake niri config\ninput {\n    keyboard {\n    }\n}\n"
WINDOW_RULES = (
    "// DMS Window Rules - Managed by DMS\n"
    "window-rule {\n"
    "    opacity %s\n"
    "    geometry-corner-radius 12\n"
    "}\n" % OPACITY
)
DMS_COLORS = {"mode": "dark", "colors": {"dark": {"surface": "#102030"},
                                         "light": {"surface": "#f0f2f8"}}}

# Firefox writes these itself while it runs: not compared byte for byte.
FIREFOX_RUNTIME = {"prefs.js", "profiles.ini", "installs.ini"}
# What browserGlass names its files: none may survive the uninstall.
BG_ARTIFACT = re.compile(r"dms-glass|dms-browser-glass|browserglass", re.I)

CHROME_SELECTORS = (":root", "#main-window", "#navigator-toolbox", "#nav-bar",
                    "#TabsToolbar", "#tabbrowser-tabbox", "#tabbrowser-tabpanels")

SETTINGS = {
    "blur": True, "isLight": False, "glassEnabled": True, "opacityOverride": False,
    "opacity": 0.85, "siteTheme": "follow", "pagesTransparent": True,
    "genericStyle": True, "excluded": [], "disabledStyles": [], "newTabGlass": True,
}
GLASS = dict(SETTINGS, readerOpaque=False, privateGlass=True)
OPAQUE = dict(SETTINGS, readerOpaque=True, privateGlass=False)
OFF = dict(OPAQUE, glassEnabled=False)


def setUpModule():
    if E2E and FIREFOX:
        mn.install_signal_handlers()


def snapshot(top):
    """{relative path: (kind, mode, content)} of everything below `top`."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            mode = stat.S_IMODE(st.st_mode)
            key = os.path.relpath(full, top)
            if stat.S_ISLNK(st.st_mode):
                out[key] = ("link", mode, os.readlink(full))
            elif stat.S_ISDIR(st.st_mode):
                out[key] = ("dir", mode, None)
            else:
                with open(full, "rb") as f:
                    out[key] = ("file", mode, f.read())
    return out


def pref_lines(text):
    """{pref: raw JS value} of user_pref lines (the last one wins)."""
    out = {}
    for m in re.finditer(r'^\s*user_pref\("([^"]+)",\s*(.*?)\);\s*$', text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def window(m, key, private):
    for w in m.get(key) or []:
        if w["private"] == private:
            return w
    return None


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class GlassE2E(unittest.TestCase):

    def setUp(self):
        self.server = mn.TestServer().start()
        self.addCleanup(self.server.stop)
        self.browser = b = mn.Browser(firefox=FIREFOX, manage_user_js=False)
        self.addCleanup(b.cleanup)  # kills Firefox and its helpers, removes the tree
        shutil.rmtree(b.profile, ignore_errors=True)  # the harness's own profile: unused
        self.home = b.home
        self.profile = os.path.join(b.home, PROFILE_ROOT, PROFILE_NAME)
        b.profile = self.profile
        # The harness prefs (marionette.port included) are the "user's own"
        # user.js; the prefs browserGlass manages are left to its block.
        b.prefs = {k: v for k, v in b.prefs.items() if k not in MANAGED_PREFS}
        self.env = dict(b.env, PYTHONDONTWRITEBYTECODE="1")
        self._seed(b.prefs)

    def tearDown(self):
        if self.browser.proc is not None:
            self.browser.stop()

    # ---- fixtures ---------------------------------------------------------

    def _write(self, rel, text, mode=None):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mode is not None:
            os.chmod(path, mode)
        return path

    def _seed(self, harness_prefs):
        prof = os.path.join(PROFILE_ROOT, PROFILE_NAME)
        self._write(os.path.join(PROFILE_ROOT, "profiles.ini"),
                    "[Profile0]\nName=e2etest\nIsRelative=1\nPath=%s\nDefault=1\n\n"
                    "[General]\nStartWithLastProfile=1\nVersion=2\n" % PROFILE_NAME)
        user_js = "// the user's own user.js\n" + "".join(
            "user_pref(%s, %s);\n" % (json.dumps(k), json.dumps(v))
            for k, v in sorted(harness_prefs.items()))
        self._write(os.path.join(prof, "user.js"), user_js, 0o600)
        self._write(os.path.join(prof, "prefs.js"),
                    "// Mozilla User Preferences\n\n"
                    'user_pref("%s", %d);\n' % (PREF_SCHEME, ORIGINAL_SCHEME))
        self._write(os.path.join(prof, "chrome", "userChrome.css"), USER_CHROME, 0o640)
        self._write(".config/niri/config.kdl", NIRI_CONFIG, 0o644)
        self._write(".config/niri/dms/windowrules.kdl", WINDOW_RULES)
        self._write(".cache/dms/dms-colors.json", json.dumps(DMS_COLORS))

    # ---- script -----------------------------------------------------------

    def run_script(self, args, stdin_bootstrap=False):
        if stdin_bootstrap:
            # The plugin's sweep: script text on stdin, no file next to it.
            with open(SCRIPT, encoding="utf-8") as f:
                text = f.read()
            bootstrap = re.search(r'^STDIN_BOOTSTRAP = "(.*)"$', text, re.M).group(1)
            argv = [sys.executable, "-I", "-c", bootstrap] + args
        else:
            text = None
            argv = [sys.executable, "-I", SCRIPT] + args
        proc = subprocess.run(argv, input=text, env=self.env, cwd=self.browser.root,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=120)
        self.assertEqual(proc.returncode, 0, "%s failed:\n%s%s" % (args[0], proc.stdout, proc.stderr))
        self.assertEqual(proc.stdout.count("\n"), 1, proc.stdout)
        return json.loads(proc.stdout)

    def sync(self, settings):
        return self.run_script(["sync", "--data", DATA, "--settings", json.dumps(settings)])

    def niri_rule(self):
        path = os.path.join(self.home, ".config/niri/dms-browser-glass.kdl")
        with open(path, encoding="utf-8") as f:
            return "window-rule" in f.read()

    # ---- browser ----------------------------------------------------------

    def measure(self):
        b = self.browser
        try:
            b.start()
            m = mn.measure(b, self.server)
            m["chrome"] = b.chrome_js(
                "const out = {};"
                "for (const sel of arguments[0].concat(['body'])) {"
                "  const el = document.querySelector(sel);"
                "  out[sel] = el ? getComputedStyle(el).backgroundColor : null; }"
                "return out;", list(CHROME_SELECTORS))
            m["prefs"] = {n: b.get_pref(n) for n in MANAGED_PREFS}
            return m
        except Exception as exc:
            raise AssertionError("%s\n--- firefox log ---\n%s" % (exc, b.log_tail()))
        finally:
            b.stop()

    # ---- checks -----------------------------------------------------------

    def check(self, label, ok, detail=""):
        with self.subTest(label):
            self.assertTrue(ok, "%s: %s" % (label, detail))

    def check_common(self, cfg, m):
        t, a = mn.transparent, mn.alpha
        self.check(cfg + ": prefs from the user.js block",
                   m["prefs"] == {PREF_STYLESHEETS: True, PREF_TRANSPARENT: True, PREF_SCHEME: 0},
                   m["prefs"])
        self.check(cfg + ": web page html+body transparent",
                   t(m["article"]["root"]) and t(m["article"]["body"]),
                   (mn.bg(m, "article", "root"), mn.bg(m, "article", "body")))
        for page in ("about:newtab", "about:home"):
            pm = m.get(page) or {}
            self.check(cfg + ": %s html+body transparent" % page,
                       "error" not in pm and t(pm.get("root")) and t(pm.get("body")), pm)
        self.check(cfg + ": new-tab wallpaper neutralised",
                   t(mn.g(m, "about:newtab", "wallpaper")), mn.g(m, "about:newtab", "wallpaper"))
        pp = m.get("private_page") or {}
        self.check(cfg + ": about:privatebrowsing transparent",
                   t(pp.get("root")) and t(pp.get("body")), pp)
        chrome = m["chrome"]
        self.check(cfg + ": chrome window body = DMS tint", chrome.get("body") == TINT, chrome)
        for sel in CHROME_SELECTORS:
            self.check(cfg + ": chrome %s transparent" % sel, a(chrome.get(sel)) == 0.0, chrome)
        nw = window(m, "chrome_with_private", False)
        self.check(cfg + ": normal window keeps the tint", nw is not None and mn.bg(nw, "body") == TINT, nw)
        self.check(cfg + ": reader loaded", m.get("reader_loaded"), mn.g(m, "reader", "url"))
        self.check(cfg + ": pdf.js loaded", m.get("pdf_loaded")
                   and (mn.g(m, "pdf", "url") or "").endswith("/doc.pdf"), mn.g(m, "pdf", "url"))

    def check_glass(self, m):
        t = mn.transparent
        self.check_common("glass", m)
        self.check("glass: reader html+body transparent",
                   t(mn.g(m, "reader", "root")) and t(mn.g(m, "reader", "body")), m.get("reader"))
        self.check("glass: pdf body transparent (generic, no opaque rule)",
                   t(mn.g(m, "pdf", "body")), m.get("pdf"))
        pw = window(m, "chrome_with_private", True)
        self.check("glass: private window keeps the glass tint",
                   pw is not None and pw["privatebrowsingmode"] == "temporary"
                   and mn.bg(pw, "body") == TINT, pw)

    def check_opaque(self, m):
        o = mn.opaque
        self.check_common("opaque", m)
        self.check("opaque: reader body opaque", o(mn.g(m, "reader", "body")), m.get("reader"))
        ids = mn.g(m, "pdf", "ids") or {}
        self.check("opaque: pdf viewer matched", ids.get("hasSelector"), ids)
        self.check("opaque: pdf body opaque", o(mn.g(m, "pdf", "body")), m.get("pdf"))
        pw = window(m, "chrome_with_private", True)
        self.check("opaque: private window body opaque tint",
                   pw is not None and pw["privatebrowsingmode"] == "temporary"
                   and mn.bg(pw, "body") == TINT_OPAQUE, pw)

    def check_off(self, m):
        o = mn.opaque
        self.check("off: web page body opaque (page's own white)",
                   mn.bg(m, "article", "body") == "rgb(255, 255, 255)", m.get("article"))
        self.check("off: chrome body not tinted", m["chrome"].get("body") not in (TINT, TINT_OPAQUE),
                   m["chrome"])
        self.check("off: about:newtab paints its own background",
                   o(mn.g(m, "about:newtab", "body")) or o(mn.g(m, "about:newtab", "root")),
                   m.get("about:newtab"))
        self.check("off: transparent-browser pref off", m["prefs"].get(PREF_TRANSPARENT) is False,
                   m["prefs"])

    def check_restored(self, before, after):
        for rel, entry in sorted(before.items()):
            if os.path.basename(rel) in FIREFOX_RUNTIME:
                continue
            self.check("restored: " + rel, after.get(rel) == entry,
                       "before=%r after=%r" % (entry[:2], (after.get(rel) or ())[:2]))
        chrome_rel = os.path.join(PROFILE_ROOT, PROFILE_NAME, "chrome")
        self.check("restored: chrome/ holds only the user's files",
                   sorted(k for k in after if k.startswith(chrome_rel + os.sep))
                   == sorted(k for k in before if k.startswith(chrome_rel + os.sep)),
                   [k for k in after if k.startswith(chrome_rel)])
        leftovers = [k for k in after if k not in before and BG_ARTIFACT.search(k)]
        self.check("restored: no browserGlass file left", not leftovers, leftovers)
        self.check("restored: state folder removed",
                   not os.path.lexists(os.path.join(self.home, ".local/state/dms/browserGlass")))
        with open(os.path.join(self.profile, "prefs.js"), encoding="utf-8") as f:
            prefs = pref_lines(f.read())
        self.check("restored: content-override back to the user's value",
                   prefs.get(PREF_SCHEME) == str(ORIGINAL_SCHEME), prefs.get(PREF_SCHEME))
        for name in (PREF_STYLESHEETS, PREF_TRANSPARENT):
            self.check("restored: %s gone from prefs.js (never set before)" % name,
                       name not in prefs, prefs.get(name))

    # ---- the test ---------------------------------------------------------

    def test_sync_in_firefox_then_uninstall(self):
        before = snapshot(self.home)

        out = self.sync(GLASS)
        self.assertEqual((out["glass"], out["reason"], out["opacity"], out["first_run"]),
                         (True, "active", OPACITY, True), out)
        self.assertEqual(len(out["changed"]), 1, out)
        self.assertEqual(out["running_changed"], [], out)
        self.assertEqual(self.sync(GLASS)["changed"], [], "second identical sync wrote")
        self.assertTrue(self.niri_rule(), "glass active: niri rule expected")
        self.check_glass(self.measure())

        out = self.sync(OPAQUE)
        self.assertEqual((out["glass"], out["first_run"], len(out["changed"])), (True, False, 1), out)
        self.check_opaque(self.measure())

        out = self.sync(OFF)
        self.assertEqual((out["glass"], out["reason"]), (False, "toggled_off"), out)
        self.assertFalse(self.niri_rule(), "glass off, browser closed: niri rule must go")
        self.check_off(self.measure())

        out = self.run_script(["uninstall"], stdin_bootstrap=True)
        self.assertEqual(out["pending"], [], out)
        self.assertTrue(out["state_removed"], out)
        self.assertTrue(out["niri_changed"], out)
        self.check_restored(before, snapshot(self.home))


if __name__ == "__main__":
    unittest.main()

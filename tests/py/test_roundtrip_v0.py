"""Black-box round trips of the browserglass.py CLI (phase P3 gate).

Everything goes through the command line, inside a FakeHome: nothing of the
script is imported.

- v0 round trip: a fake HOME (Firefox native, LibreWolf with a symlinked
  user.js, Flatpak Firefox, niri config, DMS window rules and colours) is
  snapshotted ("pre-v0"), then seeded by running the unmodified v0 bash
  script (tests/fixtures/v0/). v1 `sync` must migrate it without duplicates,
  a second `sync` must write nothing, and `uninstall` must give back the
  pre-v0 tree byte for byte, permissions and symlinks included.
- fresh round trip: the same HOME without v0, sync then uninstall.
- uninstall from the script text alone (on stdin of `python3 -I -c
  STDIN_BOOTSTRAP uninstall`) from an empty working directory, with no file
  next to the script.

No network: the v0 sites cache is pre-filled from data/ (so v0 never
fetches) and every subprocess gets a black-hole proxy.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path

from fakehome import PREFS_HEADER, REPO, SCRIPT, FakeHome, load_script

import test_contract

DATA = REPO / "data"
V0_DIR = REPO / "tests" / "fixtures" / "v0"
V0_SYNC = V0_DIR / "browser-glass-sync"
V0_SITES = V0_DIR / "browser-glass-sites"
V0_SHA256 = {
    "browser-glass-sync": "23b20505f17aad0a25030957000024623e901dc49fee3ce3a665b95e011b68ce",
    "browser-glass-sites": "4042fa45a91361e64a4726498dfaa42f248da038cdbd8565776538ea8630e9c7",
}

SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

# Port 9 (discard) on loopback: any HTTP(S) attempt fails at once.
NO_NETWORK = {
    "http_proxy": "http://127.0.0.1:9",
    "https_proxy": "http://127.0.0.1:9",
    "HTTP_PROXY": "http://127.0.0.1:9",
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "all_proxy": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9",
    "no_proxy": None,
    "NO_PROXY": None,
}

# Exact lines and markers v0 wrote (whole lines).
V0_USERJS_BEGIN = "// >>> dms-browser-glass (g\u00e9n\u00e9r\u00e9, ne pas \u00e9diter)"
IMPORT_CHROME = '@import "dms-glass-chrome.css";'
IMPORT_CONTENT = '@import "dms-glass-content.css";'
NIRI_INCLUDE = 'include optional=true "dms-browser-glass.kdl"'
MANAGED_PREFS = (
    "toolkit.legacyUserProfileCustomizations.stylesheets",
    "browser.tabs.allow_transparent_browser",
    "layout.css.prefers-color-scheme.content-override",
)
CHARSET = '@charset "UTF-8";'

SETTINGS = dict(test_contract.load_json("settings-default.json"), excluded=["example.org"])
V0_ARGS = ["--blur", "1", "--pages", "1", "--exclude", "example.org"]

# --- the fake HOME ----------------------------------------------------------

FF_ROOT = ".mozilla/firefox"
FF_PROFILE = FF_ROOT + "/q1w2e3r4.default-release"
LW_ROOT = ".librewolf"
LW_PROFILE = LW_ROOT + "/t5y6u7i8.default-default"
FP_ROOT = ".var/app/org.mozilla.firefox/.mozilla/firefox"
FP_PROFILE = FP_ROOT + "/o9p0a1s2.default"
PROFILES = (FF_PROFILE, LW_PROFILE, FP_PROFILE)
LW_USERJS_TARGET = "dotfiles/librewolf/user.js"
LW_USERJS_LINK = os.path.relpath(LW_USERJS_TARGET, LW_PROFILE)

USER_CHROME = CHARSET + "\n/* my own tweaks */\n#nav-bar { min-height: 30px !important; }\n"
USER_CONTENT = "/* my own page tweaks */\na:visited { color: purple !important; }\n"
FF_USERJS = 'user_pref("browser.startup.homepage", "about:blank");\n'
LW_USERJS = '// kept in my dotfiles\nuser_pref("privacy.resistFingerprinting", false);\n'
NIRI_CONFIG = (
    'input {\n    keyboard {\n        xkb {\n            layout "us"\n        }\n    }\n}\n'
    '\ninclude "dms/windowrules.kdl"\n'
)
WINDOW_RULES = (
    "// DMS window rules\n"
    "window-rule {\n    geometry-corner-radius 12\n    clip-to-geometry true\n    opacity 0.8\n}\n"
    'window-rule {\n    match app-id="kitty"\n    opacity 0.95\n}\n'
)
DMS_FIREFOX_CSS = "/* DMS file, never touched */\n:root { --dms-test: 1; }\n"

# Raw prefs.js values (text after the comma), as Firefox writes them.
# content-override 2 is a user choice v0 never writes (v0 wrote 0 or 1).
FF_PREFS = {"browser.startup.page": "3",
            "layout.css.prefers-color-scheme.content-override": "2"}
LW_PREFS = {"browser.download.useDownloadDir": "false"}
FP_PREFS = {"browser.uidensity": "1"}
# For the fresh HOME only (no v0 ever ran, so the value is unambiguously the
# user's): a stylesheets pref the user set himself must be kept.
FP_PREFS_FRESH = dict(FP_PREFS, **{"toolkit.legacyUserProfileCustomizations.stylesheets": "true"})

ALLOWED_PROFILE_FILES = {
    "chrome", "chrome/dms-glass-chrome.css", "chrome/dms-glass-content.css",
    "chrome/userChrome.css", "chrome/userContent.css", "user.js", "prefs.js",
}
STATE_REL = ".local/state/dms/browserGlass"
V0_CACHE_REL = ".cache/dms/browserGlass"
NIRI_OUT_REL = ".config/niri/dms-browser-glass.kdl"
NIRI_CONFIG_REL = ".config/niri/config.kdl"


def prefs_text(prefs):
    """prefs.js with raw values, sorted like Firefox writes it."""
    return PREFS_HEADER + "".join(
        'user_pref("%s", %s);\n' % (k, v) for k, v in sorted(prefs.items()))


def build_home(fh, fresh=False):
    """Lay out the fake HOME. Returns {"ids": {profile rel: id}}."""
    # Native Firefox: user chrome files with @charset, user.js in mode 600.
    fh.write(FF_PROFILE + "/prefs.js", prefs_text(FF_PREFS))
    fh.write(FF_PROFILE + "/chrome/userChrome.css", USER_CHROME, mode=0o644)
    fh.write(FF_PROFILE + "/chrome/userContent.css", USER_CONTENT, mode=0o644)
    fh.write(FF_PROFILE + "/user.js", FF_USERJS, mode=0o600)
    fh.write(FF_PROFILE + "/times.json", '{"created":1700000000000}\n')
    fh.write_profiles_ini(FF_ROOT, [{"name": "default-release", "path": "q1w2e3r4.default-release",
                                     "default": True}],
                          installs={"4F96D1932A9F858E": "q1w2e3r4.default-release"})
    # LibreWolf: no chrome folder, user.js is a symlink into the dotfiles.
    fh.write(LW_PROFILE + "/prefs.js", prefs_text(LW_PREFS))
    fh.write(LW_USERJS_TARGET, LW_USERJS, mode=0o640)
    os.symlink(LW_USERJS_LINK, str(fh.resolve(LW_PROFILE + "/user.js")))
    fh.write_profiles_ini(LW_ROOT, [{"name": "default-default", "path": "t5y6u7i8.default-default",
                                     "default": True}])
    # Flatpak Firefox: only prefs.js.
    fh.write(FP_PROFILE + "/prefs.js", prefs_text(FP_PREFS_FRESH if fresh else FP_PREFS))
    fh.write_profiles_ini(FP_ROOT, [{"name": "default", "path": "o9p0a1s2.default"}])
    # niri, DMS.
    fh.write(NIRI_CONFIG_REL, NIRI_CONFIG, mode=0o644)
    fh.write(".config/niri/dms/windowrules.kdl", WINDOW_RULES, mode=0o644)
    fh.write(".config/dms/firefox.css", DMS_FIREFOX_CSS, mode=0o644)
    fh.write(".local/state/dms/session.json", "{}\n", mode=0o644)
    fh.write_dms_colors(mode="dark", surface_dark="#1a1c22")
    ids = {}
    for rel in PROFILES:
        real = os.path.realpath(str(fh.resolve(rel)))
        ids[rel] = hashlib.sha256(os.fsencode(real)).hexdigest()[:12]
    return {"ids": ids}


def mtimes(fh):
    """{relative path: (st_mtime_ns, st_ino)} of everything below HOME."""
    out = {}
    top = str(fh.home)
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            out[os.path.relpath(full, top)] = (st.st_mtime_ns, st.st_ino)
    return out


def describe(entry):
    if entry is None:
        return "absent"
    kind, mode, content = entry
    if kind == "file":
        shown = content if len(content) <= 400 else content[:400] + b"..."
        return "file %o %r" % (mode, shown)
    return "%s %o %r" % (kind, mode, content)


def tree_diff(expected, actual):
    lines = []
    for key in sorted(set(expected) | set(actual)):
        if expected.get(key) != actual.get(key):
            lines.append("%s:\n  expected %s\n  actual   %s"
                         % (key, describe(expected.get(key)), describe(actual.get(key))))
    return "\n".join(lines)


def tools_missing(fh, names):
    path = fh.env()["PATH"]
    return [n for n in names if shutil.which(n, path=path) is None]


class RoundTripBase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    # -- running ------------------------------------------------------------

    def run_cli(self, args):
        proc = self.fh.run_script(args, extra_env=NO_NETWORK)
        self.assertEqual(proc.returncode, 0, "%s: exit %d\nstdout: %s\nstderr: %s"
                         % (args[0], proc.returncode, proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, "%s must print one line: %r" % (args[0], proc.stdout))
        doc = json.loads(lines[0])
        errs = test_contract.validate(doc, SCHEMA[SCHEMA["commands"][args[0]]], DEFS)
        self.assertEqual(errs, [], "%s output breaks the contract: %s" % (args[0], lines[0]))
        return doc

    def sync(self):
        return self.run_cli(["sync", "--data", str(DATA), "--settings", json.dumps(SETTINGS)])

    def uninstall(self):
        return self.run_cli(["uninstall"])

    def run_v0(self):
        missing = tools_missing(self.fh, ("bash", "jq", "awk", "python3"))
        if missing:
            self.skipTest("v0 needs %s (not found)" % ", ".join(missing))
        # The v0 daemon fetched the my-internet styles into this cache; fill
        # it from data/ so v0 builds its site CSS offline, like on a real
        # install. v0 sync never fetches by itself.
        cache = self.fh.resolve(V0_CACHE_REL)
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(DATA / "styles.json"), str(cache / "styles.json"))
        shutil.copyfile(str(DATA / "css-mapping.json"), str(cache / "css-mapping.json"))
        (cache / ".fetched").write_bytes(b"")
        proc = subprocess.run(
            ["bash", str(V0_SYNC)] + V0_ARGS,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=self.fh.env(NO_NETWORK), cwd=str(self.fh.home), timeout=120)
        self.assertEqual(proc.returncode, 0, "v0 failed\nstdout: %s\nstderr: %s"
                         % (proc.stdout, proc.stderr))
        self.assertIn("glass=1 opacity=0.8", proc.stdout)
        # v0 really installed itself everywhere.
        for rel in PROFILES:
            text = self.fh.read(rel + "/user.js")
            self.assertIn(V0_USERJS_BEGIN, text.splitlines(), rel)
            self.assertIn(IMPORT_CHROME, self.fh.read(rel + "/chrome/userChrome.css").splitlines())
            self.assertIn(IMPORT_CONTENT, self.fh.read(rel + "/chrome/userContent.css").splitlines())
            self.assertIn("/* Styles par site", self.fh.read(rel + "/chrome/dms-glass-content.css"))
        self.assertTrue(self.fh.exists(NIRI_OUT_REL))
        self.assertIn(NIRI_INCLUDE, self.fh.read(NIRI_CONFIG_REL).splitlines())
        return proc

    # -- checks -------------------------------------------------------------

    def assert_tree(self, expected, msg):
        actual = self.fh.snapshot(".")
        if actual != expected:
            self.fail("%s: the tree differs\n%s" % (msg, tree_diff(expected, actual)))

    def assert_writes_allowed(self, before, after, msg):
        """Every path created or changed between two snapshots is one the
        plugin may write (rule 1), and only the v0 cache may disappear."""
        def allowed(key):
            if key == STATE_REL or key.startswith(STATE_REL + "/"):
                return True
            if key in (NIRI_OUT_REL, NIRI_CONFIG_REL, LW_USERJS_TARGET):
                return True
            for rel in PROFILES:
                if key.startswith(rel + "/") and key[len(rel) + 1:] in ALLOWED_PROFILE_FILES:
                    return True
            return False

        bad = []
        for key in sorted(set(before) | set(after)):
            if before.get(key) == after.get(key):
                continue
            if key not in after:
                if key == V0_CACHE_REL or key.startswith(V0_CACHE_REL + "/"):
                    continue
                bad.append("removed " + key)
            elif before.get(key) is not None and before[key][0] == "dir" and after[key][0] == "dir":
                if before[key][1] != after[key][1]:
                    bad.append("mode changed " + key)
            elif not allowed(key):
                bad.append("wrote " + key)
        self.assertEqual(bad, [], msg)

    def assert_synced(self, out, info, first_run):
        ids = set(info["ids"].values())
        self.assertTrue(out["glass"], out)
        self.assertEqual(out["reason"], "active", out)
        self.assertAlmostEqual(out["opacity"], 0.8, places=6)
        self.assertEqual(out["first_run"], first_run, out)
        self.assertEqual(set(out["changed"]), ids, out)
        self.assertEqual(out["running_changed"], [], out)
        self.assertTrue(out["niri_changed"], out)

    def assert_single_install(self, pre):
        """One import, one user.js block and one include, nothing of v0."""
        for rel in PROFILES:
            chrome = self.fh.read(rel + "/chrome/userChrome.css").splitlines()
            content = self.fh.read(rel + "/chrome/userContent.css").splitlines()
            self.assertEqual(chrome.count(IMPORT_CHROME), 1, rel)
            self.assertEqual(content.count(IMPORT_CONTENT), 1, rel)
            self.assertNotIn(IMPORT_CONTENT, chrome, rel)
            self.assertNotIn(IMPORT_CHROME, content, rel)
            userjs = self.fh.read(rel + "/user.js").splitlines()
            self.assertNotIn(V0_USERJS_BEGIN, userjs, rel)
            self.assertEqual(len([l for l in userjs if l.startswith("// >>>")]), 1, rel)
            self.assertEqual(len([l for l in userjs if l.startswith("// <<<")]), 1, rel)
            for pref in MANAGED_PREFS:
                hits = [l for l in userjs if l.startswith('user_pref("%s",' % pref)]
                self.assertEqual(len(hits), 1, "%s: %s in user.js %r" % (rel, pref, hits))
            for name in ("dms-glass-chrome.css", "dms-glass-content.css"):
                text = self.fh.read(rel + "/chrome/" + name)
                self.assertNotIn("browser-glass-sync", text, "%s/%s still v0" % (rel, name))
        # The user's own lines are still there, once.
        chrome = self.fh.read(FF_PROFILE + "/chrome/userChrome.css").splitlines()
        self.assertEqual(chrome[0], CHARSET, "@charset must stay first")
        for line in USER_CHROME.splitlines():
            self.assertEqual(chrome.count(line), 1, line)
        content = self.fh.read(FF_PROFILE + "/chrome/userContent.css").splitlines()
        for line in USER_CONTENT.splitlines():
            self.assertEqual(content.count(line), 1, line)
        self.assertEqual(self.fh.read(FF_PROFILE + "/user.js").splitlines().count(FF_USERJS.strip()), 1)
        lw = self.fh.read(LW_PROFILE + "/user.js").splitlines()
        for line in LW_USERJS.splitlines():
            self.assertEqual(lw.count(line), 1, line)
        # user.js keeps mode 600.
        mode = stat.S_IMODE(os.stat(str(self.fh.resolve(FF_PROFILE + "/user.js"))).st_mode)
        self.assertEqual(mode, 0o600)
        # niri: the include line once, the user's config intact before it.
        config = self.fh.read(NIRI_CONFIG_REL)
        self.assertEqual(config.splitlines().count(NIRI_INCLUDE), 1, config)
        self.assertTrue(config.startswith(NIRI_CONFIG), config)
        self.assertEqual(stat.S_IMODE(os.stat(str(self.fh.resolve(NIRI_CONFIG_REL))).st_mode), 0o644)
        niri = self.fh.read(NIRI_OUT_REL)
        self.assertNotIn("G\u00e9n\u00e9r\u00e9", niri, "niri rule still v0")
        # DMS files are never touched (rule 8).
        now = self.fh.snapshot(".")
        for key in (".config/niri/dms/windowrules.kdl", ".config/dms/firefox.css",
                    ".cache/dms/dms-colors.json"):
            self.assertEqual(now[key], pre[key], key)
        # v0's cache is gone, v1 state exists.
        self.assertFalse(self.fh.exists(V0_CACHE_REL))
        self.assertTrue(self.fh.exists(STATE_REL))

    def assert_noop_sync(self, info):
        before_tree = self.fh.snapshot(".")
        before_times = mtimes(self.fh)
        out = self.sync()
        self.assertEqual(out["changed"], [], out)
        self.assertEqual(out["running_changed"], [], out)
        self.assertFalse(out["niri_changed"], out)
        self.assertFalse(out["first_run"], out)
        self.assertTrue(out["glass"], out)
        self.assert_tree(before_tree, "second sync")
        after_times = mtimes(self.fh)
        touched = sorted(k for k in after_times if before_times.get(k) != after_times[k])
        self.assertEqual(touched, [], "second sync touched files")

    def assert_uninstalled(self, out, info, expected, removed_all=True):
        ids = set(info["ids"].values())
        if removed_all:
            self.assertEqual(set(out["removed"]), ids, out)
        self.assertTrue(set(out["removed"]) | set(out["restored"]) <= ids, out)
        self.assertEqual(out["pending"], [], out)
        self.assertTrue(out["niri_changed"], out)
        self.assert_tree(expected, "after uninstall")
        self.assertFalse(self.fh.exists(STATE_REL))
        self.assertFalse(self.fh.exists(V0_CACHE_REL))
        # The user's pref is back with its original value.
        prefs = self.fh.read(FF_PROFILE + "/prefs.js")
        self.assertIn('user_pref("layout.css.prefers-color-scheme.content-override", 2);', prefs)

    def simulate_browser_run(self, original, check_ff=True):
        """What a browser start does to prefs.js: every pref user.js sets is
        copied in (only the managed ones here; the user's own user.js prefs
        are left out so the expected tree stays the pre-v0 one)."""
        for rel, prefs in original.items():
            userjs = self.fh.read(rel + "/user.js")
            merged = dict(prefs)
            for pref in MANAGED_PREFS:
                found = re.findall(r'^user_pref\("%s",\s*(.*?)\);\s*$' % re.escape(pref),
                                   userjs, re.M)
                self.assertTrue(found, "%s: %s not in user.js" % (rel, pref))
                merged[pref] = found[-1]
            self.fh.write(rel + "/prefs.js", prefs_text(merged))
        if check_ff:
            # Firefox native's content-override now holds v1's value, not 2.
            self.assertNotIn('content-override", 2);', self.fh.read(FF_PROFILE + "/prefs.js"))


class VendoredV0Test(unittest.TestCase):

    def test_unmodified(self):
        for name, digest in V0_SHA256.items():
            data = (V0_DIR / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)
        self.assertTrue(os.access(str(V0_SYNC), os.X_OK))
        self.assertTrue(os.access(str(V0_SITES), os.X_OK))


class V0RoundTripTest(RoundTripBase):
    """pre-v0 -> v0 bash -> v1 sync (x2) -> v1 uninstall == pre-v0."""

    def seed(self):
        info = build_home(self.fh)
        pre = self.fh.snapshot(".")
        self.run_v0()
        # v0 writes through mktemp + mv: the symlinked user.js becomes a
        # regular file with the target's text (the target is untouched).
        # v1 cannot know a link was there, so it is expected back as a file.
        expected = dict(pre)
        link = LW_PROFILE + "/user.js"
        if not os.path.islink(str(self.fh.resolve(link))):
            target = pre[LW_USERJS_TARGET]
            expected[link] = ("file", target[1], target[2])
            self.assertEqual(self.fh.snapshot(".")[LW_USERJS_TARGET], target)
        return info, pre, expected

    def test_sync_then_uninstall(self):
        info, pre, expected = self.seed()
        seeded = self.fh.snapshot(".")
        out = self.sync()
        self.assert_synced(out, info, first_run=True)
        self.assert_single_install(pre)
        self.assert_writes_allowed(seeded, self.fh.snapshot("."), "v1 sync over v0")
        self.assert_noop_sync(info)
        self.assert_uninstalled(self.uninstall(), info, expected)

    def test_sync_browser_ran_then_uninstall(self):
        info, pre, expected = self.seed()
        self.sync()
        self.assert_noop_sync(info)
        self.simulate_browser_run({FF_PROFILE: FF_PREFS, LW_PROFILE: LW_PREFS, FP_PROFILE: FP_PREFS})
        self.assert_uninstalled(self.uninstall(), info, expected)

    def test_v0_light_then_dark_then_sync_and_uninstall(self):
        """v0 ran in light mode while the browsers ran (prefs.js took
        content-override 1), then in dark mode with them closed (the v0
        block now says 0, prefs.js still 1). That 1 is v0's: the v1
        uninstall must remove it, giving the pre-v0 tree back."""
        info, pre, expected = self.seed()
        self.fh.write_dms_colors(mode="light", surface_dark="#1a1c22")
        self.run_v0()
        # Firefox native keeps its user value 2 (never started here).
        self.simulate_browser_run({LW_PROFILE: LW_PREFS, FP_PROFILE: FP_PREFS}, check_ff=False)
        self.fh.write_dms_colors(mode="dark", surface_dark="#1a1c22")
        self.run_v0()
        scheme = 'user_pref("layout.css.prefers-color-scheme.content-override", %s);'
        for rel in (LW_PROFILE, FP_PROFILE):
            self.assertIn(scheme % 1, self.fh.read(rel + "/prefs.js").splitlines(), rel)
            self.assertIn(scheme % 0, self.fh.read(rel + "/user.js").splitlines(), rel)
        self.assertEqual(self.fh.snapshot(".")[".cache/dms/dms-colors.json"],
                         pre[".cache/dms/dms-colors.json"])
        out = self.sync()
        self.assert_synced(out, info, first_run=True)
        self.assert_uninstalled(self.uninstall(), info, expected)

    def test_uninstall_v0_only(self):
        """Disabling the plugin right after the v1 update, before any sync."""
        info, pre, expected = self.seed()
        out = self.uninstall()
        self.assertTrue(out["v0_cache_removed"], out)
        self.assert_uninstalled(out, info, expected)


class FreshRoundTripTest(RoundTripBase):
    """No v0: sync -> sync -> uninstall == the original tree, strictly."""

    def seed(self):
        info = build_home(self.fh, fresh=True)
        return info, self.fh.snapshot(".")

    def assert_link_kept(self):
        link = self.fh.resolve(LW_PROFILE + "/user.js")
        self.assertTrue(os.path.islink(str(link)), "user.js is no longer a symlink")
        self.assertEqual(os.readlink(str(link)), LW_USERJS_LINK)

    def test_sync_then_uninstall(self):
        info, pre = self.seed()
        out = self.sync()
        self.assert_synced(out, info, first_run=True)
        self.assert_single_install(pre)
        self.assert_writes_allowed(pre, self.fh.snapshot("."), "fresh sync")
        # The link is kept and the block went into its target.
        self.assert_link_kept()
        self.assertIn("// >>>", self.fh.read(LW_USERJS_TARGET))
        self.assertEqual(stat.S_IMODE(os.stat(str(self.fh.resolve(LW_USERJS_TARGET))).st_mode), 0o640)
        self.assert_noop_sync(info)
        out = self.uninstall()
        self.assertFalse(out["v0_cache_removed"], out)
        self.assertTrue(out["state_removed"], out)
        self.assert_uninstalled(out, info, pre)
        self.assert_link_kept()

    def test_sync_browser_ran_then_uninstall(self):
        info, pre = self.seed()
        self.sync()
        self.assert_noop_sync(info)
        self.simulate_browser_run({FF_PROFILE: FF_PREFS, LW_PROFILE: LW_PREFS,
                                   FP_PROFILE: FP_PREFS_FRESH})
        out = self.uninstall()
        self.assert_uninstalled(out, info, pre)
        self.assertIn('user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);',
                      self.fh.read(FP_PROFILE + "/prefs.js"))

    def test_uninstall_from_inline_text(self):
        """The script text alone (on stdin of `python3 -I -c STDIN_BOOTSTRAP
        uninstall`), from an empty cwd: the route of the plugin's sweep."""
        info, pre = self.seed()
        self.sync()
        cwd = self.fh.root / "empty-cwd"
        cwd.mkdir()
        text = SCRIPT.read_text(encoding="utf-8")
        bootstrap = load_script().STDIN_BOOTSTRAP
        proc = subprocess.run(
            [sys.executable or "python3", "-I", "-c", bootstrap, "uninstall"], input=text,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=self.fh.env(NO_NETWORK), cwd=str(cwd), timeout=60)
        self.assertEqual(proc.returncode, 0, "stdout: %s\nstderr: %s" % (proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        out = json.loads(lines[0])
        self.assertEqual(test_contract.validate(out, SCHEMA["uninstall"], DEFS), [], lines[0])
        self.assertTrue(out["state_removed"], out)
        self.assert_uninstalled(out, info, pre)
        self.assertEqual(os.listdir(str(cwd)), [], "uninstall wrote into its cwd")


if __name__ == "__main__":
    unittest.main()

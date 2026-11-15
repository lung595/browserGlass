"""browserglass.py sync, through the command line inside a FakeHome.

Idempotence, --profile, --opacity / --off, the H1 deferral of the niri rule
removal, siteTheme "none" (H3), @charset, permissions and symlinks, read-only
files, the state lock, the v0 cache and stale temporary files.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import stat
import unittest

import test_contract
from fakehome import PREFS_HEADER, FakeHome, LockHolder, kill_strays, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

ROOT = ".mozilla/firefox"
PROFILE = ROOT + "/abcd1234.default-release"
OTHER = ROOT + "/efgh5678.work"
NIRI_CONFIG = ".config/niri/config.kdl"
NIRI_OUT = ".config/niri/dms-browser-glass.kdl"
STATE = ".local/state/dms/browserGlass"
INCLUDE = 'include optional=true "dms-browser-glass.kdl"'
IMPORT_CHROME = '@import "dms-glass-chrome.css";'
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}


def prefs_text(prefs):
    return PREFS_HEADER + "".join('user_pref("%s", %s);\n' % kv for kv in sorted(prefs.items()))


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


class SyncCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)

    def home(self, opacity="0.8", profiles=(PROFILE,), prefs=None):
        fh = self.fh
        entries = []
        for rel in profiles:
            fh.write(rel + "/prefs.js", prefs_text(prefs or {"browser.startup.page": "3"}))
            entries.append({"name": os.path.basename(rel), "path": os.path.basename(rel)})
        entries[0]["default"] = True
        fh.write_profiles_ini(ROOT, entries)
        fh.write(NIRI_CONFIG, 'input {\n}\n\ninclude "dms/windowrules.kdl"\n', mode=0o644)
        fh.write(".config/niri/dms/windowrules.kdl",
                 "window-rule {\n    opacity %s\n}\n" % opacity, mode=0o644)
        fh.write_dms_colors(mode="dark", surface_dark="#1a1c22")

    def pid(self, rel=PROFILE):
        return bg.profile_id(str(self.fh.resolve(rel)))

    def sync(self, *extra, settings_doc=None, code=0, env=None):
        args = ["sync", "--settings", json.dumps(settings_doc or settings())] + list(extra)
        proc = self.fh.run_script(args, extra_env=dict(FAST, **(env or {})))
        self.assertEqual(proc.returncode, code, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        spec = SCHEMA["sync"] if code == 0 else SCHEMA["error"]
        self.assertEqual(test_contract.validate(doc, spec, DEFS), [], lines[0])
        return doc

    def mode(self, rel):
        return stat.S_IMODE(os.stat(str(self.fh.resolve(rel))).st_mode)

    def rule_on(self):
        return "opacity 1.0" in self.fh.read(NIRI_OUT)


class BasicSyncTest(SyncCase):

    def test_first_sync_installs(self):
        self.home()
        out = self.sync()
        self.assertTrue(out["glass"])
        self.assertEqual(out["reason"], "active")
        self.assertAlmostEqual(out["opacity"], 0.8)
        self.assertTrue(out["first_run"])
        self.assertEqual(out["changed"], [self.pid()])
        self.assertEqual(out["running_changed"], [])
        self.assertTrue(out["niri_changed"])
        self.assertEqual(out["warnings"], [])
        self.assertIn(IMPORT_CHROME, self.fh.read(PROFILE + "/chrome/userChrome.css").splitlines())
        self.assertIn("/* glass active", self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertIn(bg.V1_USERJS_BEGIN, self.fh.read(PROFILE + "/user.js"))
        self.assertEqual(self.mode(PROFILE + "/user.js"), 0o600)
        self.assertEqual(self.fh.read(NIRI_CONFIG).splitlines().count(INCLUDE), 1)
        self.assertEqual(self.mode(NIRI_CONFIG), 0o644)
        self.assertTrue(self.rule_on())
        self.assertEqual(self.mode(STATE), 0o700)
        self.assertEqual(self.mode(STATE + "/state.json"), 0o600)
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["version"], 1)
        record = state["profiles"][self.pid()]
        self.assertEqual(record["prefs_original"],
                         {p: {"absent": True} for p in bg.PREFS})
        self.assertFalse(record["glass_loaded_since_start"])
        self.assertTrue(record["applied_hash"])
        self.assertIn(self.pid(), state["backups"])

    def test_second_sync_writes_nothing(self):
        self.home()
        self.sync()
        before = self.fh.snapshot(".")
        times = {}
        for dirpath, dirnames, filenames in os.walk(str(self.fh.home)):
            for name in dirnames + filenames:
                st = os.lstat(os.path.join(dirpath, name))
                times[os.path.join(dirpath, name)] = (st.st_mtime_ns, st.st_ino)
        out = self.sync()
        self.assertEqual(out["changed"], [])
        self.assertFalse(out["niri_changed"])
        self.assertFalse(out["first_run"])
        self.assertEqual(self.fh.snapshot("."), before)
        for dirpath, dirnames, filenames in os.walk(str(self.fh.home)):
            for name in dirnames + filenames:
                st = os.lstat(os.path.join(dirpath, name))
                self.assertEqual((st.st_mtime_ns, st.st_ino), times[os.path.join(dirpath, name)],
                                 name)

    def test_invalid_settings_is_a_usage_error(self):
        self.home()
        proc = self.fh.run_script(["sync", "--settings", "[1, 2]"])
        self.assertEqual(proc.returncode, 2)
        doc = json.loads(proc.stdout)
        self.assertTrue(doc["error"].startswith("invalid --settings"), doc)
        self.assertFalse(self.fh.exists(PROFILE + "/user.js"))
        proc = self.fh.run_script(["sync"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", json.loads(proc.stdout))

    def settings_file(self, content, name="bg-settings.json"):
        path = self.fh.runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            path.write_text(content, encoding="utf-8")
            os.chmod(str(path), 0o600)
        return path

    def test_settings_file_is_read_then_deleted(self):
        # The daemon's input: the excluded sites stay out of the argv
        self.home()
        path = self.settings_file(json.dumps(settings(excluded=["example.org"], opacityOverride=True, opacity=0.6)))
        args = ["sync", "--settings-file", str(path)]
        proc = self.fh.run_script(args, extra_env=FAST)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertTrue(doc["glass"])
        self.assertAlmostEqual(doc["opacity"], 0.6)
        self.assertFalse(path.exists())
        # The same result as --settings: nothing left to change
        out = self.sync(settings_doc=settings(excluded=["example.org"], opacityOverride=True, opacity=0.6))
        self.assertEqual(out["changed"], [])
        self.assertFalse(out["niri_changed"])

    def test_bad_settings_file_is_a_usage_error(self):
        self.home()
        target = self.settings_file(json.dumps(settings()), "target.json")
        link = self.fh.runtime / "link.json"
        os.symlink(str(target), str(link))
        fifo = self.fh.runtime / "fifo.json"
        os.mkfifo(str(fifo))
        big = self.settings_file(" " * (bg.SETTINGS_FILE_MAX + 1), "big.json")
        bad = self.settings_file("[1, 2]", "bad.json")
        cases = [(self.fh.runtime / "missing.json", "invalid --settings-file"), (link, "invalid --settings-file"),
                 (fifo, "invalid --settings-file"), (big, "invalid --settings-file"), (bad, "invalid --settings")]
        for path, error in cases:
            with self.subTest(path=path.name):
                proc = self.fh.run_script(["sync", "--settings-file", str(path)], extra_env=FAST)
                self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
                self.assertTrue(json.loads(proc.stdout)["error"].startswith(error), proc.stdout)
        self.assertFalse(self.fh.exists(PROFILE + "/user.js"))
        # Regular files go even when refused; a symlink, its target and a fifo stay
        self.assertEqual([p.exists() or p.is_symlink() for p in (big, bad, link, target, fifo)],
                         [False, False, True, True, True])

    def test_settings_and_settings_file_are_exclusive(self):
        self.home()
        path = self.settings_file(json.dumps(settings()))
        proc = self.fh.run_script(["sync", "--settings", "{}", "--settings-file", str(path)])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", json.loads(proc.stdout))
        self.assertFalse(self.fh.exists(PROFILE + "/user.js"))

    def test_settings_change_rewrites_only_what_changed(self):
        self.home()
        self.sync()
        chrome_before = self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css")
        out = self.sync(settings_doc=settings(pagesTransparent=False))
        self.assertEqual(out["changed"], [self.pid()])
        self.assertEqual(self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css"), chrome_before)
        self.assertIn("page transparency disabled",
                      self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))
        self.assertIn('user_pref("browser.tabs.allow_transparent_browser", false);',
                      self.fh.read(PROFILE + "/user.js"))

    def test_data_option(self):
        self.home()
        out = self.sync("--data", str(self.fh.root / "missing"))
        self.assertEqual([w["code"] for w in out["warnings"]], ["data_unavailable"])
        self.assertNotIn("Site styles", self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))
        repo_data = str(test_contract.REPO / "data")
        out = self.sync("--data", repo_data)
        self.assertEqual(out["warnings"], [])
        self.assertIn("Site styles", self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))
        self.sync()
        self.assertNotIn("Site styles", self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))


class OptionsTest(SyncCase):

    def test_profile_option_limits_the_sync(self):
        self.home(profiles=(PROFILE, OTHER))
        out = self.sync("--profile", str(self.fh.resolve(OTHER)))
        self.assertEqual(out["changed"], [self.pid(OTHER)])
        self.assertFalse(self.fh.exists(PROFILE + "/user.js"))
        self.assertTrue(self.fh.exists(OTHER + "/user.js"))
        out = self.sync()
        self.assertEqual(out["changed"], [self.pid(PROFILE)])

    def test_profile_option_undiscovered_folder(self):
        self.home()
        loose = "elsewhere/scratch-profile"
        self.fh.write(loose + "/prefs.js", prefs_text({PREF_SCHEME: "2"}))
        out = self.sync("--profile", str(self.fh.resolve(loose)),
                        "--profile", str(self.fh.resolve("elsewhere/nope")))
        pid = self.pid(loose)
        self.assertEqual(out["changed"], [pid])
        self.assertEqual([w["code"] for w in out["warnings"]], ["profile_missing"])
        self.assertFalse(self.fh.exists(PROFILE + "/user.js"))
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"][pid]["prefs_original"][PREF_SCHEME], {"value": "2"})
        self.assertIsNone(state["profiles"][pid]["family"])

    def test_opacity_option(self):
        self.home(opacity="1.0")
        out = self.sync()
        self.assertFalse(out["glass"])
        self.assertEqual(out["reason"], "opaque")
        self.assertFalse(self.rule_on())
        out = self.sync("--opacity", "0.5")
        self.assertTrue(out["glass"])
        self.assertEqual(out["opacity"], 0.5)
        self.assertIn("rgba(26, 28, 34, 0.5)", self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertTrue(self.rule_on())
        out = self.sync("--opacity", "1")
        self.assertEqual(out["opacity"], 1.0)
        self.assertEqual(out["reason"], "opaque")
        for bad in ("7", "-1", "nan", "inf", "abc"):
            out = self.sync("--opacity", bad, code=2)
            self.assertIn("--opacity", out["error"])

    def test_off_option(self):
        self.home()
        self.sync()
        out = self.sync("--off")
        self.assertFalse(out["glass"])
        self.assertEqual(out["reason"], "forced_off")
        self.assertIn("neutral file", self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertFalse(self.rule_on(), "no browser runs: the rule goes at once")
        self.assertEqual(self.fh.read(NIRI_CONFIG).splitlines().count(INCLUDE), 1)

    def test_no_niri_folder(self):
        self.home()
        self.fh.write(".config/niri/config.kdl", "")
        os.unlink(str(self.fh.resolve(".config/niri/config.kdl")))
        os.unlink(str(self.fh.resolve(".config/niri/dms/windowrules.kdl")))
        os.rmdir(str(self.fh.resolve(".config/niri/dms")))
        os.rmdir(str(self.fh.resolve(".config/niri")))
        out = self.sync("--opacity", "0.8")
        self.assertFalse(out["niri_changed"])
        self.assertFalse(self.fh.exists(".config/niri"))


class RunningProfileTest(SyncCase):
    """H1 (rule removal deferred while a running browser has glass) and
    running_changed. A LockHolder plays the browser on .parentlock."""

    def browser(self, rel=PROFILE):
        holder = LockHolder(self.fh, rel + "/.parentlock")
        self.addCleanup(holder.stop)
        return holder

    def test_running_changed(self):
        self.home(profiles=(PROFILE, OTHER))
        self.browser(OTHER)
        out = self.sync()
        self.assertEqual(sorted(out["changed"]), sorted([self.pid(PROFILE), self.pid(OTHER)]))
        self.assertEqual(out["running_changed"], [self.pid(OTHER)])

    def test_rule_kept_while_glass_loaded(self):
        self.home()
        self.sync()                       # glass CSS on disk, browser closed
        holder = self.browser()           # the browser starts: it loads glass
        self.sync()                       # sees the new instance
        state = json.loads(self.fh.read(STATE + "/state.json"))
        record = state["profiles"][self.pid()]
        self.assertTrue(record["glass_loaded_since_start"])
        self.assertRegex(record["instance"], r"^[0-9]+:[0-9]+$")
        out = self.sync(settings_doc=settings(blur=False))
        self.assertEqual(out["reason"], "blur_disabled")
        self.assertIn("neutral file", self.fh.read(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertTrue(self.rule_on(), "rule removed while a running browser still has glass")
        self.assertFalse(out["niri_changed"])
        out = self.sync(settings_doc=settings(blur=False))
        self.assertTrue(self.rule_on())
        holder.release()                  # the browser quits
        out = self.sync(settings_doc=settings(blur=False))
        self.assertTrue(out["niri_changed"])
        self.assertFalse(self.rule_on())

    def test_browser_started_without_glass(self):
        self.home(opacity="1.0")
        self.sync()                       # neutral CSS on disk
        self.browser()                    # starts without glass
        self.sync("--opacity", "0.8")     # glass on: CSS and rule now
        self.assertTrue(self.rule_on())
        out = self.sync()                 # glass off again (opaque)
        self.assertEqual(out["reason"], "opaque")
        self.assertFalse(self.rule_on(), "this browser never loaded glass")

    def test_restart_with_glass_counts(self):
        self.home()
        holder = self.browser()
        self.sync()                       # browser was started before any glass
        self.assertFalse(json.loads(self.fh.read(STATE + "/state.json"))
                         ["profiles"][self.pid()]["glass_loaded_since_start"])
        holder.release()
        holder.stop()
        self.browser()                    # restart: now it has glass loaded
        self.sync(settings_doc=settings(glassEnabled=False))
        self.assertTrue(self.rule_on())


class PrefsTest(SyncCase):

    def test_site_theme_none_restores_user_pref(self):
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        userjs = self.fh.read(PROFILE + "/user.js")
        self.assertIn('user_pref("%s", 2);' % PREF_SCHEME, userjs)
        # The browser ran: prefs.js now holds our value.
        self.fh.write(PROFILE + "/prefs.js", prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"}))
        out = self.sync(settings_doc=settings(siteTheme="none"))
        self.assertEqual(out["changed"], [self.pid()])
        self.assertNotIn(PREF_SCHEME, self.fh.read(PROFILE + "/user.js"))
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"}))
        self.assertEqual(self.sync(settings_doc=settings(siteTheme="none"))["changed"], [])

    def test_site_theme_none_waits_for_the_browser(self):
        self.home()
        self.sync()
        ours = prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", ours)
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        self.sync(settings_doc=settings(siteTheme="none"))
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ours, "prefs.js written while running")
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"][self.pid()]["restore_prefs"], [PREF_SCHEME])
        holder.release()
        self.sync(settings_doc=settings(siteTheme="none"))
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({"browser.startup.page": "3"}))
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"][self.pid()]["restore_prefs"], [])

    def test_back_to_follow_cancels_the_restore(self):
        self.home()
        self.sync()
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        self.sync(settings_doc=settings(siteTheme="none"))
        self.sync(settings_doc=settings(siteTheme="dark"))
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"][self.pid()]["restore_prefs"], [])
        # No --plugin-dir: no companion pref in the block.
        self.assertEqual(state["profiles"][self.pid()]["owned_prefs"],
                         [p for p in bg.PREFS if p not in bg.COMPANION_PREFS])


class FilesTest(SyncCase):

    def test_charset_stays_first(self):
        self.home()
        self.fh.write(PROFILE + "/chrome/userChrome.css", '@charset "UTF-8";\n#nav-bar { color: red; }\n')
        self.sync()
        lines = self.fh.read(PROFILE + "/chrome/userChrome.css").splitlines()
        self.assertEqual(lines, ['@charset "UTF-8";', IMPORT_CHROME, "#nav-bar { color: red; }"])

    def test_modes_and_symlink_kept(self):
        self.home()
        self.fh.write("dotfiles/user.js", 'user_pref("a.b", 1);\n', mode=0o640)
        os.symlink("../../../dotfiles/user.js", str(self.fh.resolve(PROFILE + "/user.js")))
        self.fh.write(PROFILE + "/chrome/userContent.css", "/* mine */\n", mode=0o604)
        os.chmod(str(self.fh.resolve(NIRI_CONFIG)), 0o644)
        self.sync()
        link = str(self.fh.resolve(PROFILE + "/user.js"))
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), "../../../dotfiles/user.js")
        self.assertIn(bg.V1_USERJS_BEGIN, self.fh.read("dotfiles/user.js"))
        self.assertEqual(self.mode("dotfiles/user.js"), 0o640)
        self.assertEqual(self.mode(PROFILE + "/chrome/userContent.css"), 0o604)
        self.assertEqual(self.mode(NIRI_CONFIG), 0o644)

    def test_read_only_file_is_a_warning(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores file permissions")
        self.home()
        path = self.fh.write(PROFILE + "/chrome/userChrome.css", "/* locked */\n", mode=0o444)
        out = self.sync()
        self.assertEqual([(w["code"], w["profile"]) for w in out["warnings"]],
                         [("read_only", self.pid())])
        self.assertEqual(path.read_text(), "/* locked */\n")
        self.assertIn(bg.V1_USERJS_BEGIN, self.fh.read(PROFILE + "/user.js"))
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertIsNone(state["profiles"][self.pid()]["applied_hash"])

    def test_v0_cache_and_stale_tmp_removed(self):
        self.home()
        self.fh.write(".cache/dms/browserGlass/styles.json", "{}")
        self.fh.write(".cache/dms/browserGlass/.fetched", "")
        old = self.fh.write(PROFILE + "/.browserglass-user.js.abcd_123.tmp", "half")
        fresh = self.fh.write(PROFILE + "/.browserglass-prefs.js.zz99xx11.tmp", "busy")
        other = self.fh.write(PROFILE + "/.unrelated.abcdefgh.tmp", "x")
        mine = self.fh.write(PROFILE + "/.user.js.original.tmp", "user copy")
        niri_mine = self.fh.write(".config/niri/.config.kdl.20260101.tmp", "user copy")
        for path in (old, other, mine, niri_mine):
            os.utime(str(path), (1, 1))
        self.sync()
        self.assertFalse(self.fh.exists(".cache/dms/browserGlass"))
        self.assertTrue(self.fh.exists(".cache/dms/dms-colors.json"))
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue(other.exists())
        self.assertTrue(mine.exists())
        self.assertTrue(niri_mine.exists())


class StateLockTest(SyncCase):

    def test_concurrent_sync_is_refused(self):
        self.home()
        self.sync()
        before = self.fh.snapshot(".")
        with LockHolder(self.fh, STATE + "/state.lock", kind="flock"):
            out = self.sync("--opacity", "0.3", code=1)
            self.assertIn("lock", out["error"])
            self.assertEqual(self.fh.snapshot("."), before)
        self.assertEqual(self.sync("--opacity", "0.3")["changed"], [self.pid()])

    def test_corrupt_state_is_a_warning(self):
        self.home()
        self.sync()
        self.fh.write(STATE + "/state.json", "{not json")
        out = self.sync()
        self.assertFalse(out["first_run"])
        self.assertEqual([w["code"] for w in out["warnings"]], ["state_corrupt"])
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertIn(self.pid(), state["backups"], "backup record recovered from meta.json")


if __name__ == "__main__":
    unittest.main()

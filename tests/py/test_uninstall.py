"""browserglass.py uninstall, through the command line inside a FakeHome.

Nothing installed, a full install then uninstall, backups kept when the user
edited a file, the deferred prefs.js cleanup of a running profile (H6) and
the script run from its text alone (no file next to it, empty cwd).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import subprocess
import sys
import unittest

import test_contract
from fakehome import (PREFS_HEADER, SCRIPT, FakeHome, LockHolder, fake_home_pids,
                      kill_strays, load_script, wait_until)

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

ROOT = ".mozilla/firefox"
PROFILE = ROOT + "/abcd1234.default-release"
NIRI_CONFIG = ".config/niri/config.kdl"
NIRI_OUT = ".config/niri/dms-browser-glass.kdl"
STATE = ".local/state/dms/browserGlass"
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05", "BG_POLL_MAX": "20"}
# Runs the script text read from stdin: the size of an argv string is
# bounded (MAX_ARG_STRLEN), the script text is not.
BOOTSTRAP = "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))"


def prefs_text(prefs):
    return PREFS_HEADER + "".join('user_pref("%s", %s);\n' % kv for kv in sorted(prefs.items()))


def settings_json(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return json.dumps(doc)


class UninstallCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)

    def home(self, prefs=None):
        fh = self.fh
        fh.write(PROFILE + "/prefs.js", prefs_text(prefs or {"browser.startup.page": "3"}))
        fh.write_profiles_ini(ROOT, [{"name": "default-release",
                                      "path": os.path.basename(PROFILE), "default": True}])
        fh.write(NIRI_CONFIG, 'input {\n}\n\ninclude "dms/windowrules.kdl"\n', mode=0o644)
        fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.8\n}\n", mode=0o644)
        fh.write_dms_colors()

    def pid(self):
        return bg.profile_id(str(self.fh.resolve(PROFILE)))

    def check(self, proc, command):
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        self.assertEqual(test_contract.validate(doc, SCHEMA[command], DEFS), [], lines[0])
        return doc

    def sync(self, **over):
        return self.check(self.fh.run_script(["sync", "--settings", settings_json(**over)],
                                             extra_env=FAST), "sync")

    def uninstall(self):
        return self.check(self.fh.run_script(["uninstall"], extra_env=FAST), "uninstall")


class NothingInstalledTest(UninstallCase):

    def test_noop(self):
        self.home()
        before = self.fh.snapshot(".")
        out = self.uninstall()
        self.assertEqual(out, test_contract.load_json("uninstall-noop.json"))
        self.assertEqual(self.fh.snapshot("."), before)

    def test_empty_home(self):
        before = self.fh.snapshot(".")
        self.assertEqual(self.uninstall(), test_contract.load_json("uninstall-noop.json"))
        self.assertEqual(self.fh.snapshot("."), before)


class FullUninstallTest(UninstallCase):

    def test_install_then_uninstall(self):
        self.home(prefs={PREF_SCHEME: "2", "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/chrome/userChrome.css", "#nav-bar { color: red; }\n", mode=0o640)
        self.fh.write(".cache/dms/browserGlass/styles.json", "{}")
        before = self.fh.snapshot(".")
        self.sync()
        # The browser ran meanwhile: prefs.js holds the managed values.
        self.fh.write(PROFILE + "/prefs.js", prefs_text({
            PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
            "browser.startup.page": "3"}))
        out = self.uninstall()
        self.assertEqual(out["removed"], [self.pid()])
        self.assertEqual(out["restored"], [self.pid()])
        self.assertEqual(out["pending"], [])
        self.assertTrue(out["niri_changed"])
        self.assertTrue(out["state_removed"])
        self.assertFalse(out["v0_cache_removed"], "sync already removed it")
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.fh.snapshot("."), _without(before, ".cache/dms/browserGlass"))
        self.assertFalse(self.fh.exists(NIRI_OUT))
        self.assertFalse(self.fh.exists(STATE))
        self.assertFalse(self.fh.exists(".local/state/dms"), "created folders are removed")
        self.assertTrue(self.fh.exists(".local/state"))
        self.assertEqual(self.uninstall(), test_contract.load_json("uninstall-noop.json"))

    def test_edited_file_keeps_the_backup(self):
        self.home()
        self.fh.write(PROFILE + "/chrome/userChrome.css", "/* mine */\n")
        self.sync()
        text = self.fh.read(PROFILE + "/chrome/userChrome.css")
        self.fh.write(PROFILE + "/chrome/userChrome.css", text + "/* edited later */\n")
        out = self.uninstall()
        self.assertEqual([w["code"] for w in out["warnings"]], ["backup_kept"])
        self.assertFalse(out["state_removed"])
        self.assertEqual(self.fh.read(PROFILE + "/chrome/userChrome.css"),
                         "/* mine */\n/* edited later */\n")
        self.assertEqual(self.fh.read(STATE + "/backup/%s/userChrome.css" % self.pid()),
                         "/* mine */\n")
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"], {})
        self.assertIn(self.pid(), state["backups"])
        self.assertFalse(self.fh.exists(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertNotIn(bg.V1_USERJS_BEGIN, self.fh.read(PROFILE + "/user.js") if
                         self.fh.exists(PROFILE + "/user.js") else "")

    def test_v0_prefs_rule_without_state(self):
        self.home(prefs={PREF_SCHEME: "2", PREF_TRANSPARENT: "true", "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/chrome/dms-glass-chrome.css", "/* v0 */\n")
        out = self.uninstall()
        self.assertEqual(out["removed"], [self.pid()])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"}))


class DeferredCleanupTest(UninstallCase):
    """H6: a running browser rewrites prefs.js on exit, so the cleanup waits."""

    def test_pending_profile_cleaned_after_exit(self):
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        managed = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                              "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        self.assertTrue(out["state_removed"])
        self.assertEqual(len(fake_home_pids(self.fh)), 2, "holder plus the detached cleanup")
        wait_until(lambda: False, timeout=0.3)
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed, "written while running")
        holder.release()
        expected = prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == expected),
                        self.fh.read(PROFILE + "/prefs.js"))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE), "the cleanup removes its pending record")
        self.assertFalse(self.fh.exists(".local/state/dms"), "and the folders made for the state")

    def test_cleanup_gives_up_after_poll_max(self):
        self.home()
        self.sync()
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, BG_POLL_MAX="0.2"))
        self.assertEqual(self.check(proc, "uninstall")["pending"], [self.pid()])
        self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1, timeout=5),
                        "cleanup still polling past BG_POLL_MAX")


class InlineTextTest(UninstallCase):
    """The plugin keeps the script text in memory and runs it with no file
    next to it (the plugin folder may already be gone)."""

    def run_text(self, args, cwd):
        return subprocess.run(
            [sys.executable or "python3", "-I", "-c", BOOTSTRAP] + args,
            input=SCRIPT.read_text(encoding="utf-8"), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, universal_newlines=True, env=self.fh.env(FAST),
            cwd=cwd, timeout=60)

    def test_uninstall_from_stdin_text(self):
        self.home(prefs={PREF_SCHEME: "2", "browser.startup.page": "3"})
        self.sync()
        self.fh.write(PROFILE + "/prefs.js", prefs_text({PREF_SCHEME: "0", "browser.startup.page": "3"}))
        empty = self.fh.resolve("empty-cwd")
        empty.mkdir()
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.check(self.run_text(["uninstall"], str(empty)), "uninstall")
        self.assertEqual(out["pending"], [self.pid()])
        self.assertEqual(os.listdir(str(empty)), [])
        holder.release()
        expected = prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"})
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == expected),
                        self.fh.read(PROFILE + "/prefs.js"))
        self.assertFalse(self.fh.exists(STATE))

    # -- the sweep: `uninstall --if-gone <plugin.json>` from the text alone --

    def sweep(self, manifest, grace="0", cwd=None):
        env = dict(FAST, BG_SWEEP_GRACE=grace)
        return subprocess.run(
            [sys.executable or "python3", "-I", "-c", BOOTSTRAP, "uninstall", "--if-gone", manifest],
            input=SCRIPT.read_text(encoding="utf-8"), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, universal_newlines=True, env=self.fh.env(env),
            cwd=cwd or str(self.fh.home), timeout=60)

    def test_sweep_keeps_everything_while_the_manifest_exists(self):
        self.home()
        self.sync()
        manifest = self.fh.write(".config/DankMaterialShell/plugins/browserGlass/plugin.json", "{}")
        before = self.fh.snapshot()
        proc = self.sweep(str(manifest))
        self.assertEqual((proc.returncode, proc.stdout), (bg.EXIT_KEPT, ""), proc.stderr)
        self.assertEqual(self.fh.snapshot(), before)

    def test_sweep_uninstalls_once_the_manifest_is_gone(self):
        self.home()
        self.sync()
        manifest = self.fh.resolve(".config/DankMaterialShell/plugins/browserGlass/plugin.json")
        out = self.check(self.sweep(str(manifest)), "uninstall")
        self.assertEqual(out["pending"], [])
        self.assertFalse(self.fh.exists(STATE))
        self.assertFalse(self.fh.exists(NIRI_OUT))

    def test_sweep_waits_for_a_manifest_coming_back(self):
        # An update or reinstall writes plugin.json again during the grace
        self.home()
        self.sync()
        manifest = self.fh.resolve(".config/DankMaterialShell/plugins/browserGlass/plugin.json")
        before = self.fh.snapshot()
        proc = subprocess.Popen(
            [sys.executable or "python3", "-I", "-c", BOOTSTRAP, "uninstall", "--if-gone", str(manifest)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, env=self.fh.env(dict(FAST, BG_SWEEP_GRACE="1.5")),
            cwd=str(self.fh.home))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        proc.stdin.write(SCRIPT.read_text(encoding="utf-8"))
        proc.stdin.close()
        self.fh.write(".config/DankMaterialShell/plugins/browserGlass/plugin.json", "{}")
        out, err = proc.communicate(timeout=60)
        self.assertEqual((proc.returncode, out), (bg.EXIT_KEPT, ""), err)
        after = self.fh.snapshot()
        after.pop(".config/DankMaterialShell/plugins/browserGlass/plugin.json", None)
        self.assertEqual(_without(after, ".config/DankMaterialShell"),
                         _without(before, ".config/DankMaterialShell"))

    def test_uninstall_waits_for_a_running_sync(self):
        # No BG_LOCK_TIMEOUT: uninstall's own wait outlasts a short hold
        self.home()
        self.sync()
        holder = LockHolder(self.fh, STATE + "/state.lock", kind="flock")
        self.addCleanup(holder.stop)
        proc = subprocess.Popen(
            [sys.executable or "python3", "-I", str(SCRIPT), "uninstall"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=self.fh.env({"BG_POLL_INTERVAL": "0.05", "BG_POLL_MAX": "20"}),
            cwd=str(self.fh.home))
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        self.assertFalse(wait_until(lambda: proc.poll() is not None, timeout=bg.DEFAULT_LOCK_TIMEOUT + 1))
        holder.release()
        out, err = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 0, err)
        self.assertFalse(self.fh.exists(STATE))


def _without(snapshot, prefix):
    return {k: v for k, v in snapshot.items() if not (k == prefix or k.startswith(prefix + "/"))}


if __name__ == "__main__":
    unittest.main()

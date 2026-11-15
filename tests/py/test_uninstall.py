"""browserglass.py uninstall, through the command line inside a FakeHome.

Nothing installed, a full install then uninstall, backups kept when the user
edited a file, the deferred prefs.js cleanup of a running profile (H6) and
the script run from its text alone (no file next to it, empty cwd).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import signal
import subprocess
import sys
import time
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

    def test_unread_sync_settings_file_goes(self):
        # The daemon wrote the settings of a sync that never ran (disabled
        # within the debounce): uninstall removes that file, not a symlink.
        self.home()
        path = self.fh.runtime / bg.SYNC_SETTINGS_NAME
        path.write_text('{"excluded": ["example.org"]}', encoding="utf-8")
        self.assertEqual(self.uninstall(), test_contract.load_json("uninstall-noop.json"))
        self.assertFalse(os.path.lexists(str(path)))
        target = self.fh.runtime / "target.json"
        target.write_text("{}", encoding="utf-8")
        os.symlink(str(target), str(path))
        self.uninstall()
        self.assertTrue(os.path.islink(str(path)) and target.exists())


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

    def test_state_tidied_when_pending_not_written(self):
        # pending/<pid>.json cannot be written (EACCES): the cleaner still
        # cleans prefs.js once the browser exits. state.json keeps the
        # profile's record (unfinished) until a later uninstall, which then
        # removes the state folder and its parents.
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        managed = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                              "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        pdir = os.path.join(str(self.fh.home), STATE, bg.PENDING_DIR)
        os.makedirs(pdir, exist_ok=True)
        os.chmod(pdir, 0o500)
        self.addCleanup(lambda: os.path.isdir(pdir) and os.chmod(pdir, 0o700))
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        self.assertFalse(out["state_removed"])
        self.assertTrue(out["warnings"], "the pending record was not written")
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertFalse(state["synced"])
        self.assertIn(self.pid(), state["profiles"], "kept for a re-enable or a retry")
        holder.release()
        expected = prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == expected),
                        self.fh.read(PROFILE + "/prefs.js"))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE + "/" + bg.PENDING_DIR), "the cleanup tidies pending/")
        self.assertTrue(self.uninstall()["state_removed"])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), expected)
        self.assertFalse(self.fh.exists(STATE), "the retry removes the state folder")
        self.assertFalse(self.fh.exists(".local/state/dms"), "and the folders made for it")

    def test_cleanup_gives_up_after_poll_max(self):
        self.home()
        self.sync()
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, BG_POLL_MAX="0.2"))
        self.assertEqual(self.check(proc, "uninstall")["pending"], [self.pid()])
        self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1, timeout=5),
                        "cleanup still polling past BG_POLL_MAX")

    def cleaner_pid(self, holder):
        """The detached cleaner's pid, once it catches SIGTERM and SIGHUP."""
        pids = [p for p in fake_home_pids(self.fh) if p != holder.child.pid]
        self.assertEqual(len(pids), 1, "one detached cleanup")
        wanted = (1 << (signal.SIGTERM - 1)) | (1 << (signal.SIGHUP - 1))

        def catching():
            try:
                with open("/proc/%d/status" % pids[0]) as f:
                    line = next(l for l in f if l.startswith("SigCgt:"))
            except (OSError, StopIteration):
                return False
            return int(line.split()[1], 16) & wanted == wanted
        self.assertTrue(wait_until(catching), "the cleanup never caught SIGTERM")
        return pids[0]

    def running_uninstall(self, **env):
        """Sync, then uninstall while a lock holder plays the browser."""
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        managed = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                              "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, **env))
        self.assertEqual(self.check(proc, "uninstall")["pending"], [self.pid()])
        return holder, managed

    def test_sigterm_cleans_once_the_browser_exits(self):
        # Logout: the cleaner gets SIGTERM with the browser, which then
        # releases its lock. The 60 s probe interval would miss it; after
        # the signal the cleaner polls fast and cleans within its grace.
        holder, _ = self.running_uninstall(BG_POLL_INTERVAL="60", BG_TERM_GRACE="20")
        cleaner = self.cleaner_pid(holder)
        os.kill(cleaner, signal.SIGTERM)
        os.kill(cleaner, signal.SIGHUP)  # logind sends both
        wait_until(lambda: False, timeout=0.3)
        self.assertIn(cleaner, fake_home_pids(self.fh), "SIGTERM killed the cleanup")
        holder.release()
        expected = prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == expected, timeout=5),
                        self.fh.read(PROFILE + "/prefs.js"))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh), timeout=5), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE), "the cleanup removes its pending record")
        self.assertFalse(self.fh.exists(".local/state/dms"), "and the folders made for the state")

    def test_sigterm_gives_up_after_grace(self):
        # The browser never lets go: the cleaner exits after its grace time
        # and keeps the pending file for a later sync or uninstall.
        holder, managed = self.running_uninstall(BG_POLL_INTERVAL="60", BG_TERM_GRACE="0.5")
        cleaner = self.cleaner_pid(holder)
        os.kill(cleaner, signal.SIGTERM)
        self.assertTrue(wait_until(lambda: cleaner not in fake_home_pids(self.fh), timeout=5),
                        "cleanup still polling past BG_TERM_GRACE")
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed)
        self.assertTrue(self.fh.exists("%s/%s/%s.json" % (STATE, bg.PENDING_DIR, self.pid())),
                        "the pending file stays for a retry")

    def test_sigterm_default_grace_ends_before_the_shell_stop_timeout(self):
        # A shell restart (dms.service, TimeoutStopSec=10) stops the cleaner
        # while the browser stays open: it exits well before SIGKILL.
        holder, managed = self.running_uninstall(BG_POLL_INTERVAL="60")
        cleaner = self.cleaner_pid(holder)
        start = time.monotonic()
        os.kill(cleaner, signal.SIGTERM)
        self.assertTrue(wait_until(lambda: cleaner not in fake_home_pids(self.fh), timeout=10),
                        "cleanup still polling")
        self.assertLess(time.monotonic() - start, bg.DEFAULT_TERM_GRACE + 2)
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed)

    def test_unrecorded_job_dropped_by_reenable(self):
        # pending/<pid>.json cannot be written, then the plugin is enabled
        # again before the browser exits: the sync records the profile, so
        # the cleaner must not rewrite prefs.js behind it.
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        managed = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                              "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        pdir = os.path.join(str(self.fh.home), STATE, bg.PENDING_DIR)
        os.makedirs(pdir, exist_ok=True)
        os.chmod(pdir, 0o500)
        self.addCleanup(lambda: os.path.isdir(pdir) and os.chmod(pdir, 0o700))
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        self.assertTrue(out["warnings"], "the pending record was not written")
        os.chmod(pdir, 0o700)
        self.sync()
        state = json.loads(self.fh.read(STATE + "/state.json"))
        originals = state["profiles"][self.pid()]["prefs_original"]
        self.assertEqual(originals[PREF_SCHEME], {"value": "1"}, "the user's original, not ours")
        self.assertEqual(originals[PREF_TRANSPARENT], {"absent": True})
        self.assertEqual(originals[PREF_STYLESHEETS], {"absent": True})
        holder.release()
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed, "the cleaner was not cancelled")
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertIn(self.pid(), state["profiles"], "the sync's record stays")
        self.uninstall()
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"}))

    def test_unrecorded_job_runs_over_a_stale_state(self):
        # The state folder cannot be written at all: the uninstall can
        # neither record the job nor clear state.json, whose last sync still
        # lists the profile. That stale record must not cancel the cleaner.
        self.home(prefs={PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.sync()
        managed = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                              "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        sdir = os.path.join(str(self.fh.home), STATE)
        os.chmod(sdir, 0o500)
        self.addCleanup(lambda: os.path.isdir(sdir) and os.chmod(sdir, 0o700))
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        self.assertTrue(json.loads(self.fh.read(STATE + "/state.json"))["synced"], "stale state")
        holder.release()
        expected = prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"})
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == expected),
                        self.fh.read(PROFILE + "/prefs.js"))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")


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
        proc.stdin = None  # communicate() flushes a closed stdin before Python 3.13
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

"""Uninstall robustness: the H2 originals survive a killed deferred cleanup,
a re-enable while the browser runs, a lost or corrupt state, and files that
cannot be cleaned yet (read-only, unremovable); one bad profile never stops
the others."""

import json
import os
import shutil
import signal
import subprocess
import sys
import unittest

import test_contract
from fakehome import SCRIPT, LockHolder, fake_home_pids, wait_until
from test_uninstall import (BOOTSTRAP, FAST, PREF_SCHEME, PREF_STYLESHEETS, PREF_TRANSPARENT,
                            PROFILE, ROOT, STATE, UninstallCase, bg, prefs_text)

ORIGINAL = prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"})
# prefs.js as a running browser rewrites it while our block is in user.js.
MANAGED = prefs_text({PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true",
                      "browser.startup.page": "3"})


class RobustCase(UninstallCase):

    def setUp(self):
        super().setUp()
        self.home(prefs={PREF_SCHEME: "2", "browser.startup.page": "3"})

    def browser_ran(self):
        self.fh.write(PROFILE + "/prefs.js", MANAGED)

    def hold(self):
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        return holder

    def pending_path(self):
        return STATE + "/pending/%s.json" % self.pid()

    def kill_cleaners(self, holder):
        for pid in fake_home_pids(self.fh):
            if pid != holder.child.pid:
                os.kill(pid, signal.SIGKILL)
        self.assertTrue(wait_until(lambda: fake_home_pids(self.fh) == [holder.child.pid]))

    def state(self):
        return json.loads(self.fh.read(STATE + "/state.json"))

    def run_failing(self, args):
        proc = self.fh.run_script(args, extra_env=FAST)
        self.assertEqual(proc.returncode, 1, proc.stdout)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, test_contract.SCHEMA["error"], test_contract.DEFS),
                         [], proc.stdout)
        return doc


class PendingRecordTest(RobustCase):

    def test_killed_cleaner_then_second_uninstall(self):
        self.sync()
        self.browser_ran()
        holder = self.hold()
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        self.assertTrue(out["state_removed"])
        self.assertTrue(self.fh.exists(self.pending_path()))
        self.assertFalse(self.fh.exists(STATE + "/state.json"))
        self.kill_cleaners(holder)  # logout, OOM, cgroup stop
        holder.release()
        out = self.uninstall()
        self.assertIn(self.pid(), out["restored"])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)
        self.assertFalse(self.fh.exists(STATE))

    def test_killed_cleaner_then_clean_prefs(self):
        self.sync()
        self.browser_ran()
        holder = self.hold()
        self.uninstall()
        self.kill_cleaners(holder)
        holder.release()
        proc = self.fh.run_script(["clean-prefs", str(self.fh.resolve(PROFILE))], extra_env=FAST)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)
        self.assertFalse(self.fh.exists(STATE))

    def test_reenable_while_running_keeps_the_originals(self):
        self.sync()
        self.browser_ran()
        holder = self.hold()
        self.assertEqual(self.uninstall()["pending"], [self.pid()])
        self.sync()  # re-enabled while the browser still runs
        record = self.state()["profiles"][self.pid()]
        self.assertEqual(record["prefs_original"][PREF_SCHEME], {"value": "2"})
        self.assertEqual(record["prefs_original"][PREF_TRANSPARENT], {"absent": True})
        self.assertFalse(self.fh.exists(self.pending_path()), "the sync took the profile back")
        holder.release()  # browser closes: the stale cleaner must not undo the block
        self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1))
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), MANAGED)
        holder.stop()
        holder = self.hold()  # runs again, then disable while running
        self.assertEqual(self.uninstall()["pending"], [self.pid()])
        holder.release()
        self.assertTrue(wait_until(lambda: self.fh.read(PROFILE + "/prefs.js") == ORIGINAL),
                        self.fh.read(PROFILE + "/prefs.js"))
        self.assertTrue(wait_until(lambda: not self.fh.exists(STATE)), "state folder left")

    def test_reenable_when_glass_no_longer_owns_a_pref(self):
        self.sync()
        self.browser_ran()
        holder = self.hold()
        self.uninstall()
        self.sync(siteTheme="none")  # content-override is the user's again
        holder.release()
        holder.stop()
        self.sync(siteTheme="none")  # browser closed: the left-over 0 is restored
        self.assertIn('user_pref("%s", 2);' % PREF_SCHEME, self.fh.read(PROFILE + "/prefs.js"))
        self.uninstall()
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)


class LostStateTest(RobustCase):

    def ran_and_closed(self):
        self.sync()
        self.browser_ran()

    def test_corrupt_state(self):
        self.ran_and_closed()
        self.fh.write(STATE + "/state.json", '{"version": 1, "prof')
        out = self.sync()
        self.assertEqual([w["code"] for w in out["warnings"]], ["state_corrupt"])
        self.assertEqual(self.state()["profiles"][self.pid()]["prefs_original"][PREF_SCHEME],
                         {"value": "2"})
        self.uninstall()
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)

    def test_deleted_state_then_sync(self):
        self.ran_and_closed()
        os.unlink(str(self.fh.resolve(STATE + "/state.json")))
        self.sync()
        self.uninstall()
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)

    def test_deleted_state_then_uninstall(self):
        self.ran_and_closed()
        os.unlink(str(self.fh.resolve(STATE + "/state.json")))
        out = self.uninstall()
        self.assertTrue(out["state_removed"])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)
        self.assertFalse(self.fh.exists(PROFILE + "/chrome"))

    def test_newer_state_is_never_overwritten(self):
        self.ran_and_closed()
        newer = '{"version": 2, "future": true}\n'
        self.fh.write(STATE + "/state.json", newer)
        self.assertIn("newer", self.run_failing(["sync", "--settings", "{}"])["error"])
        self.assertIn("newer", self.run_failing(["uninstall"])["error"])
        self.assertEqual(self.fh.read(STATE + "/state.json"), newer)
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), MANAGED)


class UnfinishedTest(RobustCase):

    def test_read_only_prefs_keeps_the_record(self):
        self.sync()
        self.browser_ran()
        prefs = self.fh.resolve(PROFILE + "/prefs.js")
        os.chmod(str(prefs), 0o400)
        out = self.uninstall()
        self.assertIn("read_only", [w["code"] for w in out["warnings"]])
        self.assertFalse(out["state_removed"])
        self.assertIn(self.pid(), self.state()["profiles"])
        os.chmod(str(prefs), 0o600)
        out = self.uninstall()
        self.assertEqual(out["warnings"], [])
        self.assertTrue(out["state_removed"])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)

    def test_read_only_user_file_is_left_alone(self):
        css = PROFILE + "/chrome/userChrome.css"
        self.fh.write(css, "#nav-bar { color: red; }\n", mode=0o644)
        self.fh.write(PROFILE + "/user.js", 'user_pref("a.b", 1);\n', mode=0o600)
        before = self.fh.snapshot(".")
        self.sync()
        os.chmod(str(self.fh.resolve(css)), 0o444)
        os.chmod(str(self.fh.resolve(PROFILE + "/user.js")), 0o400)
        out = self.uninstall()
        codes = [w["code"] for w in out["warnings"]]
        self.assertEqual(codes.count("read_only"), 2, out)
        self.assertFalse(out["state_removed"])
        self.assertEqual(os.stat(str(self.fh.resolve(css))).st_mode & 0o777, 0o444)
        self.assertEqual(os.stat(str(self.fh.resolve(PROFILE + "/user.js"))).st_mode & 0o777, 0o400)
        self.assertIn(bg.V1_IMPORT_CHROME, self.fh.read(css))
        self.assertIn(bg.V1_USERJS_BEGIN, self.fh.read(PROFILE + "/user.js"))
        os.chmod(str(self.fh.resolve(css)), 0o644)
        os.chmod(str(self.fh.resolve(PROFILE + "/user.js")), 0o600)
        out = self.uninstall()
        self.assertEqual(out["warnings"], [])
        self.assertTrue(out["state_removed"])
        self.assertEqual(self.fh.snapshot("."), before)

    def test_unremovable_profile_does_not_stop_the_others(self):
        other = ROOT + "/efgh5678.other"
        self.fh.write(other + "/prefs.js", ORIGINAL)
        self.fh.write_profiles_ini(ROOT, [
            {"name": "default-release", "path": os.path.basename(PROFILE), "default": True},
            {"name": "other", "path": os.path.basename(other)}])
        self.sync()
        locked = self.fh.resolve(other + "/chrome")
        os.chmod(str(locked), 0o500)
        self.addCleanup(lambda: locked.exists() and os.chmod(str(locked), 0o755))
        out = self.uninstall()
        other_id = bg.profile_id(str(self.fh.resolve(other)))
        self.assertIn(self.pid(), out["removed"])
        self.assertIn(other_id, [w["profile"] for w in out["warnings"]])
        self.assertFalse(self.fh.exists(".config/niri/dms-browser-glass.kdl"))
        self.assertFalse(self.fh.exists(PROFILE + "/chrome/dms-glass-chrome.css"))
        self.assertFalse(out["state_removed"])
        self.assertEqual(list(self.state()["profiles"]), [other_id])
        os.chmod(str(locked), 0o755)
        out = self.uninstall()
        self.assertEqual(out["warnings"], [])
        self.assertTrue(out["state_removed"])
        self.assertFalse(self.fh.exists(other + "/chrome"))

    def test_no_state_folder_possible(self):
        self.sync()
        state_root = self.fh.resolve(".local/state")
        shutil.rmtree(str(self.fh.resolve(".local/state/dms")))
        os.chmod(str(state_root), 0o555)
        self.addCleanup(os.chmod, str(state_root), 0o755)
        out = self.uninstall()
        self.assertIn(self.pid(), out["removed"])
        self.assertFalse(self.fh.exists(PROFILE + "/chrome/dms-glass-chrome.css"))

    def test_state_lock_unusable(self):
        self.sync()
        os.unlink(str(self.fh.resolve(STATE + "/state.lock")))
        os.mkdir(str(self.fh.resolve(STATE + "/state.lock")))
        out = self.uninstall()
        self.assertEqual([w["code"] for w in out["warnings"]], ["state_unavailable"])
        self.assertTrue(out["state_removed"])
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), ORIGINAL)


class KeptBackupTest(RobustCase):

    def test_backup_kept_is_reported_once(self):
        css = PROFILE + "/chrome/userChrome.css"
        self.fh.write(css, "/* mine */\n")
        self.sync()
        self.fh.write(css, self.fh.read(css) + "/* edited later */\n")
        self.assertEqual([w["code"] for w in self.uninstall()["warnings"]], ["backup_kept"])
        self.assertEqual(self.uninstall()["warnings"], [])
        self.assertTrue(self.sync()["first_run"])


class SyncEdgeTest(RobustCase):

    def test_owned_again_takes_the_users_new_value(self):
        # H3: the user changed the pref while glass did not own it.
        self.sync()
        self.browser_ran()
        self.sync(siteTheme="none")
        self.assertIn('user_pref("%s", 2);' % PREF_SCHEME, self.fh.read(PROFILE + "/prefs.js"))
        self.fh.write(PROFILE + "/prefs.js", prefs_text({PREF_SCHEME: "1", PREF_TRANSPARENT: "true",
                                                         PREF_STYLESHEETS: "true",
                                                         "browser.startup.page": "3"}))
        self.sync()
        self.browser_ran()
        self.uninstall()
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "1", "browser.startup.page": "3"}))

    def test_dangling_link_is_left_alone(self):
        outside = self.fh.root / "outside"
        outside.mkdir()
        link = self.fh.resolve(PROFILE + "/chrome/userContent.css")
        link.parent.mkdir(parents=True)
        os.symlink(str(outside / "missing" / "dir" / "uc.css"), str(link))
        before = self.fh.snapshot(".")
        out = self.sync()
        self.assertIn("dangling_link", [w["code"] for w in out["warnings"]])
        self.assertEqual(os.listdir(str(outside)), [])
        self.uninstall()
        self.assertEqual(self.fh.snapshot("."), before)

    def test_dangling_chrome_folder_link_is_left_alone(self):
        outside = self.fh.root / "outside"
        outside.mkdir()
        chrome = self.fh.resolve(PROFILE + "/chrome")
        os.symlink(str(outside / "missing" / "chrome"), str(chrome))
        before = self.fh.snapshot(".")
        out = self.sync()
        self.assertIn("dangling_link", [w["code"] for w in out["warnings"]])
        self.assertEqual(os.listdir(str(outside)), [])
        self.uninstall()
        self.assertEqual(os.listdir(str(outside)), [])
        self.assertEqual(self.fh.snapshot("."), before)

    def test_bad_backup_mode_is_ignored(self):
        css = PROFILE + "/chrome/userChrome.css"
        for bad in (-1, 2 ** 40):
            with self.subTest(mode=bad):
                self.fh.write(css, "/* mine */\n", mode=0o644)
                self.sync()
                doc = self.state()
                doc["backups"][self.pid()]["files"]["userChrome.css"]["mode"] = bad
                self.fh.write(STATE + "/state.json", json.dumps(doc))
                self.uninstall()
                self.assertEqual(self.fh.read(css), "/* mine */\n")
                mode = os.stat(str(self.fh.resolve(css))).st_mode
                self.assertEqual(mode & ~0o777 & 0o7777, 0, oct(mode))

    def test_empty_chrome_folder_survives(self):
        chrome = self.fh.resolve(PROFILE + "/chrome")
        chrome.mkdir()
        before = self.fh.snapshot(".")
        self.sync()
        self.uninstall()
        self.assertEqual(self.fh.snapshot("."), before)


class TransportTest(unittest.TestCase):
    """The script text runs from stdin: its size is not bounded by the
    128 KiB of one argv string (MAX_ARG_STRLEN)."""

    def test_bootstrap(self):
        self.assertEqual(bg.STDIN_BOOTSTRAP, BOOTSTRAP)
        self.assertLess(len(bg.STDIN_BOOTSTRAP.encode()), 1024)

    def test_any_size(self):
        text = SCRIPT.read_text(encoding="utf-8") + "\n#" + "x" * 200000 + "\n"
        proc = subprocess.run([sys.executable or "python3", "-I", "-c", bg.STDIN_BOOTSTRAP, "--version"],
                              input=text, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=60, cwd="/")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "browserglass " + bg.VERSION)


if __name__ == "__main__":
    unittest.main()

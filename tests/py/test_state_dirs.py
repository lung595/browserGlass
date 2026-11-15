"""The folders made for the state folder (state.created_dirs, e.g.
~/.local/state/dms) outlive a second uninstall, a sync taking a deferred
profile back, and a lost or corrupt state.json (state-dirs.json); they go
once empty, never otherwise. Also the scope prefs restored when no record
is left (prefs_plan_lost).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import tempfile
import unittest

from fakehome import LockHolder, fake_home_pids, load_script, wait_until
from test_uninstall import FAST, PROFILE, ROOT, STATE, UninstallCase

bg = load_script()
DMS = ".local/state/dms"
OTHER = DMS + "/other.txt"
AUTO = bg.PREF_AUTODISABLE
SCAN = bg.PREF_STARTUP_SCAN


class StateDirsTest(UninstallCase):

    def assert_dms(self, keep_other):
        if keep_other:
            self.assertTrue(self.fh.exists(OTHER), "a folder holding another file stays")
        else:
            self.assertFalse(self.fh.exists(DMS), "the folder made for the state goes")
        self.assertFalse(self.fh.exists(STATE))

    def running(self):
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        return holder

    def test_sync_take_back_then_uninstall(self):
        for keep_other in (False, True):
            with self.subTest(keep_other=keep_other):
                self.setUp()
                self.home()
                self.sync()
                holder = self.running()
                self.assertEqual(self.uninstall()["pending"], [self.pid()])
                self.sync()  # re-enabled while the browser runs
                self.assertFalse(self.fh.exists(STATE + "/pending"))
                state = json.loads(self.fh.read(STATE + "/" + bg.STATE_FILE))
                self.assertIn(str(self.fh.resolve(DMS)), state["created_dirs"])
                holder.release()
                self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1, timeout=10),
                                "the taken-back cleaner did not exit")
                if keep_other:
                    self.fh.write(OTHER, "x\n")
                self.assertEqual(self.uninstall()["pending"], [])
                self.assert_dms(keep_other)

    def test_cleaner_gave_up_then_uninstall_again(self):
        for keep_other in (False, True):
            with self.subTest(keep_other=keep_other):
                self.setUp()
                self.home()
                self.sync()
                holder = self.running()
                proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, BG_POLL_MAX="0.2"))
                self.assertEqual(self.check(proc, "uninstall")["pending"], [self.pid()])
                self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1, timeout=5),
                                "cleanup still polling past BG_POLL_MAX")
                pend = json.loads(self.fh.read("%s/%s/%s.json" % (STATE, bg.PENDING_DIR, self.pid())))
                self.assertIn(str(self.fh.resolve(DMS)), pend["created_dirs"])
                holder.release()
                if keep_other:
                    self.fh.write(OTHER, "x\n")
                self.assertEqual(self.uninstall()["pending"], [])
                self.assert_dms(keep_other)

    def test_second_deferred_uninstall_keeps_the_folders(self):
        # The cleaner gave up and the browser still runs: the new pending
        # file still lists the state folders, and its cleaner removes them.
        self.home()
        self.sync()
        holder = self.running()
        proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, BG_POLL_MAX="0.2"))
        self.check(proc, "uninstall")
        self.assertTrue(wait_until(lambda: len(fake_home_pids(self.fh)) == 1, timeout=5))
        self.assertEqual(self.uninstall()["pending"], [self.pid()])
        pend = json.loads(self.fh.read("%s/%s/%s.json" % (STATE, bg.PENDING_DIR, self.pid())))
        self.assertIn(str(self.fh.resolve(DMS)), pend["created_dirs"])
        holder.release()
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assert_dms(False)

    def test_state_json_corrupt_or_deleted_then_uninstall(self):
        for kind in ("corrupt", "deleted"):
            for keep_other in (False, True):
                with self.subTest(kind=kind, keep_other=keep_other):
                    self.setUp()
                    self.home()
                    self.sync()
                    sidecar = json.loads(self.fh.read(STATE + "/" + bg.STATE_DIRS))
                    self.assertIn(str(self.fh.resolve(DMS)), sidecar)
                    if kind == "corrupt":
                        self.fh.write(STATE + "/" + bg.STATE_FILE, '{"version": 1, "prof', mode=0o600)
                    else:
                        os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
                    if keep_other:
                        self.fh.write(OTHER, "x\n")
                    self.uninstall()
                    self.assert_dms(keep_other)

    def test_no_state_uninstall_saving_a_state_keeps_its_folders(self):
        # No state at all: one profile deferred (running), one unfinished
        # (read-only chrome folder). The saved state.json lists the folders
        # this uninstall made for it.
        second = ROOT + "/efgh5678.second"
        self.fh.write(PROFILE + "/prefs.js", "")
        self.fh.write(second + "/prefs.js", "")
        self.fh.write_profiles_ini(ROOT, [
            {"name": "default-release", "path": os.path.basename(PROFILE), "default": True},
            {"name": "second", "path": os.path.basename(second)}])
        for rel in (PROFILE, second):
            self.fh.write(rel + "/chrome/dms-glass-chrome.css", "/* v0 */\n")
        chrome = str(self.fh.resolve(second + "/chrome"))
        os.chmod(chrome, 0o500)
        self.addCleanup(os.chmod, chrome, 0o700)
        self.running()
        out = self.uninstall()
        self.assertEqual(out["pending"], [self.pid()])
        state = json.loads(self.fh.read(STATE + "/" + bg.STATE_FILE))
        self.assertIn(str(self.fh.resolve(DMS)), state["created_dirs"])
        self.assertIn(str(self.fh.resolve(STATE)), state["created_dirs"])


class StateDirsFileTest(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.sdir = os.path.join(tmp.name, "state")
        os.mkdir(self.sdir)

    def test_kept_beside_state_json(self):
        state = bg.new_state()
        state["created_dirs"] = ["/x/b", "/x/a"]
        self.assertTrue(bg.state_save(self.sdir, state, []))
        with open(os.path.join(self.sdir, bg.STATE_DIRS), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), ["/x/a", "/x/b"])
        os.unlink(os.path.join(self.sdir, bg.STATE_FILE))
        self.assertEqual(bg.state_load(self.sdir, [])[0]["created_dirs"], ["/x/a", "/x/b"])
        with open(os.path.join(self.sdir, bg.STATE_FILE), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        warnings = []
        self.assertEqual(bg.state_load(self.sdir, warnings)[0]["created_dirs"], ["/x/a", "/x/b"])
        self.assertEqual([w["code"] for w in warnings], [bg.WARN_STATE_CORRUPT])
        state["created_dirs"] = []
        self.assertTrue(bg.state_save(self.sdir, state, []))
        self.assertFalse(os.path.exists(os.path.join(self.sdir, bg.STATE_DIRS)))

    def test_odd_file_ignored(self):
        with open(os.path.join(self.sdir, bg.STATE_DIRS), "w", encoding="utf-8") as fh:
            fh.write('{"a": 1}')
        self.assertEqual(bg.state_load(self.sdir, [])[0]["created_dirs"], [])


class PlanLostScopesTest(unittest.TestCase):

    def plan(self, originals):
        block = dict(bg.companion_prefs(originals))
        text = "".join('user_pref("%s", %s);\n' % kv for kv in sorted(block.items()))
        return block, dict(bg.prefs_plan_lost(text, block))

    def test_non_default_originals_come_back(self):
        block, plan = self.plan({AUTO: "11", SCAN: "2"})
        self.assertEqual((block[AUTO], block[SCAN]), ("10", "3"))
        self.assertEqual((plan[AUTO], plan[SCAN]), ("11", "2"))
        self.assertIsNone(plan[bg.PREF_SIGNATURES])

    def test_default_derived_values_are_deleted(self):
        _, plan = self.plan({})
        self.assertEqual((plan[AUTO], plan[SCAN]), (None, None))
        _, plan = self.plan({AUTO: "15", SCAN: "0"})
        self.assertEqual((plan[AUTO], plan[SCAN]), (None, None))

    def test_a_value_consistent_with_the_block(self):
        # 10 and 3 could come from 10/11 and 2/3: one of them, never the
        # default (15, 0) that deleting the line gives.
        _, plan = self.plan({AUTO: "10", SCAN: "3"})
        self.assertEqual((plan[AUTO], plan[SCAN]), ("11", "2"))
        text = 'user_pref("%s", 10);\nuser_pref("%s", 3);\n' % (AUTO, SCAN)
        new = bg.prefs_restore(text, bg.prefs_plan_lost(text, {AUTO: "10", SCAN: "3"}))
        self.assertEqual(bg.parse_prefs(new), {AUTO: "11", SCAN: "2"})

    def test_user_value_kept(self):
        text = 'user_pref("%s", 3);\n' % AUTO
        self.assertEqual(bg.prefs_plan_lost(text, {AUTO: "10"}), [])

    def test_originals_keep_the_guess(self):
        # The originals saved next to the lost-state plan (pending file, a
        # sync's take-back) hold the same guessed scope values.
        block, _ = self.plan({AUTO: "11", SCAN: "2"})
        with tempfile.TemporaryDirectory() as profile:
            text = "".join('user_pref("%s", %s);\n' % kv for kv in sorted(block.items()))
            with open(os.path.join(profile, bg.PREFS_JS), "w", encoding="utf-8") as fh:
                fh.write(text)
            ctx = {"pending": {}, "state": {"backups": {}}}
            plan, originals = bg._uninstall_plan(ctx, "0" * 12, profile, None, True,
                                                 bg.userjs_block_text(sorted(block.items())))
        self.assertEqual(dict(plan)[AUTO], "11")
        self.assertEqual((originals[AUTO], originals[SCAN]), ({"value": "11"}, {"value": "2"}))
        guess = {p: item.get("value") for p, item in originals.items()}
        self.assertEqual(dict(bg.companion_prefs(guess))[AUTO], block[AUTO])


class UnrecordedJobTest(unittest.TestCase):
    """An unrecorded cleaner job is cancelled only by a sync's record."""

    def test_only_a_synced_record_cancels(self):
        with tempfile.TemporaryDirectory() as sdir:
            pid = "a" * 12
            state = bg.new_state()
            state["profiles"][pid] = bg._norm_record({"path": "/p"})
            for synced in (False, True):
                state["synced"] = synced
                self.assertTrue(bg.state_save(sdir, state, []))
                self.assertIs(bg._state_has_profile(sdir, pid), synced)


if __name__ == "__main__":
    unittest.main()

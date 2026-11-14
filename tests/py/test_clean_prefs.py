"""browserglass.py clean-prefs PROFILE... (internal, H6), inside a FakeHome.

It waits until each profile is free, cleans prefs.js, prints nothing and
exits 0: with a v1 state it restores the recorded originals, without one it
deletes only the values v0 could have written.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import subprocess
import sys
import unittest

import test_contract
from fakehome import PREFS_HEADER, SCRIPT, FakeHome, LockHolder, kill_strays, load_script, wait_until

bg = load_script()

PROFILE = ".mozilla/firefox/abcd1234.default-release"
STATE = ".local/state/dms/browserGlass"
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
FAST = {"BG_POLL_INTERVAL": "0.05", "BG_POLL_MAX": "20"}


def prefs_text(prefs):
    return PREFS_HEADER + "".join('user_pref("%s", %s);\n' % kv for kv in sorted(prefs.items()))


class CleanPrefsTest(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)

    def path(self, rel=PROFILE):
        return str(self.fh.resolve(rel))

    def run_clean(self, *profiles, env=None):
        proc = self.fh.run_script(["clean-prefs"] + list(profiles), extra_env=dict(FAST, **(env or {})),
                                  timeout=30)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)
        return proc

    def test_v0_rule_without_state(self):
        self.fh.write(PROFILE + "/prefs.js", prefs_text({
            PREF_SCHEME: "2", PREF_TRANSPARENT: "false", PREF_STYLESHEETS: "true",
            "browser.startup.page": "3"}))
        self.run_clean(self.path())
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "2", "browser.startup.page": "3"}))

    def test_record_restores_originals(self):
        self.fh.write(PROFILE + "/prefs.js", prefs_text({
            PREF_SCHEME: "0", PREF_TRANSPARENT: "true", PREF_STYLESHEETS: "true"}))
        pid = bg.profile_id(self.path())
        state = bg.new_state()
        record = bg._norm_record({"path": self.path()})
        record["prefs_original"] = {PREF_SCHEME: {"value": "2"}, PREF_TRANSPARENT: {"absent": True},
                                    PREF_STYLESHEETS: {"value": "true"}}
        record["owned_prefs"] = [PREF_SCHEME, PREF_TRANSPARENT, PREF_STYLESHEETS]
        state["profiles"][pid] = record
        self.fh.write(STATE + "/state.json", bg.state_text(state))
        self.run_clean(self.path())
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({PREF_SCHEME: "2", PREF_STYLESHEETS: "true"}))

    def test_waits_while_running(self):
        managed = prefs_text({PREF_SCHEME: "0", "browser.startup.page": "3"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        holder = LockHolder(self.fh, PROFILE + "/.parentlock")
        self.addCleanup(holder.stop)
        child = subprocess.Popen(
            [sys.executable or "python3", "-I", str(SCRIPT), "clean-prefs", self.path()],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
            env=self.fh.env(FAST), cwd=str(self.fh.home))
        self.addCleanup(_reap, child)
        wait_until(lambda: child.poll() is not None, timeout=0.4)
        self.assertIsNone(child.poll(), "clean-prefs did not wait for the browser")
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed)
        holder.release()
        stdout, stderr = child.communicate(timeout=10)
        self.assertEqual((child.returncode, stdout), (0, ""), stderr)
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"),
                         prefs_text({"browser.startup.page": "3"}))

    def test_gives_up_after_poll_max(self):
        managed = prefs_text({PREF_SCHEME: "0"})
        self.fh.write(PROFILE + "/prefs.js", managed)
        with LockHolder(self.fh, PROFILE + "/.parentlock"):
            self.run_clean(self.path(), env={"BG_POLL_MAX": "0.2"})
            self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), managed)

    def test_missing_profile_and_no_prefs(self):
        self.fh.write(PROFILE + "/user.js", "")
        before = self.fh.snapshot(".")
        self.run_clean(self.path(), self.path("nowhere/profile"))
        self.assertEqual(self.fh.snapshot("."), before, "prefs.js is never created")

    def test_corrupt_state_falls_back_to_the_v0_rule(self):
        self.fh.write(STATE + "/state.json", "{broken")
        self.fh.write(PROFILE + "/prefs.js", prefs_text({PREF_SCHEME: "1", PREF_TRANSPARENT: "7"}))
        self.run_clean(self.path())
        self.assertEqual(self.fh.read(PROFILE + "/prefs.js"), prefs_text({PREF_TRANSPARENT: "7"}))
        self.assertEqual(self.fh.read(STATE + "/state.json"), "{broken", "state is only read")

    def test_usage(self):
        proc = self.fh.run_script(["clean-prefs"])
        self.assertEqual(proc.returncode, 2)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, test_contract.SCHEMA["error"],
                                                test_contract.DEFS), [])


def _reap(child):
    if child.poll() is None:
        child.kill()
    child.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()

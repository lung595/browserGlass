"""sync against a deleted plugin folder (the uninstall sweep race).

When the plugin folder is deleted, the daemon's sweep runs
`uninstall --if-gone <plugin>/plugin.json`. A sync launched just before
(already reading its script, or waiting for the state lock the uninstall
holds) must not write everything back afterwards: the daemon passes
`sync --if-plugin <plugin>/plugin.json`, and sync refuses, with the
"plugin_gone" error line and nothing written, when that file is missing.
Checked before the lock and again under it. Without --if-plugin, --data
keeps its meaning wherever it is (manual runs, a copy of data/, a symlink).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import contextlib
import io
import json
import os
import shutil
import unittest
from unittest import mock

import test_contract
from fakehome import PREFS_HEADER, FakeHome, kill_strays, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

ROOT = ".mozilla/firefox"
PROFILE = ROOT + "/abcd1234.default-release"
PLUGIN = ".config/dms/plugins/browserGlassRaceTest"
DATA = PLUGIN + "/data"
STATE = ".local/state/dms/browserGlass"
DMS_SETTINGS = ".config/dms/plugin_settings.json"
FAST = {"BG_LOCK_TIMEOUT": "5", "BG_POLL_INTERVAL": "0.05", "BG_SWEEP_GRACE": "0",
        "BG_PLUGIN_RECHECK": "0"}


def settings_json():
    return json.dumps(test_contract.load_json("settings-default.json"))


class SweepRaceTest(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)
        fh = self.fh
        fh.write(PROFILE + "/prefs.js", PREFS_HEADER + 'user_pref("browser.startup.page", 3);\n')
        fh.write_profiles_ini(ROOT, [{"name": "default-release",
                                      "path": "abcd1234.default-release", "default": True}])
        fh.write(".config/niri/config.kdl", 'input {\n}\n\ninclude "dms/windowrules.kdl"\n', mode=0o644)
        fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.8\n}\n", mode=0o644)
        fh.write_dms_colors(mode="dark", surface_dark="#1a1c22")
        fh.write(PLUGIN + "/plugin.json", json.dumps({"id": "browserGlassRaceTest"}) + "\n")
        fh.resolve(DATA).mkdir()
        for name in ("styles.json", "css-mapping.json"):
            shutil.copyfile(str(test_contract.REPO / "data" / name), str(fh.resolve(DATA + "/" + name)))

    def data(self):
        return str(self.fh.resolve(DATA))

    def manifest(self):
        return str(self.fh.resolve(PLUGIN + "/plugin.json"))

    def daemon_args(self):
        return ["sync", "--data", self.data(), "--settings", settings_json(),
                "--if-plugin", self.manifest()]

    def run_cli(self, *args, code=0):
        proc = self.fh.run_script(list(args), extra_env=FAST)
        self.assertEqual(proc.returncode, code, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        return proc

    def sync(self, code=0, args=None):
        proc = self.run_cli(*(args or self.daemon_args()), code=code)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        spec = SCHEMA["sync"] if code == 0 else SCHEMA["error"]
        self.assertEqual(test_contract.validate(doc, spec, DEFS), [], lines[0])
        return doc

    def assert_refused(self, doc):
        self.assertTrue(doc["error"].startswith("plugin_gone:"), doc)

    def test_present_plugin_syncs(self):
        out = self.sync()
        self.assertTrue(out["glass"])
        self.assertEqual(out["warnings"], [])
        self.assertIn("Site styles", self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))

    def test_deleted_folder_after_sweep_writes_nothing(self):
        self.sync()
        shutil.rmtree(str(self.fh.resolve(PLUGIN)))
        proc = self.run_cli("uninstall", "--if-gone", str(self.fh.resolve(PLUGIN + "/plugin.json")))
        self.assertEqual(json.loads(proc.stdout)["state_removed"], True, proc.stdout)
        self.assertFalse(self.fh.exists(STATE))
        before = self.fh.snapshot(".")
        self.assert_refused(self.sync(code=1))
        self.assertEqual(self.fh.snapshot("."), before)
        self.assertFalse(self.fh.exists(".local/state/dms"))

    def test_lost_manifest_is_refused(self):
        # A removal in progress: data/ still there, plugin.json already gone.
        os.unlink(str(self.fh.resolve(PLUGIN + "/plugin.json")))
        before = self.fh.snapshot(".")
        self.assert_refused(self.sync(code=1))
        self.assertEqual(self.fh.snapshot("."), before)

    def manual(self, data, cwd=None, extra=()):
        """A sync without --if-plugin (a manual or --profile run)."""
        args = ["sync", "--data", data, "--settings", settings_json()] + list(extra)
        proc = self.fh.run_script(args, extra_env=FAST, cwd=cwd)
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["sync"], DEFS), [], proc.stdout)
        return doc

    def copy_data(self, rel):
        folder = self.fh.resolve(rel)
        folder.mkdir(parents=True)
        for name in ("styles.json", "css-mapping.json"):
            shutil.copyfile(str(test_contract.REPO / "data" / name), str(folder / name))
        return folder

    def assert_styled(self, doc):
        self.assertTrue(doc["glass"], doc)
        self.assertEqual(doc["warnings"], [], doc)
        self.assertIn("Site styles", self.fh.read(PROFILE + "/chrome/dms-glass-content.css"))

    def test_missing_data_outside_a_plugin_is_only_a_warning(self):
        # Data folder and its parent both missing: the old warning only.
        doc = self.manual(str(self.fh.root / "nope" / "data"))
        self.assertEqual([w["code"] for w in doc["warnings"]], ["data_unavailable"])

    def test_data_copy_outside_a_plugin_syncs(self):
        self.assert_styled(self.manual(str(self.copy_data("mystyles/data"))))

    def test_relative_data_in_a_plain_folder_syncs(self):
        folder = self.copy_data("mystyles/data").parent
        self.assert_styled(self.manual("data", cwd=str(folder)))

    def test_symlinked_data_syncs(self):
        link = self.fh.root / "linkdata"
        os.symlink(str(test_contract.REPO / "data"), str(link))
        self.assert_styled(self.manual(str(link)))

    def test_profile_run_with_a_data_copy_syncs(self):
        data = str(self.copy_data("mystyles/data"))
        doc = self.manual(data, extra=["--profile", str(self.fh.resolve(PROFILE))])
        self.assert_styled(doc)

    def test_data_of_a_plugin_without_manifest_syncs_without_if_plugin(self):
        # The refusal is the daemon's choice (--if-plugin), never a guess
        # from where --data is.
        os.unlink(self.manifest())
        self.assert_styled(self.manual(self.data()))

    def test_plugin_gone_predicate(self):
        manifest = self.manifest()
        env = dict(FAST)
        self.assertFalse(bg.plugin_gone(manifest, env))
        os.unlink(manifest)
        self.assertTrue(bg.plugin_gone(manifest, env))
        shutil.rmtree(str(self.fh.resolve(PLUGIN)))
        self.assertTrue(bg.plugin_gone(manifest, env))

    def test_recreated_manifest_is_not_a_removal(self):
        # A git checkout deletes plugin.json and writes it again: the second
        # look, $BG_PLUGIN_RECHECK seconds later, finds it.
        manifest = self.manifest()
        text = self.fh.read(PLUGIN + "/plugin.json")
        os.unlink(manifest)
        slept = []

        def fake_sleep(seconds):
            slept.append(seconds)
            with open(manifest, "w") as f:
                f.write(text)

        with mock.patch.object(bg.time, "sleep", fake_sleep):
            self.assertFalse(bg.plugin_gone(manifest, {"BG_PLUGIN_RECHECK": "0.5"}))
        self.assertEqual(slept, [0.5])
        # A folder that is gone needs no second look.
        shutil.rmtree(str(self.fh.resolve(PLUGIN)))
        with mock.patch.object(bg.time, "sleep", fake_sleep):
            self.assertTrue(bg.plugin_gone(manifest, {}))
        self.assertEqual(slept, [0.5])

    def test_folder_deleted_while_waiting_for_the_lock(self):
        # The sync passed its first check, then the folder went and the
        # sweep's uninstall ran (removing the state folder) before the sync
        # got the lock: the check under the lock refuses, and the state
        # folder state_lock() made again is taken back.
        self.sync()
        real_lock = bg.state_lock
        fh = self.fh

        def racing_lock(folder, env=None, *rest):
            shutil.rmtree(str(fh.resolve(PLUGIN)))
            proc = fh.run_script(["uninstall", "--if-gone", str(fh.resolve(PLUGIN + "/plugin.json"))],
                                 extra_env=FAST)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse(os.path.lexists(folder))
            racing_lock.after_uninstall = fh.snapshot(".")
            return real_lock(folder, env, *rest)

        out = io.StringIO()
        with mock.patch.object(bg, "state_lock", racing_lock), contextlib.redirect_stdout(out):
            code = bg.main(self.daemon_args(), env=fh.env(FAST))
        self.assertEqual(code, bg.EXIT_ERROR, out.getvalue())
        doc = json.loads(out.getvalue())
        self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], doc)
        self.assert_refused(doc)
        self.assertEqual(fh.snapshot("."), racing_lock.after_uninstall)
        self.assertFalse(fh.exists(STATE))
        self.assertFalse(fh.exists(".local/state/dms"))

    def test_lock_file_is_unlinked_while_still_locked(self):
        # Otherwise a command could lock the file between the close and the
        # unlink, while a later one locks a new state.lock at the same path.
        self.sync()
        fh = self.fh
        real_lock, real_close, real_unlink = bg.state_lock, os.close, os.unlink
        events = []

        def racing_lock(folder, env=None, *rest):
            shutil.rmtree(str(fh.resolve(PLUGIN)))
            shutil.rmtree(str(fh.resolve(STATE)))
            del events[:]  # the sweep's own removal
            fd = real_lock(folder, env, *rest)
            racing_lock.fd = fd
            return fd

        def close(fd):
            if fd == getattr(racing_lock, "fd", None):
                events.append("close")
            return real_close(fd)

        def unlink(path, *a, **kw):
            if os.path.basename(str(path)) == bg.STATE_LOCK:
                events.append("unlink")
            return real_unlink(path, *a, **kw)

        out = io.StringIO()
        with mock.patch.object(bg, "state_lock", racing_lock), \
                mock.patch.object(bg.os, "close", close), \
                mock.patch.object(bg.os, "unlink", unlink), contextlib.redirect_stdout(out):
            code = bg.main(self.daemon_args(), env=fh.env(FAST))
        self.assertEqual(code, bg.EXIT_ERROR, out.getvalue())
        self.assertEqual(events, ["unlink", "close"])
        self.assertFalse(fh.exists(STATE))

    def test_existing_state_folder_is_kept_on_refusal(self):
        # Refused under the lock while the state folder was never removed
        # (the sweep's uninstall has not run yet): state.lock and the state
        # stay, the uninstall cleans them later.
        self.sync()
        lock_rel = STATE + "/" + bg.STATE_LOCK
        real_lock = bg.state_lock
        fh = self.fh

        def racing_lock(folder, env=None, *rest):
            os.unlink(str(fh.resolve(PLUGIN + "/plugin.json")))
            racing_lock.before = fh.snapshot(".")
            return real_lock(folder, env, *rest)

        out = io.StringIO()
        with mock.patch.object(bg, "state_lock", racing_lock), contextlib.redirect_stdout(out):
            code = bg.main(self.daemon_args(), env=fh.env(FAST))
        self.assertEqual(code, bg.EXIT_ERROR, out.getvalue())
        self.assert_refused(json.loads(out.getvalue()))
        self.assertEqual(fh.snapshot("."), racing_lock.before)
        self.assertTrue(fh.exists(lock_rel))

    # Disabling the plugin: DMS writes "enabled": false to
    # plugin_settings.json, then the daemon's onDestruction runs `uninstall`
    # (the folder stays). A sync the daemon started just before is not
    # killed: if it gets the lock after that uninstall, --if-plugin refuses
    # it, and nothing is written back.

    def set_enabled(self, value, other=None):
        doc = {"otherPlugin": {"enabled": True}}
        if value is not None:
            doc[bg.PLUGIN_ID] = {"enabled": value, "liveControl": True}
        self.fh.write(DMS_SETTINGS, json.dumps(doc, indent=2) if other is None else other, mode=0o644)

    def test_enabled_plugin_syncs(self):
        self.set_enabled(True)
        self.assert_styled(self.sync())

    def test_disabled_while_waiting_for_the_lock(self):
        self.set_enabled(True)
        self.sync()
        self.assertTrue(self.fh.exists(STATE))
        real_lock = bg.state_lock
        fh = self.fh

        def racing_lock(folder, env=None, *rest):
            # The sync passed its first check and is about to lock: the
            # user disables the plugin and the uninstall runs first.
            self.set_enabled(False)
            proc = fh.run_script(["uninstall"], extra_env=FAST)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue(json.loads(proc.stdout)["state_removed"], proc.stdout)
            racing_lock.after_uninstall = fh.snapshot(".")
            return real_lock(folder, env, *rest)

        out = io.StringIO()
        args = self.daemon_args() + ["--plugin-dir", str(test_contract.REPO)]
        with mock.patch.object(bg, "state_lock", racing_lock), contextlib.redirect_stdout(out):
            code = bg.main(args, env=fh.env(FAST))
        self.assertEqual(code, bg.EXIT_ERROR, out.getvalue())
        doc = json.loads(out.getvalue())
        self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], doc)
        self.assert_refused(doc)
        self.assertEqual(fh.snapshot("."), racing_lock.after_uninstall)
        self.assertFalse(fh.exists(PROFILE + "/chrome/dms-glass-content.css"))
        self.assertFalse(fh.exists(PROFILE + "/user.js"))
        self.assertFalse(fh.exists(STATE))
        self.assertFalse(fh.exists(".local/state/dms"))

    def test_disabled_plugin_is_refused_before_the_lock(self):
        self.set_enabled(False)
        before = self.fh.snapshot(".")
        self.assert_refused(self.sync(code=1))
        self.assertEqual(self.fh.snapshot("."), before)

    def test_disabled_plugin_still_syncs_without_if_plugin(self):
        # A manual run is the user's choice, whatever DMS says.
        self.set_enabled(False)
        self.assert_styled(self.manual(self.data()))

    def test_plugin_disabled_predicate(self):
        env = self.fh.env(FAST)
        self.assertFalse(bg.plugin_disabled(env))
        for value, disabled in ((False, True), (True, False), (None, False), (0, False), ("false", False)):
            self.set_enabled(value)
            self.assertEqual(bg.plugin_disabled(env), disabled, value)
        self.set_enabled(None, other="\ufeff" + json.dumps({bg.PLUGIN_ID: {"enabled": False}}))
        self.assertTrue(bg.plugin_disabled(env))
        for text in ("{", "[]", json.dumps({bg.PLUGIN_ID: False}), ""):
            self.set_enabled(None, other=text)
            self.assertFalse(bg.plugin_disabled(env), text)
        os.unlink(str(self.fh.resolve(DMS_SETTINGS)))
        self.assertFalse(bg.plugin_disabled(env))
        # The path follows $XDG_CONFIG_HOME.
        other = self.fh.root / "otherconfig"
        (other / "dms").mkdir(parents=True)
        (other / "dms" / "plugin_settings.json").write_text(json.dumps({bg.PLUGIN_ID: {"enabled": False}}))
        self.assertTrue(bg.plugin_disabled(self.fh.env(dict(FAST, XDG_CONFIG_HOME=str(other)))))


if __name__ == "__main__":
    unittest.main()

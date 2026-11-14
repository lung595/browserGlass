"""Tests of the FakeHome helpers the other suites build on.

Run from the plugin root: python3 -m unittest discover -s tests/py -v
"""

import configparser
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import fakehome
from fakehome import REAL_HOME, FakeHome


class FakeHomeLayout(unittest.TestCase):
    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def test_folders_exist(self):
        for folder in (self.fh.home, self.fh.config, self.fh.state, self.fh.cache, self.fh.data):
            self.assertTrue(folder.is_dir(), folder)
        self.assertEqual(self.fh.home.name, "alice")

    def test_under_temp_and_away_from_real_home(self):
        self.assertTrue(str(self.fh.home).startswith(tempfile.gettempdir()) or str(self.fh.home).startswith("/tmp/"))
        self.assertNotEqual(self.fh.home, REAL_HOME)
        self.assertNotIn(REAL_HOME, self.fh.home.parents)
        self.fh.assert_safe()

    def test_assert_safe_refuses_the_real_home(self):
        self.fh.home = REAL_HOME
        with self.assertRaises(AssertionError):
            self.fh.assert_safe()

    def test_cleanup_removes_everything(self):
        fh = FakeHome()
        root = fh.root
        fh.write(".config/x/y.txt", "hi")
        locked = fh.resolve(".config/x")
        os.chmod(str(locked), 0o500)
        fh.cleanup()
        self.assertFalse(root.exists())

    def test_context_manager(self):
        with FakeHome("bob") as fh:
            root = fh.root
            self.assertEqual(fh.home.name, "bob")
        self.assertFalse(root.exists())

    def test_resolve_refuses_escapes(self):
        with self.assertRaises(ValueError):
            self.fh.resolve("../../etc/passwd")
        with self.assertRaises(ValueError):
            self.fh.resolve("/etc/passwd")
        self.assertEqual(self.fh.resolve("a/b"), self.fh.home / "a" / "b")


class FakeHomeEnv(unittest.TestCase):
    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def test_env_points_inside(self):
        env = self.fh.env()
        self.assertEqual(env["HOME"], str(self.fh.home))
        self.assertEqual(env["XDG_CONFIG_HOME"], str(self.fh.config))
        self.assertEqual(env["XDG_STATE_HOME"], str(self.fh.state))
        self.assertEqual(env["XDG_CACHE_HOME"], str(self.fh.cache))
        self.assertEqual(env["XDG_DATA_HOME"], str(self.fh.data))
        self.assertEqual(env["USER"], "alice")
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "TMPDIR"):
            self.assertTrue(env[key].startswith(str(self.fh.root) + "/"), key)

    def test_env_has_no_real_home_path(self):
        real = str(REAL_HOME)
        env = self.fh.env()
        self.assertEqual(self.fh.leaks(env), [])
        for key, value in env.items():
            for part in value.split(os.pathsep):
                self.assertFalse(part == real or part.startswith(real + "/"), "%s=%s" % (key, value))

    def test_env_drops_path_entries_in_real_home(self):
        old = os.environ.get("PATH")
        os.environ["PATH"] = str(REAL_HOME / ".local" / "bin") + os.pathsep + "/usr/bin"
        try:
            env = self.fh.env()
        finally:
            if old is None:
                del os.environ["PATH"]
            else:
                os.environ["PATH"] = old
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_env_does_not_inherit(self):
        os.environ["BG_FAKEHOME_PROBE"] = "1"
        try:
            self.assertNotIn("BG_FAKEHOME_PROBE", self.fh.env())
        finally:
            del os.environ["BG_FAKEHOME_PROBE"]

    def test_env_extra(self):
        env = self.fh.env({"MOZ_HEADLESS": 1, "LANG": None})
        self.assertEqual(env["MOZ_HEADLESS"], "1")
        self.assertNotIn("LANG", env)

    def test_leaks_detects(self):
        self.assertEqual(self.fh.leaks({"A": str(REAL_HOME), "B": "/usr:" + str(REAL_HOME / "x"), "C": "/tmp"}), ["A", "B"])


class FakeHomeGenerators(unittest.TestCase):
    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def test_make_profile(self):
        p = self.fh.make_profile(".mozilla/firefox", "abcd1234.default-release",
                                 files={"chrome/userChrome.css": "a{}", "user.js": b"// x\n"},
                                 prefs={"b.int": 3, "a.bool": True, "c.str": 'q"x'})
        self.assertEqual(p, self.fh.home / ".mozilla/firefox/abcd1234.default-release")
        prefs = (p / "prefs.js").read_text()
        self.assertTrue(prefs.startswith("// Mozilla User Preferences\n"))
        self.assertIn('user_pref("a.bool", true);\n', prefs)
        self.assertIn('user_pref("b.int", 3);\n', prefs)
        self.assertIn('user_pref("c.str", "q\\"x");\n', prefs)
        self.assertLess(prefs.index("a.bool"), prefs.index("b.int"))
        self.assertEqual((p / "chrome/userChrome.css").read_text(), "a{}")
        self.assertEqual((p / "user.js").read_bytes(), b"// x\n")

    def test_pref_value_rejects_floats(self):
        with self.assertRaises(TypeError):
            fakehome.pref_value(1.5)

    def test_profiles_ini_relative(self):
        ini = self.fh.write_profiles_ini(
            ".mozilla/firefox",
            ["plain", {"name": "default-release", "path": "abcd.default-release", "default": True}],
            installs={"4F96D1932A9F858E": "abcd.default-release"})
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read(str(ini))
        self.assertEqual(cp["Install4F96D1932A9F858E"]["Default"], "abcd.default-release")
        self.assertEqual(cp["Profile0"]["Path"], "plain")
        self.assertEqual(cp["Profile0"]["IsRelative"], "1")
        self.assertEqual(cp["Profile1"]["Default"], "1")
        self.assertNotIn("Default", cp["Profile0"])
        self.assertEqual(cp["General"]["Version"], "2")
        self.assertLess(ini.read_text().index("[Install"), ini.read_text().index("[Profile0]"))

    def test_profiles_ini_absolute(self):
        ini = self.fh.write_profiles_ini(".librewolf", [{"name": "x", "path": "x.default"}],
                                         installs={"ABC": "x.default"}, relative=False)
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read(str(ini))
        want = str(self.fh.home / ".librewolf" / "x.default")
        self.assertEqual(cp["Profile0"]["Path"], want)
        self.assertEqual(cp["Profile0"]["IsRelative"], "0")
        self.assertEqual(cp["InstallABC"]["Default"], want)

    def test_profiles_ini_mixed(self):
        ini = self.fh.write_profiles_ini(".zen", [{"name": "a"}, {"name": "b", "relative": False}])
        text = ini.read_text()
        self.assertIn("Path=a\n", text)
        self.assertIn("Path=%s\n" % (self.fh.home / ".zen" / "b"), text)

    def test_profile_group(self):
        made = self.fh.make_profile_group(".config/mozilla/firefox", ["g1.Work", "g2.Play"], prefs={"x": 1})
        root = self.fh.home / ".config/mozilla/firefox"
        self.assertEqual(made, [root / "g1.Work", root / "g2.Play"])
        for p in made:
            self.assertIn('user_pref("x", 1);', (p / "prefs.js").read_text())
        self.assertTrue((root / "Profile Groups" / "0a1b2c3d4e5f.sqlite").is_file())
        self.assertFalse((root / "profiles.ini").exists())

    def test_write_kdl(self):
        p = self.fh.write_kdl(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.9\n}\n")
        self.assertEqual(p, self.fh.config / "niri/dms/windowrules.kdl")
        self.assertIn("opacity 0.9", p.read_text())

    def test_dms_colors(self):
        p = self.fh.write_dms_colors("light", "#111111", "#eeeeee")
        self.assertEqual(p, self.fh.cache / "dms" / "dms-colors.json")
        doc = json.loads(p.read_text())
        self.assertEqual(doc["mode"], "light")
        self.assertEqual(doc["colors"]["dark"]["surface"], "#111111")
        self.assertEqual(doc["colors"]["light"]["surface"], "#eeeeee")
        self.assertIn("dank16", doc)

    def test_snapshot(self):
        self.fh.write("a/f.txt", "x", mode=0o600)
        os.symlink("f.txt", str(self.fh.resolve("a/l")))
        snap = self.fh.snapshot("a")
        self.assertEqual(snap["f.txt"], ("file", 0o600, b"x"))
        self.assertEqual(snap["l"][0], "link")
        self.assertEqual(snap["l"][2], "f.txt")
        self.assertEqual(snap, self.fh.snapshot("a"))
        os.chmod(str(self.fh.resolve("a/f.txt")), 0o644)
        self.assertNotEqual(snap, self.fh.snapshot("a"))


class RunScript(unittest.TestCase):
    PROBE = (
        "import json, os, sys\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'env': dict(os.environ),"
        " 'stdin': sys.stdin.read(), 'isolated': sys.flags.isolated}))\n"
    )

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.probe = self.fh.write(self.fh.tmp / "probe.py", self.PROBE)

    def test_runs_isolated_inside_fake_home(self):
        proc = self.fh.run_script(["sync", "--off"], stdin="hello", script=self.probe)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["argv"], ["sync", "--off"])
        self.assertEqual(out["stdin"], "hello")
        self.assertEqual(out["isolated"], 1)
        self.assertEqual(os.path.realpath(out["cwd"]), str(self.fh.home))
        self.assertEqual(out["env"]["HOME"], str(self.fh.home))
        self.assertEqual(self.fh.leaks(out["env"]), [])

    def test_nonzero_exit_is_returned(self):
        bad = self.fh.write(self.fh.tmp / "bad.py", "import sys; sys.stderr.write('boom'); sys.exit(3)\n")
        proc = self.fh.run_script([], script=bad)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stderr, "boom")

    def test_default_script_is_the_repo_one(self):
        self.assertEqual(fakehome.SCRIPT, Path(__file__).resolve().parents[2] / "browserglass.py")


if __name__ == "__main__":
    unittest.main()

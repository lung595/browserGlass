"""Zen Browser: discovery, transparency mods, sync/uninstall round trip.

Zen's mod manager keeps the registry of installed mods at the profile root,
<profile>/zen-themes.json (chrome/ holds the generated zen-themes.css and the
zen-themes/<uuid>/ mod folders); <profile>/chrome/zen-themes.json, the path
first guessed, is read as a fallback. A mod (or a zen.* pref) that makes the
browser see-through stacks with browserGlass: status and sync warn
("zen_transparency_mod"), nothing else changes and no Zen file is touched.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import unittest

import test_contract
from fakehome import FakeHome, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

ZEN = ".zen"
ZEN_XDG = ".config/zen"
ZEN_FLATPAK = ".var/app/app.zen_browser.zen/.zen"
FOLDER = "w1x2y3z4.Default (release)"
PROFILE = ZEN + "/" + FOLDER
MODS = PROFILE + "/zen-themes.json"
CHROME_MODS = PROFILE + "/chrome/zen-themes.json"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}
WARNING = "Zen transparency mod detected; it may stack with browserGlass."


def mod(name, description="", enabled=True, **extra):
    doc = {"id": "00000000-0000-4000-8000-%012d" % len(name), "name": name,
           "description": description, "author": "example", "version": "1.0.0"}
    if enabled is not None:
        doc["enabled"] = enabled
    doc.update(extra)
    return doc


def settings():
    return dict(test_contract.load_json("settings-default.json"))


class ZenCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def zen_profile(self, root=ZEN, folder=FOLDER, prefs=None):
        self.fh.make_profile(root, folder, prefs=prefs or {"browser.startup.page": 3})
        self.fh.write_profiles_ini(root, [{"name": folder.split(".", 1)[1], "path": folder,
                                           "default": True}])
        return str(self.fh.resolve(root + "/" + folder))

    def detect(self, mods=None, raw=None, prefs=None, where=MODS):
        path = self.zen_profile(prefs=prefs)
        if raw is not None:
            self.fh.write(where, raw)
        elif mods is not None:
            self.fh.write(where, json.dumps(mods))
        return bg.zen_transparency(path)


class DetectionTest(ZenCase):

    def test_mods(self):
        cases = [
            ({"a": mod("Transparent Zen")}, True),
            ({"a": mod("Sidebar", "A translucent sidebar")}, False),
            ({"a": mod("Sidebar", tags=["translucent"])}, True),
            ({"a": mod("Glassy Sidebar")}, True),
            ({"a": mod("Blurred tabs")}, True),
            ({"a": mod("Frosted", tags=["Blur", "theme"])}, True),
            ({"a": mod("Acrylic tabs")}, True),
            ({"a": mod("Glass toolbar", enabled=None)}, True),
            ([mod("Mica urlbar")], True),
            ({"a": mod("Transparent Zen", enabled=False)}, False),
            ({"a": mod("Transparent Zen", enabled="false")}, False),
            ({"a": mod("Transparent Zen", enabled=0)}, False),
            ({"a": mod("Transparent Zen", enabled="0")}, False),
            ({"a": mod("Transparent Zen", enabled="true")}, True),
            ({"a": mod("Hourglass loading spinner")}, False),
            ({"a": mod("Chemical colors")}, False),
            ({"a": mod("Clean UI", "Removes the blur from popups")}, False),
            ({"a": mod("Solid sidebar", "Removes the blur and transparency from the sidebar")}, False),
            ({"a": mod("Compact Tabs", "Smaller tab strip.")}, False),
            ({}, False),
            ({"a": "Transparent Zen", "b": None, "c": [1]}, False),
            ("Transparent Zen", False),
        ]
        for mods, expected in cases:
            for where in (MODS, CHROME_MODS):
                with self.subTest(mods=mods, where=where):
                    self.setUp()
                    self.assertEqual(self.detect(mods, where=where), expected)

    def test_either_registry_file(self):
        # The root registry is read first; a hit in either file is enough.
        path = self.zen_profile()
        self.fh.write(MODS, json.dumps({"a": mod("Compact Tabs")}))
        self.fh.write(CHROME_MODS, json.dumps({"a": mod("Transparent Zen")}))
        self.assertTrue(bg.zen_transparency(path))
        self.fh.write(MODS, json.dumps({"a": mod("Transparent Zen")}))
        self.fh.write(CHROME_MODS, "{broken")
        self.assertTrue(bg.zen_transparency(path))
        self.fh.write(MODS, json.dumps({"a": mod("Compact Tabs")}))
        self.assertFalse(bg.zen_transparency(path))

    def test_unusable_files(self):
        for raw in ("{not json", "", "\x00\x01", "[" * 5000 + "]" * 5000):
            with self.subTest(raw=raw[:10]):
                self.setUp()
                self.assertFalse(self.detect(raw=raw))
        self.setUp()
        path = self.zen_profile()
        self.fh.resolve(MODS).mkdir(parents=True)
        self.assertFalse(bg.zen_transparency(path), "a folder in place of the file")
        self.assertFalse(bg.zen_transparency(str(self.fh.resolve("nowhere"))))

    def test_bom(self):
        self.assertTrue(self.detect(raw="\ufeff" + json.dumps({"a": mod("Transparent")})))

    def test_prefs(self):
        cases = [
            ({"zen.widget.linux.transparency": True}, True),
            ({"zen.theme.acrylic-elements": True}, True),
            ({"zen.view.blur-amount": 12}, True),
            ({"zen.widget.linux.transparency": False}, False),
            ({"zen.view.blur-amount": 0}, False),
            ({"zen.view.compact": True}, False),
            ({"zen.urlbar.blur-amount": "0"}, False),
            ({"zen.theme.acrylic-elements": "false"}, False),
            ({"zen.theme.acrylic-elements": ""}, False),
            ({"zen.view.blur-amount": "0.0"}, False),
            ({"zen.theme.acrylic-elements": "on"}, True),
            ({"browser.tabs.allow_transparent_browser": True}, False),
        ]
        for prefs, expected in cases:
            with self.subTest(prefs=prefs):
                self.setUp()
                self.assertEqual(self.detect(prefs=prefs), expected)

    def test_userjs_pref(self):
        path = self.zen_profile()
        self.fh.write(PROFILE + "/user.js", 'user_pref("zen.widget.linux.transparency", true);\n')
        self.assertTrue(bg.zen_transparency(path))

    def test_userjs_overrides_prefs(self):
        # user.js is applied at startup, after prefs.js: its value wins.
        path = self.zen_profile(prefs={"zen.widget.linux.transparency": True})
        self.assertTrue(bg.zen_transparency(path))
        self.fh.write(PROFILE + "/user.js", 'user_pref("zen.widget.linux.transparency", false);\n')
        self.assertFalse(bg.zen_transparency(path))

    def test_discovery_and_app_ids(self):
        for root in (ZEN, ZEN_XDG, ZEN_FLATPAK):
            self.zen_profile(root)
        got = [(p.family, p.variant, p.name) for p in bg.find_profiles(self.fh.env())]
        self.assertEqual(sorted(got), [("zen", "flatpak", "Default (release)"),
                                       ("zen", "native", "Default (release)"),
                                       ("zen", "native", "Default (release)")])
        rule = bg.niri_kdl(True)
        for app_id in ("zen", "zen-browser", "zen-beta", "app\\.zen_browser\\.zen"):
            self.assertIn(app_id, rule)


class CommandTest(ZenCase):

    def run_ok(self, args, spec):
        proc = self.fh.run_script(args, extra_env=FAST)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA[spec], DEFS), [], proc.stdout)
        return doc

    def home(self, mods, where=MODS):
        """Two Zen profiles laid out as Zen does: an [Install<hash>] section,
        the root mod registry, the generated chrome/zen-themes.css, a mod
        folder and the user's own userChrome.css."""
        self.zen_profile()
        self.zen_profile(ZEN_FLATPAK)
        ini = ZEN + "/profiles.ini"
        self.fh.write(ini, "[Install0123456789ABCDEF]\nDefault=%s\nLocked=1\n\n" % FOLDER
                      + self.fh.read(ini))
        self.fh.write(where, json.dumps(mods, indent=2) + "\n")
        self.fh.write(PROFILE + "/chrome/zen-themes.css", "/* generated by Zen */\n")
        self.fh.write(PROFILE + "/chrome/zen-themes/8f3c0000-aaaa-4bbb-8ccc-dddddddddddd/chrome.css",
                      ":root { --zen-example: 1px; }\n")
        self.fh.write(PROFILE + "/chrome/userChrome.css", "/* the user's own */\n#nav-bar { order: 1 }\n")
        self.fh.write(".config/niri/config.kdl", "input {\n}\n")
        self.fh.write_dms_colors()

    def test_status_and_sync_warn(self):
        for where in (MODS, CHROME_MODS):
            with self.subTest(where=where):
                self.setUp()
                self.home({"a": mod("Transparent Zen")}, where)
                pid = bg.profile_id(str(self.fh.resolve(PROFILE)))
                expected = [{"code": "zen_transparency_mod", "message": WARNING, "family": "zen",
                             "profile": pid}]
                status = self.run_ok(["status", "--json"], "status")
                self.assertEqual(status["warnings"], expected)
                out = self.run_ok(["sync", "--settings", json.dumps(settings())], "sync")
                self.assertEqual(out["warnings"], expected)
                self.assertEqual(len(out["changed"]), 2, "the other Zen profile is synced too")
                self.assertEqual(self.run_ok(["status", "--json"], "status")["warnings"], expected)

    def test_fixture_warning(self):
        fixture = test_contract.load_json("sync.json")
        zen = [w for w in fixture["warnings"] if w["code"] == "zen_transparency_mod"]
        self.assertEqual(zen[0]["message"], WARNING)
        self.assertEqual(bg.zen_warning(zen[0]["profile"]), zen[0])

    def test_round_trip(self):
        self.home({"a": mod("Transparent Zen"), "b": mod("Compact Tabs")})
        zen_files = [MODS, PROFILE + "/chrome/zen-themes.css", ZEN + "/profiles.ini",
                     PROFILE + "/chrome/zen-themes/8f3c0000-aaaa-4bbb-8ccc-dddddddddddd/chrome.css"]
        kept = {rel: self.fh.resolve(rel).read_bytes() for rel in zen_files}
        before = self.fh.snapshot()
        self.run_ok(["sync", "--settings", json.dumps(settings())], "sync")
        self.assertEqual({rel: self.fh.resolve(rel).read_bytes() for rel in zen_files}, kept)
        chrome = self.fh.read(PROFILE + "/chrome/userChrome.css")
        self.assertIn("dms-glass-chrome.css", chrome)
        self.assertIn("#nav-bar { order: 1 }", chrome, "the user's rules are kept")
        proc = self.fh.run_script(["report"], extra_env=FAST)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        status = self.run_ok(["status", "--json"], "status")
        self.assertTrue(all(p["applied"] for b in status["browsers"] for p in b["profiles"]))
        out = self.run_ok(["uninstall"], "uninstall")
        self.assertEqual(len(out["removed"]), 2)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.fh.snapshot(), before, "uninstall left traces")


if __name__ == "__main__":
    unittest.main()

"""browserglass.py report: contract lines, anonymity, read-only.

The fake account is "alice" and every profile name and folder carries it:
the report must never show it, nor the home path, a profile id, a path or
the hostname.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import hashlib
import json
import os
import re
import socket
import unittest

import test_contract
from fakehome import FakeHome, LockHolder, kill_strays, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
REPORT_LINES = SCHEMA["report_lines"]

FF = ".mozilla/firefox"
LW = ".librewolf"
ZEN = ".zen"
PROFILES = (
    (FF, "x1y2z3w4.alice-main", "alice-main"),
    (FF, "v5u6t7s8.alice private", "alice private"),
    (LW, "r9q8p7o6.alice-wolf", "alice-wolf"),
    (ZEN, "n5m4l3k2.alice (zen)", "alice (zen)"),
)
MAIN = FF + "/x1y2z3w4.alice-main"
ZEN_P = ZEN + "/n5m4l3k2.alice (zen)"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}
ZEN_MODS = {"0f0f0f0f-1111-4222-8333-444444444444": {
    "id": "0f0f0f0f-1111-4222-8333-444444444444", "name": "Glassy Sidebar",
    "description": "Blurred translucent sidebar.", "enabled": True}}


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


class ReportCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome(name="alice")
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)
        self.extra = dict(FAST, BG_DMS_SHELL_DIR=str(self.fh.root / "dms-shell"))

    def home(self):
        fh = self.fh
        groups = {}
        for root, folder, name in PROFILES:
            fh.make_profile(root, folder, prefs={"browser.startup.page": 3})
            groups.setdefault(root, []).append({"name": name, "path": folder})
        for root, entries in groups.items():
            entries[0]["default"] = True
            fh.write_profiles_ini(root, entries)
        fh.write(ZEN_P + "/chrome/zen-themes.json", json.dumps(ZEN_MODS))
        fh.write(".config/niri/config.kdl", "input {\n}\n")
        fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.85\n}\n")
        fh.write_dms_colors()

    def sync(self, *extra, **over):
        proc = self.fh.run_script(["sync", "--settings", json.dumps(settings(**over))] + list(extra),
                                  extra_env=self.extra)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def report(self, *extra):
        before = self.fh.snapshot(str(self.fh.root))
        proc = self.fh.run_script(["report"] + list(extra), extra_env=self.extra)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.fh.snapshot(str(self.fh.root)), before,
                         "report modified the fake home")
        text = proc.stdout
        self.assertTrue(text.endswith("\n"))
        lines = text.splitlines()
        self.assertEqual(lines[0], REPORT_LINES[0])
        at = 0
        for prefix in REPORT_LINES[1:]:
            found = [i for i in range(at, len(lines)) if lines[i].startswith(prefix)]
            self.assertTrue(found, "no %r line after %d:\n%s" % (prefix, at, text))
            at = found[0] + 1
        self.check_anonymous(text)
        return text

    def line(self, text, prefix):
        found = [l for l in text.splitlines() if l.startswith(prefix)]
        self.assertEqual(len(found), 1, text)
        return found[0][len(prefix):]

    def check_anonymous(self, text):
        fh = self.fh
        tokens = {"alice", str(fh.home), str(fh.root), os.path.basename(str(fh.root))}
        for root, folder, name in PROFILES:
            real = os.path.realpath(str(fh.resolve(root + "/" + folder)))
            digest = hashlib.sha256(os.fsencode(real)).hexdigest()
            tokens.update((folder, name, folder.split(".", 1)[0], digest, digest[:12]))
        host = socket.gethostname()
        if host:
            tokens.update((host, host.split(".", 1)[0]))
        low = text.lower()
        for token in tokens:
            if len(token) >= 3:
                self.assertNotIn(token.lower(), low, "report leaks %r:\n%s" % (token, text))
        self.assertIsNone(re.search(r"~|/|://", text), "report shows a path:\n" + text)
        self.assertIsNone(re.search(r"\b[0-9a-f]{12}\b", text), "report shows an id:\n" + text)


class ReportTest(ReportCase):

    def test_layout_before_sync(self):
        self.home()
        text = self.report()
        self.assertEqual(self.line(text, "version: "), bg.VERSION)
        self.assertRegex(self.line(text, "python: "), r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertEqual(self.line(text, "dms: "), "unknown")
        self.assertEqual(self.line(text, "glass: "),
                         "active (reason active, opacity 0.85, source dms, mode dark)")
        self.assertEqual(self.line(text, "niri: "), "config yes, include no, rule no")
        self.assertEqual(self.line(text, "applied: "), "0 of 4 profiles")
        lines = text.splitlines()
        start = lines.index("profiles:")
        self.assertEqual(lines[start + 1:start + 4], [
            "  firefox native: 2 (0 running, 0 restart needed)",
            "  librewolf native: 1 (0 running, 0 restart needed)",
            "  zen native: 1 (0 running, 0 restart needed)",
        ])
        self.assertTrue(lines[start + 4].startswith("settings: "))
        self.assertEqual(self.line(text, "warnings: "), "zen_transparency_mod")

    def test_settings_line_matches_the_fixture(self):
        self.home()
        fixture = (test_contract.CONTRACT / "report.txt").read_text(encoding="utf-8")
        expected = [l for l in fixture.splitlines() if l.startswith("settings: ")]
        self.assertEqual(self.line(self.report(), "settings: "), expected[0][len("settings: "):])

    def test_after_sync_running_and_held(self):
        self.home()
        self.sync()
        holder = LockHolder(self.fh, MAIN + "/.parentlock")
        self.addCleanup(holder.stop)
        self.sync()
        self.sync(glassEnabled=False, excluded=["a.example", "b.example"])
        text = self.report()
        self.assertEqual(self.line(text, "glass: "),
                         "inactive (reason toggled_off, opacity 0.85, source dms, mode dark)")
        self.assertEqual(self.line(text, "niri: "),
                         "config yes, include yes, rule yes (held until a browser restarts)")
        self.assertIn("  firefox native: 2 (1 running, 1 restart needed)", text.splitlines())
        self.assertIn("glassEnabled=false", text)
        self.assertIn("excluded=2", text)
        self.assertNotIn("example", text, "settings values are counted, never shown")
        self.assertEqual(self.line(text, "warnings: "), "zen_transparency_mod, niri_rule_held")
        self.assertNotIn("stack", text, "warning messages are not shown")

    def test_versions(self):
        self.home()
        self.fh.write(str(self.fh.root / "dms-shell" / "VERSION"), "2.1.2\n")
        self.fh.write(MAIN + "/compatibility.ini",
                      "[Compatibility]\nLastVersion=128.0.3_20240701000000/20240701000000\n"
                      "LastOSABI=Linux_x86_64-gcc3\nLastPlatformDir=/usr/lib/firefox\n")
        self.fh.write(ZEN_P + "/compatibility.ini",
                      "[Compatibility]\nLastVersion=alice/../etc_1/1\n")
        text = self.report()
        self.assertEqual(self.line(text, "dms: "), "2.1.2")
        self.assertEqual(self.line(text, "browsers: "),
                         "firefox native 128.0.3, librewolf native unknown, zen native unknown")

    def test_dms_version_is_validated(self):
        self.home()
        shell = self.fh.root / "dms-shell" / "VERSION"
        for raw, shown in ((str(self.fh.home), "unknown"), ("1alice", "unknown"),
                           ("1.0-alice", "unknown"), ("v1.2.3+alice.secret", "unknown"),
                           ("v1.7.0", "v1.7.0"), ("1.7.0-12-gabcdef0", "1.7.0-12-gabcdef0")):
            with self.subTest(raw=raw):
                self.fh.write(str(shell), raw + "\n")
                self.assertEqual(self.line(self.report(), "dms: "), shown)

    def test_browser_versions_are_validated(self):
        self.home()
        for raw, shown in (("128alice_20240101/20240101", "unknown"),
                           ("1.0-alice_1/1", "unknown"), ("128.0.alice_1/1", "unknown"),
                           ("129.0b5_20240101/20240101", "129.0b5"),
                           ("115.9.0esr_1/1", "115.9.0esr"), ("1.7.6b_1/1", "1.7.6b"),
                           ("1.0.1-a.19_1/1", "1.0.1-a.19"), ("128.0", "128.0")):
            with self.subTest(raw=raw):
                self.fh.write(MAIN + "/compatibility.ini",
                              "[Compatibility]\r\nLastVersion=%s\r\n" % raw)
                self.assertTrue(self.line(self.report(), "browsers: ").startswith(
                    "firefox native %s," % shown))

    def test_last_sync_inputs(self):
        # The report shows what the last full sync decided.
        self.home()
        self.sync(blur=False, opacityOverride=True, opacity=0.5)
        text = self.report()
        self.assertEqual(self.line(text, "glass: "),
                         "inactive (reason blur_disabled, opacity 0.5, source override, mode dark)")
        self.assertEqual(self.line(text, "applied: "), "4 of 4 profiles")

    def test_sync_warning_codes(self):
        # A warning raised by the last full sync shows (code only), once.
        self.home()
        self.sync("--data", str(self.fh.root / "no-data"))
        text = self.report()
        self.assertEqual(self.line(text, "warnings: "), "zen_transparency_mod, data_unavailable")
        self.sync()
        self.assertEqual(self.line(self.report(), "warnings: "), "zen_transparency_mod")

    def test_not_applied_count(self):
        self.home()
        self.sync()
        self.fh.write(MAIN + "/chrome/dms-glass-chrome.css", "/* edited */\n")
        self.assertEqual(self.line(self.report(), "applied: "), "3 of 4 profiles")

    def test_empty_home(self):
        text = self.report()
        lines = text.splitlines()
        start = lines.index("profiles:")
        self.assertTrue(lines[start + 1].startswith("settings: "))
        self.assertEqual(self.line(text, "browsers: "), "none")
        self.assertEqual(self.line(text, "warnings: "), "none")
        self.assertEqual(self.line(text, "niri: "), "config no, include no, rule no")

    def test_deterministic_and_uninstall(self):
        self.home()
        self.sync()
        self.assertEqual(self.report(), self.report())
        proc = self.fh.run_script(["uninstall"], extra_env=self.extra)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.report()

    def test_fixture_is_anonymous_too(self):
        # The contract fixture follows the same rules (checked in the same way).
        fixture = (test_contract.CONTRACT / "report.txt").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"~|/|://", fixture))


if __name__ == "__main__":
    unittest.main()

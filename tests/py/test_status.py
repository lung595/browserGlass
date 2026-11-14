"""browserglass.py status --json (P4): contract, read-only, H1 held rule.

Runs the command line inside a FakeHome, plus unit tests of the helpers
(tilde_path, process_start, profile_applied, state.json "last_sync").
A running browser is a LockHolder child holding .parentlock.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import subprocess
import sys
import unittest

import test_contract
from fakehome import SCRIPT, FakeHome, LockHolder, kill_strays, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

FF = ".mozilla/firefox"
SNAP = "snap/firefox/common/.mozilla/firefox"
LWF = ".var/app/io.gitlab.librewolf-community/.librewolf"
ZEN = ".zen"
MAIN = FF + "/a1b2c3d4.default-release"
WORK = FF + "/e5f6g7h8.work"
SNAP_P = SNAP + "/i9j0k1l2.default"
LWF_P = LWF + "/m3n4o5p6.default"
ZEN_P = ZEN + "/q7r8s9t0.Default (release)"
ALL = (MAIN, WORK, SNAP_P, LWF_P, ZEN_P)
STATE = ".local/state/dms/browserGlass"
NIRI_CONFIG = ".config/niri/config.kdl"
NIRI_OUT = ".config/niri/dms-browser-glass.kdl"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


def tree(fh):
    """{path: (kind, mode, inode, mtime_ns, content)} of the whole fake root."""
    out = {}
    top = str(fh.root)
    for dirpath, dirnames, filenames in os.walk(top):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            st = os.lstat(full)
            content = None
            if os.path.isfile(full) and not os.path.islink(full):
                with open(full, "rb") as f:
                    content = f.read()
            out[os.path.relpath(full, top)] = (st.st_mode, st.st_ino, st.st_mtime_ns, content)
    return out


class StatusCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)

    def home(self, niri=True):
        fh = self.fh
        groups = {}
        for rel in ALL:
            root, folder = rel.rsplit("/", 1)
            fh.make_profile(root, folder, prefs={"browser.startup.page": 3})
            groups.setdefault(root, []).append({"name": folder.split(".", 1)[1], "path": folder,
                                                "default": not groups.get(root)})
        for root, entries in groups.items():
            fh.write_profiles_ini(root, entries)
        if niri:
            fh.write(NIRI_CONFIG, 'input {\n}\n\ninclude "dms/windowrules.kdl"\n')
        fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.9\n}\n")
        fh.write_dms_colors(mode="dark", surface_dark="#223344")

    def pid(self, rel):
        return bg.profile_id(str(self.fh.resolve(rel)))

    def browser(self, rel):
        holder = LockHolder(self.fh, rel + "/.parentlock")
        self.addCleanup(holder.stop)
        return holder

    def run_ok(self, args, spec):
        proc = self.fh.run_script(args, extra_env=FAST)
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        self.assertEqual(test_contract.validate(doc, SCHEMA[spec], DEFS), [], lines[0])
        return doc

    def sync(self, *extra, **over):
        return self.run_ok(["sync", "--settings", json.dumps(settings(**over))] + list(extra), "sync")

    def status(self, *extra):
        before = tree(self.fh)
        doc = self.run_ok(["status", "--json"] + list(extra), "status")
        self.assertEqual(tree(self.fh), before, "status modified the fake home")
        self.assertNotIn(str(self.fh.home), json.dumps(doc))
        return doc

    def profile(self, doc, rel):
        pid = self.pid(rel)
        for browser in doc["browsers"]:
            for profile in browser["profiles"]:
                if profile["id"] == pid:
                    return browser, profile
        self.fail("profile %s not in status" % rel)

    def codes(self, doc):
        return [w["code"] for w in doc["warnings"]]


class LayoutTest(StatusCase):

    def test_every_variant(self):
        self.home()
        doc = self.status()
        keys = [(b["family"], b["variant"], b["root"]) for b in doc["browsers"]]
        self.assertEqual(sorted(keys), sorted([
            ("firefox", "native", "~/" + FF), ("firefox", "snap", "~/" + SNAP),
            ("librewolf", "flatpak", "~/" + LWF), ("zen", "native", "~/" + ZEN)]))
        _, main = self.profile(doc, MAIN)
        self.assertEqual(main["path"], "~/" + MAIN)
        self.assertEqual(main["name"], "default-release")
        self.assertTrue(main["default"])
        self.assertFalse(self.profile(doc, WORK)[1]["default"])
        self.assertEqual(doc["version"], bg.VERSION)
        self.assertEqual(doc["glass"]["opacity"], 0.9)
        self.assertEqual(doc["glass"]["surface"], "#223344")
        self.assertEqual(doc["warnings"], [])

    def test_newline_in_a_profile_folder(self):
        self.home()
        self.fh.make_profile(FF, "weird\nname", prefs={"browser.startup.page": 3})
        self.fh.make_profile(FF, "plain.group", prefs={"browser.startup.page": 3})
        doc = self.status()
        paths = [p["path"] for b in doc["browsers"] for p in b["profiles"]]
        self.assertIn("~/" + FF + "/plain.group", paths)
        self.assertFalse(any("\n" in p for p in paths), paths)

    def test_read_only_creates_no_state_folder(self):
        self.home()
        self.status()
        self.assertFalse(self.fh.exists(STATE))
        self.assertFalse(self.fh.exists(".local/state/dms"))
        self.assertFalse(self.fh.exists(NIRI_OUT))

    def test_read_only_after_sync_with_a_running_browser(self):
        self.home()
        self.browser(MAIN)
        self.sync()
        snap = self.fh.snapshot()
        self.status()
        self.assertEqual(self.fh.snapshot(), snap)

    def test_stdin_bootstrap(self):
        self.home()
        proc = subprocess.run(
            [sys.executable, "-I", "-c", bg.STDIN_BOOTSTRAP, "status", "--json"],
            input=SCRIPT.read_text(encoding="utf-8"), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, universal_newlines=True, env=self.fh.env(FAST),
            cwd=str(self.fh.home), timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["status"], DEFS), [])

    def test_usage_errors(self):
        for args in (["status"], ["status", "--json", "--settings", "[1]"],
                     ["status", "--json", "--settings", "{nope"]):
            proc = self.fh.run_script(args, extra_env=FAST)
            self.assertEqual(proc.returncode, 2, args)
            doc = json.loads(proc.stdout)
            self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], proc.stdout)


class GlassInputsTest(StatusCase):

    def test_settings_of_the_last_sync(self):
        self.home()
        self.sync(opacityOverride=True, opacity=0.6, isLight=True)
        glass = self.status()["glass"]
        self.assertEqual((glass["opacity"], glass["opacity_source"], glass["mode"]),
                         (0.6, "override", "light"))
        self.assertEqual(glass["surface"], "#f7f9ff")
        self.assertTrue(glass["active"])

    def test_forced_opacity_and_off(self):
        self.home()
        self.sync("--opacity", "0.5")
        glass = self.status()["glass"]
        self.assertEqual((glass["opacity"], glass["opacity_source"]), (0.5, "forced"))
        self.sync("--off")
        glass = self.status()["glass"]
        self.assertEqual((glass["active"], glass["reason"]), (False, "forced_off"))

    def test_dms_opacity_read_now(self):
        # glass.dms_opacity is the DMS rule as it is now, whatever opacity
        # the last sync used (the settings page shows both)
        self.home()
        self.sync(opacityOverride=True, opacity=0.6)
        glass = self.status()["glass"]
        self.assertEqual((glass["opacity"], glass["dms_opacity"]), (0.6, 0.9))
        self.fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.7\n}\n")
        glass = self.status()["glass"]
        self.assertEqual((glass["opacity"], glass["dms_opacity"]), (0.6, 0.7))
        self.fh.resolve(".config/niri/dms/windowrules.kdl").unlink()
        self.assertEqual(self.status()["glass"]["dms_opacity"], bg.DEFAULT_OPACITY)

    def test_status_describes_the_last_sync(self):
        # glass.* is what the last full sync decided, as applied and niri
        # are: a DMS input changed since then shows after the next sync only.
        self.home()
        self.sync()
        self.fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 1.0\n}\n")
        doc = self.status()
        self.assertEqual((doc["glass"]["active"], doc["glass"]["opacity"]), (True, 0.9))
        self.assertTrue(all(p["applied"] for b in doc["browsers"] for p in b["profiles"]))
        self.assertTrue(doc["niri"]["rule"])
        self.sync()
        doc = self.status()
        self.assertEqual((doc["glass"]["active"], doc["glass"]["reason"]), (False, "opaque"))
        self.assertTrue(all(p["applied"] for b in doc["browsers"] for p in b["profiles"]))
        self.assertFalse(doc["niri"]["rule"])

    def test_preview_before_any_sync(self):
        self.home()
        self.fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 1\n}\n")
        glass = self.status()["glass"]
        self.assertEqual((glass["active"], glass["reason"], glass["opacity_source"]),
                         (False, "opaque", "dms"))

    def test_profile_sync_keeps_the_global_record(self):
        # A --profile sync (P10 captures) must not change what status shows
        # for the real profiles: no held rule, no restart, same opacity.
        self.home()
        self.sync()
        self.browser(MAIN)
        self.sync()
        other = self.fh.make_profile("media", "prof", prefs={"browser.startup.page": 3})
        out = self.sync("--profile", str(other), "--off")
        self.assertEqual(out["reason"], "forced_off")
        self.assertEqual(out["changed"], [bg.profile_id(str(other))])
        doc = self.status()
        self.assertEqual((doc["glass"]["active"], doc["glass"]["reason"]), (True, "active"))
        self.assertTrue(doc["niri"]["rule"])
        self.assertFalse(doc["restart_needed"])
        self.assertEqual(doc["warnings"], [])
        self.assertTrue(self.profile(doc, MAIN)[1]["running"])
        self.assertFalse(self.profile(doc, MAIN)[1]["restart_needed"])
        self.sync("--profile", str(other), "--opacity", "0.5")
        glass = self.status()["glass"]
        self.assertEqual((glass["opacity"], glass["opacity_source"]), (0.9, "dms"))
        self.assertIn("0.9", self.fh.read(MAIN + "/chrome/dms-glass-chrome.css"))

    def test_light_mode_without_colours(self):
        self.home()
        self.fh.resolve(".cache/dms/dms-colors.json").unlink()
        self.sync(isLight=True)
        glass = self.status()["glass"]
        self.assertEqual((glass["mode"], glass["surface"]), ("light", bg.DEFAULT_SURFACES["light"]))
        self.assertIn("rgba(247, 249, 255, 0.9)", self.fh.read(MAIN + "/chrome/dms-glass-chrome.css"))

    def test_no_effect_settings_leave_the_state_untouched(self):
        self.home()
        self.sync()
        before = self.fh.snapshot(STATE)
        out = self.sync(opacity=0.3)  # override off: the slider changes nothing
        self.assertEqual(out["changed"], [])
        self.assertEqual(self.fh.snapshot(STATE), before)

    def test_same_settings_keep_the_state_untouched(self):
        self.home()
        self.sync()
        before = self.fh.snapshot(STATE)
        out = self.sync()
        self.assertEqual(out["changed"], [])
        self.assertEqual(self.fh.snapshot(STATE), before)

    def test_corrupt_state(self):
        self.home()
        self.fh.write(STATE + "/state.json", "{broken")
        doc = self.status()
        self.assertIn("state_corrupt", self.codes(doc))
        self.assertEqual(self.fh.read(STATE + "/state.json"), "{broken")

    def test_newer_state(self):
        self.home()
        self.fh.write(STATE + "/state.json", '{"version": 99}\n')
        doc = self.status()
        self.assertIn("state_unavailable", self.codes(doc))
        self.assertEqual(self.fh.read(STATE + "/state.json"), '{"version": 99}\n')


class AppliedTest(StatusCase):

    def test_applied_follows_the_files(self):
        self.home()
        self.sync()
        for rel in ALL:
            self.assertTrue(self.profile(self.status(), rel)[1]["applied"], rel)
        # The user edits our user.js block: no longer what sync wrote.
        userjs = self.fh.read(MAIN + "/user.js")
        self.fh.write(MAIN + "/user.js", userjs.replace("true", "false", 1))
        self.fh.write(WORK + "/chrome/dms-glass-content.css", "/* emptied */\n")
        self.fh.write(SNAP_P + "/chrome/userChrome.css", "/* import removed */\n")
        doc = self.status()
        for rel in (MAIN, WORK, SNAP_P):
            self.assertFalse(self.profile(doc, rel)[1]["applied"], rel)
        self.assertTrue(self.profile(doc, LWF_P)[1]["applied"])
        self.sync()
        self.assertTrue(all(p["applied"] for b in self.status()["browsers"] for p in b["profiles"]))

    def test_unit_needs_a_hash(self):
        self.home()
        path = str(self.fh.resolve(MAIN))
        self.assertFalse(bg.profile_applied(path, None))
        self.assertFalse(bg.profile_applied(path, {"applied_hash": None}))


class RestartTest(StatusCase):

    def test_held_rule(self):
        # H1 (deferred from P3): glass off while a browser that loaded it
        # runs: the rule stays, status reports it and asks for a restart.
        self.home()
        self.sync()
        holder = self.browser(MAIN)
        self.sync()
        out = self.sync(glassEnabled=False)
        self.assertFalse(out["glass"])
        doc = self.status()
        self.assertFalse(doc["glass"]["active"])
        self.assertEqual(doc["glass"]["reason"], "toggled_off")
        self.assertTrue(doc["niri"]["rule"])
        self.assertTrue(doc["restart_needed"])
        held = [w for w in doc["warnings"] if w["code"] == "niri_rule_held"]
        self.assertEqual(held, [{"code": "niri_rule_held",
                                 "message": "the niri opacity rule stays until this browser restarts",
                                 "family": "firefox", "profile": self.pid(MAIN)}])
        browser, profile = self.profile(doc, MAIN)
        self.assertTrue(profile["running"] and profile["restart_needed"] and browser["restart_needed"])
        # Closed: nothing to restart any more (the next sync drops the rule).
        holder.release()
        holder.stop()
        doc = self.status()
        self.assertFalse(doc["restart_needed"])
        self.assertNotIn("niri_rule_held", self.codes(doc))
        self.assertTrue(doc["niri"]["rule"])
        self.assertEqual(doc["warnings"], [{
            "code": "niri_rule_stale",
            "message": "the niri opacity rule is no longer needed; the next sync removes it",
            "family": None, "profile": None}])
        self.sync(glassEnabled=False)
        doc = self.status()
        self.assertFalse(doc["niri"]["rule"])
        self.assertEqual(doc["warnings"], [])

    def test_held_instance_is_recorded(self):
        # sync records that the running browser loaded glass (H1).
        self.home()
        self.sync()
        self.browser(WORK)
        self.sync()
        self.sync(blur=False)
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertTrue(state["profiles"][self.pid(WORK)]["glass_loaded_since_start"])
        doc = self.status()
        self.assertTrue(doc["niri"]["rule"])
        self.assertTrue(doc["restart_needed"])

    def test_browser_started_without_glass_holds_nothing(self):
        self.home()
        self.sync(glassEnabled=False)
        self.browser(MAIN)
        self.sync(glassEnabled=False)
        doc = self.status()
        self.assertFalse(doc["niri"]["rule"])
        self.assertFalse(doc["restart_needed"])
        self.assertEqual(doc["warnings"], [])

    def test_unknown_lock_is_not_running(self):
        self.home()
        self.sync()
        os.symlink("elsewhere", str(self.fh.resolve(MAIN + "/.parentlock")))
        doc = self.status()
        _, profile = self.profile(doc, MAIN)
        self.assertFalse(profile["running"])
        self.assertFalse(profile["restart_needed"])
        # It still holds the rule (H1 counts it as running): said so.
        self.sync()
        self.sync(glassEnabled=False)
        doc = self.status()
        held = [w for w in doc["warnings"] if w["code"] == "niri_rule_held"]
        self.assertEqual([w["profile"] for w in held], [self.pid(MAIN)])
        self.assertIn("lock state is unknown", held[0]["message"])
        self.assertTrue(doc["restart_needed"])

    def test_niri_states(self):
        self.home(niri=False)
        self.assertEqual(self.status()["niri"], {"config": False, "include": False, "rule": False})
        self.fh.write(NIRI_CONFIG, '/*\ninclude optional=true "dms-browser-glass.kdl"\n*/\n')
        self.assertEqual(self.status()["niri"], {"config": True, "include": False, "rule": False})
        self.fh.write(NIRI_CONFIG, 'include optional=true "dms-browser-glass.kdl"\n')
        self.fh.write(NIRI_OUT, bg.niri_kdl(False))
        self.assertEqual(self.status()["niri"], {"config": True, "include": True, "rule": False})
        self.fh.write(NIRI_OUT, bg.niri_kdl(True) + "// edited\n")
        self.assertFalse(self.status()["niri"]["rule"], "a stale rule file is not current")


class HelpersTest(unittest.TestCase):

    def test_tilde_path(self):
        env = {"HOME": "/fake/u"}
        self.assertEqual(bg.tilde_path("/fake/u", env), "~")
        self.assertEqual(bg.tilde_path("/fake/u/.zen/a b", env), "~/.zen/a b")
        self.assertEqual(bg.tilde_path("/fake/other", env), "~/../other")

    def test_process_start(self):
        self.assertIsNone(bg.process_start("?"))
        self.assertIsNone(bg.process_start(None))
        self.assertIsNone(bg.process_start("12:x"))
        own = bg.read_text("/proc/self/stat")
        ticks = own[own.rindex(")") + 2:].split()[19]
        start = bg.process_start("1:" + ticks)
        self.assertIsNotNone(start)
        import time
        self.assertLess(start, time.time() + 1)
        self.assertGreater(start, time.time() - 3600 * 24 * 365)

    def glass(self, **over):
        doc = {"active": True, "reason": "active", "opacity": 0.8, "opacity_source": "dms",
               "surface": "#101418", "mode": "dark"}
        doc.update(over)
        return doc

    def test_last_sync_normalised(self):
        norm = bg._norm_last_sync
        self.assertIsNone(norm(None))
        self.assertIsNone(norm({"settings": "x", "glass": self.glass()}))
        self.assertIsNone(norm({"settings": {}}))
        for bad in ({"active": False}, {"reason": "nope"}, {"opacity": 7}, {"opacity": True},
                    {"opacity": float("nan")}, {"opacity_source": "x"}, {"surface": "red"},
                    {"surface": "#ABCDEF"}, {"mode": "sepia"}):
            self.assertIsNone(norm({"settings": {}, "glass": self.glass(**bad)}), bad)
        out = norm({"settings": {"glassEnabled": "no", "bogus": 1, "blur": False},
                    "glass": self.glass(), "warning_codes": ["write_failed", "BAD", 3,
                                                            "write_failed", "x" * 99]})
        expected = dict(bg.settings_from_json({"glassEnabled": False}))
        for key in ("blur", "isLight", "opacity"):
            del expected[key]
        self.assertEqual(out["settings"], expected)
        self.assertEqual(dict(out["glass"]), self.glass())
        self.assertEqual(out["warning_codes"], ["write_failed"])
        self.assertEqual(norm({"settings": {}, "glass": self.glass()})["warning_codes"], [])

    def test_state_load_keeps_last_sync(self):
        with FakeHome() as fh:
            folder = str(fh.resolve(STATE))
            os.makedirs(folder)
            state = bg.new_state(synced=True)
            self.assertIsNone(state["last_sync"])
            state["last_sync"] = bg.last_sync_record(
                bg.settings_from_json({}), self.glass(), [bg.make_warning("write_failed", "x")])
            with open(os.path.join(folder, "state.json"), "w") as f:
                f.write(bg.state_text(state))
            loaded, existed = bg.state_load(folder, [])
            self.assertTrue(existed)
            self.assertEqual(bg.state_text(loaded), bg.state_text(state))


if __name__ == "__main__":
    unittest.main()

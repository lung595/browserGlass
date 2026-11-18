"""The companion add-on in the profiles: sync --plugin-dir deposits the xpi,
the 3 companion prefs and the native messaging files; status reports them;
uninstall removes all of it, the browser's own records of the add-on
included. Every browser here is a folder in a FakeHome.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

import test_contract
from fakehome import (PREFS_HEADER, REPO, SCRIPT, FakeHome, LockHolder, fake_home_pids,
                      kill_strays, load_script, wait_until)

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05", "BG_POLL_MAX": "20"}
BOOTSTRAP = "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))"
STATE = ".local/state/dms/browserGlass"
MANIFEST = ".mozilla/native-messaging-hosts/" + bg.NATIVE_MANIFEST_NAME
NIRI_CONFIG = ".config/niri/config.kdl"
LIBREWOLF = ".librewolf/lw0001.default"
FIREFOX = ".mozilla/firefox/ff0001.default-release"
FIREFOX_NIGHTLY = ".mozilla/firefox/ff0003.default-nightly"
BETA = ".mozilla/firefox/ff0004.default-beta"
FLATPAK = ".var/app/org.mozilla.firefox/.mozilla/firefox/fp0001.default"
SNAP = "snap/firefox/common/.mozilla/firefox/sn0001.default"
XPI_REL = "/extensions/" + bg.COMPANION_XPI
SIG, AUTO, SCAN = bg.PREF_SIGNATURES, bg.PREF_AUTODISABLE, bg.PREF_STARTUP_SCAN
OTHER_UUID = "11111111-2222-3333-4444-555555555555"
OUR_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def prefs_text(prefs):
    return PREFS_HEADER + "".join('user_pref("%s", %s);\n' % kv for kv in sorted(prefs.items()))


def settings_json(**over):
    # The contract's defaults with Live control on (off by default): these
    # tests are about the companion add-on
    doc = dict(test_contract.load_json("settings-default.json"), liveControl=True)
    doc.update(over)
    return json.dumps(doc)


def _without(snapshot, prefix):
    return {k: v for k, v in snapshot.items() if not (k == prefix or k.startswith(prefix + "/"))}


class CompanionCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)
        self.fh.write(NIRI_CONFIG, "input {\n}\n", mode=0o644)
        self.fh.write_dms_colors()

    def profile(self, rel, prefs=None, version="140.0_20250101000000/20250101000000", channel=None):
        """A profile at `rel` with its profiles.ini and a compatibility.ini
        naming a browser build whose channel-prefs.js says `channel`."""
        fh = self.fh
        root, name = os.path.split(rel)
        fh.write(rel + "/prefs.js", prefs_text(prefs or {"browser.startup.page": "3"}))
        fh.write_profiles_ini(root, [{"name": name, "path": name, "default": True}])
        lines = ["[Compatibility]", "LastVersion=" + version]
        if channel is not None:
            build = fh.root / "opt" / name
            build.joinpath("defaults", "pref").mkdir(parents=True, exist_ok=True)
            build.joinpath("defaults", "pref", "channel-prefs.js").write_text(
                'pref("app.update.channel", "%s");\n' % channel, encoding="utf-8")
            lines.append("LastPlatformDir=%s" % build)
        fh.write(rel + "/compatibility.ini", "\n".join(lines) + "\n")
        return bg.profile_id(str(fh.resolve(rel)))

    def check(self, proc, command):
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        self.assertEqual(test_contract.validate(doc, SCHEMA[command], DEFS), [], lines[0])
        return doc

    def sync(self, plugin_dir=REPO, **over):
        args = ["sync", "--settings", settings_json(**over)]
        if plugin_dir is not None:
            args += ["--plugin-dir", str(plugin_dir)]
        doc = self.check(self.fh.run_script(args, extra_env=FAST), "sync")
        return doc

    def states(self, doc):
        return {item["profile"]: item["state"] for item in doc["companion"]}

    def uninstall(self):
        return self.check(self.fh.run_script(["uninstall"], extra_env=FAST), "uninstall")

    def status(self):
        doc = self.check(self.fh.run_script(["status", "--json"], extra_env=FAST), "status")
        return doc, {p["id"]: p["companion"] for b in doc["browsers"] for p in b["profiles"]}

    def update_browser(self, rel):
        """A new browser build ran the profile `rel` (LastVersion changes,
        its build folder stays)."""
        path = rel + "/compatibility.ini"
        self.fh.write(path, self.fh.read(path).replace(
            "LastVersion=140.0_20250101000000/20250101000000",
            "LastVersion=141.0_20250201000000/20250201000000"))

    def userjs(self, rel):
        path = rel + "/user.js"
        return bg.parse_prefs(self.fh.read(path)) if self.fh.exists(path) else {}

    def leftovers(self):
        """Files of the companion still anywhere in the fake tree."""
        found = []
        for dirpath, dirnames, filenames in os.walk(str(self.fh.root)):
            for name in dirnames + filenames:
                if name in (bg.COMPANION_XPI, bg.NATIVE_MANIFEST_NAME, bg.HOST_WRAPPER,
                            bg.RUNTIME_DIR_NAME, "native-messaging-hosts"):
                    found.append(os.path.relpath(os.path.join(dirpath, name), str(self.fh.root)))
        return found


class DepositTest(CompanionCase):

    def test_round_trip_every_variant(self):
        lw = self.profile(LIBREWOLF)
        ff = self.profile(FIREFOX, channel="release")
        nightly = self.profile(FIREFOX_NIGHTLY, channel="nightly")
        self.fh.write_profiles_ini(".mozilla/firefox", [
            {"name": os.path.basename(FIREFOX), "path": os.path.basename(FIREFOX), "default": True},
            {"name": os.path.basename(FIREFOX_NIGHTLY), "path": os.path.basename(FIREFOX_NIGHTLY)}])
        fp = self.profile(FLATPAK)
        sn = self.profile(SNAP)
        before = self.fh.snapshot(".")
        out = self.sync()
        self.assertEqual(self.states(out), {
            lw: bg.COMPANION_PENDING, ff: bg.COMPANION_ENFORCED, nightly: bg.COMPANION_PENDING,
            fp: bg.COMPANION_UNSUPPORTED, sn: bg.COMPANION_UNSUPPORTED})
        for rel in (LIBREWOLF, FIREFOX_NIGHTLY):
            xpi = self.fh.resolve(rel + XPI_REL)
            self.assertEqual(xpi.read_bytes(), bg.companion_xpi(str(REPO / bg.EXTENSION_DIR)))
            self.assertEqual(os.stat(str(xpi)).st_mode & 0o777, 0o644)
            prefs = self.userjs(rel)
            self.assertEqual((prefs[SIG], prefs[AUTO], prefs[SCAN]), ("false", "14", "1"), rel)
        for rel in (FIREFOX, FLATPAK, SNAP):
            self.assertFalse(self.fh.exists(rel + "/extensions"), rel)
            self.assertFalse(set(self.userjs(rel)) & set(bg.COMPANION_PREFS), rel)
        manifest = json.loads(self.fh.read(MANIFEST))
        wrapper = str(self.fh.resolve(STATE + "/" + bg.HOST_WRAPPER))
        self.assertEqual(manifest["path"], wrapper)
        self.assertEqual(manifest["allowed_extensions"], [bg.COMPANION_ID])
        self.assertEqual(os.stat(wrapper).st_mode & 0o777, 0o755)
        self.assertIn(str(REPO), self.fh.read(STATE + "/" + bg.HOST_WRAPPER))

        snap = self.fh.snapshot(".")
        again = self.sync()
        self.assertEqual(self.states(again), self.states(out))
        self.assertEqual(self.fh.snapshot("."), snap, "a second sync writes nothing")

        # The browser copied user.js into prefs.js: uninstall restores it.
        for rel in (LIBREWOLF, FIREFOX_NIGHTLY):
            self.fh.write(rel + "/prefs.js", prefs_text(dict(
                {"browser.startup.page": "3"}, **self.userjs(rel))))
        out = self.uninstall()
        self.assertEqual(sorted(out["xpi_removed"]), sorted([lw, nightly]))
        self.assertTrue(out["native_host_removed"])
        self.assertEqual(out["warnings"], [])
        self.assertEqual(self.fh.snapshot("."), _without(before, ".cache/dms/browserGlass"))
        self.assertEqual(self.leftovers(), [])

    def test_unknown_channel_deposits(self):
        ff = self.profile(FIREFOX, channel="nightly")
        out = self.sync()
        self.assertEqual(self.states(out), {ff: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(FIREFOX + XPI_REL))
        ff2 = FIREFOX.replace("ff0001", "ff0002")
        self.fh.write(ff2 + "/prefs.js", prefs_text({}))
        self.fh.write_profiles_ini(".mozilla/firefox", [
            {"name": "a", "path": os.path.basename(FIREFOX), "default": True},
            {"name": "b", "path": os.path.basename(ff2)}])
        out = self.sync()
        self.assertEqual(self.states(out)[bg.profile_id(str(self.fh.resolve(ff2)))],
                         bg.COMPANION_PENDING, "no compatibility.ini: unknown channel")

    def test_never_run_profile_takes_the_installed_channel(self):
        rel = FIREFOX.replace("ff0001", "ff0002")
        self.fh.write(rel + "/prefs.js", prefs_text({}))
        self.fh.write_profiles_ini(".mozilla/firefox", [{"name": "b", "path": os.path.basename(rel),
                                                         "default": True}])
        ff = bg.profile_id(str(self.fh.resolve(rel)))
        build = self.fh.root / "usr" / "lib64" / "firefox" / "defaults" / "pref"
        for channel, state in (("release", bg.COMPANION_ENFORCED), ("esr", bg.COMPANION_ENFORCED),
                               ("beta", bg.COMPANION_ENFORCED), ("nightly", bg.COMPANION_PENDING)):
            with self.subTest(channel=channel):
                build.mkdir(parents=True, exist_ok=True)
                build.joinpath("channel-prefs.js").write_text(
                    'pref("app.update.channel", "%s");\n' % channel, encoding="utf-8")
                self.assertEqual(self.states(self.sync()), {ff: state})
                self.assertEqual(self.fh.exists(rel + XPI_REL), state == bg.COMPANION_PENDING)

    def test_esr_is_enforced(self):
        ff = self.profile(FIREFOX, channel="esr")
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_ENFORCED})
        self.assertFalse(self.fh.exists(FIREFOX + "/extensions"))
        self.assertFalse(self.fh.exists(MANIFEST), "no deposited profile, no host")
        self.assertFalse(self.fh.exists(STATE + "/" + bg.HOST_WRAPPER))

    def test_scope_prefs_keep_the_other_bits(self):
        for value, expected in (("0", "0"), ("15", "14"), ("5", "4"), (None, "14")):
            with self.subTest(value=value):
                fh = FakeHome()
                self.addCleanup(fh.cleanup)
                self.fh, keep = fh, self.fh
                try:
                    prefs = {"browser.startup.page": "3"}
                    if value is not None:
                        prefs[AUTO] = value
                        prefs[SCAN] = "4"
                    self.profile(LIBREWOLF, prefs=prefs)
                    self.sync()
                    got = self.userjs(LIBREWOLF)
                    self.assertEqual(got[AUTO], expected)
                    self.assertEqual(got[SCAN], "5" if value is not None else "1")
                    # The browser copied user.js into prefs.js; uninstall gives
                    # the originals back.
                    managed = dict(prefs, **{SIG: "false", AUTO: got[AUTO], SCAN: got[SCAN]})
                    self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(managed))
                    self.uninstall()
                    self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
                finally:
                    self.fh = keep

    def test_without_plugin_dir_nothing_moves(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        snap = self.fh.snapshot(".")
        out = self.sync(plugin_dir=None)
        self.assertNotIn("companion", out)
        self.assertEqual(self.fh.snapshot("."), snap, "R15: left as it is")
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_PENDING)

    def test_v10_install_then_plugin_dir(self):
        prefs = {"browser.startup.page": "3", AUTO: "11"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync(plugin_dir=None)
        self.assertFalse(set(self.userjs(LIBREWOLF)) & set(bg.COMPANION_PREFS))
        self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
        out = self.sync()
        self.assertEqual(self.states(out), {lw: bg.COMPANION_PENDING})
        self.assertEqual(self.userjs(LIBREWOLF)[AUTO], "10")
        managed = dict(prefs, **{SIG: "false", AUTO: "10", SCAN: "1"})
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(managed))
        self.uninstall()
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))

    def test_live_control_off_removes_everything(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        self.assertTrue(self.fh.exists(MANIFEST))
        out = self.sync(liveControl=False)
        self.assertEqual(self.states(out), {lw: bg.COMPANION_OFF})
        self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
        self.assertFalse(self.fh.exists(MANIFEST))
        self.assertFalse(self.fh.exists(".mozilla"), "the folders made for the manifest")
        self.assertFalse(self.fh.exists(STATE + "/" + bg.HOST_WRAPPER))
        self.assertFalse(set(self.userjs(LIBREWOLF)) & set(bg.COMPANION_PREFS))
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_OFF)
        self.assertEqual(status["companion"]["state"], "off")

    def off_while_running(self, prefs):
        """liveControl on, then off while the browser runs; the browser
        then exits writing the companion prefs it had into prefs.js."""
        self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        self.sync(liveControl=False)
        got = self.userjs(LIBREWOLF)
        self.assertEqual((got.get(SIG), got.get(AUTO), got.get(SCAN)), ("true", "11", "0"),
                         "the originals hold until prefs.js is restored")
        self.fh.write(LIBREWOLF + "/prefs.js",
                      prefs_text(dict(prefs, **{SIG: "false", AUTO: "10", SCAN: "1"})))
        holder.release()
        holder.stop()

    def test_live_control_off_while_running(self):
        prefs = {"browser.startup.page": "3", AUTO: "11"}
        self.off_while_running(prefs)
        # Started again before any sync: user.js still overrides prefs.js.
        got = self.userjs(LIBREWOLF)
        self.assertEqual((got.get(SIG), got.get(AUTO), got.get(SCAN)), ("true", "11", "0"))
        self.sync(liveControl=False)
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.assertFalse(set(self.userjs(LIBREWOLF)) & set(bg.COMPANION_PREFS))
        before = self.fh.snapshot(".")
        self.sync(liveControl=False)
        self.assertEqual(self.fh.snapshot("."), before, "a second sync changes nothing")

    def test_live_control_off_while_running_then_uninstall(self):
        prefs = {"browser.startup.page": "3", AUTO: "11"}
        self.off_while_running(prefs)
        self.uninstall()
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.assertFalse(self.fh.exists(LIBREWOLF + "/user.js"))

    def test_missing_extension_folder_warns(self):
        lw = self.profile(LIBREWOLF)
        plugin = self.fh.root / "plugin"
        plugin.mkdir()
        out = self.sync(plugin_dir=plugin)
        self.assertIn("data_unavailable", [w["code"] for w in out["warnings"]])
        self.assertEqual(self.states(out), {lw: bg.COMPANION_NO_PLUGIN})
        self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
        self.assertFalse(self.fh.exists(MANIFEST))
        (plugin / bg.EXTENSION_DIR).mkdir()
        out = self.sync(plugin_dir=plugin)
        messages = [w["message"] for w in out["warnings"] if w["code"] == "data_unavailable"]
        self.assertEqual(messages, ["companion add-on unavailable: extension/: no manifest.json"])
        self.assertNotIn(str(self.fh.root), json.dumps(out), "no path in the warnings")


class RefusedTest(CompanionCase):

    def test_deleted_by_the_browser(self):
        # A build with a channel we do not know (a distribution's own) may
        # require signed add-ons: the deposit happens, and the browser deletes it.
        ff = self.profile(BETA, channel="distro-custom")
        self.sync()
        dropped = os.stat(str(self.fh.resolve(BETA + XPI_REL))).st_mtime
        # The browser started, refused the unsigned add-on and deleted it.
        os.unlink(str(self.fh.resolve(BETA + XPI_REL)))
        compat = str(self.fh.resolve(BETA + "/compatibility.ini"))
        os.utime(compat, (dropped + 10, dropped + 10))
        out = self.sync()
        self.assertEqual(self.states(out), {ff: bg.COMPANION_REFUSED})
        self.assertFalse(self.fh.exists(BETA + XPI_REL), "no new deposit")
        self.assertFalse(set(self.userjs(BETA)) & set(bg.COMPANION_PREFS))
        self.assertFalse(self.fh.exists(MANIFEST))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REFUSED}, "still refused")
        status, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_REFUSED)
        # A new browser build: try again.
        self.update_browser(BETA)
        out = self.sync()
        self.assertEqual(self.states(out), {ff: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(BETA + XPI_REL))
        self.assertEqual(self.userjs(BETA)[SIG], "false")
        self.assertTrue(self.fh.exists(MANIFEST))


class RemovedByUserTest(CompanionCase):

    def prefsjs(self, rel):
        return bg.parse_prefs(self.fh.read(rel + "/prefs.js"))

    def removed(self, lw):
        """Assert the state of a profile whose add-on the user removed."""
        self.assertFalse(self.fh.exists(LIBREWOLF + XPI_REL), "no new deposit")
        self.assertFalse(set(self.userjs(LIBREWOLF)) & set(bg.COMPANION_PREFS))
        self.assertFalse(set(self.prefsjs(LIBREWOLF)) & set(bg.COMPANION_PREFS),
                         "the originals (absent) back in prefs.js")
        self.assertEqual(self.prefsjs(LIBREWOLF)["browser.startup.page"], "3")
        self.assertFalse(self.fh.exists(MANIFEST))
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_REMOVED)
        self.assertEqual(status["companion"]["state"], "removed")

    def test_removed_in_about_addons(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        # The browser started, registered and enabled the add-on, and
        # copied the companion prefs into prefs.js.
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON,
                      json.dumps({"addons": [{"id": bg.COMPANION_ID}]}))
        prefs = dict(self.userjs(LIBREWOLF), **{"browser.startup.page": "3"})
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(prefs))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_INSTALLED})
        # Removed in about:addons: xpi deleted, extensions.json entry dropped.
        dropped = os.stat(str(self.fh.resolve(LIBREWOLF + XPI_REL))).st_mtime
        os.unlink(str(self.fh.resolve(LIBREWOLF + XPI_REL)))
        ext_json = str(self.fh.resolve(LIBREWOLF + "/" + bg.EXTENSIONS_JSON))
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        os.utime(ext_json, (dropped + 10, dropped + 10))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.removed(lw)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED}, "stable")
        self.sync(plugin_dir=None)
        self.removed(lw)
        # A browser update: still left out.
        self.update_browser(LIBREWOLF)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.removed(lw)
        # Live control off and on again: placed again.
        self.assertEqual(self.states(self.sync(liveControl=False)), {lw: bg.COMPANION_OFF})
        out = self.sync()
        self.assertEqual(self.states(out), {lw: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(LIBREWOLF + XPI_REL))
        self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
        self.assertTrue(self.fh.exists(MANIFEST))

    def test_uninstall_clears_the_mark(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON,
                      json.dumps({"addons": [{"id": bg.COMPANION_ID}]}))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_INSTALLED})
        os.unlink(str(self.fh.resolve(LIBREWOLF + XPI_REL)))
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.uninstall()
        # The plugin enabled again.
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(LIBREWOLF + XPI_REL))

    def test_removal_survives_a_lost_state(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON,
                      json.dumps({"addons": [{"id": bg.COMPANION_ID}]}))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_INSTALLED})
        os.unlink(str(self.fh.resolve(LIBREWOLF + XPI_REL)))
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        meta = STATE + "/%s/%s/%s" % (bg.BACKUP_DIR, lw, bg.BACKUP_META)
        self.assertIs(json.loads(self.fh.read(meta))["companion_removed"], True)
        os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.removed(lw)
        # Live control off and on again still places it.
        self.assertEqual(self.states(self.sync(liveControl=False)), {lw: bg.COMPANION_OFF})
        os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(LIBREWOLF + XPI_REL))

    def test_removal_mark_parsed(self):
        base = {"path": "/p", "files": {}, "prefs_original": None}
        for value, expected in ((True, True), (False, False), (None, False), ("true", False),
                                (1, False), ([True], False), ({"x": 1}, False)):
            doc = dict(base, companion_removed=value)
            self.assertIs(bg._norm_backup(doc)["companion_removed"], expected, repr(value))
        self.assertIs(bg._norm_backup(base)["companion_removed"], False, "absent")
        self.assertNotIn("garbage", bg._norm_backup(dict(base, garbage=True)))

    def test_never_seen_is_not_a_removal(self):
        # Deposited, never seen registered by a sync, then gone, on a build
        # that may require signed add-ons: the browser's refusal.
        ff = self.profile(BETA, channel="distro-custom")
        self.sync()
        dropped = os.stat(str(self.fh.resolve(BETA + XPI_REL))).st_mtime
        os.unlink(str(self.fh.resolve(BETA + XPI_REL)))
        compat = str(self.fh.resolve(BETA + "/compatibility.ini"))
        os.utime(compat, (dropped + 10, dropped + 10))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REFUSED})

    def removed_before_any_sync(self, rel):
        """Deposit in `rel`; the browser starts and registers the add-on,
        and the user removes it in about:addons, with no sync between."""
        self.sync()
        xpi = str(self.fh.resolve(rel + XPI_REL))
        dropped = os.stat(xpi).st_mtime
        ext_json = str(self.fh.resolve(rel + "/" + bg.EXTENSIONS_JSON))
        self.fh.write(rel + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": [{"id": bg.COMPANION_ID}]}))
        os.unlink(xpi)
        self.fh.write(rel + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        os.utime(ext_json, (dropped + 10, dropped + 10))

    def test_removed_before_any_sync(self):
        # LibreWolf never deletes an unsigned add-on: only the user did.
        lw = self.profile(LIBREWOLF)
        self.removed_before_any_sync(LIBREWOLF)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.removed(lw)
        # A browser update: not placed again.
        self.update_browser(LIBREWOLF)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_REMOVED})
        self.removed(lw)
        self.assertEqual(self.states(self.sync(liveControl=False)), {lw: bg.COMPANION_OFF})
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_PENDING})
        self.assertTrue(self.fh.exists(LIBREWOLF + XPI_REL))

    def test_removed_from_firefox_nightly(self):
        ff = self.profile(FIREFOX_NIGHTLY, channel="nightly")
        self.removed_before_any_sync(FIREFOX_NIGHTLY)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED})
        self.update_browser(FIREFOX_NIGHTLY)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED})
        self.assertFalse(self.fh.exists(FIREFOX_NIGHTLY + XPI_REL))
        _, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_REMOVED)


class StatusTest(CompanionCase):

    def test_status_and_report(self):
        lw = self.profile(LIBREWOLF)
        fp = self.profile(FLATPAK)
        self.sync()
        status, per = self.status()
        self.assertEqual(per, {lw: bg.COMPANION_PENDING, fp: bg.COMPANION_UNSUPPORTED})
        self.assertEqual(dict(status["companion"]), {
            "enabled": True, "state": "waiting_restart", "hosts": 0, "manifest": True})
        # The browser registered it at its start.
        self.fh.write(LIBREWOLF + "/" + bg.EXTENSIONS_JSON,
                      json.dumps({"addons": [{"id": bg.COMPANION_ID}]}))
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_INSTALLED)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_INSTALLED,
                                                     fp: bg.COMPANION_UNSUPPORTED})
        proc = self.fh.run_script(["report"], extra_env=FAST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("companion: waiting_restart (hosts 0, manifest yes, profiles "
                      "installed 1, unsupported_variant 1)", proc.stdout.splitlines())

    def test_outdated_host(self):
        # The running browser's host speaks another protocol: per profile
        # "outdated", and the summary waits for one more restart.
        lw = self.profile(LIBREWOLF)
        self.sync()
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        bpid = holder.child.pid
        rdir = self.fh.runtime / bg.RUNTIME_DIR_NAME
        rdir.mkdir(mode=0o700)
        active = rdir / ("active-%d.json" % bpid)
        active.write_text(json.dumps({"version": 1, "browser_pid": bpid, "outdated": True}),
                          encoding="utf-8")
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_OUTDATED)
        self.assertEqual((status["companion"]["state"], status["companion"]["hosts"]),
                         ("waiting_restart", 0))
        (rdir / ("host-%d.sock" % bpid)).write_text("", encoding="utf-8")
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_OUTDATED)
        self.assertEqual((status["companion"]["state"], status["companion"]["hosts"]),
                         ("waiting_restart", 1), "an outdated host is not connected")
        active.write_text(json.dumps({"version": 1, "browser_pid": bpid, "host": ""}),
                          encoding="utf-8")
        status, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_PENDING)
        self.assertEqual(status["companion"]["state"], "connected")

    def test_nothing_deposited(self):
        self.profile(LIBREWOLF)
        # No sync yet: liveControl reads its default, off
        status, per = self.status()
        self.assertEqual(list(per.values()), [bg.COMPANION_OFF])
        self.assertEqual(status["companion"]["state"], "off")
        # On, synced without the plugin folder: nothing deposited
        self.sync(plugin_dir=None)
        status, per = self.status()
        self.assertEqual(list(per.values()), [bg.COMPANION_NO_PLUGIN])
        self.assertEqual(status["companion"]["state"], "unavailable")
        self.assertFalse(status["companion"]["manifest"])


class UninstallTest(CompanionCase):

    def residues(self, prefs):
        uuids = {"other@example.org": OTHER_UUID, bg.COMPANION_ID: OUR_UUID}
        return dict(prefs, **{
            bg.PREF_EXT_UUIDS: json.dumps(json.dumps(uuids, separators=(",", ":"))),
            bg.PREF_EXT_MIGRATED: "true"})

    def storage(self, rel):
        base = rel + "/storage/default/"
        ours = [base + name % OUR_UUID for name in bg._EXT_STORAGE]
        other = base + bg._EXT_STORAGE[0] % OTHER_UUID
        for folder in ours + [other]:
            self.fh.write(folder + "/idb/data.sqlite", b"x")
        return ours, other

    def expected_prefs(self, prefs):
        kept = json.dumps(json.dumps({"other@example.org": OTHER_UUID}, separators=(",", ":")))
        return prefs_text(dict(prefs, **{bg.PREF_EXT_UUIDS: kept}))

    def test_residues_removed(self):
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        ours, other = self.storage(LIBREWOLF)
        managed = self.residues(dict(prefs, **{SIG: "false", AUTO: "14", SCAN: "1"}))
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(managed))
        out = self.uninstall()
        self.assertEqual(out["xpi_removed"], [lw])
        self.assertEqual(out["pending"], [])
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), self.expected_prefs(prefs))
        for folder in ours:
            self.assertFalse(self.fh.exists(folder), folder)
        self.assertTrue(self.fh.exists(other))
        self.assertEqual(self.leftovers(), [])

    def test_residues_without_a_restore(self):
        # The companion prefs already gone (liveControl turned off): only the
        # browser's records of the add-on remain.
        prefs = {"browser.startup.page": "3"}
        self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        self.sync(liveControl=False)
        self.storage(LIBREWOLF)
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(self.residues(prefs)))
        self.uninstall()
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), self.expected_prefs(prefs))

    def test_running_browser_cleaned_after_exit(self):
        prefs = {"browser.startup.page": "3", AUTO: "15"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        ours, other = self.storage(LIBREWOLF)
        managed = prefs_text(self.residues(dict(prefs, **{SIG: "false", AUTO: "14", SCAN: "1"})))
        self.fh.write(LIBREWOLF + "/prefs.js", managed)
        rdir = self.fh.runtime / bg.RUNTIME_DIR_NAME
        rdir.mkdir(mode=0o700)
        (rdir / "active-4242.json").write_text("{}", encoding="utf-8")
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [lw])
        self.assertEqual(out["xpi_removed"], [lw])
        self.assertTrue(out["runtime_removed"])
        self.assertFalse(rdir.exists())
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), managed, "written while running")
        holder.release()
        expected = self.expected_prefs(prefs)
        self.assertTrue(wait_until(lambda: self.fh.read(LIBREWOLF + "/prefs.js") == expected),
                        self.fh.read(LIBREWOLF + "/prefs.js"))
        self.assertTrue(wait_until(lambda: not any(self.fh.exists(f) for f in ours)))
        self.assertTrue(self.fh.exists(other))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE))
        self.assertEqual(self.leftovers(), [])

    def test_clean_prefs_runs_a_residues_only_record(self):
        # The detached cleaner gave up while the browser ran: clean-prefs
        # still runs the record whose plan is [] (the residues alone).
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        ours, other = self.storage(LIBREWOLF)
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(self.residues(prefs)))
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        proc = self.fh.run_script(["uninstall"], extra_env=dict(FAST, BG_POLL_MAX="0.2"))
        self.assertEqual(self.check(proc, "uninstall")["pending"], [lw])
        pending = STATE + "/" + bg.PENDING_DIR + "/%s.json" % lw
        self.assertTrue(self.fh.exists(pending))
        self.assertTrue(wait_until(lambda: fake_home_pids(self.fh) == [holder.child.pid], timeout=5),
                        "cleanup still polling past BG_POLL_MAX")
        holder.release()
        holder.stop()
        proc = self.fh.run_script(["clean-prefs", str(self.fh.resolve(LIBREWOLF))], extra_env=FAST)
        self.assertEqual((proc.returncode, proc.stdout), (0, ""), proc.stderr)
        self.assertFalse(self.fh.exists(pending))
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), self.expected_prefs(prefs))
        for folder in ours:
            self.assertFalse(self.fh.exists(folder), folder)
        self.assertTrue(self.fh.exists(other))
        self.assertFalse(self.fh.exists(STATE), "the state folder is tidied")

    def test_from_stdin_text_with_the_plugin_gone(self):
        plugin = self.fh.root / "plugin"
        shutil.copytree(str(REPO / bg.EXTENSION_DIR), str(plugin / bg.EXTENSION_DIR))
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        before = self.fh.snapshot(".")
        self.sync(plugin_dir=plugin)
        self.assertIn(str(plugin), self.fh.read(STATE + "/" + bg.HOST_WRAPPER))
        shutil.rmtree(str(plugin))
        empty = self.fh.root / "empty-cwd"
        empty.mkdir()
        proc = subprocess.run(
            [sys.executable or "python3", "-I", "-c", BOOTSTRAP, "uninstall"],
            input=SCRIPT.read_text(encoding="utf-8"), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, universal_newlines=True, env=self.fh.env(FAST),
            cwd=str(empty), timeout=60)
        out = self.check(proc, "uninstall")
        self.assertEqual(out["xpi_removed"], [lw])
        self.assertTrue(out["native_host_removed"])
        self.assertEqual(os.listdir(str(empty)), [])
        self.assertEqual(self.fh.snapshot("."), _without(before, ".cache/dms/browserGlass"))
        self.assertEqual(self.leftovers(), [])

    def as_v10(self, rel):
        """Strip the companion prefs from the JSON file `rel` of the state
        folder (prefs_original anywhere in it), as v1.0 wrote it."""
        def strip(doc):
            if isinstance(doc, dict):
                for key, value in doc.items():
                    if key == "prefs_original" and isinstance(value, dict):
                        for pref in bg.COMPANION_PREFS:
                            value.pop(pref, None)
                    else:
                        strip(value)
        doc = json.loads(self.fh.read(STATE + "/" + rel))
        strip(doc)
        self.fh.write(STATE + "/" + rel, json.dumps(doc), mode=0o600)

    def test_v10_backup_then_state_lost(self):
        # A v1.0 backup (no companion prefs), then liveControl and a lost
        # state.json: uninstall still takes xpinstall.signatures.required
        # and the scope prefs back out.
        prefs = {"browser.startup.page": "3", AUTO: "11"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync(plugin_dir=None)
        self.as_v10(bg.STATE_FILE)
        self.as_v10("%s/%s/%s" % (bg.BACKUP_DIR, lw, bg.BACKUP_META))
        self.sync()
        self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
        meta = json.loads(self.fh.read("%s/%s/%s/%s" % (STATE, bg.BACKUP_DIR, lw, bg.BACKUP_META)))
        self.assertEqual(meta["prefs_original"][AUTO], {"value": "11"})
        self.assertEqual(meta["prefs_original"][SIG], {"absent": True})
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **self.userjs(LIBREWOLF))))
        os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
        self.uninstall()
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))

    def test_v10_pending_taken_back(self):
        # A v1.0 pending cleanup (no companion prefs) taken back by a sync:
        # the companion prefs derive from the user's own values.
        prefs = {"browser.startup.page": "3", AUTO: "0", SCAN: "4"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync(plugin_dir=None)
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        self.assertEqual(self.uninstall()["pending"], [lw])
        self.as_v10("pending/%s.json" % lw)
        self.sync()
        got = self.userjs(LIBREWOLF)
        self.assertEqual((got[SIG], got[AUTO], got[SCAN]), ("false", "0", "5"))
        holder.release()
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **got)))
        self.uninstall()
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))

    def test_residues_only(self):
        # No record and no trace of ours (state lost, files cleaned): only
        # the browser's records of the add-on, now or after it closes.
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        ours, other = self.storage(LIBREWOLF)
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(self.residues(prefs)))
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual((out["pending"], out["restored"]), ([lw], [lw]))
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(self.residues(prefs)))
        holder.release()
        expected = self.expected_prefs(prefs)
        self.assertTrue(wait_until(lambda: self.fh.read(LIBREWOLF + "/prefs.js") == expected),
                        self.fh.read(LIBREWOLF + "/prefs.js"))
        self.assertTrue(wait_until(lambda: not any(self.fh.exists(f) for f in ours)))
        self.assertTrue(self.fh.exists(other))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE))
        # Browser closed: at once, and reported.
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(self.residues(prefs)))
        out = self.uninstall()
        self.assertEqual((out["pending"], out["restored"]), ([], [lw]))
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), expected)
        self.assertEqual((self.uninstall()["restored"]), [], "nothing left")

    def browser_saved(self, rel, prefs):
        """prefs.js as the browser writes it: `prefs` plus the managed
        block's values it loaded from user.js."""
        self.fh.write(rel + "/prefs.js", prefs_text(dict(prefs, **self.userjs(rel))))

    def test_state_folder_lost(self):
        # No state.json, no pending file, no backup: the values the
        # stripped block set (companion prefs, content-override 2) still
        # leave prefs.js; a value of the user's own stays.
        prefs = {"browser.startup.page": "3"}
        self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        block = self.userjs(LIBREWOLF)
        self.assertEqual(block[bg.PREF_COLOR_SCHEME], str(bg.COLOR_SCHEME_BROWSER))
        self.assertTrue(set(bg.COMPANION_PREFS) <= set(block), block)
        self.browser_saved(LIBREWOLF, dict(prefs, **{"user.own": "1"}))
        text = self.fh.read(LIBREWOLF + "/prefs.js").replace(
            'user_pref("%s", %s);' % (AUTO, block[AUTO]), 'user_pref("%s", 3);' % AUTO)
        self.fh.write(LIBREWOLF + "/prefs.js", text)
        shutil.rmtree(str(self.fh.resolve(STATE)))
        out = self.uninstall()
        self.assertEqual(out["pending"], [])
        self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"),
                         prefs_text(dict(prefs, **{"user.own": "1", AUTO: "3"})))
        self.assertFalse(self.fh.exists(LIBREWOLF + "/user.js"))
        self.assertFalse(self.fh.exists(STATE))
        self.assertEqual(self.leftovers(), [])

    def test_state_folder_lost_browser_running(self):
        # The same, deferred: the plan goes into the pending file, and a
        # block pref the browser writes only at exit goes too.
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        block = self.userjs(LIBREWOLF)
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(
            dict(prefs, **{p: v for p, v in block.items() if p != SCAN})))
        shutil.rmtree(str(self.fh.resolve(STATE)))
        holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
        self.addCleanup(holder.stop)
        out = self.uninstall()
        self.assertEqual(out["pending"], [lw])
        pend = json.loads(self.fh.read("%s/%s/%s.json" % (STATE, bg.PENDING_DIR, lw)))
        self.assertEqual(sorted(p for p, v in pend["plan"]), sorted(block))
        self.assertTrue(all(v is None for p, v in pend["plan"]), pend["plan"])
        self.assertEqual(pend["prefs_original"][SIG], {"absent": True})
        self.browser_saved(LIBREWOLF, prefs)  # the browser exits
        holder.release()
        expected = prefs_text(prefs)
        self.assertTrue(wait_until(lambda: self.fh.read(LIBREWOLF + "/prefs.js") == expected),
                        self.fh.read(LIBREWOLF + "/prefs.js"))
        holder.stop()
        self.assertTrue(wait_until(lambda: not fake_home_pids(self.fh)), "cleanup did not exit")
        self.assertFalse(self.fh.exists(STATE))
        self.assertEqual(self.leftovers(), [])

    def test_state_json_corrupt_or_deleted(self):
        # Without state.json the folders made for the add-on and the
        # manifest go too, once empty: extensions/, native-messaging-hosts/
        # and ~/.mozilla/.
        for kind in ("corrupt", "deleted"):
            with self.subTest(kind):
                self.profile(LIBREWOLF)
                self.sync()
                self.assertTrue(self.fh.exists(LIBREWOLF + "/extensions"))
                self.assertTrue(self.fh.exists(MANIFEST))
                if kind == "corrupt":
                    self.fh.write(STATE + "/" + bg.STATE_FILE, '{"version": 1, "prof', mode=0o600)
                else:
                    os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
                out = self.uninstall()
                self.assertTrue(out["xpi_removed"])
                self.assertTrue(out["native_host_removed"])
                self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
                self.assertFalse(self.fh.exists(".mozilla"))
                self.assertFalse(self.fh.exists(STATE))
                self.assertEqual(self.leftovers(), [])

    def test_kept_backup_then_sync_then_state_lost(self):
        # An edited userChrome.css keeps the backup without its originals;
        # the next sync refills them, so a later state.json loss still
        # takes the block values out of prefs.js.
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        css = LIBREWOLF + "/chrome/userChrome.css"
        meta = "%s/%s/%s/%s" % (STATE, bg.BACKUP_DIR, lw, bg.BACKUP_META)
        self.fh.write(css, "/* mine */\n#nav-bar{color:red}\n")
        self.sync()
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **self.userjs(LIBREWOLF))))
        self.fh.write(css, self.fh.read(css) + "/* edited */\n")
        self.uninstall()
        self.assertTrue(self.fh.exists(meta))
        self.assertIsNone(json.loads(self.fh.read(meta))["prefs_original"])
        self.sync()
        block = self.userjs(LIBREWOLF)
        for pref in (SIG, AUTO, SCAN, bg.PREF_COLOR_SCHEME):
            self.assertIn(pref, block)
        self.assertEqual(json.loads(self.fh.read(meta))["prefs_original"][SIG], {"absent": True})
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **block)))
        self.fh.write(STATE + "/" + bg.STATE_FILE, "{", mode=0o600)
        self.uninstall()
        got = bg.parse_prefs(self.fh.read(LIBREWOLF + "/prefs.js"))
        for pref in (SIG, AUTO, SCAN, bg.PREF_COLOR_SCHEME):
            self.assertNotIn(pref, got)
        self.assertEqual(got, prefs)

    def test_kept_backup_then_state_lost(self):
        # Same without the refill (a meta.json whose originals are null):
        # the block read from user.js still marks the prefs as ours.
        prefs = {"browser.startup.page": "3"}
        lw = self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        block = self.userjs(LIBREWOLF)
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **block)))
        meta = "%s/%s/%s/%s" % (STATE, bg.BACKUP_DIR, lw, bg.BACKUP_META)
        doc = json.loads(self.fh.read(meta))
        doc["prefs_original"] = None
        self.fh.write(meta, json.dumps(doc), mode=0o600)
        self.fh.write(STATE + "/" + bg.STATE_FILE, "{", mode=0o600)
        self.uninstall()
        self.assertEqual(bg.parse_prefs(self.fh.read(LIBREWOLF + "/prefs.js")), prefs)

    def test_state_json_lost_keeps_foreign_folders(self):
        # Folders that hold something else stay.
        self.profile(LIBREWOLF)
        self.sync()
        self.fh.write(LIBREWOLF + "/extensions/other@example.org.xpi", b"x")
        self.fh.write(".mozilla/firefox/installs.ini", "")
        os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
        self.uninstall()
        self.assertTrue(self.fh.exists(LIBREWOLF + "/extensions/other@example.org.xpi"))
        self.assertTrue(self.fh.exists(".mozilla/firefox/installs.ini"))
        self.assertEqual(self.leftovers(), [])

    def lose_state(self, kind):
        if kind == "corrupt":
            self.fh.write(STATE + "/" + bg.STATE_FILE, '{"version": 1, "prof', mode=0o600)
        elif kind == "deleted":
            os.unlink(str(self.fh.resolve(STATE + "/" + bg.STATE_FILE)))
        else:
            shutil.rmtree(str(self.fh.resolve(STATE)))

    def assert_all_gone(self):
        self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
        self.assertFalse(self.fh.exists(".mozilla"))
        self.assertFalse(self.fh.exists(STATE))
        self.assertEqual(self.leftovers(), [])

    def test_state_lost_then_sync(self):
        # The daemon syncs again before the uninstall: the new records
        # still know which folders were made for the add-on and the
        # manifest (backup meta.json, native-dirs.json; without the state
        # folder, folders holding nothing but ours).
        for kind in ("corrupt", "deleted", "folder"):
            with self.subTest(kind):
                lw = self.profile(LIBREWOLF)
                self.sync()
                self.lose_state(kind)
                self.sync()
                self.assertTrue(self.fh.exists(LIBREWOLF + XPI_REL))
                out = self.uninstall()
                self.assertEqual(out["xpi_removed"], [lw])
                self.assertTrue(out["native_host_removed"])
                self.assert_all_gone()

    def test_state_lost_then_sync_without_our_files(self):
        # The add-on and the manifest gone too before the sync: the
        # folders made for them are still known, and go.
        for kind in ("corrupt", "deleted"):
            with self.subTest(kind):
                self.profile(LIBREWOLF)
                self.sync()
                self.lose_state(kind)
                os.unlink(str(self.fh.resolve(LIBREWOLF + XPI_REL)))
                os.unlink(str(self.fh.resolve(MANIFEST)))
                self.sync(liveControl=False)
                self.assertFalse(self.fh.exists(LIBREWOLF + "/extensions"))
                self.assertFalse(self.fh.exists(".mozilla"))
                self.uninstall()
                self.assert_all_gone()

    def test_state_lost_then_sync_keeps_foreign_files(self):
        # Folders holding something of the user's stay, with it, whether
        # it was there before the first sync or came after the loss.
        for kind in ("corrupt", "deleted", "folder"):
            for before in (True, False):
                with self.subTest(kind=kind, before=before):
                    own_xpi = LIBREWOLF + "/extensions/other@example.org.xpi"
                    own_manifest = ".mozilla/native-messaging-hosts/other.json"
                    self.profile(LIBREWOLF)
                    if before:
                        self.fh.write(own_xpi, b"x")
                        self.fh.write(own_manifest, "{}")
                    self.sync()
                    self.lose_state(kind)
                    if not before:
                        self.fh.write(own_xpi, b"x")
                        self.fh.write(own_manifest, "{}")
                    self.sync()
                    out = self.uninstall()
                    self.assertTrue(out["xpi_removed"])
                    self.assertTrue(self.fh.exists(own_xpi))
                    self.assertTrue(self.fh.exists(own_manifest))
                    folder = self.fh.resolve(".mozilla/native-messaging-hosts")
                    self.assertEqual(self.leftovers(), [os.path.relpath(str(folder), str(self.fh.root))])
                    self.assertFalse(self.fh.exists(STATE))
                    shutil.rmtree(str(self.fh.resolve(".mozilla")))
                    shutil.rmtree(str(self.fh.resolve(LIBREWOLF + "/extensions")))

    def test_wrapper_kept_with_its_manifest(self):
        # A manifest that cannot go keeps the wrapper it names.
        self.profile(LIBREWOLF)
        self.sync()
        folder = self.fh.resolve(MANIFEST).parent
        os.chmod(str(folder), 0o500)
        self.addCleanup(lambda: folder.exists() and os.chmod(str(folder), 0o700))
        out = self.sync(liveControl=False)
        self.assertIn("write_failed", [w["code"] for w in out["warnings"]])
        self.assertTrue(self.fh.exists(MANIFEST))
        self.assertTrue(self.fh.exists(STATE + "/" + bg.HOST_WRAPPER))
        os.chmod(str(folder), 0o700)
        out = self.sync(liveControl=False)
        self.assertFalse(self.fh.exists(MANIFEST))
        self.assertFalse(self.fh.exists(STATE + "/" + bg.HOST_WRAPPER))

    def test_foreign_manifest_kept(self):
        self.profile(LIBREWOLF)
        self.fh.write(MANIFEST, json.dumps({"name": "someone-else", "allowed_extensions": []}))
        self.sync(liveControl=False)
        self.uninstall()
        self.assertTrue(self.fh.exists(MANIFEST), "not ours: kept")


class ResiduesUnitTest(unittest.TestCase):

    def test_only_our_key(self):
        uuids = {"a@x": OTHER_UUID, bg.COMPANION_ID: OUR_UUID, "b@y": "é"}
        text = prefs_text({bg.PREF_EXT_UUIDS: json.dumps(json.dumps(uuids, ensure_ascii=False),
                                                         ensure_ascii=False),
                           "x.y": "1"})
        out, uuid = bg.companion_residues(text)
        self.assertEqual(uuid, OUR_UUID)
        inner = json.loads(json.loads(bg.parse_prefs(out)[bg.PREF_EXT_UUIDS]))
        self.assertEqual(list(inner), ["a@x", "b@y"])
        self.assertEqual(inner["b@y"], "é")
        self.assertEqual(bg.parse_prefs(out)["x.y"], "1")

    def test_nothing_of_ours(self):
        text = prefs_text({bg.PREF_EXT_UUIDS: json.dumps('{"a@x":"%s"}' % OTHER_UUID)})
        self.assertEqual(bg.companion_residues(text), (text, None))
        self.assertEqual(bg.companion_residues(prefs_text({})), (prefs_text({}), None))

    def test_odd_values(self):
        for raw in ('"not json"', "42", json.dumps("[1]"), json.dumps('{"%s": 7}' % bg.COMPANION_ID)):
            with self.subTest(raw=raw):
                text = prefs_text({bg.PREF_EXT_UUIDS: raw})
                out, uuid = bg.companion_residues(text)
                self.assertIsNone(uuid)

    def test_companion_prefs(self):
        self.assertEqual(bg.companion_prefs({}), [(SIG, "false"), (AUTO, "14"), (SCAN, "1")])
        self.assertEqual(bg.companion_prefs({AUTO: "0", SCAN: "1"}),
                         [(SIG, "false"), (AUTO, "0"), (SCAN, "1")])
        self.assertEqual(bg.companion_prefs({AUTO: '"odd"', SCAN: "true"}),
                         [(SIG, "false"), (AUTO, "14"), (SCAN, "1")])

    def test_companion_guard(self):
        everything = (SIG, AUTO, SCAN)
        self.assertEqual(bg.companion_guard({}, everything),
                         [(SIG, "true"), (AUTO, "15"), (SCAN, "0")])
        originals = {SIG: {"value": "false"}, AUTO: {"value": "3"}, SCAN: {"absent": True}}
        self.assertEqual(bg.companion_guard(originals, everything),
                         [(SIG, "false"), (AUTO, "3"), (SCAN, "0")])
        odd = {SIG: {"value": '"no"'}, AUTO: {"value": "true"}, SCAN: {"value": "1);x("}}
        self.assertEqual(bg.companion_guard(odd, (SCAN, SIG)), [(SIG, "true"), (SCAN, "0")])

    def test_firefox_builds_from_the_env_argument(self):
        # The env given to main() wins over os.environ (a profile that
        # never ran: the installed build decides).
        fh = FakeHome()
        self.addCleanup(fh.cleanup)
        build = fh.root / "opt" / "release"
        build.joinpath("defaults", "pref").mkdir(parents=True)
        build.joinpath("defaults", "pref", "channel-prefs.js").write_text(
            'pref("app.update.channel", "release");\n', encoding="utf-8")
        nightly = fh.root / "opt" / "nightly"
        nightly.mkdir(parents=True)
        profile = fh.root / "profile"
        profile.mkdir()
        saved = os.environ.get(bg.ENV_FIREFOX_BUILDS)
        os.environ[bg.ENV_FIREFOX_BUILDS] = str(nightly)
        if saved is None:
            self.addCleanup(os.environ.pop, bg.ENV_FIREFOX_BUILDS, None)
        else:
            self.addCleanup(os.environ.__setitem__, bg.ENV_FIREFOX_BUILDS, saved)
        env = {bg.ENV_FIREFOX_BUILDS: str(build)}
        self.assertTrue(bg.installed_firefox_signed(env))
        self.assertFalse(bg.installed_firefox_signed())
        self.assertEqual(bg.companion_state(str(profile), "firefox", "firefox", None, True, True,
                                            {}, env), bg.COMPANION_ENFORCED)
        self.assertEqual(bg.companion_state(str(profile), "firefox", "firefox", None, True, True,
                                            {}), bg.COMPANION_PENDING)


if __name__ == "__main__":
    unittest.main()

"""The companion state "disabled": the add-on is in the profile and the
browser registered it, but its extensions.json entry is inactive, disabled
by the user (about:addons) or by the browser. The xpi stays, and a later
removal reads as the user's (removed_by_user), never as a signing refusal.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fakehome import load_script
from test_companion_sync import BETA, LIBREWOLF, SIG, XPI_REL, CompanionCase

bg = load_script()


def entry(**fields):
    return dict({"id": bg.COMPANION_ID, "location": "app-profile"}, **fields)


class EntryTest(unittest.TestCase):
    """companion_entry() and companion_state() on a bare profile folder."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bg-disabled-")
        self.addCleanup(shutil.rmtree, self.dir)
        os.mkdir(os.path.join(self.dir, bg.EXTENSIONS_DIR))
        with open(bg.companion_xpi_path(self.dir), "wb") as f:
            f.write(b"xpi")
        self.comp = {"dropped": 1.0, "build": None, "refused": None, "ext_dir": True,
                     "seen": False, "signed": False}

    def write(self, text):
        with open(os.path.join(self.dir, bg.EXTENSIONS_JSON), "w", encoding="utf-8") as f:
            f.write(text)

    def state(self):
        return bg.companion_state(self.dir, "librewolf", "native", self.comp, True, True,
                                  compat={"LastVersion": "1"}, env={})

    def test_disabled_entries(self):
        for fields in ({"active": False}, {"userDisabled": True}, {"appDisabled": True},
                       {"active": True, "userDisabled": True},
                       {"active": False, "userDisabled": False, "appDisabled": False}):
            with self.subTest(fields=fields):
                self.write(json.dumps({"addons": [entry(**fields)]}))
                self.assertTrue(bg.companion_registered(self.dir))
                self.assertEqual(self.state(), bg.COMPANION_DISABLED)

    def test_active_entries(self):
        for fields in ({}, {"active": True}, {"active": True, "userDisabled": False,
                                              "appDisabled": False},
                       {"active": "false"}, {"userDisabled": "true"}, {"appDisabled": 1}):
            with self.subTest(fields=fields):
                self.write(json.dumps({"addons": [{"id": "other@x", "active": False},
                                                  entry(**fields)]}))
                self.assertEqual(self.state(), bg.COMPANION_INSTALLED)

    def test_the_visible_entry_decides(self):
        self.write(json.dumps({"addons": [entry(visible=False, active=True),
                                          entry(visible=True, active=False)]}))
        self.assertEqual(self.state(), bg.COMPANION_DISABLED)
        self.write(json.dumps({"addons": [entry(visible=False, active=False),
                                          entry(active=True)]}))
        self.assertEqual(self.state(), bg.COMPANION_INSTALLED)

    def test_not_registered(self):
        # Malformed or foreign extensions.json: not registered, no crash.
        for text in ("", "{", "not json", "[]", "null", '"%s"' % bg.COMPANION_ID,
                     json.dumps({"addons": {"id": bg.COMPANION_ID}}),
                     json.dumps({"addons": [bg.COMPANION_ID, None, 3]}),
                     json.dumps({"addons": [{"id": "other@x"}]}),
                     json.dumps({"note": bg.COMPANION_ID}), "[" * 100000):
            with self.subTest(text=text[:40]):
                self.write(text)
                self.assertIsNone(bg.companion_entry(self.dir))
                self.assertFalse(bg.companion_registered(self.dir))
                self.assertEqual(self.state(), bg.COMPANION_PENDING)

    def test_unreadable(self):
        self.assertIsNone(bg.companion_entry(self.dir), "missing")
        os.mkdir(os.path.join(self.dir, bg.EXTENSIONS_JSON))
        self.assertIsNone(bg.companion_entry(self.dir), "a folder")
        self.assertEqual(self.state(), bg.COMPANION_PENDING)

    def test_oversized(self):
        self.write(json.dumps({"addons": [entry(active=False)], "pad": "x" * 200}))
        self.assertEqual(self.state(), bg.COMPANION_DISABLED)
        with mock.patch.object(bg, "_EXTENSIONS_JSON_LIMIT", 100):
            self.assertIsNone(bg.companion_entry(self.dir))
            self.assertEqual(self.state(), bg.COMPANION_PENDING)

    def test_no_xpi_is_not_disabled(self):
        self.write(json.dumps({"addons": [entry(active=False)]}))
        os.unlink(bg.companion_xpi_path(self.dir))
        self.assertNotEqual(self.state(), bg.COMPANION_DISABLED)


class DisabledSyncTest(CompanionCase):

    def register(self, rel, **fields):
        self.fh.write(rel + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": [entry(**fields)]}))

    def record(self, pid):
        state = json.loads(self.fh.read(".local/state/dms/browserGlass/" + bg.STATE_FILE))
        return state["profiles"][pid]["companion"]

    def test_disabled_then_removed_by_the_user(self):
        # A build that may require signing: without the "seen" mark a
        # removal would read as signing_required.
        ff = self.profile(BETA, channel="distro-custom")
        self.sync()
        xpi = self.fh.resolve(BETA + XPI_REL).read_bytes()
        self.register(BETA, active=False, userDisabled=True)
        out = self.sync()
        self.assertEqual(self.states(out), {ff: bg.COMPANION_DISABLED})
        self.assertTrue(self.fh.exists(BETA + XPI_REL), "the xpi stays")
        self.assertEqual(self.fh.resolve(BETA + XPI_REL).read_bytes(), xpi)
        self.assertEqual(self.userjs(BETA)[SIG], "false", "the prefs stay")
        self.assertIs(self.record(ff)["seen"], True)
        again = self.sync()
        self.assertEqual(self.states(again), {ff: bg.COMPANION_DISABLED})
        self.assertEqual(again["changed"], [], "an unchanged sync writes nothing")
        status, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_DISABLED)
        self.assertEqual(status["companion"]["state"], "disabled")
        self.assertTrue(status["companion"]["manifest"])
        # Enabled again in about:addons.
        self.register(BETA, active=True, userDisabled=False)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_INSTALLED})
        self.register(BETA, active=False, userDisabled=True)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_DISABLED})
        # Then removed in about:addons.
        dropped = os.stat(str(self.fh.resolve(BETA + XPI_REL))).st_mtime
        os.unlink(str(self.fh.resolve(BETA + XPI_REL)))
        self.fh.write(BETA + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        ext_json = str(self.fh.resolve(BETA + "/" + bg.EXTENSIONS_JSON))
        os.utime(ext_json, (dropped + 10, dropped + 10))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED})
        self.assertFalse(self.fh.exists(BETA + XPI_REL))

    def test_disabled_before_any_sync_marks_seen(self):
        # Registered disabled between the deposit and the next sync (the
        # sidebar prompt, or disabled at once): the next sync records it.
        lw = self.profile(LIBREWOLF)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_PENDING})
        self.assertIs(self.record(lw)["seen"], False)
        self.register(LIBREWOLF, appDisabled=True)
        _, per = self.status()
        self.assertEqual(per[lw], bg.COMPANION_DISABLED)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_DISABLED})
        self.assertIs(self.record(lw)["seen"], True)

    def test_summary_prefers_a_profile_that_runs_it(self):
        lw = self.profile(LIBREWOLF)
        ff = self.profile(BETA, channel="distro-custom")
        self.sync()
        self.register(LIBREWOLF, active=True)
        self.register(BETA, active=False)
        status, per = self.status()
        self.assertEqual(per, {lw: bg.COMPANION_INSTALLED, ff: bg.COMPANION_DISABLED})
        self.assertEqual(status["companion"]["state"], "waiting_restart")
        self.register(LIBREWOLF, userDisabled=True)
        status, _ = self.status()
        self.assertEqual(status["companion"]["state"], "disabled")

    def test_live_control_off_removes_a_disabled_addon(self):
        lw = self.profile(LIBREWOLF)
        self.sync()
        self.register(LIBREWOLF, active=False)
        self.assertEqual(self.states(self.sync()), {lw: bg.COMPANION_DISABLED})
        self.assertEqual(self.states(self.sync(liveControl=False)), {lw: bg.COMPANION_OFF})
        self.assertFalse(self.fh.exists(LIBREWOLF + XPI_REL))
        self.assertNotIn(SIG, self.userjs(LIBREWOLF))


if __name__ == "__main__":
    unittest.main()

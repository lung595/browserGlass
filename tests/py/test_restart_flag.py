"""Per-profile output (profile_output) and the restart flag of a change
applied live (restart_hash / excl_hash, live_push acknowledgements).

sync runs in-process (bg.main) with live_push replaced by a fake host that
acknowledges for chosen browser pids; status runs through the command line.
A running browser is a LockHolder child holding .parentlock: its pid is the
one a host of that browser acknowledges for.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import contextlib
import io
import json
import os
import time
import unittest
from unittest import mock

import test_contract
from fakehome import REPO, FakeHome, LockHolder, kill_strays, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS

FF_ROOT = ".mozilla/firefox"
LW_ROOT = ".librewolf"
FF = FF_ROOT + "/a1b2c3d4.default-release"
LW = LW_ROOT + "/e5f6g7h8.default-default"
STATE_DIR = ".local/state/dms/browserGlass"
STATE = STATE_DIR + "/state.json"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}
DATA = str(REPO / "data")


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


class RestartCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)
        fh = self.fh
        for rel in (FF, LW):
            root, folder = rel.rsplit("/", 1)
            fh.make_profile(root, folder, prefs={"browser.startup.page": 3})
            fh.write_profiles_ini(root, [{"name": folder.split(".", 1)[1], "path": folder,
                                          "default": True}])
        fh.write(".config/niri/config.kdl", 'input {\n}\n\ninclude "dms/windowrules.kdl"\n')
        fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.9\n}\n")
        fh.write_dms_colors(mode="dark", surface_dark="#223344")
        self.pushes = []

    def pid(self, rel):
        return bg.profile_id(str(self.fh.resolve(rel)))

    def browser(self, rel):
        holder = LockHolder(self.fh, rel + "/.parentlock")
        self.addCleanup(holder.stop)
        # An in-process sync is fast: wait until a file written now is
        # surely newer than the start process_start() gives (one clock tick
        # later than the real one, file times are coarse).
        _, key = bg.lock_instance(str(self.fh.resolve(rel)))
        start = bg.process_start(key)
        self.assertIsNotNone(start)
        time.sleep(max(0.0, start + 0.05 - time.time()))
        return holder

    def sync(self, *extra, acked=(), **over):
        """sync in-process; the fake host acknowledges for the pids `acked`."""
        def fake_push(env, domains):
            self.pushes.append(list(domains))
            return len(acked), frozenset(acked)

        argv = ["sync", "--settings", json.dumps(settings(**over))] + list(extra)
        out = io.StringIO()
        with mock.patch.object(bg, "live_push", fake_push), contextlib.redirect_stdout(out):
            code = bg.main(argv, env=self.fh.env(FAST))
        self.assertEqual(code, bg.EXIT_OK, out.getvalue())
        doc = json.loads(out.getvalue())
        self.assertEqual(test_contract.validate(doc, SCHEMA["sync"], DEFS), [], out.getvalue())
        return doc

    def status(self):
        proc = self.fh.run_script(["status", "--json"], extra_env=FAST)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["status"], DEFS), [], proc.stdout)
        return doc

    def profile_status(self, doc, rel):
        for browser in doc["browsers"]:
            for profile in browser["profiles"]:
                if profile["id"] == self.pid(rel):
                    return profile
        self.fail("profile not in status")

    def record(self, rel):
        return json.loads(self.fh.read(STATE))["profiles"][self.pid(rel)]

    def edit_later(self, rel, text):
        """Append `text` to the profile file `rel`, surely after the last
        write (file times are coarse)."""
        time.sleep(0.05)
        self.fh.write(rel, self.fh.read(rel) + text)


class SeamTest(RestartCase):

    def test_same_block_and_v1_hash_for_every_profile(self):
        out = self.sync()
        self.assertEqual(sorted(out["changed"]), sorted([self.pid(FF), self.pid(LW)]))
        self.assertEqual(self.fh.read(FF + "/user.js"), self.fh.read(LW + "/user.js"))
        # The v1.0 applied_hash, computed from the files sync wrote.
        chrome = self.fh.read(FF + "/chrome/dms-glass-chrome.css")
        content = self.fh.read(FF + "/chrome/dms-glass-content.css")
        block = bg.userjs_block(bg.settings_from_json(settings()), 0.9)
        legacy = bg._sha256("\0".join((chrome, content, block)))[:16]
        self.assertEqual(bg.applied_hash_of(chrome, content, block), legacy)
        for rel in (FF, LW):
            record = self.record(rel)
            self.assertEqual(record["applied_hash"], legacy)
            self.assertEqual(len(record["restart_hash"]), 16)
            self.assertEqual(record["live"], None)
        self.assertEqual(self.pushes, [[]])

    def test_per_profile_block(self):
        # The seam made to differ by family: each profile gets its own
        # block, owned prefs and applied hash.
        real = bg.userjs_prefs

        def by_family(settings_doc, opacity, off=False, profile=None, companion=None):
            prefs = real(settings_doc, opacity, off, profile, companion)
            if profile is not None and profile.family == "librewolf":
                prefs = [(p, "0" if p == bg.PREF_COLOR_SCHEME else v) for p, v in prefs]
            return prefs

        with mock.patch.object(bg, "userjs_prefs", by_family):
            self.sync()
        ff_js, lw_js = self.fh.read(FF + "/user.js"), self.fh.read(LW + "/user.js")
        self.assertIn('"%s", 2);' % bg.PREF_COLOR_SCHEME, ff_js)
        self.assertIn('"%s", 0);' % bg.PREF_COLOR_SCHEME, lw_js)
        ff, lw = self.record(FF), self.record(LW)
        self.assertNotEqual(ff["applied_hash"], lw["applied_hash"])
        self.assertNotEqual(ff["restart_hash"], lw["restart_hash"])
        self.assertEqual(ff["excl_hash"], lw["excl_hash"])
        state, _ = bg.state_load(str(self.fh.resolve(STATE_DIR)), [])
        ff_path, lw_path = str(self.fh.resolve(FF)), str(self.fh.resolve(LW))
        ff_rec, lw_rec = state["profiles"][self.pid(FF)], state["profiles"][self.pid(LW)]
        self.assertTrue(bg.profile_applied(ff_path, ff_rec))
        self.assertTrue(bg.profile_applied(lw_path, lw_rec))
        self.assertFalse(bg.profile_applied(ff_path, lw_rec))
        self.assertFalse(bg.profile_applied(lw_path, ff_rec))
        doc = self.status()
        self.assertTrue(self.profile_status(doc, FF)["applied"])
        self.assertTrue(self.profile_status(doc, LW)["applied"])
        # Back to the same block everywhere: only LibreWolf changes.
        out = self.sync()
        self.assertEqual(out["changed"], [self.pid(LW)])
        self.assertEqual(self.fh.read(LW + "/user.js"), ff_js)
        self.assertEqual(self.record(LW)["applied_hash"], ff["applied_hash"])

    def test_restart_content_has_no_exclusion(self):
        # restart_hash comes from the content rendered without exclusions.
        sites = bg.sites_load(DATA)
        opts = bg.settings_from_json(settings(excluded=["example.org", "sub.example.net"]))
        bare = bg.settings_from_json(settings())

        def content(doc):
            return bg._render_content(doc, 0.8, sites, False, None)

        chrome = bg.chrome_css(opts, 0.8, bg.DEFAULT_SURFACES)
        with_excl = bg.sync_base(opts, 0.8, False, chrome, content(opts), content(bare))
        without = bg.sync_base(bare, 0.8, False, chrome, content(bare))
        self.assertNotEqual(content(opts), content(bare))
        one = bg.profile_output(with_excl, None)
        two = bg.profile_output(without, None)
        self.assertNotEqual(one["hash"], two["hash"])
        self.assertEqual(one["restart_hash"], two["restart_hash"])
        self.assertNotEqual(one["excl_hash"], two["excl_hash"])
        self.assertEqual(two["restart_hash"], two["hash"])
        swapped = bg.settings_from_json(settings(excluded=["sub.example.net", "example.org"]))
        self.assertEqual(bg.sync_base(swapped, 0.8, False, chrome, "")["excl_hash"],
                         with_excl["excl_hash"])

    def test_bare_content_rendered_only_for_a_change(self):
        # The second site styles build (the bare stylesheet) runs only when
        # a profile's output changed; an unchanged one keeps restart_hash.
        real = bg._render_content
        calls = []

        def counting(*args, **kwargs):
            calls.append(args[0]["excluded"])
            return real(*args, **kwargs)

        with mock.patch.object(bg, "_render_content", counting):
            self.sync("--data", DATA, excluded=["old.reddit.com"])
            self.assertEqual(calls, [["old.reddit.com"], []])
            first = self.record(FF)
            calls.clear()
            out = self.sync("--data", DATA, excluded=["old.reddit.com"])
            self.assertEqual(out["changed"], [])
            self.assertEqual(calls, [["old.reddit.com"]])
            self.assertEqual(self.record(FF), first)
            calls.clear()
            self.sync("--data", DATA, excluded=["old.reddit.com", "example.org"])
            self.assertEqual(calls, [["old.reddit.com", "example.org"], []])
            self.assertEqual(self.record(FF)["restart_hash"], first["restart_hash"])
            calls.clear()
            self.sync("--data", DATA)
            self.assertEqual(calls, [[]])
            self.assertEqual(self.record(FF)["restart_hash"], first["restart_hash"])

    def test_restart_hash_ignores_every_exclusion(self):
        # Through sync with the shipped site styles: an excluded domain that
        # is also a style's deeper domain (written in the same lookahead
        # form) or anything the exclusion list adds to the content leaves
        # restart_hash alone. A renderer that adds exclusion-dependent
        # parts (behind a setting) must keep this true with it on.
        self.sync("--data", DATA)
        first = self.record(FF)
        for excluded in (["example.org"], ["old.reddit.com"], ["app.slack.com"],
                         ["old.reddit.com", "developer.mozilla.org", "dash.cloudflare.com"]):
            self.sync("--data", DATA, excluded=excluded)
            record = self.record(FF)
            self.assertNotEqual(record["applied_hash"], first["applied_hash"], excluded)
            self.assertNotEqual(record["excl_hash"], first["excl_hash"], excluded)
            self.assertEqual(record["restart_hash"], first["restart_hash"], excluded)
        self.sync("--data", DATA, excluded=["old.reddit.com"], disabledStyles=["reddit.com"])
        self.assertNotEqual(self.record(FF)["restart_hash"], first["restart_hash"])


class LiveTest(RestartCase):

    def test_exclusion_applied_live(self):
        self.sync()
        holder = self.browser(FF)
        out = self.sync(acked={holder.child.pid}, excluded=["example.org"])
        self.assertEqual(sorted(out["changed"]), sorted([self.pid(FF), self.pid(LW)]))
        self.assertEqual(out["running_changed"], [])
        self.assertEqual(self.pushes[-1], ["example.org"])
        self.assertIn("example\\\\.org", self.fh.read(FF + "/chrome/dms-glass-content.css"))
        doc = self.status()
        profile = self.profile_status(doc, FF)
        self.assertTrue(profile["running"] and profile["applied"])
        self.assertFalse(profile["restart_needed"])
        self.assertFalse(doc["restart_needed"])
        record = self.record(FF)
        self.assertEqual(record["live"]["instance"], record["instance"])
        # Without the live record the files would ask for a restart.
        self.assertTrue(bg.files_changed_since(str(self.fh.resolve(FF)),
                                               bg.process_start(record["instance"])))
        self.assertEqual(record["live"]["excl_hash"], record["excl_hash"])
        self.assertIsNone(self.record(LW)["live"])
        # A second change on top of the live one, acknowledged again.
        out = self.sync(acked={holder.child.pid}, excluded=["example.org", "example.net"])
        self.assertEqual(out["running_changed"], [])
        self.assertFalse(self.status()["restart_needed"])
        # The host is gone: the next exclusion change needs a restart.
        out = self.sync(excluded=["example.net"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        doc = self.status()
        self.assertTrue(doc["restart_needed"])
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])

    def test_deeper_domain_excluded_live(self):
        self.sync("--data", DATA)
        holder = self.browser(FF)
        out = self.sync("--data", DATA, acked={holder.child.pid}, excluded=["old.reddit.com"])
        self.assertEqual(out["running_changed"], [])
        self.assertFalse(self.status()["restart_needed"])

    def test_user_edit_after_a_live_change_needs_a_restart(self):
        for rel in ("/chrome/userChrome.css", "/user.js"):
            with self.subTest(rel=rel):
                self.sync()
                holder = self.browser(FF)
                self.sync(acked={holder.child.pid}, excluded=["example.org"])
                self.assertFalse(self.status()["restart_needed"])
                self.edit_later(FF + rel, "#nav-bar { color: red; }\n" if rel.endswith(".css")
                                else 'user_pref("example.user.pref", true);\n')
                doc = self.status()
                self.assertTrue(self.profile_status(doc, FF)["restart_needed"])
                self.assertTrue(doc["restart_needed"])
                # A later acknowledged exclusion change does not hide it.
                out = self.sync(acked={holder.child.pid}, excluded=["example.net"])
                self.assertEqual(out["running_changed"], [self.pid(FF)])
                self.assertTrue(self.status()["restart_needed"])
                self.assertIsNone(self.record(FF)["live"])
                holder.release()
                holder.stop()
                self.sync()

    def test_edit_during_the_push_needs_a_restart(self):
        # An edit between the writes and the ack (the push waits for acks)
        # is no part of what the browser applied live.
        self.sync()
        holder = self.browser(FF)
        pid = holder.child.pid

        def editing_push(env, domains):
            self.edit_later(FF + "/chrome/userChrome.css", "#nav-bar { color: red; }\n")
            return 1, frozenset({pid})

        out = io.StringIO()
        argv = ["sync", "--settings", json.dumps(settings(excluded=["example.org"]))]
        with mock.patch.object(bg, "live_push", editing_push), contextlib.redirect_stdout(out):
            self.assertEqual(bg.main(argv, env=self.fh.env(FAST)), bg.EXIT_OK)
        self.assertEqual(json.loads(out.getvalue())["running_changed"], [self.pid(FF)])
        self.assertIsNone(self.record(FF)["live"])
        doc = self.status()
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])
        self.assertTrue(doc["restart_needed"])

    def test_unacknowledged_push_drops_the_live_record(self):
        # S2 acked, S3 (another list) not: S3's list may have reached the
        # browser, so going back to S2's list without an ack (S4) is no
        # known state either.
        self.sync()
        holder = self.browser(FF)
        self.sync(acked={holder.child.pid}, excluded=["a.example.org"])
        out = self.sync(excluded=["b.example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        self.assertIsNone(self.record(FF)["live"])
        out = self.sync(excluded=["a.example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        doc = self.status()
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])

    def test_unacknowledged_same_list_keeps_the_live_record(self):
        self.sync()
        holder = self.browser(FF)
        self.sync(acked={holder.child.pid}, excluded=["example.org"])
        out = self.sync(excluded=["example.org"])
        self.assertEqual(out["changed"], [])
        self.assertIsNotNone(self.record(FF)["live"])
        self.assertFalse(self.status()["restart_needed"])

    def test_exclusion_without_ack_needs_a_restart(self):
        self.sync()
        self.browser(FF)
        out = self.sync(excluded=["example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        doc = self.status()
        self.assertTrue(doc["restart_needed"])
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])
        self.assertIsNone(self.record(FF)["live"])

    def test_ack_of_another_browser(self):
        self.sync()
        self.browser(FF)
        lw = self.browser(LW)
        out = self.sync(acked={lw.child.pid}, excluded=["example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        doc = self.status()
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])
        self.assertFalse(self.profile_status(doc, LW)["restart_needed"])

    def test_opacity_and_exclusion_need_a_restart(self):
        self.sync()
        holder = self.browser(FF)
        acked = {holder.child.pid}
        out = self.sync(acked=acked, excluded=["example.org"], opacityOverride=True, opacity=0.5)
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        doc = self.status()
        self.assertTrue(doc["restart_needed"])
        self.assertTrue(self.profile_status(doc, FF)["restart_needed"])
        # The opacity back to what the browser loaded, the exclusion kept
        # (it was applied live): nothing left to restart for.
        out = self.sync(acked=acked, excluded=["example.org"])
        self.assertIn(self.pid(FF), out["changed"])
        self.assertEqual(out["running_changed"], [])
        self.assertFalse(self.status()["restart_needed"])

    def test_change_before_the_start_is_unknown(self):
        # Files written while the browser runs, without an ack: what it
        # loaded is no longer what the record says, a later ack cannot fix it.
        self.sync()
        holder = self.browser(FF)
        self.sync(opacityOverride=True, opacity=0.5)
        out = self.sync(acked={holder.child.pid}, opacityOverride=True, opacity=0.5,
                        excluded=["example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        self.assertIsNone(self.record(FF)["live"])
        self.assertTrue(self.status()["restart_needed"])

    def test_restart_clears_the_live_record(self):
        self.sync()
        holder = self.browser(FF)
        self.sync(acked={holder.child.pid}, excluded=["example.org"])
        old = self.record(FF)["live"]["instance"]
        holder.release()
        holder.stop()
        again = self.browser(FF)
        doc = self.status()
        self.assertFalse(self.profile_status(doc, FF)["restart_needed"])
        self.sync(excluded=["example.org"])
        record = self.record(FF)
        self.assertNotEqual(record["instance"], old)
        self.assertIsNone(record["live"])
        # The new instance loaded the files: a change without ack needs a
        # restart, one with its own ack does not.
        out = self.sync(excluded=["example.net"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])
        self.assertTrue(self.status()["restart_needed"])
        again.release()
        again.stop()
        self.sync(excluded=["example.net"])
        self.assertIsNone(self.record(FF)["live"])
        third = self.browser(FF)
        out = self.sync(acked={third.child.pid}, excluded=["example.com"])
        self.assertEqual(out["running_changed"], [])
        self.assertFalse(self.status()["restart_needed"])
        third.release()
        third.stop()
        self.sync(excluded=["example.com"])
        self.assertIsNone(self.record(FF)["live"])

    def test_profile_sync_does_not_push(self):
        self.sync()
        holder = self.browser(FF)
        self.pushes.clear()
        out = self.sync("--profile", str(self.fh.resolve(FF)), acked={holder.child.pid},
                        excluded=["example.org"])
        self.assertEqual(self.pushes, [])
        self.assertEqual(out["running_changed"], [self.pid(FF)])

    def test_push_failure_is_no_ack(self):
        self.sync()
        holder = self.browser(FF)
        pid = holder.child.pid

        def raising(exc):
            def push(env, domains):
                raise exc
            return push

        pushes = [raising(OSError("no socket")), raising(TypeError("bad reply")),
                  raising(KeyError("ack")), lambda env, domains: None,
                  lambda env, domains: 1, lambda env, domains: (1, None),
                  lambda env, domains: (1, 2, 3)]
        for number, push in enumerate(pushes):
            with self.subTest(number=number):
                excluded = ["n%d.example.org" % number]
                out = io.StringIO()
                argv = ["sync", "--settings", json.dumps(settings(excluded=excluded))]
                with mock.patch.object(bg, "live_push", push), contextlib.redirect_stdout(out):
                    self.assertEqual(bg.main(argv, env=self.fh.env(FAST)), bg.EXIT_OK)
                doc = json.loads(out.getvalue())
                # The state is saved all the same.
                self.assertEqual(json.loads(self.fh.read(STATE))["last_sync"]["settings"]["excluded"],
                                 excluded)
                self.assertEqual(doc["running_changed"], [self.pid(FF)])
        self.assertEqual(bg._live_push_safe(self.fh.env(), []), (0, frozenset()))
        # An unusable count with usable acks: only the pids count.
        with mock.patch.object(bg, "live_push", lambda env, domains: ("1", [pid, True, "7"])):
            self.assertEqual(bg._live_push_safe(self.fh.env(), []), (1, frozenset({pid})))

    def test_unsaved_state_is_no_live_change(self):
        # status reads the live record back from state.json: when it cannot
        # be saved, sync must not promise that no restart is needed.
        self.sync()
        holder = self.browser(FF)
        with mock.patch.object(bg, "state_save", lambda sdir, state, warnings: False):
            out = self.sync(acked={holder.child.pid}, excluded=["example.org"])
        self.assertEqual(out["running_changed"], [self.pid(FF)])

    def test_no_host_by_default(self):
        self.assertEqual(bg.live_push(self.fh.env(), ["example.org"]), (0, frozenset()))


class StateTest(unittest.TestCase):

    def test_v1_record_without_fingerprints(self):
        record = bg._norm_record({"path": "/x/p", "applied_hash": "abc", "instance": "1:2"})
        self.assertEqual((record["restart_hash"], record["excl_hash"], record["live"]),
                         (None, None, None))
        self.assertFalse(bg.live_applied("/x/p", record, "1:2"))

    def test_live_normalised(self):
        good = {"instance": "12:34", "restart_hash": "r" * 16, "excl_hash": "e" * 16,
                "mtime": 1700000000.25}
        self.assertEqual(bg._norm_live(dict(good, junk=1)), good)
        self.assertEqual(bg._norm_live(dict(good, mtime=17))["mtime"], 17.0)
        no_mtime = dict(good)
        del no_mtime["mtime"]
        for bad in (None, [], "x", dict(good, instance=None), dict(good, excl_hash=3),
                    {"instance": "12:34"}, no_mtime, dict(good, mtime="1"),
                    dict(good, mtime=True), dict(good, mtime=float("nan")),
                    dict(good, mtime=10 ** 400), dict(good, mtime=float("inf"))):
            self.assertIsNone(bg._norm_live(bad), bad)

    def test_live_applied(self):
        with FakeHome() as fh:
            fh.write("p/user.js", "")
            path = str(fh.resolve("p"))
            mtime = bg.restart_files_mtime(path)
            self.assertGreater(mtime, 0.0)
            live = {"instance": "12:34", "restart_hash": "r", "excl_hash": "e", "mtime": mtime}
            record = {"applied_hash": "h", "restart_hash": "r", "excl_hash": "e", "live": live}
            self.assertTrue(bg.live_applied(path, record, "12:34"))
            self.assertFalse(bg.live_applied(path, record, "12:35"))
            self.assertFalse(bg.live_applied(path, record, None))
            self.assertFalse(bg.live_applied(path, dict(record, excl_hash="f"), "12:34"))
            self.assertFalse(bg.live_applied(path, dict(record, restart_hash="s"), "12:34"))
            self.assertFalse(bg.live_applied(path, dict(record, applied_hash=None), "12:34"))
            self.assertFalse(bg.live_applied(path, None, "12:34"))
            # A file written after the live record.
            os.utime(os.path.join(path, "user.js"), (mtime + 1, mtime + 1))
            self.assertFalse(bg.live_applied(path, record, "12:34"))

    def test_instance_browser_pid(self):
        self.assertEqual(bg.instance_browser_pid("1234:5678"), 1234)
        for key in ("?", None, "", "x:1", "12"):
            self.assertIsNone(bg.instance_browser_pid(key), key)

    def test_round_trip(self):
        with FakeHome() as fh:
            folder = str(fh.resolve(STATE_DIR))
            os.makedirs(folder)
            state = bg.new_state(synced=True)
            state["profiles"]["0123456789ab"] = bg._norm_record({
                "path": "/x/p", "applied_hash": "h", "restart_hash": "r", "excl_hash": "e",
                "instance": "1:2", "live": {"instance": "1:2", "restart_hash": "r",
                                            "excl_hash": "e", "mtime": 1700000000.5}})
            bg.state_save(folder, state, [])
            loaded, _ = bg.state_load(folder, [])
            self.assertEqual(bg.state_text(loaded), bg.state_text(state))
            self.assertTrue(bg.live_applied("/x/p", loaded["profiles"]["0123456789ab"], "1:2"))


if __name__ == "__main__":
    unittest.main()

"""The state section of browserglass.py, in-process: state.json load/save,
state.lock, backups, prefs.js helpers, niri include and stale temp files.

Every call gets an explicit environment built by FakeHome (never os.environ).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import stat
import time
import unittest

from fakehome import PREFS_HEADER, FakeHome, load_script

bg = load_script()

PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
V1_BLOCK = '%s\nuser_pref("%s", 0);\n%s\n' % (bg.V1_USERJS_BEGIN, PREF_SCHEME, bg.V1_USERJS_END)
V0_BLOCK = '%s\nuser_pref("%s", 1);\n%s\n' % (bg.V0_USERJS_BEGIN, PREF_SCHEME, bg.V0_USERJS_END)


class StateCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.env = self.fh.env({"BG_LOCK_TIMEOUT": "0.2"})
        self.sdir = bg.state_dir(self.env)


class PathsTest(StateCase):

    def test_folders_follow_the_environment(self):
        self.assertEqual(self.sdir, str(self.fh.state / "dms" / "browserGlass"))
        self.assertEqual(bg.v0_cache_dir(self.env), str(self.fh.cache / "dms" / "browserGlass"))
        self.assertEqual(bg.niri_dir(self.env), str(self.fh.config / "niri"))

    def test_env_seconds(self):
        self.assertEqual(bg.env_seconds({"X": "0.5"}, "X", 3.0), 0.5)
        for bad in ("", "nan", "-1", "inf", "x"):
            self.assertEqual(bg.env_seconds({"X": bad}, "X", 3.0), 3.0, bad)
        self.assertEqual(bg.env_seconds({}, "X", 3.0), 3.0)

    def test_make_dirs_tracked(self):
        target = str(self.fh.resolve("a/b/c"))
        created = bg.make_dirs_tracked(target)
        self.assertEqual(created, [str(self.fh.resolve(p)) for p in ("a", "a/b", "a/b/c")])
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o700)
        self.assertEqual(bg.make_dirs_tracked(target), [])


class StateFileTest(StateCase):

    def test_newer_state_is_refused(self):
        self.fh.write(self.fh.state / "dms/browserGlass/state.json", '{"version": 2}')
        with self.assertRaises(bg.StateNewer):
            bg.state_load(self.sdir, [])

    def test_missing_state(self):
        warnings = []
        state, existed = bg.state_load(self.sdir, warnings)
        self.assertEqual((state, existed, warnings), (bg.new_state(), False, []))

    def test_corrupt_state(self):
        for text in ("{nope", "[]", '{"version": 0}', '{"version": "2"}', "\x00"):
            self.fh.write(self.fh.state / "dms/browserGlass/state.json", text)
            warnings = []
            state, existed = bg.state_load(self.sdir, warnings)
            self.assertEqual(state, bg.new_state(synced=True), text)
            self.assertTrue(existed)
            self.assertEqual([w["code"] for w in warnings], ["state_corrupt"], text)

    def test_round_trip_and_normalisation(self):
        state = bg.new_state()
        pid = "0123456789ab"
        state["profiles"][pid] = bg._norm_record({
            "path": "/x/profile", "family": "firefox", "applied_hash": "abc",
            "prefs_original": {PREF_SCHEME: {"value": "2"}, PREF_TRANSPARENT: {"absent": True},
                               "other.pref": {"value": "1"}},
            "owned_prefs": [PREF_SCHEME, "junk"], "glass_loaded_since_start": True})
        state["profiles"]["NOT-A-PID"] = state["profiles"][pid]
        state["created_dirs"] = ["/x/a", "relative/b", 3]
        os.makedirs(self.sdir)
        warnings = []
        bg.state_save(self.sdir, state, warnings)
        self.assertEqual(warnings, [])
        path = os.path.join(self.sdir, "state.json")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        loaded, existed = bg.state_load(self.sdir, warnings)
        self.assertTrue(existed)
        self.assertEqual(sorted(loaded["profiles"]), [pid])
        record = loaded["profiles"][pid]
        self.assertEqual(record["prefs_original"],
                         {PREF_SCHEME: {"value": "2"}, PREF_TRANSPARENT: {"absent": True}})
        self.assertEqual(record["owned_prefs"], [PREF_SCHEME])
        self.assertTrue(record["glass_loaded_since_start"])
        self.assertEqual(loaded["created_dirs"], ["/x/a"])
        self.assertEqual(json.loads(bg.state_text(loaded))["version"], bg.STATE_VERSION)

    def test_save_is_deterministic(self):
        os.makedirs(self.sdir)
        state = bg.new_state()
        bg.state_save(self.sdir, state, [])
        path = os.path.join(self.sdir, "state.json")
        before = os.stat(path)
        time.sleep(0.01)
        bg.state_save(self.sdir, bg.state_load(self.sdir, [])[0], [])
        after = os.stat(path)
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))


class StateLockTest(StateCase):

    def test_lock_creates_the_folder(self):
        fd = bg.state_lock(self.sdir, self.env)
        try:
            self.assertTrue(os.path.isfile(os.path.join(self.sdir, "state.lock")))
            start = time.monotonic()
            with self.assertRaises(bg.StateBusy):
                bg.state_lock(self.sdir, self.env)
            self.assertLess(time.monotonic() - start, 2.0)
        finally:
            os.close(fd)
        os.close(bg.state_lock(self.sdir, self.env))

    def test_lock_file_replaced_while_waiting(self):
        fd = bg.state_lock(self.sdir, self.env)
        os.unlink(os.path.join(self.sdir, "state.lock"))
        try:
            fd2 = bg.state_lock(self.sdir, self.env)  # a new file: not the held one
            os.close(fd2)
        finally:
            os.close(fd)


class BackupTest(StateCase):

    def profile(self, files):
        root = self.fh.resolve("profiles/p1")
        for rel, (text, mode) in files.items():
            self.fh.write(root / rel, text, mode=mode)
        os.makedirs(str(root), exist_ok=True)
        texts = {}
        for name, rel in bg.PROFILE_FILES:
            path = root / rel
            texts[name] = path.read_text() if path.exists() else None
        return str(root), texts

    def test_backup_strips_v0_and_records_modes(self):
        path, texts = self.profile({
            "chrome/userChrome.css": ('@import "dms-glass-chrome.css";\n/* mine */\n', 0o640),
            "chrome/userContent.css": ('@import "dms-glass-content.css";\n', 0o644),
            "user.js": ('user_pref("a", 1);\n' + V0_BLOCK, 0o600),
        })
        record = bg.backup_take(self.sdir, "0123456789ab", path, texts)
        files = record["files"]
        self.assertEqual(files["userChrome.css"]["mode"], 0o640)
        self.assertTrue(files["userChrome.css"]["existed"])
        self.assertFalse(files["userContent.css"]["existed"], "v0 created it")
        self.assertTrue(files["user.js"]["existed"])
        self.assertTrue(record["chrome_dir"])
        folder = bg.backup_folder(self.sdir, "0123456789ab")
        with open(os.path.join(folder, "userChrome.css")) as f:
            self.assertEqual(f.read(), "/* mine */\n")
        with open(os.path.join(folder, "user.js")) as f:
            self.assertEqual(f.read(), 'user_pref("a", 1);\n')
        self.assertFalse(os.path.exists(os.path.join(folder, "userContent.css")))
        self.assertEqual(bg.backup_read(self.sdir, "0123456789ab", "user.js", record),
                         'user_pref("a", 1);\n')
        self.assertIsNone(bg.backup_read(self.sdir, "0123456789ab", "userContent.css", record))

    def test_backup_never_overwritten(self):
        path, texts = self.profile({"user.js": ('user_pref("a", 1);\n', 0o644)})
        first = bg.backup_take(self.sdir, "0123456789ab", path, texts)
        self.assertFalse(first["chrome_dir"])
        texts["user.js"] = 'user_pref("b", 2);\n'
        again = bg.backup_take(self.sdir, "0123456789ab", path, texts)
        self.assertEqual(again, first)
        self.assertEqual(bg.backup_read(self.sdir, "0123456789ab", "user.js", again),
                         'user_pref("a", 1);\n')
        meta = os.path.join(bg.backup_folder(self.sdir, "0123456789ab"), "meta.json")
        with open(meta, "w") as f:
            f.write("{broken")
        with self.assertRaises(OSError):
            bg.backup_take(self.sdir, "0123456789ab", path, texts)

    def test_incomplete_backup_is_taken_again(self):
        # A hard stop before meta.json: nothing was written to the profile
        # yet, so the half-made folder protects nothing and is redone.
        path, texts = self.profile({"user.js": ('user_pref("a", 1);\n', 0o644)})
        folder = bg.backup_folder(self.sdir, "0123456789ab")
        os.makedirs(folder)
        with open(os.path.join(folder, "user.js"), "w") as f:
            f.write("half")
        record = bg.backup_take(self.sdir, "0123456789ab", path, texts, {"x": {"absent": True}})
        self.assertEqual(bg.backup_read(self.sdir, "0123456789ab", "user.js", record),
                         'user_pref("a", 1);\n')
        self.assertEqual(record["prefs_original"], {"x": {"absent": True}})

    def test_empty_chrome_folder_is_the_users(self):
        path, texts = self.profile({"user.js": ('user_pref("a", 1);\n', 0o644)})
        os.mkdir(os.path.join(path, "chrome"))
        self.assertTrue(bg.backup_take(self.sdir, "0123456789ab", path, texts)["chrome_dir"])

    def test_tampered_backup_is_unusable(self):
        path, texts = self.profile({"user.js": ('user_pref("a", 1);\n', 0o644)})
        record = bg.backup_take(self.sdir, "0123456789ab", path, texts)
        with open(os.path.join(bg.backup_folder(self.sdir, "0123456789ab"), "user.js"), "w") as f:
            f.write("changed\n")
        self.assertIsNone(bg.backup_read(self.sdir, "0123456789ab", "user.js", record))


class PrefsTest(unittest.TestCase):

    def test_parse_and_block_prefs(self):
        text = PREFS_HEADER + 'user_pref("a.b", true);\nuser_pref("a.b", false);\n  user_pref( "c" , "x" ) ;\n'
        self.assertEqual(bg.parse_prefs(text), {"a.b": "false", "c": '"x"'})
        self.assertEqual(bg.block_prefs('user_pref("%s", 5);\n' % PREF_SCHEME + V1_BLOCK),
                         {PREF_SCHEME: "0"})

    def test_originals(self):
        prefs = 'user_pref("%s", 0);\nuser_pref("%s", false);\n' % (PREF_SCHEME, PREF_TRANSPARENT)
        self.assertEqual(bg.prefs_originals(prefs, V1_BLOCK), {
            PREF_SCHEME: {"absent": True},          # the value our block sets
            PREF_TRANSPARENT: {"value": "false"},
            PREF_STYLESHEETS: {"absent": True},
            bg.PREF_SIGNATURES: {"absent": True},
            bg.PREF_AUTODISABLE: {"absent": True},
            bg.PREF_STARTUP_SCAN: {"absent": True},
        })
        self.assertEqual(bg.prefs_originals(prefs, "")[PREF_SCHEME], {"value": "0"})

    def test_originals_under_a_v0_block(self):
        # v0 rewrote every managed pref on each sync, so with its block
        # in user.js any value v0 could write is ours, even one that differs
        # from the block (1 kept in prefs.js after a light -> dark switch).
        userjs = V0_BLOCK.replace('", 1);', '", 0);')
        prefs = ('user_pref("%s", 1);\nuser_pref("%s", true);\nuser_pref("%s", true);\n'
                 % (PREF_SCHEME, PREF_TRANSPARENT, PREF_STYLESHEETS))
        absent = {p: {"absent": True} for p in bg.PREFS}
        self.assertTrue(bg.has_v0_block(userjs))
        self.assertEqual(bg.prefs_originals(prefs, userjs), absent)
        self.assertEqual(bg.prefs_originals(prefs, userjs), bg.prefs_originals_v0(prefs))
        # A value v0 never writes stays the user's.
        self.assertEqual(bg.prefs_originals('user_pref("%s", 2);\n' % PREF_SCHEME, userjs)[PREF_SCHEME],
                         {"value": "2"})
        # A v1 block keeps the exact-match rule.
        self.assertFalse(bg.has_v0_block(V1_BLOCK))
        self.assertEqual(bg.prefs_originals(prefs, V1_BLOCK)[PREF_SCHEME], {"value": "1"})

    def test_restore_plan(self):
        text = 'user_pref("a", 1);\r\nuser_pref("%s", 0);\r\nuser_pref("%s", 0);\r\n' % (
            PREF_SCHEME, PREF_SCHEME)
        self.assertEqual(bg.prefs_restore(text, [(PREF_SCHEME, "2")]),
                         'user_pref("a", 1);\r\nuser_pref("%s", 2);\r\n' % PREF_SCHEME)
        self.assertEqual(bg.prefs_restore(text, [(PREF_SCHEME, None)]), 'user_pref("a", 1);\r\n')
        self.assertEqual(bg.prefs_restore('user_pref("a", 1);', [(PREF_TRANSPARENT, "true")]),
                         'user_pref("a", 1);\nuser_pref("%s", true);\n' % PREF_TRANSPARENT)

    def test_v0_plan_and_record_plan(self):
        text = 'user_pref("%s", 2);\nuser_pref("%s", true);\n' % (PREF_SCHEME, PREF_STYLESHEETS)
        self.assertEqual(bg.prefs_plan_v0(text), [(PREF_STYLESHEETS, None)])
        record = {"prefs_original": {PREF_SCHEME: {"value": "2"}, PREF_STYLESHEETS: {"absent": True}}}
        self.assertEqual(bg.prefs_plan_record(record, {PREF_SCHEME, PREF_STYLESHEETS, PREF_TRANSPARENT}),
                         [(PREF_STYLESHEETS, None), (PREF_TRANSPARENT, None), (PREF_SCHEME, "2")])

    def test_apply_never_creates(self):
        with FakeHome() as fh:
            profile = fh.resolve("p")
            profile.mkdir()
            self.assertFalse(bg.prefs_apply(str(profile), [(PREF_SCHEME, "2")]))
            self.assertFalse((profile / "prefs.js").exists())
            fh.write("p/prefs.js", 'user_pref("%s", 0);\n' % PREF_SCHEME, mode=0o600)
            self.assertTrue(bg.prefs_apply(str(profile), [(PREF_SCHEME, None)]))
            self.assertEqual(fh.read("p/prefs.js"), "")
            self.assertEqual(stat.S_IMODE(os.stat(str(profile / "prefs.js")).st_mode), 0o600)


class ProfileFilesTest(unittest.TestCase):

    def test_strip_and_apply(self):
        css = '@charset "UTF-8";\n#x {}\n'
        added = bg.apply_ours("userChrome.css", css, None)
        self.assertEqual(bg.strip_ours("userChrome.css", added), css)
        js = 'user_pref("a", 1);\n' + V0_BLOCK
        self.assertEqual(bg.strip_ours("user.js", js), 'user_pref("a", 1);\n')
        self.assertIn(bg.V1_USERJS_BEGIN, bg.apply_ours("user.js", js, V1_BLOCK))
        self.assertNotIn(bg.V0_USERJS_BEGIN, bg.apply_ours("user.js", js, V1_BLOCK))

    def test_css_has_glass(self):
        self.assertFalse(bg.css_has_glass(None))
        self.assertTrue(bg.css_has_glass(bg.V0_CSS_HEADER_GLASS.format(opacity="0.8") + "\n"))
        self.assertTrue(bg.css_has_glass("/* browserGlass */\n/* glass active, opacity 0.8 */\n"))
        self.assertFalse(bg.css_has_glass("/* neutral file */\n"))


class NiriIncludeTest(unittest.TestCase):

    def test_round_trips(self):
        for text in ("", "input {\n}\n", "input {\n}", "a\r\nb\r\n"):
            new, eol = bg.niri_add_include(text)
            self.assertEqual(new.count(bg.V1_NIRI_INCLUDE), 1, repr(text))
            self.assertEqual(bg.niri_add_include(new), (new, True))
            self.assertEqual(bg.niri_strip_include(new, eol), text, repr(text))

    def test_strip_untouched_without_include(self):
        self.assertEqual(bg.niri_strip_include("a\n\n", False), "a\n\n")

    def test_commented_include_is_the_users_choice(self):
        inc = bg.V1_NIRI_INCLUDE
        for text in ("a\n// " + inc + "\n", "a\n//" + inc + "\n", "a\n/-" + inc + "\n",
                     "a\n/*\n" + inc + "\n*/\n", "a\n/* x /* y */\n" + inc + "\n*/\n"):
            self.assertEqual(bg.niri_add_include(text), (text, True), repr(text))
            self.assertEqual(bg.niri_strip_include(text), text, repr(text))

    def test_comment_markers_inside_strings_or_line_comments(self):
        inc = bg.V1_NIRI_INCLUDE
        for head in ('a "/*"\n', "// /* not a block\n"):
            new, eol = bg.niri_add_include(head)
            self.assertIn("\n" + inc + "\n", new, repr(head))
            self.assertEqual(bg.niri_strip_include(new, eol), head)

    def test_user_lines_after_the_include_keep_their_newline(self):
        new, eol = bg.niri_add_include("a {\n}")
        self.assertFalse(eol)
        self.assertEqual(bg.niri_strip_include(new + "b {\n}\n", eol), "a {\n}\nb {\n}\n")


class StaleTmpTest(unittest.TestCase):

    def test_sweep(self):
        with FakeHome() as fh:
            old = fh.write("p/.browserglass-user.js.abcd_ef1.tmp", "x")
            fresh = fh.write("p/.browserglass-prefs.js.abcd_ef2.tmp", "x")
            foreign = fh.write("p/.browserglass-notes.txt.abcd_ef3.tmp", "x")
            # Hand-made files with the usual temporary-file look are the user's.
            lookalikes = [fh.write("p/" + name, "mine") for name in (
                ".user.js.abcdef_1.tmp", ".config.kdl.20260101.tmp", ".user.js.original.tmp",
                ".browserglass-user.js.ABCDEFGH.tmp")]
            for path in [old, foreign] + lookalikes:
                os.utime(str(path), (1, 1))
            bg.sweep_stale_tmp([str(fh.resolve("p")), str(fh.resolve("missing"))])
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())
            self.assertTrue(foreign.exists())
            for path in lookalikes:
                self.assertTrue(path.exists(), path.name)

    def test_write_uses_our_prefix(self):
        with FakeHome() as fh:
            target = fh.write("p/user.js", "a")
            seen = []
            real = bg.tempfile.mkstemp

            def spy(*args, **kwargs):
                fd, name = real(*args, **kwargs)
                seen.append(os.path.basename(name))
                return fd, name

            bg.tempfile.mkstemp = spy
            try:
                bg.write_if_changed(str(target), "b")
            finally:
                bg.tempfile.mkstemp = real
            self.assertEqual(len(seen), 1)
            self.assertTrue(bg._STALE_TMP.fullmatch(seen[0]), seen[0])


class BadPathTest(unittest.TestCase):
    """state.json paths holding a NUL or relative are dropped, and the
    quiet removers never raise on them."""

    def test_quiet_removers(self):
        bg._rmdir_quiet("/x/\x00y")
        self.assertFalse(bg._remove_file("/x/\x00y"))

    def test_normalisers(self):
        self.assertEqual(bg._abs_paths(["/a", "/b\x00", "rel", 3]), ["/a"])
        self.assertIsNone(bg._norm_record({"path": "/p\x00"}))
        self.assertIsNone(bg._norm_record({"path": "rel/p"}))
        self.assertEqual(bg._norm_record({"path": "/p"})["path"], "/p")
        backup = {"files": {}, "path": "/p\x00"}
        self.assertIsNone(bg._norm_backup(backup)["path"])
        self.assertEqual(bg._norm_backup(dict(backup, path="/p"))["path"], "/p")
        pend = {"version": bg.STATE_VERSION, "path": "/p\x00", "created_dirs": ["/d", "/e\x00"]}
        self.assertIsNone(bg._norm_pending(pend))
        self.assertEqual(bg._norm_pending(dict(pend, path="/p"))["created_dirs"], ["/d"])

    def test_stale_tmp_dirs_files(self):
        for name in ("state-dirs.json", "native-dirs.json"):
            self.assertTrue(bg._STALE_TMP.fullmatch(".browserglass-%s.abcd_ef1.tmp" % name))


class CompanionOutdatedTest(unittest.TestCase):

    def test_foreign_runtime_dir_not_read(self):
        with FakeHome() as fh:
            real = fh.resolve("run/real")
            os.makedirs(str(real))
            pid = os.getpid()
            with open(bg.runtime_file(str(real), "active", pid), "w") as f:
                json.dump({"outdated": True}, f)
            self.assertTrue(bg.companion_outdated(str(real), pid))
            link = fh.resolve("run/link")
            os.symlink(str(real), str(link))
            self.assertFalse(bg.companion_outdated(str(link), pid))


if __name__ == "__main__":
    unittest.main()

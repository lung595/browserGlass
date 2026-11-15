"""The signed companion add-on: <plugin>/companion/browserglass@companion.xpi
is deposited instead of the zipped sources when it holds exactly them,
signed. Firefox release, ESR and Beta then get the add-on, no profile gets
xpinstall.signatures.required any more, and a v1.1/v1.2 install gives that
pref back to prefs.js. Every browser is a folder in a FakeHome; the signed
xpi is a test one (fake META-INF files, no real signature).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import unittest
import warnings
import zipfile
from unittest import mock

import test_contract
from fakehome import REPO, FakeHome, LockHolder, load_script
from test_companion_sync import (AUTO, BETA, FAST, FIREFOX, LIBREWOLF, MANIFEST, SCAN, SIG,
                                 XPI_REL, CompanionCase, prefs_text, settings_json)

bg = load_script()
EXT = REPO / bg.EXTENSION_DIR
ESR = ".mozilla/firefox/ff0005.default-esr"
SIGNATURES = ("META-INF/cose.manifest", "META-INF/cose.sig", "META-INF/manifest.mf",
              "META-INF/mozilla.sf", "META-INF/mozilla.rsa")
PLUGIN = object()  # sync(): the test's plugin folder


def signed_xpi(plain, extra=None, drop=None, change=None, signature=SIGNATURES,
               method=zipfile.ZIP_DEFLATED):
    """A test "signed" xpi: the entries of `plain` re-zipped (deflated, the
    way AMO repacks), plus the fake META-INF files `signature`."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(plain)) as src, zipfile.ZipFile(buf, "w", method) as zf:
        for name in signature:
            zf.writestr(name, b"fake signature " + name.encode("ascii"))
        for name in src.namelist():
            if name == drop:
                continue
            data = src.read(name)
            if name == change:
                data += b"\n// changed\n"
            zf.writestr(name, data)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def with_id(ext_dir, gecko_id):
    """Give the manifest.json of `ext_dir` the gecko id `gecko_id`."""
    path = os.path.join(ext_dir, "manifest.json")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    doc["browser_specific_settings"]["gecko"]["id"] = gecko_id
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)


class ProblemTest(unittest.TestCase):
    """companion_signed_problem(): the signed xpi against the sources."""

    @classmethod
    def setUpClass(cls):
        cls.plain = bg.companion_xpi(str(EXT))

    def problem(self, data):
        return bg.companion_signed_problem(data, self.plain)

    def test_valid(self):
        self.assertIsNone(self.problem(signed_xpi(self.plain)))
        for kept in (("META-INF/cose.sig", "META-INF/cose.manifest"),
                     ("META-INF/mozilla.rsa", "META-INF/mozilla.sf", "META-INF/manifest.mf")):
            with self.subTest(kept=kept):
                self.assertIsNone(self.problem(signed_xpi(self.plain, signature=kept)))
        self.assertIsNone(self.problem(signed_xpi(self.plain, method=zipfile.ZIP_STORED)))
        # Pure directory entries do not count.
        dirs = signed_xpi(self.plain, extra={"vendor/": b"", "META-INF/": b""})
        self.assertIsNone(self.problem(dirs))

    def test_not_the_sources(self):
        names = zipfile.ZipFile(io.BytesIO(self.plain)).namelist()
        self.assertIn("manifest.json", names)
        cases = {
            "a file differs": signed_xpi(self.plain, change="content.js"),
            "manifest differs": signed_xpi(self.plain, change="manifest.json"),
            "extra entry": signed_xpi(self.plain, extra={"extra.js": b"x"}),
            "directory with content": signed_xpi(self.plain, extra={"icons/": b"x"}),
            "missing entry": signed_xpi(self.plain, drop="background.js"),
            "missing manifest": signed_xpi(self.plain, drop="manifest.json"),
        }
        for label, data in cases.items():
            with self.subTest(label):
                self.assertIsNotNone(self.problem(data))

    def test_no_signature(self):
        for kept in ((), ("META-INF/manifest.mf",), ("META-INF/cose.manifest", "META-INF/mozilla.sf")):
            with self.subTest(kept=kept):
                self.assertEqual(self.problem(signed_xpi(self.plain, signature=kept)),
                                 "no Mozilla signature in META-INF/")

    def test_wrong_id(self):
        tmp = FakeHome()
        self.addCleanup(tmp.cleanup)
        ext = str(tmp.root / "ext")
        shutil.copytree(str(EXT), ext)
        with_id(ext, "other@example.org")
        plain = bg.companion_xpi(ext)
        self.assertEqual(bg.companion_signed_problem(signed_xpi(plain), plain),
                         "manifest.json does not name %s" % bg.COMPANION_ID)

    def test_corrupt(self):
        good = signed_xpi(self.plain, method=zipfile.ZIP_STORED)
        manifest = (EXT / "manifest.json").read_bytes()
        at = good.index(manifest)
        flipped = good[:at] + bytes([manifest[0] ^ 1]) + good[at + 1:]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # zipfile: "Duplicate name"
            duplicate = signed_xpi(self.plain, extra={"content.js": b"x"})
        cases = {
            "not a zip": b"not a zip at all",
            "empty": b"",
            "truncated": good[:len(good) // 2],
            "bad crc": flipped,
            "duplicate": duplicate,
        }
        for label, data in cases.items():
            with self.subTest(label):
                self.assertIsInstance(self.problem(data), str)

    def test_too_large(self):
        data = signed_xpi(self.plain) + b"\0" * (bg._SIGNED_XPI_MAX_BYTES)
        self.assertEqual(self.problem(data), "larger than %d bytes" % bg._SIGNED_XPI_MAX_BYTES)

    def test_sources_key(self):
        tmp = FakeHome()
        self.addCleanup(tmp.cleanup)
        ext = str(tmp.root / "ext")
        shutil.copytree(str(EXT), ext)
        key = bg.companion_sources_key(ext)
        self.assertEqual(key, bg.companion_sources_key(ext))
        path = os.path.join(ext, "content.js")
        st = os.stat(path)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
        self.assertNotEqual(bg.companion_sources_key(ext), key)


class SignedCase(CompanionCase):

    def setUp(self):
        super().setUp()
        self.plugin = self.fh.root / "plugin"
        self.ext = self.plugin / bg.EXTENSION_DIR
        shutil.copytree(str(EXT), str(self.ext))
        self.plain = bg.companion_xpi(str(self.ext))
        self.signed = signed_xpi(self.plain)
        self.pushes = []

    def put_signed(self, data=None):
        folder = self.plugin / bg.COMPANION_DIR
        folder.mkdir(exist_ok=True)
        path = folder / bg.COMPANION_XPI
        if path.is_symlink() or path.is_file():
            path.unlink()
        path.write_bytes(self.signed if data is None else data)
        return path

    def sync(self, plugin_dir=PLUGIN, **over):
        return super().sync(self.plugin if plugin_dir is PLUGIN else plugin_dir, **over)

    def sync_here(self, **over):
        """sync in-process (to count calls), live_push left out."""
        argv = ["sync", "--settings", settings_json(**over), "--plugin-dir", str(self.plugin)]
        out = io.StringIO()
        with mock.patch.object(bg, "live_push", lambda env, domains, darken=False: (0, frozenset())), \
                contextlib.redirect_stdout(out):
            code = bg.main(argv, env=self.fh.env(FAST))
        self.assertEqual(code, bg.EXIT_OK, out.getvalue())
        doc = json.loads(out.getvalue())
        self.assertEqual(test_contract.validate(doc, test_contract.SCHEMA["sync"],
                                                test_contract.DEFS), [], out.getvalue())
        return doc

    def firefox_profiles(self):
        """Firefox release, ESR and Beta profiles in one profiles.ini."""
        ids = {}
        for rel, channel in ((FIREFOX, "release"), (ESR, "esr"), (BETA, "beta")):
            ids[rel] = self.profile(rel, channel=channel)
        self.fh.write_profiles_ini(".mozilla/firefox", [
            {"name": os.path.basename(rel), "path": os.path.basename(rel), "default": rel == FIREFOX}
            for rel in ids])
        return ids

    def unusable(self, doc):
        return [w for w in doc["warnings"] if w["code"] == bg.WARN_SIGNED_XPI]

    def register(self, rel):
        self.fh.write(rel + "/" + bg.EXTENSIONS_JSON, json.dumps(
            {"addons": [{"id": bg.COMPANION_ID, "active": True, "userDisabled": False,
                         "appDisabled": False}]}))

    def state(self):
        return json.loads(self.fh.read(".local/state/dms/browserGlass/state.json"))


class ChoiceTest(SignedCase):

    def test_signed_xpi_deposited_everywhere(self):
        ids = self.firefox_profiles()
        lw = self.profile(LIBREWOLF)
        self.put_signed()
        out = self.sync()
        self.assertEqual(self.unusable(out), [])
        self.assertEqual(self.states(out), dict({i: bg.COMPANION_PENDING for i in ids.values()},
                                                **{lw: bg.COMPANION_PENDING}))
        for rel in list(ids) + [LIBREWOLF]:
            with self.subTest(rel=rel):
                self.assertEqual(self.fh.resolve(rel + XPI_REL).read_bytes(), self.signed,
                                 "the signed file's bytes, exactly")
                prefs = self.userjs(rel)
                self.assertNotIn(SIG, prefs)
                self.assertEqual((prefs[AUTO], prefs[SCAN]), ("14", "1"))
                record = self.state()["profiles"][bg.profile_id(str(self.fh.resolve(rel)))]
                self.assertTrue(record["companion"]["signed"])
                self.assertNotIn(SIG, record["owned_prefs"])
        self.assertTrue(self.fh.exists(MANIFEST))
        _, per = self.status()
        self.assertEqual(per[ids[FIREFOX]], bg.COMPANION_PENDING)
        # The browser loaded it at its start.
        self.register(FIREFOX)
        _, per = self.status()
        self.assertEqual(per[ids[FIREFOX]], bg.COMPANION_INSTALLED)
        self.assertEqual(self.states(self.sync())[ids[FIREFOX]], bg.COMPANION_INSTALLED)
        snap = self.fh.snapshot(".")
        self.sync()
        self.assertEqual(self.fh.snapshot("."), snap, "a second sync writes nothing")
        # Uninstall takes everything back.
        out = self.uninstall()
        self.assertEqual(sorted(out["xpi_removed"]), sorted(list(ids.values()) + [lw]))
        self.assertEqual([f for f in self.leftovers() if not f.startswith("plugin/")], [])

    def test_never_run_profile_with_an_installed_release(self):
        rel = FIREFOX.replace("ff0001", "ff0002")
        self.fh.write(rel + "/prefs.js", prefs_text({}))
        self.fh.write_profiles_ini(".mozilla/firefox", [{"name": "b", "path": os.path.basename(rel),
                                                         "default": True}])
        build = self.fh.root / "usr" / "lib64" / "firefox" / "defaults" / "pref"
        build.mkdir(parents=True)
        build.joinpath("channel-prefs.js").write_text('pref("app.update.channel", "release");\n',
                                                      encoding="utf-8")
        ff = bg.profile_id(str(self.fh.resolve(rel)))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_ENFORCED})
        self.put_signed()
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING})
        self.assertEqual(self.fh.resolve(rel + XPI_REL).read_bytes(), self.signed)

    def bad_files(self):
        """(label, prepare) of signed xpis that must not be used."""
        def content(data):
            return lambda: self.put_signed(data)

        def symlink():
            target = self.fh.root / "elsewhere.xpi"
            target.write_bytes(self.signed)
            path = self.put_signed()
            path.unlink()
            path.symlink_to(target)

        def folder():
            path = self.put_signed()
            path.unlink()
            path.mkdir()

        def large():
            self.put_signed(self.signed + b"\0" * bg._SIGNED_XPI_MAX_BYTES)

        def wrong_id():
            with_id(str(self.ext), "other@example.org")
            self.put_signed(signed_xpi(bg.companion_xpi(str(self.ext))))

        cases = [
            ("mismatching entry", content(signed_xpi(self.plain, change="content.js"))),
            ("extra entry", content(signed_xpi(self.plain, extra={"x.js": b"1"}))),
            ("missing entry", content(signed_xpi(self.plain, drop="content.js"))),
            ("no signature", content(signed_xpi(self.plain, signature=("META-INF/manifest.mf",)))),
            ("corrupt", content(b"PK\x03\x04 not really a zip")),
            ("symlink", symlink),
            ("not a file", folder),
            ("too large", large),
        ]
        if os.geteuid() != 0:
            def unreadable():
                self.put_signed().chmod(0)
            cases.append(("unreadable", unreadable))
        cases.append(("wrong id", wrong_id))  # last: it changes the sources
        return cases

    def test_unusable_signed_xpi_falls_back(self):
        ff = self.profile(FIREFOX, channel="release")
        lw = self.profile(LIBREWOLF)
        for label, prepare in self.bad_files():
            with self.subTest(label):
                folder = self.plugin / bg.COMPANION_DIR
                if folder.exists():
                    for child in folder.iterdir():
                        if child.is_dir() and not child.is_symlink():
                            child.rmdir()
                        else:
                            child.unlink()
                prepare()
                out = self.sync()
                found = self.unusable(out)
                self.assertEqual(len(found), 1, out["warnings"])
                self.assertTrue(found[0]["message"].startswith(
                    "companion/%s not used, " % bg.COMPANION_XPI), found[0]["message"])
                self.assertIsNone(found[0]["profile"])
                self.assertNotIn(str(self.fh.root), json.dumps(out), "no path in the warnings")
                self.assertEqual(self.states(out), {ff: bg.COMPANION_ENFORCED,
                                                    lw: bg.COMPANION_PENDING})
                self.assertFalse(self.fh.exists(FIREFOX + "/extensions"))
                self.assertEqual(self.fh.resolve(LIBREWOLF + XPI_REL).read_bytes(),
                                 bg.companion_xpi(str(self.ext)), "the unsigned add-on")
                self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
                self.assertFalse(self.state()["profiles"][lw]["companion"]["signed"])
                _, per = self.status()
                self.assertEqual(per[ff], bg.COMPANION_ENFORCED)
                snap = self.fh.snapshot(".")
                again = self.sync()
                self.assertEqual(len(self.unusable(again)), 1, "warned at every sync")
                self.assertEqual(self.fh.snapshot("."), snap, "and nothing written")
        (self.plugin / bg.COMPANION_DIR / bg.COMPANION_XPI).unlink()

    def test_switches_between_signed_and_unsigned(self):
        ff = self.profile(FIREFOX, channel="release")
        lw = self.profile(LIBREWOLF)
        self.put_signed()
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING,
                                                    lw: bg.COMPANION_PENDING})
        # The signed file goes (an older checkout): back to v1.2.
        (self.plugin / bg.COMPANION_DIR / bg.COMPANION_XPI).unlink()
        out = self.sync()
        self.assertEqual(self.unusable(out), [])
        self.assertEqual(self.states(out), {ff: bg.COMPANION_ENFORCED, lw: bg.COMPANION_PENDING})
        self.assertFalse(self.fh.exists(FIREFOX + "/extensions"))
        self.assertFalse(set(self.userjs(FIREFOX)) & set(bg.COMPANION_PREFS))
        self.assertEqual(self.fh.resolve(LIBREWOLF + XPI_REL).read_bytes(), self.plain)
        self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
        self.assertIsNone(self.state()["signed_xpi"])
        self.put_signed()
        self.sync()
        self.assertEqual(self.fh.resolve(LIBREWOLF + XPI_REL).read_bytes(), self.signed)
        self.assertNotIn(SIG, self.userjs(LIBREWOLF))

    def test_without_plugin_dir_the_signed_deposit_stays(self):
        ff = self.profile(FIREFOX, channel="release")
        self.put_signed()
        self.sync()
        snap = self.fh.snapshot(".")
        out = self.sync(plugin_dir=None)
        self.assertEqual(self.fh.snapshot("."), snap, "R15: left as it is")
        self.assertNotIn("companion", out)
        _, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_PENDING)

    def test_check_cached(self):
        self.profile(LIBREWOLF)
        path = self.put_signed()
        real_xpi, real_entries = bg.companion_xpi, bg._zip_entries

        def counted():
            return (mock.patch.object(bg, "companion_xpi", side_effect=real_xpi),
                    mock.patch.object(bg, "_zip_entries", side_effect=real_entries))

        def run():
            xpi, entries = counted()
            with xpi as built, entries as opened:
                doc = self.sync_here()
            return doc, built.call_count, opened.call_count

        doc, built, opened = run()
        self.assertEqual((built, opened), (1, 2), "first sync: checked")
        self.assertEqual(self.unusable(doc), [])
        cached = self.state()["signed_xpi"]
        st = os.stat(str(path))
        self.assertEqual((cached["mtime_ns"], cached["size"], cached["sha256"], cached["problem"]),
                         (st.st_mtime_ns, st.st_size, hashlib.sha256(self.signed).hexdigest(), None))
        snap = self.fh.snapshot(".")
        doc, built, opened = run()
        self.assertEqual((built, opened), (0, 0), "nothing changed: no zip work")
        self.assertEqual(self.fh.snapshot("."), snap, "and nothing written")
        # The signed file touched: checked again (same verdict, same deposit).
        os.utime(str(path), ns=(st.st_atime_ns, st.st_mtime_ns + 1000))
        doc, built, opened = run()
        self.assertEqual((built, opened), (1, 2))
        # A source touched: checked again.
        src = self.ext / "background.js"
        sst = os.stat(str(src))
        os.utime(str(src), ns=(sst.st_atime_ns, sst.st_mtime_ns + 1000))
        doc, built, opened = run()
        self.assertEqual((built, opened), (1, 2))
        self.assertEqual(self.fh.resolve(LIBREWOLF + XPI_REL).read_bytes(), self.signed)
        # A bad file: its verdict is cached too, the unsigned add-on built.
        self.put_signed(signed_xpi(self.plain, change="content.js"))
        doc, built, opened = run()
        self.assertEqual((built, opened, len(self.unusable(doc))), (1, 2, 1))
        snap = self.fh.snapshot(".")
        doc, built, opened = run()
        self.assertEqual((built, opened, len(self.unusable(doc))), (1, 0, 1))
        self.assertEqual(self.fh.snapshot("."), snap)

    def test_same_size_same_mtime_swap_checked_again(self):
        # A signed file replaced by another of the same size, given back
        # the same mtime: its bytes differ (sha256), so it is checked again
        # and the bad one is not deposited.
        self.profile(LIBREWOLF)
        path = self.put_signed()
        self.sync_here()
        st = os.stat(str(path))
        bad = bytearray(self.signed)
        bad[len(bad) // 2] ^= 0xff
        path.write_bytes(bytes(bad))
        os.utime(str(path), ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertEqual((os.stat(str(path)).st_size, os.stat(str(path)).st_mtime_ns),
                         (st.st_size, st.st_mtime_ns))
        with mock.patch.object(bg, "companion_signed_problem",
                               wraps=bg.companion_signed_problem) as check:
            doc = self.sync_here()
        self.assertEqual(check.call_count, 1)
        self.assertEqual(self.state()["signed_xpi"]["sha256"], hashlib.sha256(bytes(bad)).hexdigest())
        self.assertNotEqual(self.fh.resolve(LIBREWOLF + XPI_REL).read_bytes(), bytes(bad))
        self.assertEqual(len(self.unusable(doc)), 1)

    def test_state_record_normalized(self):
        for value in ({"mtime_ns": "1", "size": 2, "sha256": "h", "sources": "x", "problem": None},
                      {"mtime_ns": 1, "size": True, "sha256": "h", "sources": "x", "problem": None},
                      {"mtime_ns": 1, "size": 2, "sha256": "h", "sources": None, "problem": None},
                      {"mtime_ns": 1, "size": 2, "sources": "x", "problem": None},
                      {"mtime_ns": 1, "size": 2, "sha256": 3, "sources": "x", "problem": None},
                      {"mtime_ns": 1, "size": 2, "sha256": "h", "sources": "x", "problem": 3},
                      [], "x"):
            with self.subTest(value=value):
                self.assertIsNone(bg._norm_signed_xpi(value))
        good = {"mtime_ns": 1, "size": 2, "sha256": "h", "sources": "x", "problem": "bad", "extra": 1}
        self.assertEqual(bg._norm_signed_xpi(good),
                         {"mtime_ns": 1, "size": 2, "sha256": "h", "sources": "x", "problem": "bad"})


class SignedStatesTest(SignedCase):

    def test_deleted_by_the_browser_all_the_same(self):
        # The safety net: a browser that deletes even the signed xpi.
        ff = self.profile(FIREFOX, channel="release")
        self.put_signed()
        self.sync()
        dropped = os.stat(str(self.fh.resolve(FIREFOX + XPI_REL))).st_mtime
        os.unlink(str(self.fh.resolve(FIREFOX + XPI_REL)))
        compat = str(self.fh.resolve(FIREFOX + "/compatibility.ini"))
        os.utime(compat, (dropped + 10, dropped + 10))
        out = self.sync()
        self.assertEqual(self.states(out), {ff: bg.COMPANION_REFUSED})
        self.assertFalse(self.fh.exists(FIREFOX + XPI_REL), "no new deposit")
        self.assertFalse(set(self.userjs(FIREFOX)) & set(bg.COMPANION_PREFS))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REFUSED}, "still refused")
        _, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_REFUSED)
        self.update_browser(FIREFOX)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING})
        self.assertEqual(self.fh.resolve(FIREFOX + XPI_REL).read_bytes(), self.signed)

    def test_unsigned_refusal_does_not_stop_the_signed_xpi(self):
        ff = self.profile(BETA, channel="distro-custom")
        self.sync()
        dropped = os.stat(str(self.fh.resolve(BETA + XPI_REL))).st_mtime
        os.unlink(str(self.fh.resolve(BETA + XPI_REL)))
        compat = str(self.fh.resolve(BETA + "/compatibility.ini"))
        os.utime(compat, (dropped + 10, dropped + 10))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REFUSED})
        self.put_signed()
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING})
        self.assertEqual(self.fh.resolve(BETA + XPI_REL).read_bytes(), self.signed)
        self.assertNotIn(SIG, self.userjs(BETA))

    def removed_on_release(self):
        ff = self.profile(FIREFOX, channel="release")
        self.put_signed()
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING})
        self.register(FIREFOX)
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_INSTALLED})
        os.unlink(str(self.fh.resolve(FIREFOX + XPI_REL)))
        self.fh.write(FIREFOX + "/" + bg.EXTENSIONS_JSON, json.dumps({"addons": []}))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED})
        return ff

    def assert_removed(self, ff, why):
        doc, per = self.status()
        self.assertEqual(per[ff], bg.COMPANION_REMOVED, why)
        self.assertEqual(doc["companion"]["state"], "removed", why)

    def test_removed_on_release_reads_as_removed(self):
        # Not signing_enforced: the record keeps the kind of xpi removed.
        ff = self.removed_on_release()
        self.assert_removed(ff, "status")
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED}, "stable")
        self.assert_removed(ff, "status after another sync")

    def test_removal_holds_through_an_unsigned_sync(self):
        for name, middle in (("no --plugin-dir", lambda: self.sync(plugin_dir=None)),
                             ("unusable signed xpi", lambda: (
                                 self.put_signed(signed_xpi(self.plain, change="content.js")),
                                 self.sync()))):
            with self.subTest(middle=name):
                fh = FakeHome()
                self.addCleanup(fh.cleanup)
                self.fh = fh
                self.fh.write(".config/niri/config.kdl", "input {\n}\n", mode=0o644)
                self.fh.write_dms_colors()
                self.plugin = fh.root / "plugin"
                self.ext = self.plugin / bg.EXTENSION_DIR
                shutil.copytree(str(EXT), str(self.ext))
                ff = self.removed_on_release()
                middle()
                self.assertTrue(self.state()["profiles"][ff]["companion"]["seen"], name)
                self.put_signed()
                self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED}, name)
                self.assertFalse(self.fh.exists(FIREFOX + XPI_REL), "not deposited again")
                self.assert_removed(ff, name)

    def test_removal_on_release_survives_a_lost_state(self):
        ff = self.removed_on_release()
        os.unlink(str(self.fh.resolve(".local/state/dms/browserGlass/" + bg.STATE_FILE)))
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_REMOVED})
        self.assertFalse(self.fh.exists(FIREFOX + XPI_REL))
        self.assert_removed(ff, "status after a lost state.json")
        # Live control off and on again places it.
        self.assertEqual(self.states(self.sync(liveControl=False)), {ff: bg.COMPANION_OFF})
        self.assertEqual(self.states(self.sync()), {ff: bg.COMPANION_PENDING})
        self.assertEqual(self.fh.resolve(FIREFOX + XPI_REL).read_bytes(), self.signed)


class MigrationTest(SignedCase):
    """A v1.1/v1.2 install (xpinstall.signatures.required false in the
    block, and in prefs.js where the browser copied it) meets the signed
    xpi: the pref leaves the block and its original goes back to prefs.js."""

    ORIGINALS = (None, "true", "false")

    def as_v12(self, original):
        prefs = {"browser.startup.page": "3"}
        if original is not None:
            prefs[SIG] = original
        self.profile(LIBREWOLF, prefs=prefs)
        self.sync()  # no signed file: v1.2
        self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
        # The browser ran: user.js copied into prefs.js.
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(prefs, **self.userjs(LIBREWOLF))))
        self.put_signed()
        return prefs

    def prefsjs(self):
        return bg.parse_prefs(self.fh.read(LIBREWOLF + "/prefs.js"))

    def record(self):
        return self.state()["profiles"][bg.profile_id(str(self.fh.resolve(LIBREWOLF)))]

    def each(self, check):
        for original in self.ORIGINALS:
            with self.subTest(original=original):
                fh = FakeHome()
                self.addCleanup(fh.cleanup)
                keep_fh, keep_plugin = self.fh, self.plugin
                self.fh = fh
                self.fh.write(".config/niri/config.kdl", "input {\n}\n", mode=0o644)
                self.fh.write_dms_colors()
                self.plugin = fh.root / "plugin"
                self.ext = self.plugin / bg.EXTENSION_DIR
                shutil.copytree(str(EXT), str(self.ext))
                try:
                    check(original)
                finally:
                    self.fh, self.plugin = keep_fh, keep_plugin
                    self.ext = self.plugin / bg.EXTENSION_DIR

    def test_browser_closed(self):
        def check(original):
            prefs = self.as_v12(original)
            out = self.sync()
            self.assertEqual(out["warnings"], [])
            self.assertNotIn(SIG, self.userjs(LIBREWOLF))
            self.assertEqual(self.prefsjs().get(SIG), original, "the original is back")
            self.assertEqual(self.record()["restore_prefs"], [])
            self.assertNotIn(SIG, self.record()["owned_prefs"])
            snap = self.fh.snapshot(".")
            self.sync()
            self.assertEqual(self.fh.snapshot("."), snap, "a second sync writes nothing")
            # The browser copies the block again; uninstall gives prefs.js back.
            self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(self.prefsjs(),
                                                                   **self.userjs(LIBREWOLF))))
            self.uninstall()
            self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.each(check)

    def test_browser_running(self):
        def check(original):
            prefs = self.as_v12(original)
            holder = LockHolder(self.fh, LIBREWOLF + "/.parentlock")
            self.addCleanup(holder.stop)
            self.sync()
            got = self.userjs(LIBREWOLF)
            self.assertEqual(got[SIG], original or "true", "the guard holds the original")
            self.assertEqual((got[AUTO], got[SCAN]), ("14", "1"))
            self.assertEqual(self.prefsjs()[SIG], "false", "prefs.js waits for the browser")
            self.assertEqual(self.record()["restore_prefs"], [SIG])
            self.assertNotIn(SIG, self.record()["owned_prefs"])
            snap = self.fh.snapshot(".")
            self.sync()
            self.assertEqual(self.fh.snapshot("."), snap)
            holder.release()
            holder.stop()
            self.sync()
            self.assertNotIn(SIG, self.userjs(LIBREWOLF), "the guard goes")
            self.assertEqual(self.prefsjs().get(SIG), original)
            self.assertEqual(self.record()["restore_prefs"], [])
            self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(self.prefsjs(),
                                                                   **self.userjs(LIBREWOLF))))
            self.uninstall()
            self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.each(check)

    def test_restore_fails_with_the_browser_closed(self):
        # f1: prefs.js cannot be restored, the browser is closed: the guard
        # still keeps our value out of the next start.
        def check(original):
            self.as_v12(original)

            def failing(*args, **kwargs):
                raise OSError(13, "Permission denied")

            with mock.patch.object(bg, "prefs_apply", failing):
                out = self.sync_here()
            self.assertIn("write_failed", [w["code"] for w in out["warnings"]])
            self.assertEqual(self.userjs(LIBREWOLF)[SIG], original or "true")
            self.assertEqual(self.prefsjs()[SIG], "false")
            self.assertEqual(self.record()["restore_prefs"], [SIG])
            out = self.sync_here()
            self.assertEqual(out["warnings"], [])
            self.assertNotIn(SIG, self.userjs(LIBREWOLF))
            self.assertEqual(self.prefsjs().get(SIG), original)
        self.each(check)

    @unittest.skipIf(os.geteuid() == 0, "root writes read-only files")
    def test_read_only_userjs(self):
        # prefs.js gets the original back but the block on disk still
        # holds false: the restore is done again once user.js is written.
        def check(original):
            prefs = self.as_v12(original)
            userjs = self.fh.resolve(LIBREWOLF + "/user.js")
            userjs.chmod(0o444)
            self.addCleanup(lambda: userjs.exists() and userjs.chmod(0o644))
            out = self.sync()
            self.assertEqual([w["code"] for w in out["warnings"]], ["read_only"])
            self.assertEqual(self.userjs(LIBREWOLF)[SIG], "false")
            self.assertEqual(self.record()["restore_prefs"], [SIG])
            snap = self.fh.snapshot(".")
            self.sync()
            self.assertEqual(self.fh.snapshot("."), snap, "a second sync writes nothing")
            # The browser ran: the old block went into prefs.js again.
            self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(self.prefsjs(),
                                                                   **self.userjs(LIBREWOLF))))
            userjs.chmod(0o644)
            out = self.sync()
            self.assertEqual(out["warnings"], [])
            self.assertNotIn(SIG, self.userjs(LIBREWOLF))
            self.assertEqual(self.prefsjs().get(SIG), original, "the original is back")
            self.assertEqual(self.record()["restore_prefs"], [])
            self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(self.prefsjs(),
                                                                   **self.userjs(LIBREWOLF))))
            self.uninstall()
            self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.each(check)

    @unittest.skipIf(os.geteuid() == 0, "root writes read-only files")
    def test_read_only_userjs_then_uninstall(self):
        # Uninstalled while user.js is still read-only and the browser
        # copied its block: prefs.js still gets the original back.
        def check(original):
            prefs = self.as_v12(original)
            userjs = self.fh.resolve(LIBREWOLF + "/user.js")
            userjs.chmod(0o444)
            self.addCleanup(lambda: userjs.exists() and userjs.chmod(0o644))
            self.sync()
            self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(dict(self.prefsjs(),
                                                                   **self.userjs(LIBREWOLF))))
            userjs.chmod(0o644)
            self.uninstall()
            self.assertEqual(self.fh.read(LIBREWOLF + "/prefs.js"), prefs_text(prefs))
        self.each(check)


class GuardOnFailureTest(CompanionCase):

    @unittest.skipIf(os.geteuid() == 0, "root writes read-only files")
    def test_live_control_off_with_a_read_only_prefs_js(self):
        # f1 without the signed xpi: liveControl off, browser closed,
        # prefs.js read-only: the block holds the originals meanwhile.
        prefs = {"browser.startup.page": "3", AUTO: "11"}
        self.profile(LIBREWOLF, prefs=prefs)
        self.sync()
        managed = dict(prefs, **self.userjs(LIBREWOLF))
        self.fh.write(LIBREWOLF + "/prefs.js", prefs_text(managed))
        path = self.fh.resolve(LIBREWOLF + "/prefs.js")
        path.chmod(0o444)
        self.addCleanup(path.chmod, 0o644)
        out = self.sync(liveControl=False)
        self.assertIn("read_only", [w["code"] for w in out["warnings"]])
        got = self.userjs(LIBREWOLF)
        self.assertEqual((got.get(SIG), got.get(AUTO), got.get(SCAN)), ("true", "11", "0"))
        path.chmod(0o644)
        out = self.sync(liveControl=False)
        self.assertEqual(out["warnings"], [])
        restored = bg.parse_prefs(self.fh.read(LIBREWOLF + "/prefs.js"))
        self.assertEqual((restored.get(SIG), restored.get(AUTO), restored.get(SCAN)),
                         (None, "11", None))
        self.assertFalse(set(self.userjs(LIBREWOLF)) & set(bg.COMPANION_PREFS))


if __name__ == "__main__":
    unittest.main()

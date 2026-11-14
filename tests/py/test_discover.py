"""discover: profiles.ini parsing, Profile Groups scan and the profile roots
(native, Flatpak, Snap, XDG_CONFIG_HOME), all inside a FakeHome.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import hashlib
import os
import re
import unittest

from fakehome import FakeHome, fixture_text, load_script

bg = load_script()

FF = ".mozilla/firefox"


class DiscoverCase(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.env = self.fh.env()

    def ini(self, root_rel, fixture, **subst):
        return self.fh.write(os.path.join(root_rel, "profiles.ini"), fixture_text(fixture, **subst))

    def profiles(self, env=None):
        return bg.find_profiles(self.env if env is None else env)

    def by_name(self, env=None):
        return {p.name: p for p in self.profiles(env)}


class ParseProfilesIniTest(DiscoverCase):

    def test_install_default_overrides_default_flag(self):
        root = self.fh.resolve(FF)
        self.ini(FF, "profiles/install-default.ini")
        got = bg.parse_profiles_ini(str(root))
        self.assertEqual([(p.name, p.default) for p in got],
                         [("default-release", True), ("default", False)])
        self.assertEqual(got[0].path, str(root / "fake0001.default-release"))

    def test_default_flag_without_install(self):
        self.ini(FF, "profiles/default-flag-only.ini")
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        self.assertEqual([(p.name, p.default) for p in got],
                         [("default-release", False), ("default", True)])

    def test_install_naming_an_unlisted_profile_falls_back_to_default_flag(self):
        self.ini(FF, "profiles/install-unknown.ini")
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        self.assertEqual([p.name for p in got if p.default], ["default"])

    def test_two_installs_share_a_root(self):
        self.ini(FF, "profiles/two-installs.ini")
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        self.assertEqual(sorted(p.name for p in got if p.default), ["default-esr", "default-release"])

    def test_relative_and_absolute_paths(self):
        root = self.fh.resolve(FF)
        elsewhere = self.fh.resolve("profiles/fake0002.elsewhere")
        other = self.fh.resolve("other/fake0005.implicit-absolute")
        self.ini(FF, "profiles/absolute.ini", ELSEWHERE=elsewhere, OTHER=other)
        got = {p.name: p for p in bg.parse_profiles_ini(str(root))}
        self.assertEqual(got["elsewhere"].path, str(elsewhere))
        self.assertTrue(got["elsewhere"].default)          # Install Default= (absolute) wins
        self.assertFalse(got["nested"].default)            # over Default=1
        self.assertEqual(got["nested"].path, str(root / "Profiles" / "fake0003.nested"))
        self.assertEqual(got["no-isrelative-absolute"].path, str(other))
        self.assertEqual(got["no-isrelative-relative"].path, str(root / "fake0004.implicit"))

    def test_generator_absolute_entries(self):
        # FakeHome's own generator, non-relative: absolute Path= and Default=.
        self.fh.make_profile(FF, "fake0001.a")
        self.fh.make_profile(FF, "fake0002.b")
        self.fh.write_profiles_ini(FF, [{"name": "a", "path": "fake0001.a"},
                                        {"name": "b", "path": "fake0002.b", "default": True}],
                                   installs={"0123456789ABCDEF": "fake0001.a"}, relative=False)
        text = self.fh.read(os.path.join(FF, "profiles.ini"))
        self.assertIn("IsRelative=0", text)
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        self.assertEqual([(p.name, p.default) for p in got], [("a", True), ("b", False)])

    def test_garbled_file(self):
        text = fixture_text("profiles/garbled.ini").replace("fake0008.nul", "fake0008\0nul")
        self.fh.write(os.path.join(FF, "profiles.ini"), b"\xef\xbb\xbf" + text.encode("utf-8")
                      + b"\n[Profile9]\nName=\xff\xfe binary\nPath=fake0009.bin\n")
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        names = [p.name for p in got]
        self.assertEqual(names[0], "repeated key wins")   # last value wins (nsINIParser)
        self.assertNotIn("ok", names)
        self.assertNotIn("broken header", names)
        self.assertNotIn("not a profile section", names)
        self.assertNotIn("no path", names)
        self.assertNotIn("null byte", names)
        self.assertIn("missing folder", names)            # existence is find_profiles' job
        self.assertFalse(any(p.default for p in got))     # [Install] without a hash is ignored

    def test_repeated_section_is_merged(self):
        # nsINIParser keeps one section per name: keys of a repeated header
        # join it, and the last value of a key wins.
        root = self.fh.resolve(FF)
        self.fh.write(os.path.join(FF, "profiles.ini"),
                      "[Profile0]\nName=one\nIsRelative=1\nPath=fake0001.one\nPath=fake0002.two\n"
                      "\n[General]\nVersion=2\n\n[Profile0]\nDefault=1\n")
        self.assertEqual(bg.parse_profiles_ini(str(root)),
                         [bg.IniProfile("one", str(root / "fake0002.two"), True)])

    def test_lines_split_on_cr_and_lf_only(self):
        # U+2028, U+0085 and \x1c-\x1e are not line breaks for Firefox.
        root = self.fh.resolve(FF)
        for odd in ("\u2028", "\x85", "\x1c", "\x1d", "\x1e"):
            folder = "fake0001.x" + odd + "y"
            self.fh.write(os.path.join(FF, "profiles.ini"),
                          "[Profile0]\rName=n\r\nIsRelative=1\nPath=%s\nDefault=1\n" % folder)
            self.assertEqual(bg.parse_profiles_ini(str(root)),
                             [bg.IniProfile("n", str(root / folder), True)], repr(odd))

    def test_default_follows_firefox(self):
        root = self.fh.resolve(FF)

        def defaults(text):
            self.fh.write(os.path.join(FF, "profiles.ini"), text)
            return [(p.name, p.default) for p in bg.parse_profiles_ini(str(root))]

        one = "[Profile%d]\nName=%s\n%sPath=%s\n%s\n"
        # Firefox stops at Profile0 (no IsRelative): nothing it loads is default.
        self.assertEqual(defaults(one % (0, "one", "", "fake0001.one", "")
                                  + one % (1, "two", "IsRelative=1\n", "fake0002.two", "Default=1")),
                         [("one", False), ("two", False)])
        # A gap: Profile5 is never read by Firefox.
        self.assertEqual(defaults(one % (0, "one", "IsRelative=1\n", "fake0001.one", "")
                                  + one % (5, "five", "IsRelative=1\n", "fake0005.five", "Default=1")),
                         [("one", False), ("five", False)])
        # IsRelative=true is not "1": an absolute path is expected, a.one is not one.
        self.assertEqual(defaults(one % (0, "one", "IsRelative=true\n", "fake0001.one", "Default=1")),
                         [("one", False)])
        # No Name=: Firefox skips the entry but goes on reading.
        self.assertEqual(defaults("[Profile0]\nIsRelative=1\nPath=fake0001.one\nDefault=1\n"
                                  + one % (1, "two", "IsRelative=1\n", "fake0002.two", "")),
                         [("fake0001.one", False), ("two", False)])
        # The last Default=1 wins.
        self.assertEqual(defaults(one % (0, "one", "IsRelative=1\n", "fake0001.one", "Default=1")
                                  + one % (1, "two", "IsRelative=1\n", "fake0002.two", "Default=1")),
                         [("one", False), ("two", True)])
        # An [Install] default only counts when it names an entry Firefox loads.
        self.assertEqual(defaults("[InstallAAAA]\nDefault=fake0005.five\n\n"
                                  + one % (0, "one", "IsRelative=1\n", "fake0001.one", "Default=1")
                                  + one % (5, "five", "IsRelative=1\n", "fake0005.five", "")),
                         [("one", True), ("five", False)])

    def test_crlf_and_spaces(self):
        self.fh.write(os.path.join(FF, "profiles.ini"),
                      b"[Profile0]\r\nName = spaced \r\nIsRelative=1\r\nPath= fake0001.x \r\nDefault=1\r\n")
        got = bg.parse_profiles_ini(str(self.fh.resolve(FF)))
        self.assertEqual(got, [bg.IniProfile("spaced", str(self.fh.resolve(FF) / "fake0001.x"), True)])

    def test_binary_junk_missing_and_not_a_file(self):
        root = self.fh.resolve(FF)
        self.assertEqual(bg.parse_profiles_ini(str(root)), [])   # no root at all
        self.fh.write(os.path.join(FF, "profiles.ini"), os.urandom(4096) + b"\x00\n[[[\n")
        self.assertIsInstance(bg.parse_profiles_ini(str(root)), list)
        os.remove(str(root / "profiles.ini"))
        os.mkfifo(str(root / "profiles.ini"))                 # must not hang
        self.assertEqual(bg.parse_profiles_ini(str(root)), [])

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_unreadable_file(self):
        path = self.ini(FF, "profiles/install-default.ini")
        os.chmod(str(path), 0)
        self.assertEqual(bg.parse_profiles_ini(str(self.fh.resolve(FF))), [])


class FindProfilesTest(DiscoverCase):

    def test_record_fields(self):
        self.fh.make_profile(FF, "fake0001.default-release")
        self.fh.make_profile(FF, "fake0002.default")
        self.ini(FF, "profiles/install-default.ini")
        got = self.profiles()
        self.assertEqual([p.name for p in got], ["default-release", "default"])
        p = got[0]
        root = self.fh.resolve(FF)
        self.assertEqual((p.family, p.variant, p.root, p.default, p.source),
                         ("firefox", "native", str(root), True, "ini"))
        self.assertEqual(p.path, str(root / "fake0001.default-release"))
        self.assertRegex(p.id, r"^[0-9a-f]{12}$")
        self.assertEqual(p.id, hashlib.sha256(os.fsencode(os.path.realpath(p.path))).hexdigest()[:12])
        self.assertNotEqual(got[0].id, got[1].id)
        self.assertEqual(self.profiles(), got)            # stable

    def test_listed_folder_missing_is_dropped(self):
        self.fh.make_profile(FF, "fake0001.default-release")
        self.ini(FF, "profiles/install-default.ini")       # fake0002.default does not exist
        self.assertEqual([p.name for p in self.profiles()], ["default-release"])

    def test_absolute_profile_outside_the_root(self):
        elsewhere = self.fh.make_profile("profiles", "fake0002.elsewhere")
        other = self.fh.resolve("other/fake0005.implicit-absolute")
        self.fh.make_profile(os.path.join(FF, "Profiles"), "fake0003.nested")
        self.ini(FF, "profiles/absolute.ini", ELSEWHERE=elsewhere, OTHER=other)
        got = self.by_name()
        self.assertEqual(sorted(got), ["elsewhere", "nested"])
        self.assertEqual(got["elsewhere"].path, str(elsewhere))
        self.assertEqual(got["elsewhere"].root, str(self.fh.resolve(FF)))
        self.assertTrue(got["elsewhere"].default)

    def test_profile_groups(self):
        # The profile manager's group: one profile in profiles.ini, the
        # others only on disk, plus folders that are not profiles.
        self.fh.make_profile(FF, "fake0001.default-release")
        self.fh.write_profiles_ini(FF, [{"name": "default-release", "path": "fake0001.default-release"}],
                                   installs={"0123456789ABCDEF": "fake0001.default-release"})
        self.fh.make_profile_group(FF, ["fake0010.Work", "fake0011.Profile 2", "nosalt"])
        self.fh.write(os.path.join(FF, "Crash Reports", "InstallTime0"), "0")
        self.fh.resolve(os.path.join(FF, "Pending Pings")).mkdir()
        target = self.fh.make_profile("linked", "fake0012.linked")
        os.symlink(str(target), str(self.fh.resolve(os.path.join(FF, "fake0012.linked"))))
        got = self.profiles()
        # Unlisted folders sorted by folder name: fake0010.Work, fake0011.Profile 2, nosalt.
        self.assertEqual([(p.name, p.source, p.default) for p in got], [
            ("default-release", "ini", True),
            ("Work", "scan", False),
            ("Profile 2", "scan", False),
            ("nosalt", "scan", False),
        ])
        self.assertEqual(len({p.id for p in got}), 4)

    def test_scan_groups_skips_known(self):
        root = self.fh.resolve(FF)
        a = self.fh.make_profile(FF, "fake0001.a")
        self.fh.make_profile(FF, "fake0002.b")
        got = bg.scan_groups(str(root), {os.path.realpath(str(a))})
        self.assertEqual(got, [("b", str(root / "fake0002.b"))])
        self.assertEqual(bg.scan_groups(str(self.fh.resolve("nowhere"))), [])

    def test_root_without_profiles_ini(self):
        self.fh.make_profile_group(".zen", ["fake0020.Default (release)"])
        got = self.profiles()
        self.assertEqual([(p.family, p.name, p.source) for p in got],
                         [("zen", "Default (release)", "scan")])

    def test_listed_profile_not_scanned_twice(self):
        self.fh.make_profile(FF, "fake0001.default-release")
        self.fh.make_profile(FF, "fake0002.default")
        self.ini(FF, "profiles/install-default.ini")
        self.assertEqual([p.source for p in self.profiles()], ["ini", "ini"])

    def test_every_root(self):
        # One profile in every ROOTS entry: each is found once, with the
        # family and variant of its root (native, Snap and every Flatpak).
        env = self.env
        expected = []
        for index, root in enumerate(bg.ROOTS):
            top = bg.root_path(root, env)
            folder = "fake%04d.r%d" % (index, index)
            self.fh.make_profile(top, folder)
            self.fh.write_profiles_ini(top, [{"name": "p%d" % index, "path": folder, "default": True}])
            expected.append(("p%d" % index, root.family, root.variant, top))
        got = [(p.name, p.family, p.variant, p.root) for p in self.profiles()]
        self.assertEqual(got, expected)
        variants = {root.variant for root in bg.ROOTS}
        self.assertEqual(variants, {"native", "flatpak", "snap"})

    def test_flatpak_roots(self):
        layouts = {
            ".var/app/org.mozilla.firefox/.mozilla/firefox": "firefox",
            ".var/app/io.gitlab.librewolf-community/.librewolf": "librewolf",
            ".var/app/app.zen_browser.zen/config/zen": "zen",
            ".var/app/one.ablaze.floorp/.floorp": "floorp",
            ".var/app/net.waterfox.waterfox/config/waterfox": "waterfox",
        }
        for rel in layouts:
            self.fh.make_profile(rel, "fake0001.default-release")
            self.fh.write_profiles_ini(rel, [{"name": "default-release", "path": "fake0001.default-release"}])
        got = sorted((p.root, p.family, p.variant) for p in self.profiles())
        self.assertEqual(got, sorted((str(self.fh.resolve(rel)), fam, "flatpak")
                                     for rel, fam in layouts.items()))

    def test_flatpak_config_layout_ignores_host_xdg(self):
        # Inside the sandbox the config dir is ~/.var/app/<id>/config, whatever
        # the host's XDG_CONFIG_HOME says.
        rel = ".var/app/org.mozilla.firefox/config/mozilla/firefox"
        self.fh.make_profile(rel, "fake0001.default-release")
        self.fh.write_profiles_ini(rel, ["fake0001.default-release"])
        env = self.fh.env({"XDG_CONFIG_HOME": self.fh.resolve("xdg")})
        self.assertEqual([(p.variant, p.root) for p in self.profiles(env)],
                         [("flatpak", str(self.fh.resolve(rel)))])

    def test_snap_root(self):
        rel = "snap/firefox/common/.mozilla/firefox"
        self.fh.make_profile(rel, "fake0003.default")
        self.ini(rel, "profiles/default-flag-only.ini")
        self.fh.make_profile(rel, "fake0002.default")
        got = self.profiles()
        self.assertEqual([(p.family, p.variant, p.name, p.default, p.source) for p in got], [
            ("firefox", "snap", "default", True, "ini"),       # fake0002.default, Default=1
            ("firefox", "snap", "default", False, "scan"),     # fake0003.default, unlisted
        ])
        self.assertEqual(got[0].path, str(self.fh.resolve(rel) / "fake0002.default"))

    def test_xdg_config_home(self):
        xdg = self.fh.resolve("xdg-config")
        env = self.fh.env({"XDG_CONFIG_HOME": xdg})
        self.fh.make_profile("xdg-config/mozilla/firefox", "fake0001.xdg")
        self.fh.write_profiles_ini("xdg-config/mozilla/firefox", ["fake0001.xdg"])
        self.fh.make_profile(".config/mozilla/firefox", "fake0002.ignored")
        self.fh.write_profiles_ini(".config/mozilla/firefox", ["fake0002.ignored"])
        got = self.profiles(env)
        self.assertEqual([(p.name, p.root) for p in got],
                         [("fake0001.xdg", str(xdg / "mozilla" / "firefox"))])
        # Default: $HOME/.config.
        got = self.profiles(self.fh.env({"XDG_CONFIG_HOME": None}))
        self.assertEqual([p.name for p in got], ["fake0002.ignored"])

    def test_relative_xdg_config_home_is_ignored(self):
        self.fh.make_profile(".config/librewolf/librewolf", "fake0001.default")
        self.fh.write_profiles_ini(".config/librewolf/librewolf", ["fake0001.default"])
        for value in ("relative/dir", ""):
            env = self.fh.env({"XDG_CONFIG_HOME": value})
            self.assertEqual(bg.xdg_dir("XDG_CONFIG_HOME", env), str(self.fh.config))
            self.assertEqual([p.family for p in self.profiles(env)], ["librewolf"])

    def test_xdg_dir_defaults(self):
        env = self.fh.env({"XDG_CONFIG_HOME": None, "XDG_CACHE_HOME": None,
                           "XDG_STATE_HOME": None, "XDG_DATA_HOME": None})
        self.assertEqual(bg.home_dir(env), str(self.fh.home))
        self.assertEqual(bg.xdg_dir("XDG_CONFIG_HOME", env), str(self.fh.home / ".config"))
        self.assertEqual(bg.xdg_dir("XDG_CACHE_HOME", env), str(self.fh.home / ".cache"))
        self.assertEqual(bg.xdg_dir("XDG_STATE_HOME", env), str(self.fh.home / ".local" / "state"))
        self.assertEqual(bg.xdg_dir("XDG_DATA_HOME", env), str(self.fh.home / ".local" / "share"))

    def test_symlinked_root_is_walked_once(self):
        # ~/.mozilla/firefox -> ~/.config/mozilla/firefox: same profiles once,
        # under the first root in ROOTS order.
        real = ".config/mozilla/firefox"
        self.fh.make_profile(real, "fake0001.default-release")
        self.fh.make_profile(real, "fake0002.default")
        self.ini(real, "profiles/install-default.ini")
        self.fh.resolve(".mozilla").mkdir()
        os.symlink(str(self.fh.resolve(real)), str(self.fh.resolve(FF)))
        got = self.profiles()
        self.assertEqual([p.name for p in got], ["default-release", "default"])
        self.assertEqual({p.root for p in got}, {str(self.fh.resolve(real))})

    def test_reverse_symlinked_root_keeps_the_id(self):
        # The id hashes the canonical path: it does not depend on the root
        # (or symlink) the profile was found through.
        self.fh.make_profile(FF, "fake0001.default-release")
        self.fh.make_profile(FF, "fake0002.default")
        self.ini(FF, "profiles/install-default.ini")
        before = {p.name: p.id for p in self.profiles()}
        self.fh.resolve(".config/mozilla").mkdir(parents=True)
        os.symlink(str(self.fh.resolve(FF)), str(self.fh.resolve(".config/mozilla/firefox")))
        got = self.profiles()
        self.assertEqual({p.name: p.id for p in got}, before)
        self.assertEqual({p.root for p in got}, {str(self.fh.resolve(".config/mozilla/firefox"))})

    def test_profile_listed_by_two_roots(self):
        shared = self.fh.make_profile("shared", "fake0001.shared")
        for rel in (FF, ".librewolf"):
            self.fh.write_profiles_ini(rel, [{"name": "shared", "path": str(shared), "relative": False}])
        got = self.profiles()
        self.assertEqual([(p.family, p.name) for p in got], [("firefox", "shared")])

    def test_symlinked_profile_listed_in_ini(self):
        target = self.fh.make_profile("store", "fake0001.target")
        self.fh.resolve(FF).mkdir(parents=True)
        os.symlink(str(target), str(self.fh.resolve(os.path.join(FF, "fake0001.link"))))
        self.fh.write_profiles_ini(FF, [{"name": "link", "path": "fake0001.link", "default": True}])
        got = self.profiles()
        self.assertEqual([(p.name, p.source) for p in got], [("link", "ini")])
        self.assertEqual(got[0].id, bg.profile_id(str(target)))

    def test_root_or_parent_is_never_a_profile(self):
        self.fh.write(os.path.join(FF, "prefs.js"), "")
        self.fh.write("prefs.js", "")                      # even with a prefs.js in $HOME
        self.fh.make_profile(FF, "fake0001.ok")
        self.fh.write_profiles_ini(FF, [{"name": "dot", "path": "."}, {"name": "up", "path": ".."},
                                        {"name": "home", "path": "../..", "default": True},
                                        {"name": "slash", "path": "/", "relative": False},
                                        {"name": "ok", "path": "fake0001.ok"}])
        self.assertEqual([p.name for p in self.profiles()], ["ok"])

    def test_other_roots_home_and_nested_profiles_are_never_profiles(self):
        a = self.fh.make_profile(FF, "fake0001.a")
        self.fh.write(os.path.join(FF, "fake0001.a", "chrome", "prefs.js"), "")
        lw = self.fh.make_profile(".librewolf", "fake0002.lw")
        self.fh.write(os.path.join(".librewolf", "prefs.js"), "")
        self.fh.write(os.path.join(".config", "prefs.js"), "")
        self.fh.write(os.path.join(".local", "state", "prefs.js"), "")
        self.fh.write_profiles_ini(FF, [
            {"name": "a", "path": "fake0001.a"},
            {"name": "nested", "path": "fake0001.a/chrome"},
            {"name": "lwroot", "path": str(self.fh.resolve(".librewolf")), "relative": False},
            {"name": "config", "path": "../../.config"},
            {"name": "local", "path": "../../.local"},
            {"name": "state", "path": "../../.local/state"},
            {"name": "parent-of-a", "path": "../../.mozilla"},
        ])
        got = self.profiles()
        # The LibreWolf profile is found once, by its own root's scan.
        self.assertEqual([(p.name, p.family, p.path) for p in got],
                         [("a", "firefox", str(a)), ("lw", "librewolf", str(lw))])

    def test_profile_under_another_root_takes_the_first_root(self):
        # Documented: attribution follows ROOTS order.
        lw = self.fh.make_profile(".librewolf", "fake0002.lw")
        self.fh.write_profiles_ini(FF, [{"name": "sib", "path": "../../.librewolf/fake0002.lw"}])
        self.assertEqual([(p.name, p.family, p.path) for p in self.profiles()],
                         [("sib", "firefox", str(lw))])

    def test_nothing_installed(self):
        self.assertEqual(self.profiles(), [])

    def test_contract_shapes(self):
        self.fh.make_profile(FF, "fake0001.default-release")
        self.fh.write_profiles_ini(FF, ["fake0001.default-release"])
        for p in self.profiles():
            self.assertIn(p.family, bg.FAMILIES)
            self.assertIn(p.variant, bg.VARIANTS)
            self.assertIsInstance(p.default, bool)
            self.assertTrue(re.fullmatch(r"[0-9a-f]{12}", p.id))
            self.assertTrue(os.path.isabs(p.path) and os.path.isabs(p.root))


if __name__ == "__main__":
    unittest.main()

"""inputs: DMS's global opacity (niri windowrules.kdl) and its colours
(dms-colors.json), read from a FakeHome.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import os
import unittest

from fakehome import FakeHome, fixture_text, load_script

bg = load_script()

RULES = ".config/niri/dms/windowrules.kdl"


def opacity(text):
    return bg.global_opacity(text)


class KdlOpacityTest(unittest.TestCase):

    def test_dms_shaped_file(self):
        # Mirrors the file DMS writes: the global "Glass blur" rule first,
        # then rules matching DMS's own windows.
        self.assertEqual(opacity(fixture_text("kdl/dms-windowrules.kdl")), 0.85)

    def test_comments(self):
        # //, nested /* */, /- on rules, on children and on a match.
        self.assertEqual(opacity(fixture_text("kdl/comments.kdl")), 0.7)

    def test_rules_with_match_are_skipped(self):
        # A rule with both `match` and `exclude` is local too. Also: a global
        # rule without opacity is passed over (v0 semantics: the first global
        # rule that sets an opacity).
        self.assertEqual(opacity(fixture_text("kdl/match-first.kdl")), 0.9)

    def test_exclude_only_rule_is_global(self):
        # niri: a rule without `match` applies to every window but the
        # excluded ones, so its opacity is the DMS look (v0 did the same).
        cases = {
            'window-rule {\n    exclude title="Private"\n    opacity 0.55\n}\n'
            'window-rule { opacity 0.9; }': 0.55,
            'window-rule {\n    match app-id="x"\n    exclude title="y"\n    opacity 0.3\n}\n'
            'window-rule {\n    exclude app-id="z"\n    opacity 0.45\n}': 0.45,
            'window-rule {\n    exclude app-id="z"\n}\nwindow-rule { opacity 0.65; }': 0.65,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_nested(self):
        # window-rule below the top level, opacity in nested blocks: ignored.
        self.assertEqual(opacity(fixture_text("kdl/nested.kdl")), 0.75)

    def test_strings_with_braces_and_comment_markers(self):
        self.assertEqual(opacity(fixture_text("kdl/strings.kdl")), 0.65)

    def test_no_global_rule(self):
        self.assertEqual(opacity(fixture_text("kdl/no-global.kdl")), 1.0)
        self.assertEqual(opacity(""), 1.0)
        self.assertEqual(opacity("window-rule\n"), 1.0)          # no block
        self.assertEqual(opacity("window-rule {}\n"), 1.0)

    def test_values(self):
        cases = {
            "window-rule {\n    opacity 1.00\n}\n": 1.0,
            "window-rule {\n    opacity 1\n}\n": 1.0,
            "window-rule { opacity 0.5; }": 0.5,
            "window-rule { opacity 1.5; }": 1.0,                 # clamped
            "window-rule { opacity -0.5; }": 0.0,
            "window-rule { opacity 0.2_5; }": 0.25,
            "window-rule { opacity (f64)0.6; }": 0.6,             # type annotation
            "window-rule { opacity abc; }\nwindow-rule { opacity 0.4; }": 0.4,
            "window-rule { opacity nan; }\nwindow-rule { opacity 0.3; }": 0.3,
            "window-rule { opacity inf; }": 1.0,
            'window-rule { opacity "0.2"; }': 1.0,               # a string is not a number
            "window-rule { opacity; }\nwindow-rule { opacity 0.45; }": 0.45,
            "window-rule {\n    opacity \\\n        0.55\n}\n": 0.55,   # line continuation
            "window-rule {\n    opacity 0.35 /- 0.9\n}\n": 0.35,
            "window-rule {\n    opacity /- 0.9 0.25\n}\n": 0.25,
            "window-rule {\r\n    opacity 0.15\r\n}\r\n": 0.15,
            "\ufeffwindow-rule { opacity 0.65; }": 0.65,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_slashdash_variants(self):
        cases = {
            "/-window-rule { opacity 0.1; }\nwindow-rule { opacity 0.2; }": 0.2,
            "/-\nwindow-rule { opacity 0.1; }\nwindow-rule { opacity 0.2; }": 0.2,
            "window-rule /-{ opacity 0.1; } { opacity 0.3; }": 0.3,
            'window-rule {\n    /-match app-id="x"\n    opacity 0.4\n}': 0.4,
            'window-rule {\n    match /-app-id="x"\n    opacity 0.4\n}\nwindow-rule { opacity 0.5; }': 0.5,
            'window-rule {\n    /- match app-id="x" {\n        nested 1\n    }\n    opacity 0.6\n}': 0.6,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_comment_edge_cases(self):
        cases = {
            "/* unterminated window-rule { opacity 0.1; }": 1.0,
            "/* a /* b */ window-rule { opacity 0.1; } */ window-rule { opacity 0.2; }": 0.2,
            "window-rule { opacity 0.3; } // window-rule { opacity 0.1; }": 0.3,
            "window-rule { // }\n    opacity 0.35\n}": 0.35,
            "window-rule { /* } */ opacity 0.4; }": 0.4,
            "window-rule { opacity/* x */0.45; }": 0.45,
            "window-rule { opacity 0.5;} //* not a block comment\nwindow-rule { opacity 0.1; }": 0.5,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_string_edge_cases(self):
        cases = {
            'window-rule {\n    match title="}"\n    opacity 0.1\n}\nwindow-rule { opacity 0.2; }': 0.2,
            'window-rule {\n    match title="\\\\"\n    opacity 0.1\n}\nwindow-rule { opacity 0.25; }': 0.25,
            'window-rule {\n    match title=r"C:\\"\n    opacity 0.1\n}\nwindow-rule { opacity 0.3; }': 0.3,
            'window-rule {\n    match title=r##"a "# } b"##\n    opacity 0.1\n}\nwindow-rule { opacity 0.35; }': 0.35,
            'window-rule {\n    match title="""\n  }  {\n  """\n    opacity 0.1\n}\nwindow-rule { opacity 0.4; }': 0.4,
            'window-rule {\n    match title="multi\nline } {"\n    opacity 0.1\n}\nwindow-rule { opacity 0.45; }': 0.45,
            'window-rule {\n    match title="unterminated\n    opacity 0.1\n}\n': 1.0,
            'window-rule {\n    match title="" opacity 0.1\n}\nwindow-rule { opacity 0.5; }': 0.5,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_unbalanced_and_garbage(self):
        cases = {
            "}}}\nwindow-rule { opacity 0.3; }": 0.3,
            "window-rule {\n    opacity 0.4\n": 0.4,                  # never closed
            "foo {\nwindow-rule { opacity 0.1; }": 1.0,               # inside an open block
            "window-rule { opacity 0.2; }}}}\nwindow-rule { opacity 0.1; }": 0.2,
            "= = = window-rule { opacity 0.3; }": 0.3,
            "((((": 1.0,
            "\\": 1.0,
            "/": 1.0,
            "#": 1.0,
            "r#\"": 1.0,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(opacity(text), want, msg=repr(text))

    def test_deep_nesting_does_not_crash(self):
        deep = "a {\n" * 5000 + "window-rule { opacity 0.1; }\n" + "}\n" * 5000
        self.assertEqual(opacity(deep + "window-rule { opacity 0.6; }\n"), 0.6)
        self.assertEqual(opacity("a {" * 100000), 1.0)

    def test_random_bytes_do_not_crash(self):
        import random
        rng = random.Random(1234)
        alphabet = 'window-rule opacity match {}();="\\/*-#r\n 0.5'
        for _ in range(300):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(80)))
            value = opacity(text)
            self.assertTrue(0.0 <= value <= 1.0, repr(text))

    def test_tokens(self):
        toks = bg.kdl_tokens('node "a b" r#"c"# 1 { x=2; } /- y')
        self.assertEqual(toks, [
            ("word", "node"), ("str", "a b"), ("str", "c"), ("word", "1"), ("{", None),
            ("word", "x"), ("=", None), ("word", "2"), bg._KDL_TERM, ("}", None),
            bg._KDL_SLASHDASH, ("word", "y"),
        ])

    def test_parse_tree(self):
        nodes = bg.kdl_parse('window-rule {\n    match app-id="x" is-floating=true\n    opacity 0.5\n}\n')
        self.assertEqual(len(nodes), 1)
        rule = nodes[0]
        self.assertEqual(rule.name, "window-rule")
        self.assertEqual([c.name for c in rule.children], ["match", "opacity"])
        self.assertEqual(rule.children[0].props, {"app-id": ("str", "x"), "is-floating": ("word", "true")})
        self.assertEqual(rule.children[1].args, [("word", "0.5")])


class DmsOpacityTest(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def test_reads_windowrules_kdl(self):
        path = self.fh.write_kdl(RULES, fixture_text("kdl/dms-windowrules.kdl"))
        before = path.read_bytes(), os.stat(str(path)).st_mtime_ns
        self.assertEqual(bg.dms_opacity(self.fh.env()), 0.85)
        self.assertEqual((path.read_bytes(), os.stat(str(path)).st_mtime_ns), before)  # read only

    def test_missing_file(self):
        self.assertEqual(bg.dms_opacity(self.fh.env()), 1.0)
        self.assertEqual(bg.DEFAULT_OPACITY, 1.0)

    def test_xdg_config_home(self):
        self.fh.write_kdl(RULES, "window-rule { opacity 0.5; }\n")
        self.fh.write_kdl("xdg/niri/dms/windowrules.kdl", "window-rule { opacity 0.7; }\n")
        self.assertEqual(bg.dms_opacity(self.fh.env({"XDG_CONFIG_HOME": self.fh.resolve("xdg")})), 0.7)
        self.assertEqual(bg.dms_opacity(self.fh.env({"XDG_CONFIG_HOME": None})), 0.5)
        self.assertEqual(bg.dms_opacity(self.fh.env({"XDG_CONFIG_HOME": "relative"})), 0.5)

    def test_symlinked_rules(self):
        target = self.fh.write_kdl("dotfiles/windowrules.kdl", "window-rule { opacity 0.6; }\n")
        self.fh.resolve(".config/niri/dms").mkdir(parents=True)
        os.symlink(str(target), str(self.fh.resolve(RULES)))
        self.assertEqual(bg.dms_opacity(self.fh.env()), 0.6)

    def test_unusable_files(self):
        self.fh.write(RULES, os.urandom(2048))
        self.assertTrue(0.0 <= bg.dms_opacity(self.fh.env()) <= 1.0)
        self.fh.write(RULES, b"window-rule { opacity 0.4; }\n\xff\xfe\n")
        self.assertEqual(bg.dms_opacity(self.fh.env()), 0.4)
        os.remove(str(self.fh.resolve(RULES)))
        os.mkdir(str(self.fh.resolve(RULES)))
        self.assertEqual(bg.dms_opacity(self.fh.env()), 1.0)
        os.rmdir(str(self.fh.resolve(RULES)))
        os.mkfifo(str(self.fh.resolve(RULES)))                # must not hang
        self.assertEqual(bg.dms_opacity(self.fh.env()), 1.0)


class DmsColorsTest(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.env = self.fh.env()

    def colors_path(self):
        return self.fh.cache / "dms" / "dms-colors.json"

    def test_dark(self):
        self.fh.write_dms_colors(mode="dark", surface_dark="#1a1b2c", surface_light="#f0f1f2")
        self.assertEqual(bg.dms_colors(self.env), bg.Colors("dark", "#1a1b2c"))

    def test_light(self):
        self.fh.write_dms_colors(mode="light", surface_dark="#1a1b2c", surface_light="#f0f1f2")
        self.assertEqual(bg.dms_colors(self.env), ("light", "#f0f1f2"))

    def test_mode_argument_forces_the_palette(self):
        self.fh.write_dms_colors(mode="dark", surface_dark="#1a1b2c", surface_light="#f0f1f2")
        self.assertEqual(bg.dms_colors(self.env, mode="light"), ("light", "#f0f1f2"))
        self.assertEqual(bg.dms_colors(self.env, mode="dark"), ("dark", "#1a1b2c"))
        self.assertEqual(bg.dms_colors(self.env, mode="bogus"), ("dark", "#1a1b2c"))

    def test_corrupt_file(self):
        self.fh.write_dms_colors(mode="light", surface_light="#f0f1f2")
        full = self.colors_path().read_text(encoding="utf-8")
        for broken in (full[: len(full) // 2], "", "not json", "\xff", "[1, 2]", "null", '"dark"',
                       "[" * 100000):
            self.fh.write(self.colors_path(), broken)
            self.assertEqual(bg.dms_colors(self.env), ("dark", bg.DEFAULT_SURFACE), repr(broken[:20]))
        self.fh.write(self.colors_path(), os.urandom(512))
        self.assertEqual(bg.dms_colors(self.env).surface, bg.DEFAULT_SURFACE)

    def test_missing_file(self):
        self.assertEqual(bg.dms_colors(self.env), ("dark", bg.DEFAULT_SURFACE))
        self.assertEqual(bg.dms_colors(self.env, mode="light"), ("light", bg.DEFAULT_SURFACES["light"]))

    def test_wrong_shapes(self):
        docs = [
            ({"mode": "light", "colors": []}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": "x"}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {"surface": 12}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {"surface": "red"}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {"surface": "#fFf"}}}, ("light", "#ffffff")),
            ({"mode": "light", "colors": {"light": {"surface": "#a1c"}}}, ("light", "#aa11cc")),
            ({"mode": "light", "colors": {"light": {"surface": "#abcd"}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {"surface": "#1234567"}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"light": {"surface": "#12345g"}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": "light", "colors": {"dark": {"surface": "#111111"}}}, ("light", bg.DEFAULT_SURFACES["light"])),
            ({"mode": ["light"], "colors": {"dark": {"surface": "#111111"}}}, ("dark", "#111111")),
            ({"mode": "sepia", "colors": {"dark": {"surface": "#111111"}}}, ("dark", "#111111")),
            ({"colors": {"dark": {"surface": "#111111"}}}, ("dark", "#111111")),
            ({"mode": "dark", "colors": {"dark": {"surface": " #ABCDEF "}}}, ("dark", "#abcdef")),
            ({"mode": "dark", "colors": {"dark": {"surface": "#AbCdEf80"}}}, ("dark", "#abcdef")),
        ]
        for doc, want in docs:
            self.fh.write(self.colors_path(), json.dumps(doc))
            self.assertEqual(bg.dms_colors(self.env), want, doc)

    def test_utf8_bom(self):
        doc = {"mode": "light", "colors": {"light": {"surface": "#eeeeee"}}}
        self.fh.write(self.colors_path(), b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
        self.assertEqual(bg.dms_colors(self.env), ("light", "#eeeeee"))

    def test_xdg_cache_home(self):
        self.fh.write_dms_colors(mode="dark", surface_dark="#222222")
        other = self.fh.write("xdg-cache/dms/dms-colors.json", json.dumps(
            {"mode": "light", "colors": {"light": {"surface": "#eeeeee"}}}))
        self.assertTrue(other.exists())
        env = self.fh.env({"XDG_CACHE_HOME": self.fh.resolve("xdg-cache")})
        self.assertEqual(bg.dms_colors(env), ("light", "#eeeeee"))
        self.assertEqual(bg.dms_colors(self.fh.env({"XDG_CACHE_HOME": None})), ("dark", "#222222"))

    def test_contract_pattern(self):
        self.fh.write_dms_colors()
        got = bg.dms_colors(self.env)
        self.assertIn(got.mode, ("dark", "light"))
        self.assertRegex(got.surface, r"^#[0-9a-fA-F]{6}$")
        self.assertRegex(bg.DEFAULT_SURFACE, r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()

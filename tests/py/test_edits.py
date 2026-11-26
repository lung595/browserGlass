"""edits: @import lines of userChrome.css / userContent.css and the managed
block of user.js (v0 and v1 markers, CRLF, damaged blocks).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import unittest

from fakehome import load_script

bg = load_script()

IMPORT = bg.V1_IMPORT_CHROME
V0_BLOCK = bg.V0_USERJS_BLOCK_TEMPLATE.format(transparent="true", scheme="0")


def has_import(text, import_line):
    """True when a whole line of `text` imports what `import_line` imports."""
    matcher = bg._import_matcher(import_line)
    return any(matcher.fullmatch(bg._line_body(line)) for line in bg._lines(bg._split_bom(text)[1]))


def v1_block(**over):
    settings = bg.settings_from_json("{}")
    settings.update(over)
    return bg.userjs_block(settings, 0.85)


class ImportTest(unittest.TestCase):

    def test_added_at_top(self):
        self.assertEqual(bg.ensure_import("", IMPORT), IMPORT + "\n")
        self.assertEqual(bg.ensure_import("a {}\n", IMPORT), IMPORT + "\na {}\n")
        self.assertEqual(bg.ensure_import("a {}", IMPORT), IMPORT + "\na {}")

    def test_idempotent(self):
        once = bg.ensure_import("a {}\n", IMPORT)
        self.assertEqual(bg.ensure_import(once, IMPORT), once)

    def test_v0_line_recognised(self):
        text = '/* mine */\n%s\na {}\n' % bg.V0_IMPORT_CHROME
        self.assertEqual(bg.ensure_import(text, IMPORT), text)

    def test_variants_recognised(self):
        for line in ("@import 'dms-glass-chrome.css';", '@import url("dms-glass-chrome.css");',
                     "@import url(dms-glass-chrome.css);", '  @IMPORT   "dms-glass-chrome.css" ;  ',
                     '@import "dms-glass-chrome.css";\r'):
            for text in (line + "\na {}\n", "/* x\n y */\n" + line + "\na {}\n",
                         '@charset "x";\n@import "o.css";\n' + line + "\n"):
                self.assertEqual(bg.ensure_import(text, IMPORT), text, line)
                self.assertTrue(has_import(text, IMPORT), line)
        # Not ours: another file, or our name inside a comment.
        for line in ('@import "other.css";', '/* @import "dms-glass-chrome.css"; */',
                     '@import "dms-glass-chrome.css.bak";'):
            text = line + "\n"
            self.assertEqual(bg.ensure_import(text, IMPORT), IMPORT + "\n" + text, line)

    def test_misplaced_import_moved(self):
        # Firefox ignores an @import after a rule, and an @charset that is not
        # first: such a copy is replaced by one in the right place.
        cases = {
            "a {}\n%s\n" % IMPORT: "%s\na {}\n" % IMPORT,
            "a {}\n@import url(dms-glass-chrome.css);\nb {}\n": "%s\na {}\nb {}\n" % IMPORT,
            '%s\n@charset "x";\na {}\n' % IMPORT: '@charset "x";\n%s\na {}\n' % IMPORT,
            '\ufeffa {}\r\n%s\r\n' % IMPORT: '\ufeff%s\r\na {}\r\n' % IMPORT,
        }
        for src, expected in cases.items():
            out = bg.ensure_import(src, IMPORT)
            self.assertEqual(out, expected, repr(src))
            self.assertEqual(bg.ensure_import(out, IMPORT), out, repr(src))

    def test_bom_round_trip(self):
        for src in ("\ufeff", "\ufeffa {}\n", "\ufeffa {}\r\nb {}\r\n",
                    '\ufeff@charset "UTF-8";\na {}\n', '\ufeff@charset "UTF-8";\r\na {}\r\n'):
            out = bg.ensure_import(src, IMPORT)
            self.assertTrue(out.startswith("\ufeff"), repr(src))
            self.assertEqual(out.count("\ufeff"), 1, repr(src))
            self.assertTrue(has_import(out, IMPORT), repr(src))
            self.assertEqual(bg.ensure_import(out, IMPORT), out, repr(src))
            self.assertEqual(bg.strip_import(out, IMPORT), src, repr(src))
        # A BOM before our own line: recognised, stripped, BOM kept.
        self.assertTrue(has_import("\ufeff%s\nbody {}" % IMPORT, IMPORT))
        self.assertEqual(bg.ensure_import("\ufeff%s\nbody {}" % IMPORT, IMPORT),
                         "\ufeff%s\nbody {}" % IMPORT)
        self.assertEqual(bg.strip_import("\ufeff%s\nbody {}" % IMPORT, IMPORT), "\ufeffbody {}")

    def test_charset_without_newline_normalised(self):
        # Documented normalisation: the @charset rule gets its own line.
        out = bg.ensure_import('@charset "x";a{}', IMPORT)
        self.assertEqual(bg.strip_import(out, IMPORT), '@charset "x";\na{}')

    def test_after_charset(self):
        self.assertEqual(bg.ensure_import('@charset "UTF-8";\na {}\n', IMPORT),
                         '@charset "UTF-8";\n%s\na {}\n' % IMPORT)
        self.assertEqual(bg.ensure_import('@charset "UTF-8";', IMPORT),
                         '@charset "UTF-8";\n%s\n' % IMPORT)
        self.assertEqual(bg.ensure_import('@charset "UTF-8"; a {}\n', IMPORT),
                         '@charset "UTF-8";\n%s\n a {}\n' % IMPORT)
        self.assertEqual(bg.ensure_import('\ufeff@charset "x";\r\na{}\r\n', IMPORT),
                         '\ufeff@charset "x";\r\n%s\r\na{}\r\n' % IMPORT)

    def test_bom_and_crlf(self):
        self.assertEqual(bg.ensure_import("\ufeffa {}\n", IMPORT), "\ufeff%s\na {}\n" % IMPORT)
        self.assertEqual(bg.ensure_import("a {}\r\nb {}\r\n", IMPORT),
                         "%s\r\na {}\r\nb {}\r\n" % IMPORT)

    def test_strip(self):
        text = "%s\n/* x */\n%s\r\na {}\n@import 'dms-glass-chrome.css';" % (IMPORT, IMPORT)
        self.assertEqual(bg.strip_import(text, IMPORT), "/* x */\na {}\n")
        self.assertEqual(bg.strip_import("a {}\n", IMPORT), "a {}\n")
        self.assertEqual(bg.strip_import(bg.ensure_import("a {}\n", IMPORT), IMPORT), "a {}\n")
        self.assertTrue(has_import(IMPORT + "\n", IMPORT))
        self.assertFalse(has_import("", IMPORT))

    def test_round_trip_with_charset(self):
        original = '@charset "UTF-8";\r\n/* user */\r\na {}\r\n'
        added = bg.ensure_import(original, IMPORT)
        self.assertEqual(bg.strip_import(added, IMPORT), original)


class BlockTest(unittest.TestCase):

    def test_append(self):
        block = v1_block()
        self.assertEqual(bg.replace_block("", block), block)
        self.assertEqual(bg.replace_block('user_pref("a", 1);\n', block),
                         'user_pref("a", 1);\n' + block)
        self.assertEqual(bg.replace_block('user_pref("a", 1);', block),
                         'user_pref("a", 1);\n' + block)

    def test_idempotent(self):
        block = v1_block()
        once = bg.replace_block('user_pref("a", 1);\n', block)
        self.assertEqual(bg.replace_block(once, block), once)

    def test_replaces_v0_in_place(self):
        text = 'user_pref("a", 1);\n' + V0_BLOCK + 'user_pref("b", 2);\n'
        block = v1_block()
        self.assertEqual(bg.replace_block(text, block),
                         'user_pref("a", 1);\n' + block + 'user_pref("b", 2);\n')

    def test_updates_v1(self):
        text = "// top\n" + v1_block() + "// bottom\n"
        new = v1_block(siteTheme="none")
        self.assertEqual(bg.replace_block(text, new), "// top\n" + new + "// bottom\n")

    def test_duplicates_removed(self):
        text = "a\n" + V0_BLOCK + "b\n" + v1_block() + "c\n" + V0_BLOCK
        block = v1_block(isLight=True)
        self.assertEqual(bg.replace_block(text, block), "a\n" + block + "b\nc\n")

    def test_strip(self):
        text = "a\n" + V0_BLOCK + "b\n" + v1_block() + "c\n"
        self.assertEqual(bg.strip_block(text), "a\nb\nc\n")
        self.assertEqual(bg.strip_block("a\n"), "a\n")
        self.assertEqual(bg.strip_block(bg.replace_block("a\n", v1_block())), "a\n")

    def test_bom_before_marker(self):
        block = v1_block()
        for old in (V0_BLOCK, v1_block(isLight=True)):
            text = "\ufeff" + old + 'user_pref("b", 2);\n'
            out = bg.replace_block(text, block)
            self.assertEqual(out, "\ufeff" + block + 'user_pref("b", 2);\n')
            self.assertEqual(bg.replace_block(out, block), out)
            self.assertEqual(bg.strip_block(text), '\ufeffuser_pref("b", 2);\n')
        self.assertEqual(bg.replace_block("\ufeff", block), "\ufeff" + block)
        self.assertEqual(bg.strip_block(bg.replace_block("\ufeffa\n", block)), "\ufeffa\n")

    def test_crlf(self):
        text = 'user_pref("a", 1);\r\n' + V0_BLOCK.replace("\n", "\r\n") + 'user_pref("b", 2);\r\n'
        block = v1_block()
        out = bg.replace_block(text, block)
        self.assertEqual(out, 'user_pref("a", 1);\r\n' + block.replace("\n", "\r\n")
                         + 'user_pref("b", 2);\r\n')
        self.assertEqual(bg.strip_block(out), 'user_pref("a", 1);\r\nuser_pref("b", 2);\r\n')
        appended = bg.replace_block('user_pref("a", 1);\r\n', block)
        self.assertEqual(appended, 'user_pref("a", 1);\r\n' + block.replace("\n", "\r\n"))

    def test_markers_with_trailing_blanks(self):
        text = "a\n" + V0_BLOCK.replace("\n", "  \n", 1) + "b\n"
        self.assertEqual(bg.strip_block(text), "a\nb\n")

    def test_missing_end_marker(self):
        # Only the begin line and our own prefs right after it go; the rest
        # of the file is never eaten.
        text = ("a\n" + bg.V1_USERJS_BEGIN + "\n"
                'user_pref("%s", true);\n' % bg.PREF_STYLESHEETS
                + 'user_pref("%s", false);\n' % bg.PREF_TRANSPARENT
                + 'user_pref("user.own", 1);\n'
                + 'user_pref("%s", 0);\n' % bg.PREF_COLOR_SCHEME
                + "z\n")
        expected = 'a\nuser_pref("user.own", 1);\nuser_pref("%s", 0);\nz\n' % bg.PREF_COLOR_SCHEME
        self.assertEqual(bg.strip_block(text), expected)
        block = v1_block()
        self.assertEqual(bg.replace_block(text, block),
                         "a\n" + block + 'user_pref("user.own", 1);\nuser_pref("%s", 0);\nz\n'
                         % bg.PREF_COLOR_SCHEME)

    def test_begin_followed_by_another_begin(self):
        text = (bg.V0_USERJS_BEGIN + "\nkeep\n" + v1_block() + "tail\n")
        self.assertEqual(bg.strip_block(text), "keep\ntail\n")

    def test_lone_end_marker(self):
        text = "a\n" + bg.V1_USERJS_END + "\nb\n" + bg.V0_USERJS_END + "\n"
        self.assertEqual(bg.strip_block(text), "a\nb\n")

    def test_marker_text_inside_a_line_is_not_a_marker(self):
        text = "// note: %s\nb\n" % bg.V1_USERJS_BEGIN
        self.assertEqual(bg.strip_block(text), text)

    def test_no_final_newline(self):
        text = "a\n" + V0_BLOCK.rstrip("\n")
        self.assertEqual(bg.strip_block(text), "a\n")
        self.assertEqual(bg.replace_block(text, v1_block()), "a\n" + v1_block())
        self.assertEqual(bg.replace_block("x\n" + v1_block() + "y", v1_block()),
                         "x\n" + v1_block() + "y")

    def test_surrogates_kept(self):
        text = "a\udcff\n" + V0_BLOCK + "b\udcfe\n"
        self.assertEqual(bg.strip_block(text), "a\udcff\nb\udcfe\n")


if __name__ == "__main__":
    unittest.main()

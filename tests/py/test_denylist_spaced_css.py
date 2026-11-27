"""tools/update_styles.py: a denied style must stay denied under every key
spelling browserglass.py folds onto the same file ("x.css", "x .css",
"X .CSS"), and a mapping entry under such a spelling of a dropped style goes
with it.

Run: python3 -B -m unittest discover -s tests/py -p test_denylist_spaced_css.py
"""

import unittest

from test_update_styles import load_tool, sha

NAME = "zz-blocked-style.example.css"


class SpacedCssKeyTest(unittest.TestCase):

    def setUp(self):
        self.tool = load_tool()
        self.deny = self.tool.Denylist({sha(NAME)})

    def test_spaced_and_cased_keys_denied(self):
        for key in (NAME, "zz-blocked-style.example .css", " ZZ-Blocked-Style.example .CSS "):
            self.assertTrue(self.deny.denies_name(key), key)

    def test_mapping_variant_of_dropped_key_removed(self):
        empty = self.tool.Denylist()
        out, changed = self.tool._filter_mapping(
            {"other.example .css": ["a.example"], "kept.example.css": ["b.example"]},
            {"other.example.css"}, empty)
        self.assertTrue(changed)
        self.assertEqual(out, {"kept.example.css": ["b.example"]})


if __name__ == "__main__":
    unittest.main()

"""Zen transparency detection reads prefs.js with the same limit as the
other prefs.js readers: a big profile (over READ_LIMIT) keeps its warning.

Run: python3 -B -m unittest discover -s tests/py -p test_zen_large_prefs.py
"""

import os
import tempfile
import unittest

from fakehome import load_script

bg = load_script()


class ZenLargePrefsTest(unittest.TestCase):

    def test_large_prefs_js_still_detects_mod(self):
        with tempfile.TemporaryDirectory() as profile:
            pad = "x" * 1000
            with open(os.path.join(profile, bg.PREFS_JS), "w", encoding="utf-8") as f:
                f.write('user_pref("zen.theme.acrylic-elements", true);\n')
                while f.tell() <= bg.READ_LIMIT:
                    f.write('user_pref("pad.%d", "%s");\n' % (f.tell(), pad))
            self.assertTrue(bg.zen_transparency(profile))


if __name__ == "__main__":
    unittest.main()

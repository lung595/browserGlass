"""sync must never record "all prefs absent" for a prefs.js it could not
read: uninstall would later delete the user's own values. A large prefs.js
(over READ_LIMIT) is still read; an unreadable one skips the profile.

Run: python3 -B -m unittest discover -s tests/py -p test_prefs_read.py
"""

import json
import os
import unittest

from test_sync import PROFILE, STATE, SyncCase, prefs_text

STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"


class PrefsReadTest(SyncCase):

    def test_large_prefs_js_keeps_user_values(self):
        self.home(prefs={STYLESHEETS: "true"})
        padding = "".join('user_pref("pad.%d", "%s");\n' % (i, "x" * 1000) for i in range(4500))
        self.fh.write(PROFILE + "/prefs.js", prefs_text({STYLESHEETS: "true"}) + padding)
        out = self.sync()
        self.assertEqual(out["warnings"], [])
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertEqual(state["profiles"][self.pid()]["prefs_original"][STYLESHEETS],
                         {"value": "true"})

    @unittest.skipIf(os.geteuid() == 0, "root reads a mode 000 file")
    def test_unreadable_prefs_js_skips_profile(self):
        self.home(prefs={STYLESHEETS: "true"})
        os.chmod(str(self.fh.resolve(PROFILE + "/prefs.js")), 0)
        out = self.sync()
        self.assertEqual([w["code"] for w in out["warnings"]], ["read_failed"])
        self.assertEqual(out["changed"], [])
        state = json.loads(self.fh.read(STATE + "/state.json"))
        self.assertNotIn(self.pid(), state["profiles"])


if __name__ == "__main__":
    unittest.main()

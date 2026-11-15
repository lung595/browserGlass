"""tools/media/plugin_settings.py: the browserGlass entry of a fake
plugin_settings.json saved, changed, put back JSON-equal, every other key
byte for byte, and never printed."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("media_plugin_settings",
                                               REPO / "tools" / "media" / "plugin_settings.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

SECRET = "secret-site.example"
DOC = {
    "otherPlugin": {"enabled": True, "ratio": 1.5, "list": ["a", "b"]},
    "browserGlass": {"enabled": True, "noTrigger": True, "excludedSites": [{"domain": SECRET}],
                     "opacity": 0.85, "name": "café"},
    "last": {"x": []},
}


def dms_text(doc):
    """What DMS writes: JSON.stringify(doc, null, 2)."""
    return json.dumps(doc, indent=2, ensure_ascii=False)


class PluginSettingsTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bg-media-ps-")
        self.addCleanup(shutil.rmtree, self.dir)
        self.settings = os.path.join(self.dir, "plugin_settings.json")
        self.copy = os.path.join(self.dir, "orig", "plugin-browserGlass.json")
        os.mkdir(os.path.dirname(self.copy))

    def write(self, text, mode=0o640):
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(self.settings, mode)

    def read(self):
        with open(self.settings, encoding="utf-8") as f:
            return f.read()

    def run_cmd(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            rc = ps.main(list(args))
        self.assertNotIn(SECRET, out.getvalue())
        return rc, out.getvalue()

    def save(self):
        rc, _ = self.run_cmd("save", self.settings, self.copy)
        self.assertEqual(rc, 0)
        self.assertEqual(stat.S_IMODE(os.stat(self.copy).st_mode), 0o600)

    def test_roundtrip_byte_identical(self):
        original = dms_text(DOC)
        self.write(original)
        self.save()
        changed = json.loads(original)
        changed["browserGlass"]["excludedSites"].append({"domain": "glass-demo.test"})
        changed["browserGlass"]["glassEnabled"] = False
        changed["otherPlugin"]["ratio"] = 2
        self.write(dms_text(changed))
        rc, _ = self.run_cmd("check", self.settings, self.copy)
        self.assertEqual(rc, 1)
        self.assertEqual(self.run_cmd("restore", "--dry-run", self.settings, self.copy)[0], 0)
        self.assertEqual(self.read(), dms_text(changed))  # dry run writes nothing
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        want = json.loads(dms_text(changed))
        want["browserGlass"] = DOC["browserGlass"]
        self.assertEqual(json.loads(self.read()), want)
        # Every other key keeps the bytes it had just before the restore
        self.assertEqual(self.read(), dms_text(want))
        self.assertEqual(stat.S_IMODE(os.stat(self.settings).st_mode), 0o640)
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 0)
        self.assertEqual(sorted(os.listdir(self.dir)), ["orig", "plugin_settings.json"])  # no tmp left

    def test_unchanged_is_not_written(self):
        self.write(dms_text(DOC))
        self.save()
        before = os.stat(self.settings)
        rc, out = self.run_cmd("restore", self.settings, self.copy)
        self.assertEqual(rc, 0)
        self.assertIn("unchanged", out)
        self.assertEqual(os.stat(self.settings).st_ino, before.st_ino)

    def test_absent_entry_removed_again(self):
        doc = {k: v for k, v in DOC.items() if k != "browserGlass"}
        for first in (True, False):
            with self.subTest(first=first):
                os.unlink(self.copy) if os.path.exists(self.copy) else None
                self.write(dms_text(doc))
                self.save()
                added = dict(doc)
                added["browserGlass"] = {"noTrigger": True}
                if first:
                    added = dict([("browserGlass", added.pop("browserGlass"))] + list(added.items()))
                self.write(dms_text(added))
                self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
                self.assertEqual(self.read(), dms_text(doc))

    def test_entry_put_back_when_deleted(self):
        self.write(dms_text(DOC))
        self.save()
        doc = {k: v for k, v in DOC.items() if k != "browserGlass"}
        self.write(dms_text(doc))
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        self.assertEqual(json.loads(self.read()), DOC)
        self.assertTrue(self.read().startswith(dms_text(doc)[:-2]))
        self.write("{}")
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        self.assertEqual(json.loads(self.read()), {"browserGlass": DOC["browserGlass"]})

    def test_compact_and_odd_text(self):
        self.write(json.dumps(DOC, separators=(",", ":")))
        self.save()
        self.write(json.dumps({"z": 1, "browserGlass": {"a": [1, 2]}, "y": {"k": "v"}}))
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        self.assertEqual(json.loads(self.read()), {"z": 1, "browserGlass": DOC["browserGlass"],
                                                   "y": {"k": "v"}})
        self.assertTrue(self.read().endswith(', "y": {"k": "v"}}'))

    def test_save_refuses_overwrite_and_bad_json(self):
        self.write(dms_text(DOC))
        self.save()
        self.assertEqual(self.run_cmd("save", self.settings, self.copy)[0], 1)
        os.unlink(self.copy)
        self.write('{"browserGlass": ')
        self.assertEqual(self.run_cmd("save", self.settings, self.copy)[0], 1)
        self.assertFalse(os.path.exists(self.copy))

    def test_missing_file(self):
        os.unlink(self.settings) if os.path.exists(self.settings) else None
        self.save()
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 0)
        self.write(dms_text(DOC))
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        self.assertEqual(json.loads(self.read()), {k: v for k, v in DOC.items() if k != "browserGlass"})

    def test_no_trigger_added_by_daemon_is_same(self):
        entry = {k: v for k, v in DOC["browserGlass"].items() if k != "noTrigger"}
        self.write(dms_text(dict(DOC, browserGlass=entry)))
        self.save()
        self.write(dms_text(DOC))  # the daemon saved noTrigger: true on start
        before = os.stat(self.settings).st_ino
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 0)
        rc, out = self.run_cmd("restore", self.settings, self.copy)
        self.assertEqual((rc, "unchanged" in out), (0, True))
        self.assertEqual(os.stat(self.settings).st_ino, before)
        self.write(dms_text(dict(DOC, browserGlass=dict(entry, noTrigger=False))))
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 1)

    def test_empty_excluded_sites_left_by_unblist_is_same(self):
        entry = {k: v for k, v in DOC["browserGlass"].items() if k != "excludedSites"}
        self.write(dms_text(dict(DOC, browserGlass=entry)))
        self.save()
        # blist then unblist: the daemon wrote excludedSites: []
        self.write(dms_text(dict(DOC, browserGlass=dict(entry, excludedSites=[]))))
        before = os.stat(self.settings).st_ino
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 0)
        rc, out = self.run_cmd("restore", self.settings, self.copy)
        self.assertEqual((rc, "unchanged" in out), (0, True))
        self.assertEqual(os.stat(self.settings).st_ino, before)
        self.write(dms_text(dict(DOC, browserGlass=dict(entry, excludedSites=[{"domain": "x.test"}]))))
        self.assertEqual(self.run_cmd("check", self.settings, self.copy)[0], 1)

    def test_leftover_tmp_does_not_block_restore(self):
        self.write(dms_text(DOC))
        self.save()
        self.write(dms_text(dict(DOC, browserGlass={"noTrigger": True})))
        with open(self.settings + ".bg-media.tmp", "w") as f:
            f.write("partial")
        self.assertEqual(self.run_cmd("restore", self.settings, self.copy)[0], 0)
        self.assertEqual(json.loads(self.read()), DOC)
        self.assertFalse(os.path.exists(self.settings + ".bg-media.tmp"))

    def test_excluded_answers_without_domains(self):
        self.write(dms_text(DOC))
        self.save()

        def answer(sites):
            entry = dict(DOC["browserGlass"], excludedSites=[{"domain": d} for d in sites])
            self.write(dms_text(dict(DOC, browserGlass=entry)))
            rc, out = self.run_cmd("excluded", self.settings, self.copy, "glass-demo.test")
            self.assertEqual(rc, 0)
            return out.strip()

        self.assertEqual(answer([SECRET]), "same")
        self.assertEqual(answer([SECRET, "glass-demo.test"]), "added")
        self.assertEqual(answer([SECRET, "other.example"]), "other")
        self.assertEqual(answer([SECRET, "glass-demo.test", "other.example"]), "other")
        self.assertEqual(answer([]), "other")


if __name__ == "__main__":
    unittest.main()

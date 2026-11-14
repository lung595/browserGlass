"""browserglass.py sites --json (P4): contract, embedded data, errors.

The command reads only the --data folder (default: the installed plugin's
data/ under $XDG_CONFIG_HOME), never the network, and writes nothing.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import contextlib
import io
import json
import shutil
import socket
import unittest

import test_contract
from fakehome import REPO, FakeHome, load_script

bg = load_script()
SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS
DATA = REPO / "data"
INSTALLED_DATA = ".config/dms/plugins/browserGlass/data"


class SitesCliTest(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def sites(self, *extra, code=0):
        before = self.fh.snapshot()
        proc = self.fh.run_script(["sites", "--json"] + [str(a) for a in extra])
        self.assertEqual(self.fh.snapshot(), before, "sites modified the fake home")
        self.assertEqual(proc.returncode, code, proc.stdout + proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        spec = SCHEMA["sites"] if code == 0 else SCHEMA["error"]
        self.assertEqual(test_contract.validate(doc, spec, DEFS), [], lines[0][:500])
        return doc

    def test_embedded_data(self):
        doc = self.sites("--data", DATA)
        self.assertEqual(doc, bg.sites_list(bg.sites_load(str(DATA))))
        names = [row["name"] for row in doc]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("example.com", names)

    def test_contract_fixture_shape(self):
        fixture = test_contract.load_json("sites.json")
        self.assertEqual(test_contract.validate(fixture, SCHEMA["sites"], DEFS), [])
        self.assertEqual(sorted(fixture[0]), ["domains", "name"])

    def test_default_data_folder(self):
        shutil.copytree(str(DATA), str(self.fh.resolve(INSTALLED_DATA)))
        self.assertEqual(self.sites(), self.sites("--data", DATA))

    def test_errors(self):
        self.assertIn("error", self.sites(code=1))
        self.sites("--data", self.fh.root / "missing", code=1)
        self.fh.write("data/styles.json", "[]")
        doc = self.sites("--data", self.fh.resolve("data"), code=1)
        self.assertIn("site styles unavailable", doc["error"])
        self.fh.write("data/styles.json", '{"website": {}}')
        self.assertEqual(self.sites("--data", self.fh.resolve("data")), [])

    def test_usage(self):
        proc = self.fh.run_script(["sites"])
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(test_contract.validate(json.loads(proc.stdout), SCHEMA["error"], DEFS), [])


class NoNetworkTest(unittest.TestCase):
    """status, report and sites run in-process with every socket refused."""

    def test_read_only_commands_open_no_socket(self):
        opened = []

        class Refused(socket.socket):
            def __init__(self, *args, **kwargs):
                opened.append(args)
                raise OSError("network refused by the test")

        with FakeHome() as fh:
            fh.make_profile(".zen", "a1b2c3d4.Default", prefs={"zen.view.grey-out-inactive-windows": True})
            fh.write_profiles_ini(".zen", [{"name": "Default", "path": "a1b2c3d4.Default", "default": True}])
            env = fh.env()
            real = socket.socket
            socket.socket = Refused
            try:
                for argv in (["sites", "--json", "--data", str(DATA)], ["status", "--json"], ["report"]):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        code = bg.main(argv, env)
                    self.assertEqual(code, 0, out.getvalue()[:300])
                    self.assertNotIn('"error"', out.getvalue()[:20])
            finally:
                socket.socket = real
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()

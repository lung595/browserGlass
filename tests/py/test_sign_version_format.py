"""tools/sign_companion.py version format: AMO refuses leading zeros, and the
version is recorded before the upload, so a local pass would burn it."""

import json
import unittest

from test_sign_companion import tool


def manifest(version):
    return json.dumps({"version": version, "browser_specific_settings":
                       {"gecko": {"id": "browserglass@companion"}}}).encode()


class VersionFormat(unittest.TestCase):
    def test_leading_zero_refused(self):
        for v in ("1.04", "01.2", "00", "1.2.03", "1.4\n"):
            with self.subTest(v=v), self.assertRaises(tool.ToolError):
                tool.parse_manifest(manifest(v), "x")

    def test_plain_versions_pass(self):
        for v in ("0", "1.4.1", "0.0.10", "1.2.3.4", "999999999"):
            with self.subTest(v=v):
                self.assertEqual(tool.parse_manifest(manifest(v), "x")[0], v)


if __name__ == "__main__":
    unittest.main()

"""The pre-paint OFF script must also reach hosts written with a final dot.

Firefox match patterns `*://*.example.org/*` do not match `example.org.`,
so an excluded site opened as https://example.org./ painted glass until
content.js switched it off.
"""
import json
import os
import re
import shutil
import subprocess
import unittest

BG = os.path.join(os.path.dirname(__file__), "..", "..", "extension", "background.js")


def patterns(domains):
    with open(BG, encoding="utf-8") as f:
        src = f.read()
    fn = re.search(r"^function patterns\(domains\) \{.*?^\}", src, re.S | re.M).group(0)
    js = fn + "\nprocess.stdout.write(JSON.stringify(patterns(" + json.dumps(domains) + ")));"
    return json.loads(subprocess.run(["node", "-e", js], stdout=subprocess.PIPE, check=True).stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PrePaintFinalDot(unittest.TestCase):
    def test_domain_gets_final_dot_pattern(self):
        self.assertEqual(patterns(["example.org"]),
                         ["*://*.example.org/*", "*://*.example.org./*"])

    def test_ip_unchanged(self):
        # An IP address never takes a final dot.
        self.assertEqual(patterns(["10.0.0.1"]), ["*://10.0.0.1/*"])


if __name__ == "__main__":
    unittest.main()

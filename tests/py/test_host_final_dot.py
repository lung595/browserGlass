"""A host written with a final dot (https://example.org./) is the same
site: exclusions, the live inclusion and the per-site blocks must match it.

Run: python3 -B -m unittest discover -s tests/py -p test_host_final_dot.py
"""

import re
import unittest

from fakehome import FIXTURES, load_script

bg = load_script()


def rx(tail):
    return re.compile(bg.css_unescape("https?://" + tail))


class FinalDotTest(unittest.TestCase):

    def test_exclusion(self):
        excl = rx(bg.exclusion_lookahead(["example.org"]) + ".*")
        for url in ("https://example.org/", "https://example.org./", "https://a.example.org.:443/"):
            self.assertFalse(excl.fullmatch(url), url)
        self.assertTrue(excl.fullmatch("https://example.org.evil/"))

    def test_inclusion(self):
        incl = rx(bg.inclusion_lookahead(["example.org"]) + ".*")
        for url in ("https://example.org./", "https://a.example.org.:443/x"):
            self.assertTrue(incl.fullmatch(url), url)
        self.assertFalse(incl.fullmatch("https://example.org.evil/"))

    def test_site_blocks(self):
        sites = bg.sites_load(str(FIXTURES / "sites"))
        rows = [(comment, rx(tail)) for comment, tail, _ in bg._sites_blocks(sites)]
        generic = [r for c, r in rows if c == bg.SITES_GENERIC_COMMENT]
        self.assertTrue(generic)
        for comment, block in rows:
            if comment == bg.SITES_GENERIC_COMMENT:
                continue
            with self.subTest(block=comment):
                hosts = [h for h in self._hosts(block) if block.fullmatch("https://%s/" % h)]
                self.assertTrue(hosts, "no plain host matches")
                for host in hosts:
                    self.assertTrue(block.fullmatch("https://%s./x" % host), host)
                    # The generic style must not also apply there.
                    self.assertFalse(generic[0].fullmatch("https://%s./x" % host), host)

    @staticmethod
    def _hosts(block):
        # Hosts named in the block's regexp, read back from its text (a "-"
        # style takes any last label, hence the ".com" variant).
        text = block.pattern.replace("\\.", ".")
        names = re.findall(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*", text)
        return set(names) | {n + ".com" for n in names}


if __name__ == "__main__":
    unittest.main()

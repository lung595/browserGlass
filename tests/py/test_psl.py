"""psl: parsing the embedded Public Suffix List, the standard registrable
domain algorithm (the official cases of the PSL repository's
tests/test_psl.txt, copied as tests/py/fixtures/psl/test_psl.txt) and
registrable_domain(), the domain the launcher excludes.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import os
import re
import shutil
import tempfile
import unittest

from fakehome import FIXTURES, REPO, load_script

bg = load_script()

DATA = REPO / "data"
CASE = re.compile(r"checkPublicSuffix\((null|'[^']*'), (null|'[^']*')\);")

# A small list in the upstream format: both sections, a wildcard with an
# exception, an IDN rule and a PRIVATE rule.
SMALL = """// header comment
// ===BEGIN ICANN DOMAINS===
com
uk
co.uk
// a comment line between rules
*.ck
!www.ck
公司.cn
cn
jp   trailing words are ignored
// ===END ICANN DOMAINS===
// ===BEGIN PRIVATE DOMAINS===
github.io
// ===END PRIVATE DOMAINS===
"""


def official_cases():
    """[(input or None, expected or None)] of the official fixture; the
    commented-out cases ("//checkPublicSuffix") are skipped like upstream."""
    out = []
    text = (FIXTURES / "psl" / "test_psl.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        match = CASE.match(line.strip())
        if match:
            out.append(tuple(None if v == "null" else v[1:-1] for v in match.groups()))
    return out


class PslParseTest(unittest.TestCase):

    def test_small_list(self):
        psl = bg.psl_parse(SMALL)
        self.assertEqual(psl.rules, {"com", "uk", "co.uk", "xn--55qx5d.cn", "cn", "jp",
                                     "github.io"})
        self.assertEqual(psl.wildcards, {"ck"})
        self.assertEqual(psl.exceptions, {"www.ck"})

    def test_bad_rules_skipped(self):
        psl = bg.psl_parse("com\nhttps://x.com/\n.org\na..b\n*.\n!\nfoo_bar.net\n")
        self.assertEqual(psl.rules, {"com"})
        self.assertFalse(psl.wildcards or psl.exceptions)

    def test_embedded_list(self):
        psl = bg.psl_load(str(DATA))
        # ICANN and PRIVATE sections, wildcard, exception, IDN as Punycode
        for rule in ("com", "co.uk", "github.io", "xn--55qx5d.cn"):
            self.assertIn(rule, psl.rules)
        self.assertIn("ck", psl.wildcards)
        self.assertIn("www.ck", psl.exceptions)
        self.assertGreater(len(psl.rules), 5000)
        for rule in psl.rules | psl.wildcards | psl.exceptions:
            self.assertTrue(rule.isascii(), rule)
        # Parsed once per path
        self.assertIs(bg.psl_load(str(DATA)), psl)


class PslLoadErrorsTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bg-psl-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.path = os.path.join(self.tmp, bg.PSL_FILE)

    def write(self, data):
        with open(self.path, "wb") as f:
            f.write(data)

    def assert_error(self, needle):
        with self.assertRaises(bg.PslError) as ctx:
            bg.psl_load(self.tmp)
        self.assertIn(bg.PSL_FILE, str(ctx.exception))
        self.assertIn(needle, str(ctx.exception))
        # A ValueError: callers catching ValueError turn it into a warning
        self.assertIsInstance(ctx.exception, ValueError)

    def test_missing(self):
        self.assert_error("No such file")

    def test_not_utf8(self):
        self.write(b"com\n\xff\xfe\n" * 2000)
        self.assert_error("not UTF-8")

    def test_too_few_rules(self):
        self.write(SMALL.encode("utf-8"))
        self.assert_error("corrupt")

    def test_no_com_rule(self):
        self.write("".join("r%d.example\n" % i for i in range(2000)).encode("utf-8"))
        self.assert_error("corrupt")

    def test_not_a_regular_file(self):
        os.mkdir(self.path)
        with self.assertRaises(bg.PslError):
            bg.psl_load(self.tmp)

    def test_reloaded_when_changed(self):
        shutil.copyfile(str(DATA / bg.PSL_FILE), self.path)
        first = bg.psl_load(self.tmp)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("zz-added-rule.example\n")
        os.utime(self.path, ns=(1, 1))
        second = bg.psl_load(self.tmp)
        self.assertIsNot(first, second)
        self.assertIn("zz-added-rule.example", second.rules)


class OfficialCasesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.psl = bg.psl_load(str(DATA))
        cls.cases = official_cases()

    def ascii(self, name):
        return None if name is None else bg.normalize_domain(name)

    def test_fixture_read(self):
        self.assertEqual(len(self.cases), 78)

    def test_standard_algorithm(self):
        # psl_registrable follows the standard exactly: None for a public
        # suffix; invalid inputs (null, leading dot) are refused upstream by
        # registrable_domain, so they are checked there.
        for host, expected in self.cases:
            if host is None or host.startswith("."):
                continue
            with self.subTest(host=host):
                got = bg.psl_registrable(bg.normalize_domain(host), self.psl)
                self.assertEqual(got, self.ascii(expected))

    def test_registrable_domain(self):
        # Same cases through registrable_domain(): a bare public suffix gives
        # the host itself, an invalid input None.
        for host, expected in self.cases:
            with self.subTest(host=host):
                got = bg.registrable_domain(host, self.psl)
                if host is None or host.startswith("."):
                    self.assertIsNone(got)
                elif expected is None:
                    self.assertEqual(got, bg.normalize_domain(host))
                else:
                    self.assertEqual(got, self.ascii(expected))


class RegistrableDomainTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.psl = bg.psl_load(str(DATA))

    def check(self, host, expected):
        self.assertEqual(bg.registrable_domain(host, self.psl), expected, host)

    def test_plan_cases(self):
        self.check("account.proton.me", "proton.me")
        self.check("a.b.co.uk", "b.co.uk")
        self.check("foo.bar.co.uk", "bar.co.uk")
        self.check("user.github.io", "user.github.io")
        self.check("www.user.github.io", "user.github.io")

    def test_bare_suffix_is_kept_whole(self):
        # never "every site under a public suffix"
        for host in ("co.uk", "github.io", "com", "uk", "ck"):
            self.check(host, host)

    def test_wildcard_and_exception(self):
        self.check("a.b.test.ck", "b.test.ck")
        self.check("test.ck", "test.ck")       # public suffix (*.ck): kept whole
        self.check("www.ck", "www.ck")          # exception: registrable
        self.check("a.www.ck", "www.ck")

    def test_idn(self):
        self.check("www.食狮.公司.cn", "xn--85x722f.xn--55qx5d.cn")
        self.check("www.xn--85x722f.xn--55qx5d.cn", "xn--85x722f.xn--55qx5d.cn")
        self.check("WWW.Faß.DE", "xn--fa-hia.de")   # U+00DF kept, as normalize_domain

    def test_case_trailing_dot_and_port(self):
        self.check("WwW.Example.COM", "example.com")
        self.check("www.example.com.", "example.com")
        self.check("www.example.com:8443", "example.com")
        self.check("www.example.com.:8443", "example.com")
        self.check("  www.example.com  ", "example.com")

    def test_ip_and_localhost(self):
        self.check("127.0.0.1", "127.0.0.1")
        self.check("192.168.1.20:8080", "192.168.1.20")
        self.check("localhost", "localhost")
        self.check("localhost.", "localhost")
        self.check("LOCALHOST:3000", "localhost")

    def test_unsupported(self):
        # None: the caller's "unsupported"
        for host in ("[::1]", "[::1]:8080", "::1", "fe80::1", "2001:db8::1",
                     ".example.com", "example..com", "exa_mple.com", "", "   ",
                     "*.com", "*.co.uk", "a.*.example.com",
                     # full-width forms NFKC folds into "*", "." and ":"
                     "\uff0a.com", "\uff0a.co.uk", "\uff0eexample.com",
                     "\u3002example.com", "a\uff1a\uff1a1",
                     "example.com\uff1a\uff1a1",
                     None, 42, b"example.com"):
            self.check(host, None)


if __name__ == "__main__":
    unittest.main()

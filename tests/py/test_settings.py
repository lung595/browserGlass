"""settings: --settings JSON -> complete normalised settings (defaults,
coercion, clamping, domain lists, v0 migration).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import json
import unittest

from fakehome import REPO, load_script

bg = load_script()
CONTRACT = REPO / "tests" / "fixtures" / "contract"


def parse(doc):
    return bg.settings_from_json(json.dumps(doc))


class DefaultsTest(unittest.TestCase):

    def test_empty_gives_contract_defaults(self):
        expected = json.loads((CONTRACT / "settings-default.json").read_text(encoding="utf-8"))
        for value in ("", "{}", "null", b"{}", {}, None):
            self.assertEqual(dict(bg.settings_from_json(value)), expected, repr(value))

    def test_keys_complete_and_ordered(self):
        out = parse({"zzz": 1, "opacity": 0.5})
        self.assertEqual(list(out), list(bg.SETTINGS_DEFAULTS))
        self.assertNotIn("zzz", out)

    def test_schema_defaults(self):
        schema = json.loads((CONTRACT / "schema.json").read_text(encoding="utf-8"))
        out = bg.settings_from_json("{}")
        for key, spec in schema["settings"]["fields"].items():
            self.assertEqual(out[key], spec["default"], key)

    def test_rejects_non_objects(self):
        for bad in ("[1]", "42", '"x"', "{", "nope", "[" * 100000):
            with self.assertRaises(ValueError, msg=bad[:20]):
                bg.settings_from_json(bad)

    def test_full_round_trip(self):
        doc = {"blur": False, "isLight": True, "glassEnabled": False, "opacityOverride": True,
               "opacity": 0.4, "siteTheme": "none", "pagesTransparent": False,
               "genericStyle": False, "excluded": ["a.org"], "disabledStyles": ["-google.com"],
               "newTabGlass": False, "readerOpaque": False, "privateGlass": False}
        self.assertEqual(dict(parse(doc)), doc)


class CoercionTest(unittest.TestCase):

    def test_booleans(self):
        for raw, expected in ((True, True), (False, False), (1, True), (0, False),
                              ("true", True), ("False", False), (" yes ", True), ("off", False),
                              ("1", True), ("0", False)):
            self.assertIs(parse({"blur": raw})["blur"], expected, repr(raw))
            self.assertIs(parse({"isLight": raw})["isLight"], expected, repr(raw))
        for raw in ("maybe", 2, -1, 0.5, None, [], {}):
            self.assertIs(parse({"blur": raw})["blur"], True, repr(raw))
            self.assertIs(parse({"isLight": raw})["isLight"], False, repr(raw))

    def test_opacity(self):
        for raw, expected in ((0.5, 0.5), (0, 0.0), (1, 1.0), (85, 0.85), (100, 1.0),
                              (250, 1.0), (-3, 0.0), ("0.7", 0.7), ("60", 0.6), (1.5, 1.0), (1.01, 1.0),
                              (99.5, 1.0), ("100", 1.0)):
            self.assertAlmostEqual(parse({"opacity": raw})["opacity"], expected, msg=repr(raw))
        for raw in (True, "abc", None, [], {}, "nan", "inf"):
            self.assertEqual(parse({"opacity": raw})["opacity"], 0.85, repr(raw))
        self.assertEqual(bg.settings_from_json('{"opacity": NaN}')["opacity"], 0.85)
        self.assertEqual(bg.settings_from_json('{"opacity": Infinity}')["opacity"], 0.85)
        self.assertEqual(bg.settings_from_json('{"opacity": 1e400}')["opacity"], 0.85)
        self.assertEqual(parse({"opacity": 10 ** 400})["opacity"], 0.85)
        self.assertEqual(parse({"opacity": "9" * 400})["opacity"], 0.85)

    def test_site_theme(self):
        for raw, expected in (("dark", "dark"), (" None ", "none"), ("FOLLOW", "follow"),
                              ("light", "follow"), (1, "follow"), (None, "follow")):
            self.assertEqual(parse({"siteTheme": raw})["siteTheme"], expected, repr(raw))


class DomainListTest(unittest.TestCase):

    def test_normalize_domain(self):
        cases = {
            "example.org": "example.org",
            "  Example.ORG  ": "example.org",
            "https://www.example.org/path?q=1#x": "www.example.org",
            "http://user:pw@sub.example.org:8080/": "sub.example.org",
            "*.example.org": "example.org",
            "example.org.": "example.org",
            ".example.org": "example.org",
            "my-site.net": "my-site.net",
            "www.example.org": "www.example.org",
            "www.com": "www.com",
            "www.gov.uk": "www.gov.uk",
            "fa\u00df.de": "xn--fa-hia.de",
            "FA\u1e9e.de": "xn--fa-hia.de",
            "\u03c3\u03bf\u03c6\u03bf\u03c2.gr": "xn--0xaajbq.gr",
            "example\u3002org": "example.org",
            "\uff25xample.org": "example.org",
            "b\u00fccher.example": "xn--bcher-kva.example",
            "localhost": "localhost",
            "127.0.0.1": "127.0.0.1",
        }
        for raw, expected in cases.items():
            self.assertEqual(bg.normalize_domain(raw), expected, raw)
        for bad in ("", "   ", "a..b", "a b.c", "exa_mple.org", "[::1]", "https://[::1]/",
                    "*", "x" * 64 + ".org", "a.%s" % ("b" * 250), None, 5, "a\x00b.org", "\u2603." * 60):
            self.assertIsNone(bg.normalize_domain(bad), repr(bad))

    def test_excluded_list(self):
        out = parse({"excluded": ["A.org", "https://a.org/x", "bad domain", 7, {"domain": "b.org"},
                                  "www.c.org", "c.org"]})
        self.assertEqual(out["excluded"], ["a.org", "b.org", "www.c.org", "c.org"])

    def test_excluded_string(self):
        self.assertEqual(parse({"excluded": "a.org, b.org  c.org,,"})["excluded"],
                         ["a.org", "b.org", "c.org"])
        self.assertEqual(parse({"excluded": 5})["excluded"], [])

    def test_disabled_styles(self):
        out = parse({"disabledStyles": ["GitHub.com.css", "+wikipedia.org", "-google.com",
                                        " x.org ", "github.com", "bad name", "-", "", 3,
                                        {"name": "y.org"}]})
        self.assertEqual(out["disabledStyles"], ["github.com", "+wikipedia.org", "-google.com",
                                                 "x.org", "y.org"])

    def test_outputs_match_contract_patterns(self):
        import re
        out = parse({"excluded": ["https://\u00e9t\u00e9.example/", "a-b.org"],
                     "disabledStyles": ["+A.b"]})
        for domain in out["excluded"]:
            self.assertTrue(re.search(r"^[A-Za-z0-9.-]+$", domain), domain)
        for name in out["disabledStyles"]:
            self.assertTrue(re.search(r"^[+-]?[a-z0-9][a-z0-9.-]*$", name), name)


class MigrationTest(unittest.TestCase):
    """v0 pluginData keys (H4)."""

    def test_excluded_sites(self):
        out = parse({bg.V0_SETTING_EXCLUDED: [{"domain": "Old.org"}, {"domain": "x.net"},
                                              {"nodomain": 1}, "plain.org"]})
        self.assertEqual(out["excluded"], ["old.org", "x.net", "plain.org"])

    def test_merged_after_excluded(self):
        out = parse({"excluded": ["new.org", "x.net"],
                     bg.V0_SETTING_EXCLUDED: [{"domain": "x.net"}, {"domain": "old.org"}]})
        self.assertEqual(out["excluded"], ["new.org", "x.net", "old.org"])

    def test_pages_transparent_kept(self):
        self.assertIs(parse({bg.V0_SETTING_PAGES: False})["pagesTransparent"], False)
        self.assertIs(parse({bg.V0_SETTING_PAGES: True})["pagesTransparent"], True)


if __name__ == "__main__":
    unittest.main()

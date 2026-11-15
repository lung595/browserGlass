"""sites: loading the embedded my-internet styles, building the userContent
CSS (port of v0 `browser-glass-sites build`), validating CSS, listing the
dedicated styles; parity with v0 on the embedded data.

Run: python3 -B -m unittest discover -s tests/py -v

Golden files (regenerate with BG_REGEN_GOLDEN=1, then review the diff):
  - tests/py/golden/sites-build.txt, sites-list.txt: build and list of the
    small fixture tests/py/fixtures/sites/ for a few settings;
  - tests/py/golden/v0-sites-build.css.gz: the output of v0
    `browser-glass-sites build CACHE "example.org,www.my-site.net"` on data/
    (PYTHONHASHSEED=0, gzip mtime 0). It is regenerated only when the v0
    script is available: $BG_V0_DIR/browser-glass-sites, else the repo's
    browser-glass-sites while it still exists. The v0 script always runs
    under a FakeHome, on a copy of data/ in the fake cache.

Documented differences with v0 (normalised away by v0_normalize()):
  1. v0 re.escape()d the domains, which escapes "-": in the Unicode-mode
     regexps Firefox compiles for @-moz-document regexp(), "\\-" is a syntax
     error, and an invalid regexp() applies the block to EVERY page
     (measured on Firefox 160). v1 escapes only ".".
  2. The upstream key "bestbuy.com .css" is normalised to "bestbuy.com.css"
     (v0's "bestbuy\\.com\\ " could never match a host).
  3. The mapping target "-cifraclub.com.br" is dropped (no host starts with
     "-").
  4. v0 ordered equal-length alternatives by set() iteration order (it
     depends on PYTHONHASHSEED); v1 orders them by name. Alternatives inside
     each (?:a|b) group are sorted on both sides before comparing.
  5. The two French comments of v0 are in English.
  6. data/styles.json is the upstream file minus the keys whose name hits
     the project's denylist (see test_leaks.py); v0 runs on the same
     filtered data, so nothing is normalised here. tools/update_styles.py
     (P8) must apply the same filter.
  7. Every style (generic and dedicated) is gated on the colour scheme: as
     is under a light theme, only on pages declaring a dark version under a
     dark one (bg._scheme_gated), so light-only pages stay legible.
  8. browserGlass's own site css (data/sites/) ends its style's blocks.
  9. The generic style loses its "background: none" line: background images
     (a photo behind a <section>) stay, background colours still go.

Exclusions keep "www." as entered, like v0: "www.x" refuses www.x and its
subdomains, not x (the parity golden uses such an exclusion).
"""

import collections
import gzip
import json
import os
import re
import pathlib
import shutil
import tempfile
import unittest

from fakehome import FIXTURES, GOLDEN, REGEN_GOLDEN, REPO, FakeHome, check_golden, load_script

bg = load_script()

DATA = REPO / "data"
FIXTURE = FIXTURES / "sites"
V0_GOLDEN = GOLDEN / "v0-sites-build.css.gz"
V0_EXCLUSIONS = "example.org,www.my-site.net"
BLOCK = re.compile(r'/\* (?P<comment>.*?) \*/\n@-moz-document regexp\("(?P<rx>[^"]*)"\) \{\n')


def blocks(css):
    """[(comment, compiled pattern)] of the @-moz-document regexp() blocks."""
    return [(m.group("comment"), re.compile(bg.css_unescape(m.group("rx"))))
            for m in BLOCK.finditer(css)]


def matching(css, url):
    """Comments of the blocks whose regexp matches `url` (whole-URL match, as
    Firefox does)."""
    return [comment for comment, rx in blocks(css) if rx.fullmatch(url)]


def v0_script():
    """Path of the v0 browser-glass-sites script, or None."""
    folder = os.environ.get("BG_V0_DIR")
    path = os.path.join(folder, "browser-glass-sites") if folder else str(REPO / "browser-glass-sites")
    return path if os.path.isfile(path) else None


def run_v0_build(script, data_dir, exclusions):
    """stdout of v0 `browser-glass-sites build` run under a FakeHome, on a
    copy of `data_dir` in the fake v0 cache folder, with PYTHONHASHSEED=0
    so the output is reproducible."""
    import subprocess
    import sys
    with FakeHome() as fh:
        cache = fh.cache / "dms" / "browserGlass"
        cache.mkdir(parents=True)
        for name in ("styles.json", "css-mapping.json"):
            shutil.copyfile(str(data_dir / name), str(cache / name))
        proc = subprocess.run(
            # Not -I: it implies -E, which would ignore PYTHONHASHSEED (v0's
            # output order depends on it). -s and the FakeHome environment
            # keep the user's site-packages and PYTHON* variables out.
            [sys.executable, "-s", script, "build", str(cache), exclusions],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(fh.home),
            env=fh.env({"PYTHONHASHSEED": "0"}), timeout=120)
        if proc.returncode != 0:
            raise AssertionError("v0 build failed: %s" % proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8")


_GROUP = re.compile(r"\(\?:([^()]*\|[^()]*)\)")


def sort_alternatives(css):
    return _GROUP.sub(lambda m: "(?:%s)" % "|".join(sorted(m.group(1).split("|"))), css)


def v0_normalize(css):
    """v0 output with the documented differences applied (see the module doc)."""
    css = css.replace("\\\\-", "-")
    css = css.replace(bg.V0_SITES_HEADER, bg.SITES_HEADER)
    css = css.replace(bg.V0_SITES_GENERIC_COMMENT, bg.SITES_GENERIC_COMMENT)
    css = css.replace("/* bestbuy.com .css */", "/* bestbuy.com.css */")
    css = css.replace("bestbuy\\\\.com\\\\ ", "bestbuy\\\\.com")
    css = css.replace("|-cifraclub\\\\.com\\\\.br", "").replace("-cifraclub\\\\.com\\\\.br|", "")
    # v1 ends a style's blocks with its data/sites/ file.
    for key, fix in bg._sites_own(str(DATA)):
        parts = css.split("/* %s" % key)
        for i in range(1, len(parts)):
            block = parts[i].split("\n\n/* ", 1)[0].rstrip("\n")
            end = block.rindex("\n}")
            parts[i] = parts[i][:end] + "\n" + fix + parts[i][end:]
        css = ("/* %s" % key).join(parts)
    # v1's generic style keeps background images (no "background: none"),
    # in all its blocks: example.com's own, the mapping, the other sites.
    parts = css.split("\n\n/* ")
    for i, part in enumerate(parts):
        if ("/* " + part).startswith((bg.SITES_GENERIC_COMMENT, "/* %s */" % bg.SITES_GENERIC_KEY,
                                   "/* %s (mapping)" % bg.SITES_GENERIC_KEY)):
            head, sep, rest = part.partition("\n")
            parts[i] = head + sep + bg._GENERIC_NO_BACKGROUND.sub("", rest)
    css = "\n\n/* ".join(parts)
    # v1 gates every style on the colour scheme (bg._scheme_gated).
    pieces = []
    for piece in css.split("\n\n/* "):
        if pieces and not BLOCK.match("/* " + piece):
            pieces[-1] += "\n\n/* " + piece  # a comment inside a style
        else:
            pieces.append(piece)
    for i in range(1, len(pieces)):
        start = BLOCK.match("/* " + pieces[i]).end() - 3
        body = pieces[i][start:]
        trail = body[len(body.rstrip("\n")):]
        body = body.rstrip("\n")
        assert body.endswith("\n}"), body[-50:]
        shadow = not ("/* " + pieces[i]).startswith(bg.SITES_GENERIC_COMMENT)
        pieces[i] = pieces[i][:start] + bg._scheme_gated(body[:-2], None, shadow) + "\n}" + trail
    return sort_alternatives("\n\n/* ".join(pieces))


def own_new_keys():
    """data/sites/ keys that are new styles (no my-internet style of that name)."""
    upstream = bg.sites_load(str(DATA)).styles
    return {key for key, _ in bg._sites_own(str(DATA))
            if list(upstream[key]) == [bg.SITES_OWN_FEATURE]}


def v0_golden():
    if REGEN_GOLDEN:
        script = v0_script()
        if script:
            text = run_v0_build(script, DATA, V0_EXCLUSIONS)
            GOLDEN.mkdir(parents=True, exist_ok=True)
            V0_GOLDEN.write_bytes(gzip.compress(text.encode("utf-8"), 9, mtime=0))
    if not V0_GOLDEN.exists():
        raise unittest.SkipTest("no v0 golden and no v0 script")
    return gzip.decompress(V0_GOLDEN.read_bytes()).decode("utf-8")


def fixture_sites():
    return bg.sites_load(str(FIXTURE))


class LoadTest(unittest.TestCase):

    def test_fixture_keys(self):
        sites = fixture_sites()
        keys = list(sites.styles)
        self.assertIn("spaced.test.css", keys)
        self.assertIn("upper.test.css", keys)
        self.assertNotIn("spaced.test .css", keys)
        self.assertFalse(any("!" in k for k in keys))
        self.assertEqual(keys.count("dup.test.css"), 1)
        # The untouched key wins over the normalised one.
        self.assertIn(".dup {", sites.styles["dup.test.css"]["Transparency"])
        # Non-string features are dropped.
        self.assertEqual(list(sites.styles["numbers.test.css"]), ["Glass"])
        # styles.json's own "mapping" key is not used (v0 reads css-mapping.json).
        self.assertNotIn("ignored.css", sites.mapping)

    def test_fixture_mapping(self):
        mapping = fixture_sites().mapping
        self.assertEqual(mapping["a.test.css"], ["a-mirror.test", "sub.a.test"])
        self.assertEqual(mapping["example.com.css"], ["generic-host.test", "www.generic-host.test"])

    def test_missing_mapping(self):
        with FakeHome() as fh:
            fh.write("d/styles.json", '{"website": {"x.test.css": {"glass": "a { b: c }"}}}')
            sites = bg.sites_load(str(fh.home / "d"))
            self.assertEqual(dict(sites.mapping), {})
            fh.write("d/css-mapping.json", "{corrupt")
            self.assertEqual(dict(bg.sites_load(str(fh.home / "d")).mapping), {})

    def test_bad_styles(self):
        with FakeHome() as fh:
            with self.assertRaises(OSError):
                bg.sites_load(str(fh.home / "nowhere"))
            for text in ("{bad", "[]", '{"website": []}', "{}"):
                fh.write("d/styles.json", text)
                with self.assertRaises(ValueError, msg=text):
                    bg.sites_load(str(fh.home / "d"))

    def test_embedded_data(self):
        sites = bg.sites_load(str(DATA))
        self.assertGreater(len(sites.styles), 600)
        self.assertIn("bestbuy.com.css", sites.styles)
        self.assertNotIn("bestbuy.com .css", sites.styles)
        for key in sites.styles:
            self.assertTrue(re.search(r"^[+-]?[a-z0-9][a-z0-9.-]*$", key[:-4]), key)
        targets = [t for hosts in sites.mapping.values() for t in hosts]
        self.assertNotIn("-cifraclub.com.br", targets)
        for target in targets:
            self.assertTrue(re.search(r"^(\*\.)?[a-z0-9][a-z0-9.-]*(\.\*)?$", target), target)


class BuildTest(unittest.TestCase):

    CASES = collections.OrderedDict([
        ("default", {}),
        ("excluded", {"excluded": ["example.org", "my-site.net", "https://www.b.test/"]}),
        ("disabled", {"disabled": ["a.test", "-goo.test", "example.com"]}),
        ("generic-off", {"generic": False}),
        ("excluded-disabled-generic-off", {"excluded": ["a.test"], "disabled": ["gist.a.test"],
                                           "generic": False}),
    ])

    def build(self, problems=None, **kwargs):
        return bg.sites_build_css(fixture_sites(), problems=problems, **kwargs)

    def test_golden(self):
        # "<case> gated": the same build gated for liveControl (the plain
        # cases are the v1.0 output).
        results = collections.OrderedDict(
            (name, self.build(**kwargs)) for name, kwargs in self.CASES.items())
        results.update(("%s gated" % name, self.build(gate=bg.GATE_NORMAL_ROOT, **kwargs))
                       for name, kwargs in self.CASES.items())
        check_golden(self, "sites-build.txt", results)

    def test_matching(self):
        css = self.build()
        expect = {
            "https://a.test/": ["a.test.css"],
            "http://www.a.test:8080/x": ["a.test.css"],
            "https://deep.sub.a.test/": ["a.test.css"],
            "https://gist.a.test/": ["gist.a.test.css"],
            "https://x.gist.a.test/y": ["gist.a.test.css"],
            "https://b.test": ["+b.test.css"],
            "https://c.test/": ["www.c.test.css"],
            "https://www.c.test/": ["www.c.test.css"],
            "https://goo.fr/": ["-goo.test.css"],
            "https://www.goo.com/search": ["-goo.test.css"],
            "https://shop.co.jp/": ["-shop.co.uk.css"],
            "https://my-site.net/": ["my-site.net.css"],
            "https://a-mirror.test/": ["a.test.css (mapping)"],
            "https://www.a-mirror.test/": ["a.test.css (mapping)"],
            "https://b-alt.test/": ["+b.test.css (mapping)"],
            "https://generic-host.test/": ["example.com.css (mapping)"],
            "https://spaced.test/": ["spaced.test.css"],
            "https://upper.test/": ["upper.test.css"],
            "https://unknown.test/": ["Other sites: generic style (example.com.css)"],
            "https://a.test.evil.test/": ["Other sites: generic style (example.com.css)"],
            "https://nofeat.test/": ["Other sites: generic style (example.com.css)"],
            "https://nofeat-alt.test/": ["Other sites: generic style (example.com.css)"],
            # A broken style claims its domain but emits nothing.
            "https://broken.test/": [],
            "https://imports.test/": [],
            "https://example.com/": ["example.com.css"],
        }
        for url, comments in expect.items():
            self.assertEqual(matching(css, url), comments, url)

    def test_feature_filter(self):
        css = self.build()
        self.assertIn(".b-side", css)
        self.assertIn(".b-head", css)
        self.assertNotIn("footer", css)
        self.assertNotIn(".cookie", css)
        self.assertNotIn(".a-plus", css)
        self.assertNotIn(".dup-spaced", css)

    def test_problems(self):
        problems = []
        self.build(problems=problems)
        self.assertTrue(any(p.startswith("broken.test.css: ") for p in problems), problems)
        self.assertTrue(any(p.startswith("imports.test.css: ") and "@import" in p
                            for p in problems), problems)
        self.assertEqual(len([p for p in problems if not p.startswith(("broken", "imports"))]), 0)

    def test_excluded(self):
        css = self.build(excluded=["a.test", "my-site.net"])
        for url in ("https://a.test/", "https://gist.a.test/", "https://www.a.test/",
                    "https://my-site.net/x", "https://sub.my-site.net"):
            self.assertEqual(matching(css, url), [], url)
        self.assertEqual(matching(css, "https://b.test/"), ["+b.test.css"])
        self.assertEqual(matching(css, "https://unknown.test/"),
                         ["Other sites: generic style (example.com.css)"])

    def test_www_exclusion_kept(self):
        css = self.build(excluded=["www.b.test", "www.test"])
        self.assertEqual(matching(css, "https://www.b.test/"), [])
        self.assertEqual(matching(css, "https://x.www.b.test/"), [])
        self.assertEqual(matching(css, "https://b.test/"), ["+b.test.css"])
        self.assertIn("www\\\\.test", bg.exclusion_lookahead(["www.test"]))
        self.assertEqual(matching(css, "https://unknown.test/"),
                         ["Other sites: generic style (example.com.css)"])

    def test_disabled_keeps_domain_known(self):
        css = self.build(disabled=["a.test", "-goo.test"])
        self.assertEqual(matching(css, "https://a.test/"), [])
        self.assertEqual(matching(css, "https://goo.fr/"), [])
        self.assertEqual(matching(css, "https://gist.a.test/"), ["gist.a.test.css"])
        self.assertEqual(matching(css, "https://a-mirror.test/"), [])

    def test_generic_off(self):
        css = self.build(generic=False)
        for url in ("https://unknown.test/", "https://generic-host.test/", "https://example.com/"):
            self.assertEqual(matching(css, url), [], url)
        self.assertNotIn("example.com.css", css)
        self.assertEqual(matching(css, "https://a.test/"), ["a.test.css"])

    def test_generic_keeps_images(self):
        # the generic style drops background colours, not background images
        # (a photo behind a <section>); a dedicated style is left as it is
        rule = "section {\n  background-color: transparent !important;\n  background: none !important;\n}"
        sites = bg.Sites({"example.com.css": {"transparency": rule}, "a.test.css": {"glass": rule}}, {})
        css = bg.sites_build_css(sites)
        generic = css[css.index(bg.SITES_GENERIC_COMMENT):]
        self.assertIn("background-color: transparent !important;", generic)
        self.assertNotIn("background: none", generic)
        self.assertIn("background: none !important;", css[:css.index(bg.SITES_GENERIC_COMMENT)])

    def test_empty(self):
        self.assertEqual(bg.sites_build_css(bg.Sites({}, {})), "")
        sites = bg.Sites({"example.com.css": {"glass": "a { b: c }"}}, {})
        self.assertEqual(bg.sites_build_css(sites, generic=False), "")
        self.assertIn("Other sites", bg.sites_build_css(sites))

    def test_regexps_valid(self):
        for name, kwargs in self.CASES.items():
            css = self.build(**kwargs)
            self.assertEqual(bg.sites_validate(css), [], name)
            for comment, rx in blocks(css):
                self.assertIsNone(bg.js_regexp_problem(rx.pattern), comment)


class ListTest(unittest.TestCase):

    def test_golden(self):
        rows = bg.sites_list(fixture_sites())
        check_golden(self, "sites-list.txt", {"fixture": json.dumps(rows, indent=1) + "\n"})

    def test_fixture(self):
        rows = {row["name"]: row["domains"] for row in bg.sites_list(fixture_sites())}
        # sub.a.test is already covered by a.test: dropped, as in v0.
        self.assertEqual(rows["a.test"], ["a.test", "*.a.test", "a-mirror.test"])
        self.assertEqual(rows["+b.test"], ["b.test", "*.b.test", "b-alt.test"])
        self.assertEqual(rows["www.c.test"], ["c.test", "*.c.test"])
        self.assertEqual(rows["-goo.test"], ["goo.*", "www.goo.*"])
        self.assertEqual(rows["-shop.co.uk"], ["shop.co.*", "www.shop.co.*"])
        for absent in ("+a.test", "example.com", "nofeat.test", "dup.test .css"):
            self.assertNotIn(absent, rows)

    def test_contract_shape(self):
        site_name = re.compile(r"^[+-]?[a-z0-9][a-z0-9.-]*$")
        site_domain = re.compile(r"^(\*\.)?[a-z0-9][a-z0-9.-]*(\.\*)?$")
        for sites in (fixture_sites(), bg.sites_load(str(DATA))):
            rows = bg.sites_list(sites)
            names = [row["name"] for row in rows]
            self.assertEqual(len(names), len(set(names)))
            for row in rows:
                self.assertEqual(sorted(row), ["domains", "name"])
                self.assertTrue(site_name.search(row["name"]), row)
                self.assertGreaterEqual(len(row["domains"]), 1)
                self.assertEqual(len(row["domains"]), len(set(row["domains"])), row)
                for domain in row["domains"]:
                    self.assertTrue(site_domain.search(domain), row)

    def test_contract_examples(self):
        rows = {row["name"]: row["domains"] for row in bg.sites_list(bg.sites_load(str(DATA)))}
        self.assertEqual(rows["github.com"], ["github.com", "*.github.com"])
        self.assertEqual(rows["-google.com"], ["google.*", "www.google.*"])
        self.assertEqual(rows["+wikipedia.org"], ["wikipedia.org", "*.wikipedia.org"])


class ValidateTest(unittest.TestCase):

    def assertProblem(self, css, word):
        problems = bg.sites_validate(css)
        self.assertTrue(any(word in p for p in problems), (css, problems))

    def test_valid(self):
        for css in ("", "a { b: c }", "a { b: '}' } /* { */", 'a[x="{"] { b: c; }',
                    '@media (x) { a { b: c } }',
                    '@-moz-document regexp("https?://(?:[^/]*\\\\.)?a-b\\\\.test(?:[:/].*)?") { a {} }',
                    "@-moz-document regexp('https?://x\\\\.test/[a-z\\\\-]+') {}",
                    "/* @import url(x.css); */ a { b: c }", "a { content: \"@import\"; }",
                    "a { b: c }\r\n"):
            self.assertEqual(bg.sites_validate(css), [], css)

    def test_braces(self):
        self.assertProblem("a { b: c", "unclosed")
        self.assertProblem("a { b: c } }", "unbalanced")
        self.assertProblem("} a {", "unbalanced")
        self.assertProblem("a { { b: c }", "unclosed")

    def test_firefox_tokenization(self):
        # Each payload would let a style close its @-moz-document block early
        # (or swallow the next one) once tokenized the way Firefox does.
        for css, word in (
                ("a { b: \\} } }", "unbalanced"),                  # escaped brace is a name char
                ("a { b: url({) } }", "unbalanced"),                # url( token eats "{"
                ("a { b: url(/*) } } /* */", "unbalanced"),         # no comment inside url(
                ('a { content: "x\\" }', "unterminated string"),  # escaped quote
                ('a { content: "x\r} " }', "unterminated string"),  # CR ends a string
                ('a { content: "x\f} " }', "unterminated string"),  # FF ends a string
                ("a { b: url(x) ) }", "unbalanced"),
                ("a { b: c(} }", "unbalanced"),
                ("a { b: [} }", "unbalanced"),
                ("a { b: url(x\\) } } }", "unterminated url("),
                ("a { b: url(x", "unterminated url(")):
            self.assertProblem(css, word)
        for css in ("a { b: url({) }", "a { b: url(/*) }", 'a { content: "x\\" }" }',
                    "a\\{ { b: c }", "a { b: url( x ) }", "a { b: url(\"{\") }",
                    'a { content: "x\\\ny" }', "a { b: c(d) [e] }"):
            self.assertEqual(bg.sites_validate(css), [], css)

    def test_escaped_names(self):
        # Firefox unescapes at-keywords and function names.
        self.assertProblem('@\\69mport "x.css";', "@import")
        self.assertProblem('@im\\port "x.css";', "@import")
        self.assertProblem('@-moz-document \\72 egexp("(") {}', "regexp")
        self.assertProblem('@-moz-document REGEXP("(") {}', "regexp")
        self.assertProblem("@-moz-document r\\65 gexp(x) {}", "without a string")
        # "\\e" is the hex escape U+000E, not "e": not regexp(), nothing to check.
        self.assertEqual(bg.sites_validate("@-moz-document r\\egexp(x) {}"), [])
        self.assertProblem("a { b: \\75 rl({) } }", "unbalanced")

    def test_comments_and_strings(self):
        self.assertProblem("a { b: c } /* open", "unterminated comment")
        self.assertProblem('a { content: "open }', "unterminated string")
        self.assertProblem("a { content: 'x\n' }", "unterminated string")

    def test_import(self):
        self.assertProblem('@import "x.css";', "@import")
        self.assertProblem("a {}\n@IMPORT url(x.css);", "@import")

    def test_bad_regexp(self):
        self.assertProblem('@-moz-document regexp("(.*") {}', "regexp")
        self.assertProblem('@-moz-document regexp("x[") {}', "regexp")
        self.assertProblem('@-moz-document regexp("") {}', "empty")
        self.assertProblem("@-moz-document regexp(x) {}", "without a string")
        # Valid for Python, invalid in JavaScript Unicode mode (Firefox).
        self.assertProblem('@-moz-document regexp("https?://x\\\\-y\\\\.test/.*") {}', "escape")
        self.assertProblem('@-moz-document regexp("a{") {}', "lone")
        self.assertProblem('@-moz-document regexp("a]") {}', "lone")
        self.assertProblem('@-moz-document regexp("\\\\a") {}', "escape")

    def test_js_regexp_problem(self):
        for ok in ("a\\.b", "[a\\-z]", "\\d+\\s*", "a{2,3}", "\\u0041", "\\u{1F600}", "\\x41",
                   "(?:a|b)", "(?!x)", "\\/", "[\\]]", "\\cA", "\\p{L}"):
            self.assertIsNone(bg.js_regexp_problem(ok), ok)
        for ok in ("(?<n>a)\\k<n>", "(a)\\1", "(?<=a)b", "(?<!a)b", "a*?", "a{2}?", "\\0",
                   "[\\b]", "(?=a)"):
            self.assertIsNone(bg.js_regexp_problem(ok), ok)
        for bad in ("a\\-b", "\\a", "a{", "a}", "]", "\\x4", "\\u12", "\\e", "\\",
                    "(?P<x>a)", "(?i)a", "(?#c)a", "a*+", "a++", "(?>a)", "(a)(?(1)b|c)",
                    "(a)\\2", "[\\1]", "\\01", "(?=a)*", "*a", "a**", "(", ")", "[a",
                    "\\A", "\\Z", "a|*"):
            self.assertIsNotNone(bg.js_regexp_problem(bad), bad)

    def test_css_unescape(self):
        self.assertEqual(bg.css_unescape("a\\\\.b"), "a\\.b")
        self.assertEqual(bg.css_unescape("\\41 b"), "Ab")
        self.assertEqual(bg.css_unescape("x\\\ny"), "xy")
        self.assertEqual(bg.css_unescape("\\0"), "\ufffd")


class V0ParityTest(unittest.TestCase):
    """v1 build == v0 build on the embedded data, documented differences aside."""

    @classmethod
    def setUpClass(cls):
        cls.v0 = v0_golden()
        # A data/sites/ file with no my-internet style of its name is a new
        # style that v0 never had: leave those out (OwnNewStyleTest).
        sites = bg.sites_load(str(DATA))
        new = own_new_keys()
        cls.sites = bg.Sites(
            collections.OrderedDict((k, v) for k, v in sites.styles.items() if k not in new),
            sites.mapping)

    def test_with_exclusions(self):
        v1 = bg.sites_build_css(self.sites, V0_EXCLUSIONS.split(","))
        self.assertEqual(v0_normalize(self.v0).splitlines(), sort_alternatives(v1).splitlines())

    def test_without_exclusions(self):
        # v0 without exclusions = the same output minus its exclusion lookahead.
        lookahead = sort_alternatives(bg.exclusion_lookahead(V0_EXCLUSIONS.split(",")))
        expected = v0_normalize(self.v0).replace(lookahead, "")
        v1 = bg.sites_build_css(self.sites)
        self.assertEqual(expected.splitlines(), sort_alternatives(v1).splitlines())

    def test_block_count(self):
        v1 = bg.sites_build_css(self.sites, V0_EXCLUSIONS.split(","))
        self.assertEqual(v1.count("@-moz-document"), self.v0.count("@-moz-document"))

    def test_v1_regexps_valid(self):
        v1 = bg.sites_build_css(self.sites, V0_EXCLUSIONS.split(","))
        self.assertEqual(bg.sites_validate(v1), [])
        found = blocks(v1)
        self.assertEqual(len(found), v1.count("@-moz-document"))
        for comment, rx in found:
            self.assertIsNone(bg.js_regexp_problem(rx.pattern), comment)

    def test_v0_hyphen_bug(self):
        # Difference 1: v0's hyphenated regexps are invalid for Firefox.
        problems = bg.sites_validate(self.v0)
        self.assertTrue(problems)
        self.assertTrue(any("invalid escape '\\\\-'" in p for p in problems), problems[:3])

    def test_live_v0(self):
        script = v0_script()
        if not script:
            self.skipTest("v0 browser-glass-sites not available (set BG_V0_DIR)")
        self.assertEqual(run_v0_build(script, DATA, V0_EXCLUSIONS), self.v0)


if __name__ == "__main__":
    unittest.main()



class OwnNewStyleTest(unittest.TestCase):
    """A data/sites/ file with no my-internet style becomes a style of its own."""

    def test_new_styles_get_a_block_and_leave_the_generic(self):
        sites = bg.sites_load(str(DATA))
        css = bg.sites_build_css(sites)
        generic = css.partition(bg.SITES_GENERIC_COMMENT)[2]
        self.assertTrue(generic)
        for key in sorted(own_new_keys()):
            name = key[:-4]
            self.assertIn("/* %s */\n@-moz-document" % key, css)
            # The generic style skips the site: its name is in the lookahead.
            self.assertIn(name.replace(".", "\\\\."), generic, key)

class OwnSitesTest(unittest.TestCase):

    def own_dir(self, files):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        (pathlib.Path(tmp) / "styles.json").write_text(json.dumps({"website": {
            "youtube.com.css": {"transparency": "ytd-app { background: none !important; }"}}}))
        (pathlib.Path(tmp) / "sites").mkdir()
        for name, text in files.items():
            (pathlib.Path(tmp) / "sites" / name).write_text(text)
        return tmp

    def test_extends_the_style_as_its_last_feature(self):
        sites = bg.sites_load(self.own_dir({"youtube.com.css": "#bar { color: red; }\n"}))
        css = bg.sites_build_css(sites)
        self.assertIn("ytd-app { background: none !important; }\n#bar { color: red; }\n}", css)
        self.assertNotIn("#bar", bg.sites_build_css(sites, disabled=["youtube.com"]))

    def test_new_site_gets_its_own_style(self):
        sites = bg.sites_load(self.own_dir({"example.org.css": "#x { color: red; }",
                                            "README.md": "x", "Bad Name.css": "#y {}"}))
        self.assertIn("/* example.org.css */", bg.sites_build_css(sites))
        self.assertIn({"name": "example.org", "domains": ["example.org", "*.example.org"]},
                      bg.sites_list(sites))
        self.assertNotIn("#y", bg.sites_build_css(sites))

    def test_bundled_files_are_valid(self):
        folder = DATA / bg.SITES_OWN_DIR
        names = sorted(p.name for p in folder.glob("*.css"))
        self.assertEqual(names, [key for key, _ in bg._sites_own(str(DATA))])
        for key, css in bg._sites_own(str(DATA)):
            self.assertEqual(bg.sites_validate(css), [], key)
            # No network and no nested document rule (the block is one already).
            self.assertNotRegex(css, r"(?i)url\(|@-moz-document", key)
            self.assertTrue(css.startswith("/*"), "%s: begin with a comment" % key)

"""tools/update_styles.py: the offline parts (--check, --from-dir build and
the denylist filter). Nothing here uses the network: the upstream copies
are built in a FakeHome from the bundled data/.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import unittest
import urllib.request
from unittest import mock

from fakehome import REPO, FakeHome

TOOL = REPO / "tools" / "update_styles.py"
DENYLIST = REPO / "tools" / "style-denylist.txt"
DATA = REPO / "data"
DATA_FILES = ("styles.json", "css-mapping.json", "MY-INTERNET-LICENSE")

# Synthetic names only: the real denylisted ones never appear in the repo.
BLOCKED_NAME = "zz-blocked-style.example.css"
BLOCKED_WORD = "zorblaxian"

_TOOL_MODULE = None


def load_tool():
    global _TOOL_MODULE
    if _TOOL_MODULE is None:
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec = importlib.util.spec_from_file_location("update_styles_under_test", str(TOOL))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = old
        _TOOL_MODULE = module
    return _TOOL_MODULE


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_bytes(path):
    with open(str(path), "rb") as f:
        return f.read()


def write_bytes(path, data):
    with open(str(path), "wb") as f:
        f.write(data)


def dump(doc):
    """Serialised the way upstream (and the tool) write JSON."""
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")


class UpdateStylesTest(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.work = self.fh.tmp

    # -- helpers --------------------------------------------------------------

    def run_tool(self, *args):
        return self.fh.run_script([str(a) for a in args], script=TOOL)

    def copy_data(self, name="data"):
        folder = self.work / name
        folder.mkdir()
        for file in DATA_FILES:
            shutil.copyfile(str(DATA / file), str(folder / file))
        return folder

    def denylist(self, names=(), words=()):
        """The shipped denylist plus synthetic entries."""
        lines = [read_bytes(DENYLIST).decode("utf-8").rstrip("\n")]
        lines += ["name %s" % sha(n) for n in names]
        lines += ["word %d %s" % (len(w), sha(w)) for w in words]
        path = self.work / "denylist.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def upstream_from_data(self, extra_style=None, at=None):
        """A local upstream copy derived from data/, optionally with an extra
        style (key, features) inserted at position `at` of "website"."""
        folder = self.work / "upstream"
        folder.mkdir()
        doc = json.loads(read_bytes(DATA / "styles.json").decode("utf-8"))
        if extra_style is not None:
            items = list(doc["website"].items())
            items.insert(len(items) // 2 if at is None else at, extra_style)
            doc["website"] = dict(items)
            write_bytes(folder / "styles.json", dump(doc))
        else:
            shutil.copyfile(str(DATA / "styles.json"), str(folder / "styles.json"))
        shutil.copyfile(str(DATA / "css-mapping.json"), str(folder / "css-mapping.json"))
        shutil.copyfile(str(DATA / "MY-INTERNET-LICENSE"), str(folder / "LICENSE"))
        return folder

    def assert_same_as_data(self, folder):
        for file in DATA_FILES:
            self.assertEqual(read_bytes(folder / file), read_bytes(DATA / file), file)

    def check_fails(self, folder, needle, *extra):
        proc = self.run_tool("--check", folder, *extra)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stderr)

    def edit_styles(self, folder, edit):
        doc = json.loads(read_bytes(folder / "styles.json").decode("utf-8"))
        edit(doc)
        write_bytes(folder / "styles.json", dump(doc))

    # -- sources --------------------------------------------------------------

    def test_python39_syntax(self):
        for path in (TOOL, REPO / "tests" / "py" / "test_update_styles.py"):
            ast.parse(path.read_text(encoding="utf-8"), str(path), feature_version=(3, 9))

    def test_shipped_denylist(self):
        tool = load_tool()
        denylist = tool.Denylist.load(str(DENYLIST))
        self.assertGreaterEqual(len(denylist.names), 2)
        self.assertTrue(denylist.words)
        text = read_bytes(DENYLIST).decode("utf-8")
        self.assertNotIn(".css", text)

    # -- --check --------------------------------------------------------------

    def test_check_bundled_data(self):
        proc = self.run_tool("--check", DATA)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("OK", proc.stdout)
        # The real validator of browserglass.py was used, not the fallback.
        self.assertEqual(proc.stderr, "")

    def test_check_bundled_data_with_fallback_validator(self):
        tool = load_tool()
        problems = tool.check_files(tool.read_data_dir(str(DATA)),
                                    tool.Denylist.load(str(DENYLIST)), tool.basic_validate)
        self.assertEqual(problems, [])

    def test_check_invalid_json(self):
        folder = self.copy_data()
        write_bytes(folder / "styles.json", read_bytes(folder / "styles.json")[:-3])
        self.check_fails(folder, "invalid JSON")

    def test_check_duplicate_key(self):
        folder = self.copy_data()
        write_bytes(folder / "css-mapping.json",
                    b'{"notion.so.css": ["a.example"], "notion.so.css": ["b.example"]}')
        self.check_fails(folder, "duplicate key")

    def test_check_broken_css(self):
        for css, needle in (("html { background: none !important;", "unclosed"),
                            ("@import url(x.css); html { color: red }", "@import"),
                            ('@-moz-document regexp("(") { html { color: red } }', "regexp")):
            with self.subTest(css=css):
                folder = self.copy_data("broken-%d" % len(css))
                self.edit_styles(folder, lambda doc: doc["website"]["example.com.css"].update(
                    {"transparency": css}))
                self.check_fails(folder, needle)

    def test_check_feature_not_a_string(self):
        folder = self.copy_data()
        self.edit_styles(folder, lambda doc: doc["website"]["notion.so.css"].update({"glass": 1}))
        self.check_fails(folder, "not a string")

    def test_check_mapping_names_missing_style(self):
        folder = self.copy_data()
        mapping = json.loads(read_bytes(folder / "css-mapping.json").decode("utf-8"))
        mapping["no-such-style.example.css"] = ["a.example"]
        write_bytes(folder / "css-mapping.json", dump(mapping))
        self.check_fails(folder, "names no style")

    def test_check_mapping_mismatch(self):
        folder = self.copy_data()
        self.edit_styles(folder, lambda doc: doc["mapping"].update({"notion.so.css": []}))
        self.check_fails(folder, "differs")

    def test_check_missing_generic_style(self):
        folder = self.copy_data()
        mapping = json.loads(read_bytes(folder / "css-mapping.json").decode("utf-8"))
        mapping.pop("example.com.css")
        write_bytes(folder / "css-mapping.json", dump(mapping))

        def edit(doc):
            doc["website"].pop("example.com.css")
            doc["mapping"] = mapping
        self.edit_styles(folder, edit)
        self.check_fails(folder, "no generic style")

    def test_check_missing_license(self):
        folder = self.copy_data()
        os.unlink(str(folder / "MY-INTERNET-LICENSE"))
        self.check_fails(folder, "MY-INTERNET-LICENSE: missing")

    def test_check_denylisted_name(self):
        folder = self.copy_data()
        self.edit_styles(folder, lambda doc: doc["website"].update(
            {BLOCKED_NAME: {"transparency": "html { color: red }"}}))
        proc = self.run_tool("--check", folder)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.check_fails(folder, "is denylisted", "--denylist", self.denylist(names=[BLOCKED_NAME]))

    def test_check_denylisted_word(self):
        folder = self.copy_data()
        self.edit_styles(folder, lambda doc: doc["website"]["notion.so.css"].update(
            {"transparency": ".Zorblaxian-panel { background: none !important }"}))
        self.check_fails(folder, "denylisted word", "--denylist", self.denylist(words=[BLOCKED_WORD]))

    def test_check_escaped_denylisted_word(self):
        # The word spelled with a JSON escape: absent from the raw bytes,
        # present once decoded
        folder = self.copy_data()
        raw = read_bytes(folder / "styles.json").decode("utf-8")
        hidden = "\\u007a" + BLOCKED_WORD[1:]
        style = '"+zz-escaped.example.css": {"transparency": "a::after { content: \'%s\' }"}, ' % hidden
        raw = raw.replace('"website": {', '"website": {' + style, 1)
        write_bytes(folder / "styles.json", raw.encode("utf-8"))
        self.assertNotIn(BLOCKED_WORD, raw)
        self.check_fails(folder, "a JSON string contains a denylisted word",
                         "--denylist", self.denylist(words=[BLOCKED_WORD]))

    def test_check_license_must_be_mit(self):
        folder = self.copy_data()
        write_bytes(folder / "MY-INTERNET-LICENSE",
                    b"GNU GENERAL PUBLIC LICENSE\nCopyright (c) someone\n"
                    b"Permission is hereby granted\n")
        self.check_fails(folder, "not an MIT licence text")

    def test_check_broken_default_script_fails(self):
        # A copy of the tool beside a browserglass.py that does not compile:
        # no silent fallback to the weaker validator
        copy = self.work / "repo"
        (copy / "tools").mkdir(parents=True)
        shutil.copyfile(str(TOOL), str(copy / "tools" / "update_styles.py"))
        shutil.copyfile(str(DENYLIST), str(copy / "tools" / "style-denylist.txt"))
        (copy / "browserglass.py").write_text("def broken(:\n", encoding="utf-8")
        proc = self.fh.run_script(["--check", str(DATA)], script=copy / "tools" / "update_styles.py")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("cannot load", proc.stderr)
        self.assertNotIn("OK", proc.stdout)
        # Absent altogether: the fallback, said on stderr
        os.unlink(str(copy / "browserglass.py"))
        proc = self.fh.run_script(["--check", str(DATA)], script=copy / "tools" / "update_styles.py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("fallback", proc.stderr)

    def test_check_explicit_script_must_load(self):
        proc = self.run_tool("--check", DATA, "--browserglass", self.work / "missing.py")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("cannot load", proc.stderr)

    # -- build ----------------------------------------------------------------

    def test_build_reproduces_data_byte_for_byte(self):
        upstream = self.upstream_from_data(
            (BLOCKED_NAME, {"transparency": "html { background: none !important }"}))
        out = self.copy_data("out")
        write_bytes(out / "styles.json", b"{}")
        os.unlink(str(out / "MY-INTERNET-LICENSE"))
        denylist = self.denylist(names=[BLOCKED_NAME])
        proc = self.run_tool("--from-dir", upstream, "--out", out, "--denylist", denylist)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assert_same_as_data(out)
        self.assertIn("1 excluded", proc.stdout)
        self.assertIn("styles.json: updated", proc.stdout)
        self.assertNotIn(BLOCKED_NAME, read_bytes(out / "styles.json").decode("utf-8"))
        # A second run writes nothing.
        stamps = {f: os.stat(str(out / f)).st_mtime_ns for f in DATA_FILES}
        proc = self.run_tool("--from-dir", upstream, "--out", out, "--denylist", denylist)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual({f: os.stat(str(out / f)).st_mtime_ns for f in DATA_FILES}, stamps)
        self.assertNotIn("updated", proc.stdout)
        self.assertEqual(sorted(os.listdir(str(out))), sorted(DATA_FILES))

    def test_build_unfiltered_upstream_is_kept_verbatim(self):
        upstream = self.upstream_from_data()
        out = self.copy_data("out")
        proc = self.run_tool("--from-dir", upstream, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assert_same_as_data(out)
        self.assertIn("0 excluded", proc.stdout)

    def test_build_without_license_keeps_it(self):
        upstream = self.upstream_from_data()
        os.unlink(str(upstream / "LICENSE"))
        out = self.copy_data("out")
        proc = self.run_tool("--from-dir", upstream, "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assert_same_as_data(out)

    def test_build_rejects_broken_upstream(self):
        upstream = self.upstream_from_data(("broken.example.css", {"transparency": "html {"}))
        out = self.copy_data("out")
        proc = self.run_tool("--from-dir", upstream, "--out", out)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("nothing written", proc.stderr)
        self.assert_same_as_data(out)

    def test_build_from_dir_uses_no_network(self):
        tool = load_tool()
        upstream = self.upstream_from_data()
        out = self.copy_data("out")
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")), \
                mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            status = tool.main(["--from-dir", str(upstream), "--out", str(out)])
        self.assertEqual(status, 0)
        self.assert_same_as_data(out)

    def test_bad_ref_refused(self):
        tool = load_tool()
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")):
            with self.assertRaises(tool.Failure):
                tool.fetch_upstream("../x")

    # -- denylist -------------------------------------------------------------

    def test_denylist_filters_a_listed_name(self):
        tool = load_tool()
        denylist = tool.Denylist(names=[sha(BLOCKED_NAME)])
        for variant in (BLOCKED_NAME, " %s " % BLOCKED_NAME, BLOCKED_NAME.upper()):
            self.assertTrue(denylist.denies_name(variant), variant)
        self.assertFalse(denylist.denies_name("kept.example.css"))
        mapping = {BLOCKED_NAME: ["a.example"], "kept.example.css": ["b.example"]}
        styles = {
            "website": {
                "kept.example.css": {"transparency": "html { color: red }"},
                BLOCKED_NAME: {"transparency": "html { color: blue }"},
            },
            "mapping": mapping,
        }
        upstream = {"styles.json": dump(styles), "css-mapping.json": dump(mapping)}
        out, dropped = tool.build(upstream, denylist)
        self.assertEqual(dropped, [BLOCKED_NAME])
        doc = json.loads(out["styles.json"].decode("utf-8"))
        self.assertEqual(list(doc["website"]), ["kept.example.css"])
        self.assertEqual(doc["mapping"], {"kept.example.css": ["b.example"]})
        self.assertEqual(json.loads(out["css-mapping.json"].decode("utf-8")),
                         {"kept.example.css": ["b.example"]})
        self.assertNotIn("MY-INTERNET-LICENSE", out)

    def test_denylist_filters_a_listed_word(self):
        tool = load_tool()
        denylist = tool.Denylist(words={len(BLOCKED_WORD): {sha(BLOCKED_WORD)}})
        self.assertTrue(denylist.denies_text("a.ZorBlaxianX { }"))
        self.assertFalse(denylist.denies_text("zorblaxia zorblax-ian"))
        mapping = {"kept.example.css": ["b.example", "zorblaxian.example"]}
        styles = {"website": {
            "kept.example.css": {"transparency": "html { color: red }"},
            "other.example.css": {"glass": "#zorblaxian { color: red }"},
        }}
        out, dropped = tool.build(
            {"styles.json": dump(styles), "css-mapping.json": dump(mapping)}, denylist)
        self.assertEqual(dropped, ["other.example.css"])
        self.assertEqual(json.loads(out["css-mapping.json"].decode("utf-8")),
                         {"kept.example.css": ["b.example"]})

    def test_fallback_validator(self):
        tool = load_tool()
        self.assertEqual(tool.basic_validate('html { content: "}" } /* { */'), [])
        self.assertTrue(tool.basic_validate("html { color: red"))
        self.assertTrue(tool.basic_validate("html { color: red } }"))
        self.assertTrue(tool.basic_validate("@IMPORT 'x.css';"))
        self.assertTrue(tool.basic_validate("/* open"))


if __name__ == "__main__":
    unittest.main()

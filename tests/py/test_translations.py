"""tools/check_translations.py: the plugin's French catalog covers every
user-visible string, and the checker finds the strings it should (trFor and
tr calls, the daemon's toast() texts, logic.js toast "text" entries and
reasonText() returns) and fails on a missing or broken entry.

The sample plugins are written in a fake home (temporary folder); the
subprocess run gets the fake home's environment.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

from fakehome import REPO, FakeHome

TOOL = REPO / "tools" / "check_translations.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_translations", str(TOOL))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = _load()


def catalog(table):
    """The DMS plugin catalog shape for {term: translation}."""
    return json.dumps({term: {term: value} for term, value in table.items()}, ensure_ascii=False)


class RepoCatalogTest(unittest.TestCase):
    def test_repo_catalog_complete(self):
        errors, warnings, terms = ct.check(str(REPO))
        self.assertEqual(errors, [])
        self.assertGreater(len(terms), 50)

    def test_known_strings_found(self):
        terms = ct.collect(str(REPO))
        for term in (
            "Status",
            "Copy report",
            # The daemon's toast(level, text) and the sweep's trFor(Logic.PLUGIN_ID, ...)
            "Report copied to the clipboard",
            "Browser Glass removed, but restoring the browsers failed",
            # logic.js toast objects and reasonText()
            "Browser Glass sync failed",
            "Browser Glass warning",
            "DMS blur is off",
        ):
            self.assertIn(term, terms)
        # A toast object's other keys and compared values are not texts
        self.assertNotIn("details", terms)
        self.assertNotIn("zen_transparency_mod", terms)

    def test_catalog_is_valid_json_with_french(self):
        with open(str(REPO / "translations" / "fr.json"), encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["Status"], {"Status": "État"})
        self.assertEqual(doc["Copy report"]["Copy report"], "Copier le rapport")

    def test_french_percent_typography(self):
        # French puts a no-break space before a percent sign ("85 %"); a
        # %1-style placeholder keeps its plain spacing
        with open(str(REPO / "translations" / "fr.json"), encoding="utf-8") as f:
            doc = json.load(f)
        for bucket in doc.values():
            for term, value in bucket.items():
                for i, c in enumerate(value):
                    if c != "%" or value[i + 1:i + 2].isdigit():
                        continue
                    with self.subTest(term=term):
                        self.assertEqual(value[i - 1:i], " ", value)
                self.assertNotRegex(value, " %\\d", term)

    def test_python39_syntax(self):
        for path in (TOOL, REPO / "tests" / "py" / "test_translations.py"):
            with open(str(path), encoding="utf-8") as f:
                ast.parse(f.read(), str(path), feature_version=(3, 9))


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.home = FakeHome()
        self.addCleanup(self.home.cleanup)
        self.root = self.home.resolve("plugin")
        os.makedirs(str(self.root / "translations"))
        os.makedirs(str(self.root / "components"))

    def write(self, rel, text):
        path = self.root / rel
        os.makedirs(str(path.parent), exist_ok=True)
        with open(str(path), "w", encoding="utf-8") as f:
            f.write(text)

    def run_main(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = ct.main(["check_translations.py", str(self.root)])
        return code, out.getvalue()

    def test_missing_entry_fails(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "Hello") }\n'
                               'Text { text: I18n.trFor("browserGlass", "World") }\n')
        self.write("translations/fr.json", catalog({"Hello": "Bonjour"}))
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("Page.qml:2: no French entry for 'World'", out)

    def test_complete_passes_and_stale_warns(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "Hello") }\n')
        self.write("translations/fr.json", catalog({"Hello": "Bonjour", "Gone": "Parti"}))
        code, out = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("warning: ", out)
        self.assertIn("'Gone'", out)

    def test_bad_shapes_fail(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "Hello") }\n')
        for bad in ('["Hello"]', '{"Hello": "Bonjour"}', '{"Hello": {"Hello": ""}}', '{"Hello": {"Hello": 3}}', "{not json"):
            self.write("translations/fr.json", bad)
            code, _ = self.run_main()
            self.assertEqual(code, 1, bad)

    def test_missing_catalog_fails(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "Hello") }\n')
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("cannot read", out)

    def test_placeholders_must_match(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "%1 of %2").arg(1).arg(2) }\n')
        self.write("translations/fr.json", catalog({"%1 of %2": "%1 sur"}))
        self.assertEqual(self.run_main()[0], 1)
        self.write("translations/fr.json", catalog({"%1 of %2": "%2 : %1"}))
        self.assertEqual(self.run_main()[0], 0)

    def test_source_forms(self):
        self.write("Daemon.qml", "\n".join((
            'function f() {',
            '    root.toast("info", "Toast text", detail);',
            '    I18n.trFor(Logic.PLUGIN_ID, \'Single \\\'quoted\\\'\');',
            '    I18n.trFor(id(x), "After a call");',
            '    I18n.tr("Global term", "context");',
            '    I18n.trFor("browserGlass", "Esc\\u00e9 \\"q\\"");',
            '    // I18n.trFor("browserGlass", "Commented out")',
            '    /* root.toast("info", "Block comment") */',
            '    const s = "I18n.trFor(\\"x\\", \\"inside a string\\")";',
            '}',
        )))
        self.write("components/logic.js", "\n".join((
            'function syncToasts(w) {',
            '    toasts.push({"level": "error", "text": "Sync failed", "details": message});',
            '    toasts.push({',
            '        "text": w.code === "some_code" ? "Code text" : "Other text",',
            '        "details": ""',
            '    });',
            '}',
            'function reasonText(reason) {',
            '    switch (reason) {',
            '    case "a":',
            '        return "Reason A";',
            '    default:',
            '        return "Reason other";',
            '    }',
            '}',
            'function other() {',
            '    return "Not a text";',
            '}',
        )))
        terms = ct.collect(str(self.root))
        self.assertEqual(sorted(terms), sorted([
            "Toast text", "Single 'quoted'", "After a call", "Global term", 'Escé "q"',
            "Sync failed", "Code text", "Other text", "Reason A", "Reason other",
        ]))
        self.assertEqual(terms["Toast text"], [("Daemon.qml", 2)])

    def test_tests_and_tools_skipped(self):
        self.write("tests/qml/x.test.qml", 'I18n.trFor("browserGlass", "Test only")\n')
        self.write("tools/x.js", 'I18n.trFor("browserGlass", "Tool only")\n')
        self.write(".github/x.js", 'I18n.trFor("browserGlass", "Hidden")\n')
        self.write("components/tests/Ok.qml", 'I18n.trFor("browserGlass", "Nested")\n')
        self.assertEqual(sorted(ct.collect(str(self.root))), ["Nested"])

    def test_cli_subprocess(self):
        self.write("Page.qml", 'Text { text: I18n.trFor("browserGlass", "Hello") }\n')
        self.write("translations/fr.json", catalog({"Hello": "Bonjour"}))
        r = subprocess.run([sys.executable, "-I", "-B", str(TOOL), str(self.root)],
                           env=self.home.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("1 source strings, 0 errors, 0 warnings", r.stdout)
        self.write("translations/fr.json", catalog({}))
        r = subprocess.run([sys.executable, "-I", "-B", str(TOOL), str(self.root)],
                           env=self.home.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=60)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()

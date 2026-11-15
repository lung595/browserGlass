"""Tests for tools/check_pr_body.py, the pull request template check."""

import importlib.util
import os
import re
import unittest

from fakehome import REPO

_SPEC = importlib.util.spec_from_file_location(
    "check_pr_body", os.path.join(REPO, "tools", "check_pr_body.py"))
check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check)

TEMPLATE = os.path.join(REPO, ".github", "pull_request_template.md")
WORKFLOW = os.path.join(REPO, ".github", "workflows", "pr-template.yml")
IMAGE = "![after, dark](https://github.com/user-attachments/assets/0f3c-77ab)"


def body(shots=IMAGE, what="Fixes the header of example.org."):
    with open(TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    text = text.replace("## What does this change?\n", "## What does this change?\n\n" + what + "\n", 1)
    return text.replace("## Screenshots\n", "## Screenshots\n\n" + shots + "\n", 1)


class PrBodyTest(unittest.TestCase):
    def test_the_template_has_every_required_section(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            found = check.sections(f.read())
        for name in check.REQUIRED_SECTIONS:
            self.assertIn(name.lower(), found)

    def test_the_bare_template_fails(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            out = check.problems(f.read())
        self.assertTrue(any("image" in p for p in out))
        self.assertTrue(any("empty" in p for p in out))

    def test_a_filled_template_passes(self):
        self.assertEqual(check.problems(body()), [])

    def test_image_forms(self):
        for shot in (IMAGE,
                     '<img width="800" alt="after" src="https://github.com/user-attachments/assets/1a2b">',
                     "https://github.com/user-attachments/assets/1a2b-3c4d",
                     "![x](screenshots/hero.png)"):
            with self.subTest(shot=shot):
                self.assertEqual(check.problems(body(shot)), [])

    def test_no_image_fails(self):
        for shot in ("", "See the issue.", "[a link](https://example.org/a.png)",
                     "<!-- ![hidden](https://github.com/user-attachments/assets/1a2b) -->"):
            with self.subTest(shot=shot):
                out = check.problems(body(shot))
                self.assertEqual(len(out), 1)
                self.assertIn("image", out[0])

    def test_image_outside_screenshots_does_not_count(self):
        out = check.problems(body(shots="", what="Fixes it. " + IMAGE))
        self.assertTrue(any("image" in p for p in out))

    def test_missing_section_fails(self):
        out = check.problems(body().replace("## How was it tested?", "## Tests"))
        self.assertEqual(out, ['missing section "## How was it tested?" from the template'])

    def test_empty_body_lists_every_section(self):
        self.assertEqual(len(check.problems("")), len(check.REQUIRED_SECTIONS))
        self.assertEqual(len(check.problems(None)), len(check.REQUIRED_SECTIONS))

    def test_windows_line_endings(self):
        self.assertEqual(check.problems(body().replace("\n", "\r\n")), [])

    def test_workflow_keeps_the_body_out_of_the_script(self):
        with open(WORKFLOW, encoding="utf-8") as f:
            text = f.read()
        runs = re.findall(r"^\s*run:.*(?:\n\s{10,}.*)*", text, re.M)
        self.assertTrue(runs)
        for run in runs:
            self.assertNotIn("${{", run)
        self.assertIn("PR_BODY: ${{ github.event.pull_request.body }}", text)
        self.assertIn("$GITHUB_BASE_REF", text)


if __name__ == "__main__":
    unittest.main()

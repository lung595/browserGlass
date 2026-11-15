#!/usr/bin/env python3
"""Check that a pull request description follows .github/pull_request_template.md.

The description must keep the template's sections and show the change with at
least one image of the render in its "Screenshots" section. HTML comments (the
template's hints) do not count.

Usage: PR_BODY="..." python3 -I tools/check_pr_body.py
       python3 -I tools/check_pr_body.py FILE
Exit status 0 when the description is fine, 1 with the problems on stderr.
"""

import os
import re
import sys

REQUIRED_SECTIONS = ("What does this change?", "Screenshots", "How was it tested?")
SCREENSHOTS = "Screenshots"

_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_HEADING = re.compile(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
# A Markdown image, an <img> tag, or a bare link to an image GitHub hosts
# (what dragging a file into the description inserts).
_IMAGE = re.compile(
    r"!\[[^\]]*\]\(\s*\S+[^)]*\)"
    r"|<img\b[^>]*\bsrc\s*=\s*[\"']?[^\s\"'>]+"
    r"|https://github\.com/user-attachments/assets/[\w-]+"
    r"|https://(?:user-images|private-user-images)\.githubusercontent\.com/\S+",
    re.I,
)


def sections(body):
    """Map each level-2 heading of BODY (comments removed) to its text."""
    text = _COMMENT.sub("", body.replace("\r\n", "\n"))
    found = {}
    marks = list(_HEADING.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        found.setdefault(m.group(1).strip().lower(), text[m.end():end])
    return found


def problems(body):
    """Return the list of problems with the pull request description BODY."""
    found = sections(body or "")
    out = ["missing section \"## %s\" from the template" % name
           for name in REQUIRED_SECTIONS if name.lower() not in found]
    shots = found.get(SCREENSHOTS.lower())
    if shots is not None and not _IMAGE.search(shots):
        out.append("the \"## %s\" section needs at least one image of the render"
                   " (drag the file into the description)" % SCREENSHOTS)
    what = found.get(REQUIRED_SECTIONS[0].lower())
    if what is not None and not what.strip():
        out.append("the \"## %s\" section is empty" % REQUIRED_SECTIONS[0])
    return out


def main(argv):
    if len(argv) > 1:
        with open(argv[1], encoding="utf-8") as f:
            body = f.read()
    else:
        body = os.environ.get("PR_BODY", "")
    found = problems(body)
    for p in found:
        print("pull request description: " + p, file=sys.stderr)
    if found:
        print("See .github/pull_request_template.md and CONTRIBUTING.md"
              " \"Pull requests\".", file=sys.stderr)
        return 1
    print("pull request description: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

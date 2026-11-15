#!/usr/bin/env python3
"""Checks that every user-visible string of the plugin has a French entry.

Scans the plugin's .qml and .js files (tests/, tools/, docs and dot folders
left out) for the English source strings that reach I18n, then compares them
with translations/fr.json, the DMS plugin catalog format
({"context": {"term": "translation"}}, the term as its own context).

Source strings, all as string literals:
  - I18n.trFor(<plugin id>, "term" ...) and I18n.tr("term" ...);
  - toast("level", "term" ...): the daemon's toast(level, text, details)
    translates `text` with trFor;
  - in .js files, the literals of a `"text": ...` entry (logic.js toast
    objects, comparison operands skipped) and the `return "...";` lines of
    the functions in TEXT_FUNCTIONS (logic.js reasonText(), warningText()
    and liveStatusText(), launcher.js launcherText(), whose values the QML
    and the daemon's toasts translate).

The QML passes the literal plugin id to trFor, as DMS asks, except where the
term is computed (trFor("browserGlass", Logic.reasonText(...)), the daemon's
toast()): DMS's own extractor cannot see those terms; this checker is the
supported one, and it reads them at their source (the cases above).

Fails (exit 1) when a source string has no entry, an entry is not a
non-empty string, fr.json is not that shape, or a translation drops or adds
a %1-style placeholder. Entries no source uses are only warned about.

    python3 tools/check_translations.py [PLUGIN_ROOT]

Python stdlib only, runs on Python >= 3.9.
"""

import json
import os
import re
import sys

SKIP_DIRS = {"tests", "tools", "docs", "screenshots", "node_modules", "__pycache__"}
CATALOG = os.path.join("translations", "fr.json")
# logic.js and launcher.js functions that return source strings for trFor
TEXT_FUNCTIONS = ("reasonText", "warningText", "liveStatusText", "launcherText")

# One JS string literal (double or single quotes, escapes included)
_STR = r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\''
STR_RX = re.compile(_STR)
TRFOR_RX = re.compile(r"\btrFor\s*\(\s*(?:[^,()]|\([^()]*\))+?,\s*(" + _STR + r")")
TR_RX = re.compile(r"\bI18n\s*\.\s*tr\s*\(\s*(" + _STR + r")")
TOAST_RX = re.compile(r"\btoast\s*\(\s*(?:" + _STR + r")\s*,\s*(" + _STR + r")")
TEXT_KEY_RX = re.compile(r"""["']?\btext["']?\s*:\s*([^\n]*)""")
COMPARED_RX = re.compile(r"(?:===|!==|==|!=)\s*$")
# The next property of the same object literal ends a `"text":` value
NEXT_KEY_RX = re.compile(r",\s*[\"']?[A-Za-z_$][\w$]*[\"']?\s*:")
FUNCTION_RX = re.compile(r"^function\s+(\w+)\s*\(", re.M)
RETURN_RX = re.compile(r"\breturn\s+(" + _STR + r")\s*;")
PLACEHOLDER_RX = re.compile(r"%(\d+)")

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}


def decode_literal(literal):
    """The value of a JS string literal (with its quotes)."""
    body = literal[1:-1]
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        nxt = body[i + 1] if i + 1 < len(body) else ""
        if nxt == "u" and re.match(r"[0-9a-fA-F]{4}", body[i + 2:i + 6]):
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
        elif nxt == "x" and re.match(r"[0-9a-fA-F]{2}", body[i + 2:i + 4]):
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        else:
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
    return "".join(out)


def _strip_comments(text):
    """`text` with // and /* */ comments blanked (strings kept), so a
    commented-out call is not a source string. Offsets and lines are kept."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            m = STR_RX.match(text, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(" " * (end - i))
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            out.append(re.sub(r"[^\n]", " ", text[i:end]))
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _value_part(rest):
    """The part of a `"text": ...` line before the next property (strings
    skipped, so a comma inside one does not count)."""
    i = 0
    while i < len(rest):
        if rest[i] in "\"'":
            m = STR_RX.match(rest, i)
            i = m.end() if m else i + 1
            continue
        if NEXT_KEY_RX.match(rest, i):
            return rest[:i]
        i += 1
    return rest


def _line(text, offset):
    return text.count("\n", 0, offset) + 1


def strings_in(text, is_js):
    """[(term, line)] of the source strings in one file's text."""
    text = _strip_comments(text)
    found = []
    for rx in (TRFOR_RX, TR_RX, TOAST_RX):
        for m in rx.finditer(text):
            found.append((decode_literal(m.group(1)), _line(text, m.start(1))))
    if is_js:
        for m in TEXT_KEY_RX.finditer(text):
            rest = _value_part(m.group(1))
            for s in STR_RX.finditer(rest):
                if COMPARED_RX.search(rest[:s.start()]):
                    continue
                found.append((decode_literal(s.group(0)), _line(text, m.start(1))))
        starts = [(m.start(), m.group(1)) for m in FUNCTION_RX.finditer(text)]
        for k, (start, name) in enumerate(starts):
            if name not in TEXT_FUNCTIONS:
                continue
            end = starts[k + 1][0] if k + 1 < len(starts) else len(text)
            for m in RETURN_RX.finditer(text, start, end):
                found.append((decode_literal(m.group(1)), _line(text, m.start(1))))
    return found


def source_files(root):
    """The plugin's .qml and .js files, relative to root, sorted."""
    out = []
    for folder, dirs, files in os.walk(root):
        rel_folder = os.path.relpath(folder, root)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (rel_folder == "." and d in SKIP_DIRS) and d != "__pycache__")
        for name in sorted(files):
            if name.endswith((".qml", ".js")):
                out.append(os.path.normpath(os.path.join(rel_folder, name)))
    return out


def collect(root):
    """{term: [(file, line), ...]} of every source string under root."""
    terms = {}
    for rel in source_files(root):
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            text = f.read()
        for term, line in strings_in(text, rel.endswith(".js")):
            if term:
                terms.setdefault(term, []).append((rel, line))
    return terms


def load_catalog(path):
    """({term: translation}, [errors]) from a DMS plugin catalog file."""
    errors = []
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as e:
        return {}, ["%s: cannot read: %s" % (path, e)]
    if not isinstance(doc, dict):
        return {}, ["%s: the top level must be an object" % path]
    table = {}
    for context, bucket in doc.items():
        if not isinstance(bucket, dict):
            errors.append("%s: context %r must map terms to translations" % (path, context))
            continue
        for term, value in bucket.items():
            if not isinstance(value, str) or not value.strip():
                errors.append("%s: %r has no translation" % (path, term))
                continue
            if term in table and table[term] != value:
                errors.append("%s: %r is translated twice, differently" % (path, term))
            table.setdefault(term, value)
    return table, errors


def check(root):
    """(errors, warnings, terms): lists of messages and the source strings."""
    terms = collect(root)
    table, errors = load_catalog(os.path.join(root, CATALOG))
    warnings = []
    for term in sorted(terms):
        where = "%s:%d" % terms[term][0]
        if term not in table:
            errors.append("%s: no French entry for %r" % (where, term))
            continue
        want = sorted(set(PLACEHOLDER_RX.findall(term)))
        got = sorted(set(PLACEHOLDER_RX.findall(table[term])))
        if want != got:
            errors.append("%s: the translation of %r has placeholders %s, not %s" % (where, term, got, want))
    for term in sorted(set(table) - set(terms)):
        warnings.append("%s: unused entry %r" % (CATALOG, term))
    return errors, warnings, terms


def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(sys.argv[0])))
    errors, warnings, terms = check(root)
    for w in warnings:
        print("warning: " + w)
    for e in errors:
        print("error: " + e)
    print("%d source strings, %d errors, %d warnings" % (len(terms), len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

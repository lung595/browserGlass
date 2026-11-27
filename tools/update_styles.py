#!/usr/bin/env python3
"""update_styles - refresh the bundled site styles from sameerasw/my-internet
and the bundled Public Suffix List from publicsuffix.org.

Maintenance tool, run by .github/workflows/update-styles.yml (or by hand).
It and tools/sign_companion.py (a release tool) are the only parts of the
repository that use the network: browserglass.py never does, it reads the
copies kept in data/.

    update_styles.py [--ref REF | --from-dir DIR] [--out DIR]
    update_styles.py --check DIR

Build (default): fetch styles.json, css-mapping.json and LICENSE from the
upstream repository (branch or commit REF, default "main") and
public_suffix_list.dat from publicsuffix.org, or read them from DIR (a local
checkout or cache; LICENSE and public_suffix_list.dat are optional there),
drop the styles listed in tools/style-denylist.txt and the lines of the
suffix list holding a word it lists, check the result, then write
data/styles.json, data/css-mapping.json, data/MY-INTERNET-LICENSE and
data/public_suffix_list.dat (only the files whose bytes change; the suffix
list is otherwise kept byte for byte). data/PSL-LICENSE is maintained by
hand. A JSON file the filter left untouched is kept
byte for byte; a filtered one is re-serialised with a two-space indent and no
trailing newline. That is how upstream writes styles.json
(JSON.stringify(doc, null, 2)), but not css-mapping.json (hand-formatted, one
array per line): a filtered mapping file is rewritten in the new layout.
A short summary goes to stdout.

--check DIR (offline): DIR's files are well formed and consistent: JSON
shapes, no duplicate key, every CSS passes browserglass.py's validator,
the mapping only names existing styles and matches styles.json "mapping",
browserglass.py can load and build them, the licences are there, the
suffix list is UTF-8, large enough, has both sections and a "com" rule (and
browserglass.py loads it), and the denylist is respected (in the raw bytes
and in every decoded JSON string).
Problems go to stderr, exit status 1. browserglass.py is the validator;
the weaker fallback is used only when the default browserglass.py is
absent (a browserglass.py that exists but fails to load is a failure).

Exit status: 0 success, 1 failure, 2 usage error.
Python stdlib only, Python >= 3.9.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)
DEFAULT_OUT = os.path.join(REPO_DIR, "data")
DEFAULT_DENYLIST = os.path.join(TOOLS_DIR, "style-denylist.txt")
DEFAULT_SCRIPT = os.path.join(REPO_DIR, "browserglass.py")

UPSTREAM_URL = "https://raw.githubusercontent.com/sameerasw/my-internet/%s/%s"
PSL_URL = "https://publicsuffix.org/list/public_suffix_list.dat"
USER_AGENT = "browserglass-update-styles"
FETCH_LIMIT = 32 * 1024 * 1024
FETCH_TRIES = 3

STYLES = "styles.json"
MAPPING = "css-mapping.json"
LICENSE = "MY-INTERNET-LICENSE"
# Upstream file name -> file name in data/.
SOURCES = ((STYLES, STYLES), (MAPPING, MAPPING), ("LICENSE", LICENSE))
# Mozilla Public Suffix List (same name upstream and in data/), and its
# licence notice (not fetched).
PSL = "public_suffix_list.dat"
PSL_LICENSE = "PSL-LICENSE"
DATA_FILES = (STYLES, MAPPING, LICENSE, PSL, PSL_LICENSE)
PSL_MIN_BYTES = 64 * 1024
PSL_MARKERS = ("// ===BEGIN ICANN DOMAINS===", "// ===END ICANN DOMAINS===",
               "// ===BEGIN PRIVATE DOMAINS===", "// ===END PRIVATE DOMAINS===")
MPL_PHRASES = ("Mozilla Public License", "2.0", "https://mozilla.org/MPL/2.0/")
GENERIC_KEY = "example.com.css"
# Phrases every MIT licence text holds (compared with whitespace collapsed)
MIT_PHRASES = (
    "MIT License",
    "Copyright",
    "Permission is hereby granted, free of charge",
    "The above copyright notice and this permission notice shall be included",
    'THE SOFTWARE IS PROVIDED "AS IS"',
)
SUMMARY_NAMES = 40   # style names listed per summary line

_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LETTERS = re.compile(r"[^\W\d_]+")


class Failure(Exception):
    """A problem that stops the tool (exit status 1)."""


# ---------------------------------------------------------------------------
# denylist
# ---------------------------------------------------------------------------

def _style_file(key):
    """The file name browserglass.py's normalize_style_name loads `key` as:
    "X .CSS" and "x.css" are the same style."""
    name = key.strip()
    if name.lower().endswith(".css"):
        name = name[:-4]
    return name.strip().lower() + ".css"


class Denylist(object):
    """Digests of the style names and of the words the bundle must not hold."""

    def __init__(self, names=(), words=None):
        self.names = frozenset(names)
        self.words = dict(words or {})   # {length: {digest}}

    @classmethod
    def load(cls, path):
        names = set()
        words = {}
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        for number, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[0] == "name" and _DIGEST.fullmatch(parts[1]):
                names.add(parts[1])
            elif (len(parts) == 3 and parts[0] == "word" and parts[1].isdigit()
                  and int(parts[1]) > 0 and _DIGEST.fullmatch(parts[2])):
                words.setdefault(int(parts[1]), set()).add(parts[2])
            else:
                raise Failure("%s:%d: malformed denylist entry" % (path, number))
        return cls(names, words)

    def denies_name(self, key):
        """True when the style file name `key` is listed (as is, or trimmed
        and lowercased the way browserglass.py normalises keys)."""
        if not isinstance(key, str):
            return False
        forms = {key, key.strip(), key.strip().lower(), _style_file(key)}
        return any(_digest(k) in self.names for k in forms)

    def denies_text(self, text):
        """True when `text` contains one of the listed words (any case)."""
        if not self.words or not isinstance(text, str):
            return False
        for run in set(_LETTERS.findall(text.lower())):
            for length, digests in self.words.items():
                for i in range(len(run) - length + 1):
                    if _digest(run[i:i + length]) in digests:
                        return True
        return False


def _digest(text):
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def fetch_upstream(ref):
    """{upstream file name: bytes} fetched from the upstream repository
    (and the suffix list from publicsuffix.org)."""
    if not _REF.fullmatch(ref) or ".." in ref:
        raise Failure("invalid --ref %r" % ref)
    urls = [(name, UPSTREAM_URL % (ref, name)) for name, _ in SOURCES]
    urls.append((PSL, PSL_URL))
    return {name: _fetch(url) for name, url in urls}


def _fetch(url):
    for attempt in range(1, FETCH_TRIES + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(FETCH_LIMIT + 1)
            break
        except (urllib.error.URLError, OSError) as exc:
            if attempt == FETCH_TRIES:
                raise Failure("%s: %s" % (url, exc))
            time.sleep(5 * attempt)
    if len(data) > FETCH_LIMIT:
        raise Failure("%s: larger than %d bytes" % (url, FETCH_LIMIT))
    return data


def read_upstream_dir(folder):
    """{upstream file name: bytes} read from a local copy of upstream (a
    checkout or a cache). styles.json and css-mapping.json are required,
    LICENSE and public_suffix_list.dat are optional (missing: the data/
    copy is left alone)."""
    out = {}
    for name in [n for n, _ in SOURCES] + [PSL]:
        path = os.path.join(folder, name)
        try:
            out[name] = _read_bytes(path)
        except FileNotFoundError:
            if name not in ("LICENSE", PSL):
                raise Failure("%s: missing" % path)
        except OSError as exc:
            raise Failure("%s: %s" % (path, exc.strerror or exc))
    return out


def read_data_dir(folder):
    """{data file name: bytes} of the files present in a data/ folder."""
    out = {}
    for name in DATA_FILES:
        path = os.path.join(folder, name)
        try:
            out[name] = _read_bytes(path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise Failure("%s: %s" % (path, exc.strerror or exc))
    return out


def _read_bytes(path):
    with open(path, "rb") as f:
        data = f.read(FETCH_LIMIT + 1)
    if len(data) > FETCH_LIMIT:
        raise Failure("%s: larger than %d bytes" % (path, FETCH_LIMIT))
    return data


def parse_json(data, label, problems=None):
    """The JSON document in `data` (bytes); duplicate keys, NaN/Infinity and
    bad UTF-8 are errors. Raises Failure, or appends to `problems` and
    returns None when a list is given."""
    duplicates = []

    def pairs(items):
        seen = set()
        for key, _ in items:
            if key in seen:
                duplicates.append(key)
            seen.add(key)
        return dict(items)

    def constant(name):
        raise ValueError("non-standard constant %s" % name)

    try:
        doc = json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        message = "%s: invalid JSON: %s" % (label, exc)
        if problems is None:
            raise Failure(message)
        problems.append(message)
        return None
    if duplicates:
        message = "%s: duplicate key %r" % (label, duplicates[0])
        if problems is None:
            raise Failure(message)
        problems.append(message)
    return doc


def dump_json(doc):
    """`doc` serialised like upstream's JSON.stringify(doc, null, 2)."""
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

def _style_denied(key, features, denylist):
    if denylist.denies_name(key) or denylist.denies_text(key):
        return True
    if isinstance(features, dict):
        return any(denylist.denies_text(name) or denylist.denies_text(css)
                   for name, css in features.items())
    return denylist.denies_text(json.dumps(features))


def _filter_mapping(mapping, dropped, denylist):
    """`mapping` without the entries of `dropped` styles and without the
    entries or targets naming a denied word. Returns (mapping, changed)."""
    out = {}
    changed = False
    dropped = {_style_file(k) for k in dropped}  # JSON keys: always str
    for key, targets in mapping.items():
        if _style_file(key) in dropped or denylist.denies_name(key) or denylist.denies_text(key):
            changed = True
            continue
        if isinstance(targets, list):
            kept = [t for t in targets if not denylist.denies_text(t)]
            changed = changed or len(kept) != len(targets)
            targets = kept
        out[key] = targets
    return out, changed


def filter_psl(data, denylist):
    """(bytes, number of lines dropped): the suffix list `data` without the
    lines holding a denylisted word (rules and comments alike), every other
    byte kept."""
    try:
        lines = data.decode("utf-8").splitlines(True)
    except UnicodeDecodeError:
        raise Failure("%s: not UTF-8" % PSL)
    kept = [line for line in lines if not denylist.denies_text(line)]
    return "".join(kept).encode("utf-8"), len(lines) - len(kept)


def build(upstream, denylist):
    """({data file name: bytes}, [dropped style keys], number of suffix
    list lines dropped) built from the upstream files `upstream` ({upstream
    file name: bytes})."""
    styles_doc = parse_json(upstream[STYLES], STYLES)
    if not isinstance(styles_doc, dict) or not isinstance(styles_doc.get("website"), dict):
        raise Failure("%s: no \"website\" object" % STYLES)
    website = {}
    dropped = []
    for key, features in styles_doc["website"].items():
        if _style_denied(key, features, denylist):
            dropped.append(key)
        else:
            website[key] = features
    styles_changed = bool(dropped)
    doc = {}
    for top, value in styles_doc.items():
        if top == "website":
            value = website
        elif top == "mapping" and isinstance(value, dict):
            value, changed = _filter_mapping(value, set(dropped), denylist)
            styles_changed = styles_changed or changed
        doc[top] = value

    mapping_doc = parse_json(upstream[MAPPING], MAPPING)
    if not isinstance(mapping_doc, dict):
        raise Failure("%s: not a JSON object" % MAPPING)
    mapping, mapping_changed = _filter_mapping(mapping_doc, set(dropped), denylist)

    out = {
        STYLES: dump_json(doc) if styles_changed else upstream[STYLES],
        MAPPING: dump_json(mapping) if mapping_changed else upstream[MAPPING],
    }
    if "LICENSE" in upstream:
        out[LICENSE] = upstream["LICENSE"]
    psl_dropped = 0
    if PSL in upstream:
        out[PSL], psl_dropped = filter_psl(upstream[PSL], denylist)
    return out, dropped, psl_dropped


def write_outputs(folder, files):
    """Write `files` ({name: bytes}) into `folder`, atomically, skipping the
    files whose bytes do not change. Returns the names written."""
    written = []
    for name in sorted(files):
        path = os.path.join(folder, name)
        try:
            with open(path, "rb") as f:
                if f.read() == files[name]:
                    continue
            mode = os.stat(path).st_mode & 0o777
        except FileNotFoundError:
            mode = 0o644
        fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(files[name])
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        written.append(name)
    return written


def _style_keys(data):
    try:
        doc = json.loads(data.decode("utf-8"))
        return doc["website"] if isinstance(doc.get("website"), dict) else {}
    except (AttributeError, UnicodeDecodeError, ValueError, RecursionError):
        return {}


def summary(old, new, dropped, written, psl_dropped=0):
    """Plain-text lines describing the update (used as the PR body)."""
    before = _style_keys(old.get(STYLES, b""))
    after = _style_keys(new[STYLES])
    added = sorted(k for k in after if k not in before)
    removed = sorted(k for k in before if k not in after)
    changed = sorted(k for k in after if k in before and after[k] != before[k])
    lines = ["Site styles: %d bundled, %d excluded by the denylist." % (len(after), len(dropped))]
    for label, keys in (("Added", added), ("Removed", removed), ("Changed", changed)):
        if keys:
            shown = ", ".join(keys[:SUMMARY_NAMES])
            if len(keys) > SUMMARY_NAMES:
                shown += ", and %d more" % (len(keys) - SUMMARY_NAMES)
            lines.append("%s (%d): %s" % (label, len(keys), shown))
    if PSL in new:
        lines.append("Public Suffix List: %d lines dropped by the denylist." % psl_dropped)
    for name in sorted(new):
        lines.append("%s: %s" % (name, "updated" if name in written else "unchanged"))
    return lines


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def load_script(path):
    """browserglass.py at `path` imported as a module, without bytecode."""
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("browserglass_for_update_styles", path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load %s" % path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    for name in ("sites_validate", "sites_load", "sites_build_css", "sites_list", "psl_load"):
        if not callable(getattr(module, name, None)):
            raise ImportError("%s has no %s()" % (path, name))
    return module


def basic_validate(css):
    """Fallback validator, used only when browserglass.py cannot be loaded:
    comments, strings and brackets must close and nest, no @import."""
    problems = []
    stack = []
    pairs = {"}": "{", ")": "(", "]": "["}
    i = 0
    n = len(css)
    while i < n:
        c = css[i]
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            if end < 0:
                problems.append("unterminated comment at %d" % i)
                break
            i = end + 2
            continue
        if c in "\"'":
            j = i + 1
            while j < n and css[j] != c and css[j] != "\n":
                j += 2 if css[j] == "\\" else 1
            if j >= n or css[j] != c:
                problems.append("unterminated string at %d" % i)
                break
            i = j + 1
            continue
        if c == "\\":
            i += 2
            continue
        if c in "{([":
            stack.append(c)
        elif c in "})]":
            if stack and stack[-1] == pairs[c]:
                stack.pop()
            else:
                problems.append("unbalanced %r at %d" % (c, i))
        elif c == "@" and css[i + 1:i + 7].lower() == "import":
            problems.append("@import at %d" % i)
        i += 1
    if stack:
        problems.append("%d unclosed bracket(s)" % len(stack))
    return problems


def _check_mapping(doc, label, problems):
    if not isinstance(doc, dict):
        problems.append("%s: not a JSON object" % label)
        return False
    ok = True
    for key, targets in doc.items():
        if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
            problems.append("%s: %r: not a list of strings" % (label, key))
            ok = False
    return ok


def _strings_denied(doc, denylist):
    """True when a key or string anywhere in the decoded JSON `doc` holds a
    denylisted word (an escape such as \\u0063 hides it from a scan of the
    raw bytes)."""
    stack = [doc]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            if denylist.denies_text(value):
                return True
        elif isinstance(value, dict):
            for key, item in value.items():
                if denylist.denies_text(key):
                    return True
                stack.append(item)
        elif isinstance(value, list):
            stack.extend(value)
    return False


def _check_psl(data):
    """Problems of the suffix list `data` (bytes)."""
    if len(data) < PSL_MIN_BYTES:
        return ["%s: smaller than %d bytes" % (PSL, PSL_MIN_BYTES)]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return ["%s: not UTF-8" % PSL]
    lines = [line.strip() for line in text.splitlines()]
    problems = ["%s: no %r line" % (PSL, marker) for marker in PSL_MARKERS if marker not in lines]
    if "com" not in lines:
        problems.append("%s: no \"com\" rule" % PSL)
    return problems


def check_files(files, denylist, validate):
    """Problems (strings) of the data files `files` ({data file name: bytes})."""
    problems = []
    for name in DATA_FILES:
        if name not in files:
            problems.append("%s: missing" % name)
    for name, data in sorted(files.items()):
        text = data.decode("utf-8", "replace")
        if denylist.denies_text(text):
            problems.append("%s: contains a denylisted word" % name)

    website = {}
    styles_mapping = None
    if STYLES in files:
        doc = parse_json(files[STYLES], STYLES, problems)
        if doc is not None and _strings_denied(doc, denylist):
            problems.append("%s: a JSON string contains a denylisted word" % STYLES)
        if doc is not None:
            if not isinstance(doc, dict) or not isinstance(doc.get("website"), dict):
                problems.append("%s: no \"website\" object" % STYLES)
            else:
                website = doc["website"]
                if not website:
                    problems.append("%s: \"website\" is empty" % STYLES)
                if "mapping" in doc and _check_mapping(doc["mapping"], STYLES + " mapping", problems):
                    styles_mapping = doc["mapping"]
    for key, features in website.items():
        if denylist.denies_name(key):
            problems.append("%s: %r is denylisted" % (STYLES, key))
        if not isinstance(features, dict) or not features:
            problems.append("%s: %r: not an object of features" % (STYLES, key))
            continue
        for feature, css in features.items():
            if not isinstance(css, str):
                problems.append("%s: %r / %r: not a string" % (STYLES, key, feature))
                continue
            for problem in validate(css):
                problems.append("%s: %r / %r: %s" % (STYLES, key, feature, problem))
    if website and GENERIC_KEY not in website:
        problems.append("%s: no generic style %s" % (STYLES, GENERIC_KEY))

    if MAPPING in files:
        mapping = parse_json(files[MAPPING], MAPPING, problems)
        if mapping is not None and _strings_denied(mapping, denylist):
            problems.append("%s: a JSON string contains a denylisted word" % MAPPING)
        if mapping is not None and _check_mapping(mapping, MAPPING, problems):
            for key in mapping:
                if website and key not in website:
                    problems.append("%s: %r names no style" % (MAPPING, key))
                if denylist.denies_name(key):
                    problems.append("%s: %r is denylisted" % (MAPPING, key))
            if styles_mapping is not None and styles_mapping != mapping:
                problems.append("%s: \"mapping\" differs from %s" % (STYLES, MAPPING))

    if LICENSE in files:
        text = " ".join(files[LICENSE].decode("utf-8", "replace").split())
        if not all(phrase in text for phrase in MIT_PHRASES):
            problems.append("%s: not an MIT licence text" % LICENSE)
    if PSL in files:
        problems.extend(_check_psl(files[PSL]))
    if PSL_LICENSE in files:
        text = " ".join(files[PSL_LICENSE].decode("utf-8", "replace").split())
        if not all(phrase in text for phrase in MPL_PHRASES):
            problems.append("%s: not an MPL-2.0 notice" % PSL_LICENSE)
    return problems


def check_dir(folder, denylist, script):
    """Problems of the data folder `folder`; `script` is the loaded
    browserglass module or None (fallback validator, no load check)."""
    files = read_data_dir(folder)
    validate = script.sites_validate if script is not None else basic_validate
    problems = check_files(files, denylist, validate)
    if script is not None and not problems:
        try:
            sites = script.sites_load(folder)
            build_problems = []
            css = script.sites_build_css(sites, problems=build_problems)
            problems.extend("browserglass sites build: %s" % p for p in build_problems)
            if not css or not script.sites_list(sites):
                problems.append("browserglass: no site style left")
        except (OSError, ValueError) as exc:
            problems.append("browserglass cannot load %s: %s" % (folder, exc))
        try:
            script.psl_load(folder)
        except (OSError, ValueError) as exc:
            problems.append("browserglass cannot load %s: %s" % (folder, exc))
    return problems


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _script(path, explicit):
    """The loaded browserglass module. Only a missing default script falls
    back (None: basic_validate); a script that exists but fails to load, or
    an explicit --browserglass that cannot be loaded, is a Failure."""
    if not explicit and not os.path.exists(path):
        print("update_styles: %s not found; using the fallback CSS validator" % path,
              file=sys.stderr)
        return None
    try:
        return load_script(path)
    except Exception as exc:  # any import-time error of the loaded file
        raise Failure("cannot load %s: %s" % (path, exc))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="update_styles.py",
        description="Refresh data/ from sameerasw/my-internet and publicsuffix.org, "
                    "or check a data folder offline.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--check", metavar="DIR", help="check DIR's data files offline, write nothing")
    source.add_argument("--from-dir", metavar="DIR", help="read upstream files from DIR (no network)")
    source.add_argument("--ref", default="main", help="upstream branch or commit (default: main)")
    parser.add_argument("--out", metavar="DIR", default=DEFAULT_OUT, help="data folder to write")
    parser.add_argument("--denylist", metavar="FILE", default=DEFAULT_DENYLIST)
    parser.add_argument("--browserglass", metavar="FILE", default=None,
                        help="browserglass.py providing the CSS validator")
    args = parser.parse_args(argv)
    try:
        denylist = Denylist.load(args.denylist)
        script = _script(args.browserglass or DEFAULT_SCRIPT, args.browserglass is not None)
        if args.check is not None:
            problems = check_dir(args.check, denylist, script)
            for problem in problems:
                print("update_styles: %s" % problem, file=sys.stderr)
            if problems:
                return 1
            print("%s: OK" % args.check)
            return 0
        if not os.path.isdir(args.out):
            raise Failure("%s: not a folder" % args.out)
        upstream = read_upstream_dir(args.from_dir) if args.from_dir else fetch_upstream(args.ref)
        new, dropped, psl_dropped = build(upstream, denylist)
        old = read_data_dir(args.out)
        merged = dict(old)
        merged.update(new)
        validate = script.sites_validate if script is not None else basic_validate
        problems = check_files(merged, denylist, validate)
        if problems:
            for problem in problems:
                print("update_styles: %s" % problem, file=sys.stderr)
            raise Failure("upstream data rejected, nothing written")
        written = write_outputs(args.out, new)
        print("\n".join(summary(old, new, dropped, written, psl_dropped)))
        return 0
    except Failure as exc:
        print("update_styles: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

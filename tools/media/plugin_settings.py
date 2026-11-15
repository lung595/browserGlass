"""Save and put back the browserGlass entry of DMS's plugin_settings.json
around a media capture run (capture.sh save-state, restore.sh).

Usage: python3 -I -B plugin_settings.py COMMAND SETTINGS COPY [SITE]
  save     record the entry of SETTINGS (or its absence) in COPY (mode 600);
           refuses to overwrite an existing COPY
  restore  put the recorded entry back in SETTINGS when it differs (JSON
           equality): only the entry's text changes, every other key keeps
           its bytes; written atomically (temporary file + rename) with the
           file's mode. --dry-run tells what it would do
  check    exit 0 when the entry of SETTINGS equals the recorded one
  excluded SETTINGS COPY SITE   print "added" when the entry's excludedSites
           are the recorded ones plus SITE, "same" when they are the
           recorded ones, "other" otherwise (never a domain)

A recorded entry without noTrigger equals one with noTrigger: true (the
v1.1 daemon adds it when it first starts), and one without excludedSites
equals one with excludedSites: [] (what a blist then unblist leaves).

The entry's value is never printed: it holds the user's excluded sites.
Python 3.9 standard library only.
"""

import json
import os
import re
import sys

KEY = "browserGlass"
_WS = re.compile(r"[ \t\n\r]*")


def _members(text):
    """[(key, key_start, value_start, value_end)] of the top-level object
    in `text` and the index of its closing brace. Raises ValueError."""
    dec = json.JSONDecoder()
    i = _WS.match(text, 0).end()
    if text[i:i + 1] != "{":
        raise ValueError("not a JSON object")
    i = _WS.match(text, i + 1).end()
    out = []
    if text[i:i + 1] == "}":
        return out, i
    while True:
        if text[i:i + 1] != '"':
            raise ValueError("bad key")
        key, j = json.decoder.scanstring(text, i + 1)
        j = _WS.match(text, j).end()
        if text[j:j + 1] != ":":
            raise ValueError("bad member")
        vstart = _WS.match(text, j + 1).end()
        _, vend = dec.raw_decode(text, vstart)
        out.append((key, i, vstart, vend))
        k = _WS.match(text, vend).end()
        if text[k:k + 1] == ",":
            i = _WS.match(text, k + 1).end()
        elif text[k:k + 1] == "}":
            if text[k + 1:].strip():
                raise ValueError("trailing data")
            return out, k
        else:
            raise ValueError("bad separator")


def _indent_of(text, pos):
    """The whitespace between the last newline before `pos` and `pos`."""
    line = text[text.rfind("\n", 0, pos) + 1:pos]
    return line if not line.strip() else ""


def read_entry(path):
    """(present, value, raw text of the value) of the entry in the file at
    `path`; a missing file has no entry. Raises OSError, ValueError."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return False, None, None
    if not text.strip():
        return False, None, None
    doc = json.loads(text)
    if not isinstance(doc, dict):
        raise ValueError("not a JSON object")
    if KEY not in doc:
        return False, None, None
    raw = None
    try:
        spans = [m for m in _members(text)[0] if m[0] == KEY]
        if len(spans) == 1:
            raw = text[spans[0][2]:spans[0][3]]
    except ValueError:
        pass
    return True, doc[KEY], raw


def spliced(text, present, value, raw):
    """`text` (a JSON object, or "" for no file) with the entry set to
    `value` (raw text `raw` when known) or removed (`present` false). Only
    the entry's span changes when the text can be scanned; otherwise the
    whole object is written again (indent 2, as DMS writes it)."""
    body = raw if raw is not None else json.dumps(value, indent=2, ensure_ascii=False)
    if not text.strip():
        return ("{\n  %s: %s\n}" % (json.dumps(KEY), body.replace("\n", "\n  "))) if present else text
    try:
        members, close = _members(text)
        mine = [n for n, m in enumerate(members) if m[0] == KEY]
        if len(mine) > 1:
            raise ValueError("duplicate key")
        if mine:
            n = mine[0]
            _, kstart, vstart, vend = members[n]
            if present:
                if raw is None:
                    body = body.replace("\n", "\n" + _indent_of(text, kstart))
                return text[:vstart] + body + text[vend:]
            if n > 0:
                return text[:members[n - 1][3]] + text[vend:]
            if len(members) > 1:
                return text[:kstart] + text[members[1][1]:]
            return text[:kstart].rstrip() + text[close:]
        if not present:
            return text
        if members:
            last = members[-1]
            indent = _indent_of(text, last[1])
            if raw is None:
                body = body.replace("\n", "\n" + indent)
            sep = (",\n" + indent) if indent else ", "
            return text[:last[3]] + sep + json.dumps(KEY) + ": " + body + text[last[3]:]
        return text[:close].rstrip() + "\n  %s: %s\n" % (
            json.dumps(KEY), body.replace("\n", "\n  ") if raw is None else body) + text[close:]
    except ValueError:
        doc = json.loads(text, object_pairs_hook=dict)
        if present:
            doc[KEY] = value
        else:
            doc.pop(KEY, None)
        return json.dumps(doc, indent=2, ensure_ascii=False)


def _write_atomic(path, text, mode):
    tmp = path + ".bg-media.tmp"
    try:
        # Ours, left by an interrupted run
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_copy(copy):
    with open(copy, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or doc.get("key") != KEY or not isinstance(doc.get("present"), bool):
        raise ValueError("not a saved %s entry" % KEY)
    return doc["present"], doc.get("value"), doc.get("raw")


def _comparable(saved, now):
    """`now` without the noTrigger: true the daemon adds on its first start
    when `saved` has no noTrigger key, and without the excludedSites: []
    a blist then unblist leaves when `saved` has no excludedSites key."""
    if not (isinstance(saved, dict) and isinstance(now, dict)):
        return now
    if "noTrigger" not in saved and now.get("noTrigger") is True:
        now = {k: v for k, v in now.items() if k != "noTrigger"}
    if "excludedSites" not in saved and now.get("excludedSites") == []:
        now = {k: v for k, v in now.items() if k != "excludedSites"}
    return now


def same(settings, copy):
    present, value, _ = load_copy(copy)
    now_present, now_value, _ = read_entry(settings)
    return now_present == present and (not present or _comparable(value, now_value) == value)


def _domains(entry):
    sites = entry.get("excludedSites") if isinstance(entry, dict) else None
    out = set()
    for item in sites if isinstance(sites, list) else ():
        d = item.get("domain") if isinstance(item, dict) else item
        if isinstance(d, str) and d.strip():
            out.add(d.strip().lower().rstrip("."))
    return out


def cmd_excluded(settings, copy, site):
    present, value, _ = load_copy(copy)
    _, now_value, _ = read_entry(settings)
    saved, now = _domains(value if present else None), _domains(now_value)
    site = site.strip().lower().rstrip(".")
    if now == saved:
        print("same")
    elif site not in saved and now == saved | {site}:
        print("added")
    else:
        print("other")
    return 0


def cmd_save(settings, copy):
    present, value, raw = read_entry(settings)
    doc = {"key": KEY, "present": present, "value": value, "raw": raw}
    fd = os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print("saved the %s entry of %s (%s)" % (KEY, os.path.basename(settings),
                                              "present" if present else "absent"))
    return 0


def cmd_restore(settings, copy, dry):
    present, value, raw = load_copy(copy)
    if same(settings, copy):
        print("ok   %s: %s entry unchanged" % (os.path.basename(settings), KEY))
        return 0
    if dry:
        print("would restore the %s entry of %s" % (KEY, settings))
        return 0
    try:
        with open(settings, encoding="utf-8") as f:
            text = f.read()
        mode = os.stat(settings).st_mode & 0o7777
    except FileNotFoundError:
        text, mode = "", 0o644
    new = spliced(text, present, value, raw)
    want = json.loads(text) if text.strip() else {}
    if present:
        want[KEY] = value
    else:
        want.pop(KEY, None)
    if (json.loads(new) if new.strip() else {}) != want:
        # The splice went wrong somehow: write the whole object instead.
        new = json.dumps(want, indent=2, ensure_ascii=False)
    _write_atomic(settings, new, mode)
    print("restored the %s entry of %s" % (KEY, os.path.basename(settings)))
    return 0


def cmd_check(settings, copy):
    if same(settings, copy):
        print("ok   %s: %s entry identical (JSON)" % (os.path.basename(settings), KEY))
        return 0
    print("FAIL %s: %s entry differs from the saved copy" % (os.path.basename(settings), KEY))
    return 1


def main(argv):
    dry = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    if not ((len(args) == 3 and args[0] in ("save", "restore", "check"))
            or (len(args) == 4 and args[0] == "excluded")):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    cmd, settings, copy = args[:3]
    try:
        if cmd == "excluded":
            return cmd_excluded(settings, copy, args[3])
        if cmd == "save":
            return cmd_save(settings, copy)
        if cmd == "restore":
            return cmd_restore(settings, copy, dry)
        return cmd_check(settings, copy)
    except (OSError, ValueError) as exc:
        # The message names the file or the JSON position, never the value.
        print("plugin_settings.py %s: %s" % (cmd, getattr(exc, "strerror", None) or type(exc).__name__),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

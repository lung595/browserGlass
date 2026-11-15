"""Frozen CLI contract of browserglass.py (phase P0).

Validates every fixture in tests/fixtures/contract/ against schema.json with a
tiny stdlib validator, and checks the browserglass.py skeleton: it compiles,
is pure ASCII, never uses its own path, and its consts match the contract and
the bytes v0 wrote.

Run: python3 -m unittest discover -s tests/py -p 'test_*.py'
"""

import getpass
import hashlib
import importlib.util
import json
import os
import pathlib
import py_compile
import re
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = REPO / "tests" / "fixtures" / "contract"
SCRIPT = REPO / "browserglass.py"

# fixture file -> top-level spec name in schema.json
FIXTURES = {
    "sync.json": "sync",
    "sync-noop.json": "sync",
    "sync-companion.json": "sync",
    "status.json": "status",
    "sites.json": "sites",
    "settings-default.json": "settings",
    "uninstall.json": "uninstall",
    "uninstall-noop.json": "uninstall",
    "error.json": "error",
    # one per answer of active-site
    "active-site-companion.json": "active_site",
    "active-site-session.json": "active_site",
    "active-site-no_browser.json": "active_site",
    "active-site-private.json": "active_site",
    "active-site-not_web.json": "active_site",
    "active-site-no_session.json": "active_site",
    "active-site-ambiguous.json": "active_site",
    "active-site-unsupported.json": "active_site",
    "active-site-outdated.json": "active_site",
}

# top-level schema entries that are not specs
NON_SPECS = ("defs", "commands", "report_lines")

SECTIONS = ("consts", "fsio", "discover", "lockprobe", "inputs", "settings",
            "render", "sites", "psl", "session", "edits", "companion", "native", "state",
            "cmd_* / main")

# sha256 over b"\0".join(UTF-8 of these consts, in this order). Verified
# against the v0 scripts in P0; keeps guarding the bytes after P5 deletes them.
V0_MARKER_NAMES = (
    "V0_USERJS_BEGIN", "V0_USERJS_END", "V0_USERJS_BLOCK_TEMPLATE",
    "V0_IMPORT_CHROME", "V0_IMPORT_CONTENT", "V0_NIRI_INCLUDE", "V0_NIRI_KDL",
    "V0_CSS_HEADER_GLASS", "V0_CSS_HEADER_PAGES_OFF", "V0_CSS_HEADER_GLASS_OFF",
    "V0_CONTENT_CSS_NOTE", "V0_SITES_HEADER", "V0_SITES_GENERIC_COMMENT",
    "V0_SITES_MAPPING_COMMENT_TEMPLATE",
)
V0_MARKERS_SHA256 = "4338d1068cdc1722b6ae2357bf48e3c0fa07524abfcf04d58c5d8582b21b66bb"


# ---------------------------------------------------------------------------
# Tiny schema validator (see the $comment in schema.json)
# ---------------------------------------------------------------------------

VALUE_KEYS = {"type", "ref", "enum", "pattern", "min", "max", "items",
              "min_items", "unique", "fields", "doc"}
FIELD_KEYS = VALUE_KEYS | {"required", "default"}
TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def type_ok(value, name):
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ValueError("unknown type " + name)


def resolve(spec, defs):
    while "ref" in spec:
        spec = defs[spec["ref"]]
    return spec


def check_spec(spec, defs, path, field=False):
    """Return the problems of a spec itself (typos, unknown refs)."""
    errs = []
    allowed = FIELD_KEYS if field else VALUE_KEYS
    for key in spec:
        if key not in allowed:
            errs.append("%s: unknown spec key %r" % (path, key))
    if "ref" in spec:
        if spec["ref"] not in defs:
            errs.append("%s: unknown ref %r" % (path, spec["ref"]))
    else:
        types = spec.get("type")
        types = types if isinstance(types, list) else [types]
        for t in types:
            if t not in TYPES:
                errs.append("%s: bad type %r" % (path, t))
    if "pattern" in spec:
        re.compile(spec["pattern"])
    if "items" in spec:
        errs += check_spec(spec["items"], defs, path + "[]")
    for name, sub in spec.get("fields", {}).items():
        errs += check_spec(sub, defs, path + "." + name, field=True)
    return errs


def validate(value, spec, defs, path="$"):
    """Return a list of error strings; empty means valid."""
    spec = resolve(spec, defs)
    types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
    if not any(type_ok(value, t) for t in types):
        return ["%s: expected %s, got %s" % (path, "|".join(types), type(value).__name__)]
    errs = []
    if "enum" in spec and value not in spec["enum"]:
        errs.append("%s: %r not in %r" % (path, value, spec["enum"]))
    if isinstance(value, str):
        if "pattern" in spec and not re.search(spec["pattern"], value):
            errs.append("%s: %r does not match %s" % (path, value, spec["pattern"]))
        if "min" in spec and len(value) < spec["min"]:
            errs.append("%s: shorter than %d" % (path, spec["min"]))
    if type_ok(value, "number"):
        if "min" in spec and value < spec["min"]:
            errs.append("%s: %r < %r" % (path, value, spec["min"]))
        if "max" in spec and value > spec["max"]:
            errs.append("%s: %r > %r" % (path, value, spec["max"]))
    if isinstance(value, list):
        if len(value) < spec.get("min_items", 0):
            errs.append("%s: fewer than %d items" % (path, spec["min_items"]))
        if spec.get("unique"):
            seen = [json.dumps(v, sort_keys=True) for v in value]
            if len(seen) != len(set(seen)):
                errs.append("%s: duplicate items" % path)
        if "items" in spec:
            for i, item in enumerate(value):
                errs += validate(item, spec["items"], defs, "%s[%d]" % (path, i))
    if isinstance(value, dict):
        fields = spec.get("fields", {})
        for key in value:
            if key not in fields:
                errs.append("%s: unexpected key %r" % (path, key))
        for key, sub in fields.items():
            if key in value:
                errs += validate(value[key], sub, defs, path + "." + key)
            elif sub.get("required", True):
                errs.append("%s: missing key %r" % (path, key))
    return errs


def load_json(name):
    with open(str(CONTRACT / name), encoding="utf-8") as fh:
        return json.load(fh)


def load_script_module():
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # no __pycache__ in the repo
    try:
        spec = importlib.util.spec_from_file_location("browserglass_contract", str(SCRIPT))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


SCHEMA = load_json("schema.json")
DEFS = SCHEMA["defs"]


def spec_names():
    return [k for k in SCHEMA if not k.startswith("$") and k not in NON_SPECS]


class ValidatorSelfTest(unittest.TestCase):
    """The validator must reject what it claims to reject."""

    def test_rejects(self):
        spec = SCHEMA["sync"]
        good = load_json("sync-noop.json")
        self.assertEqual(validate(good, spec, DEFS), [])
        bad_cases = [
            dict(good, glass="yes"),
            dict(good, opacity=1.5),
            dict(good, reason="sleepy"),
            dict(good, changed=["NOT-AN-ID"]),
            dict(good, changed=["a1b2c3d4e5f6", "a1b2c3d4e5f6"]),
            dict(good, extra=1),
            {k: v for k, v in good.items() if k != "warnings"},
            dict(good, niri_changed=1),
            dict(good, opacity=True),
            {k: v for k, v in good.items() if k != "live"},
            dict(good, live={"hosts": -1, "acked": 0}),
            dict(good, live={"hosts": 1}),
            dict(good, live={"hosts": 1, "acked": True}),
        ]
        for bad in bad_cases:
            self.assertNotEqual(validate(bad, spec, DEFS), [], bad)

    def test_schema_is_well_formed(self):
        errs = []
        for name, spec in DEFS.items():
            errs += check_spec(spec, DEFS, "defs." + name)
        for name in spec_names():
            errs += check_spec(SCHEMA[name], DEFS, name)
        self.assertEqual(errs, [])


class FixturesTest(unittest.TestCase):

    def test_every_fixture_is_listed(self):
        on_disk = {p.name for p in CONTRACT.iterdir() if p.suffix == ".json"} - {"schema.json"}
        self.assertEqual(on_disk, set(FIXTURES))

    def test_fixtures_match_schema(self):
        for fixture, spec_name in sorted(FIXTURES.items()):
            with self.subTest(fixture=fixture):
                self.assertEqual(validate(load_json(fixture), SCHEMA[spec_name], DEFS), [])

    def test_sync_noop_is_a_noop(self):
        noop = load_json("sync-noop.json")
        self.assertEqual(noop["changed"], [])
        self.assertEqual(noop["running_changed"], [])
        self.assertFalse(noop["niri_changed"])
        self.assertFalse(noop["first_run"])
        self.assertEqual(noop["live"], {"hosts": 0, "acked": 0})

    def test_running_changed_subset_of_changed(self):
        for name in ("sync.json", "sync-noop.json", "sync-companion.json"):
            data = load_json(name)
            self.assertTrue(set(data["running_changed"]) <= set(data["changed"]), name)

    def test_sync_companion_states(self):
        # Only sync's own states: "outdated" is told by status alone.
        items = load_json("sync-companion.json")["companion"]
        states = [item["state"] for item in items]
        self.assertEqual(len(set(item["profile"] for item in items)), len(items))
        self.assertGreater(len(set(states)), 1)
        self.assertNotIn("outdated", states)

    def test_status_consistency(self):
        status = load_json("status.json")
        ids = [p["id"] for b in status["browsers"] for p in b["profiles"]]
        self.assertEqual(len(ids), len(set(ids)))
        for b in status["browsers"]:
            self.assertEqual(b["running"], any(p["running"] for p in b["profiles"]))
            self.assertEqual(b["restart_needed"], any(p["restart_needed"] for p in b["profiles"]))
            for p in b["profiles"]:
                self.assertTrue(p["path"].startswith(b["root"] + "/"), p["path"])
        self.assertEqual(status["restart_needed"], any(b["restart_needed"] for b in status["browsers"]))
        self.assertEqual(status["glass"]["active"], status["glass"]["reason"] == "active")
        for w in status["warnings"]:
            if w["profile"] is not None:
                self.assertIn(w["profile"], ids)

    def test_uninstall_consistency(self):
        for name in ("uninstall.json", "uninstall-noop.json"):
            data = load_json(name)
            self.assertTrue(set(data["pending"]) <= set(data["removed"]) | set(data["restored"]), name)
        noop = load_json("uninstall-noop.json")
        self.assertEqual([k for k, v in noop.items() if v not in ([], False)], [])

    def test_active_site_answers(self):
        """An answer is the four site fields, or the error field alone; every
        error of the spec has its fixture, and so has each source."""
        spec = SCHEMA["active_site"]["fields"]
        site = {"host", "domain", "source", "age"}
        errors, sources = set(), set()
        for name, spec_name in FIXTURES.items():
            if spec_name != "active_site":
                continue
            doc = load_json(name)
            if "error" in doc:
                self.assertEqual(set(doc), {"error"}, name)
                errors.add(doc["error"])
            else:
                self.assertEqual(set(doc), site, name)
                sources.add(doc["source"])
        self.assertEqual(errors, set(spec["error"]["enum"]))
        self.assertEqual(sources, set(spec["source"]["enum"]))
        self.assertEqual(set(spec), site | {"error"})

    def test_sites_domains(self):
        for site in load_json("sites.json"):
            name = site["name"]
            if name.startswith("-"):
                base = name[1:].rsplit(".", 1)[0]
                self.assertEqual(site["domains"][:2], [base + ".*", "www." + base + ".*"], name)
            else:
                host = name.lstrip("+")
                self.assertEqual(site["domains"][:2], [host, "*." + host], name)

    def test_commands_map(self):
        commands = {k: v for k, v in SCHEMA["commands"].items() if k != "doc"}
        for cmd, out in commands.items():
            self.assertTrue(out is None or out == "report_lines" or out in spec_names(), cmd)
        self.assertIn("uninstall", commands)
        self.assertIsNone(commands["clean-prefs"])  # prints nothing, exit 0
        used = set(FIXTURES.values()) - {"settings", "error"}
        self.assertTrue(used <= set(commands.values()))
        self.assertTrue({v for v in commands.values() if v not in (None, "report_lines")} <= used,
                        "every JSON output has a fixture")

    def test_settings_default_equals_schema_defaults(self):
        fields = SCHEMA["settings"]["fields"]
        for key, sub in fields.items():
            self.assertIn("default", sub, key)
            self.assertFalse(sub.get("required", True), key)
        defaults = {k: v["default"] for k, v in fields.items()}
        self.assertEqual(load_json("settings-default.json"), defaults)

    def test_no_private_data(self):
        home = os.path.expanduser("~")
        tokens = {"/home/", "/root/", "/var/home/", "/Users/"}
        for tok in (getpass.getuser(), os.path.basename(home.rstrip("/"))):
            if tok and len(tok) >= 3:
                tokens.add(tok)
        if len(home) > 1:
            tokens.add(home)
        for path in sorted(CONTRACT.iterdir()):
            text = path.read_text(encoding="utf-8")
            for tok in tokens:
                self.assertNotIn(tok, text, path.name)

    def test_report(self):
        text = (CONTRACT / "report.txt").read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("/", text)
        self.assertNotIn("~", text)
        self.assertNotIn("http", text)
        self.assertIsNone(re.search(r"\b[0-9a-f]{12}\b", text))
        names = {p["name"] for b in load_json("status.json")["browsers"] for p in b["profiles"]}
        for name in names:
            self.assertNotIn(name, text)
        lines = text.splitlines()
        pos = -1
        for prefix in SCHEMA["report_lines"]:
            idx = next((i for i, line in enumerate(lines) if line.startswith(prefix)), None)
            self.assertIsNotNone(idx, prefix)
            self.assertGreater(idx, pos, prefix)
            pos = idx


class ScriptTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = SCRIPT.read_bytes()
        cls.text = cls.raw.decode("ascii")  # fails if not pure ASCII
        cls.mod = load_script_module()

    def test_py_compile(self):
        with tempfile.TemporaryDirectory() as tmp:
            py_compile.compile(str(SCRIPT), cfile=os.path.join(tmp, "bg.pyc"), doraise=True)

    def test_shape(self):
        self.assertTrue(self.text.startswith("#!/usr/bin/env python3\n"))
        self.assertNotIn("__" + "file__", self.text)
        pos = -1
        for name in SECTIONS:
            banner = "\n# " + name + "\n"
            idx = self.text.find(banner)
            self.assertGreater(idx, pos, name)
            pos = idx

    def test_settings_defaults_match_contract(self):
        self.assertEqual(dict(self.mod.SETTINGS_DEFAULTS), load_json("settings-default.json"))
        self.assertEqual(list(self.mod.SETTINGS_DEFAULTS), list(SCHEMA["settings"]["fields"]))
        self.assertEqual(list(self.mod.SITE_THEMES), SCHEMA["settings"]["fields"]["siteTheme"]["enum"])
        self.assertEqual(list(self.mod.REASONS), DEFS["reason"]["enum"])
        self.assertEqual(list(self.mod.FAMILIES), DEFS["family"]["enum"])
        self.assertEqual(list(self.mod.VARIANTS), DEFS["variant"]["enum"])
        self.assertEqual(self.mod.VERSION, load_json("status.json")["version"])

    def test_commands_match_parser(self):
        parser = self.mod.build_parser()
        sub = next(a for a in parser._actions if a.dest == "command")
        commands = {k for k in SCHEMA["commands"] if k != "doc"}
        self.assertEqual(set(sub.choices), commands)

    def test_daemon_argv_flags_match_parser(self):
        # The flags components/logic.js passes in each *Argv() must be
        # options of that command (the QML tests only run a fake Proc)
        logic = (REPO / "components" / "logic.js").read_text(encoding="utf-8")
        sub = next(a for a in self.mod.build_parser()._actions if a.dest == "command")
        seen = set()
        for body in re.findall(r"\nfunction \w+Argv\([^)]*\) \{\n(.*?)\n\}", logic, re.S):
            words = re.findall(r'"(-[^"=]*)=?[^"]*"', body)
            cmd = next((w for w in re.findall(r'"([a-z][a-z-]*)"', body)
                        if w in sub.choices), None)
            if cmd is None:
                continue
            known = {o for a in sub.choices[cmd]._actions for o in a.option_strings}
            for flag in words:
                if flag.startswith("--"):
                    self.assertIn(flag, known, cmd)
                    seen.add((cmd, flag))
        self.assertIn(("sync", "--plugin-dir"), seen)
        self.assertIn(("active-site", "--window-id"), seen)
        self.assertNotIn(("active-site", "--title"), seen)  # an argv is public

    def test_prefs(self):
        m = self.mod
        self.assertEqual(m.PREFS, (
            "toolkit.legacyUserProfileCustomizations.stylesheets",
            "browser.tabs.allow_transparent_browser",
            "layout.css.prefers-color-scheme.content-override",
            "xpinstall.signatures.required",
            "extensions.autoDisableScopes",
            "extensions.startupScanScopes",
        ))
        self.assertEqual(m.COMPANION_PREFS, m.PREFS[3:])
        self.assertEqual(set(m.V0_PREF_VALUES), set(m.PREFS))
        for pref in m.PREFS:
            if pref in m.COMPANION_PREFS:
                self.assertEqual(m.V0_PREF_VALUES[pref], ())
                self.assertNotIn(pref, m.V0_USERJS_BLOCK_TEMPLATE)
            else:
                self.assertIn('user_pref("%s", ' % pref, m.V0_USERJS_BLOCK_TEMPLATE)

    def test_roots(self):
        m = self.mod
        seen = set()
        for root in m.ROOTS:
            self.assertIn(root.base, ("home", "config"))
            self.assertIn(root.family, m.FAMILIES)
            self.assertIn(root.variant, m.VARIANTS)
            self.assertFalse(root.rel.startswith("/") or root.rel.endswith("/"), root)
            self.assertNotIn((root.base, root.rel), seen)
            seen.add((root.base, root.rel))
            if root.variant == "flatpak":
                self.assertTrue(root.rel.startswith(".var/app/"), root)
            if root.variant == "snap":
                self.assertTrue(root.rel.startswith("snap/"), root)
        for fam in m.FAMILIES:
            variants = {r.variant for r in m.ROOTS if r.family == fam}
            self.assertTrue({"native", "flatpak"} <= variants, fam)
            app = {r.rel.split("/")[2] for r in m.ROOTS if r.family == fam and r.variant == "flatpak"}
            for app_id in app:  # both flatpak layouts: dot-dir and config/<...>
                rels = [r.rel for r in m.ROOTS if r.rel.startswith(".var/app/" + app_id + "/")]
                self.assertTrue(any("/config/" in r for r in rels), app_id)
                self.assertTrue(any("/config/" not in r for r in rels), app_id)
        self.assertTrue(set(m.V0_ROOTS) <= seen)  # v1 finds everything v0 touched

    def test_app_ids(self):
        m = self.mod
        self.assertEqual(len(m.APP_IDS), len(set(m.APP_IDS)))
        self.assertNotIn("firefox_firefox", m.APP_IDS)  # unverified (H7)
        for app_id in m.APP_IDS:
            self.assertRegex(app_id, r"^[a-z][a-z0-9._-]*$")
        v0_ids = re.search(r"\^\((.*)\)\$", m.V0_NIRI_KDL).group(1).replace("\\.", ".").split("|")
        self.assertTrue(set(v0_ids) <= set(m.APP_IDS))
        for r in m.ROOTS:
            if r.variant == "flatpak":
                self.assertIn(r.rel.split("/")[2], m.APP_IDS)

    def test_v1_markers(self):
        m = self.mod
        v0 = [getattr(m, n) for n in V0_MARKER_NAMES]
        for name in ("V1_USERJS_BEGIN", "V1_USERJS_END", "V1_CSS_HEADER", "V1_NIRI_HEADER"):
            value = getattr(m, name)
            value.encode("ascii")
            self.assertNotIn(value, v0, name)
            self.assertTrue(all(value not in s and s not in value for s in
                                (m.V0_USERJS_BEGIN, m.V0_USERJS_END)), name)
        self.assertTrue(m.V1_USERJS_BEGIN.startswith("// "))
        self.assertTrue(m.V1_USERJS_END.startswith("// "))
        self.assertTrue(m.V1_CSS_HEADER.startswith("/* ") and m.V1_CSS_HEADER.endswith(" */"))
        self.assertTrue(m.V1_NIRI_HEADER.startswith("// "))

    def test_v0_markers_frozen(self):
        m = self.mod
        blob = b"\0".join(getattr(m, n).encode("utf-8") for n in V0_MARKER_NAMES)
        self.assertEqual(hashlib.sha256(blob).hexdigest(), V0_MARKERS_SHA256)
        self.assertIn("\u00e9", m.V0_USERJS_BEGIN)
        self.assertIn("\u2014", m.V0_NIRI_KDL)

    def test_v0_markers_in_v0_scripts(self):
        sync = REPO / "browser-glass-sync"
        sites = REPO / "browser-glass-sites"
        if not (sync.is_file() and sites.is_file()):
            self.skipTest("v0 scripts removed (P5); covered by test_v0_markers_frozen")
        m = self.mod
        sync_b, sites_b = sync.read_bytes(), sites.read_bytes()
        for name in ("V0_USERJS_BEGIN", "V0_USERJS_END", "V0_IMPORT_CHROME", "V0_IMPORT_CONTENT",
                     "V0_NIRI_INCLUDE", "V0_NIRI_KDL", "V0_CSS_HEADER_PAGES_OFF",
                     "V0_CSS_HEADER_GLASS_OFF", "V0_CONTENT_CSS_NOTE"):
            self.assertIn(getattr(m, name).encode("utf-8"), sync_b, name)
        self.assertIn(m.V0_CSS_HEADER_GLASS.replace("{opacity}", "$OPACITY").encode("utf-8"), sync_b)
        block = m.V0_USERJS_BLOCK_TEMPLATE.replace("{transparent}", "$TRANSP").replace(
            "{scheme}", "$SCHEME").replace('"', '\\"')
        block = block.replace(m.V0_USERJS_BEGIN, "$MARK_BEGIN").replace(m.V0_USERJS_END, "$MARK_END")
        self.assertIn(block.rstrip("\n").encode("utf-8"), sync_b)
        for name in ("V0_SITES_HEADER", "V0_SITES_GENERIC_COMMENT"):
            self.assertIn(getattr(m, name).encode("utf-8"), sites_b, name)
        self.assertIn(m.V0_SITES_MAPPING_COMMENT_TEMPLATE.encode("utf-8"), sites_b)  # f-string text


if __name__ == "__main__":
    unittest.main()

"""Black-box contract tests of `status --json`, `report` and `sites --json` (P4).

Everything goes through the command line (FakeHome.run_script): nothing of
browserglass.py is imported. Outputs are checked against
tests/fixtures/contract/schema.json. The fake HOME holds several families
(Firefox native + Flatpak, LibreWolf, Zen native); a running browser is a
LockHolder child holding an fcntl lock on the profile's .parentlock.

Every read-only command is run between two full snapshots of the fake tree
(contents, modes, inodes and mtimes): status, report and sites never write.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import getpass
import hashlib
import json
import os
import re
import socket
import stat
import unittest

import test_contract
from fakehome import REAL_HOME, REPO, FakeHome, LockHolder, kill_strays

SCHEMA = test_contract.SCHEMA
DEFS = test_contract.DEFS
REPORT_LINES = SCHEMA["report_lines"]

FF = ".mozilla/firefox"
FP = ".var/app/org.mozilla.firefox/.mozilla/firefox"
LW = ".librewolf"
ZEN = ".zen"

# (root, folder name, profiles.ini Name, default). Every name carries the
# account name, so the report test can catch any profile name or folder.
PROFILES = (
    (FF, "q1w2e3r4.alice-release", "alice-release", True),
    (FF, "t5y6u7i8.alice work", "alice work", False),
    (FP, "o9p0a1s2.alice-flat", "alice-flat", True),
    (LW, "d3f4g5h6.alice-wolf", "alice-wolf", True),
    (ZEN, "j7k8l9z0.alice (release)", "alice (release)", True),
)
FF_MAIN = FF + "/q1w2e3r4.alice-release"
FF_WORK = FF + "/t5y6u7i8.alice work"
ZEN_PROFILE = ZEN + "/j7k8l9z0.alice (release)"

# (family, variant, tilde root) of each browser the fake home holds
BROWSERS = {
    FF: ("firefox", "native", "~/.mozilla/firefox"),
    FP: ("firefox", "flatpak", "~/.var/app/org.mozilla.firefox/.mozilla/firefox"),
    LW: ("librewolf", "native", "~/.librewolf"),
    ZEN: ("zen", "native", "~/.zen"),
}

NIRI_CONFIG = ".config/niri/config.kdl"
WINDOWRULES = ".config/niri/dms/windowrules.kdl"
SURFACE = "#1a1c22"
FAST = {"BG_LOCK_TIMEOUT": "0.3", "BG_POLL_INTERVAL": "0.05"}

ZEN_MOD_TRANSPARENT = {
    "5b0a7c1e-0000-4000-8000-00000000c0de": {
        "id": "5b0a7c1e-0000-4000-8000-00000000c0de",
        "name": "Transparent Zen",
        "description": "Makes the browser background transparent.",
        "author": "example-author",
        "enabled": True,
        "version": "1.0.0",
    },
}
ZEN_MOD_OTHER = {
    "7d2c9e4f-0000-4000-8000-00000000beef": {
        "id": "7d2c9e4f-0000-4000-8000-00000000beef",
        "name": "Compact Tabs",
        "description": "Smaller tab strip.",
        "author": "example-author",
        "enabled": True,
        "version": "1.0.0",
    },
}

PROFILE_LINE = re.compile(
    r"^  (firefox|librewolf|zen|floorp|waterfox) (native|flatpak|snap): "
    r"([0-9]+) \(([0-9]+) running, ([0-9]+) restart needed\)$")


def contract_id(path):
    """The contract's profile id (defs.profile_id), computed from its doc."""
    return hashlib.sha256(os.fsencode(os.path.realpath(str(path)))).hexdigest()[:12]


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


def tree(top):
    """Everything below `top` (itself included): {relative path: details},
    details = (kind, mode, inode, mtime_ns, content). Equal trees mean
    nothing was written, created, removed or touched."""
    out = {}

    def entry(full):
        st = os.lstat(full)
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            return ("link", mode, st.st_ino, st.st_mtime_ns, os.readlink(full))
        if stat.S_ISDIR(st.st_mode):
            return ("dir", mode, st.st_ino, st.st_mtime_ns, None)
        with open(full, "rb") as f:
            return ("file", mode, st.st_ino, st.st_mtime_ns, f.read())

    out["."] = entry(top)
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            full = os.path.join(dirpath, name)
            out[os.path.relpath(full, top)] = entry(full)
    return out


class BlackBoxCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome(name="alice")
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)

    # -- the fake home ------------------------------------------------------

    def build_home(self, zen_mods=None):
        fh = self.fh
        by_root = {}
        for root, folder, name, default in PROFILES:
            fh.make_profile(root, folder, prefs={"browser.startup.page": 3})
            by_root.setdefault(root, []).append({"name": name, "path": folder, "default": default})
        for root, entries in by_root.items():
            fh.write_profiles_ini(root, entries)
        if zen_mods is not None:
            fh.write(ZEN_PROFILE + "/chrome/zen-themes.json", json.dumps(zen_mods, indent=2) + "\n")
        fh.write(NIRI_CONFIG, 'input {\n}\n\ninclude "dms/windowrules.kdl"\n', mode=0o644)
        fh.write(WINDOWRULES, "window-rule {\n    opacity 0.8\n}\n", mode=0o644)
        fh.write_dms_colors(mode="dark", surface_dark=SURFACE)

    def pid(self, rel):
        return contract_id(self.fh.resolve(rel))

    def browser(self, rel):
        """A running browser on profile `rel`; killed at tearDown."""
        holder = LockHolder(self.fh, rel + "/.parentlock")
        self.addCleanup(holder.stop)
        return holder

    # -- commands that write ------------------------------------------------

    def sync(self, settings_doc=None):
        proc = self.fh.run_script(["sync", "--settings", json.dumps(settings_doc or settings())],
                                  extra_env=FAST)
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["sync"], DEFS), [], proc.stdout)
        return doc

    def uninstall(self):
        proc = self.fh.run_script(["uninstall"], extra_env=FAST)
        self.assertEqual(proc.returncode, 0, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["uninstall"], DEFS), [], proc.stdout)
        return doc

    # -- read-only commands -------------------------------------------------

    def read_only(self, args, code=0):
        """Run `args`, failing if anything under the fake root changed."""
        before = tree(str(self.fh.root))
        proc = self.fh.run_script(args, extra_env=FAST)
        after = tree(str(self.fh.root))
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        self.assertEqual(changed, [], "%s modified the fake home" % " ".join(args))
        self.assertEqual(proc.returncode, code, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        return proc

    def status(self):
        proc = self.read_only(["status", "--json"])
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        self.assertEqual(test_contract.validate(doc, SCHEMA["status"], DEFS), [], lines[0])
        # Paths are always shown relative to HOME.
        self.assertNotIn(str(self.fh.home), proc.stdout)
        self.assertNotIn(str(self.fh.root), proc.stdout)
        return doc

    def report(self):
        proc = self.read_only(["report"])
        self.assertTrue(proc.stdout.endswith("\n"), repr(proc.stdout))
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], REPORT_LINES[0])
        # The contract's line prefixes, in their order.
        at = 0
        for prefix in REPORT_LINES[1:]:
            for index in range(at, len(lines)):
                if lines[index].startswith(prefix):
                    at = index + 1
                    break
            else:
                self.fail("report has no %r line after line %d:\n%s" % (prefix, at, proc.stdout))
        return proc.stdout

    def report_profiles(self, text):
        """{(family, variant): (count, running, restart needed)} of a report."""
        lines = text.splitlines()
        start = lines.index("profiles:") + 1
        out = {}
        for line in lines[start:]:
            if line.startswith(REPORT_LINES[6]):
                break
            if line.strip() in ("none", "(none)"):
                continue
            match = PROFILE_LINE.match(line)
            self.assertIsNotNone(match, "bad profile line %r" % line)
            key = (match.group(1), match.group(2))
            self.assertNotIn(key, out, "duplicate profile line %r" % line)
            out[key] = tuple(int(match.group(i)) for i in (3, 4, 5))
        return out

    # -- status helpers -----------------------------------------------------

    def browsers(self, doc):
        """{(family, variant, root): browser} of a status, checked unique."""
        out = {}
        for browser in doc["browsers"]:
            key = (browser["family"], browser["variant"], browser["root"])
            self.assertNotIn(key, out, "duplicate browser %r" % (key,))
            out[key] = browser
        return out

    def profiles(self, doc):
        """{profile id: (browser, profile)} of a status, checked unique."""
        out = {}
        for browser in doc["browsers"]:
            for profile in browser["profiles"]:
                self.assertNotIn(profile["id"], out, "duplicate profile id")
                out[profile["id"]] = (browser, profile)
        return out

    def check_layout(self, doc):
        """The browsers and profiles of the fake home, exactly."""
        self.assertEqual(sorted(self.browsers(doc)), sorted(BROWSERS.values()))
        found = self.profiles(doc)
        expected = {}
        for root, folder, name, default in PROFILES:
            expected[self.pid(root + "/" + folder)] = (root, folder, name, default)
        self.assertEqual(sorted(found), sorted(expected))
        for pid, (root, folder, name, default) in expected.items():
            browser, profile = found[pid]
            self.assertEqual((browser["family"], browser["variant"], browser["root"]), BROWSERS[root])
            self.assertEqual(profile["name"], name)
            self.assertEqual(profile["path"], BROWSERS[root][2] + "/" + folder)
            self.assertEqual(profile["default"], default, name)
        return found

    def check_glass_inputs(self, doc):
        glass = doc["glass"]
        self.assertAlmostEqual(glass["opacity"], 0.8)
        self.assertEqual(glass["opacity_source"], "dms")
        self.assertEqual(glass["surface"].lower(), SURFACE)
        self.assertEqual(glass["mode"], "dark")

    def check_aggregates(self, doc):
        """A browser runs / needs a restart when one of its profiles does;
        the top-level restart_needed covers every browser."""
        for browser in doc["browsers"]:
            self.assertEqual(browser["running"], any(p["running"] for p in browser["profiles"]))
            self.assertEqual(browser["restart_needed"],
                             any(p["restart_needed"] for p in browser["profiles"]))
            for profile in browser["profiles"]:
                if profile["restart_needed"]:
                    self.assertTrue(profile["running"], "restart_needed on a closed profile")
        if any(b["restart_needed"] for b in doc["browsers"]):
            self.assertTrue(doc["restart_needed"])


class StatusTest(BlackBoxCase):

    def test_before_sync(self):
        self.build_home()
        doc = self.status()
        self.assertRegex(doc["version"], r"^[0-9]+\.[0-9]+\.[0-9]+$")
        found = self.check_layout(doc)
        self.check_glass_inputs(doc)
        self.check_aggregates(doc)
        self.assertEqual(doc["niri"], {"config": True, "include": False, "rule": False})
        self.assertFalse(doc["restart_needed"])
        for _, profile in found.values():
            self.assertFalse(profile["applied"], profile["name"])
            self.assertFalse(profile["running"], profile["name"])
            self.assertFalse(profile["restart_needed"], profile["name"])
        self.assertEqual(doc["warnings"], [])
        self.assertEqual(self.status(), doc, "status is not deterministic")

    def test_no_niri_config(self):
        self.build_home()
        os.remove(str(self.fh.resolve(NIRI_CONFIG)))
        doc = self.status()
        self.assertEqual(doc["niri"], {"config": False, "include": False, "rule": False})

    def test_empty_home(self):
        doc = self.status()
        self.assertEqual(doc["browsers"], [])
        self.assertFalse(doc["restart_needed"])
        self.assertEqual(doc["niri"], {"config": False, "include": False, "rule": False})

    def test_after_sync(self):
        self.build_home()
        self.sync()
        doc = self.status()
        found = self.check_layout(doc)
        self.check_glass_inputs(doc)
        self.check_aggregates(doc)
        self.assertTrue(doc["glass"]["active"])
        self.assertEqual(doc["glass"]["reason"], "active")
        self.assertEqual(doc["niri"], {"config": True, "include": True, "rule": True})
        self.assertFalse(doc["restart_needed"], "no browser runs")
        for _, profile in found.values():
            self.assertTrue(profile["applied"], profile["name"])
            self.assertFalse(profile["running"], profile["name"])
            self.assertFalse(profile["restart_needed"], profile["name"])
        self.assertEqual(self.status(), doc, "status is not deterministic")

    def test_after_uninstall(self):
        self.build_home()
        self.sync()
        self.uninstall()
        doc = self.status()
        found = self.check_layout(doc)
        self.check_glass_inputs(doc)
        self.check_aggregates(doc)
        self.assertEqual(doc["niri"], {"config": True, "include": False, "rule": False})
        self.assertFalse(doc["restart_needed"])
        for _, profile in found.values():
            self.assertFalse(profile["applied"], profile["name"])
            self.assertFalse(profile["restart_needed"], profile["name"])
        self.assertFalse(self.fh.exists(".local/state/dms/browserGlass"))

    def test_running_before_any_sync(self):
        self.build_home()
        self.browser(FF_MAIN)
        doc = self.status()
        found = self.profiles(doc)
        self.check_aggregates(doc)
        browser, profile = found[self.pid(FF_MAIN)]
        self.assertTrue(profile["running"])
        self.assertTrue(browser["running"])
        self.assertFalse(profile["restart_needed"], "nothing was written yet")
        self.assertFalse(doc["restart_needed"])
        others = [p for pid, (_, p) in found.items() if pid != self.pid(FF_MAIN)]
        self.assertFalse(any(p["running"] for p in others))

    def test_running_while_synced_needs_restart(self):
        self.build_home()
        self.browser(FF_MAIN)
        out = self.sync()
        self.assertIn(self.pid(FF_MAIN), out["running_changed"])
        doc = self.status()
        found = self.profiles(doc)
        self.check_aggregates(doc)
        browser, profile = found[self.pid(FF_MAIN)]
        self.assertTrue(profile["running"])
        self.assertTrue(profile["restart_needed"])
        self.assertTrue(profile["applied"])
        self.assertTrue(browser["running"])
        self.assertTrue(browser["restart_needed"])
        self.assertTrue(doc["restart_needed"])
        for pid, (other_browser, other) in found.items():
            if pid == self.pid(FF_MAIN):
                continue
            self.assertFalse(other["running"], other["name"])
            self.assertFalse(other["restart_needed"], other["name"])
            if other_browser["family"] != "firefox" or other_browser["variant"] != "native":
                self.assertFalse(other_browser["restart_needed"])

    def test_restart_clears_restart_needed(self):
        self.build_home()
        holder = self.browser(FF_MAIN)
        self.sync()
        self.assertTrue(self.status()["restart_needed"])
        holder.release()
        holder.stop()
        doc = self.status()
        self.assertFalse(doc["restart_needed"], "the browser is closed")
        self.browser(FF_MAIN)                    # starts again: loads the current files
        doc = self.status()
        _, profile = self.profiles(doc)[self.pid(FF_MAIN)]
        self.assertTrue(profile["running"])
        self.assertFalse(profile["restart_needed"], "started after the files were written")
        self.assertFalse(doc["restart_needed"])

    def test_started_after_sync_needs_no_restart(self):
        self.build_home()
        self.sync()
        self.browser(FF_WORK)
        doc = self.status()
        browser, profile = self.profiles(doc)[self.pid(FF_WORK)]
        self.assertTrue(profile["running"])
        self.assertTrue(browser["running"])
        self.assertFalse(profile["restart_needed"])
        self.assertFalse(doc["restart_needed"])

    def test_held_niri_rule_counts_as_restart_needed(self):
        # H1: glass turned off while a running browser still has it loaded:
        # the niri rule stays, status shows it and asks for a restart.
        self.build_home()
        self.sync()
        self.browser(FF_MAIN)                    # starts with glass loaded
        self.sync()                              # sees the new instance
        out = self.sync(settings(blur=False))
        self.assertEqual(out["reason"], "blur_disabled")
        doc = self.status()
        self.check_aggregates(doc)
        self.assertFalse(doc["glass"]["active"])
        self.assertNotEqual(doc["glass"]["reason"], "active")
        self.assertTrue(doc["niri"]["rule"], "the held rule is still on disk")
        self.assertTrue(doc["restart_needed"])
        _, profile = self.profiles(doc)[self.pid(FF_MAIN)]
        self.assertTrue(profile["running"])

    def test_glass_off_reason(self):
        self.build_home()
        self.sync(settings(glassEnabled=False))
        doc = self.status()
        self.assertFalse(doc["glass"]["active"])
        self.assertEqual(doc["glass"]["reason"], "toggled_off")
        self.assertFalse(doc["niri"]["rule"])
        self.assertFalse(doc["restart_needed"])


class ZenTest(BlackBoxCase):
    """H9: a Zen transparency mod is reported as a warning, nothing broken."""

    def test_transparency_mod_warns(self):
        self.build_home(zen_mods=ZEN_MOD_TRANSPARENT)
        mods = self.fh.read(ZEN_PROFILE + "/chrome/zen-themes.json")
        doc = self.status()
        zen = [w for w in doc["warnings"] if w["code"] == "zen_transparency_mod"]
        self.assertEqual(len(zen), 1, doc["warnings"])
        self.assertEqual(zen[0]["family"], "zen")
        self.assertEqual(zen[0]["profile"], self.pid(ZEN_PROFILE))
        self.assertNotIn("alice", zen[0]["message"].lower())
        self.assertIn("zen_transparency_mod", self.report())
        # A sync goes on and leaves the mod alone.
        out = self.sync()
        self.assertIn(self.pid(ZEN_PROFILE), out["changed"])
        self.assertEqual(self.fh.read(ZEN_PROFILE + "/chrome/zen-themes.json"), mods)
        after = self.status()
        self.assertTrue(any(w["code"] == "zen_transparency_mod" for w in after["warnings"]))
        _, profile = self.profiles(after)[self.pid(ZEN_PROFILE)]
        self.assertTrue(profile["applied"])

    def test_other_mod_does_not_warn(self):
        self.build_home(zen_mods=ZEN_MOD_OTHER)
        doc = self.status()
        self.assertEqual([w for w in doc["warnings"] if w["code"] == "zen_transparency_mod"], [])
        self.assertNotIn("zen_transparency_mod", self.report())

    def test_corrupt_mods_file_is_harmless(self):
        self.build_home()
        self.fh.write(ZEN_PROFILE + "/chrome/zen-themes.json", "{not json")
        doc = self.status()
        self.assertEqual([w for w in doc["warnings"] if w["code"] == "zen_transparency_mod"], [])
        self.report()


class ReportTest(BlackBoxCase):
    """The report is anonymous: no account name, home path, profile name,
    profile folder, profile id or hostname."""

    def forbidden(self):
        fh = self.fh
        tokens = {"alice", str(fh.home), str(fh.root), os.path.basename(str(fh.root)),
                  str(REAL_HOME)}
        try:
            tokens.add(getpass.getuser())
        except Exception:
            pass
        for root, folder, name, _ in PROFILES:
            path = fh.resolve(root + "/" + folder)
            pid = contract_id(path)
            tokens.update((folder, name, folder.split(".", 1)[0], pid,
                           hashlib.sha256(os.fsencode(os.path.realpath(str(path)))).hexdigest()))
        for host in (socket.gethostname(), os.uname().nodename):
            if host:
                tokens.add(host)
                tokens.add(host.split(".", 1)[0])
        return sorted(t.lower() for t in tokens if t and len(t) >= 3)

    def check_anonymous(self, text):
        low = text.lower()
        for token in self.forbidden():
            self.assertNotIn(token, low, "report leaks %r:\n%s" % (token, text))
        self.assertIsNone(re.search(r"~|(^|[\s(=])/[^\s/]", text, re.M), "report shows a path:\n" + text)
        self.assertNotIn("://", text)

    def test_before_sync(self):
        self.build_home()
        text = self.report()
        self.check_anonymous(text)
        self.assertEqual(self.report_profiles(text), {
            ("firefox", "native"): (2, 0, 0),
            ("firefox", "flatpak"): (1, 0, 0),
            ("librewolf", "native"): (1, 0, 0),
            ("zen", "native"): (1, 0, 0),
        })
        version = text.splitlines()[1][len(REPORT_LINES[1]):]
        self.assertEqual(version, self.status()["version"])

    def test_after_sync_with_a_running_browser(self):
        self.build_home(zen_mods=ZEN_MOD_TRANSPARENT)
        self.browser(FF_MAIN)
        self.sync()
        text = self.report()
        self.check_anonymous(text)
        self.assertEqual(self.report_profiles(text), {
            ("firefox", "native"): (2, 1, 1),
            ("firefox", "flatpak"): (1, 0, 0),
            ("librewolf", "native"): (1, 0, 0),
            ("zen", "native"): (1, 0, 0),
        })
        self.assertIn("zen_transparency_mod", text)
        glass = [line for line in text.splitlines() if line.startswith(REPORT_LINES[3])]
        self.assertEqual(len(glass), 1)
        self.assertTrue(glass[0].startswith(REPORT_LINES[3] + "active"), glass[0])

    def test_after_uninstall(self):
        self.build_home()
        self.sync()
        self.uninstall()
        self.check_anonymous(self.report())

    def test_empty_home(self):
        text = self.report()
        self.check_anonymous(text)
        self.assertEqual(self.report_profiles(text), {})

    def test_deterministic(self):
        self.build_home()
        self.sync()
        self.assertEqual(self.report(), self.report())


# A small styles.json / css-mapping.json pair in my-internet's layout.
STYLES = {
    "website": {
        "github.com.css": {"transparency": "body { background: none !important; }"},
        "+github.com.css": {"transparency": "header { background: none !important; }"},
        "+wikipedia.org.css": {"glass": "body { background: none !important; }"},
        "-google.com.css": {"translucent": "body { background: none !important; }"},
        "youtube.com.css": {"transparency": "ytd-app { background: none !important; }"},
        "www.example.org.css": {"transparency": "main { background: none !important; }"},
        " spaced.net .css": {"transparency": "main { background: none !important; }"},
        "colors-only.com.css": {"colors": "body { color: red !important; }"},
        "example.com.css": {"transparency": "html, body { background: none !important; }"},
        "Bad Name!.css": {"transparency": "body { background: none !important; }"},
    },
}
MAPPING = {
    "youtube.com.css": ["youtube-nocookie.com", "-bad-target.com"],
    "example.com.css": ["generic.example.net"],
}
EXPECTED_SITES = {
    "github.com": ["github.com", "*.github.com"],
    "+wikipedia.org": ["wikipedia.org", "*.wikipedia.org"],
    "-google.com": ["google.*", "www.google.*"],
    "youtube.com": ["youtube.com", "*.youtube.com", "youtube-nocookie.com"],
    "www.example.org": ["example.org", "*.example.org"],
    "spaced.net": ["spaced.net", "*.spaced.net"],
}


class SitesTest(BlackBoxCase):

    def data_dir(self, styles=STYLES, mapping=MAPPING):
        folder = self.fh.root / "data"
        folder.mkdir(exist_ok=True)
        (folder / "styles.json").write_text(json.dumps(styles, indent=2) + "\n", encoding="utf-8")
        if mapping is not None:
            (folder / "css-mapping.json").write_text(json.dumps(mapping, indent=2) + "\n",
                                                     encoding="utf-8")
        return folder

    def sites(self, *extra, code=0):
        proc = self.read_only(["sites", "--json"] + [str(a) for a in extra], code=code)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        doc = json.loads(lines[0])
        spec = SCHEMA["sites"] if code == 0 else SCHEMA["error"]
        self.assertEqual(test_contract.validate(doc, spec, DEFS), [], lines[0])
        return doc

    def by_name(self, doc):
        out = {}
        for row in doc:
            self.assertNotIn(row["name"], out, "duplicate style %r" % row["name"])
            out[row["name"]] = row["domains"]
        return out

    def test_with_data(self):
        self.build_home()
        doc = self.sites("--data", self.data_dir())
        self.assertEqual(self.by_name(doc), EXPECTED_SITES)
        self.assertEqual(self.sites("--data", self.data_dir()), doc, "order is not stable")

    def test_without_mapping_file(self):
        self.build_home()
        doc = self.sites("--data", self.data_dir(mapping=None))
        expected = dict(EXPECTED_SITES, **{"youtube.com": ["youtube.com", "*.youtube.com"]})
        self.assertEqual(self.by_name(doc), expected)

    def test_with_embedded_data(self):
        doc = self.sites("--data", REPO / "data")
        names = self.by_name(doc)
        self.assertGreater(len(names), 300)
        self.assertNotIn("example.com", names, "the generic style is not a dedicated one")

    def test_without_data(self):
        # The script cannot find its own data (it never looks up its own
        # path): either no styles, or the contract's error line.
        self.build_home()
        before = tree(str(self.fh.root))
        proc = self.fh.run_script(["sites", "--json"], extra_env=FAST)
        self.assertEqual(tree(str(self.fh.root)), before, "sites modified the fake home")
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, "stdout %r stderr %r" % (proc.stdout, proc.stderr))
        doc = json.loads(lines[0])
        if proc.returncode == 0:
            self.assertEqual(doc, [])
        else:
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], lines[0])

    def test_missing_data_dir_is_an_error(self):
        self.build_home()
        doc = self.sites("--data", self.fh.root / "no-such-dir", code=1)
        self.assertIn("error", doc)

    def test_corrupt_styles_is_an_error(self):
        folder = self.fh.root / "data"
        folder.mkdir()
        (folder / "styles.json").write_text("{nope", encoding="utf-8")
        self.sites("--data", folder, code=1)

    def test_corrupt_mapping_is_ignored(self):
        folder = self.data_dir()
        (folder / "css-mapping.json").write_text("[broken", encoding="utf-8")
        doc = self.sites("--data", folder)
        self.assertEqual(self.by_name(doc)["youtube.com"], ["youtube.com", "*.youtube.com"])

    def test_after_sync_and_uninstall(self):
        self.build_home()
        data = self.data_dir()
        self.sync()
        self.assertEqual(self.by_name(self.sites("--data", data)), EXPECTED_SITES)
        self.uninstall()
        self.assertEqual(self.by_name(self.sites("--data", data)), EXPECTED_SITES)


class UsageTest(BlackBoxCase):

    def test_status_requires_json(self):
        proc = self.read_only(["status"], code=2)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], proc.stdout)

    def test_sites_requires_json(self):
        proc = self.read_only(["sites"], code=2)
        doc = json.loads(proc.stdout)
        self.assertEqual(test_contract.validate(doc, SCHEMA["error"], DEFS), [], proc.stdout)


if __name__ == "__main__":
    unittest.main()

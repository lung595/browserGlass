"""Shared fixtures of the companion end-to-end tests (test_e2e_live.py,
test_e2e_sideload.py): a throwaway browser whose profile sits where
browserglass.py looks for it in the fake HOME, and the browserglass.py
subprocesses run against that HOME.

Not a test file (unittest discovery only picks test_e2e*.py).
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "browserglass.py")
DATA = os.path.join(REPO, "data")
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402

COMPANION_ID = "browserglass@companion"
OFF = "data-browserglass-off"
LIVE = "data-browserglass-live"
OPACITY = 0.8

# What browserGlass manages in its user.js block: left out of the user's own
# user.js (the harness prefs).
MANAGED_PREFS = (
    "toolkit.legacyUserProfileCustomizations.stylesheets",
    "browser.tabs.allow_transparent_browser",
    "layout.css.prefers-color-scheme.content-override",
)
COMPANION_PREFS = (
    "xpinstall.signatures.required",
    "extensions.autoDisableScopes",
    "extensions.startupScanScopes",
)

WINDOW_RULES = (
    "// DMS Window Rules - Managed by DMS\n"
    "window-rule {\n"
    "    opacity %s\n"
    "}\n" % OPACITY
)
DMS_COLORS = {"mode": "dark", "colors": {"dark": {"surface": "#102030"},
                                         "light": {"surface": "#f0f2f8"}}}

SETTINGS = {
    "blur": True, "isLight": False, "glassEnabled": True, "opacityOverride": False,
    "opacity": 0.85, "siteTheme": "follow", "pagesTransparent": True,
    "genericStyle": True, "excluded": [], "disabledStyles": [], "newTabGlass": True,
    "readerOpaque": True, "privateGlass": False, "liveControl": True,
    "darkPages": False,
}

SCOPE_PROFILE = 1  # AddonManager.SCOPE_PROFILE: the profile's extensions/ folder
ADDON_JS = (
    "const {AddonManager} = ChromeUtils.importESModule("
    "  'resource://gre/modules/AddonManager.sys.mjs');"
    "return AddonManager.getAddonByID(arguments[0]).then((a) => a ? {"
    "  active: a.isActive, temporary: a.temporarilyInstalled, scope: a.scope} : null);"
)


def user_js_prefs(text):
    """{pref: raw JS value} of the user_pref lines of `text` (last wins)."""
    out = {}
    for m in re.finditer(r'^\s*user_pref\("([^"]+)",\s*(.*?)\);\s*$', text, re.M):
        out[m.group(1)] = m.group(2)
    return out


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


class Home:
    """A throwaway browser (manage_user_js=False) whose profile is
    <root_rel>/<name> of its fake HOME, listed in profiles.ini, with the
    harness prefs as the user's own user.js and a fake DMS (opacity rule,
    colour file) so that sync finds glass active."""

    def __init__(self, browser, root_rel, name, dark=True):
        self.browser = b = browser
        self.home = b.home
        self.profile = os.path.join(b.home, root_rel, name)
        b.profile = self.profile
        os.makedirs(self.profile, mode=0o700)
        b.prefs = {k: v for k, v in b.prefs.items() if k not in MANAGED_PREFS}
        if dark:
            b.prefs["ui.systemUsesDarkTheme"] = 1
        self.env = dict(b.env, PYTHONDONTWRITEBYTECODE="1")
        self.write(os.path.join(root_rel, "profiles.ini"),
                   "[Profile0]\nName=e2e\nIsRelative=1\nPath=%s\nDefault=1\n\n"
                   "[General]\nStartWithLastProfile=1\nVersion=2\n" % name)
        self.write(os.path.join(root_rel, name, "user.js"), "// the user's own user.js\n" + "".join(
            "user_pref(%s, %s);\n" % (json.dumps(k), json.dumps(v)) for k, v in sorted(b.prefs.items())))
        self.write(".config/niri/config.kdl", "// fake niri config\n")
        self.write(".config/niri/dms/windowrules.kdl", WINDOW_RULES)
        self.write(".cache/dms/dms-colors.json", json.dumps(DMS_COLORS))

    def write(self, rel, text, mode=None):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if mode is not None:
            os.chmod(path, mode)
        return path

    # ---- browserglass.py ----------------------------------------------------

    def run(self, args, stdin_bootstrap=False):
        """One browserglass.py command; its JSON line, decoded."""
        if stdin_bootstrap:
            with open(SCRIPT, encoding="utf-8") as f:
                text = f.read()
            bootstrap = re.search(r'^STDIN_BOOTSTRAP = "(.*)"$', text, re.M).group(1)
            argv = [sys.executable, "-I", "-B", "-c", bootstrap] + args
        else:
            text = None
            argv = [sys.executable, "-I", "-B", SCRIPT] + args
        proc = subprocess.run(argv, input=text, env=self.env, cwd=self.browser.root,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=120)
        if proc.returncode != 0 or proc.stdout.count("\n") != 1:
            raise AssertionError("%s failed (%d):\n%s%s" % (args[0], proc.returncode,
                                                             proc.stdout, proc.stderr))
        return json.loads(proc.stdout)

    def sync(self, excluded=(), plugin_dir=True, **settings):
        doc = dict(SETTINGS, excluded=list(excluded), **settings)
        args = ["sync", "--data", DATA, "--settings", json.dumps(doc)]
        if plugin_dir:
            args += ["--plugin-dir", REPO]
        return self.run(args)

    def status(self):
        return self.run(["status", "--json"])

    def profile_status(self, doc):
        """This profile's entry in a status document."""
        for browser in doc["browsers"]:
            for p in browser["profiles"]:
                if os.path.realpath(os.path.join(self.home, p["path"][2:])) == os.path.realpath(self.profile):
                    return p
        raise AssertionError("profile not in status: %r" % doc)

    # ---- files --------------------------------------------------------------

    @property
    def xpi(self):
        return os.path.join(self.profile, "extensions", COMPANION_ID + ".xpi")

    @property
    def manifest(self):
        return os.path.join(self.home, ".mozilla", "native-messaging-hosts", "browserglass.json")

    @property
    def runtime(self):
        return os.path.join(self.env["XDG_RUNTIME_DIR"], "browserGlass")

    def block_prefs(self):
        """{pref: raw value} of the user.js lines browserGlass wrote."""
        text = read(os.path.join(self.profile, "user.js")) or ""
        start = text.find("// >>> browserGlass v1 managed block")
        end = text.find("// <<< browserGlass v1", start)
        return user_js_prefs(text[start:end]) if 0 <= start < end else {}

    def prefs_js(self):
        return user_js_prefs(read(os.path.join(self.profile, "prefs.js")) or "")

    # ---- browser ------------------------------------------------------------

    def addon(self):
        """{active, temporary, scope} of the companion add-on in the
        running browser, None when it is not installed."""
        return self.browser.chrome_js(ADDON_JS, COMPANION_ID)

    def host_pids(self):
        """Pids of the native hosts started for this browser (their command
        line names the manifest of the fake HOME), zombies left out."""
        out = []
        root = self.browser.root.encode()
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % name, "rb") as f:
                    cmd = f.read()
                with open("/proc/%s/stat" % name, "rb") as f:
                    zombie = f.read().rsplit(b")", 1)[1].split()[0] == b"Z"
            except OSError:
                continue
            if b"native-host" in cmd and root in cmd and not zombie:
                out.append(int(name))
        return sorted(out)

    def wait(self, predicate, timeout=10.0, step=0.05):
        """The first truthy predicate() within `timeout` seconds, else None."""
        deadline = time.monotonic() + timeout
        while True:
            value = predicate()
            if value:
                return value
            if time.monotonic() > deadline:
                return None
            time.sleep(step)

    def quit(self, timeout=30.0):
        """Quit the browser the way a user does (no signal to its process
        group, unlike Browser.stop): its native host sees the end of stdin."""
        b = self.browser
        try:
            b.client.sock.settimeout(10)
            b.client.send("Marionette:Quit", {"flags": ["eAttemptQuit"]})
        except Exception:
            pass
        b.client.close()
        b.client = None
        try:
            b.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(b.proc.pid, signal.SIGKILL)
            b.proc.wait(timeout=10)
            raise AssertionError("the browser did not quit")
        b.proc = None

#!/usr/bin/env python3
"""Headless Firefox end-to-end harness for browserGlass (stdlib only).

Launches a throwaway Firefox (fake HOME, generated profile, Marionette on a
free port), serves local test pages (an article and a small PDF) from
127.0.0.1, and measures computed styles to validate the CSS selectors that
browserGlass generates.

Reusable API (for later phases):

    with TestServer() as srv, Browser(chrome_css=..., content_css=...) as b:
        b.navigate(srv.url("/article.html"))
        b.css("body", "background-color")      # -> {"background-color": "..."}
        b.chrome_windows()                     # chrome-level info per window

CLI: ``python3 tests/e2e/marionette.py`` runs the selector spike and prints a
result table; exit status is 1 when a check fails, 2 on a harness error
(or a BG_FIREFOX that is not an executable), 0 with "SKIP: firefox not found"
when no Firefox binary is available.

Firefox only ever sees a fake HOME: its environment is built from scratch
(fake HOME/XDG_*/TMPDIR, PATH without real-home entries) and checked for
real-home paths before launch. Every Firefox started is killed and its
throwaway directory removed on exit, Ctrl-C, SIGTERM or SIGHUP included.

Start pattern when files must be placed in the fake HOME first (native
messaging manifests, sideloaded add-ons): create the Browser without `with`,
write into ``b.home`` / ``b.profile``, then ``b.start()``, and always
``b.cleanup()`` in a ``finally`` block.

Environment:
    BG_FIREFOX    path to the Firefox binary (default: auto-detect)
    BG_LIBREWOLF  path to a LibreWolf binary, for the sideload tests (no
                  default: those tests are skipped when it is unset)
    TMPDIR        where the throwaway HOME/profile is created
"""

import atexit
import json
import os
import pwd
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STARTUP_TIMEOUT = 90.0
COMMAND_TIMEOUT = 60.0
WAIT_TIMEOUT = 30.0

# Distro wrappers (/usr/bin/firefox on Fedora is a bash script that runs
# restorecon / mkdir under $HOME); prefer the real binary when present.
FIREFOX_CANDIDATES = (
    "/usr/lib64/firefox/firefox",
    "/usr/lib/firefox/firefox",
    "/opt/firefox/firefox",
)

BASE_PREFS = {
    # first run / startup
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "startup.homepage_welcome_url": "",
    "startup.homepage_welcome_url.additional": "",
    "browser.aboutwelcome.enabled": False,
    "browser.startup.firstrunSkipsHomepage": True,
    "browser.startup.page": 0,
    "browser.startup.homepage": "about:blank",
    "startup.homepage_override_url": "",
    "browser.newtabpage.pinned": "[]",
    "browser.policies.perUserDir": False,
    "browser.sessionstore.resume_from_crash": False,
    "browser.tabs.warnOnClose": False,
    "browser.warnOnQuit": False,
    "intl.locale.requested": "en-US",
    # no helper daemons (reader mode's Narrate would spawn speech-dispatcher,
    # which detaches from Firefox's process group)
    "media.webspeech.synth.enabled": False,
    "narrate.enabled": False,
    # telemetry / studies
    "datareporting.policy.dataSubmissionEnabled": False,
    "datareporting.healthreport.uploadEnabled": False,
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.unified": False,
    "toolkit.telemetry.archive.enabled": False,
    "toolkit.telemetry.server": "",
    "app.normandy.enabled": False,
    "app.shield.optoutstudies.enabled": False,
    "browser.discovery.enabled": False,
    # updates
    "app.update.disabledForTesting": True,
    "app.update.auto": False,
    "extensions.update.enabled": False,
    "extensions.blocklist.enabled": False,
    "browser.search.update": False,
    # network-ish
    # Black-hole proxy: anything but 127.0.0.1/localhost (always bypassed
    # while allow_hijacking_localhost is false) goes to a dead port.
    "network.proxy.type": 1,
    "network.proxy.http": "127.0.0.1",
    "network.proxy.http_port": 9,
    "network.proxy.ssl": "127.0.0.1",
    "network.proxy.ssl_port": 9,
    "network.proxy.socks": "127.0.0.1",
    "network.proxy.socks_port": 9,
    "network.proxy.no_proxies_on": "",
    "network.proxy.allow_hijacking_localhost": False,
    "network.proxy.socks_remote_dns": True,
    "network.trr.mode": 5,
    "network.manage-offline-status": False,
    "toolkit.networkmanager.disable": True,
    "network.captive-portal-service.enabled": False,
    "network.connectivity-service.enabled": False,
    "network.dns.disablePrefetch": True,
    "network.prefetch-next": False,
    "network.http.speculative-parallel-limit": 0,
    "browser.safebrowsing.malware.enabled": False,
    "browser.safebrowsing.phishing.enabled": False,
    "browser.safebrowsing.downloads.enabled": False,
    "browser.safebrowsing.blockedURIs.enabled": False,
    "browser.region.update.enabled": False,
    "browser.region.network.url": "",
    "browser.search.geoip.url": "",
    "services.settings.server": "http://127.0.0.1:9/",
    "messaging-system.rsexperimentloader.enabled": False,
    "browser.newtabpage.activity-stream.feeds.section.topstories": False,
    "browser.newtabpage.activity-stream.feeds.system.topstories": False,
    "browser.newtabpage.activity-stream.showSponsored": False,
    "browser.newtabpage.activity-stream.showSponsoredTopSites": False,
    "browser.newtabpage.activity-stream.telemetry": False,
    "browser.newtabpage.activity-stream.feeds.telemetry": False,
    "browser.newtabpage.activity-stream.discoverystream.endpoints": "",
    "browser.ping-centre.telemetry": False,
    "dom.security.https_only_mode": False,
    "dom.security.https_only_mode_pbm": False,
    "dom.security.https_first": False,
    "dom.security.https_first_pbm": False,
    # pages under test
    "pdfjs.disabled": False,
    "browser.download.open_pdf_attachments_inline": True,
    "layout.css.prefers-color-scheme.content-override": 0,
    # what browserGlass sets
    "toolkit.legacyUserProfileCustomizations.stylesheets": True,
    "browser.tabs.allow_transparent_browser": True,
}


class MarionetteError(Exception):
    pass


# The account's real home, from the password database ($HOME may be faked)
REAL_HOME = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)

# Browsers started and not yet cleaned up (see _cleanup_all)
_LIVE = set()


def _inside(path, parent):
    path, parent = os.path.normpath(path), os.path.normpath(parent)
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def _kill_strays(root):
    """SIGKILL any process whose command line names `root` (a helper that
    left Firefox's process group); returns their pids."""
    killed = []
    root = root.encode()
    for name in os.listdir("/proc"):
        if not name.isdigit() or int(name) == os.getpid():
            continue
        try:
            with open("/proc/%s/cmdline" % name, "rb") as f:
                cmdline = f.read()
        except OSError:
            continue
        if root in cmdline:
            try:
                os.kill(int(name), signal.SIGKILL)
                killed.append(int(name))
            except (ProcessLookupError, PermissionError):
                pass
    return killed


def _cleanup_all():
    """atexit backstop: kill every Firefox still running, drop its files."""
    for b in list(_LIVE):
        try:
            b.cleanup()
        except Exception:
            pass


def _raise_exit(signum, frame):
    # Turn SIGTERM/SIGHUP into SystemExit so finally blocks and atexit run
    raise SystemExit(128 + signum)


def install_signal_handlers():
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_exit)


atexit.register(_cleanup_all)


def find_firefox():
    env = os.environ.get("BG_FIREFOX")
    if env:
        return env if os.access(env, os.X_OK) else None
    for path in FIREFOX_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    return shutil.which("firefox")


def find_librewolf():
    """The LibreWolf binary named by BG_LIBREWOLF (symlinks resolved), or
    None when unset or not executable."""
    env = os.environ.get("BG_LIBREWOLF")
    if not env:
        return None
    path = os.path.realpath(env)
    return path if os.access(path, os.X_OK) else None


def test_host_prefs(hosts):
    """Prefs that resolve each of `hosts` (names under .test) to 127.0.0.1
    and keep them away from the black-hole proxy."""
    return {"network.dns.localDomains": ",".join(hosts),
            "network.proxy.no_proxies_on": ".test"}


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fake_env(home):
    """Environment for a subprocess whose HOME and XDG dirs live in `home`.

    Built from scratch (nothing inherited but PATH, minus its entries inside
    the real home), as tests/py/fakehome.py does.
    """
    path = [p for p in os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep)
            if os.path.isabs(p) and not _inside(p, REAL_HOME)
            and not _inside(os.path.realpath(p), REAL_HOME)]
    env = {
        "PATH": os.pathsep.join(path) or "/usr/bin:/bin",
        "USER": "e2e",
        "LOGNAME": "e2e",
        "LANG": "C.UTF-8",
    }
    dirs = {
        "XDG_CONFIG_HOME": ".config",
        "XDG_CACHE_HOME": ".cache",
        "XDG_DATA_HOME": ".local/share",
        "XDG_STATE_HOME": ".local/state",
        "XDG_RUNTIME_DIR": "run",
    }
    for key, rel in dirs.items():
        path = os.path.join(home, rel)
        os.makedirs(path, mode=0o700, exist_ok=True)
        env[key] = path
    tmp = os.path.join(home, "tmp")
    os.makedirs(tmp, mode=0o700, exist_ok=True)
    env.update(HOME=home, TMPDIR=tmp, MOZ_HEADLESS="1",
               MOZ_CRASHREPORTER_DISABLE="1", MOZ_DISABLE_AUTO_SAFE_MODE="1",
               DBUS_SESSION_BUS_ADDRESS="disabled:",
               MOZ_REMOTE_ALLOW_SYSTEM_ACCESS="1")
    return env


def env_leaks(env, allowed_root):
    """Variables of `env` naming a real-home path outside `allowed_root`.

    The throwaway directory may itself sit under the real home (TMPDIR), so
    paths inside it are allowed; anything else under the real home is a leak.
    """
    allowed = os.path.realpath(allowed_root)
    found = []
    for key, value in env.items():
        for part in str(value).split(os.pathsep):
            if not os.path.isabs(part):
                continue
            real = os.path.realpath(part)
            if ((_inside(part, REAL_HOME) or _inside(real, REAL_HOME))
                    and not _inside(real, allowed)):
                found.append(key)
                break
    return found


def write_user_js(profile, prefs):
    lines = ["user_pref(%s, %s);" % (json.dumps(k), json.dumps(v))
             for k, v in sorted(prefs.items())]
    with open(os.path.join(profile, "user.js"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_profile_css(profile, chrome=None, content=None):
    """Write userChrome.css / userContent.css (None removes the file)."""
    d = os.path.join(profile, "chrome")
    os.makedirs(d, exist_ok=True)
    for name, text in (("userChrome.css", chrome), ("userContent.css", content)):
        path = os.path.join(d, name)
        if text is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)


class Marionette:
    """Minimal Marionette protocol client ('len:{json}' framing, protocol 3)."""

    def __init__(self, port, timeout=COMMAND_TIMEOUT):
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.msg_id = 0
        self.handshake = None

    def connect(self, deadline, alive=lambda: True):
        last = None
        while time.monotonic() < deadline:
            if not alive():
                raise MarionetteError("firefox exited during startup")
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                s.settimeout(self.timeout)
                self.sock = s
                self.handshake = self._recv()
                return self.handshake
            except (OSError, MarionetteError) as e:
                last = e
                if self.sock:
                    self.sock.close()
                    self.sock = None
                time.sleep(0.25)
        raise MarionetteError("marionette not reachable on port %d: %s" % (self.port, last))

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _read_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise MarionetteError("connection closed")
            buf += chunk
        return buf

    def _recv(self):
        head = b""
        while not head.endswith(b":"):
            c = self.sock.recv(1)
            if not c:
                raise MarionetteError("connection closed")
            head += c
            if len(head) > 12:
                raise MarionetteError("bad frame header %r" % head)
        return json.loads(self._read_exact(int(head[:-1])).decode("utf-8"))

    def send(self, name, params=None):
        self.msg_id += 1
        data = json.dumps([0, self.msg_id, name, params or {}]).encode("utf-8")
        self.sock.sendall(str(len(data)).encode("ascii") + b":" + data)
        while True:
            msg = self._recv()
            if isinstance(msg, list) and len(msg) == 4 and msg[0] == 1 and msg[1] == self.msg_id:
                break
        if msg[2]:
            err = msg[2]
            raise MarionetteError("%s: %s: %s" % (name, err.get("error"), err.get("message")))
        return msg[3]


class Browser:
    """A throwaway headless Firefox driven over Marionette."""

    def __init__(self, chrome_css=None, content_css=None, prefs=None,
                 firefox=None, base_dir=None, manage_user_js=True,
                 recommended_prefs=True):
        """manage_user_js=False: start() leaves user.js alone (the caller
        writes it, with self.prefs["marionette.port"], before starting); the
        port is then chosen once and kept across restarts.

        recommended_prefs=False writes remote.prefs.recommended=false:
        required by every sideload test, since Marionette otherwise forces
        extensions.autoDisableScopes=0 and extensions.enabledScopes=5."""
        self.firefox = firefox or find_firefox()
        if not self.firefox:
            raise FileNotFoundError("firefox not found")
        # LibreWolf refuses WebDriver:NewWindow; windows go through chrome
        self.librewolf = "librewolf" in os.path.basename(self.firefox).lower()
        self.root = tempfile.mkdtemp(prefix="bg-e2e-", dir=base_dir)
        self.home = os.path.join(self.root, "home")
        self.profile = os.path.join(self.root, "profile")
        os.makedirs(self.home, mode=0o700)
        os.makedirs(self.profile, mode=0o700)
        self.env = fake_env(self.home)
        leaks = env_leaks(self.env, self.root)
        if leaks:
            shutil.rmtree(self.root, ignore_errors=True)
            raise MarionetteError("environment names the real home: " + ", ".join(sorted(leaks)))
        self.prefs = dict(BASE_PREFS)
        if not recommended_prefs:
            self.prefs["remote.prefs.recommended"] = False
        self.prefs.update(prefs or {})
        self.manage_user_js = manage_user_js
        if not manage_user_js:
            self.prefs["marionette.port"] = free_port()
        self.proc = None
        self.client = None
        self.context = "content"
        self.log_path = os.path.join(self.root, "firefox.log")
        write_profile_css(self.profile, chrome_css, content_css)

    # ---- lifecycle ----
    def start(self):
        if self.manage_user_js:
            self.prefs["marionette.port"] = free_port()
            write_user_js(self.profile, self.prefs)
        port = self.prefs["marionette.port"]
        _LIVE.add(self)
        with open(self.log_path, "ab") as log:
            self.proc = subprocess.Popen(
                [self.firefox, "--headless", "--marionette", "-remote-allow-system-access",
                 "-no-remote", "-new-instance", "-profile", self.profile, "about:blank"],
                env=self.env, cwd=self.root, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.client = Marionette(port)
        self.client.connect(time.monotonic() + STARTUP_TIMEOUT,
                            alive=lambda: self.proc.poll() is None)
        self.client.send("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {}}})
        self.client.send("WebDriver:SetTimeouts",
                         {"script": int(WAIT_TIMEOUT * 1000), "pageLoad": int(WAIT_TIMEOUT * 1000)})
        self.context = "content"
        return self

    def stop(self):
        if self.client:
            try:
                self.client.sock.settimeout(5)
                self.client.send("Marionette:Quit", {"flags": ["eForceQuit"]})
            except Exception:
                pass
            self.client.close()
            self.client = None
        if self.proc:
            if self.proc.poll() is None:
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(self.proc.pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                try:
                    self.proc.wait(timeout=10)
                    break
                except subprocess.TimeoutExpired:
                    continue
            self.proc = None

    def cleanup(self):
        try:
            self.stop()
        finally:
            _kill_strays(self.root)
            shutil.rmtree(self.root, ignore_errors=True)
            _LIVE.discard(self)

    def restart(self):
        self.stop()
        return self.start()

    def write_profile_css(self, chrome=None, content=None):
        """Replace the profile stylesheets; restarts Firefox if running
        (user stylesheets are only read at startup)."""
        write_profile_css(self.profile, chrome, content)
        if self.proc:
            self.restart()

    def __enter__(self):
        try:
            return self.start()
        except BaseException:
            self.cleanup()
            raise

    def __exit__(self, *exc):
        self.cleanup()

    def log_tail(self, n=40):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return "".join(f.readlines()[-n:])
        except OSError:
            return ""

    # ---- protocol helpers ----
    def send(self, name, params=None):
        return self.client.send(name, params)

    def set_context(self, ctx):
        if ctx != self.context:
            self.send("Marionette:SetContext", {"value": ctx})
            self.context = ctx

    def navigate(self, url):
        """WebDriver:Navigate; falls back to a chrome-side load for privileged
        about: pages that Marionette refuses (e.g. about:reader)."""
        self.set_context("content")
        try:
            self.send("WebDriver:Navigate", {"url": url})
        except MarionetteError as e:
            if "not allowed" not in str(e):
                raise
            self.load_privileged(url)

    def load_privileged(self, url, timeout=WAIT_TIMEOUT):
        self.chrome_js(
            "gBrowser.selectedBrowser.fixupAndLoadURIString(arguments[0], {"
            "  triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal() });", url)
        if not self.wait_for("return document.URL === arguments[0]"
                             " && document.readyState === 'complete';", timeout, url):
            raise MarionetteError("timed out loading %s" % url)

    def js(self, script, *args):
        """Run `script` (a function body) in the current content document."""
        self.set_context("content")
        return self.send("WebDriver:ExecuteScript", {"script": script, "args": list(args)})["value"]

    def chrome_js(self, script, *args):
        """Run `script` in the chrome (browser.xhtml) context."""
        self.set_context("chrome")
        try:
            return self.send("WebDriver:ExecuteScript", {"script": script, "args": list(args)})["value"]
        finally:
            self.set_context("content")

    def wait_for(self, script, timeout=WAIT_TIMEOUT, *args):
        deadline = time.monotonic() + timeout
        while True:
            try:
                if self.js(script, *args):
                    return True
            except MarionetteError:
                pass
            if time.monotonic() > deadline:
                return False
            time.sleep(0.2)

    def css(self, selector, *props, pseudo=None):
        """Computed style values of the first element matching `selector`
        (None if no match). Custom properties (--x) are supported."""
        return self.js(
            "const [sel, props, pseudo] = arguments;"
            "const el = document.querySelector(sel); if (!el) return null;"
            "const cs = getComputedStyle(el, pseudo);"
            "const out = {}; for (const p of props) out[p] = cs.getPropertyValue(p).trim();"
            "return out;", selector, list(props), pseudo)

    def new_window(self, private=False):
        """Open a new top-level window, switch to it, return its handle."""
        self.set_context("content")
        if not self.librewolf:
            try:
                res = self.send("WebDriver:NewWindow", {"type": "window", "private": bool(private)})
                self.switch_to(res["handle"])
                return res["handle"]
            except MarionetteError:
                pass
        return self._chrome_new_window(private)

    def _handles(self):
        res = self.send("WebDriver:GetWindowHandles")
        return res.get("value", []) if isinstance(res, dict) else (res or [])

    def _chrome_new_window(self, private, timeout=WAIT_TIMEOUT):
        """new_window through the chrome window API (LibreWolf)."""
        before = set(self._handles())
        self.chrome_js("OpenBrowserWindow({ private: arguments[0] });", bool(private))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new = set(self._handles()) - before
            if new:
                handle = new.pop()
                self.switch_to(handle)
                self.wait_for("return document.readyState === 'complete';", 10)
                return handle
            time.sleep(0.2)
        raise MarionetteError("new window did not open")

    def switch_to(self, handle):
        self.set_context("content")
        self.send("WebDriver:SwitchToWindow", {"handle": handle, "focus": True})

    def close_window(self):
        self.set_context("content")
        return self.send("WebDriver:CloseWindow")

    def chrome_windows(self, *props):
        """Per browser window: private flag, privatebrowsingmode attribute and
        computed styles of :root and body (chrome documents)."""
        props = list(props) or ["background-color"]
        return self.chrome_js(
            "const props = arguments[0];"
            "const { PrivateBrowsingUtils } = ChromeUtils.importESModule("
            "  'resource://gre/modules/PrivateBrowsingUtils.sys.mjs');"
            "const out = [];"
            "for (const w of Services.wm.getEnumerator('navigator:browser')) {"
            "  const d = w.document, style = (el) => { if (!el) return null;"
            "    const cs = w.getComputedStyle(el), o = {};"
            "    for (const p of props) o[p] = cs.getPropertyValue(p).trim(); return o; };"
            "  out.push({ private: PrivateBrowsingUtils.isWindowPrivate(w),"
            "    privatebrowsingmode: d.documentElement.getAttribute('privatebrowsingmode'),"
            "    root: style(d.documentElement), body: style(d.body) });"
            "}"
            "return out;", props)

    def get_pref(self, name):
        return self.chrome_js(
            "const n = arguments[0], t = Services.prefs.getPrefType(n);"
            "if (t === Services.prefs.PREF_BOOL) return Services.prefs.getBoolPref(n);"
            "if (t === Services.prefs.PREF_INT) return Services.prefs.getIntPref(n);"
            "if (t === Services.prefs.PREF_STRING) return Services.prefs.getStringPref(n);"
            "return null;", name)

    def pref_names(self, branch, pattern=""):
        return self.chrome_js(
            "const [b, p] = arguments; const re = new RegExp(p, 'i');"
            "return Services.prefs.getChildList(b).filter((n) => re.test(n)).sort();",
            branch, pattern)


# ---------------------------------------------------------------- test pages

ARTICLE_PARAGRAPHS = [
    "The lighthouse keeper rose before dawn every morning, climbing the spiral "
    "staircase to polish the great lens until it shone like a second sun.",
    "Ships passing along the rocky coast relied on that beam for more than a "
    "century, and the keepers recorded every storm in a thick leather logbook.",
    "In winter the wind carried salt spray over the cliffs, coating the windows "
    "with a fine white crust that had to be scraped away by hand each evening.",
    "Supplies arrived once a fortnight by boat, weather permitting, and the "
    "keeper's family learned to bake bread, mend nets and read by lamplight.",
    "When automation finally came, the station fell silent, but visitors still "
    "walk the coastal path to watch the light sweep across the dark water.",
    "Historians who study the logbooks have found detailed notes on migrating "
    "birds, shifting sandbanks and the slow erosion of the headland itself.",
    "Those records now help scientists understand how the coastline changed "
    "over generations, long before satellites began measuring it from orbit.",
    "The tower itself was restored by volunteers who replaced the iron railings, "
    "repainted the red and white bands and rebuilt the keeper's cottage roof.",
]

ARTICLE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>The Last Lighthouse Keeper</title>
<style>html, body { background: rgb(255, 255, 255); color: rgb(20, 20, 20); }</style>
</head><body>
<header><nav><a href="/">Home</a></nav></header>
<main><article>
<h1>The Last Lighthouse Keeper</h1>
<p class="byline">By A. Writer</p>
%s
</article></main>
<footer>Footer text</footer>
</body></html>
""" % "\n".join("<p>%s %s</p>" % (p, p) for p in ARTICLE_PARAGRAPHS)

# The same article, declaring it has a dark version (like GitHub or DuckDuckGo).
DARK_ARTICLE_HTML = ARTICLE_HTML.replace(
    '<meta charset="utf-8">', '<meta charset="utf-8"><meta name="color-scheme" content="light dark">')


def make_pdf(text="browserGlass test PDF"):
    """A small valid single-page PDF with correct xref offsets."""
    stream = ("BT /F1 24 Tf 72 720 Td (%s) Tj ET" % text).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


class TestServer:
    """Local HTTP server on 127.0.0.1 (free port) serving fixed routes:
    {path: (content type, body)}, or with a third item, a dict of headers
    to add (Access-Control-Allow-Origin for a picture of another origin)."""

    def __init__(self, routes=None, cacheable=False):
        """cacheable=True drops `Cache-Control: no-store`, so pages can enter
        the back/forward cache (bfcache tests)."""
        self.routes = {
            "/article.html": ("text/html; charset=utf-8", ARTICLE_HTML.encode("utf-8")),
            "/dark.html": ("text/html; charset=utf-8", DARK_ARTICLE_HTML.encode("utf-8")),
            "/doc.pdf": ("application/pdf", make_pdf()),
        }
        self.routes.update(routes or {})
        routes_ref = self.routes
        no_store = not cacheable

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urllib.parse.urlsplit(self.path).path
                if path not in routes_ref:
                    self.send_error(404)
                    return
                ctype, body, *extra = routes_ref[path]
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                for name, value in (extra[0] if extra else {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                if no_store:
                    self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.timeout = 5
        self.port = self.httpd.server_address[1]
        self.thread = None

    def url(self, path, host="127.0.0.1"):
        """URL of `path`; `host` may be a .test name (see test_host_prefs)."""
        return "http://%s:%d%s" % (host, self.port, path)

    def start(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


# ---------------------------------------------------------------- CSS under test

SURFACE = (16, 20, 24)  # v0 fallback surface #101418
GLASS_OPACITY = 0.8

# v0 browser-glass-sync chrome CSS (glass active).
CHROME_GLASS = """body {
  background: rgba(%d, %d, %d, %s) !important;
}
:root, #main-window, #browser, #appcontent, #navigator-toolbox,
#TabsToolbar, #nav-bar, #PersonalToolbar,
#tabbrowser-tabbox, #tabbrowser-tabpanels,
.browserContainer, .browserStack, browser {
  background: transparent !important;
  border: none !important;
}
""" % (SURFACE + (GLASS_OPACITY,))

# privateGlass=false
CHROME_PRIVATE_OPAQUE = """:root[privatebrowsingmode="temporary"] body {
  background: rgba(%d, %d, %d, 1) !important;
}
""" % SURFACE

# v0 generic page rule (no exclusions).
CONTENT_GENERIC = """@-moz-document regexp("https?://.*") {
  html, body { background: transparent !important; }
}
"""

# Representative subset of my-internet example.com.css "transparency".
CONTENT_GENERIC_MYINTERNET = """@-moz-document regexp("https?://.*") {
html, body, main, #main, .main, section, #root, #app, body[data-theme="dark"], [data-color-theme] body {
  background-color: transparent !important;
  background: none !important;
}
}
"""

# readerOpaque=false (glass reader mode)
CONTENT_READER_GLASS = """@-moz-document url-prefix("about:reader") {
  :root, body { background: transparent !important; }
  body { --main-background: transparent !important; }
  .toolbar { background: transparent !important; }
}
"""

# readerOpaque=true: PDF opaque, placed AFTER the generic block.
CONTENT_PDF_OPAQUE = """body:has(> #outerContainer #viewerContainer) {
  background-color: var(--body-bg-color) !important;
}
"""

# newTabGlass=true, verified on Firefox 160: about:privatebrowsing paints its
# background on <html>, so :root needs it too (the plan's body-only rule fails).
# `background` (shorthand) also resets the new-tab wallpaper, which is a
# background-image on body (var(--newtab-wallpaper) / --newtab-wallpaper-color).
CONTENT_NEWTAB_GLASS = """@-moz-document url("about:newtab"), url("about:home"), url("about:privatebrowsing") {
  :root { --newtab-background-color: transparent !important; }
  :root, body { background: transparent !important; }
}
"""

# The rule exactly as first written in the plan (kept to document why it is
# insufficient; measured in the "opaque" config, informational only).
CONTENT_NEWTAB_GLASS_PLAN = """@-moz-document url("about:newtab"), url("about:home"), url("about:privatebrowsing") {
  :root { --newtab-background-color: transparent !important; }
  body { background: transparent !important; }
}
"""

CONFIGS = {
    "baseline": dict(chrome_css=None, content_css=None),
    "glass": dict(chrome_css=CHROME_GLASS,
                  content_css=CONTENT_GENERIC + CONTENT_READER_GLASS + CONTENT_NEWTAB_GLASS),
    "opaque": dict(chrome_css=CHROME_GLASS + CHROME_PRIVATE_OPAQUE,
                   content_css=CONTENT_GENERIC + CONTENT_GENERIC_MYINTERNET + CONTENT_PDF_OPAQUE
                   + CONTENT_NEWTAB_GLASS_PLAN),
}

# ---------------------------------------------------------------- measurements

BG = ("background-color", "background-image")

PAGE_INFO_JS = (
    "const vars = arguments[0];"
    "const st = (el) => { if (!el) return null; const cs = getComputedStyle(el), o = {};"
    "  for (const p of ['background-color', 'background-image'].concat(vars))"
    "    o[p] = cs.getPropertyValue(p).trim(); return o; };"
    "return { url: document.URL, contentType: document.contentType,"
    "  root: st(document.documentElement), body: st(document.body),"
    "  bodyClass: document.body ? document.body.className : null,"
    "  rootClass: document.documentElement.className };"
)


def page_info(b, *vars_):
    return b.js(PAGE_INFO_JS, list(vars_))


def measure(b, srv):
    m = {}
    art = srv.url("/article.html")
    pdf = srv.url("/doc.pdf")

    b.navigate(art)
    m["article"] = page_info(b)
    b.navigate(srv.url("/dark.html"))
    m["dark_article"] = page_info(b)

    b.navigate("about:reader?url=" + urllib.parse.quote(art, safe=""))
    m["reader_loaded"] = b.wait_for(
        "const c = document.querySelector('.moz-reader-content');"
        "return !!(c && c.textContent.includes('lighthouse')) && document.body.classList.contains('loaded');")
    time.sleep(0.6)  # body.loaded enables a 0.4s background transition
    m["reader"] = page_info(b, "--main-background")
    m["reader_toolbar"] = b.css(".toolbar", "background-color")

    b.navigate(pdf)
    m["pdf_loaded"] = b.wait_for(
        "return !!document.querySelector('#viewerContainer .page');", 20)
    m["pdf"] = page_info(b, "--body-bg-color")
    m["pdf"]["ids"] = b.js(
        "return { outer: !!document.getElementById('outerContainer'),"
        "  viewer: !!document.getElementById('viewerContainer'),"
        "  hasSelector: !!document.querySelector('body:has(> #outerContainer #viewerContainer)'),"
        "  rootVar: getComputedStyle(document.documentElement).getPropertyValue('--body-bg-color').trim() };")

    for page in ("about:newtab", "about:home", "about:privatebrowsing"):
        try:
            b.navigate(page)
            b.wait_for("return document.readyState === 'complete' && !!document.body;", 10)
            time.sleep(1.0)
            info = page_info(b, "--newtab-background-color", "--background-color-canvas")
            info["wallpaperNodes"] = b.js(
                "return Array.from(document.querySelectorAll('[class*=allpaper],[id*=allpaper]'))"
                ".map((e) => e.tagName.toLowerCase() + '.' + e.className).slice(0, 10);")
            info["sheets"] = b.js(
                "return Array.from(document.styleSheets).map((s) => s.href).filter(Boolean);")
            if page == "about:newtab":
                # Simulate a selected wallpaper (built-in images need the
                # network): the new tab sets these variables on the page.
                info["wallpaper"] = b.js(
                    "for (const el of [document.documentElement, document.body]) {"
                    "  el.style.setProperty('--newtab-wallpaper', 'linear-gradient(red, blue)');"
                    "  el.style.setProperty('--newtab-wallpaper-color', 'rgb(255, 0, 0)'); }"
                    "const cs = getComputedStyle(document.body);"
                    "return { 'background-color': cs.backgroundColor,"
                    "  'background-image': cs.backgroundImage };")
        except Exception as e:  # keep measuring the other pages
            info = {"error": str(e)}
        m[page] = info

    m["prefs"] = {n: b.get_pref(n) for n in
                  b.pref_names("browser.newtabpage.activity-stream.", "wallpaper")
                  + ["browser.nova.enabled", "browser.newtabpage.enabled",
                     "browser.startup.homepage"]}

    m["chrome_normal"] = b.chrome_windows()
    main = b.send("WebDriver:GetWindowHandle")["value"]
    b.new_window(private=True)
    try:
        b.navigate("about:privatebrowsing")
        b.wait_for("return document.readyState === 'complete' && !!document.body;", 10)
        time.sleep(1.0)
        m["private_page"] = page_info(b, "--newtab-background-color", "--background-color-canvas")
        m["chrome_with_private"] = b.chrome_windows()
    finally:
        b.close_window()
        b.switch_to(main)
    return m


# ---------------------------------------------------------------- checks

_RGBA = re.compile(r"rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)")


def alpha(color):
    if not color:
        return None
    if color == "transparent":
        return 0.0
    mt = _RGBA.match(color)
    if not mt:
        return None
    a = mt.group(4)
    if a is None:
        return 1.0
    return float(a[:-1]) / 100 if a.endswith("%") else float(a)


def transparent(style):
    return bool(style) and alpha(style.get("background-color")) == 0.0 \
        and style.get("background-image", "none") == "none"


def opaque(style):
    return bool(style) and alpha(style.get("background-color")) == 1.0


def g(m, *path):
    for k in path:
        if not isinstance(m, (dict, list)):
            return None
        try:
            m = m[k]
        except (KeyError, IndexError, TypeError):
            return None
    return m


def bg(m, *path):
    return g(m, *path + ("background-color",))


def build_checks(r):
    """r: {config: measurements}. Returns [(area, check, ok, detail)]."""
    base, glass, opq = r["baseline"], r["glass"], r["opaque"]
    out = []

    def add(area, name, ok, detail):
        out.append((area, name, None if ok is None else bool(ok), detail))

    # (a) generic web page
    add("web", "baseline body opaque (page sets white)", opaque(g(base, "article", "body")),
        bg(base, "article", "body"))
    add("web", "generic regexp: html+body transparent",
        transparent(g(glass, "article", "root")) and transparent(g(glass, "article", "body")),
        "html=%s body=%s" % (bg(glass, "article", "root"), bg(glass, "article", "body")))

    # (b) private windows
    def win(m, key, private):
        for w in g(m, key) or []:
            if w["private"] == private:
                return w
        return None

    nw, pw = win(glass, "chrome_with_private", False), win(glass, "chrome_with_private", True)
    add("private", "normal window: privatebrowsingmode attr absent",
        nw is not None and nw["privatebrowsingmode"] is None,
        "attr=%r" % (nw or {}).get("privatebrowsingmode"))
    add("private", "private window: privatebrowsingmode=\"temporary\"",
        pw is not None and pw["privatebrowsingmode"] == "temporary",
        "attr=%r isPrivate=%r" % ((pw or {}).get("privatebrowsingmode"), (pw or {}).get("private")))
    add("private", "glass cfg: private window body = glass tint",
        pw is not None and bg(pw, "body") == bg(nw, "body") and alpha(bg(pw, "body")) == GLASS_OPACITY,
        "normal=%s private=%s" % (bg(nw, "body"), bg(pw, "body")))
    onw, opw = win(opq, "chrome_with_private", False), win(opq, "chrome_with_private", True)
    add("private", "opaque rule: private body alpha 1, normal unchanged",
        opw is not None and alpha(bg(opw, "body")) == 1.0 and alpha(bg(onw, "body")) == GLASS_OPACITY,
        "normal=%s private=%s" % (bg(onw, "body"), bg(opw, "body")))

    # (c) reader mode
    add("reader", "about:reader loaded", base.get("reader_loaded") and glass.get("reader_loaded"),
        g(glass, "reader", "url"))
    add("reader", "generic regexp does NOT apply (opaque w/o CSS)",
        opaque(g(opq, "reader", "body")) and bg(opq, "reader", "body") == bg(base, "reader", "body"),
        "baseline=%s generic-only=%s" % (bg(base, "reader", "body"), bg(opq, "reader", "body")))
    add("reader", "--main-background exists on body",
        bool(g(base, "reader", "body", "--main-background")),
        "--main-background=%s" % g(base, "reader", "body", "--main-background"))
    add("reader", "glass rule: html+body transparent",
        transparent(g(glass, "reader", "root")) and transparent(g(glass, "reader", "body")),
        "html=%s body=%s --main-background=%s toolbar=%s" % (
            bg(glass, "reader", "root"), bg(glass, "reader", "body"),
            g(glass, "reader", "body", "--main-background"), bg(glass, "reader_toolbar")))

    # (d) PDF
    pdf_url = g(base, "pdf", "url") or ""
    add("pdf", "pdf.js loaded, document.URL is the PDF URL",
        base.get("pdf_loaded") and pdf_url.endswith("/doc.pdf"),
        "url=%s type=%s" % (pdf_url, g(base, "pdf", "contentType")))
    ids = g(base, "pdf", "ids") or {}
    add("pdf", "#outerContainer/#viewerContainer + :has selector match",
        ids.get("outer") and ids.get("viewer") and ids.get("hasSelector"), json.dumps(ids))
    add("pdf", "--body-bg-color defined",
        bool(ids.get("rootVar")), "--body-bg-color=%s body=%s" % (ids.get("rootVar"), bg(base, "pdf", "body")))
    add("pdf", "generic applies to pdf.js (body transparent)",
        transparent(g(glass, "pdf", "body")), "body=%s" % bg(glass, "pdf", "body"))
    add("pdf", "opaque rule after generic wins",
        opaque(g(opq, "pdf", "body")) and bg(opq, "pdf", "body") == bg(base, "pdf", "body"),
        "baseline=%s opaque-cfg=%s" % (bg(base, "pdf", "body"), bg(opq, "pdf", "body")))

    # (e) new tab / home / private browsing
    for page in ("about:newtab", "about:home", "about:privatebrowsing"):
        bm, gm = g(base, page) or {}, g(glass, page) or {}
        if "error" in gm or "error" in bm:
            add("newtab", page + " measurable", False, gm.get("error") or bm.get("error"))
            continue
        add("newtab", page + ": baseline opaque",
            opaque(bm.get("body")) or opaque(bm.get("root")),
            "url=%s html=%s body=%s" % (bm.get("url"), bg(bm, "root"), bg(bm, "body")))
        add("newtab", page + ": glass rule -> html+body transparent",
            transparent(gm.get("root")) and transparent(gm.get("body")),
            "html=%s body=%s img=%s --newtab-background-color=%s" % (
                bg(gm, "root"), bg(gm, "body"), g(gm, "body", "background-image"),
                g(gm, "root", "--newtab-background-color")))
    add("newtab", "wallpaper simulated: baseline paints it",
        g(base, "about:newtab", "wallpaper", "background-image") not in (None, "", "none"),
        "img=%s" % g(base, "about:newtab", "wallpaper", "background-image"))
    add("newtab", "wallpaper neutralized by glass rule",
        transparent(g(glass, "about:newtab", "wallpaper")),
        "bg=%s img=%s" % (bg(glass, "about:newtab", "wallpaper"),
                          g(glass, "about:newtab", "wallpaper", "background-image")))
    om = g(opq, "about:privatebrowsing") or {}
    add("newtab", "info: plan body-only rule on about:privatebrowsing", None,
        "html=%s body=%s (html stays opaque -> :root needed)" % (bg(om, "root"), bg(om, "body")))
    pg, pb = g(glass, "private_page") or {}, g(base, "private_page") or {}
    add("newtab", "about:privatebrowsing in private window: glass",
        transparent(pg.get("root")) and transparent(pg.get("body")),
        "baseline html=%s body=%s | glass html=%s body=%s" % (
            bg(pb, "root"), bg(pb, "body"), bg(pg, "root"), bg(pg, "body")))
    return out


def print_table(rows):
    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    for area, name, ok, detail in rows:
        mark = "--  " if ok is None else ("PASS" if ok else "FAIL")
        print("%s  %-*s  %-*s  %s" % (mark, w1, area, w2, name, detail))


def run_spike(dump=None):
    results = {}
    with TestServer() as srv:
        for name, cfg in CONFIGS.items():
            b = Browser(**cfg)
            try:
                b.start()
                results[name] = measure(b, srv)
            except Exception as e:
                tail = b.log_tail()
                raise MarionetteError("config %s: %s\n--- firefox log ---\n%s" % (name, e, tail))
            finally:  # also on KeyboardInterrupt / SystemExit (signals)
                b.cleanup()
    if dump:
        with open(dump, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, sort_keys=True)
    return results


def main(argv):
    install_signal_handlers()
    forced = os.environ.get("BG_FIREFOX")
    if forced and not os.access(forced, os.X_OK):
        print("harness error: BG_FIREFOX is not an executable: %s" % forced)
        return 2
    if not find_firefox():
        print("SKIP: firefox not found")
        return 0
    dump = None
    if len(argv) > 2 and argv[1] == "--dump":
        dump = argv[2]
    try:
        results = run_spike(dump)
    except MarionetteError as e:
        print("FAIL harness error: %s" % e)
        return 2
    rows = build_checks(results)
    print_table(rows)
    failed = sum(1 for r in rows if r[2] is False)
    counted = sum(1 for r in rows if r[2] is not None)
    print("\n%d/%d checks passed" % (counted - failed, counted))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

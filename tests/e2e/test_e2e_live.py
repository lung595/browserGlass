"""End-to-end: live control in a real headless Firefox, through the companion
add-on, the real native host and real syncs.

Opt-in (needs a Firefox binary, about 15 s):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_live.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Throwaway browser only: fake HOME and XDG folders (XDG_RUNTIME_DIR
included), a profile in its .mozilla/firefox, 127.0.0.1 page server under
made-up .test names, black-hole proxy. The add-on of extension/ is installed
as a temporary add-on (Addon:Install; Firefox release refuses an unsigned
one in the profile); the native messaging manifest is written to
~/.mozilla/native-messaging-hosts of the fake HOME and names a wrapper
(host_wrapper_text) that runs this repository's browserglass.py
native-host. The stylesheets come from `sync --plugin-dir <repo>`
(liveControl on), gone.test excluded when Firefox starts. Every page logs
the states of data-browserglass-off / -live on <html>: at its first script
(after the document_start content scripts) and at each change.

  1. hello, then the right `active` (host, domain, title hash) on navigation,
     in a new tab and back in the first tab;
  2. a sync excluding proton.test (live_push): the open page gets OFF within
     0.5 s of the sync's start (the page stamps each state change); a new
     excluded page has OFF at its first script and never loses it; another
     host is untouched;
  3. un-excluding gone.test (excluded at sync): OFF goes and the live
     section paints the glass again;
  4. two lists back to back: a page of the first list's host, no longer
     excluded, never gets OFF; the second's has it from its first script.
     The host serves one socket client at a time and answers it only once
     the add-on applied its list, so the add-on gets the second list after
     the first is applied: this checks the order of two pushes in a row,
     not the registration race of two lists in flight (the add-on's queue,
     reachable through the real host only after an ack timeout);
  5. back/forward cache: Back to a page left while excluded, after an
     un-exclude: OFF is gone;
  6. LIVE never comes before OFF on an excluded page (no "LIVE without
     OFF" state in its log), whether excluded at sync or live, and on a
     page open before the add-on is installed (no registration, no list
     yet: Firefox injects the content script into the open tab);
  7. SIGTERM to the host: the add-on starts a new one (new pid) within
     ~2 s, and pushes reach it;
  8. quitting Firefox: the host exits, its socket and files are gone;
  9. a private window: neither LIVE nor OFF, and the v1.0 rendering (glass
     unless excluded in the stylesheet); its sites are never reported;
 10. a sync of an exclusion alone with the add-on connected: live.acked >= 1,
     running_changed == [], status restart_needed false; the ack file is
     written within 2 s of the sync's start;
 11. a page shown in a frame of a glass page keeps its own look: OFF on
     the frame's <html> (frame.js), put back when the page takes it off,
     its white background kept, the top page still glass.
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "py"))

import companion_home as ch  # noqa: E402
import marionette as mn  # noqa: E402
from fakehome import load_script  # noqa: E402

bg = load_script()

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None

OFF, LIVE = ch.OFF, ch.LIVE
HOSTS = ("account.proton.test", "other.test", "gone.test", "a.test", "priv.test")
WHITE = "rgb(255, 255, 255)"
TITLE = "Live test page"
OFF_DELAY = 0.5   # seconds from the start of a sync to OFF on the open page
ACK_DELAY = 2.0   # seconds from the start of a sync to the ack file
RECONNECT = 5.0   # seconds for the add-on to start a new host (first retry: 2 s)

# A dark-capable page (the generic style paints the glass on it under the
# dark theme), white of its own. Its first script runs after every
# document_start content script; the observer then rebuilds every state
# <html> went through from the mutation records (oldValue), so a state
# that lasted only between two mutations of one batch is logged too.
PAGE = ("""<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="light dark"><title>%s</title>
<style>html, body { background: rgb(255, 255, 255); color: rgb(20, 20, 20); }</style>
<script>
window.__log = [];
window.__shown = [];
const OFF = "%s", LIVE = "%s", root = document.documentElement;
const cur = {[OFF]: root.hasAttribute(OFF), [LIVE]: root.hasAttribute(LIVE)};
const snap = (why) => __log.push([why, cur[OFF], cur[LIVE], Date.now()]);
snap("first-script");
new MutationObserver((records) => {
  records.forEach((m, i) => {
    const next = records.slice(i + 1).find((n) => n.attributeName === m.attributeName);
    cur[m.attributeName] = next ? next.oldValue !== null : root.hasAttribute(m.attributeName);
    snap("mutation");
  });
}).observe(root, {attributes: true, attributeOldValue: true, attributeFilter: [OFF, LIVE]});
addEventListener("pageshow", (e) => __shown.push(e.persisted));
</script></head><body><p>Some text.</p></body></html>
""" % (TITLE, OFF, LIVE)).encode("utf-8")

# A page with the test page in a frame.
FRAMED = ("""<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="light dark"><title>%s</title></head>
<body><iframe id="inner" src="/p.html?inner"></iframe></body></html>
""" % TITLE).encode("utf-8")
FRAME_JS = (
    "const d = document.getElementById('inner').contentDocument;"
    "if (!d || !d.body || d.readyState !== 'complete') return null;"
    "return {off: d.documentElement.hasAttribute(arguments[0]),"
    " bg: getComputedStyle(d.body).backgroundColor};"
)

STATE_JS = (
    "const r = document.documentElement;"
    "return {off: r.hasAttribute(arguments[0]), live: r.hasAttribute(arguments[1]),"
    " bg: getComputedStyle(document.body).backgroundColor, log: window.__log || null,"
    " shown: window.__shown || null, title: document.title};"
)


def setUpModule():
    if E2E and FIREFOX:
        mn.install_signal_handlers()


def title_hash(title):
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def live_without_off(log):
    return [e for e in log or [] if e[2] and not e[1]]


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class LiveE2E(unittest.TestCase):

    def setUp(self):
        self.server = mn.TestServer({"/p.html": ("text/html; charset=utf-8", PAGE),
                                     "/f.html": ("text/html; charset=utf-8", FRAMED)},
                                    cacheable=True).start()
        self.addCleanup(self.server.stop)
        self.browser = b = mn.Browser(firefox=FIREFOX, manage_user_js=False,
                                      prefs=mn.test_host_prefs(HOSTS))
        self.addCleanup(b.cleanup)  # kills Firefox and its helpers, removes the tree
        shutil.rmtree(b.profile, ignore_errors=True)  # the harness's own profile: unused
        self.h = ch.Home(b, ".mozilla/firefox", "e2elive.default")
        # The wrapper outside the state folder: a sync on Firefox release
        # (signing_enforced) removes its own wrapper and manifest.
        self.wrapper = os.path.join(b.root, "bin", "native-host")
        os.makedirs(os.path.dirname(self.wrapper))
        with open(self.wrapper, "w", encoding="utf-8") as f:
            f.write(bg.host_wrapper_text(ch.REPO))
        os.chmod(self.wrapper, 0o755)

    def tearDown(self):
        if self.browser.proc is not None:
            self.browser.stop()

    # ---- helpers ------------------------------------------------------------

    def check(self, label, ok, detail=""):
        with self.subTest(label):
            self.assertTrue(ok, "%s: %s" % (label, detail))

    def write_manifest(self):
        os.makedirs(os.path.dirname(self.h.manifest), exist_ok=True)
        with open(self.h.manifest, "w", encoding="utf-8") as f:
            f.write(bg.native_manifest_text(self.wrapper))

    def sync(self, excluded):
        out = self.h.sync(excluded)
        self.write_manifest()  # for the next host the add-on starts
        return out

    def url(self, host, query=""):
        return self.server.url("/p.html" + query, host=host)

    def page(self):
        return self.browser.js(STATE_JS, OFF, LIVE)

    def open(self, host, query=""):
        """Navigate, then give the content scripts time to settle."""
        self.browser.navigate(self.url(host, query))
        time.sleep(0.4)
        return self.page()

    def wait_page(self, want_off, timeout=5.0):
        return self.h.wait(lambda: (lambda s: s if s["off"] == want_off else None)(self.page()),
                           timeout) or self.page()

    def wait_glass(self, timeout=3.0):
        """The page once its background is transparent (the site styles
        animate background-color for 0.5 s when their rules start to
        apply), else its last state."""
        return self.h.wait(lambda: (lambda s: s if mn.alpha(s["bg"]) == 0.0 else None)(self.page()),
                           timeout, 0.1) or self.page()

    def runtime_file(self, kind):
        name = {"host": "host-%d.sock", "active": "active-%d.json", "ack": "ack-%d.json"}[kind]
        return os.path.join(self.h.runtime, name % self.browser.proc.pid)

    def active(self):
        text = ch.read(self.runtime_file("active"))
        try:
            return json.loads(text) if text else None
        except ValueError:
            return None  # mid-write cannot happen (atomic), but never fail on it

    def wait_active(self, host, timeout=10.0):
        """The active file once it names `host` with the page's title (the
        add-on reports again when the title changes: the first report of a
        loading tab may carry its URL as title)."""
        want = title_hash(TITLE)
        return self.h.wait(lambda: (lambda a: a if a and a.get("host") == host
                                    and a.get("title_hash") == want else None)(self.active()),
                           timeout)

    def raw_push(self, domains):
        """A connected socket that sent the list `domains` to the host."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(self.runtime_file("host"))
        s.sendall((json.dumps({"excluded": domains}) + "\n").encode("ascii"))
        return s

    # ---- the test -----------------------------------------------------------

    def test_live_control(self):
        b, h = self.browser, self.h
        try:
            self._run(b, h)
        except AssertionError as exc:
            raise AssertionError("%s\n--- firefox log ---\n%s" % (exc, b.log_tail()))

    def _run(self, b, h):
        # A profile Firefox ran before (compatibility.ini names its build):
        # the sync then knows the channel, and on Firefox release deposits
        # nothing, so that the user.js block stays the same across syncs.
        b.start()
        b.stop()
        out = self.sync(["gone.test"])
        self.assertEqual((out["glass"], out["reason"]), (True, "active"), out)
        b.start()
        pid = b.proc.pid
        self.assertLess(len(self.runtime_file("host").encode()), 108, "socket path too long")
        # 6. (no registration yet) a page open before the add-on exists
        b.navigate(self.url("gone.test", "?preinstall"))
        res = b.send("Addon:Install", {"path": os.path.join(ch.REPO, "extension"), "temporary": True})
        self.assertEqual(res.get("value"), ch.COMPANION_ID, res)

        # 1. hello, then active on navigation, new tab, back to the first tab
        sock = h.wait(lambda: os.path.exists(self.runtime_file("host")), 10)
        self.assertTrue(sock, "the native host did not start (no socket)")
        hosts = h.host_pids()
        self.assertEqual(len(hosts), 1, hosts)
        s = h.wait(lambda: (lambda s: s if s["live"] and s["off"] else None)(self.page()),
                   10) or self.page()
        self.check("6 open before the install: OFF and LIVE once the list is known",
                   s["off"] and s["live"] and s["bg"] == WHITE, s)
        self.check("6 open before the install: never LIVE without OFF",
                   not live_without_off(s["log"]), s["log"])
        first = b.send("WebDriver:GetWindowHandle")["value"]
        b.navigate(self.url("other.test"))
        act = self.wait_active("other.test")
        self.check("1 active on navigation (other.test)",
                   act and act["domain"] == "other.test" and act["title_hash"] == title_hash(TITLE)
                   and act["browser_pid"] == pid and not act.get("outdated"), act)
        s = h.wait(lambda: (lambda s: s if s["live"] else None)(self.page()), 10) or self.page()
        self.check("1 hello answered: the list arrived, LIVE set, glass on",
                   s["live"] and not s["off"] and mn.alpha(s["bg"]) == 0.0, s)
        b.navigate(self.url("account.proton.test"))
        act = self.wait_active("account.proton.test")
        self.check("1 active on navigation (account.proton.test -> proton.test)",
                   act and act["domain"] == "proton.test", act)
        tab = b.send("WebDriver:NewWindow", {"type": "tab"})["handle"]
        b.switch_to(tab)
        b.navigate(self.url("other.test", "?tab"))
        self.check("1 active in a new tab", self.wait_active("other.test"), self.active())
        b.switch_to(first)
        self.check("1 active back in the first tab", self.wait_active("account.proton.test"),
                   self.active())

        # 6. (excluded at sync) a gone.test page: OFF first, LIVE never alone
        s = self.open("gone.test", "?sync")
        self.check("6 excluded at sync: OFF at the first script, never lost",
                   s["log"] and all(e[1] for e in s["log"]) and s["off"] and s["bg"] == WHITE, s)
        self.check("6 excluded at sync: never LIVE without OFF", not live_without_off(s["log"]), s["log"])

        # 2. + 10. exclude proton.test live
        s = self.open("account.proton.test", "?2")
        self.check("2 before: LIVE, no OFF, glass", s["live"] and not s["off"]
                   and mn.alpha(s["bg"]) == 0.0, s)
        t0 = time.time()
        out = self.sync(["gone.test", "proton.test"])
        s = self.wait_page(True)
        stamp = next((e[3] for e in s["log"] or [] if e[1]), None)
        delay = stamp / 1000.0 - t0 if stamp is not None else None
        self.check("2 open page OFF within %.1fs of the sync's start" % OFF_DELAY,
                   s["off"] and s["bg"] == WHITE and delay is not None and delay <= OFF_DELAY,
                   "%r %r" % (delay, s))
        self.check("10 sync: live.acked >= 1, nothing to restart",
                   out["live"]["hosts"] >= 1 and out["live"]["acked"] >= 1
                   and out["running_changed"] == [], out)
        ack = json.loads(ch.read(self.runtime_file("ack")) or "{}")
        self.check("10 ack file within %.0fs of the sync's start" % ACK_DELAY,
                   ack.get("seq", 0) >= 1 and 0 <= ack["ts"] - t0 <= ACK_DELAY, (ack, t0))
        st = h.status()
        self.check("10 status: restart_needed false",
                   st["restart_needed"] is False and h.profile_status(st)["restart_needed"] is False
                   and h.profile_status(st)["running"] is True, st)
        self.check("10 status: one live host", st["companion"]["hosts"] >= 1, st["companion"])
        s = self.open("account.proton.test", "?new")
        self.check("2 new excluded page: OFF at its first script, never toggled",
                   s["log"] and all(e[1] for e in s["log"]) and s["off"] and s["bg"] == WHITE, s)
        self.check("6 excluded live: never LIVE without OFF", not live_without_off(s["log"]), s["log"])
        s = self.open("other.test", "?2")
        self.check("2 other host untouched", not any(e[1] for e in s["log"]) and s["live"]
                   and mn.alpha(s["bg"]) == 0.0, s)

        # 11. a framed page keeps its own look, the top page is glass
        b.navigate(self.server.url("/f.html", host="other.test"))
        f = h.wait(lambda: b.js(FRAME_JS, OFF), 5) or b.js(FRAME_JS, OFF)
        s = self.wait_glass()
        self.check("11 frame: OFF, own white background",
                   f and f["off"] and f["bg"] == WHITE, f)
        self.check("11 top page: no OFF, glass", not s["off"] and mn.alpha(s["bg"]) == 0.0, s)
        b.js("document.getElementById('inner').contentDocument.documentElement"
             ".removeAttribute(arguments[0]);", OFF)
        f = h.wait(lambda: (lambda f: f if f and f["off"] else None)(b.js(FRAME_JS, OFF)), 2)
        self.check("11 frame: OFF put back", f, b.js(FRAME_JS, OFF))

        # 3. un-exclude gone.test: OFF goes, the live section paints the glass
        s = self.open("gone.test", "?3")
        self.check("3 before: OFF, page white", s["off"] and s["bg"] == WHITE, s)
        out = self.sync(["proton.test"])
        self.wait_page(False)
        s = self.wait_glass()
        self.check("3 OFF removed, LIVE kept, glass back (live section)",
                   not s["off"] and s["live"] and mn.alpha(s["bg"]) == 0.0, s)
        st = h.status()
        self.check("3 still nothing to restart", out["running_changed"] == []
                   and st["restart_needed"] is False, (out, st["restart_needed"]))

        # 5. back/forward cache
        s = self.open("account.proton.test", "?5")
        self.check("5 before: excluded page OFF", s["off"], s)
        self.open("other.test", "?5")
        out = self.sync([])
        self.check("5 un-exclude acked", out["live"]["acked"] >= 1, out)
        b.send("WebDriver:Back")
        self.wait_page(False, 3.0)
        s = self.wait_glass()
        self.check("5 restored from the bfcache", s["shown"] and s["shown"][-1] is True, s)
        self.check("5 Back after un-exclude: OFF gone", not s["off"] and s["live"]
                   and mn.alpha(s["bg"]) == 0.0, s)

        # 4. two lists back to back
        first_push = self.raw_push(["a.test"])
        second_push = self.raw_push(["proton.test"])
        replies = []
        for conn in (first_push, second_push):
            with conn:
                try:
                    replies.append(conn.recv(4096))
                except OSError:
                    replies.append(b"")
        self.check("4 both lists acked", all(b'"acked"' in r for r in replies), replies)
        s = self.open("a.test", "?4")
        self.check("4 first list's host, no longer excluded: never OFF",
                   not any(e[1] for e in s["log"]) and not s["off"], s)
        s = self.open("account.proton.test", "?4")
        self.check("4 second list's host: OFF from the first script",
                   s["log"] and all(e[1] for e in s["log"]), s)

        # 7. SIGTERM to the host: a new one, pushes reach it
        old = h.host_pids()
        self.assertEqual(len(old), 1, old)
        t = time.monotonic()
        os.kill(old[0], signal.SIGTERM)
        new = h.wait(lambda: [p for p in h.host_pids() if p not in old]
                     if os.path.exists(self.runtime_file("host")) else None, RECONNECT + 5, 0.1)
        took = time.monotonic() - t
        self.check("7 new host within %.0fs of the SIGTERM" % RECONNECT,
                   new and len(new) == 1 and took <= RECONNECT, "%.1fs %r" % (took, new))
        self.check("7 the old host is gone", old[0] not in h.host_pids(), h.host_pids())
        self.open("account.proton.test", "?7")
        out = self.sync([])
        s = self.wait_page(False)
        self.check("7 push after the reconnect acked and applied",
                   out["live"]["acked"] >= 1 and not s["off"], (out, s))

        # 9. private window: no attribute, v1.0 rendering, not reported. The
        # first private window loads the stylesheets as they are on disk
        # then: back to the list Firefox started with, so that both agree.
        self.sync(["gone.test"])
        before = self.active()
        b.new_window(private=True)
        private = {}
        for host in ("priv.test", "account.proton.test", "gone.test"):
            b.navigate(self.url(host, "?private"))
            time.sleep(0.4)
            private[host] = self.page()
        self.check("9 private window: neither LIVE nor OFF, ever",
                   all(not s["off"] and not s["live"] and not any(e[1] or e[2] for e in s["log"])
                       for s in private.values()), private)
        self.check("9 private window: glass on the sites not excluded",
                   mn.alpha(private["priv.test"]["bg"]) == 0.0
                   and mn.alpha(private["account.proton.test"]["bg"]) == 0.0, private)
        self.check("9 private window: an excluded site keeps its own background",
                   private["gone.test"]["bg"] == WHITE, private["gone.test"])
        time.sleep(0.5)
        after = self.active()
        self.check("9 private sites never reported",
                   after and after.get("host") != "priv.test"
                   and after.get("host") == (before or {}).get("host"), (before, after))
        b.close_window()
        b.switch_to(first)

        # 8. quit: the host sees the end of stdin and leaves nothing
        hosts = h.host_pids()
        runtime = [self.runtime_file(k) for k in ("host", "active", "ack")]
        h.quit()
        gone = h.wait(lambda: not any(p in h.host_pids() for p in hosts), 10)
        self.check("8 host exited with the browser", gone, h.host_pids())
        left = [p for p in runtime if os.path.lexists(p)]
        self.check("8 no socket or file of that browser left", not left, left)
        self.check("8 runtime folder removed (empty)", not os.path.lexists(h.runtime),
                   os.listdir(h.runtime) if os.path.isdir(h.runtime) else None)


if __name__ == "__main__":
    unittest.main()

"""session: the site of the focused browser window (`active-site`): the
mozlz4/LZ4 decoder (round trips through a naive compressor, corrupt input),
the session walk on made-up session files, the profile of a browser pid
(a fake /proc), the companion's live report (a fake runtime folder with a
listening socket) and the CLI answers, each checked against the contract.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import hashlib
import json
import os
import random
import socket
import struct
import tempfile
import threading
import time
import unittest

from fakehome import FakeHome, LockHolder, REPO, load_script
from test_contract import DEFS, SCHEMA, validate

bg = load_script()

DATA = str(REPO / "data")
PID = 4242
FIREFOX_ROOT = ".mozilla/firefox"
LIBREWOLF_ROOT = ".librewolf"
DASH = " — "


# ---- a naive LZ4 block compressor (for round trips) --------------------------

def _len_bytes(n):
    out = bytearray()
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)
    return out


def lz4_compress(data, window=65535):
    """Greedy LZ4 block: 4-byte hash matches, overlapping matches allowed,
    offsets up to `window`, the LZ4 end rules kept (last 5 bytes literals)."""
    out = bytearray()
    table = {}
    i = anchor = 0
    n = len(data)
    while i < n - 12:
        key = data[i:i + 4]
        cand = table.get(key)
        table[key] = i
        if cand is None or i - cand > window:
            i += 1
            continue
        m = 4
        while i + m < n - 5 and data[cand + m] == data[i + m]:
            m += 1
        lit = i - anchor
        out.append((min(lit, 15) << 4) | min(m - 4, 15))
        if lit >= 15:
            out += _len_bytes(lit - 15)
        out += data[anchor:i]
        off = i - cand
        out += bytes((off & 255, off >> 8))
        if m - 4 >= 15:
            out += _len_bytes(m - 4 - 15)
        i += m
        anchor = i
    lit = n - anchor
    out.append(min(lit, 15) << 4)
    if lit >= 15:
        out += _len_bytes(lit - 15)
    out += data[anchor:]
    return bytes(out)


def mozlz4(data):
    return bg.MOZLZ4_MAGIC + struct.pack("<I", len(data)) + lz4_compress(data)


# ---- made-up session states ------------------------------------------------------

def entry(url, title):
    return {"url": url, "title": title}


def tab(*entries, index=None):
    return {"entries": list(entries), "index": len(entries) if index is None else index}


def win(*tabs, selected=1, z=None):
    w = {"tabs": list(tabs), "selected": selected}
    if z is not None:
        w["zIndex"] = z
    return w


def state(*windows, selected=1, last=None):
    s = {"windows": list(windows), "selectedWindow": selected}
    if last is not None:
        s["session"] = {"lastUpdate": last}
    return s


def two_windows():
    w1 = win(tab(entry("https://a.example.com/", "Alpha")),
             tab(entry("https://b.example.org/1", "Beta one"),
                 entry("https://b.example.org/2", "Beta two"), index=1),
             selected=2, z=2)
    w2 = win(tab(entry("https://c.example.net/", "Gamma")),
             tab(entry("http://d.example.co.uk/x", "Delta")), selected=2, z=1)
    return state(w1, w2, selected=2)


class Lz4Test(unittest.TestCase):

    def check(self, data):
        self.assertEqual(bg.lz4_block_decode(lz4_compress(data), len(data)), data)

    def test_round_trips(self):
        rnd = random.Random(1)
        cases = [b"", b"a", b"abc", b"a" * 1000, b"ab" * 5000, bytes(70000),
                 bytes(rnd.randrange(256) for _ in range(5000))]
        for _ in range(150):
            alpha = rnd.choice([b"ab", b"abcd", b'{"url":"https://', bytes(range(256))])
            cases.append(bytes(rnd.choice(alpha) for _ in range(rnd.randrange(1, 3000))))
        for data in cases:
            self.check(data)

    def test_lengths_overlap_and_far_offsets(self):
        rnd = random.Random(2)
        noise = bytes(rnd.randrange(256) for _ in range(65530))
        # literal run >= 15 (extended), match >= 15 + 255 (two extra bytes),
        # an overlapping match (offset 1 and 3), a match 65 530 bytes back
        data = bytes(range(40)) + b"x" * 600 + b"abc" * 300 + noise + bytes(range(40)) + noise[:50]
        block = lz4_compress(data)
        self.assertEqual(bg.lz4_block_decode(block, len(data)), data)
        # the far match is really there: an offset >= 65 000 appears
        self.check(noise + noise[:4000])

    def test_overlap_copy(self):
        # token 0x1f: 1 literal "a", match of 15+0+4=19 at offset 1
        block = bytes([0x1F, ord("a"), 1, 0, 0]) + bytes([0x50]) + b"tail!"
        self.assertEqual(bg.lz4_block_decode(block, 25), b"a" * 20 + b"tail!")

    def test_corrupt_blocks_raise(self):
        rnd = random.Random(3)
        plain = b'{"windows":[{"tabs":[' + b'{"url":"https://example.com/a"},' * 200 + b"]}]}"
        base = lz4_compress(plain)
        start = time.monotonic()
        for _ in range(2000):
            b = bytearray(base)
            mode = rnd.randrange(3)
            if mode == 0:
                b = b[:rnd.randrange(len(b))]
            elif mode == 1:
                b[rnd.randrange(len(b))] = rnd.randrange(256)
            else:
                b += bytes([rnd.randrange(256)])
            try:
                out = bg.lz4_block_decode(bytes(b), len(plain))
            except bg.Lz4Error:
                continue
            self.assertEqual(len(out), len(plain))
        self.assertLess(time.monotonic() - start, 30)
        for bad in (b"", b"\x00", b"\x10", b"\x00\x00\x00", b"\x0f\x00\x00\xff"):
            with self.assertRaises(bg.Lz4Error):
                bg.lz4_block_decode(bad, 10)
        with self.assertRaises(bg.Lz4Error):  # offset 0
            bg.lz4_block_decode(bytes([0x10, 65, 0, 0, 0x50]) + b"12345", 10)
        with self.assertRaises(bg.Lz4Error):  # offset before the start
            bg.lz4_block_decode(bytes([0x10, 65, 2, 0, 0x50]) + b"12345", 10)
        # A huge match length (each 0xFF adds 255) is refused before the copy
        huge = bytes([0x1F, 65, 1, 0]) + b"\xff" * (4 << 20) + b"\x00"
        start = time.monotonic()
        with self.assertRaises(bg.Lz4Error):
            bg.lz4_block_decode(huge, 100)
        self.assertLess(time.monotonic() - start, 5)
        with self.assertRaises(bg.Lz4Error):  # literals longer than the header says
            bg.lz4_block_decode(bytes([0xF0, 10]) + b"x" * 25, 20)

    def test_mozlz4_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f.jsonlz4")
            data = json.dumps(two_windows()).encode()
            with open(path, "wb") as f:
                f.write(mozlz4(data))
            self.assertEqual(bg.mozlz4_read(path), data)
            for raw in (b"", b"mozLz40\0", b"mozLz41\0\x05\0\0\0\x50hello",
                        bg.MOZLZ4_MAGIC + struct.pack("<I", bg.MOZLZ4_MAX + 1) + b"\x00",
                        mozlz4(data)[:-7]):
                with open(path, "wb") as f:
                    f.write(raw)
                with self.assertRaises(bg.Lz4Error, msg=raw[:20]):
                    bg.mozlz4_read(path)


class UrlAndTitleTest(unittest.TestCase):

    def test_url_host(self):
        for url in ("about:blank", "about:reader?url=https%3A%2F%2Fx.com%2F",
                    "view-source:https://x.com/", "file:///etc/hosts",
                    "moz-extension://0a1b2c3d/page.html", "data:text/html,hi", "", None,
                    "chrome://browser/content/browser.xhtml", "ftp://x.com/"):
            self.assertEqual(bg.url_host(url), (None, "not_web"), url)
        for url in ("http://[::1]/", "https://[fe80::1]:8443/x", "http://::1/",
                    "https://exa mple.com/", "http:///path"):
            self.assertEqual(bg.url_host(url), (None, "unsupported"), url)
        self.assertEqual(bg.url_host("HTTPS://user:pw@Account.Proton.ME:8080/p?q#f"),
                         ("account.proton.me", None))
        self.assertEqual(bg.url_host("http://127.0.0.1:8000/"), ("127.0.0.1", None))
        self.assertEqual(bg.url_host("https://bücher.example/"), ("xn--bcher-kva.example", None))

    def test_titles(self):
        self.assertEqual(bg.title_strip_brand("A — B" + DASH + "Mozilla Firefox"), "A — B")
        self.assertEqual(bg.title_strip_brand("A - B - LibreWolf"), "A - B")
        self.assertEqual(bg.title_strip_brand("Mozilla Firefox"), "Mozilla Firefox")
        for t in ("Page" + DASH + "Mozilla Firefox Private Browsing",
                  "Page" + DASH + "LibreWolf Private Browsing",
                  "Page" + DASH + "Mozilla Firefox Navigation privée",
                  "Zen Private Browsing  "):
            self.assertTrue(bg.title_is_private(t), t)
        self.assertFalse(bg.title_is_private("Private Browsing tips" + DASH + "Mozilla Firefox"))
        h = bg.title_hash("Alpha")
        self.assertRegex(h, r"^[0-9a-f]{16}$")
        self.assertEqual(h, hashlib.sha256(b"Alpha").hexdigest()[:16])

    def test_app_family_covers_app_ids(self):
        self.assertEqual(set(bg.APP_FAMILY), set(bg.APP_IDS))
        self.assertTrue(set(bg.APP_FAMILY.values()) <= set(bg.FAMILIES))
        self.assertEqual(list(bg.SITE_ERRORS), SCHEMA["active_site"]["fields"]["error"]["enum"])


class SessionWalkTest(unittest.TestCase):

    def test_title_match_wins_over_stale_selection(self):
        s = two_windows()
        self.assertEqual(bg.session_active_tab(s, "Alpha" + DASH + "Mozilla Firefox"),
                         ("https://a.example.com/", None))

    def test_selected_window_and_tab_are_one_based(self):
        s = two_windows()
        self.assertEqual(bg.session_active_tab(s, None), ("http://d.example.co.uk/x", None))
        s["selectedWindow"] = 1
        s["windows"][0]["selected"] = 1
        self.assertEqual(bg.session_active_tab(s, ""), ("https://a.example.com/", None))

    def test_tab_index_after_back(self):
        s = two_windows()
        s["selectedWindow"] = 1  # its selected tab went Back: index 1 of 2
        self.assertEqual(bg.session_active_tab(s, None), ("https://b.example.org/1", None))
        # the title of the shown entry matches, not the newer one
        self.assertEqual(bg.session_active_tab(s, "Beta one" + DASH + "LibreWolf"),
                         ("https://b.example.org/1", None))
        self.assertEqual(bg.session_active_tab(s, "Beta two" + DASH + "LibreWolf"),
                         ("https://b.example.org/1", None))  # no hit: the selected tab

    def test_no_title_hit_falls_back(self):
        self.assertEqual(bg.session_active_tab(two_windows(), "Elsewhere" + DASH + "Firefox"),
                         ("http://d.example.co.uk/x", None))

    def test_missing_zindex_1_refuses(self):
        s = two_windows()
        s["windows"][1]["zIndex"] = 3  # the most recent window was private
        self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"))
        for w in s["windows"]:
            del w["zIndex"]
        self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"))
        s["windows"][1]["zIndex"] = True  # not an integer 1
        self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"))
        # a title hit needs no zIndex
        self.assertEqual(bg.session_active_tab(s, "Gamma" + DASH + "Firefox"),
                         ("https://c.example.net/", None))

    def test_ambiguous_title(self):
        s = two_windows()
        s["windows"][1]["tabs"][0]["entries"][0]["title"] = "Alpha"
        self.assertEqual(bg.session_active_tab(s, "Alpha" + DASH + "Firefox"), (None, "ambiguous"))
        # same title twice on the same host: that host
        s["windows"][1]["tabs"][0]["entries"][0]["url"] = "https://a.example.com/other"
        url, error = bg.session_active_tab(s, "Alpha" + DASH + "Firefox")
        self.assertIsNone(error)
        self.assertEqual(bg.url_host(url), ("a.example.com", None))

    def test_bad_indexes_and_shapes(self):
        s = two_windows()
        for sel in (0, 3, -1, True, "2", None):
            s["selectedWindow"] = sel
            self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"), sel)
        s = two_windows()
        s["windows"][1]["selected"] = 9
        self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"))
        s = two_windows()
        s["windows"][1]["tabs"][1]["index"] = 0
        self.assertEqual(bg.session_active_tab(s, None), (None, "ambiguous"))
        for bad in ({}, {"windows": []}, {"windows": "x"}, {"windows": [1, "a"]}):
            self.assertEqual(bg.session_active_tab(bad, "A" + DASH + "B"), (None, "no_session"))
        weird = {"windows": [{"tabs": [1, {"entries": "x"}, {"entries": [5], "index": 1}]}]}
        self.assertEqual(bg.session_active_tab(weird, "A" + DASH + "B"), (None, "ambiguous"))

    def test_age(self):
        self.assertEqual(bg.session_age(state(last=1000000), now=1003.5), 3.5)
        self.assertEqual(bg.session_age(state(last=2000000), now=1000), 0.0)
        for s in (state(), {"session": {"lastUpdate": True}}, {"session": {"lastUpdate": "1"}},
                  {"session": {"lastUpdate": float("nan")}}, {"session": 3},
                  {"session": {"lastUpdate": 10 ** 400}}, json.loads('{"session": {"lastUpdate": 1e999}}')):
            self.assertIsNone(bg.session_age(s), s)


class SiteCase(unittest.TestCase):
    """A fake home, a fake /proc and a short fake runtime folder."""

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.env = self.fh.env()
        self.proc = self.fh.root / "proc"
        self.proc.mkdir()
        old = bg.PROC_DIR
        bg.PROC_DIR = str(self.proc)
        self.addCleanup(setattr, bg, "PROC_DIR", old)
        self.psl = bg.psl_load(DATA)
        self.read = []
        real_read = bg.session_read

        def spy(profile):
            self.read.append(os.path.realpath(profile))
            return real_read(profile)
        bg.session_read = spy
        self.addCleanup(setattr, bg, "session_read", real_read)

    def profile(self, root, name, session=None, rel="sessionstore-backups/recovery.jsonlz4"):
        path = self.fh.make_profile(root, name)
        self.fh.write(path / ".parentlock", "")
        if session is not None:
            self.fh.write(path / rel, mozlz4(json.dumps(session).encode()))
        return path

    def browser_pid(self, pid, profile):
        """/proc/<pid>/fd as Firefox has it: .parentlock among other fds."""
        fd = self.proc / str(pid) / "fd"
        fd.mkdir(parents=True)
        os.symlink("/dev/null", str(fd / "0"))
        os.symlink("socket:[1234]", str(fd / "1"))
        if profile is not None:
            os.symlink(str(profile / ".parentlock"), str(fd / "7"))

    def site(self, pid, app_id, title):
        return bg.active_site(pid, app_id, title, self.env, lambda: self.psl)

    def assertAnswer(self, doc, expected):
        self.assertEqual(doc, expected)
        self.assertEqual(validate(doc, SCHEMA["active_site"], DEFS), [])


class ProfileChoiceTest(SiteCase):

    def test_profile_of_pid(self):
        a = self.profile(FIREFOX_ROOT, "a.default", state())
        b = self.profile(FIREFOX_ROOT, "b.other", state())
        self.browser_pid(PID, b)
        self.assertEqual(os.path.realpath(bg.profile_of_pid(PID, self.env).path), os.path.realpath(str(b)))
        self.browser_pid(PID + 1, None)
        self.assertIsNone(bg.profile_of_pid(PID + 1, self.env))
        self.assertIsNone(bg.profile_of_pid(PID + 2, self.env))  # no such process
        self.assertTrue(a.exists())

    def test_session_through_pid(self):
        s = two_windows()
        s["session"] = {"lastUpdate": time.time() * 1000 - 2000}
        b = self.profile(FIREFOX_ROOT, "b.other", s)
        self.profile(FIREFOX_ROOT, "a.default", state(win(tab(entry("https://z.com/", "Z")), z=1)))
        self.browser_pid(PID, b)
        doc = self.site(PID, "firefox", "Delta" + DASH + "Mozilla Firefox")
        age = doc.pop("age")
        self.assertAnswer(dict(doc, age=None), {"host": "d.example.co.uk", "domain": "example.co.uk",
                                                "source": "session", "age": None})
        self.assertTrue(1.5 <= age <= 30, age)
        self.assertEqual(self.read, [os.path.realpath(str(b))])  # the other profile never read

    def test_newest_session_file_wins(self):
        old = state(win(tab(entry("https://old.example.com/", "Old")), z=1))
        new = state(win(tab(entry("https://new.example.com/", "New")), z=1))
        p = self.profile(FIREFOX_ROOT, "a.default", old, rel="sessionstore.jsonlz4")
        rec = self.fh.write(p / "sessionstore-backups/recovery.jsonlz4", mozlz4(json.dumps(new).encode()))
        os.utime(str(p / "sessionstore.jsonlz4"), (1000, 1000))
        self.browser_pid(PID, p)
        self.assertEqual(self.site(PID, "firefox", None)["host"], "new.example.com")
        rec.write_bytes(b"mozLz40\0garbage")  # unreadable newest: the next one
        self.assertEqual(self.site(PID, "firefox", None)["host"], "old.example.com")
        os.unlink(str(p / "sessionstore.jsonlz4"))
        self.assertAnswer(self.site(PID, "firefox", None), {"error": "no_session"})

    def test_fallback_running_profiles_of_the_family(self):
        s1 = state(win(tab(entry("https://one.example.com/", "One")), z=1))
        s2 = state(win(tab(entry("https://two.example.com/", "Two")), z=1))
        stopped = state(win(tab(entry("https://three.example.com/", "Three")), z=1))
        p1 = self.profile(FIREFOX_ROOT, "p1.default", s1)
        p2 = self.profile(FIREFOX_ROOT, "p2.default", s2)
        p3 = self.profile(FIREFOX_ROOT, "p3.default", stopped)
        lw = self.profile(LIBREWOLF_ROOT, "lw.default", s2)
        self.browser_pid(PID, None)  # no .parentlock fd visible (e.g. a sandbox)
        with LockHolder(self.fh, p1 / ".parentlock"), LockHolder(self.fh, lw / ".parentlock"):
            self.assertAnswer(self.site(PID, "firefox", "One" + DASH + "Mozilla Firefox"),
                              {"host": "one.example.com", "domain": "example.com",
                               "source": "session", "age": None})
            self.read.clear()
            # a stopped profile is never read, even when its tab matches
            self.assertEqual(self.site(PID, "firefox", "Three" + DASH + "Mozilla Firefox")["host"],
                             "one.example.com")
            self.assertNotIn(os.path.realpath(str(p3)), self.read)
            with LockHolder(self.fh, p2 / ".parentlock"):
                self.assertEqual(self.site(PID, "firefox", "Two" + DASH + "Mozilla Firefox")["host"],
                                 "two.example.com")
                self.assertAnswer(self.site(PID, "firefox", "Three" + DASH + "Mozilla Firefox"),
                                  {"error": "ambiguous"})
                self.assertAnswer(self.site(PID, "firefox", None), {"error": "ambiguous"})
            self.assertNotIn(os.path.realpath(str(p3)), self.read)
        self.assertAnswer(self.site(PID, "firefox", "One" + DASH + "Mozilla Firefox"),
                          {"error": "no_session"})


class AnswersTest(SiteCase):

    def page(self, url, title="Page"):
        p = self.profile(FIREFOX_ROOT, "a.default", state(win(tab(entry(url, title)), z=1)))
        self.browser_pid(PID, p)

    def test_no_browser_and_private(self):
        self.assertAnswer(self.site(PID, "kitty", "x"), {"error": "no_browser"})
        self.assertAnswer(self.site(PID, "Firefox", "x"), {"error": "no_browser"})
        self.assertAnswer(self.site(0, "firefox", "x"), {"error": "no_browser"})
        self.assertAnswer(self.site(PID, "librewolf", "Page" + DASH + "LibreWolf Private Browsing"),
                          {"error": "private"})
        self.assertEqual(self.read, [])

    def test_not_web(self):
        for url in ("about:newtab", "about:reader?url=https%3A%2F%2Fx.com%2F",
                    "view-source:https://x.com/", "file:///tmp/a.html",
                    "moz-extension://0a1b2c3d/options.html", "data:text/html,hi"):
            with self.subTest(url=url):
                self.setUp()
                self.page(url)
                self.assertAnswer(self.site(PID, "firefox", "Page" + DASH + "Mozilla Firefox"),
                                  {"error": "not_web"})

    def test_unsupported(self):
        # an IPv6 host, or a host that is itself a public suffix (excluding
        # it would exclude every site under it)
        for url in ("http://[::1]:8080/", "https://[2001:db8::1]/", "http://github.io/",
                    "https://co.uk/"):
            with self.subTest(url=url):
                self.setUp()
                self.page(url)
                self.assertAnswer(self.site(PID, "firefox", "Page" + DASH + "Mozilla Firefox"),
                                  {"error": "unsupported"})

    def test_registrable_domain(self):
        for url, host, domain in (("https://account.proton.me/login", "account.proton.me", "proton.me"),
                                  ("https://user.github.io/", "user.github.io", "user.github.io"),
                                  # "www." is kept when the rest is a public suffix
                                  ("https://www.gov.uk/x", "www.gov.uk", "www.gov.uk"),
                                  ("http://localhost:3000/", "localhost", "localhost"),
                                  ("http://192.168.1.2/", "192.168.1.2", "192.168.1.2")):
            with self.subTest(url=url):
                self.setUp()
                self.page(url)
                self.assertAnswer(self.site(PID, "firefox", "Page" + DASH + "Mozilla Firefox"),
                                  {"host": host, "domain": domain, "source": "session", "age": None})


class CompanionTest(SiteCase):
    """The native host's report: <runtime>/browserGlass/active-<pid>.json
    and the live socket host-<pid>.sock."""

    def setUp(self):
        super().setUp()
        self.rdir = self.fh.runtime / bg.RUNTIME_DIR_NAME
        self.rdir.mkdir(mode=0o700)
        sock_path = str(self.rdir / (bg.HOST_SOCKET % PID))
        self.assertLess(len(sock_path.encode()), 108)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(self.listener.close)
        self.listener.bind(sock_path)
        # never accept()ed: each liveness probe (connect, then close) waits in
        # the backlog, so it is made far larger than the probes of one test
        self.listener.listen(socket.SOMAXCONN)
        # the session says another site: a companion answer cannot come from it
        p = self.profile(FIREFOX_ROOT, "a.default",
                         state(win(tab(entry("https://session.example.com/", "Mail")), z=1)))
        self.browser_pid(PID, p)

    def report(self, host="mail.proton.me", title="Mail", **extra):
        doc = {"version": 1, "browser_pid": PID, "host": host,
               "domain": host, "title_hash": bg.title_hash(title), "ts": time.time()}
        doc.update(extra)
        self.fh.write(self.rdir / (bg.ACTIVE_FILE % PID), json.dumps(doc), 0o600)

    def test_companion_wins(self):
        self.report()
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"host": "mail.proton.me", "domain": "proton.me",
                           "source": "companion", "age": None})
        self.assertEqual(self.read, [])  # the session file is not even read

    def test_companion_answers(self):
        self.report(host="")
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "not_web"})
        self.report(host="[::1]")
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "unsupported"})

    def test_title_hash_differs(self):
        self.report(title="Another tab")
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "ambiguous"})
        self.report(title="Mail")  # the brand is the add-on's own: never stripped twice
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Other" + DASH + "Mozilla Firefox"),
                          {"error": "ambiguous"})

    def test_brandless_window_title(self):
        # A build whose window title is the bare page title: one holding
        # " - " is cut by title_strip_brand, the whole title still matches
        companion = {"host": "mail.proton.me", "domain": "proton.me",
                     "source": "companion", "age": None}
        self.report(title="Inbox - Proton Mail")
        self.assertAnswer(self.site(PID, "firefox", "Inbox - Proton Mail"), companion)
        self.report(title="Inbox")
        self.assertAnswer(self.site(PID, "firefox", "Inbox"), companion)

    def test_page_without_title(self):
        # about:newtab: niri shows the brand alone, the add-on hashed "New Tab"
        self.report(host="", title="New Tab")
        self.assertAnswer(self.site(PID, "firefox", "Mozilla Firefox"), {"error": "not_web"})
        self.assertEqual(self.read, [])
        # a web page whose hash cannot be checked: the session file decides
        self.report(title="New Tab")
        self.assertEqual(self.site(PID, "firefox", "Mozilla Firefox")["source"], "session")

    def test_foreign_runtime_folder_is_not_read(self):
        self.report()
        title = "Mail" + DASH + "Mozilla Firefox"
        real = self.fh.runtime / "real"
        os.rename(str(self.rdir), str(real))
        os.symlink(str(real), str(self.rdir))
        self.assertEqual(self.site(PID, "firefox", title)["source"], "session")

    def test_outdated(self):
        self.report(version=2)
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "outdated"})
        self.report(outdated=True)
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "outdated"})

    def test_dead_or_foreign_report_falls_back_to_the_session(self):
        session = {"host": "session.example.com", "domain": "example.com",
                   "source": "session", "age": None}
        title = "Mail" + DASH + "Mozilla Firefox"
        for broken in ({"browser_pid": PID + 1}, {"browser_pid": True}):
            self.report(**broken)
            self.assertAnswer(self.site(PID, "firefox", title), session)
        self.fh.write(self.rdir / (bg.ACTIVE_FILE % PID), "{not json", 0o600)
        self.assertAnswer(self.site(PID, "firefox", title), session)
        self.report()
        self.assertEqual(self.site(PID, "firefox", None)["source"], "session")  # nothing to check
        self.listener.close()  # the host died, its socket is left behind
        self.assertAnswer(self.site(PID, "firefox", title), session)
        os.unlink(str(self.rdir / (bg.HOST_SOCKET % PID)))
        self.assertAnswer(self.site(PID, "firefox", title), session)

    def test_browser_gone(self):
        self.report()
        for name in os.listdir(str(self.proc / str(PID) / "fd")):
            os.unlink(str(self.proc / str(PID) / "fd" / name))
        os.rmdir(str(self.proc / str(PID) / "fd"))
        os.rmdir(str(self.proc / str(PID)))
        self.assertAnswer(self.site(PID, "firefox", "Mail" + DASH + "Mozilla Firefox"),
                          {"error": "no_session"})


class CliTest(unittest.TestCase):
    """The command itself, in a subprocess (the real /proc: only this test
    process's own pid, which is no browser)."""

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def run_site(self, *args):
        proc = self.fh.run_script(["active-site", "--json"] + list(args))
        doc = json.loads(proc.stdout)
        return proc.returncode, doc

    def test_answers_exit_0(self):
        pid = str(os.getpid())
        code, doc = self.run_site("--pid", pid, "--app-id", "kitty", "--data", DATA)
        self.assertEqual((code, doc), (0, {"error": "no_browser"}))
        code, doc = self.run_site("--pid", pid, "--app-id", "firefox", "--title",
                                  "x" + DASH + "Mozilla Firefox Private Browsing", "--data", DATA)
        self.assertEqual((code, doc), (0, {"error": "private"}))
        code, doc = self.run_site("--pid", pid, "--app-id", "firefox", "--title", "x", "--data", DATA)
        self.assertEqual((code, doc), (0, {"error": "no_session"}))

    def test_companion_through_the_cli(self):
        pid = os.getpid()
        rdir = self.fh.runtime / "browserGlass"
        rdir.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(rdir / ("host-%d.sock" % pid)))
        listener.listen(4)
        doc = {"version": 1, "browser_pid": pid, "host": "www.example.co.uk",
               "domain": "example.co.uk", "title_hash": bg.title_hash("T"), "ts": 1}
        self.fh.write(rdir / ("active-%d.json" % pid), json.dumps(doc), 0o600)
        code, out = self.run_site("--pid", str(pid), "--app-id", "librewolf",
                                  "--title", "T" + DASH + "LibreWolf", "--data", DATA)
        self.assertEqual(code, 0)
        self.assertEqual(out, {"host": "www.example.co.uk", "domain": "example.co.uk",
                               "source": "companion", "age": None})
        self.assertEqual(validate(out, SCHEMA["active_site"], DEFS), [])

    def test_missing_psl_is_an_error(self):
        pid = os.getpid()
        rdir = self.fh.runtime / "browserGlass"
        rdir.mkdir(mode=0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(str(rdir / ("host-%d.sock" % pid)))
        listener.listen(4)
        doc = {"version": 1, "browser_pid": pid, "host": "a.example.com",
               "title_hash": bg.title_hash("T"), "ts": 1}
        self.fh.write(rdir / ("active-%d.json" % pid), json.dumps(doc), 0o600)
        empty = self.fh.root / "nodata"
        empty.mkdir()
        code, out = self.run_site("--pid", str(pid), "--app-id", "firefox", "--title",
                                  "T" + DASH + "Mozilla Firefox", "--data", str(empty))
        self.assertEqual(code, 1)
        self.assertEqual(validate(out, SCHEMA["error"], DEFS), [])

    def fake_niri(self, reply):
        """A niri IPC socket that answers each request line with `reply`
        (bytes); the requests it got go in the returned list."""
        path = str(self.fh.runtime / "niri.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(path)
        server.listen(4)
        got = []

        def serve():
            while True:
                try:
                    conn, _ = server.accept()
                except OSError:
                    return
                with conn:
                    got.append(conn.makefile("rb").readline())
                    conn.sendall(reply)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return path, got

    def test_title_from_niri(self):
        # The daemon passes --window-id, never the title (an argv is public):
        # the script asks niri's socket for it
        pid = str(os.getpid())
        windows = [{"id": 3, "title": "x" + DASH + "Mozilla Firefox Private Browsing",
                    "app_id": "firefox", "pid": os.getpid()},
                   {"id": 4, "title": "x", "app_id": "firefox", "pid": os.getpid()}]
        path, got = self.fake_niri(json.dumps({"Ok": {"Windows": windows}}).encode() + b"\n")
        env = {"NIRI_SOCKET": path}

        def run(*args):
            proc = self.fh.run_script(["active-site", "--json", "--pid", pid, "--app-id", "firefox",
                                       "--data", DATA] + list(args), extra_env=env)
            return proc.returncode, json.loads(proc.stdout)

        self.assertEqual(run("--window-id", "3"), (0, {"error": "private"}))
        self.assertEqual(got, [b'"Windows"\n'])
        self.assertEqual(run("--window-id", "4"), (0, {"error": "no_session"}))
        self.assertEqual(run("--window-id", "9"), (0, {"error": "no_browser"}))  # closed meanwhile

    def test_niri_unavailable_is_an_error(self):
        pid = str(os.getpid())
        args = ["active-site", "--json", "--pid", pid, "--app-id", "firefox", "--window-id", "3",
                "--data", DATA]
        broken, _ = self.fake_niri(b'{"Err": "nope"}\n')
        for extra in ({}, {"NIRI_SOCKET": str(self.fh.runtime / "none.sock")},
                      {"NIRI_SOCKET": broken}):
            proc = self.fh.run_script(args, extra_env=extra)
            out = json.loads(proc.stdout)
            self.assertEqual(proc.returncode, 1, extra)
            self.assertEqual(validate(out, SCHEMA["error"], DEFS), [])
            self.assertIn("niri", out["error"])

    def test_usage(self):
        proc = self.fh.run_script(["active-site", "--json", "--pid", "x", "--app-id", "firefox"])
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()

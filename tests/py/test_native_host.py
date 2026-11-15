"""native: the native messaging host (`native-host`), its runtime files and
live_push (section native, and the live push of section sync).

The host runs as a subprocess of the test inside a fake HOME, with
XDG_RUNTIME_DIR set to a short temp folder (a unix socket path must stay
under 108 bytes). It is started through /bin/sh, like the browser starts the
wrapper, so its parent (the "browser" pid of its files) is that shell, one
per host. live_push runs in-process, in a thread, while the test plays the
add-on on the host's stdin and stdout.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import io
import json
import os
import select
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock

import test_contract
from fakehome import REPO, SCRIPT, FakeHome, kill_strays, load_script, wait_until

bg = load_script()
DATA = str(REPO / "data")
TIMEOUT = 10.0


def frame(doc):
    data = json.dumps(doc).encode("utf-8")
    return struct.pack("=I", len(data)) + data


def settings(**over):
    doc = dict(test_contract.load_json("settings-default.json"))
    doc.update(over)
    return doc


class Host:
    """A native host subprocess, and the add-on side of its pipes."""

    def __init__(self, case, wrap=True):
        argv = [sys.executable, "-I", "-B", str(SCRIPT), "native-host", "--data", DATA,
                "/nm/browserglass.json", "browserglass@test"]
        if wrap:  # the shell stays the parent: one browser pid per host
            argv = ["/bin/sh", "-c", '"$@"; exit $?', "sh"] + argv
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=case.env(),
                                     cwd=str(case.fh.home))
        self.bpid = self.proc.pid if wrap else os.getpid()
        self.rdir = case.rdir
        self.buf = b""
        self.stderr = None
        case.addCleanup(self.stop)

    def path(self, kind):
        return bg.runtime_file(self.rdir, kind, self.bpid)

    def send(self, doc):
        self.write(frame(doc))

    def write(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _fill(self, timeout):
        fd = self.proc.stdout.fileno()
        if not select.select([fd], [], [], timeout)[0]:
            return False
        chunk = os.read(fd, 65536)
        if not chunk:
            raise EOFError("the host closed stdout")
        self.buf += chunk
        return True

    def _frame(self):
        if len(self.buf) < 4:
            return None
        size = struct.unpack("=I", self.buf[:4])[0]
        if len(self.buf) < 4 + size:
            return None
        body, self.buf = self.buf[4:4 + size], self.buf[4 + size:]
        return json.loads(body.decode("utf-8"))

    def recv(self, timeout=TIMEOUT):
        deadline = time.monotonic() + timeout
        while True:
            doc = self._frame()
            if doc is not None:
                return doc
            left = deadline - time.monotonic()
            if left <= 0 or not self._fill(left):
                raise AssertionError("no frame from the host")

    def quiet(self, timeout=0.3):
        """True when no byte comes on stdout for `timeout` seconds."""
        return not self.buf and not self._fill(timeout)

    def start(self):
        """The add-on's hello; the host answers hello, then the list."""
        self.hello = self.recv()
        self.send({"type": "hello", "proto": bg.NM_PROTO, "version": "1.1.0"})
        return self.recv()

    def finish(self):
        """Close stdin (the browser closed); returns (exit code, rest of stdout)."""
        self.proc.stdin.close()
        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            try:
                if not self._fill(deadline - time.monotonic()):
                    break
            except EOFError:
                break
        code = self.proc.wait(timeout=TIMEOUT)
        self.stderr = self.proc.stderr.read().decode("utf-8", "replace")
        return code, self.buf

    def wait(self):
        code = self.proc.wait(timeout=TIMEOUT)
        self.stderr = self.proc.stderr.read().decode("utf-8", "replace")
        return code

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


class Pusher(threading.Thread):
    """live_push(env, domains) in a thread: the test answers as the add-on."""

    def __init__(self, env, domains):
        super().__init__(daemon=True)
        self.env = env
        self.domains = domains
        self.result = None
        self.start()

    def run(self):
        self.result = bg.live_push(self.env, self.domains)

    def get(self):
        self.join(TIMEOUT)
        return self.result


class HostCase(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.addCleanup(kill_strays, self.fh)
        # Short on purpose: TMPDIR may be a long folder.
        self.run_base = tempfile.mkdtemp(prefix="bg-run-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.run_base, True)
        self.rdir = os.path.join(self.run_base, bg.RUNTIME_DIR_NAME)

    def env(self, extra=None):
        env = {"XDG_RUNTIME_DIR": self.run_base}
        env.update(extra or {})
        return self.fh.env(env)

    def host(self, wrap=True):
        host = Host(self, wrap)
        self.assertEqual(host.start(), {"type": "excluded", "seq": 1, "domains": []})
        self.assertEqual(host.hello, {"type": "hello", "proto": bg.NM_PROTO})
        return host

    def read_json(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def folder(self):
        return sorted(os.listdir(self.rdir)) if os.path.isdir(self.rdir) else None


class FramesTest(unittest.TestCase):
    """nm_read / nm_write on byte streams, in-process."""

    def test_round_trip(self):
        out = io.BytesIO()
        bg.nm_write(out, {"type": "excluded", "seq": 3, "domains": ["xn--bcher-kva.example"]})
        data = out.getvalue()
        self.assertEqual(struct.unpack("=I", data[:4])[0], len(data) - 4)
        self.assertEqual(bg.nm_read(io.BytesIO(data)),
                         {"type": "excluded", "seq": 3, "domains": ["xn--bcher-kva.example"]})

    def test_end_and_bad_frames(self):
        self.assertIsNone(bg.nm_read(io.BytesIO(b"")))
        self.assertEqual(bg.nm_read(io.BytesIO(struct.pack("=I", 3) + b"{x}")), {})
        self.assertEqual(bg.nm_read(io.BytesIO(struct.pack("=I", 2) + b"\xff\xfe")), {})
        for data in (b"\x01\x00", struct.pack("=I", 10) + b"{}",
                     struct.pack("=I", bg.NM_MAX_MESSAGE + 1) + b"{}"):
            with self.assertRaises(bg.NmError):
                bg.nm_read(io.BytesIO(data))

    def test_live_domains(self):
        self.assertEqual(bg.live_domains(["Example.ORG", "https://a.example.net:8080/x",
                                          "example.org", "", 7, None]),
                         ["example.org", "a.example.net"])
        self.assertEqual(bg.live_domains("example.org"), [])
        self.assertEqual(bg.live_domains(None), [])

    def test_runtime_dir(self):
        self.assertEqual(bg.runtime_dir({"XDG_RUNTIME_DIR": "/run/x/"}),
                         os.path.join("/run/x", bg.RUNTIME_DIR_NAME))
        fallback = "/run/user/%d" % os.getuid()
        expected = os.path.join(fallback, bg.RUNTIME_DIR_NAME) if os.path.isdir(fallback) else None
        self.assertEqual(bg.runtime_dir({"XDG_RUNTIME_DIR": "relative"}), expected)
        self.assertEqual(bg.runtime_dir({}), expected)


class NativeHostTest(HostCase):

    def test_socket_and_folder(self):
        host = self.host()
        path = host.path("host")
        self.assertLess(len(os.fsencode(path)), 108)
        self.assertTrue(stat.S_ISSOCK(os.lstat(path).st_mode))
        self.assertEqual(stat.S_IMODE(os.lstat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.lstat(self.rdir).st_mode), 0o700)
        self.assertEqual(self.folder(), ["host-%d.sock" % host.bpid])

    def test_active_file(self):
        host = self.host()
        host.send({"type": "active", "host": "News.Example.CO.UK", "title_hash": "0123456789abcdef"})
        active = host.path("active")
        self.assertTrue(wait_until(lambda: os.path.exists(active)))
        doc = self.read_json(active)
        self.assertEqual(stat.S_IMODE(os.stat(active).st_mode), 0o600)
        ts = doc.pop("ts")
        self.assertLess(abs(ts - time.time()), 60)
        self.assertEqual(doc, {"version": 1, "browser_pid": host.bpid, "host": "news.example.co.uk",
                               "domain": "example.co.uk", "title_hash": "0123456789abcdef"})
        # Replaced whole (no temp file left), a bad hash is dropped.
        host.send({"type": "active", "host": "", "title_hash": "../../etc"})
        self.assertTrue(wait_until(lambda: self.read_json(active)["host"] == ""))
        doc = self.read_json(active)
        self.assertEqual((doc["domain"], doc["title_hash"]), ("", ""))
        self.assertEqual(self.folder(), sorted(["host-%d.sock" % host.bpid, "active-%d.json" % host.bpid]))
        # A frame that is not JSON is ignored, the host goes on.
        host.write(struct.pack("=I", 5) + b"nope!")
        host.send({"type": "active", "host": "x.example.org", "title_hash": "ffffffffffffffff"})
        self.assertTrue(wait_until(lambda: self.read_json(active)["domain"] == "example.org"))
        code, rest = host.finish()
        self.assertEqual((code, rest), (0, b""))
        # Diagnostics never name a site.
        self.assertEqual(host.stderr, "")

    def test_push_relayed_and_acked(self):
        host = self.host()
        push = Pusher(self.env(), ["example.org", "news.example.net"])
        self.assertEqual(host.recv(), {"type": "excluded", "seq": 2,
                                       "domains": ["example.org", "news.example.net"]})
        host.send({"type": "applied", "seq": 2})
        self.assertEqual(push.get(), (1, frozenset({host.bpid})))
        ack = self.read_json(host.path("ack"))
        self.assertEqual(ack["seq"], 2)
        self.assertEqual(stat.S_IMODE(os.stat(host.path("ack")).st_mode), 0o600)
        # A list the add-on does not apply in time: delivered, not acked.
        push = Pusher(self.env(), [])
        self.assertEqual(host.recv(), {"type": "excluded", "seq": 3, "domains": []})
        host.send({"type": "applied", "seq": 9})  # not a list it was sent
        self.assertEqual(push.get(), (1, frozenset()))
        self.assertEqual(self.read_json(host.path("ack"))["seq"], 2)
        # The add-on reconnects (hello again): it gets the current list.
        host.send({"type": "hello", "proto": bg.NM_PROTO, "version": "1.1.0"})
        self.assertEqual(host.recv(), {"type": "excluded", "seq": 4, "domains": []})

    def test_push_reaches_every_host(self):
        first, second = self.host(), self.host()
        push = Pusher(self.env(), ["example.org"])
        for host in (first, second):
            self.assertEqual(host.recv()["domains"], ["example.org"])
        first.send({"type": "applied", "seq": 2})
        second.send({"type": "applied", "seq": 2})
        self.assertEqual(push.get(), (2, frozenset({first.bpid, second.bpid})))

    def test_garbage_on_the_socket(self):
        host = self.host()
        for data in (b"not json\n", b'{"excluded": "x"}\n', b"[]\n", b""):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(TIMEOUT)
                sock.connect(host.path("host"))
                sock.sendall(data)
                sock.shutdown(socket.SHUT_WR)
                self.assertEqual(sock.recv(100), b"")
        self.assertTrue(host.quiet())

    def test_other_protocol_is_outdated(self):
        host = Host(self)
        host.recv()
        host.send({"type": "hello", "proto": bg.NM_PROTO + 1, "version": "9.0.0"})
        active = host.path("active")
        self.assertTrue(wait_until(lambda: os.path.exists(active)))
        doc = self.read_json(active)
        self.assertEqual((doc["outdated"], doc["browser_pid"]), (True, host.bpid))
        self.assertNotIn("host", doc)
        # Nothing else is understood, no list is relayed.
        host.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertEqual(Pusher(self.env(), ["example.org"]).get(), (1, frozenset()))
        self.assertTrue(self.read_json(active)["outdated"])
        self.assertTrue(host.quiet())
        self.assertEqual(host.finish(), (0, b""))

    def test_eof_cleans_up(self):
        host = self.host()
        host.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        push = Pusher(self.env(), ["example.org"])
        host.recv()
        host.send({"type": "applied", "seq": 2})
        push.get()
        self.assertEqual(len(self.folder()), 3)
        self.assertEqual(host.finish(), (0, b""))
        self.assertIsNone(self.folder())
        self.assertTrue(os.path.isdir(self.run_base))

    def test_eof_keeps_the_others(self):
        first, second = self.host(), self.host()
        first.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertTrue(wait_until(lambda: os.path.exists(first.path("active"))))
        self.assertEqual(first.finish(), (0, b""))
        self.assertEqual(self.folder(), ["host-%d.sock" % second.bpid])
        self.assertEqual(Pusher(self.env(), []).get()[0], 1)

    def test_oversize_message_exits(self):
        host = self.host()
        host.write(struct.pack("=I", bg.NM_MAX_MESSAGE + 1))
        self.assertEqual(host.wait(), bg.EXIT_ERROR)
        self.assertIn("refused", host.stderr)
        self.assertIsNone(self.folder())

    def test_truncated_frame_exits(self):
        host = self.host()
        host.write(struct.pack("=I", 50) + b'{"type"')
        code, rest = host.finish()
        self.assertEqual((code, rest), (bg.EXIT_ERROR, b""))
        self.assertIsNone(self.folder())

    def test_runtime_folder_removed(self):
        host = self.host()
        shutil.rmtree(self.rdir)
        host.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertEqual(host.wait(), 0)
        self.assertIsNone(self.folder())
        self.assertEqual(host.stderr, "")

    def test_socket_gone_removes_its_late_files(self):
        # Uninstall emptied the folder, then the host wrote a file before
        # it saw its socket gone: that file goes, then the folder.
        host = self.host()
        host.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertTrue(wait_until(lambda: os.path.exists(host.path("active"))))
        os.unlink(host.path("host"))
        host.send({"type": "active", "host": "example.net", "title_hash": "0123456789abcdef"})
        self.assertEqual(host.wait(), 0)
        self.assertIsNone(self.folder())
        self.assertEqual(host.stderr, "")

    def test_runtime_remove_lists_again(self):
        # A live host writes between the listing and the rmdir.
        os.mkdir(self.rdir, 0o700)
        late = bg.runtime_file(self.rdir, "active", 4242)
        real_rmdir = os.rmdir
        calls = []

        def racing_rmdir(path):
            if not calls:
                with open(late, "w") as f:
                    f.write("{}\n")
            calls.append(path)
            return real_rmdir(path)

        with unittest.mock.patch.object(bg.os, "rmdir", racing_rmdir):
            self.assertTrue(bg.runtime_remove(self.env()))
        self.assertEqual(len(calls), 2)
        self.assertIsNone(self.folder())
        # A file not ours stays, and so does the folder.
        os.mkdir(self.rdir, 0o700)
        with open(os.path.join(self.rdir, "notes.txt"), "w") as f:
            f.write("x\n")
        self.assertFalse(bg.runtime_remove(self.env()))
        self.assertEqual(self.folder(), ["notes.txt"])

    def test_replaced_by_a_new_host(self):
        # Same browser pid (both are children of the test): the new host
        # takes the socket over, the old one leaves it alone.
        old = self.host(wrap=False)
        new = self.host(wrap=False)
        old.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertEqual(old.wait(), 0)
        self.assertEqual(self.folder(), ["host-%d.sock" % new.bpid])
        push = Pusher(self.env(), ["example.org"])
        self.assertEqual(new.recv()["seq"], 2)
        new.send({"type": "applied", "seq": 2})
        self.assertEqual(push.get(), (1, frozenset({new.bpid})))

    def test_replaced_host_leaves_the_new_files(self):
        # The old host wrote active-<pid>.json, then a new host of the same
        # browser took over and wrote its own: the old one's end keeps it.
        old = self.host(wrap=False)
        old.send({"type": "active", "host": "example.org", "title_hash": "0123456789abcdef"})
        self.assertTrue(wait_until(lambda: os.path.exists(old.path("active"))))
        new = self.host(wrap=False)
        new.send({"type": "active", "host": "example.net", "title_hash": "0123456789abcdef"})
        self.assertTrue(wait_until(lambda: self.read_json(new.path("active"))["host"] == "example.net"))
        self.assertEqual(old.finish(), (0, b""))
        self.assertEqual(self.read_json(new.path("active"))["host"], "example.net")
        self.assertEqual(self.folder(), ["active-%d.json" % new.bpid, "host-%d.sock" % new.bpid])

    def test_no_runtime_folder(self):
        # No XDG_RUNTIME_DIR, no /run/user/<uid> under a fake root: the
        # add-on still gets its hello and lists, without live control.
        host = Host.__new__(Host)
        env = self.fh.env({"XDG_RUNTIME_DIR": os.path.join(self.run_base, "missing")})
        argv = [sys.executable, "-I", "-B", str(SCRIPT), "native-host", "--data", DATA]
        host.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=env)
        host.buf = b""
        self.addCleanup(host.stop)
        self.assertEqual(host.start(), {"type": "excluded", "seq": 1, "domains": []})
        self.assertEqual(host.finish(), (0, b""))
        self.assertIn("no live control", host.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.run_base, "missing")))


class LivePushTest(HostCase):

    def test_stale_socket_removed(self):
        os.mkdir(self.rdir, 0o700)
        dead = bg.runtime_file(self.rdir, "host", 999999)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(dead)  # closed without listening: refused
        for kind in ("active", "ack"):
            with open(bg.runtime_file(self.rdir, kind, 999999), "w") as f:
                f.write("{}\n")
        with open(os.path.join(self.rdir, "notes.txt"), "w") as f:
            f.write("x\n")
        self.assertEqual(bg.live_push(self.env(), ["example.org"]), (0, frozenset()))
        self.assertEqual(self.folder(), ["notes.txt"])

    def test_no_folder_or_not_ours(self):
        self.assertEqual(bg.live_push(self.env(), ["example.org"]), (0, frozenset()))
        os.mkdir(os.path.join(self.run_base, "real"), 0o700)
        os.symlink("real", self.rdir)
        self.assertEqual(bg.live_push(self.env(), ["example.org"]), (0, frozenset()))


class SyncPushTest(HostCase):
    """sync, run as a subprocess, pushes to a running host."""

    def setUp(self):
        super().setUp()
        self.fh.write(".config/niri/config.kdl", 'input {\n}\n\ninclude "dms/windowrules.kdl"\n')
        self.fh.write(".config/niri/dms/windowrules.kdl", "window-rule {\n    opacity 0.9\n}\n")
        self.fh.write_dms_colors(mode="dark", surface_dark="#223344")
        self.profile = self.fh.make_profile(".mozilla/firefox", "a1b2c3d4.default-release")
        self.fh.write_profiles_ini(".mozilla/firefox", [{"name": "default-release",
                                                          "path": "a1b2c3d4.default-release",
                                                          "default": True}])

    def sync(self, *extra, **over):
        argv = [sys.executable, "-I", "-B", str(SCRIPT), "sync",
                "--settings", json.dumps(settings(**over))] + list(extra)
        return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, env=self.env(), cwd=str(self.fh.home))

    def result(self, proc):
        out, err = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 0, err)
        doc = json.loads(out)
        self.assertEqual(test_contract.validate(doc, test_contract.SCHEMA["sync"], test_contract.DEFS),
                         [], out)
        return doc

    def test_sync_pushes_then_new_hosts_start_with_it(self):
        host = self.host()
        proc = self.sync(excluded=["example.org"])
        msg = host.recv(60)
        self.assertEqual(msg["domains"], ["example.org"])
        host.send({"type": "applied", "seq": msg["seq"]})
        self.assertEqual(self.result(proc)["live"], {"hosts": 1, "acked": 1})
        self.assertEqual(self.read_json(host.path("ack"))["seq"], msg["seq"])
        # A browser started later gets the list of the last sync at once.
        later = Host(self)
        self.assertEqual(later.start(), {"type": "excluded", "seq": 1, "domains": ["example.org"]})

    def test_no_push(self):
        host = self.host()
        self.assertEqual(self.result(self.sync(excluded=["example.org"], liveControl=False))["live"],
                         {"hosts": 0, "acked": 0})
        self.assertEqual(self.result(self.sync("--profile", str(self.profile),
                                               excluded=["example.net"]))["live"],
                         {"hosts": 0, "acked": 0})
        self.assertTrue(host.quiet())


class ContractTest(unittest.TestCase):

    def test_command_registered(self):
        self.assertIs(bg.COMMANDS["native-host"], bg.cmd_native_host)
        self.assertIsNone(test_contract.SCHEMA["commands"]["native-host"])
        self.assertIn("native-host", bg.__doc__)
        args = bg.build_parser().parse_args(["native-host", "--data", DATA,
                                             "/nm/browserglass.json", "browserglass@test"])
        self.assertEqual(args.extra, ["/nm/browserglass.json", "browserglass@test"])

    def test_wrapper_runs_the_host(self):
        self.assertIn(" native-host --data ", bg.host_wrapper_text("/opt/bg"))


if __name__ == "__main__":
    unittest.main()

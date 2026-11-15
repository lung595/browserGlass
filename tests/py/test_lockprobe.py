"""lockprobe: F_GETLK on .parentlock, and the `lock` symlink fallback.

A child process plays the browser: it takes the fcntl lock Firefox takes, or
renames itself (comm) to look like a browser for the symlink fallback.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import errno
import io
import os
import subprocess
import sys
import tokenize
import unittest
from unittest import mock

from fakehome import SCRIPT, FakeHome, fixture_text, load_script

bg = load_script()

# Holds a POSIX record lock on argv[1] the way Firefox does (F_SETLK, whole
# file); argv[2]: "w" write lock, "r" read lock, "-" no lock; argv[3]
# (optional): new comm. Prints "ready", then on each stdin line: unlocks and
# prints "released", then exits.
HOLDER = r"""
import fcntl, os, struct, sys
flock = struct.Struct("@hhqqi4x")
if len(sys.argv) > 3:
    with open("/proc/self/comm", "w") as f:
        f.write(sys.argv[3])
fd = None
if sys.argv[2] != "-":
    fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o644)
    kind = fcntl.F_WRLCK if sys.argv[2] == "w" else fcntl.F_RDLCK
    fcntl.fcntl(fd, fcntl.F_SETLK, flock.pack(kind, os.SEEK_SET, 0, 0, 0))
print("ready", flush=True)
sys.stdin.readline()
if fd is not None:
    fcntl.fcntl(fd, fcntl.F_SETLK, flock.pack(fcntl.F_UNLCK, os.SEEK_SET, 0, 0, 0))
print("released", flush=True)
sys.stdin.readline()
"""


class LockCase(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.profile = str(self.fh.make_profile(".mozilla/firefox", "fake0001.default-release"))
        self.parentlock = os.path.join(self.profile, ".parentlock")
        self.link = os.path.join(self.profile, "lock")

    def holder(self, mode="w", comm=None, path=None):
        """Start a HOLDER child (inside the fake home); returns it once ready."""
        argv = [sys.executable, "-I", "-c", HOLDER, path or self.parentlock, mode]
        if comm:
            argv.append(comm)
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 universal_newlines=True, env=self.fh.env(), cwd=str(self.fh.home))
        self.addCleanup(self.stop, child)
        self.assertEqual(child.stdout.readline().strip(), "ready")
        return child

    def step(self, child, expect):
        child.stdin.write("\n")
        child.stdin.flush()
        self.assertEqual(child.stdout.readline().strip(), expect)

    @staticmethod
    def stop(child):
        if child.poll() is None:
            child.kill()
        child.wait()
        for stream in (child.stdin, child.stdout):
            if stream:
                stream.close()

    def dead_pid(self):
        child = subprocess.Popen([sys.executable, "-I", "-c", "pass"], env=self.fh.env())
        child.wait()
        return child.pid

    def make_link(self, target):
        os.symlink(target, self.link)


class ParentLockTest(LockCase):

    def test_flock_struct(self):
        self.assertEqual(bg.FLOCK.format, "@hhqqi4x")
        self.assertEqual(bg.FLOCK.size, 32)

    def test_no_parentlock_no_link_is_free_and_nothing_created(self):
        before = self.fh.snapshot(self.profile)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.assertEqual(self.fh.snapshot(self.profile), before)
        self.assertFalse(os.path.lexists(self.parentlock))

    def test_probing_leaves_an_existing_parentlock_unchanged(self):
        self.fh.write(self.parentlock, b"")
        os.chmod(self.parentlock, 0o644)
        os.utime(self.parentlock, ns=(10 ** 9, 10 ** 9))

        def stamp():
            st = os.lstat(self.parentlock)
            return (st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_mode, st.st_nlink)

        before = stamp()
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)
        self.assertEqual(stamp(), before)
        child = self.holder("w")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_RUNNING)
        self.assertEqual(stamp(), before)
        self.step(child, "released")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)
        self.assertEqual(stamp(), before)
        self.assertEqual(os.listdir(self.profile).count(".parentlock"), 1)

    def test_unlocked_parentlock_is_free(self):
        self.fh.write(self.parentlock, b"")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)

    def test_write_lock_held_by_a_process_then_released(self):
        child = self.holder("w")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_RUNNING)
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        # Probing took no lock and dropped none: still held.
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.step(child, "released")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.stop(child)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_lock_dropped_when_the_process_dies(self):
        child = self.holder("w")
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        child.kill()
        child.wait()
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_read_lock_counts_as_running(self):
        child = self.holder("r")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_RUNNING)
        self.step(child, "released")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)

    def test_readonly_parentlock(self):
        child = self.holder("w")
        os.chmod(self.parentlock, 0o444)
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.step(child, "released")
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_flatpak_profile(self):
        # Same inode whatever the mount: the probe works for any root.
        rel = ".var/app/org.mozilla.firefox/.mozilla/firefox"
        profile = str(self.fh.make_profile(rel, "fake0002.default-release"))
        child = self.holder("w", path=os.path.join(profile, ".parentlock"))
        self.assertTrue(bg.lock_state(profile) == bg.LOCK_RUNNING)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.step(child, "released")
        self.assertFalse(bg.lock_state(profile) == bg.LOCK_RUNNING)

    def test_stale_link_ignored_when_parentlock_answers(self):
        # A browser-looking process and a local host, but .parentlock is free:
        # F_GETLK decides, the link is not consulted.
        child = self.holder("-", comm="firefox")
        self.fh.write(self.parentlock, b"")
        self.make_link("127.0.0.1:+%d" % child.pid)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)

    def test_symlinked_parentlock_is_not_followed(self):
        target = self.fh.write("elsewhere/.parentlock", b"")
        child = self.holder("w", path=str(target))
        os.symlink(str(target), self.parentlock)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_UNKNOWN)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.step(child, "released")

    def test_dangling_symlinked_parentlock(self):
        os.symlink("/nonexistent-target-for-test", self.parentlock)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_UNKNOWN)
        self.assertFalse(os.path.exists("/nonexistent-target-for-test"))

    def test_fifo_parentlock_does_not_hang(self):
        os.mkfifo(self.parentlock)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_UNKNOWN)

    def test_directory_parentlock(self):
        os.mkdir(self.parentlock)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_UNKNOWN)

    def test_missing_profile(self):
        self.assertEqual(bg.lock_state(os.path.join(self.profile, "nope")), bg.LOCK_FREE)

    def test_getlk_other_error_is_unknown(self):
        self.fh.write(self.parentlock, b"")
        child = self.holder("-", comm="firefox")
        self.make_link("127.0.0.1:+%d" % child.pid)
        with mock.patch.object(bg, "_getlk", side_effect=OSError(errno.EINVAL, "bad")):
            self.assertEqual(bg.lock_state(self.profile), bg.LOCK_UNKNOWN)
            self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_no_lockf_flock_or_create_in_lockprobe(self):
        # The code of the section (comments and strings aside) never locks,
        # writes or creates.
        text = SCRIPT.read_text(encoding="ascii")
        section = text[text.index("\n# lockprobe\n"):text.index("\n# inputs\n")]
        names = {tok.string for tok in tokenize.generate_tokens(io.StringIO(section).readline)
                 if tok.type == tokenize.NAME}
        for name in ("lockf", "flock", "O_CREAT", "O_WRONLY", "O_RDWR", "F_SETLK", "F_SETLKW"):
            self.assertNotIn(name, names)
        self.assertIn("F_GETLK", names)
        self.assertIn("O_NOFOLLOW", names)


class LockLinkFallbackTest(LockCase):
    """The `lock` symlink, used only when .parentlock is missing or ENOLCK."""

    def test_stale_link_dead_pid(self):
        # The shape seen in the wild: a LAN address and a pid long gone.
        self.make_link("192.0.2.177:+%d" % self.dead_pid())
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_stale_link_pid_reused_by_another_program(self):
        child = self.holder("-")                       # comm: python
        self.make_link("127.0.0.1:+%d" % child.pid)
        self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_live_browser_on_loopback(self):
        child = self.holder("-", comm="firefox")
        self.make_link("127.0.0.1:+%d" % child.pid)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_RUNNING)
        self.assertFalse(os.path.lexists(self.parentlock))

    def test_live_browser_without_plus(self):
        child = self.holder("-", comm="librewolf")
        self.make_link("127.0.0.1:%d" % child.pid)
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)

    def test_browser_comms(self):
        for comm in ("firefox-bin", "GeckoMain", "zen", "floorp", "waterfox", "LibreWolf"):
            self.assertTrue(bg._is_browser_comm(comm), comm)
        for comm in ("firefox-esr", "zen-bin", "librewolf-bin", "waterfox-bin", "floorp-bin"):
            self.assertTrue(bg._is_browser_comm(comm), comm)
        for comm in ("python3", "", None, "bash", "sleep", "zenity", "floorplan", "firefoxpwa",
                     "firefox-helper", "Web Content", "zen-browser-upd"):
            self.assertFalse(bg._is_browser_comm(comm), comm)
        for name in bg.BROWSER_COMMS:
            self.assertLessEqual(len(name), bg.COMM_MAX, name)

    def test_link_to_a_reused_pid_named_like_a_lookalike(self):
        child = self.holder("-", comm="zenity")
        self.make_link("127.0.0.1:+%d" % child.pid)
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)

    def test_foreign_host(self):
        child = self.holder("-", comm="firefox")
        self.make_link("192.0.2.177:+%d" % child.pid)
        with mock.patch.object(bg, "_local_addresses", return_value={"127.0.0.1", "198.51.100.23"}):
            self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        os.remove(self.link)
        self.make_link("198.51.100.23:+%d" % child.pid)
        with mock.patch.object(bg, "_local_addresses", return_value={"127.0.0.1", "198.51.100.23"}):
            self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        with mock.patch.object(bg, "_local_addresses", return_value=None):
            self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)   # cannot tell: trust the pid

    def test_garbage_links(self):
        for target in ("", "nonsense", "host:+abc", "host:+-1", "127.0.0.1:+0",
                       "127.0.0.1:+99999999999", "127.0.0.1:+", "127.0.0.1:+12 "):
            if os.path.lexists(self.link):
                os.remove(self.link)
            if target:
                self.make_link(target)
            self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE, target)

    def test_lock_regular_file_is_free(self):
        self.fh.write(self.link, "127.0.0.1:+1")
        self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)

    def test_enolck_falls_back_to_the_link(self):
        self.fh.write(self.parentlock, b"")
        child = self.holder("-", comm="firefox")
        enolck = OSError(errno.ENOLCK, "No locks available")
        with mock.patch.object(bg, "_getlk", side_effect=enolck):
            self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)   # no link
            self.make_link("127.0.0.1:+%d" % child.pid)
            self.assertEqual(bg.lock_state(self.profile), bg.LOCK_RUNNING)
            os.remove(self.link)
            self.make_link("192.0.2.177:+%d" % self.dead_pid())
            self.assertEqual(bg.lock_state(self.profile), bg.LOCK_FREE)  # stale

    def test_enolck_with_a_real_lock_held(self):
        # Even with the fcntl lock really held, ENOLCK means F_GETLK cannot be
        # trusted: only the link decides.
        holder = self.holder("w")
        with mock.patch.object(bg, "_getlk", side_effect=OSError(errno.ENOLCK, "x")):
            self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.assertTrue(bg.lock_state(self.profile) == bg.LOCK_RUNNING)
        self.step(holder, "released")

    def test_fallback_reads_proc_comm(self):
        child = self.holder("-", comm="firefox")
        self.assertEqual(bg._proc_comm(child.pid), "firefox")
        self.assertIsNone(bg._proc_comm(self.dead_pid()))
        self.make_link("127.0.0.1:+%d" % child.pid)
        with mock.patch.object(bg, "_proc_comm", return_value="bash"):
            self.assertFalse(bg.lock_state(self.profile) == bg.LOCK_RUNNING)


class FibTrieTest(unittest.TestCase):

    def test_parse(self):
        self.assertEqual(bg.parse_fib_trie(fixture_text("proc/fib_trie")),
                         {"127.0.0.1", "198.51.100.23"})

    def test_parse_garbage(self):
        self.assertEqual(bg.parse_fib_trie(""), set())
        self.assertEqual(bg.parse_fib_trie("/32 host LOCAL\n|-- x\n"), set())

    def test_local_addresses_are_read_locally(self):
        local = bg._local_addresses()
        if local is not None:
            self.assertIn("127.0.0.1", local)
        self.assertTrue(bg._host_is_local("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()

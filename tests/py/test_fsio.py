"""fsio: read_text / write_if_changed (atomic write, permissions kept,
symlinks followed, read-only targets skipped, surrogateescape round trip,
nothing written when unchanged). Everything happens in a FakeHome.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import os
import stat
import unittest

from fakehome import FakeHome, load_script

bg = load_script()


def mode_of(path):
    return stat.S_IMODE(os.lstat(str(path)).st_mode)


class WriteTest(unittest.TestCase):

    def setUp(self):
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)

    def test_new_file(self):
        path = self.fh.home / "p" / "chrome" / "x.css"
        self.assertTrue(bg.write_if_changed(str(path), "a {}\n"))
        self.assertEqual(path.read_bytes(), b"a {}\n")
        umask = os.umask(0)
        os.umask(umask)
        self.assertEqual(mode_of(path), 0o666 & ~umask)

    def test_new_file_mode(self):
        path = self.fh.home / "x.kdl"
        self.assertTrue(bg.write_if_changed(str(path), "x\n", mode=0o600))
        self.assertEqual(mode_of(path), 0o600)

    def test_no_dirs(self):
        path = self.fh.home / "missing" / "x.css"
        with self.assertRaises(OSError):
            bg.write_if_changed(str(path), "x", make_dirs=False)

    def test_permissions_kept(self):
        for mode in (0o600, 0o644, 0o640, 0o755):
            path = self.fh.write("user%o.js" % mode, "old\n", mode=mode)
            self.assertTrue(bg.write_if_changed(str(path), "new\n"))
            self.assertEqual(path.read_text(), "new\n")
            self.assertEqual(mode_of(path), mode)

    def test_unchanged_not_written(self):
        path = self.fh.write("user.js", "same\n", mode=0o600)
        past = 1000000000
        os.utime(str(path), (past, past))
        inode = os.stat(str(path)).st_ino
        self.assertFalse(bg.write_if_changed(str(path), "same\n"))
        st = os.stat(str(path))
        self.assertEqual(st.st_mtime, past)
        self.assertEqual(st.st_ino, inode)
        # Same size, different content: written.
        self.assertTrue(bg.write_if_changed(str(path), "sane\n"))
        self.assertEqual(path.read_text(), "sane\n")

    def test_atomic_replace_and_no_leftover(self):
        path = self.fh.write("d/x.css", "old")
        inode = os.stat(str(path)).st_ino
        self.assertTrue(bg.write_if_changed(str(path), "new"))
        self.assertNotEqual(os.stat(str(path)).st_ino, inode)
        self.assertEqual(sorted(os.listdir(str(path.parent))), ["x.css"])

    def test_symlink_target_written(self):
        target = self.fh.write("dotfiles/user.js", "old\n", mode=0o600)
        link = self.fh.home / "profile" / "user.js"
        link.parent.mkdir()
        os.symlink("../dotfiles/user.js", str(link))
        self.assertTrue(bg.write_if_changed(str(link), "new\n"))
        self.assertTrue(os.path.islink(str(link)))
        self.assertEqual(os.readlink(str(link)), "../dotfiles/user.js")
        self.assertEqual(target.read_text(), "new\n")
        self.assertEqual(mode_of(target), 0o600)
        self.assertEqual(sorted(os.listdir(str(target.parent))), ["user.js"])
        self.assertEqual(sorted(os.listdir(str(link.parent))), ["user.js"])

    def test_dangling_symlink_creates_target(self):
        link = self.fh.home / "user.js"
        os.symlink("real/user.js", str(link))
        self.assertTrue(bg.write_if_changed(str(link), "x\n"))
        self.assertTrue(os.path.islink(str(link)))
        self.assertEqual((self.fh.home / "real" / "user.js").read_text(), "x\n")

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_read_only_file_skipped(self):
        path = self.fh.write("user.js", "old\n", mode=0o444)
        warnings = []
        self.assertFalse(bg.write_if_changed(str(path), "new\n", warnings, family="firefox",
                                             profile="0123456789ab"))
        self.assertEqual(path.read_text(), "old\n")
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertEqual(warning["code"], bg.WARN_READ_ONLY)
        self.assertEqual(warning["family"], "firefox")
        self.assertEqual(warning["profile"], "0123456789ab")
        self.assertNotIn(str(self.fh.home), warning["message"])
        # Unchanged content on a read-only file: no warning, nothing to do.
        warnings = []
        self.assertFalse(bg.write_if_changed(str(path), "old\n", warnings))
        self.assertEqual(warnings, [])

    @unittest.skipIf(os.geteuid() == 0, "root ignores file permissions")
    def test_read_only_folder_skipped(self):
        path = self.fh.write("ro/x.css", "old")
        os.chmod(str(path.parent), 0o555)
        warnings = []
        self.assertFalse(bg.write_if_changed(str(path), "new", warnings))
        self.assertEqual(path.read_text(), "old")
        self.assertEqual([w["code"] for w in warnings], [bg.WARN_READ_ONLY])
        self.assertFalse(bg.write_if_changed(str(path.parent / "new.css"), "x", warnings))
        self.assertEqual(len(warnings), 2)
        self.assertEqual(sorted(os.listdir(str(path.parent))), ["x.css"])

    def test_read_only_without_warning_list(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores file permissions")
        path = self.fh.write("x.css", "old", mode=0o444)
        self.assertFalse(bg.write_if_changed(str(path), "new"))

    def test_not_a_regular_file(self):
        folder = self.fh.home / "dir.css"
        folder.mkdir()
        with self.assertRaises(OSError):
            bg.write_if_changed(str(folder), "x")

    def test_surrogateescape_round_trip(self):
        raw = b"// caf\xe9 latin-1\nuser_pref(\"a\", \"\xff\xfe\");\n\xc3\xa9 utf-8\n"
        path = self.fh.write("user.js", raw, mode=0o600)
        text = bg.read_text(str(path))
        self.assertIn("\udce9", text)
        self.assertIn("\u00e9 utf-8", text)
        self.assertFalse(bg.write_if_changed(str(path), text))
        edited = text + "user_pref(\"b\", 1);\n"
        self.assertTrue(bg.write_if_changed(str(path), edited))
        self.assertEqual(path.read_bytes(), raw + b"user_pref(\"b\", 1);\n")
        self.assertEqual(bg.read_text(str(path)), edited)

    def test_crlf_and_bom_kept(self):
        raw = b"\xef\xbb\xbfa {}\r\nb {}\r\n"
        path = self.fh.write("u.css", raw)
        text = bg.read_text(str(path))
        self.assertTrue(text.startswith("\ufeff"))
        self.assertFalse(bg.write_if_changed(str(path), text))
        self.assertEqual(path.read_bytes(), raw)


class ReadTest(unittest.TestCase):

    def test_missing(self):
        with FakeHome() as fh:
            with self.assertRaises(OSError):
                bg.read_text(str(fh.home / "nope"))

    def test_fifo_not_read(self):
        with FakeHome() as fh:
            fifo = fh.home / "fifo"
            os.mkfifo(str(fifo))
            with self.assertRaises(OSError):
                bg.read_text(str(fifo))

    def test_oversize_never_truncated_nor_rewritten(self):
        import errno
        with FakeHome() as fh:
            small = fh.write("small.css", "a" * 17)
            self.assertEqual(bg.read_text(str(small), limit=17), "a" * 17)
            with self.assertRaises(OSError) as cm:
                bg.read_text(str(small), limit=16)
            self.assertEqual(cm.exception.errno, errno.EFBIG)
            # Default limit: an edit pipeline (read, edit, write) stops at the
            # read, so the big file keeps every byte.
            big = fh.home / "userChrome.css"
            content = b"/* x */\n" * (bg.READ_LIMIT // 8 + 1)
            big.write_bytes(content)
            with self.assertRaises(OSError) as cm:
                text = bg.read_text(str(big))
                bg.write_if_changed(str(big), bg.ensure_import(text, '@import "x.css";'))
            self.assertEqual(cm.exception.errno, errno.EFBIG)
            self.assertEqual(big.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()

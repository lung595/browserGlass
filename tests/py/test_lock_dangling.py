"""state_lock() on a state folder that is a dangling symlink: it must fail
with OSError, not spin forever re-creating a folder it cannot create.

Run: python3 -B -m unittest discover -s tests/py -p test_lock_dangling.py
"""

import os
import threading
import unittest

from fakehome import FakeHome, load_script

bg = load_script()


class DanglingStateFolderTest(unittest.TestCase):

    def test_dangling_symlink_raises(self):
        with FakeHome() as fh:
            folder = str(fh.resolve(".local/state/dms/browserGlass"))
            os.makedirs(os.path.dirname(folder))
            os.symlink(str(fh.resolve("unmounted/disk")), folder)
            result = []

            def attempt():
                try:
                    os.close(bg.state_lock(folder, env={"BG_LOCK_TIMEOUT": "0.2"}))
                    result.append("locked")
                except OSError as exc:
                    result.append(exc)

            worker = threading.Thread(target=attempt, daemon=True)
            worker.start()
            worker.join(5)
            self.assertFalse(worker.is_alive(), "state_lock still spinning")
            self.assertIsInstance(result[0], OSError)
            self.assertNotIsInstance(result[0], bg.StateBusy)


if __name__ == "__main__":
    unittest.main()

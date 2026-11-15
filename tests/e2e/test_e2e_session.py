"""End-to-end: `browserglass.py active-site` on the session file of a real
headless Firefox, without the companion.

Opt-in, like test_e2e_glass.py:

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -v

Firefox runs on a throwaway profile in .mozilla/firefox of a throwaway HOME
(browser.sessionstore.interval=1000), loads a page from the 127.0.0.1 server
under the name account.proton.test, then:
  1. the session file shows the page within 5 s;
  2. active-site --pid <firefox pid> --title <the window title> answers
     host account.proton.test, domain proton.test, source session;
  3. the decoder reads the file exactly as Firefox does: the decoded JSON
     equals IOUtils.readJSON(path, {decompress: true}) run in the browser.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(REPO, "browserglass.py")
DATA = os.path.join(REPO, "data")
sys.path.insert(0, HERE)

import marionette as mn  # noqa: E402

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None

PROFILE_ROOT = ".mozilla/firefox"
PROFILE_NAME = "e2esession.default"
HOST = "account.proton.test"
WRITE_TIMEOUT = 5.0
PREFS = dict(mn.test_host_prefs([HOST]), **{
    "browser.sessionstore.interval": 1000,
    "browser.sessionstore.resume_from_crash": True,
})


def setUpModule():
    if E2E and FIREFOX:
        mn.install_signal_handlers()


def load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("browserglass_e2e", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class SessionE2E(unittest.TestCase):

    def setUp(self):
        self.bg = load_script()
        self.server = mn.TestServer().start()
        self.addCleanup(self.server.stop)
        self.browser = b = mn.Browser(firefox=FIREFOX, manage_user_js=False, prefs=PREFS)
        self.addCleanup(b.cleanup)  # kills Firefox and its helpers, removes the tree
        shutil.rmtree(b.profile, ignore_errors=True)  # the harness's own profile: unused
        b.profile = os.path.join(b.home, PROFILE_ROOT, PROFILE_NAME)
        os.makedirs(b.profile, mode=0o700)
        with open(os.path.join(b.home, PROFILE_ROOT, "profiles.ini"), "w", encoding="utf-8") as f:
            f.write("[Profile0]\nName=e2esession\nIsRelative=1\nPath=%s\nDefault=1\n\n"
                    "[General]\nStartWithLastProfile=1\nVersion=2\n" % PROFILE_NAME)
        mn.write_user_js(b.profile, b.prefs)
        self.env = dict(b.env, PYTHONDONTWRITEBYTECODE="1")

    def tearDown(self):
        if self.browser.proc is not None:
            self.browser.stop()

    def active_site(self, title):
        proc = subprocess.run(
            [sys.executable, "-I", SCRIPT, "active-site", "--json", "--pid", str(self.browser.proc.pid),
             "--app-id", "firefox", "--title", title, "--data", DATA],
            env=self.env, cwd=self.browser.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("\n"), 1, proc.stdout)
        return json.loads(proc.stdout)

    def test_active_site_from_the_session_file(self):
        b = self.browser
        try:
            b.start()
            url = self.server.url("/article.html", host=HOST)
            b.navigate(url)
            title = b.chrome_js("return document.title;")  # what niri shows
            path = os.path.join(b.profile, "sessionstore-backups", "recovery.jsonlz4")
            deadline = time.monotonic() + WRITE_TIMEOUT
            raw = None
            while time.monotonic() < deadline:
                try:
                    raw = self.bg.mozlz4_read(path)
                except (OSError, ValueError):
                    raw = None
                if raw is not None and url.encode() in raw:
                    break
                time.sleep(0.05)
            else:
                self.fail("the session file did not show %s within %ss" % (url, WRITE_TIMEOUT))

            doc = self.active_site(title)
            age = doc.pop("age")
            self.assertEqual(doc, {"host": HOST, "domain": "proton.test", "source": "session"})
            self.assertIsInstance(age, (int, float))
            self.assertTrue(0 <= age < 60, age)

            # the decoder against Firefox's own reader, on one stable file
            copy = os.path.join(b.root, "copy.jsonlz4")
            shutil.copyfile(path, copy)
            oracle = b.chrome_js("return IOUtils.readJSON(arguments[0], {decompress: true})"
                                 ".then(j => JSON.stringify(j));", copy)
            self.assertEqual(json.loads(self.bg.mozlz4_read(copy).decode("utf-8")), json.loads(oracle))
        except AssertionError as exc:
            raise AssertionError("%s\n--- firefox log ---\n%s" % (exc, b.log_tail()))
        finally:
            b.stop()


if __name__ == "__main__":
    unittest.main()

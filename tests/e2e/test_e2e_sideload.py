"""End-to-end: the companion add-on as `sync --plugin-dir <repo>` deposits it
(profile extensions/ folder, prefs in the user.js block, native messaging
manifest and wrapper), in real headless browsers.

Opt-in (needs the browsers, about 10 s):

    BG_E2E=1 BG_LIBREWOLF=/path/to/librewolf \\
        python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_sideload.py' -v

Throwaway browsers only: fake HOME and XDG folders, profiles in its
.librewolf or .mozilla/firefox, 127.0.0.1 page server, black-hole proxy,
remote.prefs.recommended=false (Marionette would otherwise force
extensions.autoDisableScopes=0, which hides what the companion prefs do).

LibreWolf (BG_LIBREWOLF; unsigned add-ons allowed, autoDisableScopes 15):
  1. fresh profile: the add-on is active at the first start, the page gets
     data-browserglass-live, status says installed / connected;
  2. existing profile (started once before the sync): active at the first
     restart (startupScanScopes gets the profile bit); then uninstall: the
     add-on is gone at the next start, and not back from a stale
     extensions.json at the start after.
Firefox release (BG_FIREFOX or the auto-detected one; skipped on another
channel):
  3. a profile started once (compatibility.ini names the build): sync
     deposits nothing (signing_enforced): no xpi, no companion pref, no
     manifest; status companion unavailable;
  4. safety net: an xpi deposited while the channel is unknown (fresh
     profile, then compatibility.ini made to point to a build folder
     without channel-prefs.js) is deleted by Firefox at startup; the next
     sync says
     signing_required, leaves no xpi or companion pref (prefs.js back to
     the originals), and the sync after does not deposit it again.
"""

import json
import os
import re
import shutil
import sys
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
LIBREWOLF = mn.find_librewolf() if E2E else None

HOSTS = ("page.test",)
PAGE = (b"<!doctype html><html><head><meta charset='utf-8'><title>Sideload</title>"
        b"</head><body><p>Some text.</p></body></html>")
ACTIVE = 20.0  # seconds for an add-on to show up active after the start


def setUpModule():
    if E2E and (FIREFOX or LIBREWOLF):
        mn.install_signal_handlers()


def binary_channel(binary):
    """app.update.channel of a Firefox build, from its installation folder."""
    text = ch.read(os.path.join(os.path.dirname(os.path.realpath(binary)), bg.CHANNEL_PREFS_REL))
    m = bg._CHANNEL_PREF.search(text or "")
    return m.group(1) if m else None


class _Sideload(unittest.TestCase):
    BINARY = None
    ROOT = None

    def setUp(self):
        self.server = mn.TestServer({"/p.html": ("text/html; charset=utf-8", PAGE)}).start()
        self.addCleanup(self.server.stop)
        self.browser = b = mn.Browser(firefox=self.BINARY, manage_user_js=False,
                                      recommended_prefs=False, prefs=mn.test_host_prefs(HOSTS))
        self.addCleanup(b.cleanup)
        shutil.rmtree(b.profile, ignore_errors=True)  # the harness's own profile: unused
        self.h = ch.Home(b, self.ROOT, "e2eside.default")

    def tearDown(self):
        if self.browser.proc is not None:
            self.browser.stop()

    def fail_log(self, fn):
        try:
            fn()
        except AssertionError as exc:
            raise AssertionError("%s\n--- browser log ---\n%s" % (exc, self.browser.log_tail()))

    def wait_addon(self, want_active=True, timeout=ACTIVE):
        """The add-on's record once active (want_active), else None."""
        return self.h.wait(lambda: (lambda a: a if a and a["active"] == want_active else None)(
            self.h.addon()), timeout, 0.25)

    def page_live(self):
        b = self.browser
        b.navigate(self.server.url("/p.html", host="page.test"))
        return self.h.wait(lambda: b.js("return document.documentElement.hasAttribute(arguments[0])",
                                        ch.LIVE), 10, 0.1)

    def no_companion_prefs(self):
        return not set(ch.COMPANION_PREFS) & set(self.h.block_prefs())


@unittest.skipUnless(E2E and LIBREWOLF, "set BG_E2E=1 and BG_LIBREWOLF=/path/to/librewolf to run")
class LibreWolfSideloadE2E(_Sideload):
    BINARY = LIBREWOLF
    ROOT = ".librewolf"

    def test_fresh_profile(self):
        self.fail_log(self._fresh)

    def _fresh(self):
        b, h = self.browser, self.h
        out = h.sync()
        self.assertEqual(out["companion"], [{"profile": out["changed"][0], "state": "pending_restart"}], out)
        self.assertTrue(os.path.isfile(h.xpi), "no xpi deposited")
        self.assertEqual(json.loads(ch.read(h.manifest))["allowed_extensions"], [ch.COMPANION_ID])
        self.assertTrue(set(ch.COMPANION_PREFS) <= set(h.block_prefs()), h.block_prefs())
        b.start()
        addon = self.wait_addon()
        self.assertTrue(addon, "the add-on is not active at the first start: %r" % (h.addon(),))
        self.assertEqual(addon["scope"], ch.SCOPE_PROFILE, addon)
        self.assertFalse(addon["temporary"], addon)
        self.assertTrue(self.page_live(), "no data-browserglass-live on the page")
        st = h.status()
        self.assertEqual(h.profile_status(st)["companion"], "installed", st)
        self.assertEqual(st["companion"]["state"], "connected", st["companion"])
        self.assertTrue(st["companion"]["manifest"], st["companion"])

    def test_existing_profile_then_uninstall(self):
        self.fail_log(self._existing)

    def _existing(self):
        b, h = self.browser, self.h
        b.start()
        self.assertIsNone(h.addon())
        h.quit()
        out = h.sync()
        self.assertEqual(out["companion"][0]["state"], "pending_restart", out)
        self.assertTrue(os.path.isfile(h.xpi), "no xpi deposited")
        self.assertTrue(int(h.block_prefs()["extensions.startupScanScopes"]) & 1, h.block_prefs())
        b.start()
        addon = self.wait_addon()
        self.assertTrue(addon, "the add-on is not active at the first restart: %r" % (h.addon(),))
        self.assertTrue(self.page_live(), "no data-browserglass-live on the page")
        h.quit()

        out = h.run(["uninstall"], stdin_bootstrap=True)
        self.assertTrue(out.get("xpi_removed"), out)
        self.assertFalse(os.path.lexists(h.xpi), "xpi left by uninstall")
        self.assertFalse(os.path.lexists(h.manifest), "manifest left by uninstall")
        self.assertTrue(self.no_companion_prefs(), h.block_prefs())
        self.assertIn(ch.COMPANION_ID, ch.read(os.path.join(h.profile, bg.EXTENSIONS_JSON)) or "",
                      "the next start must see a stale extensions.json")
        for start in ("next start", "start after"):
            b.start()
            time.sleep(2)  # the startup scan is done before Marionette answers; margin
            self.assertIsNone(h.addon(), "add-on still there at the %s" % start)
            h.quit()
        self.assertNotIn(ch.COMPANION_ID, ch.read(os.path.join(h.profile, bg.EXTENSIONS_JSON)) or "")
        self.assertFalse(os.path.lexists(h.xpi))
        left = {p: v for p, v in h.prefs_js().items() if p in ch.COMPANION_PREFS}
        self.assertEqual(left, {}, "companion prefs left in prefs.js")


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class FirefoxReleaseSideloadE2E(_Sideload):
    BINARY = FIREFOX
    ROOT = ".mozilla/firefox"

    def setUp(self):
        channel = binary_channel(FIREFOX)
        if channel not in bg.SIGNED_CHANNELS:
            self.skipTest("Firefox channel %r does not require signing" % channel)
        super().setUp()

    def test_signing_enforced(self):
        self.fail_log(self._enforced)

    def _enforced(self):
        b, h = self.browser, self.h
        b.start()
        h.quit()
        self.assertTrue(os.path.isfile(os.path.join(h.profile, "compatibility.ini")))
        out = h.sync()
        self.assertEqual(out["companion"][0]["state"], "signing_enforced", out)
        self.assertFalse(os.path.lexists(h.xpi), "xpi deposited on Firefox release")
        self.assertTrue(self.no_companion_prefs(), h.block_prefs())
        self.assertTrue(h.block_prefs(), "no managed block in user.js")
        self.assertFalse(os.path.lexists(h.manifest), "manifest written with no add-on")
        st = h.status()
        self.assertEqual(h.profile_status(st)["companion"], "signing_enforced", st)
        self.assertEqual(st["companion"]["state"], "unavailable", st["companion"])

    def test_signing_required_safety_net(self):
        self.fail_log(self._net)

    def _net(self):
        b, h = self.browser, self.h
        # No installed Firefox build counts: on a machine with Firefox
        # release installed the first sync would say signing_enforced.
        h.env[bg.ENV_FIREFOX_BUILDS] = os.path.join(b.root, "no-firefox-builds")
        out = h.sync()  # fresh profile: no compatibility.ini, channel unknown
        self.assertEqual(out["companion"][0]["state"], "pending_restart", out)
        self.assertTrue(os.path.isfile(h.xpi), "no xpi deposited")
        self.assertTrue(set(ch.COMPANION_PREFS) <= set(h.block_prefs()), h.block_prefs())
        b.start()
        gone = h.wait(lambda: not os.path.lexists(h.xpi), ACTIVE, 0.25)
        self.assertTrue(gone, "Firefox release kept the unsigned xpi")
        a = h.addon()
        self.assertFalse(a and a["active"], a)
        h.quit()
        # A build whose channel cannot be read (no channel-prefs.js where
        # compatibility.ini points): the sync cannot tell signing_enforced.
        compat = os.path.join(h.profile, "compatibility.ini")
        unknown = os.path.join(b.root, "platform-without-channel")
        os.makedirs(unknown)
        text = re.sub(r"(?m)^LastPlatformDir=.*$", lambda m: "LastPlatformDir=" + unknown, ch.read(compat))
        with open(compat, "w", encoding="utf-8") as f:
            f.write(text)
        self.assertIsNone(bg.browser_channel(bg.compat_values(h.profile)))
        for n in (1, 2):
            out = h.sync()
            self.assertEqual(out["companion"][0]["state"], "signing_required", (n, out))
            self.assertFalse(os.path.lexists(h.xpi), "xpi deposited again (sync %d)" % n)
            self.assertTrue(self.no_companion_prefs(), (n, h.block_prefs()))
            left = {p: v for p, v in h.prefs_js().items() if p in ch.COMPANION_PREFS}
            self.assertEqual(left, {}, "companion prefs left in prefs.js (sync %d)" % n)
        st = h.status()
        self.assertEqual(h.profile_status(st)["companion"], "signing_required", st)


if __name__ == "__main__":
    unittest.main()

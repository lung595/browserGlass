"""render: golden tests of the four generated files (chrome CSS, content CSS,
user.js block, niri KDL) for every combination of the settings they read,
plus the rules they must (not) contain.

Run: python3 -B -m unittest discover -s tests/py -v

The golden files are tests/py/golden/{chrome,content,userjs,niri}.txt. The
matrix is generated below (itertools.product); each distinct output is
stored once with the list of cases producing it. After an intended change
of the output, regenerate them and review the diff:

    BG_REGEN_GOLDEN=1 python3 -B -m unittest discover -s tests/py -p test_render.py
"""

import collections
import itertools
import re
import unittest

from fakehome import check_golden, load_script

bg = load_script()

# What decides whether glass is active: (blur, glassEnabled, off, opacity).
STATE_DIMS = collections.OrderedDict([
    ("blur", (True, False)),
    ("glassEnabled", (True, False)),
    ("off", (False, True)),
    ("opacity", (0.85, 1.0)),
])
SITES_CSS = (
    "/* Site styles: fixture */\n\n"
    "/* a.test.css */\n"
    '@-moz-document regexp("https?://(?:[^/]*\\\\.)?a\\\\.test(?:[:/].*)?") {\n'
    "body { background: none !important; }\n"
    "}\n"
)


def settings(**values):
    out = bg.settings_from_json("{}")
    out.update(values)
    return out


def matrix(dims):
    """[(case label, {dim: value})] for every combination of `dims`."""
    names = list(dims)
    cases = []
    for values in itertools.product(*(dims[n] for n in names)):
        combo = dict(zip(names, values))
        label = " ".join("%s=%s" % (n, _label(combo[n])) for n in names)
        cases.append((label, combo))
    return cases


def _label(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, tuple)):
        return ",".join(value) or "-"
    if value is None:
        return "none"
    return str(value)


def split_state(combo):
    """(settings overrides, opacity, off) of a matrix combo."""
    combo = dict(combo)
    off = combo.pop("off", False)
    opacity = combo.pop("opacity", 0.85)
    return combo, opacity, off


CHROME_DIMS = collections.OrderedDict(STATE_DIMS)
CHROME_DIMS["privateGlass"] = (True, False)
CHROME_DIMS["surface"] = ("#2a3b4c", "#abc", "bogus", None)
CHROME_DIMS["mode"] = ("dark", "light")

CONTENT_DIMS = collections.OrderedDict(STATE_DIMS)
CONTENT_DIMS["pagesTransparent"] = (True, False)
CONTENT_DIMS["readerOpaque"] = (True, False)
CONTENT_DIMS["newTabGlass"] = (True, False)
CONTENT_DIMS["excluded"] = ((), ("example.org", "my-site.net"))
CONTENT_DIMS["sites"] = (False, True)

USERJS_DIMS = collections.OrderedDict(STATE_DIMS)
USERJS_DIMS["pagesTransparent"] = (True, False)
USERJS_DIMS["siteTheme"] = ("follow", "dark", "none")
USERJS_DIMS["isLight"] = (False, True)


def render_chrome(combo):
    over, opacity, off = split_state(combo)
    surface = over.pop("surface")
    mode = over.pop("mode")
    return bg.chrome_css(settings(**over), opacity, surface, mode, off=off)


def render_content(combo):
    over, opacity, off = split_state(combo)
    sites = SITES_CSS if over.pop("sites") else ""
    over["excluded"] = list(over["excluded"])
    return bg.content_css(settings(**over), opacity, sites, off=off)


def render_userjs(combo):
    over, opacity, off = split_state(combo)
    return bg.userjs_block(settings(**over), opacity, off=off)


def active(combo):
    return (combo["blur"] and combo["glassEnabled"] and not combo["off"]
            and combo["opacity"] < 1)


class GoldenTest(unittest.TestCase):

    def test_chrome(self):
        check_golden(self, "chrome.txt", collections.OrderedDict(
            (label, render_chrome(combo)) for label, combo in matrix(CHROME_DIMS)))

    def test_content(self):
        check_golden(self, "content.txt", collections.OrderedDict(
            (label, render_content(combo)) for label, combo in matrix(CONTENT_DIMS)))

    def test_userjs(self):
        check_golden(self, "userjs.txt", collections.OrderedDict(
            (label, render_userjs(combo)) for label, combo in matrix(USERJS_DIMS)))

    def test_niri(self):
        check_golden(self, "niri.txt", collections.OrderedDict(
            ("rule_needed=%s" % _label(flag), bg.niri_kdl(flag)) for flag in (False, True)))


class RulesTest(unittest.TestCase):
    """The plan's verified rules, checked on the matrix outputs."""

    def test_inactive_css_is_header_only(self):
        for label, combo in matrix(CONTENT_DIMS):
            if active(combo) and combo["pagesTransparent"]:
                continue
            text = render_content(combo)
            self.assertTrue(text.startswith(bg.V1_CSS_HEADER + "\n"), label)
            self.assertNotIn("{", text, label)
        for label, combo in matrix(CHROME_DIMS):
            if not active(combo):
                text = render_chrome(combo)
                self.assertTrue(text.startswith(bg.V1_CSS_HEADER + "\n"), label)
                self.assertNotIn("{", text, label)

    def test_inactive_reason_in_header(self):
        cases = [
            (dict(), True, "forced_off"),
            (dict(glassEnabled=False), False, "toggled_off"),
            (dict(blur=False), False, "blur_disabled"),
        ]
        for over, off, reason in cases:
            text = bg.chrome_css(settings(**over), 0.85, "#101418", off=off)
            self.assertIn("(%s)" % reason, text)
        self.assertIn("(opaque)", bg.chrome_css(settings(), 1.0, "#101418"))

    def test_chrome_private_rule_only_without_private_glass(self):
        rule = ':root[privatebrowsingmode="temporary"] body'
        on = bg.chrome_css(settings(privateGlass=True), 0.85, "#101418")
        off = bg.chrome_css(settings(privateGlass=False), 0.85, "#101418")
        self.assertNotIn("privatebrowsingmode", on)
        self.assertIn(rule, off)
        self.assertIn("background: rgba(16, 20, 24, 1) !important;", off)
        self.assertNotIn("[privatebrowsingmode]", off)
        # After the main rules.
        self.assertGreater(off.index(rule), off.index(".browserContainer"))

    def test_chrome_tint(self):
        text = bg.chrome_css(settings(), 0.85, "#2A3B4C")
        self.assertIn("body {\n  background: rgba(42, 59, 76, 0.85) !important;\n}", text)
        for selector in ("#main-window", "#navigator-toolbox", "#tabbrowser-tabpanels",
                         ".browserStack", "browser {"):
            self.assertIn(selector, text)

    def test_surface_fallback_by_mode(self):
        dark = bg.chrome_css(settings(), 0.5, None, "dark")
        light = bg.chrome_css(settings(), 0.5, "nope", "light")
        self.assertIn("rgba(16, 20, 24, 0.5)", dark)
        self.assertIn("rgba(247, 249, 255, 0.5)", light)
        self.assertIn("rgba(170, 187, 204, 0.5)", bg.chrome_css(settings(), 0.5, "#abc"))

    def test_content_order(self):
        text = bg.content_css(settings(readerOpaque=True, newTabGlass=True), 0.85, SITES_CSS)
        generic = text.index('regexp("https?://.*")')
        newtab = text.index('url("about:newtab"), url("about:home"), url("about:privatebrowsing")')
        sites = text.index("/* Site styles: fixture */")
        pdf = text.index("body:has(> #outerContainer #viewerContainer)")
        self.assertLess(generic, newtab)
        self.assertLess(newtab, sites)
        self.assertLess(sites, pdf)
        self.assertNotIn("about:reader", text)
        self.assertTrue(text.endswith(
            "body:has(> #outerContainer #viewerContainer) {\n"
            "  background-color: var(--body-bg-color) !important;\n}\n"))

    def test_content_reader_glass(self):
        text = bg.content_css(settings(readerOpaque=False), 0.85)
        self.assertIn('@-moz-document url-prefix("about:reader") {\n'
                      "  :root, body { background: transparent !important; }\n"
                      "  body { --main-background: transparent !important; }\n}", text)
        self.assertNotIn("outerContainer", text)
        self.assertNotIn(".toolbar", text)

    def test_content_newtab(self):
        on = bg.content_css(settings(newTabGlass=True), 0.85)
        off = bg.content_css(settings(newTabGlass=False), 0.85)
        self.assertIn("  :root { --newtab-background-color: transparent !important; }\n"
                      "  :root, body { background: transparent !important; }\n", on)
        self.assertNotIn("about:newtab", off)

    def test_content_exclusions(self):
        text = bg.content_css(settings(excluded=["example.org", "my-site.net"]), 0.85)
        rx = re.search(r'regexp\("([^"]*)"\)', text).group(1)
        pattern = re.compile(bg.css_unescape(rx))
        self.assertEqual(bg.js_regexp_problem(pattern.pattern), None)
        for url in ("https://example.org/", "http://www.example.org", "https://a.b.example.org:8080/x",
                    "https://my-site.net/page"):
            self.assertIsNone(pattern.fullmatch(url), url)
        for url in ("https://example.org.evil.test/", "https://notexample.org/", "https://site.net/"):
            self.assertIsNotNone(pattern.fullmatch(url), url)

    def test_userjs(self):
        def prefs(**over):
            return bg.userjs_block(settings(**over), 0.85)
        block = prefs()
        lines = block.splitlines()
        self.assertEqual(lines[0], bg.V1_USERJS_BEGIN)
        self.assertEqual(lines[-1], bg.V1_USERJS_END)
        self.assertIn('user_pref("%s", true);' % bg.PREF_STYLESHEETS, lines)
        self.assertIn('user_pref("%s", true);' % bg.PREF_TRANSPARENT, lines)
        self.assertIn('user_pref("%s", 0);' % bg.PREF_COLOR_SCHEME, lines)
        self.assertIn('user_pref("%s", 1);' % bg.PREF_COLOR_SCHEME, prefs(isLight=True).splitlines())
        self.assertIn('user_pref("%s", 0);' % bg.PREF_COLOR_SCHEME,
                      prefs(isLight=True, siteTheme="dark").splitlines())
        self.assertNotIn(bg.PREF_COLOR_SCHEME, prefs(siteTheme="none"))
        self.assertIn('user_pref("%s", false);' % bg.PREF_TRANSPARENT,
                      prefs(pagesTransparent=False).splitlines())
        off = bg.userjs_block(settings(), 0.85, off=True).splitlines()
        self.assertIn('user_pref("%s", true);' % bg.PREF_STYLESHEETS, off)
        self.assertIn('user_pref("%s", false);' % bg.PREF_TRANSPARENT, off)
        self.assertIn('user_pref("%s", 0);' % bg.PREF_COLOR_SCHEME, off)

    def test_niri(self):
        text = bg.niri_kdl(True)
        self.assertTrue(text.startswith(bg.V1_NIRI_HEADER + "\n"))
        self.assertIn("    opacity 1.0\n", text)
        rx = re.search(r'app-id=r#"(.*)"#', text).group(1)
        self.assertTrue(rx.startswith("^(") and rx.endswith(")$"))
        pattern = re.compile(rx)
        for app_id in bg.APP_IDS:
            self.assertTrue(pattern.search(app_id), app_id)
        for other in ("firefoxx", "org.mozilla.firefox.beta", "xfirefox", "orgXmozillaXfirefox"):
            self.assertIsNone(pattern.search(other), other)
        none = bg.niri_kdl(False)
        self.assertTrue(none.startswith(bg.V1_NIRI_HEADER + "\n"))
        self.assertNotIn("window-rule", none)

    def test_outputs_are_ascii(self):
        for label, combo in matrix(CONTENT_DIMS)[:8]:
            render_content(combo).encode("ascii")
        bg.niri_kdl(True).encode("ascii")
        bg.userjs_block(settings(), 0.5).encode("ascii")


class OpacityStateTest(unittest.TestCase):

    def test_effective_opacity(self):
        self.assertEqual(bg.effective_opacity(settings(), 0.8), (0.8, "dms"))
        self.assertEqual(bg.effective_opacity(settings(opacityOverride=True, opacity=0.6), 0.8),
                         (0.6, "override"))
        self.assertEqual(bg.effective_opacity(settings(opacityOverride=True), 0.8, forced=0.3),
                         (0.3, "forced"))
        self.assertEqual(bg.effective_opacity(settings(), 7), (1.0, "dms"))
        self.assertEqual(bg.effective_opacity(settings(), float("nan")), (1.0, "dms"))

    def test_glass_state_precedence(self):
        self.assertEqual(bg.glass_state(settings(glassEnabled=False, blur=False), 1.0, off=True),
                         (False, "forced_off"))
        self.assertEqual(bg.glass_state(settings(glassEnabled=False, blur=False), 1.0),
                         (False, "toggled_off"))
        self.assertEqual(bg.glass_state(settings(blur=False), 1.0), (False, "blur_disabled"))
        self.assertEqual(bg.glass_state(settings(), 1.0), (False, "opaque"))
        self.assertEqual(bg.glass_state(settings(), 0.0), (True, "active"))
        for _, reason in [bg.glass_state(settings(), 0.5)]:
            self.assertIn(reason, bg.REASONS)

    def test_rounding_agrees_with_text(self):
        # What is written ("1" for 0.99996) and the state agree.
        self.assertEqual(bg.glass_state(settings(), 0.99996), (False, "opaque"))
        self.assertEqual(bg.glass_state(settings(), 0.99994), (True, "active"))
        self.assertEqual(bg.glass_state(settings(), 10 ** 400), (False, "opaque"))
        # Unusable (overflowing) values fall back to the default: opaque.
        self.assertEqual(bg.glass_state(settings(), -(10 ** 400)), (False, "opaque"))

    def test_format_number(self):
        self.assertEqual(bg.format_number(0.85), "0.85")
        self.assertEqual(bg.format_number(1.0), "1")
        self.assertEqual(bg.format_number(0.0), "0")
        self.assertEqual(bg.format_number(1 / 3), "0.3333")


if __name__ == "__main__":
    unittest.main()

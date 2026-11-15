"""End-to-end: the live gating of the content stylesheet (liveControl), in a
real headless Firefox (and LibreWolf with BG_LIBREWOLF).

Opt-in (needs a Firefox binary, about 15 s per browser):

    BG_E2E=1 python3 -B -m unittest discover -s tests/e2e -p 'test_e2e_gate.py' -v

Skipped unless BG_E2E=1 and a Firefox binary is found (see marionette.py).
Throwaway browsers only (fake HOME, generated profile, 127.0.0.1 page
server, black-hole proxy); no browserglass.py subprocess: the stylesheets
come from its render functions.

Two stylesheets, from the same made-up site styles (the youtube.com style of
data/ renamed tube.test.css and mapped to vid.test and m.cov.test as well,
the generic style of data/, and edge.test.css, mapped to edgeoff.test as
well: rules Firefox drops or reads in a special way, which the gating must
keep so; each with SHADOW_CSS, a rule for an element in a shadow tree):
  - the original: liveControl off, nothing excluded (the v1.0 file);
  - the gated one: liveControl on, vid.test, cov.test (a parent of the mapped
    host m.cov.test), gone.test and edgeoff.test excluded at sync.
The original gives, for each host, the values "styled". On the same page,
for each host and both colour schemes, the gated stylesheet goes through the
five states the companion add-on can set on <html> (set here by Marionette):
none, OFF, LIVE, LIVE+OFF, none again. A host that is not excluded is styled
in the states without OFF; an excluded one only in LIVE (the bar variable,
set on every page, in the states without OFF). Styled values must equal the
original's, the others the page's own colours. The shadow tree element
cannot see the root's attributes: it is styled as by the original in every
state on a host that is not excluded (OFF included, a known limit), and
never on an excluded one (as when the original excludes it).
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tests", "py"))

import marionette as mn  # noqa: E402
from fakehome import load_script  # noqa: E402

bg = load_script()

E2E = os.environ.get("BG_E2E") == "1"
FIREFOX = mn.find_firefox() if E2E else None
LIBREWOLF = mn.find_librewolf() if E2E else None

OFF, LIVE = bg.ATTR_OFF, bg.ATTR_LIVE
STATES = ((False, False), (False, True), (True, False), (True, True), (False, False))
# The colour scheme of the pages: 0 dark, 1 light (live)
PREF_SCHEME = "layout.css.prefers-color-scheme.content-override"

# host -> the domain excluded at sync that covers it (None: not excluded)
HOSTS = {
    "www.tube.test": None,          # dedicated style
    "www.vid.test": "vid.test",     # same style, through the mapping
    "m.cov.test": "cov.test",       # same, a mapped host under the excluded domain
    "plain.test": None,             # generic style
    "gone.test": "gone.test",       # generic style
    "edge.test": None,              # edge.test.css
    "edgeoff.test": "edgeoff.test",  # the same, through the mapping
}
EXCLUDED = sorted({d for d in HOSTS.values() if d})

# A page shaped like the parts of youtube.com its style paints, plus a
# colour-scheme declaration (dark version: the generic style applies under a
# dark theme too).
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="color-scheme" content="dark light"><style>
html{background:rgb(1,1,1)} body{background:rgb(2,2,2)} ytd-app{display:block;background:rgb(5,5,5)}
#masthead-container{background:rgb(3,3,3)} #app{background:rgb(4,4,4)}
#e1,#e2,#e3,#e4,#e5,#e6,#e7,#e8,#e9,#e10,#e11,#e12,#e13{background:rgb(6,6,6)}
</style></head><body><ytd-app><div id="masthead-container">m</div></ytd-app><div id="app">a</div>
<div id="e1">1</div><div id="e2">2</div><div id="e3">3</div><div id="e4">4</div><div id="e5">5</div>
<div id="e6">6</div><div id="e7">7</div><div id="e8">8</div><div id="e9">9</div><div id="e10">10</div>
<div id="e11">11</div><div id="e12">12</div><div id="e13">13</div>
<div id="host"></div><script>
document.getElementById("host").attachShadow({mode: "open"}).innerHTML =
  '<style>#s1{background:rgb(7,7,7)}</style><section><div id="s1" class="in">s</div></section>';
</script></body></html>"""
BACKGROUND = "background-color"
BAR = "--browserglass-bar"
# (selector, property) -> the page's own value (no stylesheet of ours)
PAGE_VALUES = {
    ("html", BACKGROUND): "rgb(1, 1, 1)",
    ("html", BAR): "",
    ("body", BACKGROUND): "rgb(2, 2, 2)",
    ("ytd-app", BACKGROUND): "rgb(5, 5, 5)",
    ("#masthead-container", BACKGROUND): "rgb(3, 3, 3)",
    ("#app", BACKGROUND): "rgb(4, 4, 4)",
}
for _n in range(1, 14):
    PAGE_VALUES[("#e%d" % _n, BACKGROUND)] = "rgb(6, 6, 6)"
PAGE_VALUES[("#e9", "--scoped")] = ""
PROBES = sorted(PAGE_VALUES)
# The element in #host's shadow tree (read through its shadow root), under
# its top element: the shadow branch of the wrapper reaches it through "& *".
SHADOW = ("#host >> #s1", BACKGROUND)
PAGE_VALUES[SHADOW] = "rgb(7, 7, 7)"
SHADOW_CSS = "div.in#s1 { background: rgb(23, 0, 0) !important; }\n"

# Rules Firefox drops or reads in a special way (checked against the
# original): a "--x:" prelude eats the next rule, a {} block ends it, a
# combinator prelude is dropped, and so is a declaration left outside a rule
# with the rule after it (in @media too, html keeping its background), a
# ";" before a rule is skipped, @scope gets the plain gate and applies its
# own declarations to the scope root, @keyframes and a pseudo-element, a
# "--x" type selector does not eat the next rule, and the selectors after it
# in a list match (in @scope too), and a list with a selector starting with a
# combinator is dropped.
EDGE_CSS = """#e1 { background: rgb(11, 0, 0) !important; }
--stray: 1; #e2 { background: rgb(12, 0, 0) !important; }
#e3 { background: rgb(13, 0, 0) !important; }
--block: { a: b } #e4 { background: rgb(14, 0, 0) !important; }
> #e5 { background: rgb(15, 0, 0) !important; }
@scope (body) {
  #e5 { background: rgb(16, 0, 0) !important; }
  :scope > #app { background: rgb(17, 0, 0) !important; }
  --y, #e13 { background: rgb(26, 0, 0) !important; }
}
background-color: rgb(18, 0, 0) !important; #e6 { background: rgb(18, 0, 0) !important; }
; #e7 { background: rgb(19, 0, 0) !important; }
@media screen {
  background-color: rgb(20, 0, 0) !important; #e8 { background: rgb(20, 0, 0) !important; }
}
@scope (#e9) { background-color: rgb(21, 0, 0) !important; --scoped: 1; }
@keyframes bg-test { from { opacity: 1; } to { opacity: 1; } }
#app::before { content: "x"; animation: bg-test 1s; }
--dashed { color: red } #e10 { background: rgb(22, 0, 0) !important; }
--x, #e11 { background: rgb(24, 0, 0) !important; }
#e12, > #e5 { background: rgb(25, 0, 0) !important; }
"""


def browsers():
    """[(name, binary)] of the browsers to run."""
    out = [("firefox", FIREFOX)]
    if LIBREWOLF:
        out.append(("librewolf", LIBREWOLF))
    return out


def made_up_sites():
    """The site styles of the test (see the module docstring)."""
    real = bg.sites_load(os.path.join(REPO, "data"))
    styles = {
        "tube.test.css": real.styles["youtube.com.css"],
        bg.SITES_GENERIC_KEY: real.styles[bg.SITES_GENERIC_KEY],
        "edge.test.css": {"glass": EDGE_CSS},
    }
    styles = {key: dict(style, **{"glass: shadow tree": SHADOW_CSS}) for key, style in styles.items()}
    return bg.Sites(styles, {"tube.test.css": ["vid.test", "m.cov.test"],
                             "edge.test.css": ["edgeoff.test"]})


def stylesheet(sites, live, excluded):
    values = bg.settings_from_json("{}")
    values.update(liveControl=live, excluded=list(excluded))
    problems = []
    css = bg._render_content(values, 0.8, sites, False, None, problems)
    assert not problems, problems
    return css


def browser_prefs():
    prefs = mn.test_host_prefs(sorted(HOSTS))
    # LibreWolf's defaults: no HTTPS upgrade of the test server, real colour scheme
    prefs.update({"dom.security.https_only_mode": False,
                  "privacy.resistFingerprinting": False,
                  PREF_SCHEME: 0})
    return prefs


def snapshot(b):
    out = {}
    for selector in sorted({s for s, _ in PROBES}):
        values = b.css(selector, *sorted({p for s, p in PROBES if s == selector}))
        for prop, value in values.items():
            out[(selector, prop)] = value
    out[SHADOW] = b.js("const el = document.getElementById('host').shadowRoot.getElementById('s1');"
                       "return getComputedStyle(el).getPropertyValue(arguments[0]).trim();",
                       SHADOW[1])
    return out


def set_scheme(b, dark):
    b.chrome_js("Services.prefs.setIntPref(arguments[0], arguments[1]);", PREF_SCHEME, 0 if dark else 1)
    if not b.wait_for("return matchMedia('(prefers-color-scheme: dark)').matches === arguments[0];",
                      mn.WAIT_TIMEOUT, dark):
        raise AssertionError("the colour scheme did not switch to %s" % ("dark" if dark else "light"))
    settle(b)


def set_state(b, live, off):
    b.js("const root = document.documentElement;"
         "for (const [name, on] of arguments[0])"
         "  on ? root.setAttribute(name, '') : root.removeAttribute(name);",
         [[LIVE, live], [OFF, off]])
    settle(b)


def settle(b):
    """Wait for the CSS transitions the last change started (the generic
    style of data/ fades backgrounds in 0.5 s) to end."""
    if not b.wait_for("getComputedStyle(document.body).backgroundColor;"
                      "return !document.getAnimations().some("
                      "  a => a instanceof CSSTransition && a.playState === 'running');"):
        raise AssertionError("CSS transitions still running")


def measure(binary, css, states):
    """{(host, dark, live, off): snapshot} for the stylesheet `css`, each
    host and colour scheme going through `states`."""
    out = {}
    with mn.TestServer({"/p.html": ("text/html; charset=utf-8", PAGE.encode("utf-8"))}) as srv, \
            mn.Browser(content_css=css, prefs=browser_prefs(), firefox=binary) as b:
        for host in sorted(HOSTS):
            b.navigate(srv.url("/p.html", host))
            assert b.js("return location.hostname;") == host
            for dark in (True, False):
                set_scheme(b, dark)
                for live, off in states:
                    set_state(b, live, off)
                    out[(host, dark, live, off)] = snapshot(b)
    return out


@unittest.skipUnless(E2E and FIREFOX, "set BG_E2E=1 (and have a Firefox binary) to run")
class GateE2E(unittest.TestCase):

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        mn.install_signal_handlers()
        sites = made_up_sites()
        cls.original = stylesheet(sites, False, ())
        cls.gated = stylesheet(sites, True, EXCLUDED)
        assert OFF not in cls.original and LIVE in cls.gated

    def test_states(self):
        for name, binary in browsers():
            with self.subTest(browser=name):
                self.check(binary)

    def check(self, binary):
        styled = measure(binary, self.original, ((False, False),))
        gated = measure(binary, self.gated, STATES)
        for host, excluded in sorted(HOSTS.items()):
            for dark in (True, False):
                want_styled = styled[(host, dark, False, False)]
                # the original styles this host: the test is not vacuous
                self.assertNotEqual(want_styled, PAGE_VALUES, (host, dark))
                for live, off in STATES:
                    on = (live and not off) if excluded else not off
                    want = dict(want_styled if on else PAGE_VALUES)
                    # the bar variable is set on every page (excluded ones
                    # included, it only names a colour), unless OFF
                    want[("html", BAR)] = PAGE_VALUES[("html", BAR)] if off else want_styled[("html", BAR)]
                    # the shadow tree element cannot see the root's attributes
                    want[SHADOW] = PAGE_VALUES[SHADOW] if excluded else want_styled[SHADOW]
                    with self.subTest(host=host, dark=dark, live=live, off=off):
                        self.assertEqual(gated[(host, dark, live, off)], want)
        edge = styled[("edge.test", True, False, False)]
        # what Firefox drops stays dropped, what follows still applies
        self.assertEqual(edge[("#e1", BACKGROUND)], "rgb(11, 0, 0)")
        self.assertEqual(edge[("#e2", BACKGROUND)], "rgb(6, 6, 6)")
        self.assertEqual(edge[("#e3", BACKGROUND)], "rgb(13, 0, 0)")
        self.assertEqual(edge[("#e4", BACKGROUND)], "rgb(14, 0, 0)")
        self.assertEqual(edge[("#e5", BACKGROUND)], "rgb(16, 0, 0)")
        self.assertEqual(edge[("#app", BACKGROUND)], "rgb(17, 0, 0)")
        self.assertNotIn(edge[("html", BACKGROUND)], ("rgb(18, 0, 0)", "rgb(20, 0, 0)"))
        self.assertEqual(edge[("#e6", BACKGROUND)], "rgb(6, 6, 6)")
        self.assertEqual(edge[("#e7", BACKGROUND)], "rgb(19, 0, 0)")
        self.assertEqual(edge[("#e8", BACKGROUND)], "rgb(6, 6, 6)")
        self.assertEqual(edge[("#e9", BACKGROUND)], "rgb(21, 0, 0)")
        self.assertEqual(edge[("#e9", "--scoped")], "1")
        self.assertEqual(edge[("#e10", BACKGROUND)], "rgb(22, 0, 0)")
        self.assertEqual(edge[("#e11", BACKGROUND)], "rgb(24, 0, 0)")
        self.assertEqual(edge[("#e12", BACKGROUND)], "rgb(6, 6, 6)")
        self.assertEqual(edge[("#e13", BACKGROUND)], "rgb(26, 0, 0)")
        # the site styles reach into shadow trees (the test is not vacuous)
        for host in sorted(HOSTS):
            self.assertEqual(styled[(host, False, False, False)][SHADOW], "rgb(23, 0, 0)", host)


if __name__ == "__main__":
    unittest.main()

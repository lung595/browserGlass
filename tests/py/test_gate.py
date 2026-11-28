"""render: live gating (liveControl) of the content stylesheet.

Run: python3 -B -m unittest discover -s tests/py -v

  - css_gate_selector_list: where the gate goes in a selector list;
  - css_gate_rules: the "nesting run" on rule lists (at-rules copied or
    gated recursively, @scope, stray declarations, nested rules untouched),
    and on every site style of data/: only text inserted (ungate() gives the
    input back), braces balanced, sites_validate still happy;
  - content_css / content_live_section: liveControl off is the v1.0 file,
    on it gates the http(s) rules only, the live section brings back the
    domains excluded at sync (fixture tests/py/fixtures/sites/), and the
    gating grows the text it gates by at most MAX_GROWTH on data/, and so
    does the whole file for typical exclusions (the live section adds the
    blocks of each excluded domain once more, gated, so the whole file
    grows more than that when the heaviest sites are excluded: about 47 %
    with google.com alone, 53 % for EXCLUDED_HEAVY).
The golden cases are in test_render.py (content.txt) and test_sites.py
(sites-build.txt).
"""

import re
import unittest

from fakehome import FIXTURES, REPO, load_script

bg = load_script()

DATA = str(REPO / "data")
G = "@G"
COND = "C"
# Real-data exclusions of the growth and round-trip tests.
EXCLUDED = ("youtube.com", "proton.me", "github.com")
# The same with the heaviest styles of data/ (the largest live section).
EXCLUDED_HEAVY = ("google.com", "chatgpt.com", "youtube.com", "github.com", "reddit.com")
# Size growth allowed by the gating (gated / ungated - 1) on data/.
MAX_GROWTH = 0.45
# The same for the live section (see test_growth).
MAX_GROWTH_LIVE = 0.60
# The content file with each site style once per colour scheme, against
# one copy (see test_scheme_size).
MAX_SCHEME_RATIO = 2.75
BLOCK = re.compile(r'/\* (?P<comment>.*?) \*/\n@-moz-document regexp\("(?P<rx>[^"]*)"\) \{\n')

# Selector list -> the list gated with G. 19 cases: lists, :root/html,
# pseudo-elements (legacy ones included), combinators, :has/:is/:not,
# escapes, strings, comments.
SELECTOR_CASES = [
    ("html, body", "html@G, body@G"),
    (":root", ":root@G"),
    ("a > b + c ~ d e", "a > b + c ~ d e@G"),
    ("#s::before", "#s@G::before"),
    ("#s:before", "#s@G:before"),
    ("a:hover::-webkit-scrollbar-thumb:hover", "a:hover@G::-webkit-scrollbar-thumb:hover"),
    ("::selection", "@G::selection"),
    ("#h:has(> .q, a::b)", "#h:has(> .q, a::b)@G"),
    (".erp-tab\\:rounded-none, \\@container\\/main",
     ".erp-tab\\:rounded-none@G, \\@container\\/main@G"),
    (".text-black\\!, /* @ c, x */\n  .text-gray-900 /* @ d */ ",
     ".text-black\\!@G, /* @ c, x */\n  .text-gray-900@G /* @ d */ "),
    ('a[title="x::y, z"] b', 'a[title="x::y, z"] b@G'),
    ("svg|rect", "svg|rect@G"),
    ("a || b", "a || b@G"),
    ("&._1e0c", "&._1e0c@G"),
    (":is(a,b) :not(c)", ":is(a,b) :not(c)@G"),
    ("x:first-letter", "x@G:first-letter"),
    ("x:nth-child(2n+1)", "x:nth-child(2n+1)@G"),
    ("#radix-:rq:", "#radix-:rq:@G"),
    ("a\n>\nb", "a\n>\nb@G"),
]


def ungate(text, cond, shadow=True):
    """`text` (css_gate_rules output for `cond` and `shadow`) without what
    the gating inserted: each wrapper (":where(cond){", or the @scope
    declarations' one) with its "}", each selector gate (the generic
    style's with its exemption, _GATE_KEEP). Wrappers never nest (group
    rules stay outside them)."""
    nest = bg._Nest(cond, shadow)
    keep = bg._Nest(cond, shadow, True)
    out = []
    pos = 0
    while True:
        found = [(at, opener) for at, opener in
                 ((text.find(o, pos), o) for o in (nest.open, nest.scope_open)) if at >= 0]
        if not found:
            break
        at, opener = min(found)
        brace = at + len(opener) - 1
        close = bg._gate_block_end(text, brace, len(text))
        out += [text[pos:at], text[brace + 1:close - 1]]
        pos = close
    out.append(text[pos:])
    text = "".join(out).replace(keep.amp, "").replace(keep.plain, "")
    return text.replace(nest.amp, "").replace(nest.plain, "")


def ungate_scheme(text, gate):
    """`text` without the gating of the root condition `gate` (None: none)
    and of GATE_DARK[gate] (_scheme_gated's two branches, with or without
    the shadow branch)."""
    if gate:
        text = ungate(text, gate)
    return ungate(ungate(text, bg.GATE_DARK[gate]), bg.GATE_DARK[gate], False)


def braces(text):
    """Depth of the top-level "{" left open in `text` (negative: too many
    "}"), strings and comments skipped, and the lowest depth reached."""
    depth = low = 0
    for match in bg._GATE_TOK.finditer(text):
        char = match.group("ch")
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            low = min(low, depth)
    return depth, low


def blocks(css):
    """[(comment, compiled pattern, start)] of the regexp() blocks of `css`."""
    return [(m.group("comment"), re.compile(bg.css_unescape(m.group("rx"))), m.start())
            for m in BLOCK.finditer(css)]


def matching(css, url):
    """Comments of the blocks of `css` whose regexp matches all of `url`."""
    return [comment for comment, rx, _ in blocks(css) if rx.fullmatch(url)]


def settings(**values):
    out = bg.settings_from_json("{}")
    out.update(values)
    return out


_REAL = []


def real_sites():
    """sites_load(data/), loaded once."""
    if not _REAL:
        _REAL.append(bg.sites_load(DATA))
    return _REAL[0]


def render(sites, **values):
    """The content stylesheet of `sites` for the default settings plus
    `values`, as sync renders it (glass active)."""
    return bg._render_content(settings(**values), 0.8, sites, False, None)


class SelectorTest(unittest.TestCase):

    def test_cases(self):
        for sel, want in SELECTOR_CASES:
            with self.subTest(sel=sel):
                self.assertEqual(bg.css_gate_selector_list(sel, G), want)

    def test_only_inserts(self):
        for sel, _ in SELECTOR_CASES:
            self.assertEqual(bg.css_gate_selector_list(sel, G).replace(G, ""), sel)

    def test_empty(self):
        self.assertEqual(bg.css_gate_selector_list("", G), "")
        self.assertEqual(bg.css_gate_selector_list("  /* x */ ", G), "  /* x */ ")

    def test_skip_first(self):
        for sel, want in (("--x, a", "--x, a@G"), ("--x b::before, a, c", "--x b::before, a@G, c@G"),
                          ("--x", "--x"), (", a", ", a@G")):
            with self.subTest(sel=sel):
                self.assertEqual(bg.css_gate_selector_list(sel, G, skip_first=True), want)

    def test_relative(self):
        for sel in ("> a", "a, > b", "a,~b", "a, /* c */ + b", "a,\n  > b"):
            with self.subTest(sel=sel):
                self.assertTrue(bg._gate_selector_relative(sel))
        for sel in ("a > b", "a, b ~ c", ":has(> a), b", '[x=", > y"]', "a /* , > b */", ""):
            with self.subTest(sel=sel):
                self.assertFalse(bg._gate_selector_relative(sel))


class RuleListTest(unittest.TestCase):

    def gate(self, text):
        return bg.css_gate_rules(text, COND)

    def test_run(self):
        self.assertEqual(self.gate("a{x:1}\n"), ":where(C){a:where(&,& *){x:1}}\n")
        # one wrapper per run of style rules, comments inside, whitespace after
        self.assertEqual(self.gate("a{} /* c */ b{}\n\n@media x{}\nc{}"),
                         ":where(C){a:where(&,& *){} /* c */ b:where(&,& *){}}\n\n"
                         "@media x{}\n:where(C){c:where(&,& *){}}")

    def test_group_rules_recursive(self):
        self.assertEqual(
            self.gate("@media (x){ b, c{y:2} @supports (z){d::after{}} }"),
            "@media (x){ :where(C){b:where(&,& *), c:where(&,& *){y:2}} "
            "@supports (z){:where(C){d:where(&,& *)::after{}}} }")
        self.assertEqual(self.gate("@-moz-document url-prefix(x){a{}}"),
                         "@-moz-document url-prefix(x){:where(C){a:where(&,& *){}}}")
        self.assertEqual(self.gate("@LAYER{a{}}"), "@LAYER{:where(C){a:where(&,& *){}}}")

    def test_other_at_rules_verbatim(self):
        for text in ("@keyframes k{from{a:1}to{b:2}}",
                     "@-webkit-keyframes k { 0% { a: 1 } }",
                     "@font-face{font-family:f; src: url(x.woff)}",
                     "@page :first { margin: 1in }",
                     "@property --x { syntax: '<color>'; inherits: false; initial-value: red }"):
            with self.subTest(text=text):
                self.assertEqual(self.gate(text), text)
        self.assertEqual(self.gate("@layer x;\na{}"), "@layer x;\n:where(C){a:where(&,& *){}}")
        self.assertEqual(self.gate("@namespace svg url(http://x);\na{}"),
                         "@namespace svg url(http://x);\n:where(C){a:where(&,& *){}}")

    def test_scope_simple_gate(self):
        self.assertEqual(
            self.gate("@scope (.a) to (.b) { b, c::before{x:1} @media (y){d{}} }"),
            "@scope (.a) to (.b) { b:where(C, C *), c:where(C, C *)::before{x:1} "
            "@media (y){d:where(C, C *){}} }")

    def test_scope_declarations(self):
        # declarations of the scope root, each in an explicit :where(:scope) rule
        self.assertEqual(
            self.gate("@scope (a) { color: red !important; --v: 1; b{} @media x{ c: d } e: f }"),
            "@scope (a) { :where(:scope:where(C, C *)){color: red !important;} "
            ":where(:scope:where(C, C *)){--v: 1;} b:where(C, C *){} "
            "@media x{ :where(:scope:where(C, C *)){c: d }} :where(:scope:where(C, C *)){e: f }}")
        # a custom property's value may hold a {} block: up to ";"
        self.assertEqual(self.gate("@scope (a) { --x: {a:b} c{} ; d{} }"),
                         "@scope (a) { :where(:scope:where(C, C *)){--x: {a:b} c{} ;} d:where(C, C *){} }")

    def test_stray_declaration_intact(self):
        # Firefox drops "--x:..." up to the end of the next {} block, a ";"
        # included: copied with that block, so what follows still applies
        self.assertEqual(
            self.gate("@layer{ html,body{c:1} --v: 1 !important; e{} f{} }"),
            "@layer{ :where(C){html:where(&,& *),body:where(&,& *){c:1}} --v: 1 !important; e{} "
            ":where(C){f:where(&,& *){}} }")
        self.assertEqual(self.gate("--x: {a:b} c{}"), "--x: {a:b} :where(C){c:where(&,& *){}}")
        self.assertEqual(self.gate("@media x{ --q: 1 }"), "@media x{ --q: 1 }")
        # and so is any prelude holding a ";" (a declaration left outside a
        # rule): inside the wrapper it would be a declaration of the root
        for text in ("foo; a{}", "color: red; a{}", "@media x{ color:red; a{} }",
                     "a; --x: {}", "; c: d; e{}"):
            with self.subTest(text=text):
                self.assertEqual(self.gate(text), text)
        self.assertEqual(self.gate("color: red; a{x:1} b{}"),
                         "color: red; a{x:1} :where(C){b:where(&,& *){}}")
        # a ";" in a string or brackets is not one
        self.assertEqual(self.gate('a[x=";"]{}'), ':where(C){a[x=";"]:where(&,& *){}}')

    def test_leading_semicolon(self):
        # Firefox skips a ";" before a rule: it stays where it is
        self.assertEqual(self.gate("; a{}"), "; :where(C){a:where(&,& *){}}")
        self.assertEqual(self.gate("#p0{}; #p1{}"), ":where(C){#p0:where(&,& *){}; #p1:where(&,& *){}}")
        self.assertEqual(self.gate("@scope (a) { ; b{} }"), "@scope (a) { ; b:where(C, C *){} }")

    def test_trailing_at(self):
        # a stray "@" at the end of a rule list (sites_validate accepts it)
        for text in ("@", "a{} @", "a{}@", "@media{a{}}@", "@media x{a{} @}"):
            with self.subTest(text=text):
                self.assertEqual(ungate(self.gate(text), COND), text)
        self.assertEqual(self.gate("@"), "@")
        self.assertEqual(self.gate("a{} @"), ":where(C){a:where(&,& *){}} @")
        sites = bg.Sites({"a.test.css": {"glass": "body{background:none} @"}}, {})
        self.assertEqual(bg.sites_validate(sites.styles["a.test.css"]["glass"]), [])
        css = bg.sites_build_css(sites, gate=bg.GATE_NORMAL_ROOT)
        self.assertIn("body:where(&,& *){background:none}} @\n}", css)

    def test_combinator_prelude_intact(self):
        # dropped by Firefox, kept so: inside the wrapper "> a" would be a
        # relative selector, so the rule would apply (any item of the list)
        self.assertEqual(self.gate("> a{x:1} b{}"), "> a{x:1} :where(C){b:where(&,& *){}}")
        for text in ("a, > b{}", "a, /* c */ ~ b{}", "a,\n+ b{}", "--x, > a{}"):
            with self.subTest(text=text):
                self.assertEqual(self.gate(text), text)
        self.assertEqual(self.gate("a, > b{} c{}"), "a, > b{} :where(C){c:where(&,& *){}}")
        # in @scope a relative selector is read (relative to the scope root)
        self.assertEqual(self.gate("@scope (a) { b, > c{} }"),
                         "@scope (a) { b:where(C, C *), > c:where(C, C *){} }")

    def test_dashed_prelude_intact(self):
        # "--x" then the gate would read "--x:", a declaration eating "c{}"
        self.assertEqual(self.gate("--x{a:b} c{}"), "--x{a:b} :where(C){c:where(&,& *){}}")
        self.assertEqual(self.gate("a{} --x::before {a:b} c{}"),
                         ":where(C){a:where(&,& *){}} --x::before {a:b} :where(C){c:where(&,& *){}}")
        self.assertEqual(self.gate("@scope (a) { --x{a:b} c{} }"),
                         "@scope (a) { --x{a:b} c:where(C, C *){} }")

    def test_dashed_prelude_list_gated(self):
        # the "--x" type selector never matches, the others do: gated with
        # the plain gate, outside the wrapper
        for text, want in (("--x, a{}", "--x, a:where(C, C *){}"),
                           ("--x.y, a{}", "--x.y, a:where(C, C *){}"),
                           ("--x b, a::before{} c{}",
                            "--x b, a:where(C, C *)::before{} :where(C){c:where(&,& *){}}"),
                           ("@scope (b){ --y, c{} }", "@scope (b){ --y, c:where(C, C *){} }"),
                           ("@media x{ --y, c{} }", "@media x{ --y, c:where(C, C *){} }")):
            with self.subTest(text=text):
                self.assertEqual(self.gate(text), want)
                self.assertEqual(ungate(want, COND), text)
        normal = bg._Nest(bg.GATE_NORMAL_ROOT)
        self.assertEqual(bg.css_gate_rules("--x, a{}", bg.GATE_NORMAL_ROOT),
                         "--x, a%s{}" % normal.plain)
        # "--x:" (a declaration look) is still dropped by Firefox: kept so
        self.assertEqual(self.gate("--x:hover, a{}"), "--x:hover, a{}")

    def test_live_leaves_out_ungated_at_rules(self):
        """The live section applies on excluded domains without ATTR_LIVE
        too: at-rules that cannot be gated are left out of it (but
        @keyframes, used by name)."""
        text = ("@page :first { margin: 0 } @property --p { syntax: '*'; inherits: false }\n"
                "@font-face { font-family: f } @counter-style c { system: cyclic }\n"
                "@view-transition { navigation: auto } @font-feature-values f { @swash { s: 1 } }\n"
                "@keyframes k { from { a: 1 } } @layer l;\n"
                "@media x { @page { margin: 1in } b{} } a{}")
        live = bg._Nest(bg.GATE_LIVE_ROOT)
        out = bg.css_gate_rules(text, bg.GATE_LIVE_ROOT)
        self.assertEqual(out, " \n \n \n@keyframes k { from { a: 1 } } @layer l;\n"
                              "@media x {  %sb:where(&,& *){}} } %sa:where(&,& *){}}"
                              % (live.open, live.open))
        # the normal gate copies them
        self.assertEqual(ungate(bg.css_gate_rules(text, bg.GATE_NORMAL_ROOT), bg.GATE_NORMAL_ROOT),
                         text)
        sites = bg.Sites({"a.test.css": {"glass": text}}, {})
        self.assertEqual(bg.sites_validate(text), [])
        section = bg.content_live_section(settings(liveControl=True, excluded=["a.test"]), sites)
        self.assertIn("a.test.css", section)
        for word in ("@page", "@property", "@font-face", "@counter-style", "@view-transition",
                     "@font-feature-values"):
            self.assertNotIn(word, section)
        self.assertIn("@keyframes k", section)
        normal = render(sites, liveControl=True)
        self.assertIn("@page :first", normal)

    def test_shadow_branch(self):
        """The normal gate also lets shadow tree elements through (they
        cannot see the root's attributes), the live one does not. In the
        wrapper it is GATE_SHADOW_TOP, never GATE_SHADOW_TREE: "& *" tests
        the wrapper on every ancestor, and GATE_SHADOW_TREE climbs to the
        root from each (a match in depth squared)."""
        normal = bg._Nest(bg.GATE_NORMAL_ROOT)
        self.assertEqual(normal.open, ":where(%s,%s){" % (bg.GATE_NORMAL_ROOT, bg.GATE_SHADOW_TOP))
        for gate in (None, bg.GATE_NORMAL_ROOT):
            nest = bg._Nest(bg.GATE_DARK[gate])
            self.assertNotIn(bg.GATE_SHADOW_TREE, nest.open)
            self.assertTrue(nest.open.endswith("," + bg.GATE_SHADOW_TOP + "){"))
            self.assertEqual(nest.amp, ":where(&,& *)")
        self.assertEqual(normal.plain, ":where(%s, %s *,%s)"
                         % (bg.GATE_NORMAL_ROOT, bg.GATE_NORMAL_ROOT, bg.GATE_SHADOW_TREE))
        live = bg._Nest(bg.GATE_LIVE_ROOT)
        for text in (live.open, live.plain, live.scope_open):
            self.assertNotIn(bg.GATE_SHADOW_TREE, text)
            self.assertNotIn(bg.GATE_SHADOW_TOP, text)
        self.assertEqual(bg.css_gate_rules("a{}", bg.GATE_NORMAL_ROOT),
                         normal.open + "a:where(&,& *){}}")

    def test_nested_rules_untouched(self):
        self.assertEqual(self.gate("p{ & > q{} r{} }"), ":where(C){p:where(&,& *){ & > q{} r{} }}")

    def test_strings_and_comments(self):
        text = 'a[x="}{"]{content:"}"} /* } { */ b{background:url(a}b)}'
        out = self.gate(text)
        self.assertEqual(out, ':where(C){a[x="}{"]:where(&,& *){content:"}"} /* } { */ '
                              'b:where(&,& *){background:url(a}b)}}')
        self.assertEqual(ungate(out, COND), text)

    def test_unbalanced_copied(self):
        # never produced by validated input; kept as is, nothing lost
        for text in ("}a{}", "a{", "a{}}", "@media x{a{}", "b"):
            with self.subTest(text=text):
                self.assertEqual(ungate(self.gate(text), COND), text)

    def test_real_styles(self):
        """Every site style of data/ (and the generic one, scheme-gated):
        only text inserted, braces balanced, still valid."""
        sites = real_sites()
        index = bg._sites_index(sites, True)
        self.assertGreater(len(index.css), 100)
        for key, css in sorted(index.css.items()):
            if bg.sites_validate(css):
                continue  # left out by the build
            for cond in (bg.GATE_NORMAL_ROOT, bg.GATE_LIVE_ROOT) + tuple(bg.GATE_DARK.values()):
                out = bg.css_gate_rules(css, cond)
                self.assertEqual(ungate(out, cond), css, key)
                self.assertEqual(braces(out), braces(css), key)
                self.assertEqual(braces(out)[1], 0, key)
                self.assertEqual(bg.sites_validate(out), [], key)
            for gate in bg.GATE_DARK:
                out = bg._scheme_gated(css, gate)
                self.assertEqual(braces(out), (0, 0), key)
                self.assertEqual(bg.sites_validate(out), [], key)


class SchemeTest(unittest.TestCase):
    """_scheme_gated: every site style block applies as is (or gated) under
    a light theme, and under a dark one only on a page declaring a dark
    version (with liveControl: or measured by the add-on), in one gating
    per branch."""

    def test_shape(self):
        normal, dark = bg._Nest(bg.GATE_NORMAL_ROOT), bg._Nest(bg.GATE_DARK[bg.GATE_NORMAL_ROOT])
        self.assertEqual(bg._scheme_gated("a{}"),
                         "@media not (prefers-color-scheme: dark) {\na{}\n}\n"
                         "@media (prefers-color-scheme: dark) {\n%sa:where(&,& *){}}\n}"
                         % bg._Nest(bg.GATE_DARK[None]).open)
        self.assertEqual(bg._scheme_gated("a{}", bg.GATE_NORMAL_ROOT),
                         "@media not (prefers-color-scheme: dark) {\n%sa:where(&,& *){}}\n}\n"
                         "@media (prefers-color-scheme: dark) {\n%sa:where(&,& *){}}\n}"
                         % (normal.open, dark.open))

    def test_conditions(self):
        tone = "[%s]" % bg.ATTR_TONE
        self.assertEqual(bg.GATE_DARK[None], bg._DARK_PAGE_ROOT)
        self.assertNotIn("data-browserglass", bg.GATE_DARK[None])
        for gate in (bg.GATE_NORMAL_ROOT, bg.GATE_LIVE_ROOT):
            self.assertEqual(bg.GATE_DARK[gate], gate + bg._DARK_PAGE_TONE_WHERE)
            self.assertIn(tone, bg.GATE_DARK[gate])
        for marker in bg._DARK_PAGE_MARKERS:
            self.assertIn(marker, bg._DARK_PAGE_TONE_WHERE)
        # a page naming both schemes but showing its light one is light
        meta = bg._DARK_PAGE_MARKERS[0]
        self.assertIn('meta[name="color-scheme" i][content~="dark" i]', meta)
        self.assertTrue(meta.startswith(":not("))
        self.assertIn('[data-color-mode="light" i]', meta)
        # the shadow branch (unless left out) and the at-rules follow the gate
        for gate in (None, bg.GATE_NORMAL_ROOT):
            nest = bg._Nest(bg.GATE_DARK[gate])
            self.assertIn(bg.GATE_SHADOW_TOP, nest.open)
            self.assertIn(bg.GATE_SHADOW_TREE, nest.plain)
            self.assertTrue(nest.ungated_at_rules)
            nest = bg._Nest(bg.GATE_DARK[gate], False)
            self.assertNotIn(bg.GATE_SHADOW_TREE, nest.open + nest.plain)
            self.assertNotIn(bg.GATE_SHADOW_TOP, nest.open + nest.plain)
            self.assertTrue(nest.ungated_at_rules)
        for shadow in (True, False):
            nest = bg._Nest(bg.GATE_DARK[bg.GATE_LIVE_ROOT], shadow)
            self.assertNotIn(bg.GATE_SHADOW_TREE, nest.open + nest.plain)
            self.assertNotIn(bg.GATE_SHADOW_TOP, nest.open + nest.plain)
            self.assertFalse(nest.ungated_at_rules)

    def test_generic_not_in_shadow_trees(self):
        """Under a dark theme the generic style never reaches a shadow tree
        (as in v1.0: a light-only page's web components keep their own
        backgrounds), with or without liveControl; a dedicated style keeps
        the shadow branch, as before the scheme gating. Under a light theme
        both follow the gate."""
        sites = bg.sites_load(str(FIXTURES / "sites"))
        for gate in (None, bg.GATE_NORMAL_ROOT):
            with self.subTest(gate=gate):
                css = bg.sites_build_css(sites, gate=gate)
                found = blocks(css)
                ends = [start for _, _, start in found[1:]] + [len(css)]
                for (comment, _, start), end in zip(found, ends):
                    block = css[start:end]
                    dark = block[block.index("@media (prefers-color-scheme: dark)"):]
                    if comment == bg.SITES_GENERIC_COMMENT[3:-3]:
                        self.assertNotIn(bg.GATE_SHADOW_TREE, dark)
                        self.assertNotIn(bg.GATE_SHADOW_TOP, dark)
                        self.assertIn(bg._Nest(bg.GATE_DARK[gate], False).open, dark)
                    elif ":where(&,& *)" in dark:
                        self.assertIn(bg._Nest(bg.GATE_DARK[gate]).open, dark, comment)
                self.assertIn(bg.SITES_GENERIC_COMMENT, css)

    def test_root_rules_kept(self):
        """The gating matches the root itself: ":root" and "html" rules of
        a site style still apply under a dark theme (nesting would make
        them descendants of the root)."""
        out = bg._scheme_gated(":root{--a:1} html{b:c}")
        dark = out[out.index("@media (prefers-color-scheme: dark)"):]
        self.assertIn(":root:where(&,& *){--a:1}", dark)
        self.assertIn("html:where(&,& *){b:c}", dark)

    def test_every_block(self):
        """Every block of the build, dedicated, dash, mapped and generic
        alike, is scheme-gated, with or without liveControl, and a light
        theme keeps the plain (or live-gated) style."""
        sites = bg.sites_load(str(FIXTURES / "sites"))
        for gate in (None, bg.GATE_NORMAL_ROOT):
            css = bg.sites_build_css(sites, gate=gate)
            found = blocks(css)
            self.assertGreater(len(found), 3)
            rows = bg._sites_blocks(sites)
            self.assertEqual(len(rows), len(found))
            for comment, tail, body in rows:
                with self.subTest(gate=gate, block=comment):
                    want = bg._sites_block_text(comment, "https?://" + tail, body, gate)
                    self.assertIn(want, css)
                    self.assertIn('") {\n@media not (prefers-color-scheme: dark) {\n', want)
                    shadow = comment != bg.SITES_GENERIC_COMMENT
                    # the generic style, live-gated, skips ATTR_OWN
                    keep = not shadow and gate is not None
                    light = bg.css_gate_rules(body, gate, keep=keep) if gate else body
                    self.assertIn("{\n" + light + "\n}\n@media (prefers-color-scheme: dark) {\n"
                                  + bg.css_gate_rules(body, bg.GATE_DARK[gate], shadow, keep) + "\n}\n}",
                                  want)

    def test_one_envelope(self):
        """Live gating and scheme gating share one wrapper per run: no
        wrapper inside another, in the normal blocks and the live section."""
        sites = bg.sites_load(str(FIXTURES / "sites"))
        css = render(sites, liveControl=True, excluded=["a.test", "goo.test"])
        opens = [bg._Nest(c, shadow).open for c in (bg.GATE_NORMAL_ROOT, bg.GATE_LIVE_ROOT)
                 + tuple(bg.GATE_DARK.values()) for shadow in (True, False)]
        for opener in opens:
            at = css.find(opener)
            while at >= 0:
                close = bg._gate_block_end(css, at + len(opener) - 1, len(css))
                inner = css[at + len(opener):close]
                for other in opens:
                    self.assertNotIn(other, inner)
                at = css.find(opener, close)
        live = bg.content_live_section(settings(liveControl=True, excluded=["a.test"]), sites)
        self.assertIn(bg._Nest(bg.GATE_DARK[bg.GATE_LIVE_ROOT]).open, live)
        self.assertNotIn(bg._Nest(bg.GATE_DARK[bg.GATE_NORMAL_ROOT]).open, live)
        self.assertNotIn(bg.GATE_DARK[None] + ",", live)


class ToneTest(unittest.TestCase):
    """liveControl only: a page carrying the add-on's tone counts as one with
    a dark version, and gets the glass of its own tone."""

    def rgb(self, surfaces=None):
        surfaces = surfaces or {}
        return {mode: "%d, %d, %d" % bg.surface_rgb(surfaces.get(mode), mode) for mode in bg.MODES}

    def test_off_has_no_tone(self):
        sites = bg.sites_load(str(FIXTURES / "sites"))
        css = render(sites, liveControl=False, excluded=["a.test"])
        self.assertNotIn(bg.ATTR_TONE, css)
        self.assertIn(bg._CONTENT_GENERIC, css)

    def test_on_tone(self):
        sites = bg.sites_load(str(FIXTURES / "sites"))
        surfaces = {"dark": "#101418", "light": "#f4f0e8"}
        settings_ = settings(liveControl=True, excluded=["a.test"])
        css = bg._render_content(settings_, 0.8, sites, False, surfaces)
        normal = bg._Nest(bg.GATE_NORMAL_ROOT)
        self.assertIn("    %s,\n    %s > body" % (bg._DARK_PAGE_TONE_ROOT, bg._DARK_PAGE_TONE_ROOT),
                      bg._CONTENT_GENERIC_TONE)
        # never on the body kept for a read of its own colour (ATTR_OWN)
        self.assertIn(bg.css_gate_rules(bg._CONTENT_GENERIC_TONE, bg.GATE_NORMAL_ROOT, keep=True), css)
        self.assertIn(bg.css_gate_rules(bg._CONTENT_GENERIC_TONE, bg.GATE_LIVE_ROOT, keep=True), css)
        self.assertIn("body:where(&,& *)%s { background: transparent !important; }" % bg._GATE_KEEP, css)
        tint = bg._content_block("https?://.*", bg._CONTENT_TONE.format(
            a="0.88", bar="0.8", **self.rgb(surfaces)), bg.GATE_NORMAL_ROOT)
        self.assertEqual(css.count(tint), 1)
        # after the site styles, before the live section
        self.assertLess(css.rindex("/* a.test.css */", 0, css.index(bg._CONTENT_LIVE_COMMENT)),
                        css.index(tint))
        self.assertLess(css.index(tint), css.index(bg._CONTENT_LIVE_COMMENT))
        self.assertIn(normal.open + 'html:root[%s="light"]:not(%s):where(&,& *) {\n'
                      "      background: rgba(244, 240, 232, 0.88) !important;\n"
                      "      --browserglass-bar: rgba(244, 240, 232, 0.8);"
                      % (bg.ATTR_TONE, bg._DARK_PAGE_WHERE), css)
        self.assertIn(normal.open + 'html:root[%s="dark"]:where(&,& *) {\n'
                      "      background: rgba(16, 20, 24, 0.88) !important;" % bg.ATTR_TONE, css)
        light = tint.index('[%s="light"]' % bg.ATTR_TONE)
        self.assertLess(tint.rindex("@media (prefers-color-scheme: dark)", 0, light), light)
        dark = tint.index('[%s="dark"]' % bg.ATTR_TONE)
        self.assertLess(tint.rindex("@media not (prefers-color-scheme: dark)", 0, dark), dark)
        self.assertEqual(bg.sites_validate(css), [])

    def test_tone_without_sites(self):
        css = bg.content_css(settings(liveControl=True), 0.8, sites=None)
        self.assertIn('html:root[%s="light"]' % bg.ATTR_TONE, css)
        css = bg.content_css(settings(liveControl=False), 0.8, sites=None)
        self.assertNotIn(bg.ATTR_TONE, css)

    def test_specificity(self):
        """The tint beats the "html" and ":root" backgrounds of the site
        styles: (0,2,1) against (0,0,1) and (0,1,0), the gate adding none,
        nor the :not(:where(...)) of the pages declaring a dark version."""
        tone = bg._CONTENT_TONE.format(a="1", bar="1", light="1, 1, 1", dark="0, 0, 0")
        self.assertIn('    html:root[%s="light"]:not(%s) {' % (bg.ATTR_TONE, bg._DARK_PAGE_WHERE), tone)
        self.assertTrue(bg._DARK_PAGE_WHERE.startswith(":where("))
        self.assertIn('    html:root[%s="dark"] {' % bg.ATTR_TONE, tone)


class DarkPagesTest(unittest.TestCase):
    """darkPages (with liveControl): under a dark theme, the root of a page
    without a dark version carries the colours the add-on darkens it with,
    and the elements it marks as the page's canvas are glass."""

    def test_block(self):
        surfaces = {"dark": "#101418", "light": "#f4f0e8"}
        css = bg._render_content(settings(liveControl=True), 0.8, None, False, surfaces)
        normal = bg._Nest(bg.GATE_NORMAL_ROOT)
        block = bg._content_block("https?://.*", bg._CONTENT_DARKEN.format(
            dark_hex="#101418", light_hex="#f4f0e8"), bg.GATE_NORMAL_ROOT)
        self.assertEqual(css.count(block), 1)
        self.assertIn(normal.open + "html:root:not(%s):where(&,& *) {\n"
                      "      --browserglass-darken-bg: #101418;\n"
                      "      --browserglass-darken-fg: #f4f0e8;" % bg._DARK_PAGE_WHERE, css)
        # under a dark theme only, after the tone tint
        self.assertLess(block.index("@media (prefers-color-scheme: dark)"), block.index("--browserglass"))
        self.assertNotIn("not (prefers-color-scheme: dark)", block)
        self.assertLess(css.index('[%s="light"]' % bg.ATTR_TONE), css.index(block))
        self.assertEqual(bg.sites_validate(css), [])

    def test_off(self):
        for over in ({"liveControl": True, "darkPages": False},
                     {"liveControl": False, "darkPages": True}):
            css = bg.content_css(settings(**over), 0.8, sites=None)
            self.assertNotIn("--browserglass-darken", css, over)


class LayersTest(unittest.TestCase):
    """With liveControl, the layers the add-on marks: the page's own
    background is glass, a navigation bar the DMS surface at
    NAV_BAR_OPACITY, blurred (by the page's tone, else the theme), over the
    generic style's transparency (which reaches (1,1,2) with ids)."""

    def test_block(self):
        css = bg._render_content(settings(liveControl=True, darkPages=False), 0.8, None, False, None)
        rgb = {mode: "%d, %d, %d" % bg.surface_rgb(None, mode) for mode in bg.MODES}
        block = bg._content_block("https?://.*", bg._CONTENT_LAYERS.format(
            nav="0.65", **rgb) + bg._CONTENT_TINT.format(a="0.8"), bg.GATE_NORMAL_ROOT)
        self.assertEqual(css.count(block), 1)
        bar = "[%s]:not(#browserglass-a):not(#browserglass-b)" % bg.ATTR_BAR
        self.assertIn("[%s]:where(&,& *) { background-color: transparent !important; }"
                      % bg.ATTR_CANVAS, block)
        self.assertEqual((bg.NAV_BAR_OPACITY, bg.NAV_BAR_BLUR), (0.65, "blur(20px) saturate(1.5) url(\"#browserglass-veil\")"))
        # the blur on its ::before, never on the bar (no containing block
        # of its fixed parts, no Backdrop Root of a layer in it)
        self.assertIn("%s:where(&,& *) {\n    background: var(--browserglass-nav) !important;\n"
                      "    backdrop-filter: none !important;\n    isolation: isolate !important;" % bar, block)
        self.assertIn("%s:where(&,& *)::before { content: \"\" !important; position: absolute !important;"
                      " inset: 0 !important; z-index: -1 !important;" % bar, block)
        self.assertIn("backdrop-filter: blur(20px) saturate(1.5) url(\"#browserglass-veil\") !important; }", block)
        self.assertIn(":root:where(&,& *) { --browserglass-nav: rgba(%s, 0.65); }" % rgb["dark"], block)
        self.assertIn(":root:where(&,& *) { --browserglass-nav: rgba(%s, 0.65); }" % rgb["light"], block)
        # the bar's colour is a custom property of the root: it reaches the
        # bars of shadow trees, where html:root[tone] cannot match
        # (the light one never on a page declaring its dark version: the
        # dark glass stays there, its bars with it)
        for tone in bg.MODES:
            where = ":not(%s)" % bg._DARK_PAGE_WHERE if tone == "light" else ""
            self.assertIn('html:root[%s="%s"]%s:where(&,& *) { --browserglass-nav: rgba(%s, 0.65); }'
                          % (bg.ATTR_TONE, tone, where, rgb[tone]), block)
        # the tone wins over the theme: last
        self.assertLess(block.index("not (prefers-color-scheme: dark)"), block.index(bg.ATTR_TONE))
        self.assertLess(css.index('[%s="light"]' % bg.ATTR_TONE), css.index(block))
        self.assertEqual(bg.sites_validate(css), [])

    def test_off(self):
        css = bg.content_css(settings(liveControl=False), 0.8, sites=None)
        self.assertNotIn(bg.ATTR_BAR, css)
        self.assertNotIn(bg.ATTR_CANVAS, css)


class ContentTest(unittest.TestCase):

    def test_off_is_v1(self):
        sites = real_sites()
        for excluded in ((), EXCLUDED):
            css = render(sites, liveControl=False, excluded=list(excluded))
            self.assertNotIn("data-browserglass", css)
            self.assertNotIn(bg._CONTENT_LIVE_COMMENT, css)
            # gated on the colour scheme only (the site styles under a dark theme)
            self.assertNotIn(":where(&,& *)", ungate_scheme(css, None))

    def test_on_is_off_gated(self):
        """With liveControl, the file minus the live section is the
        liveControl-off file with what the gating inserted, the tone
        condition of the generic rule, the tone tint, the page layers and
        the dark pages block (darkPages)."""
        sites = real_sites()
        rgb = {mode: "%d, %d, %d" % bg.surface_rgb(None, mode) for mode in bg.MODES}
        tint = ('\n@-moz-document regexp("https?://.*") {\n%s}\n'
                % bg._CONTENT_TONE.format(a="0.88", bar="0.8", **rgb))
        bars = ('\n@-moz-document regexp("https?://.*") {\n%s}\n'
                % (bg._CONTENT_LAYERS.format(nav="0.65", **rgb) + bg._CONTENT_TINT.format(a="0.8")))
        hexes = {mode + "_hex": "#%02x%02x%02x" % bg.surface_rgb(None, mode) for mode in bg.MODES}
        darken = ('\n@-moz-document regexp("https?://.*") {\n%s}\n'
                  % bg._CONTENT_DARKEN.format(**hexes))
        for excluded in ((), EXCLUDED):
            for reader in (True, False):
                over = {"excluded": list(excluded), "readerOpaque": reader}
                off = render(sites, liveControl=False, **over)
                on = render(sites, liveControl=True, **over)
                live = bg.content_live_section(settings(liveControl=True, **over), sites)
                self.assertEqual(bool(live), bool(excluded))
                if live:
                    self.assertEqual(on.count(live), 1)
                    on = on.replace("\n" + live, "")
                plain = ungate_scheme(on, bg.GATE_NORMAL_ROOT)
                self.assertEqual(plain.count(tint), 1)
                self.assertEqual(plain.count(darken), 1)
                self.assertEqual(plain.count(bars), 1)
                self.assertEqual(plain.count(bg._CONTENT_GENERIC_TONE), 1)
                plain = plain.replace(tint, "").replace(bars, "").replace(darken, "").replace(bg._CONTENT_GENERIC_TONE, bg._CONTENT_GENERIC)
                self.assertEqual(plain, ungate_scheme(off, None))
                self.assertEqual(bg.sites_validate(on), [])

    def test_special_pages_not_gated(self):
        css = bg.content_css(settings(liveControl=True, readerOpaque=False, excluded=["x.test"]),
                             0.8, sites=None)
        self.assertIn(bg._CONTENT_READER_GLASS, css)
        self.assertIn(bg._CONTENT_NEWTAB_GLASS, css)
        css = bg.content_css(settings(liveControl=True, excluded=["x.test"]), 0.8, sites=None)
        self.assertTrue(css.endswith("\n" + bg._CONTENT_PDF_OPAQUE))
        # the live section comes right before the PDF rule
        live = bg.content_live_section(settings(liveControl=True, excluded=["x.test"]), None)
        self.assertTrue(css.endswith("\n" + live + "\n" + bg._CONTENT_PDF_OPAQUE))

    def test_bar_variable_gated(self):
        sites = bg.sites_load(str(FIXTURES / "sites"))
        css = render(sites, liveControl=True)
        self.assertIn(bg._Nest(bg.GATE_NORMAL_ROOT).open + ':root:where(&,& *) { --browserglass-bar:',
                      css)

    def test_growth(self):
        """The live gating grows what it gates by at most MAX_GROWTH: the
        normal blocks (the file without its live section) against the
        liveControl-off file (scheme-gated too: about +17 %), and the live
        section against its ungated text, by at most MAX_GROWTH_LIVE (its
        dark branch has the longer GATE_DARK[GATE_LIVE_ROOT] in each
        wrapper, and the generic style it repeats the exemption of
        ATTR_OWN on each selector: about +56 % with google.com alone, the
        style with the most runs). The live section itself repeats the blocks of the excluded
        domains (EXCLUDED_HEAVY: the largest), so it is not counted in the
        first ratio; the whole file is held to MAX_GROWTH for typical
        exclusions only."""
        sites = real_sites()
        for excluded in ((), EXCLUDED, ("google.com",), EXCLUDED_HEAVY):
            with self.subTest(excluded=excluded):
                off = render(sites, liveControl=False, excluded=list(excluded))
                on = render(sites, liveControl=True, excluded=list(excluded))
                live = bg.content_live_section(settings(liveControl=True, excluded=list(excluded)),
                                               sites)
                normal = on.replace("\n" + live, "") if live else on
                self.assertLessEqual(len(normal) / len(off) - 1, MAX_GROWTH)
                if excluded in ((), EXCLUDED):
                    self.assertLessEqual(len(on) / len(off) - 1, MAX_GROWTH)
                else:
                    # the live section grows with the excluded styles:
                    # about +24 % with google.com alone, +31 % for EXCLUDED_HEAVY
                    self.assertLessEqual(len(on) / len(off) - 1, 0.60)
                if live:
                    raw = ungate_scheme(live, bg.GATE_LIVE_ROOT)
                    self.assertLessEqual(len(live) / len(raw) - 1, MAX_GROWTH_LIVE)

    def test_scheme_size(self):
        """The scheme gating (_scheme_gated) writes each site style twice,
        once per colour scheme, the dark copy gated: the file is at most
        MAX_SCHEME_RATIO times the one with a single copy (the live gating
        alone; measured: x2.51 with liveControl off, x2.13 on)."""
        sites = real_sites()
        single = bg._scheme_gated

        def one_copy(css, gate=None, shadow=True, keep=False):
            return bg.css_gate_rules(css, gate, keep=keep) if gate else css

        for live in (False, True):
            with self.subTest(live=live):
                both = render(sites, liveControl=live, excluded=list(EXCLUDED))
                bg._scheme_gated = one_copy
                try:
                    one = render(sites, liveControl=live, excluded=list(EXCLUDED))
                finally:
                    bg._scheme_gated = single
                self.assertGreater(len(both) / len(one), 2)
                self.assertLessEqual(len(both) / len(one), MAX_SCHEME_RATIO)


class LiveSectionTest(unittest.TestCase):

    def setUp(self):
        self.sites = bg.sites_load(str(FIXTURES / "sites"))

    def live(self, *excluded):
        return bg.content_live_section(settings(liveControl=True, excluded=list(excluded)),
                                       self.sites)

    def kept(self, *excluded):
        return [comment for comment, _, _ in blocks(self.live(*excluded))][1:]

    def test_empty(self):
        self.assertEqual(self.live(), "")
        self.assertEqual(self.live(""), "")

    def test_shape(self):
        live = self.live("a.test")
        self.assertTrue(live.startswith(bg._CONTENT_LIVE_COMMENT + "\n@-moz-document regexp("))
        look = bg.inclusion_lookahead(["a.test"])
        for comment, _, start in blocks(live):
            with self.subTest(block=comment):
                self.assertTrue(live.startswith('regexp("https?://' + look, live.index("regexp(", start)))
        self.assertNotIn(bg.GATE_NORMAL_ROOT, live)
        self.assertEqual(bg.sites_validate(live), [])
        self.assertEqual(braces(live), (0, 0))

    def test_inclusion_lookahead(self):
        self.assertEqual(bg.inclusion_lookahead([]), "")
        rx = re.compile(bg.css_unescape("https?://" + bg.inclusion_lookahead(["a.test", "b.test"]) + ".*"))
        for url in ("https://a.test/", "http://a.test:8080/x", "https://www.a.test/", "https://x.y.b.test",
                    "https://a.test"):
            self.assertTrue(rx.fullmatch(url), url)
        for url in ("https://xa.test/", "https://a.test.evil/", "https://c.test/a.test/",
                    "https://evil/?a.test"):
            self.assertFalse(rx.fullmatch(url), url)

    def test_blocks_kept(self):
        self.assertEqual(self.kept("a.test"), ["a.test.css", "gist.a.test.css"])
        self.assertEqual(self.kept("sub.a.test"), ["a.test.css"])
        self.assertEqual(self.kept("b.test"), ["+b.test.css"])
        self.assertEqual(self.kept("goo.test"),
                         ["-goo.test.css", "Other sites: generic style (example.com.css)"])
        self.assertEqual(self.kept("generic-host.test"),
                         ["example.com.css (mapping)", "Other sites: generic style (example.com.css)"])
        self.assertEqual(self.kept("nothing.test"), ["Other sites: generic style (example.com.css)"])

    def test_dash_hosts(self):
        """A dash style whose base holds a dot matches subdomains of an
        excluded domain: it comes back too."""
        css = self.sites.styles["-goo.test.css"]
        sites = bg.Sites({"-sub.goo.test.css": css, "-goo.test.css": css}, {})
        live = bg.content_live_section(settings(liveControl=True, excluded=["goo.test"]), sites)
        self.assertEqual([c for c, _, _ in blocks(live)][1:], ["-goo.test.css", "-sub.goo.test.css"])
        self.assertEqual(matching(live, "https://www.sub.goo.test/")[1:], ["-sub.goo.test.css"])
        live = bg.content_live_section(settings(liveControl=True, excluded=["google.com"]), real_sites())
        kept = [c for c, _, _ in blocks(live)]
        for key in ("-google.com.css", "-translate.google.com.css", "-images.google.com.css"):
            self.assertIn(key, kept)
        self.assertEqual(matching(live, "https://translate.google.com/")[1:],
                         ["-translate.google.com.css"])

    def test_disabled_left_out(self):
        live = bg.content_live_section(
            settings(liveControl=True, excluded=["a.test"], disabledStyles=["gist.a.test"]), self.sites)
        self.assertEqual([c for c, _, _ in blocks(live)][1:], ["a.test.css"])

    def test_may_match(self):
        """The cheap test of _sites_block_rows never leaves out a block whose
        regexp matches a probe host (fixture and data/)."""
        for sites in (self.sites, real_sites()):
            index = bg._sites_index(sites, True)
            known = sorted(set(index.suffix) | {h for _, hosts in index.mapped for h in hosts}
                           | {b + ".test" for b in index.dash})
            hosts = bg._live_hosts(index, known + ["nothing.test"])
            for comment, tail, _, may_match in bg._sites_block_rows(sites):
                rx = re.compile(bg.css_unescape("https?://" + tail))
                for host in hosts:
                    if rx.fullmatch("https://%s/" % host):
                        self.assertTrue(may_match(host), (comment, host))

    def test_matching(self):
        live = self.live("a.test")
        generic = bg._CONTENT_LIVE_COMMENT[3:-3]
        self.assertEqual(matching(live, "https://a.test/"), [generic, "a.test.css"])
        self.assertEqual(matching(live, "http://www.a.test:8080/x"), [generic, "a.test.css"])
        self.assertEqual(matching(live, "https://gist.a.test/"), [generic, "gist.a.test.css"])
        for url in ("https://b.test/", "https://xa.test/", "https://a.test.evil/",
                    "https://a-mirror.test/"):
            self.assertEqual(matching(live, url), [], url)


if __name__ == "__main__":
    unittest.main()

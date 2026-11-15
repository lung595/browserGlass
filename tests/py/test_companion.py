"""companion: the add-on sources in extension/, the xpi built from them, the
native messaging manifest and the host wrapper (section companion).

Run: python3 -B -m unittest discover -s tests/py -v
"""

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from fakehome import REPO, load_script

bg = load_script()
EXT = REPO / bg.EXTENSION_DIR


def read(name):
    return (EXT / name).read_text(encoding="utf-8")


def strip_comments(js):
    return "\n".join(line for line in js.splitlines() if not line.lstrip().startswith("//"))


class ExtensionSourcesTest(unittest.TestCase):

    def setUp(self):
        self.manifest = json.loads(read("manifest.json"))

    def test_version_follows_plugin(self):
        # The add-on version moves with plugin.json, at release time (the
        # hello message then sends the new version).
        plugin = json.loads((REPO / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(self.manifest["version"], plugin["version"])

    def test_manifest(self):
        gecko = self.manifest["browser_specific_settings"]["gecko"]
        self.assertEqual(gecko["id"], bg.COMPANION_ID)
        # CSS nesting, which the gated stylesheets need, came with Firefox 117.
        self.assertEqual(gecko["strict_min_version"], "117.0")
        # AMO asks for it: the add-on talks only to the local native host.
        self.assertEqual(gecko["data_collection_permissions"], {"required": ["none"]})
        self.assertEqual(self.manifest["manifest_version"], 2)
        self.assertEqual(self.manifest["permissions"],
                         ["nativeMessaging", "tabs", "storage", "*://*/*"])
        # Never in a private window, whatever about:addons says.
        self.assertEqual(self.manifest["incognito"], "not_allowed")
        scripts = self.manifest["content_scripts"]
        self.assertEqual(len(scripts), 1)
        # Dark Reader first: content.js uses its global
        self.assertEqual(scripts[0]["js"], ["vendor/darkreader.js", "content.js"])
        self.assertEqual(scripts[0]["run_at"], "document_start")
        self.assertNotIn("all_frames", scripts[0])  # main document only (v1.1)
        self.assertEqual(self.manifest["background"]["scripts"], ["background.js"])
        self.assertEqual(sorted(p.name for p in EXT.iterdir()),
                         ["background.js", "content.js", "manifest.json", "vendor"])
        self.assertEqual(sorted(p.name for p in (EXT / "vendor").iterdir()),
                         ["darkreader-LICENSE.txt", "darkreader.js"])

    def test_vendored_dark_reader(self):
        # The npm build of Dark Reader, unmodified, with its MIT licence.
        js = read("vendor/darkreader.js")
        self.assertTrue(js.startswith("/**\n * Dark Reader v4.9.135\n * https://darkreader.org/\n"))
        self.assertIn("exports.enable = enable;", js)
        self.assertIn("exports.setFetchMethod = setFetchMethod;", js)
        lic = read("vendor/darkreader-LICENSE.txt")
        self.assertTrue(lic.startswith("MIT License"))
        self.assertIn("Dark Reader Ltd.", lic)

    def test_content_watches_only_the_root_attributes(self):
        # Fix F: no subtree observer (it would wake on every DOM insertion);
        # the attributes of <html>, and the document's own children (a
        # replaced <html>).
        js = strip_comments(read("content.js"))
        self.assertNotIn("subtree", js)
        observes = re.findall(r"\.observe\(([^;]*)\);", js)
        self.assertEqual(sorted(observes), sorted([
            "document, {childList: true}",
            # the body's size (not its DOM), while the tone is unsettled
            "document.body",
            "root, {attributes: true}",
            # the layers: the size of the document, the body, its children
            # and the marked elements; the body's children (not its subtree)
            "document.documentElement",
            "document.body",
            "el",
            "el",
            "el",
            "document.body, {childList: true}",
        ]))
        self.assertIn('const LIVE = "%s";' % bg.ATTR_LIVE, js)
        self.assertIn('const OFF = "%s";' % bg.ATTR_OFF, js)

    def test_content_measures_the_tone(self):
        # the tone of the page, from the colour of its text, in
        # ATTR_TONE; measured again on a change of the root attributes that
        # are not ours (so setting ours never loops), of the colour scheme,
        # and on load. Nothing is sent: no runtime message from here.
        js = strip_comments(read("content.js"))
        self.assertIn('const TONE = "%s";' % bg.ATTR_TONE, js)
        self.assertIn('const OWN = "data-browserglass-";', js)
        for name in (bg.ATTR_LIVE, bg.ATTR_OFF, bg.ATTR_TONE):
            self.assertTrue(name.startswith("data-browserglass-"))
        measure = js[js.index("function measure()"):js.index("function update()")]
        self.assertIn("document.body || document.documentElement", measure)
        self.assertIn("getComputedStyle(el).color", measure)
        self.assertIn('"dark" : "light"', measure)
        self.assertNotIn("setAttribute", measure)
        # computed colours keep the page's colour space (oklch() for
        # Tailwind v4, color() for wide gamut)
        lum = js[js.index("function luminance("):js.index("function measure()")]
        for space in ("rgb", "oklch", "oklab", "lab", "lch", "srgb", "display-p3", "xyz"):
            self.assertIn('case "%s":' % space, lum)
        self.assertIn('m[1] === "color"', lum)
        # the visible text votes (not the body's colour alone: YouTube),
        # the body's colour only without visible text
        self.assertIn("createTreeWalker(document.body, NodeFilter.SHOW_TEXT)", measure)
        self.assertIn("i < SAMPLE_NODES", measure)
        self.assertIn("checkVisibility(", measure)
        self.assertIn("isLight(getComputedStyle(p).color)", measure)
        self.assertIn("sampled ? dark > light : isLight(getComputedStyle(el).color)", measure)
        # a page still rendering: each resize of the body measures again,
        # until the text settles the tone or RESIZE_MEASURES
        upd = js[js.index("const sizes = new ResizeObserver"):js.index("function paint()")]
        self.assertIn("++resizeMeasures > RESIZE_MEASURES", upd)
        self.assertIn("sampled >= ENOUGH_TEXT || resizeMeasures >= RESIZE_MEASURES", upd)
        self.assertIn("sizes.observe(document.body)", upd)
        observer = js[js.index("new MutationObserver"):js.index("function watch()")]
        self.assertIn('r.attributeName !== "style" && !r.attributeName.startsWith(OWN)', observer)
        self.assertIn("measure()", observer)
        # the tone of the text shown: measured again once set (the site
        # styles may recolour the text), at most twice
        paint_ = js[js.index("function paint()"):js.index("function apply(")]
        self.assertIn("pass < 2", paint_)
        self.assertLess(paint_.index("setAttribute(TONE"), paint_.index("measure()"))
        self.assertIn('matchMedia("(prefers-color-scheme: dark)").addEventListener("change", update)',
                      js)
        self.assertIn('addEventListener("DOMContentLoaded", update)', js)
        self.assertIn('addEventListener("load", update)', js)
        self.assertNotIn("sendMessage", js)
        self.assertNotIn("setTimeout", js)
        self.assertNotIn("setInterval", js)
        # ATTR_TONE only once the list is known, as LIVE.
        paint = js[js.index("function paint()"):js.index("function apply(")]
        self.assertLess(paint.index("off === null"), paint.index("setAttribute(TONE"))
        self.assertEqual(js.count("setAttribute(TONE"), 1)

    def test_content_marks_page_layers(self):
        # navigation bars along a window edge get ATTR_BAR, the page's own
        # background ATTR_CANVAS (_CONTENT_LAYERS), looked for again as the
        # page changes, without a subtree observer nor a timer
        js = strip_comments(read("content.js"))
        self.assertIn('const BAR = "%s";' % bg.ATTR_BAR, js)
        self.assertTrue(bg.ATTR_BAR.startswith("data-browserglass-"))
        self.assertIn("[" + bg.ATTR_BAR + "]", bg._CONTENT_LAYERS)
        self.assertIn("[" + bg.ATTR_CANVAS + "]", bg._CONTENT_LAYERS)
        bars = js[js.index("function markBars()"):js.index("let layerFrame")]
        self.assertIn("off !== false", bars)
        # fixed or sticky, or in the flow of a page that does not scroll (an
        # app shell), the outermost one then
        self.assertIn('position === "fixed" || position === "sticky"', bars)
        self.assertIn("scroller.scrollHeight <= scroller.clientHeight + 1", bars)
        self.assertIn("(pinned(el) || (shell && inFlow(el))) && along(el)", bars)
        # headers and bottom bars, sidebars, on all four edges
        self.assertIn("r.top <= EDGE || r.bottom >= h - EDGE", bars)
        self.assertIn("r.left <= EDGE || r.right >= w - EDGE", bars)
        self.assertIn("[[x, EDGE], [x, h - EDGE], [EDGE, y], [w - EDGE, y]]", bars)
        self.assertIn("removeAttribute(BAR)", bars)
        self.assertIn("mark(found, BAR)", bars)
        self.assertNotIn("backgroundColor", bars)
        mark = js[js.index("function markCanvas()"):js.index("function markBars()")]
        self.assertIn("alpha(getComputedStyle(el).backgroundColor) >= SOLID", mark)
        self.assertIn("const SOLID = 0.99;", js)
        watch = js[js.index("let layerFrame"):js.index("function apply(")]
        self.assertIn("requestAnimationFrame(", watch)
        self.assertIn("for (const el of document.body.children)", watch)
        self.assertIn("bodyKids.observe(document.body, {childList: true})", watch)
        self.assertIn("const SETTLE_MS = [100, 500, 1500, 3000];", watch)
        for line in ('for (const type of ["scroll", "transitionend"])',
                     'for (const type of ["scrollend", "resize", "load"])',
                     'for (const type of ["click", "submit"])',
                     'for (const type of ["popstate", "hashchange"])'):
            self.assertIn(line, js)
        for fn in ("function update()", "function apply("):
            body = js[js.index(fn):]
            body = body[:body.index("\n}")]
            self.assertIn("watchLayers();", body)
            self.assertIn("markBars();", body)

    def test_content_darkens_light_pages(self):
        # darkPages: the glass styles hand the colours over on the root
        # (_CONTENT_DARKEN), the add-on darkens a light page with them,
        # stickily, and marks its large background elements (ATTR_CANVAS).
        js = strip_comments(read("content.js"))
        self.assertIn('const CANVAS = "%s";' % bg.ATTR_CANVAS, js)
        self.assertTrue(bg.ATTR_CANVAS.startswith("data-browserglass-"))
        for var in ("--browserglass-darken-bg", "--browserglass-darken-fg"):
            self.assertIn('"%s"' % var, js)
            self.assertIn(var + ":", bg._CONTENT_DARKEN)
        self.assertIn("[" + bg.ATTR_CANVAS + "]", bg._CONTENT_LAYERS)
        theme = js[js.index("function darkTheme()"):js.index("function darken()")]
        # never before the list is known, nor on an excluded page, nor
        # unless the helper says so: the variables alone (which a page can
        # set itself) never darken
        self.assertIn("off !== false", theme)
        self.assertIn("|| !helperDark ||", theme)
        self.assertIn("let helperDark = false;", js)
        apply_ = js[js.index("function apply("):js.index("function load()")]
        self.assertIn("helperDark = dark === true;", apply_)
        self.assertLess(apply_.index("helperDark ="), apply_.index("darken()"))
        load = js[js.index("function load()"):js.index("let watched")]
        self.assertIn('browser.storage.local.get(["excluded", "darken"])', load)
        self.assertIn("apply(s.excluded, s.darken)", load)
        self.assertIn("apply(msg.domains, msg.darken)", js)
        self.assertIn('typeof DarkReader === "undefined"', theme)
        self.assertIn("darkSchemeBackgroundColor: bg, darkSchemeTextColor: fg", theme)
        # a page can set the colours itself: never under a light theme
        self.assertIn('!window.matchMedia("(prefers-color-scheme: dark)").matches', theme)
        darken = js[js.index("function darken()"):js.index("const GRID")]
        self.assertIn("darkened && !theme", darken)
        # the darkening stopped by the helper takes the page's own dark
        # theme marks back too
        self.assertIn("native && (off !== false || !helperDark ||", darken)
        self.assertIn('tone === "light"', darken)
        self.assertIn('sampled >= ENOUGH_TEXT || document.readyState === "complete"', darken)
        # the add-on's fetch, which the page can read through Dark Reader's
        # copies: no credentials or referrer, stylesheets only
        self.assertIn("DarkReader.setFetchMethod(fetchStylesheet)", darken)
        self.assertNotIn("setFetchMethod(fetch)", js)
        self.assertEqual(js.count("fetch("), 1)
        fetcher = js[js.index("function fetchStylesheet("):]
        fetcher = fetcher[:fetcher.index("\n}")]
        for opt in ('credentials: "omit"', 'cache: "force-cache"',
                    'referrerPolicy: "no-referrer"',
                    "!r.ok", r"/^text\/css\b/i", 'r.headers.get("Content-Type")', "throw "):
            self.assertIn(opt, fetcher)
        self.assertEqual(js.count("DarkReader.enable("), 1)
        self.assertIn("DarkReader.disable()", darken)
        self.assertIn("removeAttribute(CANVAS)", darken)
        # a darkened page shows light text: tone "dark", not measured
        measure = js[js.index("function measure()"):js.index("function update()")]
        self.assertLess(measure.index("if (darkened)"), measure.index("readyState"))
        mark = js[js.index("function markCanvas()"):js.index("function markBars()")]
        # the lowest opaque large layer once the root and body are clear;
        # every large non-fixed one on a darkened page
        self.assertIn("off !== false", mark)
        self.assertIn("clear(root) && clear(document.body)", mark)
        self.assertIn("stack.length - 1", mark)
        self.assertIn("if (!darkened)", mark)
        self.assertIn('position !== "fixed"', mark)
        self.assertIn("elementsFromPoint(", mark)
        self.assertIn("new Set([root, document.body])", mark)
        # decided before the tone attribute is painted (no flash of tint)
        upd = js[js.index("function update()"):js.index("function paint()")]
        self.assertLess(upd.index("darken()"), upd.index("paint()"))
        apply_ = js[js.index("function apply("):js.index("function load()")]
        self.assertLess(apply_.index("darken()"), apply_.index("paint()"))

    def test_content_sets_live_with_off(self):
        # Fixes A and E: nothing is set before the list is known, then OFF
        # and LIVE together in paint().
        js = strip_comments(read("content.js"))
        self.assertIn("let off = null;", js)
        paint = js[js.index("function paint()"):js.index("function apply(")]
        self.assertIn("off === null", paint)
        self.assertLess(paint.index("off === null"), paint.index("setAttribute(LIVE"))
        self.assertEqual(js.count("setAttribute(LIVE"), 1)

    def test_content_waits_for_a_stored_list(self):
        # Fix E on a fresh install: a missing stored list is not an empty
        # one, or LIVE would come on for a site excluded at sync.
        js = strip_comments(read("content.js"))
        load = js[js.index("function load()"):js.index("let watched")]
        self.assertIn("Array.isArray(s.excluded)", load)
        self.assertNotIn("s.excluded ||", js)
        # the host is matched lowercased, without the dot of a full FQDN
        self.assertIn('hostExcluded(location.hostname.toLowerCase()'
                      '.replace(/\\.$/, ""), domains)', js)
        bjs = strip_comments(read("background.js"))
        self.assertIn("stored = Array.isArray(s.excluded);", bjs)
        self.assertIn("const first = !stored;", bjs)
        self.assertIn("if (!same || first)", bjs)

    def test_background_protocol(self):
        js = strip_comments(read("background.js"))
        self.assertIn('const HOST_APP = "%s";' % bg.NATIVE_HOST_NAME, js)
        self.assertIn('const OFF = "%s";' % bg.ATTR_OFF, js)
        self.assertIn("const PROTO = 1;", js)
        self.assertIn("const RETRY_MAX_MS = 60000;", js)
        # One busy tab never holds "applied" past the helper's wait: each
        # tab's sendMessage races TAB_WAIT_MS.
        wait = int(re.search(r"const TAB_WAIT_MS = (\d+);", js).group(1))
        self.assertLess(wait / 1000.0, bg.LIVE_ACK_TIMEOUT / 2)
        self.assertRegex(js, r"Promise\.race\(\[\s*browser\.tabs\.sendMessage\(tab\.id, "
                             r"\{type: \"excluded\", domains, darken: dark\}\)\.catch\(\(\) => \{\}\),\s*"
                             r"new Promise\(\(resolve\) => setTimeout\(resolve, TAB_WAIT_MS\)\)")
        # Fix B: lists are applied one at a time.
        self.assertIn("queue = queue.then(job)", js)
        # A private tab is never reported, and only the newest report is.
        self.assertIn("|| tab.incognito)", js)
        self.assertIn("const gen = ++reportGen;\n  const tabs = await browser.tabs.query", js)
        self.assertEqual(js.count("++reportGen"), 1)
        # "applied" goes back only on the port the list came on.
        self.assertIn("applyList(cleanList(msg.domains), msg.darken === true, msg.seq, self)", js)
        self.assertIn("&& from === port)", js)
        # darken (the darkPages setting) is stored with the list and read
        # back at startup: only true counts.
        self.assertIn("browser.storage.local.set({excluded: domains, darken: dark})", js)
        self.assertIn('browser.storage.local.get(["excluded", "darken"])', js)
        self.assertIn("darken = s.darken === true;", js)
        # a failed write is retried by the next list, even an identical one:
        # storage must not keep an old darken the helper switched off
        self.assertIn("let saved = false;", js)
        self.assertIn("if (changed || !saved)", js)
        self.assertIn("saved = await browser.storage.local.set({excluded: domains, darken: dark})"
                      ".then(() => true, () => false);", js)
        self.assertIn("stored = stored || saved;", js)
        self.assertIn("saved = stored;", js)
        self.assertNotIn("() => stored)", js)
        self.assertNotIn("all_frames", js)


class XpiTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def copy_ext(self, name="ext"):
        dst = os.path.join(self.tmp, name)
        shutil.copytree(str(EXT), dst)
        return dst

    def test_deterministic(self):
        one = bg.companion_xpi(str(EXT))
        self.assertEqual(one, bg.companion_xpi(str(EXT)))
        # Another folder with other dates and modes gives the same bytes.
        other = self.copy_ext()
        for top, _dirs, files in os.walk(other):
            for name in files:
                path = os.path.join(top, name)
                os.utime(path, (1234567890, 1234567890))
                os.chmod(path, 0o600)
        self.assertEqual(bg.companion_xpi(other), one)

    def test_layout(self):
        data = bg.companion_xpi(str(EXT))
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertIsNone(zf.testzip())
            names = zf.namelist()
            self.assertEqual(names, ["background.js", "content.js", "manifest.json",
                                     "vendor/darkreader-LICENSE.txt", "vendor/darkreader.js"])
            self.assertIn("manifest.json", names)  # at the root, no folder prefix
            for info in zf.infolist():
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.external_attr >> 16, 0o100644)
                self.assertEqual(zf.read(info), (EXT / info.filename).read_bytes())

    def test_sorted_subfolders_and_skipped_entries(self):
        ext = self.copy_ext()
        os.makedirs(os.path.join(ext, "icons"))
        os.makedirs(os.path.join(ext, ".git"))
        for rel in ("icons/b.svg", "icons/a.svg", ".hidden", ".git/config", "a.txt"):
            with open(os.path.join(ext, rel), "w") as f:
                f.write(rel)
        os.symlink("/etc/passwd", os.path.join(ext, "link.txt"))
        os.symlink(os.path.join(ext, "icons"), os.path.join(ext, "linked-dir"))
        with zipfile.ZipFile(io.BytesIO(bg.companion_xpi(ext))) as zf:
            self.assertEqual(zf.namelist(), ["a.txt", "background.js", "content.js",
                                             "icons/a.svg", "icons/b.svg", "manifest.json",
                                             "vendor/darkreader-LICENSE.txt", "vendor/darkreader.js"])

    def test_missing_manifest(self):
        ext = self.copy_ext()
        os.remove(os.path.join(ext, "manifest.json"))
        with self.assertRaises(ValueError):
            bg.companion_xpi(ext)
        os.makedirs(os.path.join(ext, "sub"))
        shutil.copy(str(EXT / "manifest.json"), os.path.join(ext, "sub", "manifest.json"))
        with self.assertRaises(ValueError):
            bg.companion_xpi(ext)  # only at the root

    def test_missing_folder(self):
        with self.assertRaises(OSError):
            bg.companion_xpi(os.path.join(self.tmp, "nope"))

    def test_xpi_name_is_the_gecko_id(self):
        self.assertEqual(bg.COMPANION_XPI, bg.COMPANION_ID + ".xpi")


class NativeManifestTest(unittest.TestCase):

    def test_valid(self):
        path = "/opt/u/.local/state/dms/browserGlass/" + bg.HOST_WRAPPER
        text = bg.native_manifest_text(path)
        self.assertTrue(text.endswith("\n"))
        doc = json.loads(text)
        self.assertEqual(sorted(doc), ["allowed_extensions", "description", "name", "path", "type"])
        self.assertRegex(doc["name"], r"^\w+(\.\w+)*$")
        self.assertEqual(doc["name"], bg.NATIVE_HOST_NAME)
        self.assertEqual(bg.NATIVE_MANIFEST_NAME, doc["name"] + ".json")
        self.assertTrue(os.path.isabs(doc["path"]))
        self.assertEqual(doc["path"], path)
        self.assertEqual(doc["type"], "stdio")
        self.assertEqual(doc["allowed_extensions"], [bg.COMPANION_ID])
        self.assertEqual(text, bg.native_manifest_text(path))

    def test_odd_path_round_trips(self):
        path = "/tmp/it's a \"dir\"/été/native-host"
        self.assertEqual(json.loads(bg.native_manifest_text(path))["path"], path)

    def test_relative_path_refused(self):
        for bad in ("native-host", "./x", "", None):
            with self.assertRaises(ValueError):
                bg.native_manifest_text(bad)

    def test_location(self):
        # Read by Firefox and LibreWolf; ~/.config/mozilla/... is not.
        self.assertEqual(bg.NATIVE_MANIFEST_REL, ".mozilla/native-messaging-hosts")


class HostWrapperTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        # A fake python3 that prints its arguments, NUL-separated.
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        fake = os.path.join(self.bin, "python3")
        with open(fake, "w") as f:
            f.write("#!/bin/sh\nprintf '%s\\0' \"$@\"\n")
        os.chmod(fake, 0o755)

    def run_wrapper(self, plugin_dir):
        wrapper = os.path.join(self.tmp, bg.HOST_WRAPPER)
        with open(wrapper, "w", encoding="utf-8") as f:
            f.write(bg.host_wrapper_text(plugin_dir))
        os.chmod(wrapper, 0o755)
        env = {"PATH": self.bin + os.pathsep + "/usr/bin:/bin"}
        out = subprocess.run([wrapper, "/m/" + bg.NATIVE_MANIFEST_NAME, bg.COMPANION_ID],
                             env=env, stdout=subprocess.PIPE, check=True).stdout
        return out.decode("utf-8").split("\0")[:-1]

    def expected(self, plugin_dir):
        return ["-I", "-B", plugin_dir + "/browserglass.py", "native-host",
                "--data", plugin_dir + "/data",
                "/m/" + bg.NATIVE_MANIFEST_NAME, bg.COMPANION_ID]

    def test_shape(self):
        text = bg.host_wrapper_text("/opt/plugins/browserGlass")
        self.assertTrue(text.startswith("#!/bin/sh\n"))
        self.assertTrue(text.endswith("\n"))
        self.assertIn("exec python3 -I -B ", text)
        self.assertIn('"$@"', text)

    def test_quotes_and_spaces(self):
        for plugin in ("/tmp/it's my plugins/browserGlass",
                       "/tmp/a b/$HOME `id` \"q\" ; rm -rf x/browserGlass",
                       "/tmp/été \\ back/browserGlass"):
            self.assertEqual(self.run_wrapper(plugin), self.expected(plugin), plugin)

    def test_trailing_slash(self):
        self.assertEqual(self.run_wrapper("/tmp/p q/"), self.expected("/tmp/p q"))

    def test_sh_syntax(self):
        text = bg.host_wrapper_text("/tmp/it's here/browserGlass")
        subprocess.run(["sh", "-n"], input=text.encode("utf-8"), check=True)

    def test_relative_refused(self):
        for bad in ("browserGlass", "", None):
            with self.assertRaises(ValueError):
                bg.host_wrapper_text(bad)


class ConstsTest(unittest.TestCase):

    def test_names(self):
        self.assertEqual(bg.EXTENSION_DIR, "extension")
        self.assertEqual(bg.NATIVE_HOST_NAME, "browserglass")
        self.assertEqual(bg.HOST_WRAPPER, "native-host")
        self.assertEqual(bg.RUNTIME_DIR_NAME, "browserGlass")
        self.assertEqual(bg.PREF_SIGNATURES, "xpinstall.signatures.required")
        self.assertEqual(bg.PREF_AUTODISABLE, "extensions.autoDisableScopes")
        self.assertEqual(bg.PREF_STARTUP_SCAN, "extensions.startupScanScopes")

    def test_live_control_setting(self):
        self.assertIs(bg.SETTINGS_DEFAULTS["liveControl"], True)
        self.assertIs(bg.settings_from_json('{"liveControl": false}')["liveControl"], False)
        self.assertIs(bg.settings_from_json('{"liveControl": "garbage"}')["liveControl"], True)


if __name__ == "__main__":
    unittest.main()

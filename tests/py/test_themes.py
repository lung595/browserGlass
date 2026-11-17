"""data/themes.json and themes_load(): the site theme recipes the native
host relays to the add-on (theme.js)."""

import json
import os
import shutil
import tempfile
import unittest

from fakehome import REPO, load_script

bg = load_script()
DATA = str(REPO / "data")


def recipe(**over):
    r = {"store": "local", "key": "theme", "op": "set", "from": ["light", None], "to": "dark",
         "verified": "2026-11-15", "note": "made up"}
    r.update(over)
    return r


class BundledTest(unittest.TestCase):

    def setUp(self):
        with open(os.path.join(DATA, bg.THEMES_FILE), encoding="utf-8") as f:
            self.doc = json.load(f)

    def test_generic_rule(self):
        gen = self.doc["generic"]
        self.assertEqual(sorted(gen["keys"]),
                         ["appearance", "color-mode", "color-scheme", "colorMode", "colorScheme", "theme"])
        self.assertEqual(gen["map"], {"light": "dark", "Light": "Dark", "LIGHT": "DARK",
                                      '"light"': '"dark"'})
        for a, b in gen["map"].items():
            self.assertIn("light", a.lower())
            self.assertEqual(a.lower().replace("light", "dark"), b.lower())

    def test_sites_are_valid(self):
        sites = self.doc["sites"]
        self.assertEqual(list(sites), sorted(sites))
        psl = bg.psl_load(DATA)
        clean = bg.themes_load(DATA)
        for host, recipes in sites.items():
            with self.subTest(host=host):
                self.assertEqual(bg.normalize_domain(host), host)
                self.assertIsNotNone(bg.psl_registrable(host, psl))
                ids = [(r["store"], r["key"], tuple(map(str, r["from"]))) for r in recipes]
                self.assertEqual(len(ids), len(set(ids)))
                for r in recipes:
                    self.assertTrue(bg._theme_date(r.get("verified")), r)
                    self.assertTrue(r.get("note", "").strip(), r)
                # nothing dropped
                self.assertEqual(len(clean["sites"][host]), len(recipes))

    def test_python_docs(self):
        # docs.python.org reads currentTheme (light, dark, auto): a stored
        # light turns dark; auto and absent follow the system already
        sent = bg.themes_load(DATA)["sites"]["docs.python.org"]
        self.assertEqual(sent, [{"store": "local", "key": "currentTheme", "op": "set",
                                 "from": ["light"], "to": "dark"}])

    def test_rev_is_stable(self):
        a = bg.themes_clean(self.doc)
        b = bg.themes_clean(json.loads(json.dumps(self.doc)))
        self.assertEqual(a["rev"], b["rev"])
        self.assertRegex(a["rev"], r"^[0-9a-f]{12}$")
        other = json.loads(json.dumps(self.doc))
        other["generic"]["keys"].append("mode")
        self.assertNotEqual(bg.themes_clean(other)["rev"], a["rev"])
        # notes and dates are not sent, and do not change the rev
        self.assertNotIn("note", json.dumps(a))


class CleanTest(unittest.TestCase):

    def clean(self, *recipes, host="example.org"):
        return bg.themes_clean({"generic": {"keys": [], "map": {}}, "sites": {host: list(recipes)}})["sites"]

    def test_good_recipes(self):
        self.assertEqual(self.clean(recipe()), {"example.org": [
            {"store": "local", "key": "theme", "op": "set", "from": ["light", None], "to": "dark"}]})
        out = self.clean(recipe(store="cookie", key="ae", domain=".example.org",
                                path="/", reload=True, skipIfCookie="session"))
        self.assertEqual(out["example.org"][0]["domain"], ".example.org")
        self.assertTrue(out["example.org"][0]["reload"])
        self.assertEqual(out["example.org"][0]["skipIfCookie"], "session")
        # no domain: a host-only cookie
        self.assertNotIn("domain", self.clean(recipe(store="cookie"))["example.org"][0])
        swap = self.clean(recipe(op="swap", key="x", **{"from": ["-day"]}, to="-os"))
        self.assertEqual(swap["example.org"][0]["op"], "swap")
        # a localStorage key may hold "/" (RTS's rts/feature/darkmode)
        slash = self.clean(recipe(key="rts/feature/darkmode", **{"from": [None, "none"]}))
        self.assertEqual(slash["example.org"][0]["key"], "rts/feature/darkmode")
        # a cookie name may start with a dot (Galaxus's .themeshade)
        self.assertEqual(self.clean(recipe(store="cookie", key=".themeshade"))["example.org"][0]["key"],
                         ".themeshade")
        # a localStorage value may hold JSON, commas included (Home Assistant's
        # demo_theme); a cookie value may not
        light, auto = '{"theme":"default","dark":false}', '{"theme":"default"}'
        js = self.clean(recipe(key="demo_theme", **{"from": [None, light]}, to=auto))
        self.assertEqual(js["example.org"][0]["from"], [None, light])
        self.assertEqual(js["example.org"][0]["to"], auto)
        self.assertEqual(self.clean(recipe(key="x", to="a;b,c"))["example.org"][0]["to"], "a;b,c")
        self.assertEqual(self.clean(recipe(store="cookie", **{"from": [None, light]}, to="dark")), {})

    def test_bad_rows_are_dropped(self):
        bad = [
            recipe(store="session"), recipe(op="toggle"), recipe(key="a b"), recipe(key="k" * 65),
            recipe(store="cookie", to="a;b"), recipe(store="cookie", to="a,b"), recipe(to="a\nb"), recipe(to="x" * 65), recipe(to=""),
            recipe(**{"from": []}), recipe(**{"from": "light"}), recipe(**{"from": ["dark"]}),
            recipe(**{"from": [1]}), recipe(verified="2026-13-01"), recipe(verified=None),
            recipe(note=""), recipe(note=None),
            recipe(op="swap", **{"from": ["a", "b"]}), recipe(op="swap", **{"from": [None]}),
            recipe(store="cookie", path="x"), recipe(store="cookie", domain="other.org"),
            recipe(store="cookie", domain=".org.example"), recipe(store="cookie", reload="yes"),
            recipe(path="/"), recipe(reload=True), recipe(skipIfCookie="a b"), "x", None,
            recipe(store="cookie", key="a/b"), recipe(skipIfCookie="a/b"),
        ]
        for r in bad:
            with self.subTest(r=r):
                self.assertEqual(self.clean(r), {})
        # one bad row never drops its neighbours
        self.assertEqual(len(self.clean(recipe(store="x"), recipe())["example.org"]), 1)
        for host in ("Example.org", "*.example.org", "exa mple.org", ""):
            self.assertEqual(self.clean(recipe(), host=host), {})
        self.assertEqual(bg.themes_clean([]), {})
        gen = bg.themes_clean({"generic": {"keys": ["theme", "a b", 3],
                                           "map": {"light": "dark", "x": "x", "a;": "b", "": "d"}}})
        self.assertEqual(gen["generic"], {"keys": ["theme"], "map": {"light": "dark"}})
        self.assertEqual(gen["sites"], {})


class LoadTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)
        self.path = os.path.join(self.dir, bg.THEMES_FILE)

    def test_missing_and_broken(self):
        self.assertEqual(bg.themes_load(self.dir), {})
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(bg.themes_load(self.dir), {})
        with open(self.path, "w") as f:
            f.write("[]")
        self.assertEqual(bg.themes_load(self.dir), {})

    def test_read_again_when_changed(self):
        with open(self.path, "w") as f:
            json.dump({"generic": {"keys": ["theme"], "map": {"light": "dark"}}, "sites": {}}, f)
        first = bg.themes_load(self.dir)
        self.assertEqual(first["generic"]["keys"], ["theme"])
        with open(self.path, "w") as f:
            json.dump({"generic": {"keys": ["theme", "appearance"], "map": {"light": "dark"}},
                       "sites": {}}, f)
        os.utime(self.path, ns=(1, 1))
        second = bg.themes_load(self.dir)
        self.assertEqual(second["generic"]["keys"], ["appearance", "theme"])
        self.assertNotEqual(first["rev"], second["rev"])


if __name__ == "__main__":
    unittest.main()

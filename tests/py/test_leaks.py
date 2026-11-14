"""Leak guard: no file of the repository tree (every folder but .git and
__pycache__: code, components/, tools/, data/, tests/, .github/...; gzip
goldens decompressed) names the denylisted vendors, carries a commit
attribution trailer, names the user running the tests or a home folder, or
holds a real Firefox profile id.

The words are stored rot13-encoded so this file does not carry them either.
Profile ids are random per machine, so the repo holds none of them, not even
hashed: list yours (comma-separated) in BG_LEAK_PROFILE_IDS to have
test_profile_ids look for them. Nothing outside the repo is read.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import codecs
import getpass
import gzip
import hashlib
import os
import re
import unittest

from fakehome import REPO

# Case-insensitive, matched anywhere. The vendor words are also in
# tools/style-denylist.txt (as sha256 "word" entries) for update_styles.py's
# filter of the upstream styles: test_style_denylist_in_step keeps the two
# lists in step.
VENDOR_WORDS = tuple(codecs.decode(word, "rot13") for word in ("pynhqr", "naguebcvp"))
# Plus the commit attribution trailer
DENYLIST = VENDOR_WORDS + (codecs.decode("pb-nhguberq", "rot13"),)
# Real profile ids that must never be committed, from the environment only.
PROFILE_IDS_ENV = "BG_LEAK_PROFILE_IDS"
SKIP_DIRS = {".git", "__pycache__"}
# The only places allowed to spell a home prefix: leak-guard token lists.
HOME_TOKEN_ALLOWED = {os.path.join("tests", "py", "test_contract.py")}
PROFILE_LIKE = re.compile(r"(?<![a-z0-9])([a-z0-9]{8})\.")


def repo_texts():
    """[(relative path, text)] of every repo file, .gz decompressed."""
    out = []
    for folder, dirs, files in os.walk(str(REPO)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(folder, name)
            if os.path.islink(path):
                continue
            with open(path, "rb") as f:
                data = f.read()
            if name.endswith(".gz"):
                data = gzip.decompress(data)
            out.append((os.path.relpath(path, str(REPO)), data.decode("utf-8", "replace")))
    return out


class LeakTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.texts = repo_texts()

    def test_files_scanned(self):
        names = {rel for rel, _ in self.texts}
        self.assertIn("browserglass.py", names)
        self.assertIn(os.path.join("data", "styles.json"), names)
        self.assertTrue(any(rel.endswith(".gz") for rel in names))

    def test_denylist(self):
        rx = re.compile("|".join(DENYLIST), re.I)
        for rel, text in self.texts:
            hit = rx.search(text)
            self.assertIsNone(hit, "%s at %d" % (rel, hit.start()) if hit else rel)

    def test_style_denylist_in_step(self):
        entries = set()
        with open(os.path.join(str(REPO), "tools", "style-denylist.txt"), encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 3 and parts[0] == "word":
                    entries.add((int(parts[1]), parts[2]))
        for word in VENDOR_WORDS:
            digest = hashlib.sha256(word.encode("utf-8")).hexdigest()
            self.assertIn((len(word), digest), entries)

    def test_user_and_home(self):
        home = os.path.expanduser("~").rstrip("/")
        tokens = set()
        # generic account/folder names (CI runners, containers, fake HOMEs)
        # are ordinary words in the code, not personal data
        generic = {"home", "root", "user", "users", "runner", "build", "tmp", "test"}
        for tok in (getpass.getuser(), os.path.basename(home)):
            if tok and len(tok) >= 3 and tok.lower() not in generic:
                tokens.add(tok.lower())
        if len(home) > 1:
            tokens.add(home.lower())
        for rel, text in self.texts:
            low = text.lower()
            for tok in tokens:
                self.assertNotIn(tok, low, rel)
            if rel not in HOME_TOKEN_ALLOWED:
                self.assertNotIn("/" + "home/", low, rel)

    def test_profile_ids(self):
        ids = {x.strip().lower() for x in os.environ.get(PROFILE_IDS_ENV, "").split(",")}
        ids.discard("")
        if not ids:
            self.skipTest("set %s to the profile ids to look for" % PROFILE_IDS_ENV)
        for rel, text in self.texts:
            for match in PROFILE_LIKE.finditer(text.lower()):
                self.assertNotIn(match.group(1), ids, "%s at %d" % (rel, match.start()))


if __name__ == "__main__":
    unittest.main()

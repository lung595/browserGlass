"""tools/sign_companion.py against a fake AMO server on 127.0.0.1 (port 0,
one thread per test), with made-up keys, a copy of extension/ and a
temporary state folder. Nothing here uses the real network.

Run: python3 -B -m unittest discover -s tests/py -v
"""

import ast
import base64
import contextlib
import hashlib
import hmac
import http.server
import io
import json
import os
import re
import shutil
import stat
import sys
import threading
import time
import unittest
import urllib.parse
import uuid
import zipfile
from unittest import mock

from fakehome import REPO, FakeHome, load_script

TOOL = REPO / "tools" / "sign_companion.py"
EXT = REPO / "extension"
GUID = "browserglass@companion"
UPLOAD_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
VERSION_ID = 777
FAST = ["--poll-interval", "0.01", "--timeout", "2"]

# Made-up keys, built at run time so the source never spells a key shape.
KEY = "user:" + "12345" + ":67"
SECRET = "S3CRET-canary-" + "a8f0c2d9e7b14b5c9d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a"

_TOOL_MODULE = None


def load_tool():
    global _TOOL_MODULE
    if _TOOL_MODULE is None:
        import importlib.util
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec = importlib.util.spec_from_file_location("sign_companion_under_test", str(TOOL))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = old
        _TOOL_MODULE = module
    return _TOOL_MODULE


tool = load_tool()
bg = load_script()


def b64d(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def jwt_parts(token):
    head, body, sig = token.split(".")
    return json.loads(b64d(head)), json.loads(b64d(body)), head, body, sig


def signed_xpi(plain, extra=None, drop=None, change=None, signature=True):
    """A test "signed" xpi: the entries of `plain` re-zipped (deflated, the
    way AMO repacks), plus fake META-INF files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(plain)) as src, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if signature:
            for name in ("META-INF/cose.manifest", "META-INF/cose.sig", "META-INF/manifest.mf",
                         "META-INF/mozilla.sf", "META-INF/mozilla.rsa"):
                zf.writestr(name, b"fake signature " + name.encode("ascii"))
        for name in src.namelist():
            if name == drop:
                continue
            data = src.read(name)
            if name == change:
                data += b"\n// changed\n"
            zf.writestr(name, data)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def parse_multipart(content_type, body):
    """{name: (filename, content type, bytes)} of a multipart/form-data body."""
    boundary = re.search(r"boundary=(\S+)", content_type).group(1).encode("ascii")
    out = {}
    chunks = body.split(b"--" + boundary)
    assert chunks[0] == b"" and chunks[-1] == b"--\r\n", "bad framing"
    for chunk in chunks[1:-1]:
        assert chunk.startswith(b"\r\n") and chunk.endswith(b"\r\n")
        head, data = chunk[2:-2].split(b"\r\n\r\n", 1)
        headers = head.decode("ascii")
        name = re.search(r'name="([^"]*)"', headers).group(1)
        filename = re.search(r'filename="([^"]*)"', headers)
        ctype = re.search(r"Content-Type: (\S+)", headers)
        out[name] = (filename.group(1) if filename else None, ctype.group(1) if ctype else None, data)
    return out


class FakeAmo:
    """A scriptable AMO API v5 on 127.0.0.1 (or `host`), port 0."""

    def __init__(self, host="127.0.0.1"):
        self.requests = []
        self.upload_code = 201
        self.upload_body = None
        self.submit_code = 201
        self.submit_body = None
        self.processed_after = 1
        self.valid = True
        self.status_sequence = ["unreviewed", "public"]
        self.file_url = None
        self.redirect_to = None
        self.signed = b""
        self.lock = threading.Lock()
        self.upload_polls = 0
        self.version_polls = 0
        amo = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                amo.handle(self, "GET")

            def do_POST(self):
                amo.handle(self, "POST")

            def do_PUT(self):
                amo.handle(self, "PUT")

        self.server = http.server.ThreadingHTTPServer((host, 0), Handler)
        self.port = self.server.server_address[1]
        self.base = "http://%s:%d" % (host, self.port)
        self.api = self.base + "/api/v5/"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02})
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    @property
    def tokens(self):
        return [r["auth"][4:] for r in self.requests if r["auth"].startswith("JWT ")]

    def paths(self, method=None):
        return [r["path"] for r in self.requests if method is None or r["method"] == method]

    def reply(self, h, code, doc=None, body=None, headers=()):
        if body is None:
            body = json.dumps(doc).encode("utf-8") if doc is not None else b""
        h.send_response(code)
        for k, v in headers:
            h.send_header(k, v)
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    def version_doc(self):
        with self.lock:
            i = min(self.version_polls, len(self.status_sequence) - 1)
            self.version_polls += 1
        status = self.status_sequence[i]
        url = self.file_url or self.base + "/downloads/file/%d/x.xpi?token=private-query" % VERSION_ID
        return {"id": VERSION_ID, "version": self.manifest_version,
                "file": {"id": 5, "status": status, "url": url if status == "public" else None}}

    def handle(self, h, method):
        length = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(length) if length else b""
        path = urllib.parse.unquote(urllib.parse.urlsplit(h.path).path)
        auth = h.headers.get("Authorization") or ""
        with self.lock:
            self.requests.append({"method": method, "path": path, "auth": auth, "body": body,
                                  "ctype": h.headers.get("Content-Type") or ""})
        api = "/api/v5/"
        addon = api + "addons/addon/%s/" % GUID
        if method == "POST" and path == api + "addons/upload/":
            code = self.upload_code
            if code in (200, 201, 202):
                return self.reply(h, code, {"uuid": UPLOAD_ID, "processed": False, "valid": False,
                                            "validation": None, "channel": "unlisted"})
            doc = self.upload_body or {"detail": "echo: %s key %s" % (auth, KEY)}
            return self.reply(h, code, doc)
        if method == "GET" and path == api + "addons/upload/%s/" % UPLOAD_ID:
            with self.lock:
                self.upload_polls += 1
                done = self.upload_polls >= self.processed_after
            validation = {"errors": 0 if self.valid else 1, "warnings": 2, "notices": 1,
                          "messages": [{"type": "warning", "message": "Unsafe assignment to innerHTML",
                                        "file": "vendor/darkreader.js"},
                                       {"type": "error" if not self.valid else "notice",
                                        "message": "Token " + auth, "file": None}]}
            return self.reply(h, 200, {"uuid": UPLOAD_ID, "processed": done, "valid": done and self.valid,
                                       "validation": validation if done else None})
        if method == "PUT" and path == addon:
            if self.submit_code != 201:
                return self.reply(h, self.submit_code, self.submit_body)
            return self.reply(h, 201, {"guid": GUID, "version": {"id": VERSION_ID, "file": {"status": "unreviewed"}}})
        if method == "GET" and path in (addon + "versions/%d/" % VERSION_ID,
                                        addon + "versions/v%s/" % self.manifest_version):
            return self.reply(h, 200, self.version_doc())
        if method == "GET" and path == "/downloads/file/%d/x.xpi" % VERSION_ID:
            target = self.redirect_to or self.base + "/cdn/signed.xpi?sig=private"
            return self.reply(h, 302, headers=[("Location", target)])
        if method == "GET" and path == "/cdn/signed.xpi":
            return self.reply(h, 200, body=self.signed)
        return self.reply(h, 404, {"detail": "not found"})


class SignCompanionCase(unittest.TestCase):

    def setUp(self):
        # each test proves its own redaction: no secret left by an earlier one
        tool.REDACT.secrets.clear()
        self.cred_files = set()
        self.fh = FakeHome()
        self.addCleanup(self.fh.cleanup)
        self.tmp = str(self.fh.tmp)
        self.ext = os.path.join(self.tmp, "extension")
        shutil.copytree(str(EXT), self.ext)
        self.state = os.path.join(self.tmp, "amo-state")
        self.amo = FakeAmo()
        self.addCleanup(self.amo.stop)
        self.amo.manifest_version = self.manifest_version()
        self.amo.signed = signed_xpi(bg.companion_xpi(self.ext))
        # in-process runs: no proxy may catch the loopback requests
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for name in list(os.environ):
            if name.lower().endswith("_proxy"):
                del os.environ[name]
        self.outputs = []

    def manifest_version(self):
        with open(os.path.join(self.ext, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)["version"]

    def set_version(self, version):
        path = os.path.join(self.ext, "manifest.json")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(re.sub(r'"version": "[^"]*"', '"version": "%s"' % version, text, count=1))
        self.amo.manifest_version = version
        self.amo.signed = signed_xpi(bg.companion_xpi(self.ext))

    def common(self, *extra):
        return ["--api-url", self.amo.api, "--state", self.state, "--ext", self.ext] + FAST + list(extra)

    def key_env(self):
        return {"WEB_EXT_API_KEY": KEY, "WEB_EXT_API_SECRET": SECRET}

    def run_sub(self, *args, env=None):
        """The tool in a subprocess; (exit status, JSON line, stderr)."""
        proc = self.fh.run_script(list(args), script=TOOL, extra_env=self.key_env() if env is None else env,
                                  timeout=30)
        self.outputs.append(proc.stdout + proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout + proc.stderr)
        return proc.returncode, json.loads(lines[0]), proc.stderr

    def run_in(self, *args, env=None):
        """The tool's main() in this process; (exit status, JSON line, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        env = dict(self.fh.env(), **(self.key_env() if env is None else env))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = tool.main(list(args), env=env)
        self.outputs.append(out.getvalue() + err.getvalue())
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, out.getvalue() + err.getvalue())
        return code, json.loads(lines[0]), err.getvalue()

    def assert_no_secret(self):
        """Neither the key, the secret nor a token the server got is in any
        output of this test, nor in any file under the fake root (state,
        --out, the extension copy, leftover temporary files), except the
        credentials files the test wrote itself."""
        tokens = self.amo.tokens
        for text in self.outputs:
            self.assertNotIn(KEY, text)
            self.assertNotIn(SECRET, text)
            self.assertNotIn("canary", text)
            for token in tokens:
                self.assertNotIn(token, text)
                for part in token.split("."):
                    self.assertNotIn(part, text)
        needles = {KEY.encode("utf-8"), SECRET.encode("utf-8"), b"canary"}
        for token in tokens:
            needles.update(part.encode("ascii") for part in token.split("."))
        skip = {os.path.realpath(p) for p in self.cred_files}
        for folder, _, names in os.walk(str(self.fh.root)):
            for name in names:
                path = os.path.join(folder, name)
                if os.path.realpath(path) in skip or not stat.S_ISREG(os.lstat(path).st_mode):
                    continue
                with open(path, "rb") as f:
                    data = f.read()
                for needle in needles:
                    self.assertNotIn(needle, data, path)

    def recorded(self):
        path = os.path.join(self.state, "amo-versions.json")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)["versions"]


class JwtTest(SignCompanionCase):

    def check_token(self, token, now):
        header, claims, head, body, sig = jwt_parts(token)
        self.assertEqual(header, {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(claims["iss"], KEY)
        self.assertEqual(uuid.UUID(claims["jti"]).version, 4)
        self.assertLessEqual(abs(claims["iat"] - now), 5)
        self.assertEqual(claims["exp"] - claims["iat"], 60)
        self.assertLessEqual(claims["exp"] - claims["iat"], 300)
        want = hmac.new(SECRET.encode("utf-8"), ("%s.%s" % (head, body)).encode("ascii"),
                        hashlib.sha256).digest()
        self.assertTrue(hmac.compare_digest(b64d(sig), want))
        return claims["jti"]

    def test_make_jwt(self):
        now = time.time()
        jtis = {self.check_token(tool.make_jwt(KEY, SECRET), now) for _ in range(5)}
        self.assertEqual(len(jtis), 5)

    def test_fresh_token_per_request(self):
        code, line, _ = self.run_sub("sign", *self.common())
        self.assertEqual(code, 0)
        self.assertGreaterEqual(len(self.amo.requests), 6)
        now = time.time()
        jtis = [self.check_token(t, now) for t in self.amo.tokens]
        # every request to the API host, downloads on it too (other hosts: test_no_token_to_another_download_host)
        self.assertEqual(len(self.amo.tokens), len(self.amo.requests))
        self.assertEqual(len(set(jtis)), len(jtis))
        self.assert_no_secret()


class SignTest(SignCompanionCase):

    def test_happy_path(self):
        code, line, err = self.run_sub("sign", "--version-check", *self.common())
        self.assertEqual(code, 0, err)
        version = self.manifest_version()
        out = os.path.join(self.state, "signed", "browserglass@companion-%s.xpi" % version)
        self.assertEqual(line, {"version": version, "xpi": out, "status": "public", "warnings": 2})
        with open(out, "rb") as f:
            self.assertEqual(f.read(), self.amo.signed)
        self.assertEqual(self.recorded(), [version])
        self.assertEqual(self.amo.paths(), [
            "/api/v5/addons/upload/",
            "/api/v5/addons/upload/%s/" % UPLOAD_ID,
            "/api/v5/addons/addon/%s/" % GUID,
            "/api/v5/addons/addon/%s/versions/%d/" % (GUID, VERSION_ID),
            "/api/v5/addons/addon/%s/versions/%d/" % (GUID, VERSION_ID),
            "/downloads/file/%d/x.xpi" % VERSION_ID,
            "/cdn/signed.xpi",
        ])
        # the upload: the packed bytes, channel unlisted
        upload = self.amo.requests[0]
        parts = parse_multipart(upload["ctype"], upload["body"])
        self.assertTrue(upload["ctype"].startswith("multipart/form-data; boundary="))
        self.assertEqual(parts["channel"], (None, None, b"unlisted"))
        self.assertEqual(parts["upload"], ("browserglass@companion.xpi", "application/x-xpinstall",
                                           bg.companion_xpi(self.ext)))
        # the submission: the upload id and the notes on Dark Reader
        doc = json.loads(self.amo.requests[2]["body"].decode("utf-8"))
        self.assertEqual(self.amo.requests[2]["method"], "PUT")
        self.assertEqual(doc["version"]["upload"], UPLOAD_ID)
        notes = doc["version"]["approval_notes"]
        self.assertIn("Dark Reader 4.9.135", notes)
        self.assertIn("https://registry.npmjs.org/darkreader/-/darkreader-4.9.135.tgz", notes)
        self.assertIn("package/darkreader.js", notes)
        self.assertIn("LF instead of CRLF", notes)
        self.assertIn("native messaging host", notes)
        self.assertIn("validation: 0 errors, 2 warnings", err)
        self.assertNotIn("private", err + json.dumps(line))  # no URL query in the output
        self.assert_no_secret()

    def test_in_process_happy_path_and_out(self):
        out = os.path.join(self.tmp, "custom", "signed.xpi")
        code, line, err = self.run_in("sign", *self.common("--out", out))
        self.assertEqual(code, 0, err)
        self.assertEqual(line["xpi"], out)
        self.assertEqual(line["status"], "public")
        self.assert_no_secret()

    def test_409_version_used(self):
        self.amo.upload_code = 409
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("version already used on AMO", err)
        self.assertEqual(line["status"], "refused")
        self.assertIsNone(line["xpi"])
        # recorded before the upload, kept after the refusal
        self.assertEqual(self.recorded(), [self.manifest_version()])
        self.assertEqual(len(self.amo.paths("POST")), 1)
        self.assert_no_secret()

    def test_submit_400_nested_version_used(self):
        for body in ({"version": {"version": ["Version %s already exists." % self.manifest_version()]}},
                     {"version": {"non_field_errors": ["Version already exists."]}}):
            self.amo.submit_code = 400
            self.amo.submit_body = body
            code, line, err = self.run_in("sign", *self.common())
            self.assertEqual(code, 1, err)
            self.assertEqual(line["status"], "refused", err)
            self.assertIn("submit: version already used on AMO (HTTP 400)", err)
            os.remove(os.path.join(self.state, "amo-versions.json"))
        self.assert_no_secret()

    def test_submit_400_nested_detail_shown(self):
        self.amo.submit_code = 400
        self.amo.submit_body = {"version": {"approval_notes": ["Ensure this field has no more than 3000 characters."]}}
        code, line, err = self.run_in("sign", *self.common())
        self.assertEqual(code, 1, err)
        self.assertEqual(line["status"], "failed")
        self.assertIn("submit: HTTP 400: Ensure this field", err)

    def test_detail_shapes(self):
        cases = [({"detail": "x"}, "x"), ({"a": ["y"]}, "y"), ({"a": "z"}, "z"),
                 ({"version": {"version": ["nested"]}}, "nested"),
                 ({"version": {"non_field_errors": ["nfe"]}}, "nfe"),
                 ({"a": {}, "b": [{"c": ["deep"]}]}, "deep"), (["top"], "top"),
                 ({"a": 1}, ""), ([], "")]
        for doc, want in cases:
            self.assertEqual(tool._detail(json.dumps(doc).encode("utf-8")), want, doc)
        deep = "end"
        for _ in range(50):
            deep = {"k": deep}
        self.assertEqual(tool._detail(json.dumps(deep).encode("utf-8")), "")
        self.assertEqual(tool._detail(b"not json"), "")

    def test_429_no_retry(self):
        self.amo.upload_code = 429
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("rate limited, try later", err)
        self.assertEqual(len(self.amo.requests), 1)
        self.assert_no_secret()

    def test_401_echoing_the_header(self):
        self.amo.upload_code = 401
        for runner in (self.run_sub, self.run_in):
            code, line, err = runner("sign", *self.common())
            self.assertEqual(code, 1)
            self.assertIn("authentication refused", err)
            os.remove(os.path.join(self.state, "amo-versions.json"))
        self.assertTrue(all(r["auth"].startswith("JWT ") for r in self.amo.requests))
        self.assert_no_secret()

    def test_400_detail_is_redacted(self):
        self.amo.upload_code = 400
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("HTTP 400: echo: <redacted>", err)
        self.assert_no_secret()

    def test_validation_rejected(self):
        self.amo.valid = False
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertEqual(line["status"], "rejected")
        self.assertEqual(line["warnings"], 2)
        self.assertIn("validation failed", err)
        self.assertIn("Unsafe assignment to innerHTML (vendor/darkreader.js)", err)
        self.assertNotIn("PUT", [r["method"] for r in self.amo.requests])
        self.assert_no_secret()

    def test_file_disabled(self):
        self.amo.status_sequence = ["unreviewed", "disabled"]
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertEqual(line["status"], "rejected")
        self.assertIn("rejected by AMO", err)
        self.assertFalse(os.path.exists(os.path.join(self.state, "signed")))
        self.assert_no_secret()

    def test_timeout_then_fetch(self):
        self.amo.status_sequence = ["unreviewed"]
        args = ["--api-url", self.amo.api, "--state", self.state, "--ext", self.ext,
                "--poll-interval", "0.01", "--timeout", "0.2"]
        code, line, err = self.run_sub("sign", *args)
        self.assertEqual(code, 3)
        self.assertEqual(line["status"], "timeout")
        self.assertIsNone(line["xpi"])
        version = self.manifest_version()
        self.assertIn("AMO version id %d" % VERSION_ID, err)
        self.assertIn("fetch %s" % version, err)
        self.amo.status_sequence = ["public"]
        self.amo.version_polls = 0
        code, line, err = self.run_sub("fetch", version, *args)
        self.assertEqual(code, 0, err)
        self.assertEqual(line["status"], "public")
        self.assertIn("/api/v5/addons/addon/%s/versions/v%s/" % (GUID, version), self.amo.paths())
        with open(line["xpi"], "rb") as f:
            self.assertEqual(f.read(), self.amo.signed)
        self.assert_no_secret()

    def test_upload_validation_timeout(self):
        self.amo.processed_after = 10 ** 6
        code, line, err = self.run_in("sign", "--api-url", self.amo.api, "--state", self.state,
                                      "--ext", self.ext, "--poll-interval", "0.01", "--timeout", "0.1")
        self.assertEqual(code, 3)
        self.assertIn(UPLOAD_ID, err)
        self.assert_no_secret()

    def test_redirect_to_another_host_refused(self):
        try:
            other = FakeAmo("127.0.0.2")
        except OSError:
            other = None
        if other is not None:
            self.addCleanup(other.stop)
            other.signed = self.amo.signed
            targets = [other.base + "/cdn/signed.xpi?sig=private"]
        else:
            targets = []
        targets += ["http://evil.invalid/cdn/signed.xpi?sig=private",
                    "https://addons.mozilla.org.evil.invalid/x.xpi",
                    "http://127.0.0.1:%d/cdn/signed.xpi" % (self.amo.port + 1 if self.amo.port < 65535 else 1)]
        for i, target in enumerate(targets):
            self.amo.redirect_to = target
            self.amo.version_polls = 0
            code, line, err = self.run_in("sign", *self.common())
            self.assertEqual(code, 1, err)
            self.assertIn("refused", err)
            self.assertNotIn("private", err)
            os.remove(os.path.join(self.state, "amo-versions.json"))
        if other is not None:
            self.assertEqual(other.requests, [])
        self.assert_no_secret()

    def test_no_token_to_another_download_host(self):
        try:
            other = FakeAmo("127.0.0.2")
        except OSError:
            self.skipTest("127.0.0.2 not available")
        self.addCleanup(other.stop)
        other.manifest_version = self.amo.manifest_version
        other.signed = self.amo.signed
        self.amo.redirect_to = other.base + "/cdn/signed.xpi"
        allowed = tool.download_allowed
        with mock.patch.object(tool, "download_allowed",
                               side_effect=lambda url, api: url.startswith(other.base) or allowed(url, api)):
            code, line, err = self.run_in("sign", *self.common())
        self.assertEqual(code, 0, err)
        self.assertEqual(other.paths(), ["/cdn/signed.xpi"])
        self.assertEqual([r["auth"] for r in other.requests], [""])
        self.assertTrue(all(r["auth"].startswith("JWT ") for r in self.amo.requests))
        self.assert_no_secret()

    def test_auth_allowed(self):
        api = "http://127.0.0.1:8000/api/v5/"
        for url in ("http://127.0.0.1:8000/downloads/a.xpi", "https://addons.mozilla.org/firefox/a.xpi"):
            self.assertTrue(tool.auth_allowed(url, api), url)
        for url in ("https://addons.cdn.mozilla.net/user-media/a.xpi", "http://127.0.0.1:8001/a.xpi",
                    "https://127.0.0.1:8000/a.xpi", "http://addons.mozilla.org/a.xpi",
                    "https://addons.mozilla.org:8443/a.xpi", "https://x@addons.mozilla.org/a.xpi",
                    "https://addons.mozilla.org.evil.invalid/a.xpi"):
            self.assertFalse(tool.auth_allowed(url, api), url)

    def test_file_url_on_another_host_refused(self):
        self.amo.file_url = "http://evil.invalid/x.xpi?token=private"
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("download from http://evil.invalid/x.xpi refused", err)
        self.assert_no_secret()

    def test_download_allowed(self):
        api = "http://127.0.0.1:8000/api/v5/"
        ok = ["https://addons.mozilla.org/firefox/downloads/file/1/a.xpi",
              "https://addons.cdn.mozilla.net/user-media/a.xpi",
              "http://127.0.0.1:8000/cdn/a.xpi"]
        bad = ["http://addons.mozilla.org/a.xpi", "https://mozilla.net.evil.invalid/a.xpi",
               "https://evil.invalid/?u=addons.mozilla.org", "http://127.0.0.1:8001/a.xpi",
               "https://127.0.0.1:8000/a.xpi", "https://x@addons.mozilla.org/a.xpi",
               "https://addons.mozilla.org:99999/a.xpi"]
        for url in ok:
            self.assertTrue(tool.download_allowed(url, api), url)
        for url in bad:
            self.assertFalse(tool.download_allowed(url, api), url)
        self.assertEqual(tool.shown_url("https://u:p@h.example:8443/a/b?q=1#f"), "https://h.example:8443/a/b")

    def test_api_url_must_be_https(self):
        code, line, err = self.run_in("sign", "--api-url", "http://amo.example/api/v5/",
                                      "--state", self.state, "--ext", self.ext)
        self.assertEqual(code, 2)
        self.assertEqual(self.recorded(), [])


class VersionCheckTest(SignCompanionCase):

    def test_same_version_twice(self):
        code, _, _ = self.run_in("sign", *self.common())
        self.assertEqual(code, 0)
        count = len(self.amo.requests)
        code, line, err = self.run_sub("sign", "--version-check", *self.common())
        self.assertEqual(code, 1)
        self.assertEqual(line["status"], "refused")
        self.assertIn("already sent to AMO", err)
        self.assertEqual(len(self.amo.requests), count)
        self.assert_no_secret()

    def test_lower_version(self):
        os.makedirs(self.state)
        with open(os.path.join(self.state, "amo-versions.json"), "w", encoding="utf-8") as f:
            json.dump({"versions": ["1.2.90", "9.0"]}, f)
        self.set_version("1.3.0")
        code, line, err = self.run_sub("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("not greater than 9.0", err)
        self.assertEqual(self.amo.requests, [])
        self.set_version("9.0.0")  # 9.0.0 == 9.0
        code, line, err = self.run_in("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertEqual(self.amo.requests, [])
        self.set_version("9.0.1")
        code, line, err = self.run_in("sign", *self.common())
        self.assertEqual(code, 0, err)
        self.assertEqual(self.recorded(), ["1.2.90", "9.0", "9.0.1"])

    def test_bad_versions_file_refused(self):
        os.makedirs(self.state)
        with open(os.path.join(self.state, "amo-versions.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        code, line, err = self.run_in("sign", *self.common())
        self.assertEqual(code, 1)
        self.assertIn("unreadable", err)
        self.assertEqual(self.amo.requests, [])

    def test_version_key(self):
        self.assertLess(tool.version_key("1.2.90"), tool.version_key("1.3"))
        self.assertLess(tool.version_key("1.9"), tool.version_key("1.10"))
        self.assertEqual(tool.version_key("1.3.0"), tool.version_key("1.3"))


class CredentialsTest(SignCompanionCase):

    def write_creds(self, mode, path=None):
        path = path or os.path.join(self.tmp, "creds")
        self.cred_files.add(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write("# AMO keys\nWEB_EXT_API_KEY=%s\nWEB_EXT_API_SECRET=%s\n" % (KEY, SECRET))
        os.chmod(path, mode)
        return path

    def load(self, env):
        try:
            return tool.load_credentials(env), None
        except tool.ToolError as exc:
            self.outputs.append(str(exc))
            return None, str(exc)

    def test_mode_0600_accepted(self):
        path = self.write_creds(0o600)
        self.assertEqual(self.load({"BG_AMO_CREDENTIALS": path}), ((KEY, SECRET), None))

    def test_default_path_under_home(self):
        folder = os.path.join(str(self.fh.home), ".config", "browserglass-amo")
        os.makedirs(folder)
        self.write_creds(0o600, os.path.join(folder, "credentials"))
        self.assertEqual(self.load({"HOME": str(self.fh.home)})[0], (KEY, SECRET))
        # the subprocess finds it in the fake HOME too
        code, line, err = self.run_sub("sign", *self.common(), env={})
        self.assertEqual(code, 0, err)
        self.assert_no_secret()

    def test_mode_0644_refused(self):
        path = self.write_creds(0o644)
        creds, err = self.load({"BG_AMO_CREDENTIALS": path})
        self.assertIsNone(creds)
        self.assertIn(path, err)
        self.assertIn("0644", err)
        code, line, err = self.run_sub("sign", *self.common(), env={"BG_AMO_CREDENTIALS": path})
        self.assertEqual(code, 1)
        self.assertIn("mode 0644", err)
        self.assertEqual(self.amo.requests, [])
        self.assertEqual(self.recorded(), [])  # a refusal consumes no version
        for mode in (0o640, 0o604, 0o660):
            os.chmod(path, mode)
            self.assertIsNone(self.load({"BG_AMO_CREDENTIALS": path})[0])
        self.assert_no_secret()

    def test_symlink_and_folder_refused(self):
        target = self.write_creds(0o600)
        link = os.path.join(self.tmp, "link")
        os.symlink(target, link)
        creds, err = self.load({"BG_AMO_CREDENTIALS": link})
        self.assertIsNone(creds)
        self.assertIn("symlink", err)
        creds, err = self.load({"BG_AMO_CREDENTIALS": self.tmp})
        self.assertIsNone(creds)
        self.assertIn("not a regular file", err)
        self.assert_no_secret()

    def test_environment_first(self):
        path = self.write_creds(0o644)  # would be refused
        env = dict(self.key_env(), BG_AMO_CREDENTIALS=path)
        self.assertEqual(self.load(env), ((KEY, SECRET), None))
        creds, err = self.load({"WEB_EXT_API_KEY": KEY, "BG_AMO_CREDENTIALS": path})
        self.assertIn("set both", err)
        creds, err = self.load({"WEB_EXT_API_SECRET": SECRET, "BG_AMO_CREDENTIALS": path})
        self.assertIn("set both", err)
        self.assert_no_secret()

    def test_undecodable_env_value(self):
        bad = SECRET[:6] + "\udcff" + SECRET[6:]  # what os.environ makes of a byte that is not UTF-8
        creds, err = self.load({"WEB_EXT_API_KEY": KEY, "WEB_EXT_API_SECRET": bad})
        self.assertIsNone(creds)
        self.assertIn("printable ASCII", err)
        self.assertIn(bad, tool.REDACT.secrets)
        self.assertIn(KEY, tool.REDACT.secrets)
        code, line, err = self.run_in("sign", *self.common(), env={"WEB_EXT_API_KEY": KEY, "WEB_EXT_API_SECRET": bad})
        self.assertEqual(code, 1, err)
        self.assertIn("printable ASCII", err)
        self.assertNotIn("position", err)
        self.assertNotIn("udcff", err.lower())
        self.assertEqual(self.amo.requests, [])
        self.assertEqual(tool.Redactor()(bad), bad)  # sanity: the check above was not vacuous
        r = tool.Redactor()
        r.add(bad)
        self.assertEqual(r("x %s y" % bad), "x <redacted> y")
        self.assert_no_secret()

    def test_missing_and_incomplete(self):
        creds, err = self.load({"BG_AMO_CREDENTIALS": os.path.join(self.tmp, "none")})
        self.assertIn("no credentials", err)
        path = os.path.join(self.tmp, "half")
        self.cred_files.add(path)
        with open(path, "w", encoding="utf-8") as f:
            f.write("WEB_EXT_API_KEY=%s\n" % KEY)
        os.chmod(path, 0o600)
        creds, err = self.load({"BG_AMO_CREDENTIALS": path})
        self.assertIn("needs a WEB_EXT_API_KEY= line", err)
        self.assert_no_secret()

    def test_pack_and_verify_never_read_keys(self):
        path = self.write_creds(0o644)
        env = {"BG_AMO_CREDENTIALS": path}
        out = os.path.join(self.tmp, "p.xpi")
        code, line, err = self.run_sub("pack", *self.common("--out", out), env=env)
        self.assertEqual(code, 0, err)
        code, line, err = self.run_sub("verify", out, *self.common(), env=env)
        self.assertEqual(code, 1)  # unsigned, but no credential error
        self.assertNotIn("credentials", err)
        self.assertNotIn("0644", err)


class NoSecretTest(SignCompanionCase):

    def test_exceptions_are_redacted(self):
        token = tool.make_jwt(KEY, SECRET)
        message = "boom %s %s JWT %s %s" % (KEY, SECRET, token, "eyJhbGciOiJI.eyJpc3MiOiJ1c2VyOjEy.c2lnbmF0dXJlcw")
        for exc in (ValueError(message), RuntimeError(message), OSError(5, message),
                    tool.ToolError(message), KeyboardInterrupt(message)):
            with mock.patch.object(tool, "pack_bytes", side_effect=exc):
                code, line, err = self.run_in("sign", *self.common())
            self.assertEqual(code, 1)
            if not isinstance(exc, KeyboardInterrupt):
                self.assertIn("<redacted>", err)
            self.assertNotIn("Traceback", err)
            self.assertNotIn("eyJ", err)
            shutil.rmtree(self.state, ignore_errors=True)
        self.assertIn(token, tool.REDACT.secrets)
        self.assert_no_secret()

    def test_exception_text_from_the_client(self):
        self.amo.upload_code = 401
        amo = tool.Amo(self.amo.api, KEY, SECRET, 0.01, 1)
        with self.assertRaises(tool.ToolError) as cm:
            amo.upload(b"xpi")
        self.outputs.append(str(cm.exception))
        self.outputs.append(repr(cm.exception))
        self.amo.upload_code = 400
        with self.assertRaises(tool.ToolError) as cm:
            amo.upload(b"xpi")
        self.outputs.append(str(cm.exception))
        self.assertIn("<redacted>", str(cm.exception))
        self.assert_no_secret()

    def test_unreachable_server(self):
        port = self.amo.port
        self.amo.stop()
        code, line, err = self.run_sub("sign", "--api-url", "http://127.0.0.1:%d/api/v5/" % port,
                                       "--state", self.state, "--ext", self.ext, *FAST)
        self.assertEqual(code, 1)
        self.assertIn("URLError", err)
        self.assertNotIn("Traceback", err)
        self.assert_no_secret()

    def test_redactor(self):
        r = tool.Redactor()
        r.add("k3y")
        self.assertEqual(r("a k3y b"), "a <redacted> b")
        self.assertEqual(r("Authorization: JWT abc"), "Authorization: <redacted>")
        self.assertEqual(r("x aaaaaaaa.bbbbbbbbb.cccccccc y"), "x <redacted> y")
        self.assertEqual(r("version 1.2.90 of browserglass@companion"), "version 1.2.90 of browserglass@companion")


class PackVerifyTest(SignCompanionCase):

    def pack(self):
        out = os.path.join(self.tmp, "pack.xpi")
        code, line, err = self.run_sub("pack", *self.common("--out", out))
        self.assertEqual(code, 0, err)
        with open(out, "rb") as f:
            return f.read(), line

    def verify(self, data):
        path = os.path.join(self.tmp, "check.xpi")
        with open(path, "wb") as f:
            f.write(data)
        return self.run_in("verify", path, *self.common())

    def test_pack_is_companion_xpi(self):
        data, line = self.pack()
        self.assertEqual(data, bg.companion_xpi(self.ext))
        self.assertEqual(line["status"], "packed")
        self.assertEqual(line["version"], self.manifest_version())

    def test_pack_default_out(self):
        code, line, err = self.run_in("pack", *self.common())
        self.assertEqual(code, 0, err)
        self.assertEqual(line["xpi"], os.path.join(self.state, "build", "browserglass@companion-%s.xpi"
                                                   % self.manifest_version()))

    def test_verify_accepts_signed(self):
        plain = bg.companion_xpi(self.ext)
        code, line, err = self.verify(signed_xpi(plain))
        self.assertEqual(code, 0, err)
        self.assertEqual(line["status"], "verified")
        # COSE alone and PKCS7 alone are each a signature
        for keep in (("META-INF/cose.sig", "META-INF/cose.manifest"),
                     ("META-INF/mozilla.rsa", "META-INF/mozilla.sf", "META-INF/manifest.mf")):
            extra = {n: b"sig" for n in keep}
            code, line, err = self.verify(signed_xpi(plain, extra=extra, signature=False))
            self.assertEqual(code, 0, err)

    def test_verify_refuses(self):
        plain = bg.companion_xpi(self.ext)
        cases = {
            "differs": signed_xpi(plain, change="content.js"),
            "differs from the sources": signed_xpi(plain, change="manifest.json"),
            "extra entry": signed_xpi(plain, extra={"evil.js": b"x"}),
            "missing entry": signed_xpi(plain, drop="background.js"),
            "no Mozilla signature": signed_xpi(plain, signature=False),
            "no Mozilla signature ": signed_xpi(plain, signature=False, extra={"META-INF/cose.sig": b"s"}),
            "unsafe entry": signed_xpi(plain, extra={"../escape.js": b"x"}),
            "unsafe entry ": signed_xpi(plain, extra={"/abs.js": b"x"}),
            "not a zip": b"not a zip at all",
        }
        for want, data in cases.items():
            code, line, err = self.verify(data)
            self.assertEqual(code, 1, want)
            self.assertEqual(line["status"], "invalid", want)
            self.assertIn(want.strip(), err)

    def test_verify_size_limit(self):
        path = os.path.join(self.tmp, "big.xpi")
        with open(path, "wb") as f:
            f.truncate(tool.XPI_LIMIT + 1)
        code, line, err = self.run_in("verify", path, *self.common())
        self.assertEqual(code, 1)
        self.assertIn("larger than", err)

    def test_usage(self):
        for args in ([], ["bogus"], ["fetch"], ["fetch", "not-a-version"], ["sign", "--timeout", "x"],
                     ["sign", "--timeout", "-1"]):
            code, line, err = self.run_in(*args)
            self.assertEqual(code, 2, args)
            self.assertEqual(line["status"], "usage")
        self.assertEqual(self.amo.requests, [])

    def test_usage_error_redacts_env_keys(self):
        # web-ext habit: the keys typed as flags, which this tool does not take
        argv = ["sign", "--api-key", KEY, "--api-secret", SECRET]
        code, line, err = self.run_sub(*argv)
        self.assertEqual(code, 2, err)
        self.assertEqual(line["status"], "usage")
        self.assertIn("unrecognized arguments", err)
        self.assertIn("<redacted>", err)
        tool.REDACT.secrets.clear()
        code, line, err = self.run_in(*argv)
        self.assertEqual(code, 2, err)
        self.assertIn("<redacted>", err)
        self.assertEqual(self.amo.requests, [])
        self.assert_no_secret()

    def test_corrupt_entry_is_invalid(self):
        plain = bg.companion_xpi(self.ext)
        with zipfile.ZipFile(io.BytesIO(plain)) as zf:
            manifest = zf.read("manifest.json")
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(signed_xpi(plain))) as src, \
                zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            for name in src.namelist():
                zf.writestr(name, src.read(name))
        data = bytearray(buf.getvalue())
        at = data.find(manifest)
        self.assertGreater(at, 0)
        data[at + 10] ^= 0x01  # the CRC-32 no longer matches
        code, line, err = self.verify(bytes(data))
        self.assertEqual(code, 1, err)
        self.assertEqual(line["status"], "invalid")
        self.assertIn("verify: entry 'manifest.json' is corrupt", err)
        with self.assertRaises(ValueError):
            tool.read_zip_entries(bytes(data))

    def test_python39_syntax(self):
        for path in (TOOL, REPO / "tests" / "py" / "test_sign_companion.py"):
            with open(str(path), encoding="utf-8") as f:
                ast.parse(f.read(), str(path), feature_version=(3, 9))


if __name__ == "__main__":
    unittest.main()

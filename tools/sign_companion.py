#!/usr/bin/env python3
"""sign_companion - have addons.mozilla.org (AMO) sign the companion add-on.

Development tool, run by hand at release time. Like tools/update_styles.py it
may use the network; browserglass.py never does. The add-on is signed on the
unlisted channel (self-distributed, no public listing) through the AMO API v5.

    sign_companion.py pack   [options]
    sign_companion.py verify XPI [options]
    sign_companion.py sign   [options]
    sign_companion.py fetch  VERSION [options]

Options (after the subcommand): --api-url URL (default
https://addons.mozilla.org/api/v5/; plain http only to a loopback address),
--state DIR (default ~/.config/browserglass-amo/, outside the repository:
amo-versions.json, build/, signed/), --ext DIR (default <repo>/extension),
--out FILE, --poll-interval SECONDS (default 5), --timeout SECONDS (default
900, the cap of each wait).

pack: the xpi exactly as browserglass.py's companion_xpi() builds it (the
function is imported and called, never copied), written to --out (default
<state>/build/browserglass@companion-<version>.xpi).

verify XPI: every entry outside META-INF/ is byte for byte what
companion_xpi() packages from --ext (same names, no entry missing or extra;
directory entries are ignored), and a Mozilla signature is there:
META-INF/cose.sig + cose.manifest, or META-INF/mozilla.rsa + mozilla.sf +
manifest.mf.

sign: refuses a manifest version already recorded in <state>/amo-versions.json
or not greater than the largest one recorded (AMO consumes a version number
forever, even after a rejection, so the version is recorded before the upload
is sent). Then: upload (channel unlisted), wait for the validation, submit
the version with approval notes, wait until its file is public, download it
(redirects followed by hand, only to addons.mozilla.org, *.mozilla.net or the
--api-url host; the Authorization header goes only to the --api-url host and
addons.mozilla.org), verify it and write it to --out (default
<state>/signed/browserglass@companion-<version>.xpi).
Nothing is retried automatically: HTTP 409 means the version number is used,
429 means try later. When a wait ends without an answer, the AMO version id is
printed and "fetch VERSION" picks the signed file up later.

fetch VERSION: the end of sign for a version already submitted.

Credentials (sign and fetch only; pack and verify never read them), never on
the command line: the environment variables WEB_EXT_API_KEY and
WEB_EXT_API_SECRET, else the file ~/.config/browserglass-amo/credentials
($BG_AMO_CREDENTIALS names another file) with the lines
"WEB_EXT_API_KEY=user:..." and "WEB_EXT_API_SECRET=...". The file must be a
regular file (no symlink) owned by the user, mode 600 (no group or other bit).
The key and the secret are printable ASCII. The key, the secret and every
token are replaced with "<redacted>" in each message the tool prints, usage
errors included.

Output: one JSON line on stdout at the end, {"version", "xpi", "status",
"warnings"} (xpi: the path written, or null); diagnostics on stderr.
Exit status: 0 success, 1 failure, 2 usage error, 3 a wait timed out.
Python stdlib only, Python >= 3.9.
"""

import argparse
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
import zlib

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TOOLS_DIR)
DEFAULT_SCRIPT = os.path.join(REPO_DIR, "browserglass.py")
DEFAULT_EXT = os.path.join(REPO_DIR, "extension")
DEFAULT_API = "https://addons.mozilla.org/api/v5/"
STATE_REL = os.path.join(".config", "browserglass-amo")
CREDENTIALS_NAME = "credentials"
VERSIONS_FILE = "amo-versions.json"

ENV_KEY = "WEB_EXT_API_KEY"
ENV_SECRET = "WEB_EXT_API_SECRET"
ENV_CREDENTIALS = "BG_AMO_CREDENTIALS"

USER_AGENT = "browserglass-sign-companion"
JWT_LIFETIME = 60
HTTP_TIMEOUT = 60
POLL_INTERVAL = 5.0
WAIT_TIMEOUT = 15 * 60
MAX_REDIRECTS = 5
JSON_LIMIT = 4 * 1024 * 1024
XPI_LIMIT = 16 * 1024 * 1024
MANIFEST_LIMIT = 1024 * 1024
CREDENTIALS_LIMIT = 64 * 1024
MESSAGE_LIMIT = 300
MAX_MESSAGES = 50

UPLOAD_NAME = "browserglass@companion.xpi"
XPI_TYPE = "application/x-xpinstall"
CHANNEL = "unlisted"
AMO_HOST = "addons.mozilla.org"
MOZILLA_NET = ".mozilla.net"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
REDIRECT_CODES = (301, 302, 303, 307, 308)

SIGNATURE_SETS = (
    ("META-INF/cose.sig", "META-INF/cose.manifest"),
    ("META-INF/mozilla.rsa", "META-INF/mozilla.sf", "META-INF/manifest.mf"),
)

APPROVAL_NOTES = (
    "vendor/darkreader.js is Dark Reader 4.9.135, unmodified: it is identical to "
    "package/darkreader.js of https://registry.npmjs.org/darkreader/-/darkreader-4.9.135.tgz "
    "except for its line endings (LF instead of CRLF). "
    "The add-on only talks to its local native messaging host (browserglass); "
    "it makes no network request and collects no data."
)

STATUS_PUBLIC = "public"
STATUS_DISABLED = "disabled"

# no leading zeros: AMO refuses "1.04" after the version is already recorded;
# \Z, not $, which lets a final newline through
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]{0,8})(\.(0|[1-9][0-9]{0,8})){0,3}\Z")
_UPLOAD_ID_RE = re.compile(r"^[0-9A-Za-z-]{1,64}$")
_B64URL = r"[A-Za-z0-9_-]"
_JWT_RE = re.compile(r"JWT\s+\S+")
_TOKEN_RE = re.compile(r"%s{8,}\.%s{8,}\.%s{8,}" % (_B64URL, _B64URL, _B64URL))
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
REDACTED = "<redacted>"


# -- secret hygiene -----------------------------------------------------------

class Redactor:
    """Replaces the known secrets (and anything shaped like a JWT) with
    "<redacted>". Every text that leaves the tool goes through it."""

    def __init__(self):
        self.secrets = set()

    def add(self, value):
        if not value:
            return
        # surrogateescape: a value from os.environ may hold undecodable bytes
        forms = {value, urllib.parse.quote(value, safe="", errors="surrogateescape"),
                 urllib.parse.quote_plus(value, errors="surrogateescape"), json.dumps(value)[1:-1]}
        self.secrets.update(f for f in forms if f)

    def __call__(self, text):
        text = str(text)
        # longest first, so a secret holding another one goes as a whole
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        text = _JWT_RE.sub(REDACTED, text)
        return _TOKEN_RE.sub(REDACTED, text)


REDACT = Redactor()


def short(value, limit=MESSAGE_LIMIT):
    """`value` as one redacted line of at most `limit` characters."""
    text = _CONTROL_RE.sub(" ", REDACT(value)).strip()
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return REDACT(text)


def say(text):
    sys.stderr.write(short(text, limit=4 * MESSAGE_LIMIT) + "\n")
    sys.stderr.flush()


def emit(doc):
    sys.stdout.write(REDACT(json.dumps(doc, sort_keys=True)) + "\n")
    sys.stdout.flush()


class ToolError(Exception):
    """A failure told to the user (already safe to print)."""
    code = 1
    status = "failed"

    def __init__(self, message, status=None):
        super().__init__(short(message))
        if status is not None:
            self.status = status


class UsageError(ToolError):
    code = 2
    status = "usage"


class WaitTimeout(ToolError):
    code = 3
    status = "timeout"


# -- credentials --------------------------------------------------------------

def default_state(env):
    return os.path.join(env.get("HOME") or os.path.expanduser("~"), STATE_REL)


def credentials_path(env):
    return env.get(ENV_CREDENTIALS) or os.path.join(default_state(env), CREDENTIALS_NAME)


def _printable(value):
    return value.isascii() and value.isprintable()


def load_credentials(env):
    """(key, secret): from the environment, else from the credentials file,
    which must be a regular file of the user with mode 600. The messages name
    the path and the mode only, never a line of the file or a value."""
    key, secret = env.get(ENV_KEY), env.get(ENV_SECRET)
    REDACT.add(key)
    REDACT.add(secret)
    if key and secret:
        if not (_printable(key) and _printable(secret)):
            raise ToolError("%s and %s must be printable ASCII" % (ENV_KEY, ENV_SECRET))
        return key, secret
    if key or secret:
        raise ToolError("set both %s and %s, or neither" % (ENV_KEY, ENV_SECRET))
    path = credentials_path(env)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise ToolError("no credentials: set %s and %s, or write %s (mode 600)"
                        % (ENV_KEY, ENV_SECRET, path)) from None
    mode = stat.S_IMODE(st.st_mode)
    if stat.S_ISLNK(st.st_mode):
        raise ToolError("%s: refused, a symlink (mode %04o)" % (path, mode))
    if not stat.S_ISREG(st.st_mode):
        raise ToolError("%s: refused, not a regular file (mode %04o)" % (path, mode))
    if st.st_uid != os.getuid():
        raise ToolError("%s: refused, not owned by you (mode %04o)" % (path, mode))
    if mode & 0o077:
        raise ToolError("%s: refused, mode %04o (run: chmod 600 on it)" % (path, mode))
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NOCTTY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as f:
        now = os.fstat(f.fileno())
        if (now.st_dev, now.st_ino) != (st.st_dev, st.st_ino):
            raise ToolError("%s: refused, replaced while being read" % path)
        data = f.read(CREDENTIALS_LIMIT + 1)
    if len(data) > CREDENTIALS_LIMIT:
        raise ToolError("%s: refused, larger than %d bytes" % (path, CREDENTIALS_LIMIT))
    values = {}
    for line in data.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if name.strip() in (ENV_KEY, ENV_SECRET):
            values[name.strip()] = value
            REDACT.add(value)
    key, secret = values.get(ENV_KEY), values.get(ENV_SECRET)
    if not key or not secret:
        raise ToolError("%s: needs a %s= line and a %s= line" % (path, ENV_KEY, ENV_SECRET))
    if not (_printable(key) and _printable(secret)):
        raise ToolError("%s: the %s and %s values must be printable ASCII" % (path, ENV_KEY, ENV_SECRET))
    return key, secret


# -- JWT ----------------------------------------------------------------------

def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_jwt(key, secret, now=None):
    """A fresh HS256 token for AMO: iss = the key, a new uuid4 jti, iat now,
    exp = iat + 60. Registered with the redactor before it is returned."""
    iat = int(time.time() if now is None else now)
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {"iss": key, "jti": str(uuid.uuid4()), "iat": iat, "exp": iat + JWT_LIFETIME}
    signing = "%s.%s" % (b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
                         b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8")))
    digest = hmac.new(secret.encode("utf-8"), signing.encode("ascii"), hashlib.sha256).digest()
    token = signing + "." + b64url(digest)
    REDACT.add(token)
    return token


# -- the add-on ---------------------------------------------------------------

def load_script(path=DEFAULT_SCRIPT):
    """browserglass.py at `path` imported as a module, without bytecode."""
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("browserglass_for_sign_companion", path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load %s" % path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    if not callable(getattr(module, "companion_xpi", None)):
        raise ImportError("%s has no companion_xpi()" % path)
    return module


_SCRIPT = None


def pack_bytes(ext_dir):
    """The xpi bytes of `ext_dir`, from browserglass.py's companion_xpi()."""
    global _SCRIPT
    if _SCRIPT is None:
        _SCRIPT = load_script()
    return _SCRIPT.companion_xpi(ext_dir)


def parse_manifest(data, label):
    try:
        doc = json.loads(data.decode("utf-8"))
    except ValueError:
        raise ToolError("%s: manifest.json is not valid JSON" % label) from None
    if not isinstance(doc, dict):
        raise ToolError("%s: manifest.json is not an object" % label)
    version = doc.get("version")
    gecko = (doc.get("browser_specific_settings") or {}).get("gecko") or {}
    guid = gecko.get("id") if isinstance(gecko, dict) else None
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        raise ToolError("%s: manifest version is not dotted numbers" % label)
    if not isinstance(guid, str) or not re.match(r"^[A-Za-z0-9._@{}-]{1,80}$", guid):
        raise ToolError("%s: manifest has no usable gecko id" % label)
    return version, guid


def ext_manifest(ext_dir):
    """(version, gecko id) of the manifest.json in `ext_dir`."""
    path = os.path.join(ext_dir, "manifest.json")
    with open(path, "rb") as f:
        data = f.read(MANIFEST_LIMIT + 1)
    if len(data) > MANIFEST_LIMIT:
        raise ToolError("%s: larger than %d bytes" % (path, MANIFEST_LIMIT))
    return parse_manifest(data, path)


def version_key(version):
    parts = [int(p) for p in version.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _safe_name(name):
    return not (not name or name.startswith("/") or "\\" in name or "\x00" in name
                or ".." in name.split("/") or re.match(r"^[A-Za-z]:", name))


def read_zip_entries(data):
    """{name: bytes} of the file entries of the zip `data` (directory
    entries left out). ValueError on an unsafe or duplicate name, an
    oversized content or a corrupt entry."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("not a zip file") from None
    out = {}
    total = 0
    with zf:
        for info in zf.infolist():
            name = info.filename
            if not _safe_name(name):
                raise ValueError("unsafe entry name %r" % name[:80])
            if name.endswith("/"):
                if info.file_size:
                    raise ValueError("directory entry %r has content" % name[:80])
                continue
            if name in out:
                raise ValueError("duplicate entry %r" % name[:80])
            total += info.file_size
            if info.file_size > XPI_LIMIT or total > XPI_LIMIT:
                raise ValueError("contents larger than %d bytes" % XPI_LIMIT)
            try:
                with zf.open(info) as f:
                    body = f.read(XPI_LIMIT + 1)
            except (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, EOFError):
                raise ValueError("entry %r is corrupt" % name[:80]) from None
            if len(body) != info.file_size:
                raise ValueError("entry %r has a wrong size" % name[:80])
            out[name] = body
    return out


def verify_bytes(data, ext_dir):
    """Problems found in the signed xpi `data` against the sources of
    `ext_dir` ([] when it is the add-on, signed)."""
    if len(data) > XPI_LIMIT:
        return ["xpi larger than %d bytes" % XPI_LIMIT]
    try:
        got = read_zip_entries(data)
        want = read_zip_entries(pack_bytes(ext_dir))
    except ValueError as exc:
        return [str(exc)]
    problems = []
    content = {n: b for n, b in got.items() if not n.startswith("META-INF/")}
    for name in sorted(set(want) - set(content)):
        problems.append("missing entry %s" % name)
    for name in sorted(set(content) - set(want)):
        problems.append("extra entry %s" % name[:80])
    for name in sorted(set(want) & set(content)):
        if content[name] != want[name]:
            problems.append("entry %s differs from the sources" % name)
    if not any(all(n in got for n in names) for names in SIGNATURE_SETS):
        problems.append("no Mozilla signature (META-INF/cose.* or META-INF/mozilla.*)")
    return problems


def read_xpi(path):
    st = os.stat(path)
    if not stat.S_ISREG(st.st_mode):
        raise ToolError("%s: not a regular file" % path)
    if st.st_size > XPI_LIMIT:
        raise ToolError("%s: larger than %d bytes" % (path, XPI_LIMIT))
    with open(path, "rb") as f:
        data = f.read(XPI_LIMIT + 1)
    if len(data) > XPI_LIMIT:
        raise ToolError("%s: larger than %d bytes" % (path, XPI_LIMIT))
    return data


def write_atomic(path, data, mode=0o644):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- versions sent to AMO -----------------------------------------------------

def read_versions(state):
    path = os.path.join(state, VERSIONS_FILE)
    try:
        with open(path, "rb") as f:
            data = f.read(JSON_LIMIT + 1)
    except FileNotFoundError:
        return []
    try:
        doc = json.loads(data.decode("utf-8"))
        versions = doc["versions"]
        if not isinstance(versions, list) or not all(
                isinstance(v, str) and _VERSION_RE.match(v) for v in versions):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise ToolError("%s is unreadable: fix it by hand (it lists the versions sent to AMO)"
                        % path) from None
    return versions


def check_version(state, version):
    """Refuses `version` when AMO may already have it."""
    versions = read_versions(state)
    if version in versions:
        raise ToolError("version %s was already sent to AMO (%s): bump the manifest version"
                        % (version, VERSIONS_FILE), status="refused")
    if versions:
        top = max(versions, key=version_key)
        if version_key(version) <= version_key(top):
            raise ToolError("version %s is not greater than %s, the last one sent to AMO"
                            % (version, top), status="refused")


def record_version(state, version):
    versions = read_versions(state) + [version]
    data = (json.dumps({"versions": versions}, indent=2) + "\n").encode("utf-8")
    write_atomic(os.path.join(state, VERSIONS_FILE), data, mode=0o600)


# -- AMO ----------------------------------------------------------------------

class _Passthrough(urllib.request.HTTPErrorProcessor):
    """Every response goes back to the caller: no HTTPError, and so no
    automatic redirect (the caller follows them, keeping its header)."""

    def http_response(self, request, response):
        return response

    https_response = http_response


def _port(parts):
    port = parts.port
    if port is None:
        port = {"http": 80, "https": 443}.get(parts.scheme)
    return port


def check_api_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        _port(parts)
    except ValueError:
        raise UsageError("--api-url: not a URL") from None
    host = (parts.hostname or "").lower()
    if parts.username or parts.password or not host or parts.query or parts.fragment:
        raise UsageError("--api-url: give scheme, host and path only")
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOOPBACK_HOSTS):
        return url if url.endswith("/") else url + "/"
    raise UsageError("--api-url: https only (http to a loopback address for tests)")


def shown_url(url):
    """`url` without its query, fragment and user info, for messages."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
        if ":" in host:
            host = "[%s]" % host
        if parts.port:
            host += ":%d" % parts.port
    except ValueError:
        return "<bad URL>"
    return "%s://%s%s" % (parts.scheme, host, parts.path)


def download_allowed(url, api_url):
    """True for https://addons.mozilla.org, https://*.mozilla.net and the
    scheme, host and port of `api_url`."""
    try:
        parts = urllib.parse.urlsplit(url)
        api = urllib.parse.urlsplit(api_url)
        if parts.username or parts.password:
            return False
        host = (parts.hostname or "").lower()
        if host and (parts.scheme, host, _port(parts)) == (api.scheme, (api.hostname or "").lower(), _port(api)):
            return True
    except ValueError:
        return False
    return parts.scheme == "https" and (host == AMO_HOST or host.endswith(MOZILLA_NET))


def auth_allowed(url, api_url):
    """True when `url` may get the Authorization header: the scheme, host
    and port of `api_url`, or https://addons.mozilla.org. A CDN host gets no
    token, even when download_allowed() accepts it."""
    try:
        parts = urllib.parse.urlsplit(url)
        api = urllib.parse.urlsplit(api_url)
        host = (parts.hostname or "").lower()
        if parts.username or parts.password or not host:
            return False
        if (parts.scheme, host, _port(parts)) == (api.scheme, (api.hostname or "").lower(), _port(api)):
            return True
        return parts.scheme == "https" and host == AMO_HOST and _port(parts) == 443
    except ValueError:
        return False


def multipart(fields, files):
    """(body, content type) of a multipart/form-data request: `fields`
    [(name, text)], `files` [(name, filename, content type, bytes)]."""
    blobs = [data for _, _, _, data in files]
    while True:
        boundary = "----browserglass" + uuid.uuid4().hex
        if not any(boundary.encode("ascii") in b for b in blobs):
            break
    out = []
    for name, value in fields:
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n"
                    % (boundary, name)).encode("ascii"))
        out.append(value.encode("utf-8") + b"\r\n")
    for name, filename, ctype, data in files:
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                    "Content-Type: %s\r\n\r\n" % (boundary, name, filename, ctype)).encode("ascii"))
        out.append(data + b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("ascii"))
    return b"".join(out), "multipart/form-data; boundary=%s" % boundary


def _first_message(value, depth=0):
    """The first text of a decoded error body: "detail" first, then the
    values in order, nested dicts and lists included (AMO's nested
    serializers answer {"version": {"version": ["..."]}})."""
    if isinstance(value, str):
        return value
    if depth >= 6:
        return ""
    if isinstance(value, dict):
        items = ([value["detail"]] if "detail" in value else []) + [
            v for k, v in value.items() if k != "detail"]
    elif isinstance(value, list):
        items = value
    else:
        return ""
    for item in items:
        text = _first_message(item, depth + 1)
        if text:
            return text
    return ""


def _detail(body):
    """The "detail" (or first error) of an AMO error body, redacted."""
    try:
        doc = json.loads(body.decode("utf-8"))
    except ValueError:
        return ""
    text = _first_message(doc)
    return short(text, 200) if text else ""


class Amo:
    """The AMO API v5 calls the tool makes. Each request carries a fresh
    JWT; responses are read with a size limit."""

    def __init__(self, api_url, key, secret, poll_interval=POLL_INTERVAL, timeout=WAIT_TIMEOUT):
        self.api = check_api_url(api_url)
        self.key = key
        self.secret = secret
        self.poll_interval = poll_interval
        self.timeout = timeout
        REDACT.add(key)
        REDACT.add(secret)
        self.opener = urllib.request.build_opener(_Passthrough)

    def url(self, *parts):
        return self.api + "/".join(urllib.parse.quote(p, safe="@{}") for p in parts) + "/"

    def send(self, method, url, data=None, content_type=None, limit=JSON_LIMIT):
        """(status, body, Location) of one request; never follows a redirect.
        A fresh token goes only to auth_allowed() hosts."""
        headers = {"User-Agent": USER_AGENT}
        if auth_allowed(url, self.api):
            headers["Authorization"] = "JWT " + make_jwt(self.key, self.secret)
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with self.opener.open(req, timeout=HTTP_TIMEOUT) as resp:
            status = resp.status
            location = resp.headers.get("Location")
            body = resp.read(limit + 1)
        if len(body) > limit:
            raise ToolError("%s: answer larger than %d bytes" % (shown_url(url), limit))
        return status, body, location

    def check(self, status, body, what):
        if 200 <= status < 300:
            return
        detail = _detail(body)
        if status in (401, 403):
            raise ToolError("%s: authentication refused (HTTP %d)" % (what, status))
        if status == 409 or (status == 400 and re.search(r"already exists|uploaded before", detail, re.I)):
            raise ToolError("%s: version already used on AMO (HTTP %d): bump the manifest version"
                            % (what, status), status="refused")
        if status == 429:
            raise ToolError("%s: rate limited, try later (HTTP 429)" % what)
        raise ToolError("%s: HTTP %d%s" % (what, status, (": " + detail) if detail else ""))

    def json_call(self, method, url, what, data=None, content_type=None):
        status, body, _ = self.send(method, url, data, content_type)
        self.check(status, body, what)
        try:
            doc = json.loads(body.decode("utf-8"))
        except ValueError:
            raise ToolError("%s: the answer is not JSON" % what) from None
        if not isinstance(doc, dict):
            raise ToolError("%s: the answer is not a JSON object" % what)
        return doc

    def upload(self, xpi):
        body, ctype = multipart([("channel", CHANNEL)], [("upload", UPLOAD_NAME, XPI_TYPE, xpi)])
        doc = self.json_call("POST", self.url("addons", "upload"), "upload", body, ctype)
        upload_id = doc.get("uuid")
        if not isinstance(upload_id, str) or not _UPLOAD_ID_RE.match(upload_id):
            raise ToolError("upload: no upload id in the answer")
        return upload_id, doc

    def wait(self, fetch, done, what):
        """Calls fetch() every poll interval until done(doc), up to the cap."""
        deadline = time.monotonic() + self.timeout
        while True:
            doc = fetch()
            if done(doc):
                return doc
            if time.monotonic() + self.poll_interval > deadline:
                raise WaitTimeout("%s: no answer after %d s" % (what, self.timeout))
            time.sleep(self.poll_interval)

    def validation(self, upload_id, doc):
        """The upload's answer once AMO has processed it."""
        if doc.get("processed") is True:
            return doc
        url = self.url("addons", "upload", upload_id)
        return self.wait(lambda: self.json_call("GET", url, "validation"),
                         lambda d: d.get("processed") is True, "validation of upload %s" % upload_id)

    def submit(self, guid, upload_id):
        payload = {"version": {"upload": upload_id, "approval_notes": APPROVAL_NOTES}}
        return self.json_call("PUT", self.url("addons", "addon", guid), "submit",
                              json.dumps(payload).encode("utf-8"), "application/json")

    def version(self, guid, ref):
        return self.json_call("GET", self.url("addons", "addon", guid, "versions", ref), "version")

    def download(self, url):
        for _ in range(MAX_REDIRECTS + 1):
            if not download_allowed(url, self.api):
                raise ToolError("download from %s refused (not AMO)" % shown_url(url))
            status, body, location = self.send("GET", url, limit=XPI_LIMIT)
            if status in REDIRECT_CODES:
                if not location:
                    raise ToolError("download: redirect without a location")
                url = urllib.parse.urljoin(url, location)
                continue
            self.check(status, body, "download")
            return body
        raise ToolError("download: more than %d redirects" % MAX_REDIRECTS)


def file_status(doc):
    f = doc.get("file") if isinstance(doc.get("file"), dict) else {}
    return f.get("status"), f.get("url")


def report_validation(doc):
    """Counts and message titles of an upload's validation; the warning count."""
    v = doc.get("validation") if isinstance(doc.get("validation"), dict) else {}
    counts = {k: v.get(k) if isinstance(v.get(k), int) else 0 for k in ("errors", "warnings", "notices")}
    say("validation: %(errors)d errors, %(warnings)d warnings, %(notices)d notices" % counts)
    messages = v.get("messages") if isinstance(v.get("messages"), list) else []
    for m in messages[:MAX_MESSAGES]:
        if not isinstance(m, dict):
            continue
        where = m.get("file")
        say("  %s: %s%s" % (short(m.get("type", "?"), 20), short(m.get("message", ""), 200),
                            (" (%s)" % short(where, 120)) if isinstance(where, str) and where else ""))
    if len(messages) > MAX_MESSAGES:
        say("  ... %d more" % (len(messages) - MAX_MESSAGES))
    return counts["warnings"]


def finish(amo, guid, doc, version, ext_dir, out, result):
    """Waits until the version `doc` is public, downloads, verifies and
    writes its file."""
    vid = doc.get("id")
    if not isinstance(vid, int):
        raise ToolError("no AMO version id in the answer")
    say("AMO version id %d (%s)" % (vid, version))

    def done(d):
        status = file_status(d)[0]
        if status == STATUS_DISABLED or d.get("is_disabled") is True:
            raise ToolError("version %s was rejected by AMO (file %s)" % (version, status),
                            status="rejected")
        return status == STATUS_PUBLIC

    try:
        doc = amo.wait(lambda: amo.version(guid, str(vid)), done, "approval")
    except WaitTimeout:
        say("AMO version id %d is not public yet; run later: "
            "python3 -I -B tools/sign_companion.py fetch %s" % (vid, version))
        raise WaitTimeout("version %s (AMO id %d) not public after %d s" % (version, vid, amo.timeout))
    url = file_status(doc)[1]
    if not isinstance(url, str) or not url:
        raise ToolError("version %s is public but has no file URL" % version)
    data = amo.download(url)
    problems = verify_bytes(data, ext_dir)
    if problems:
        for p in problems:
            say("verify: " + p)
        raise ToolError("the signed file does not match the sources of %s" % ext_dir, status="invalid")
    write_atomic(out, data)
    result.update(xpi=out, status=STATUS_PUBLIC)
    say("signed xpi written to %s" % out)


# -- commands -----------------------------------------------------------------

def default_out(args, kind, version):
    return args.out or os.path.join(args.state, kind, "browserglass@companion-%s.xpi" % version)


def cmd_pack(args, env, result):
    version, _ = ext_manifest(args.ext)
    result["version"] = version
    data = pack_bytes(args.ext)
    out = default_out(args, "build", version)
    write_atomic(out, data)
    result.update(xpi=out, status="packed")
    say("%d bytes written to %s" % (len(data), out))
    return 0


def cmd_verify(args, env, result):
    result["xpi"] = args.xpi
    data = read_xpi(args.xpi)
    try:
        entries = read_zip_entries(data)
        if "manifest.json" in entries:
            result["version"] = parse_manifest(entries["manifest.json"], args.xpi)[0]
    except (ValueError, ToolError):
        pass
    problems = verify_bytes(data, args.ext)
    for p in problems:
        say("verify: " + p)
    if problems:
        result["status"] = "invalid"
        return 1
    result["status"] = "verified"
    say("%s: the add-on of %s, signed" % (args.xpi, args.ext))
    return 0


def make_amo(args, env):
    key, secret = load_credentials(env)
    return Amo(args.api_url, key, secret, args.poll_interval, args.timeout)


def cmd_sign(args, env, result):
    version, guid = ext_manifest(args.ext)
    result["version"] = version
    amo = make_amo(args, env)
    check_version(args.state, version)
    xpi = pack_bytes(args.ext)
    out = default_out(args, "signed", version)
    record_version(args.state, version)
    say("version %s recorded in %s" % (version, os.path.join(args.state, VERSIONS_FILE)))
    upload_id, doc = amo.upload(xpi)
    say("upload %s sent (%d bytes, channel %s)" % (upload_id, len(xpi), CHANNEL))
    try:
        doc = amo.validation(upload_id, doc)
    except WaitTimeout:
        raise WaitTimeout("validation of upload %s not finished after %d s; the version number "
                          "is recorded, sign again with the next one" % (upload_id, amo.timeout))
    result["warnings"] = report_validation(doc)
    if doc.get("valid") is not True:
        raise ToolError("validation failed: upload %s refused by AMO" % upload_id, status="rejected")
    created = amo.submit(guid, upload_id)
    vdoc = created.get("version") if isinstance(created.get("version"), dict) else None
    if not vdoc or not isinstance(vdoc.get("id"), int):
        vdoc = amo.version(guid, "v" + version)
    finish(amo, guid, vdoc, version, args.ext, out, result)
    return 0


def cmd_fetch(args, env, result):
    if not _VERSION_RE.match(args.version):
        raise UsageError("fetch: the version is dotted numbers (like 1.3.0)")
    result["version"] = args.version
    _, guid = ext_manifest(args.ext)
    amo = make_amo(args, env)
    doc = amo.version(guid, "v" + args.version)
    finish(amo, guid, doc, args.version, args.ext, default_out(args, "signed", args.version), result)
    return 0


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError("%s: %s" % (self.prog, message))


def build_parser(env):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--api-url", default=DEFAULT_API)
    common.add_argument("--state", default=default_state(env))
    common.add_argument("--ext", default=DEFAULT_EXT)
    common.add_argument("--out", default=None)
    common.add_argument("--poll-interval", type=float, default=POLL_INTERVAL)
    common.add_argument("--timeout", type=float, default=WAIT_TIMEOUT)
    parser = _Parser(prog="sign_companion.py",
                     description="Have AMO sign the Browser Glass companion add-on.")
    sub = parser.add_subparsers(dest="cmd", parser_class=_Parser)
    sub.add_parser("pack", parents=[common], help="build the xpi")
    p = sub.add_parser("verify", parents=[common], help="check a signed xpi against the sources")
    p.add_argument("xpi")
    sub.add_parser("sign", parents=[common], help="upload, wait, download the signed xpi")
    p = sub.add_parser("fetch", parents=[common], help="download the signed xpi of a version sent before")
    p.add_argument("version")
    return parser


COMMANDS = {"pack": cmd_pack, "verify": cmd_verify, "sign": cmd_sign, "fetch": cmd_fetch}


def main(argv=None, env=None):
    env = os.environ if env is None else env
    result = {"version": None, "xpi": None, "status": "failed", "warnings": None}
    code = 1
    try:
        # before the parser: a usage error echoes argv, which may hold them
        REDACT.add(env.get(ENV_KEY))
        REDACT.add(env.get(ENV_SECRET))
        args = build_parser(env).parse_args(argv)
        if args.cmd not in COMMANDS:
            raise UsageError("sign_companion.py: give a subcommand: pack, verify, sign or fetch")
        if not (args.poll_interval >= 0 and args.timeout >= 0):
            raise UsageError("--poll-interval and --timeout are seconds, not negative")
        args.state = os.path.abspath(os.path.expanduser(args.state))
        args.ext = os.path.abspath(args.ext)
        if args.out:
            args.out = os.path.abspath(args.out)
        code = COMMANDS[args.cmd](args, env, result)
    except ToolError as exc:
        say("error: %s" % exc)
        result["status"] = exc.status
        code = exc.code
    except urllib.error.URLError as exc:
        say("error: URLError: %s" % short(exc.reason, 120))
    except (OSError, ValueError, zipfile.BadZipFile, ImportError) as exc:
        say("error: %s: %s" % (type(exc).__name__, short(exc, 200)))
    except KeyboardInterrupt:
        say("error: interrupted")
    except Exception as exc:  # no traceback: it could hold a request
        say("error: unexpected %s: %s" % (type(exc).__name__, short(exc, 200)))
    emit(result)
    return code


if __name__ == "__main__":
    sys.exit(main())

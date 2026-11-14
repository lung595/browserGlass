#!/usr/bin/env python3
"""browserglass - single-file backend of the DMS plugin browserGlass.

Applies the DMS "glass" look (translucent tinted background, opaque text,
images and videos) to Firefox-family browsers (Firefox, LibreWolf, Zen,
Floorp, Waterfox; native, Flatpak and Snap) under niri.

Commands (one JSON line on stdout unless stated otherwise; the frozen output
contract is tests/fixtures/contract/schema.json, an error is {"error": "..."}
with exit status 1, or 2 for a usage error):
  sync --settings JSON [--data DIR] [--profile DIR]... [--opacity X] [--off]
       [--if-plugin FILE]       (--if-plugin: refused with a "plugin_gone:"
                                error, nothing written, when FILE, the
                                daemon's plugin.json, is missing)
  status --json
  uninstall [--if-gone FILE]    (--if-gone: waits $BG_SWEEP_GRACE seconds, then
                                exits 3, printing nothing, if FILE exists again)
  clean-prefs PROFILE...        (internal: waits for the browser, cleans prefs.js;
                                prints nothing, exit 0)
  report                        (anonymous plain text)
  sites --json [--data DIR]

Constraints: Python stdlib only, Python >= 3.9, run as `python3 -I`.
The file never refers to its own location (no module path lookup): the uninstaller
must also work from this text alone, with no file next to it. The text goes
on stdin of `python3 -I -c "<STDIN_BOOTSTRAP>" uninstall` (it is larger than
the 128 KiB Linux allows for one argv string). Data files are passed
explicitly with --data.
"""

import argparse
import collections
import copy
import errno
import fcntl
import hashlib
import json
import math
import os
import pwd
import re
import shutil
import stat
import struct
import sys
import tempfile
import time
import unicodedata

# ============================================================================
# consts
# ============================================================================

VERSION = "1.0.0"
PLUGIN_ID = "browserGlass"
PROG = "browserglass"
# Runs this file's text read from stdin (`python3 -I -c STDIN_BOOTSTRAP
# uninstall`): the uninstaller then needs no file at all, whatever the size
# of the text (one argv string is capped at 128 KiB, MAX_ARG_STRLEN).
STDIN_BOOTSTRAP = "import sys; exec(compile(sys.stdin.read(), 'browserglass', 'exec'))"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_KEPT = 3  # uninstall --if-gone: the file is back, nothing was done

# ---- File and directory names ----------------------------------------------
# Profile side (relative to a profile directory).
CHROME_DIR = "chrome"
USERCHROME_CSS = "userChrome.css"
USERCONTENT_CSS = "userContent.css"
USER_JS = "user.js"
PREFS_JS = "prefs.js"
PROFILES_INI = "profiles.ini"
PARENT_LOCK = ".parentlock"
LOCK_LINK = "lock"
ZEN_THEMES_JSON = "zen-themes.json"  # Zen's mod registry (H9), see ZEN_MOD_FILES
# Generated stylesheets (same names in v0 and v1, see rule 1 of the plan).
CHROME_CSS_NAME = "dms-glass-chrome.css"
CONTENT_CSS_NAME = "dms-glass-content.css"

# niri side (relative to $XDG_CONFIG_HOME, default ~/.config).
NIRI_DIR_REL = "niri"
NIRI_CONFIG_NAME = "config.kdl"
NIRI_OUT_NAME = "dms-browser-glass.kdl"
DMS_RULES_REL = "niri/dms/windowrules.kdl"   # read only, never written (rule 8)
DMS_FIREFOX_CSS_REL = "dms/firefox.css"      # DMS file, never touched (rule 8)
DMS_PLUGIN_SETTINGS_REL = "dms/plugin_settings.json"

# DMS colors (relative to $XDG_CACHE_HOME, default ~/.cache).
# Keys: "mode" ("dark" | "light"), "colors" -> {"dark": {...}, "light": {...}},
# the tint is colors[mode]["surface"].
DMS_COLORS_REL = "dms/dms-colors.json"
DEFAULT_SURFACE = "#101418"  # v0 fallback when dms-colors.json is unreadable
# Tint used when the surface colour is unusable, per DMS mode (the dark one
# is v0's fallback).
DEFAULT_SURFACES = {"dark": DEFAULT_SURFACE, "light": "#f7f9ff"}

# v1 state (relative to $XDG_STATE_HOME, default ~/.local/state).
STATE_DIR_REL = "dms/browserGlass"
STATE_FILE = "state.json"
STATE_LOCK = "state.lock"
BACKUP_DIR = "backup"  # backup/<profile-hash>/{userChrome.css,userContent.css,user.js}

# ---- v0 markers (byte-exact copies of what v0 wrote; do not "fix") ---------
# Non-ASCII characters are written as escapes so this file stays pure ASCII
# and survives being fed to `python3 -I -c STDIN_BOOTSTRAP` under any locale.
# Encoded as UTF-8 they are byte-identical to the strings in v0
# browser-glass-sync / browser-glass-sites (checked by tests/py/test_contract.py).

# v0 cache of the my-internet styles (relative to $XDG_CACHE_HOME); removed
# by uninstall. Files inside: styles.json, css-mapping.json, .fetched
V0_CACHE_REL = "dms/browserGlass"
V0_CACHE_FILES = ("styles.json", "css-mapping.json", ".fetched")

# userChrome.css / userContent.css: v0 prepended this exact line at the top.
V0_IMPORT_CHROME = '@import "dms-glass-chrome.css";'
V0_IMPORT_CONTENT = '@import "dms-glass-content.css";'

# niri config.kdl: v0 appended "\n" + this line + "\n" at the end.
V0_NIRI_INCLUDE = 'include optional=true "dms-browser-glass.kdl"'

# user.js: v0 managed block (whole lines, compared with ==).
V0_USERJS_BEGIN = "// >>> dms-browser-glass (g\u00e9n\u00e9r\u00e9, ne pas \u00e9diter)"
V0_USERJS_END = "// <<< dms-browser-glass"
# The block v0 appended at the end of user.js (after stripping an older one).
# transparent: "true" | "false" ; scheme: "0" (dark) | "1" (light).
V0_USERJS_BLOCK_TEMPLATE = (
    V0_USERJS_BEGIN + "\n"
    'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);\n'
    'user_pref("browser.tabs.allow_transparent_browser", {transparent});\n'
    'user_pref("layout.css.prefers-color-scheme.content-override", {scheme});\n'
    + V0_USERJS_END + "\n"
)

# First line of the generated v0 CSS files. {opacity} is the raw text of the
# opacity value read from windowrules.kdl (e.g. "0.85").
V0_CSS_HEADER_GLASS = "/* G\u00e9n\u00e9r\u00e9 par browser-glass-sync \u2014 opacit\u00e9 DMS {opacity} */"
V0_CSS_HEADER_PAGES_OFF = (
    "/* G\u00e9n\u00e9r\u00e9 par browser-glass-sync \u2014 transparence des pages "
    "d\u00e9sactiv\u00e9e */"
)
V0_CSS_HEADER_GLASS_OFF = (
    "/* G\u00e9n\u00e9r\u00e9 par browser-glass-sync \u2014 verre d\u00e9sactiv\u00e9 "
    "(blur DMS off ou opacit\u00e9 1) */"
)
V0_CSS_HEADERS = (V0_CSS_HEADER_GLASS, V0_CSS_HEADER_PAGES_OFF, V0_CSS_HEADER_GLASS_OFF)
# Second line of the v0 content CSS when pages were transparent.
V0_CONTENT_CSS_NOTE = (
    "/* Fond des pages transparent (la teinte DMS est derri\u00e8re) ; images, "
    "vid\u00e9os et texte restent opaques. */"
)
# Comments written by v0 browser-glass-sites build (appended to the content CSS).
V0_SITES_HEADER = (
    "/* Styles par site : sameerasw/my-internet (MIT) \u2014 g\u00e9n\u00e9r\u00e9, "
    "ne pas \u00e9diter */"
)
V0_SITES_GENERIC_COMMENT = "/* Autres sites : style g\u00e9n\u00e9rique (example.com.css) */"
V0_SITES_MAPPING_COMMENT_TEMPLATE = "/* {src} (mapping) */"

# Whole content of the v0 niri file ($XDG_CONFIG_HOME/niri/dms-browser-glass.kdl).
V0_NIRI_KDL = (
    "// G\u00e9n\u00e9r\u00e9 par le plugin DMS browserGlass \u2014 ne pas \u00e9diter.\n"
    "// Les navigateurs Firefox-like dessinent leur propre transparence (fonds en verre,\n"
    "// vid\u00e9os et texte opaques) : niri ne doit pas att\u00e9nuer toute la fen\u00eatre.\n"
    "window-rule {\n"
    '    match app-id=r#"^(firefox|firefox-esr|librewolf|zen|zen-browser|zen-beta|floorp|'
    "waterfox|org\\.mozilla\\.firefox|io\\.gitlab\\.librewolf-community|"
    'app\\.zen_browser\\.zen)$"#\n'
    "    opacity 1.0\n"
    "}\n"
)

# v0 plugin settings keys (pluginData) that v1 migrates (H4).
V0_SETTING_PAGES = "pagesTransparent"   # bool, kept as is (master switch)
V0_SETTING_EXCLUDED = "excludedSites"   # [{"domain": "example.org"}], kept as is

# v0 profile roots, in v0 order. base "config" = $XDG_CONFIG_HOME, "home" = $HOME.
V0_ROOTS = (
    ("config", "mozilla/firefox"),
    ("home", ".mozilla/firefox"),
    ("config", "librewolf/librewolf"),
    ("home", ".librewolf"),
    ("config", "zen"),
    ("home", ".zen"),
    ("home", ".floorp"),
    ("home", ".waterfox"),
    ("home", ".var/app/org.mozilla.firefox/.mozilla/firefox"),
    ("home", ".var/app/org.mozilla.firefox/config/mozilla/firefox"),
    ("home", ".var/app/io.gitlab.librewolf-community/.librewolf"),
    ("home", ".var/app/app.zen_browser.zen/.zen"),
)

# ---- v1 markers (new, ASCII, distinct from every v0 marker) ----------------
V1_USERJS_BEGIN = "// >>> browserGlass v1 managed block (generated, do not edit)"
V1_USERJS_END = "// <<< browserGlass v1"
V1_CSS_HEADER = "/* browserGlass v1: generated file, do not edit */"
V1_NIRI_HEADER = "// browserGlass v1: generated by the DMS plugin browserGlass, do not edit."
# Import and include lines are deliberately identical to v0: they name only
# our own file, are already ASCII, and keeping them lets a v1 sync on a v0
# install leave userChrome.css, userContent.css and config.kdl untouched (H4).
V1_IMPORT_CHROME = V0_IMPORT_CHROME
V1_IMPORT_CONTENT = V0_IMPORT_CONTENT
V1_NIRI_INCLUDE = V0_NIRI_INCLUDE

# All markers recognised by uninstall (v0 and v1).
USERJS_BLOCK_MARKERS = (
    (V0_USERJS_BEGIN, V0_USERJS_END),
    (V1_USERJS_BEGIN, V1_USERJS_END),
)
IMPORT_LINES = {
    CHROME_CSS_NAME: (V1_IMPORT_CHROME,),
    CONTENT_CSS_NAME: (V1_IMPORT_CONTENT,),
}
NIRI_INCLUDE_LINES = (V1_NIRI_INCLUDE,)

# ---- Prefs (H2, H3) ---------------------------------------------------------
PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_COLOR_SCHEME = "layout.css.prefers-color-scheme.content-override"
# Prefs whose original prefs.js value is recorded in the state on first
# contact and restored on uninstall (instead of deleting the line).
PREFS = (PREF_STYLESHEETS, PREF_TRANSPARENT, PREF_COLOR_SCHEME)
# Values v0 could have written (JS literal text). Without a v1 state, uninstall
# only removes prefs.js lines carrying one of these values (H2).
V0_PREF_VALUES = {
    PREF_STYLESHEETS: ("true",),
    PREF_TRANSPARENT: ("true", "false"),
    PREF_COLOR_SCHEME: ("0", "1"),
}
# layout.css.prefers-color-scheme.content-override values.
COLOR_SCHEME_DARK = 0
COLOR_SCHEME_LIGHT = 1

# ---- Browser families, profile roots (H8) and niri app-ids (H7) ------------
FAMILIES = ("firefox", "librewolf", "zen", "floorp", "waterfox")
FAMILY_LABELS = {
    "firefox": "Firefox",
    "librewolf": "LibreWolf",
    "zen": "Zen",
    "floorp": "Floorp",
    "waterfox": "Waterfox",
}
VARIANTS = ("native", "flatpak", "snap")

# base: "home" ($HOME) or "config" ($XDG_CONFIG_HOME, default $HOME/.config;
# Firefox >= 147 and v0 both honour XDG_CONFIG_HOME). rel is relative to base.
# Convention for the XDG layouts (H8): every app gets its legacy dot-dir AND
# an XDG directory. Where the native XDG layout is known (mozilla/firefox,
# librewolf/librewolf, zen) the Flatpak sandbox gets the same path under
# config/; elsewhere, and in addition for LibreWolf, the literal plan variant
# config/<family> is listed. The XDG layouts of Floorp, Waterfox and Snap
# could not be verified offline; a root that does not exist costs nothing,
# and a root reached twice (symlink) is walked once.
Root = collections.namedtuple("Root", "base rel family variant")
ROOTS = (
    # native
    Root("config", "mozilla/firefox", "firefox", "native"),
    Root("home", ".mozilla/firefox", "firefox", "native"),
    Root("config", "librewolf/librewolf", "librewolf", "native"),
    Root("home", ".librewolf", "librewolf", "native"),
    Root("home", ".zen", "zen", "native"),
    Root("config", "zen", "zen", "native"),
    Root("home", ".floorp", "floorp", "native"),
    Root("config", "floorp", "floorp", "native"),
    Root("home", ".waterfox", "waterfox", "native"),
    Root("config", "waterfox", "waterfox", "native"),
    # snap (the snap's HOME is snap/firefox/common)
    Root("home", "snap/firefox/common/.mozilla/firefox", "firefox", "snap"),
    Root("home", "snap/firefox/common/.config/mozilla/firefox", "firefox", "snap"),
    # flatpak: legacy dot-dir layout, then the sandbox XDG layout config/<...>
    Root("home", ".var/app/org.mozilla.firefox/.mozilla/firefox", "firefox", "flatpak"),
    Root("home", ".var/app/org.mozilla.firefox/config/mozilla/firefox", "firefox", "flatpak"),
    Root("home", ".var/app/io.gitlab.librewolf-community/.librewolf", "librewolf", "flatpak"),
    Root("home", ".var/app/io.gitlab.librewolf-community/config/librewolf/librewolf",
         "librewolf", "flatpak"),
    Root("home", ".var/app/io.gitlab.librewolf-community/config/librewolf",
         "librewolf", "flatpak"),
    Root("home", ".var/app/app.zen_browser.zen/.zen", "zen", "flatpak"),
    Root("home", ".var/app/app.zen_browser.zen/config/zen", "zen", "flatpak"),
    Root("home", ".var/app/one.ablaze.floorp/.floorp", "floorp", "flatpak"),
    Root("home", ".var/app/one.ablaze.floorp/config/floorp", "floorp", "flatpak"),
    Root("home", ".var/app/net.waterfox.waterfox/.waterfox", "waterfox", "flatpak"),
    Root("home", ".var/app/net.waterfox.waterfox/config/waterfox", "waterfox", "flatpak"),
)

# niri app-ids matched by the generated rule (exact match, anchored regex).
# Snap "firefox_firefox" is NOT included: it could not be verified (no snap
# on the dev machine); add it only once confirmed.
APP_IDS = (
    "firefox",
    "firefox-esr",
    "librewolf",
    "zen",
    "zen-browser",
    "zen-beta",
    "floorp",
    "waterfox",
    "org.mozilla.firefox",
    "io.gitlab.librewolf-community",
    "app.zen_browser.zen",
    "one.ablaze.floorp",
    "net.waterfox.waterfox",
)

# /proc/PID/comm values accepted by the `lock` symlink fallback (H5): exact
# names, compared case-insensitively on the kernel's 15-char comm (no prefix
# match: "zenity" or "floorplan" must not pass for a browser).
BROWSER_COMMS = (
    "firefox", "firefox-bin", "firefox-esr",
    "librewolf", "librewolf-bin",
    "zen", "zen-bin",
    "floorp", "floorp-bin",
    "waterfox", "waterfox-bin",
    "GeckoMain",
)
COMM_MAX = 15  # TASK_COMM_LEN - 1

# ---- Settings (--settings JSON) --------------------------------------------
SITE_THEMES = ("follow", "dark", "none")
# Defaults for every --settings key; mirrored by tests/fixtures/contract/
# settings-default.json and schema.json (checked by test_contract.py).
# opacity is the override value in [0, 1] (the QML slider stores a percentage;
# components/logic.js converts it).
SETTINGS_DEFAULTS = collections.OrderedDict([
    ("blur", True),
    ("isLight", False),
    ("glassEnabled", True),
    ("opacityOverride", False),
    ("opacity", 0.85),
    ("siteTheme", "follow"),
    ("pagesTransparent", True),
    ("genericStyle", True),
    ("excluded", []),
    ("disabledStyles", []),
    ("newTabGlass", True),
    ("readerOpaque", True),
    ("privateGlass", True),
])

# Why glass is inactive (status / sync "reason"); "active" when it is on.
REASONS = ("active", "blur_disabled", "opaque", "toggled_off", "forced_off")

# ============================================================================
# fsio
# ============================================================================

# Upper bound for the small text inputs we read (profiles.ini, KDL, JSON):
# a runaway file must not make a sync slow or eat memory.
READ_LIMIT = 4 * 1024 * 1024


def read_text(path, limit=READ_LIMIT):
    """Text of the regular file `path`, decoded as UTF-8 with surrogateescape
    (undecodable bytes survive a later write unchanged).

    Follows symlinks, but opens non-blocking and refuses anything that is not
    a regular file (a FIFO must never hang a sync). A file longer than
    `limit` bytes (None = no limit) raises OSError(EFBIG): it is never
    returned truncated, so an edit of what was read can never write back a
    prefix and lose the tail. Raises OSError.
    """
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", path)
        data = f.read() if limit is None else f.read(limit + 1)
    if limit is not None and len(data) > limit:
        raise OSError(errno.EFBIG, "file larger than %d bytes" % limit, path)
    return data.decode("utf-8", "surrogateescape")


# Temporary files of write_if_changed() are named
# TMP_PREFIX + <target name> + "." + <8 mkstemp characters> + TMP_SUFFIX: the
# prefix is ours alone, so sweep_stale_tmp() never mistakes a user's file
# (".config.kdl.20260101.tmp") for one of ours.
TMP_PREFIX = ".browserglass-"
TMP_SUFFIX = ".tmp"
# Upper bound for the embedded data files (styles.json is ~1 MB today).
DATA_READ_LIMIT = 64 * 1024 * 1024
# errno values that mean "we may not write here": the file is skipped with a
# "read_only" warning instead of failing the whole sync.
_READ_ONLY_ERRNOS = (errno.EACCES, errno.EPERM, errno.EROFS)
WARN_READ_ONLY = "read_only"


def make_warning(code, message, family=None, profile=None):
    """A warning object of the contract (schema.json defs.warning)."""
    return {"code": code, "message": message, "family": family, "profile": profile}


def _new_file_mode():
    """Mode of a newly created file: 0666 minus the process umask."""
    mask = os.umask(0o022)
    os.umask(mask)
    return 0o666 & ~mask


def _fsync_dir(folder):
    """Best effort: make a rename in `folder` durable."""
    try:
        fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_if_changed(path, text, warnings=None, family=None, profile=None,
                     mode=None, make_dirs=True):
    """Write `text` to `path` unless it already holds exactly that. Returns
    True when the file was written, False when it was left alone (unchanged,
    or skipped as read-only).

    - The text is encoded as UTF-8 with surrogateescape, the inverse of
      read_text(), so undecodable bytes read earlier are written back as is.
    - A symlink is followed: its final target is written and the link stays.
    - The write is atomic: a temporary file in the target's own folder, then
      os.replace(). The permissions of an existing file are kept (user.js is
      often 600); a new file gets `mode`, default 0666 minus the umask.
    - A target we may not write (no write permission on the file, or on its
      folder, or a read-only filesystem) is skipped: a "read_only" warning
      (with `family` / `profile`) is appended to `warnings` when given.
      Other errors raise OSError.
    - make_dirs creates the missing folders above the target (for a
      dangling symlink, above the file it points to).
    - os.replace() gives the file a new inode: a hard link to the old file
      keeps the old content (as with most editors).
    """
    data = text.encode("utf-8", "surrogateescape")
    target = os.path.realpath(path)

    def skipped():
        if warnings is not None:
            warnings.append(make_warning(
                WARN_READ_ONLY, "%s is read-only, left unchanged" % os.path.basename(path),
                family, profile))
        return False

    try:
        try:
            st = os.stat(target)
        except FileNotFoundError:
            st = None
        if st is not None:
            if not stat.S_ISREG(st.st_mode):
                raise OSError(errno.EINVAL, "not a regular file", path)
            if st.st_size == len(data):
                with open(target, "rb") as f:
                    if f.read(len(data) + 1) == data:
                        return False
            if not os.access(target, os.W_OK):
                return skipped()
            new_mode = stat.S_IMODE(st.st_mode)
        else:
            new_mode = _new_file_mode() if mode is None else mode
        folder = os.path.dirname(target)
        if make_dirs:
            os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX + os.path.basename(target) + ".",
                                   suffix=TMP_SUFFIX, dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fchmod(f.fileno(), new_mode)
                os.fsync(f.fileno())
            os.replace(tmp, target)
            _fsync_dir(folder)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as exc:
        if exc.errno in _READ_ONLY_ERRNOS:
            return skipped()
        raise
    return True


# ============================================================================
# discover
# ============================================================================

# XDG base directories, relative to $HOME when the variable is unset, empty or
# not absolute (the XDG spec says a relative value must be ignored).
XDG_DEFAULTS = {
    "XDG_CONFIG_HOME": ".config",
    "XDG_CACHE_HOME": ".cache",
    "XDG_STATE_HOME": ".local/state",
    "XDG_DATA_HOME": ".local/share",
}

# One discovered profile.
#   id       profile_id: first 12 hex chars of sha256 of the profile's
#            canonical absolute path (os.path.realpath), so the id is the same
#            whichever root (or symlink) the profile was reached through.
#   family   FAMILIES; variant: VARIANTS (from the root it was found under)
#   root     absolute path of that root (as configured, symlinks not resolved)
#   path     absolute, normalised profile path (symlinks not resolved)
#            name and path are str decoded with surrogateescape: a non-UTF-8
#            byte becomes a lone surrogate, so JSON output must keep
#            json.dumps' default ensure_ascii=True (it escapes them).
#   name     Name= from profiles.ini, else the folder name minus its salt
#   default  the profile Firefox starts by default for this root
#   source   "ini" (listed in profiles.ini) or "scan" (found by scan_groups)
Profile = collections.namedtuple("Profile", "id family variant root path name default source")
# One [ProfileN] entry of profiles.ini; path is absolute and normalised.
IniProfile = collections.namedtuple("IniProfile", "name path default")

_INI_PROFILE_SECTION = re.compile(r"Profile[0-9]+")


def home_dir(env=None):
    """$HOME from `env` (default os.environ), else the password database."""
    env = os.environ if env is None else env
    home = env.get("HOME") or ""
    if not os.path.isabs(home):
        try:
            home = pwd.getpwuid(os.getuid()).pw_dir
        except KeyError:
            home = "/"
    return os.path.normpath(home)


def xdg_dir(name, env=None):
    """The XDG base directory `name` (a key of XDG_DEFAULTS) for `env`."""
    env = os.environ if env is None else env
    value = env.get(name) or ""
    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.join(home_dir(env), XDG_DEFAULTS[name])


def root_path(root, env=None):
    """Absolute path of a ROOTS entry for `env` (base "home" or "config")."""
    base = xdg_dir("XDG_CONFIG_HOME", env) if root.base == "config" else home_dir(env)
    return os.path.normpath(os.path.join(base, root.rel))


def profile_id(path):
    """profile_id of the contract: sha256 of the canonical absolute path, 12 hex chars."""
    real = os.path.realpath(os.path.abspath(path))
    return hashlib.sha256(os.fsencode(real)).hexdigest()[:12]


def _ini_sections(text):
    """{section name: {key: value}} of an INI text (insertion order), tolerant
    of garbage, following Firefox's nsINIParser where it matters:

    lines are split on "\\r" and "\\n" only (not on U+2028 & co.); blank lines
    and lines starting with ';' or '#' are skipped; a line without '=', or
    outside any section, or after a header without ']', is ignored; keys are
    case-sensitive; a repeated key keeps its LAST value and a repeated
    section header continues the same section. Keys and values are stripped
    (more lenient than Firefox).
    """
    sections = {}
    current = None
    for raw in text.lstrip("\ufeff").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line[0] == "[":
            end = line.find("]")
            if end < 0:
                current = None
                continue
            current = sections.setdefault(line[1:end].strip(), {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        current[key.strip()] = value.strip()
    return sections


def _ini_path(root, value, relative):
    """Absolute normalised path of a Path=/Default= value, or None."""
    if not value or "\0" in value:
        return None
    if relative and not os.path.isabs(value):
        value = os.path.join(root, value)
    if not os.path.isabs(value):
        return None
    return os.path.normpath(value)


def _firefox_accepts(sections):
    """Names of the [ProfileN] sections Firefox itself loads.

    nsToolkitProfileService reads Profile0, Profile1, ... and stops at the
    first one that is missing or has no IsRelative=; it skips an entry
    without Name= or Path=, and one whose IsRelative is not "1" (absolute)
    with a Path that is not absolute.
    """
    accepted = set()
    index = 0
    while True:
        name = "Profile%d" % index
        keys = sections.get(name)
        if keys is None or "IsRelative" not in keys:
            return accepted
        index += 1
        path = keys.get("Path")
        if path is None or "Name" not in keys:
            continue
        if keys["IsRelative"] != "1" and not os.path.isabs(path):
            continue
        accepted.add(name)


def parse_profiles_ini(root):
    """The profiles listed in `root`/profiles.ini, as IniProfile records.

    The listing is lenient (as v0 was): every [ProfileN] section with a
    usable Path= is returned, in file order. IsRelative=0 means Path= is
    absolute, any other value relative to the root, and when it is missing
    an absolute Path is taken as is.

    The `default` flag follows Firefox and is only ever set on entries
    Firefox itself loads (_firefox_accepts): the Default= of the
    [Install<hash>] sections (one per installation sharing the root) when it
    names such an entry (paths compared canonically); otherwise the LAST
    such entry carrying Default=1. A missing, unreadable or garbled file
    gives what could be understood, possibly []. Paths are not checked for
    existence here.
    """
    try:
        text = read_text(os.path.join(root, PROFILES_INI))
    except (OSError, ValueError):
        return []
    sections = _ini_sections(text)
    accepted = _firefox_accepts(sections)
    entries = []        # (label, path, accepted by Firefox, Default=1)
    install_defaults = []
    for name, keys in sections.items():
        if name.startswith("Install") and len(name) > len("Install"):
            value = keys.get("Default", "")
            path = _ini_path(root, value, not os.path.isabs(value))
            if path:
                install_defaults.append(path)
        elif _INI_PROFILE_SECTION.fullmatch(name):
            value = keys.get("Path", "")
            is_rel = keys.get("IsRelative")
            relative = is_rel != "0" if is_rel is not None else not os.path.isabs(value)
            path = _ini_path(root, value, relative)
            if path is None:
                continue
            label = keys.get("Name") or os.path.basename(path)
            entries.append((label, path, name in accepted, keys.get("Default") == "1"))
    # Compare canonical paths: Default= may name the profile another way.
    loaded = {os.path.realpath(path) for _, path, ok, _ in entries if ok}
    installs = {real for real in map(os.path.realpath, install_defaults) if real in loaded}
    if installs:
        return [IniProfile(n, p, ok and os.path.realpath(p) in installs)
                for n, p, ok, _ in entries]
    flagged = [i for i, (_, _, ok, flag) in enumerate(entries) if ok and flag]
    last = flagged[-1] if flagged else -1
    return [IniProfile(n, p, i == last) for i, (n, p, _, _) in enumerate(entries)]


def _profile_label(folder):
    """Display name of a profile folder: "abcd1234.work" -> "work"."""
    salt, dot, rest = folder.partition(".")
    return rest if dot and salt and rest else folder


def scan_groups(root, known=()):
    """Profiles under `root` that profiles.ini does not list: the new profile
    manager's Profile Groups keep their profiles in the root without an ini
    entry. A profile here is a real (non-symlink) folder directly under the
    root holding a prefs.js. Folders whose realpath is in `known` are left
    out. Returns [(name, absolute path)] sorted by folder name.
    """
    known = set(known)
    found = []
    try:
        with os.scandir(root) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return []
    for entry in entries:
        try:
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        path = os.path.normpath(os.path.join(root, entry.name))
        if not os.path.isfile(os.path.join(path, PREFS_JS)):
            continue
        real = os.path.realpath(path)
        if real in known:
            continue
        known.add(real)
        found.append((_profile_label(entry.name), path))
    return found


def _overlaps(real, others):
    """True when the canonical path `real` equals, contains or sits inside one
    of the canonical paths `others`."""
    for other in others:
        if real == other:
            return True
        low, high = sorted((real, other), key=len)
        if high.startswith(low.rstrip(os.sep) + os.sep):
            return True
    return False


def _contains_any(real, others):
    """True when the canonical path `real` equals or contains one of `others`."""
    prefix = real.rstrip(os.sep) + os.sep
    return any(other == real or other.startswith(prefix) for other in others)


def find_profiles(env=None):
    """Every profile of every ROOTS entry for `env`, as Profile records.

    Roots are walked in ROOTS order; a root reached a second time through a
    symlink (e.g. ~/.mozilla/firefox -> ~/.config/mozilla/firefox) is skipped,
    and a profile reachable twice is kept once, at its first sighting: the
    first root in ROOTS order gives it its family and variant, even when the
    folder lives under another browser's root (e.g. a LibreWolf profile
    listed in Firefox's profiles.ini). Entries of profiles.ini come first,
    then scan_groups. Listed paths that are not folders are dropped, and so
    is a folder we must never write into as a profile: one that equals or
    contains $HOME, an XDG base directory or any profile root (Path=., ..,
    ~/.librewolf...), or that equals, contains or sits inside a profile
    already found (Path=a.one/chrome). A folder whose path below $HOME holds
    a newline is skipped too: status could not show it as a one-line
    "~/..." path (schema defs.tilde_path).
    """
    home = home_dir(env)
    guarded = {os.path.realpath(home)}
    guarded.update(os.path.realpath(xdg_dir(name, env)) for name in XDG_DEFAULTS)
    guarded.update(os.path.realpath(root_path(root, env)) for root in ROOTS)
    seen_roots = set()
    seen = set()
    result = []
    for root in ROOTS:
        top = root_path(root, env)
        try:
            if not os.path.isdir(top):
                continue
        except (OSError, ValueError):
            continue
        real_top = os.path.realpath(top)
        if real_top in seen_roots:
            continue
        seen_roots.add(real_top)
        candidates = [(p.name, p.path, p.default, "ini") for p in parse_profiles_ini(top)]
        candidates += [(name, path, False, "scan") for name, path in scan_groups(top, seen)]
        for name, path, default, source in candidates:
            try:
                if not os.path.isdir(path):
                    continue
            except (OSError, ValueError):
                continue
            if "\n" in os.path.relpath(os.path.normpath(path), home):
                continue
            real = os.path.realpath(path)
            if _contains_any(real, guarded) or _overlaps(real, seen):
                continue
            seen.add(real)
            result.append(Profile(profile_id(path), root.family, root.variant, top, path,
                                  name, default, source))
    return result


# ---- Zen transparency mods (H9) ---------------------------------------------
# Zen's mod manager keeps the registry of installed mods at the profile root,
# <profile>/zen-themes.json (its modsDataFile is profileDir/zen-themes.json;
# chrome/ only holds the generated chrome/zen-themes.css and the mod folders
# chrome/zen-themes/<uuid>/). <profile>/chrome/zen-themes.json, the path first
# guessed by the plan, is read as a fallback. The registry is an object
# {uuid: {id, name, description, tags, enabled, ...}} (a list is accepted
# too). An enabled mod whose name or tags speak of transparency (a word that
# starts with transparen, translucen, glass, blur, acrylic or the word mica;
# the free-text description is not read), or a zen.* pref of the same kind
# that is on once user.js has overridden prefs.js, would stack its own
# see-through background with ours: status and sync warn, nothing is
# changed. Not checked against a Zen install (none here); a file that is
# missing, unreadable or corrupt simply detects nothing.
WARN_ZEN_MOD = "zen_transparency_mod"
ZEN_MOD_FILES = (ZEN_THEMES_JSON, os.path.join(CHROME_DIR, ZEN_THEMES_JSON))
_ZEN_MOD_WORDS = re.compile(r"\b(?:transparen|translucen|glass|blur|acrylic|mica\b)", re.I)
_ZEN_PREF = re.compile(r"zen\.[A-Za-z0-9._-]*(?:transparen|translucen|acrylic|blur|mica)[A-Za-z0-9._-]*",
                       re.I)
_OFF_WORDS = ("", "false", "0", "no", "off", "none", "null")


def _word_on(text):
    """False for a text that reads as off: empty, false, no, off, none,
    null or a number equal to 0; True otherwise."""
    text = text.strip().lower()
    if text in _OFF_WORDS:
        return False
    try:
        return float(text) != 0.0
    except ValueError:
        return True


def _zen_pref_on(value):
    """A user_pref value literal that turns a feature on: true, a non-zero
    number or a string that does not read as off ("false", "0", "")."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return _word_on(value)


def _zen_mod_enabled(value):
    """A mod's "enabled" value: missing (None) counts as enabled; false, 0
    and the strings "false" / "0" do not."""
    if value is None or value is True:
        return True
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return _word_on(value)
    return bool(value)


def _zen_mod_hits(mod):
    if not isinstance(mod, dict) or not _zen_mod_enabled(mod.get("enabled")):
        return False
    words = [mod.get("name")]
    tags = mod.get("tags")
    if isinstance(tags, list):
        words.extend(tags)
    return any(isinstance(w, str) and _ZEN_MOD_WORDS.search(w) for w in words)


def zen_transparency(profile):
    """True when the Zen profile folder `profile` has a transparency mod
    or pref enabled (H9). Never raises."""
    for rel in ZEN_MOD_FILES:
        try:
            doc = json.loads(read_text(os.path.join(profile, rel)).lstrip("\ufeff"))
        except (OSError, ValueError, RecursionError):
            continue
        mods = doc.values() if isinstance(doc, dict) else doc if isinstance(doc, list) else ()
        if any(_zen_mod_hits(mod) for mod in mods):
            return True
    prefs = {}
    for name in (PREFS_JS, USER_JS):  # user.js is applied last, at startup
        try:
            prefs.update(parse_prefs(read_text(os.path.join(profile, name))))
        except (OSError, ValueError):
            continue
    return any(_ZEN_PREF.fullmatch(pref) and _zen_pref_on(value) for pref, value in prefs.items())


def zen_warning(pid):
    return make_warning(WARN_ZEN_MOD, "Zen transparency mod detected; it may stack with browserGlass.",
                        "zen", pid)


# ============================================================================
# lockprobe
# ============================================================================

# Is a browser running on a profile? (H5)
# Firefox holds a POSIX record lock (fcntl F_SETLK, F_WRLCK) on .parentlock
# for as long as it runs. F_GETLK asks the kernel who would block a write
# lock: l_type F_UNLCK means nobody. The lock lives on the inode, so it is
# seen through Flatpak and Snap bind mounts too. We only ever open the file
# read-only, never create it, and never take a lock of our own (no lockf, no
# flock): closing a descriptor drops the caller's own POSIX locks on the file,
# and a lock we took could block the browser. /proc/locks is not used (the
# device numbers do not match on btrfs).
# struct flock on x86_64 / aarch64 glibc: short l_type, short l_whence,
# off_t l_start, off_t l_len, pid_t l_pid (+ padding) = 32 bytes.
FLOCK = struct.Struct("@hhqqi4x")
LOCK_RUNNING = "running"
LOCK_FREE = "free"
LOCK_UNKNOWN = "unknown"  # .parentlock exists but could not be probed
PROC_DIR = "/proc"
_LOCK_LINK_TARGET = re.compile(r"(?P<host>[^:]*):\+?(?P<pid>[0-9]{1,10})")


def _getlk(fd):
    """F_GETLK for a whole-file write lock on `fd`: the unpacked struct flock."""
    request = FLOCK.pack(fcntl.F_WRLCK, os.SEEK_SET, 0, 0, 0)
    return FLOCK.unpack(fcntl.fcntl(fd, fcntl.F_GETLK, request))


def _proc_comm(pid):
    """/proc/PID/comm of `pid` without its newline, or None."""
    try:
        return read_text(os.path.join(PROC_DIR, str(pid), "comm"), limit=64).strip()
    except (OSError, ValueError):
        return None


_BROWSER_COMMS = frozenset(name[:COMM_MAX].lower() for name in BROWSER_COMMS)


def _is_browser_comm(comm):
    return bool(comm) and comm.lower() in _BROWSER_COMMS


def parse_fib_trie(text):
    """Local IPv4 addresses listed in a /proc/net/fib_trie text (the
    "|-- A.B.C.D" line followed by "/32 host LOCAL")."""
    found = set()
    last = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|-- "):
            last = line[4:].strip()
        elif last and line.startswith("/32 host LOCAL"):
            found.add(last)
    return found


def _local_addresses():
    """This host's local IPv4 addresses, or None when they cannot be read.

    Read from /proc/net/fib_trie: no name resolution, no network.
    """
    try:
        return parse_fib_trie(read_text(os.path.join(PROC_DIR, "net", "fib_trie")))
    except (OSError, ValueError):
        return None


def _host_is_local(host):
    if host.startswith("127."):
        return True
    local = _local_addresses()
    return local is None or host in local


def lock_link_state(profile):
    """Fallback probe on the `lock` symlink (LOCK_RUNNING or LOCK_FREE).

    Firefox points it at "<host IP>:+<pid>" ("+" when it also holds the fcntl
    lock), but the link outlives crashes and reboots (seen: a link to
    "<LAN address>:+36770" with nothing running). It only counts when the pid
    is alive with a browser-like /proc/PID/comm (BROWSER_COMMS) and the host
    is one of ours; anything else (no link, garbage, stale) is free.
    """
    try:
        target = os.readlink(os.path.join(profile, LOCK_LINK))
    except (OSError, ValueError):
        return LOCK_FREE
    match = _LOCK_LINK_TARGET.fullmatch(target)
    if not match:
        return LOCK_FREE
    pid = int(match.group("pid"))
    if pid <= 0 or not _is_browser_comm(_proc_comm(pid)):
        return LOCK_FREE
    if not _host_is_local(match.group("host")):
        return LOCK_FREE
    return LOCK_RUNNING


def lock_state(profile):
    """LOCK_RUNNING, LOCK_FREE or LOCK_UNKNOWN for the profile folder `profile`.

    F_GETLK on .parentlock decides. The `lock` symlink is consulted only when
    .parentlock does not exist or the filesystem has no POSIX locks (ENOLCK).
    Any other failure (a symlinked .parentlock, which O_NOFOLLOW refuses, a
    non-regular file, EACCES...) is LOCK_UNKNOWN.
    """
    path = os.path.join(profile, PARENT_LOCK)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except FileNotFoundError:
        return lock_link_state(profile)
    except (OSError, ValueError):
        return LOCK_UNKNOWN
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return LOCK_UNKNOWN
        try:
            l_type = _getlk(fd)[0]
        except OSError as exc:
            if exc.errno == errno.ENOLCK:
                return lock_link_state(profile)
            return LOCK_UNKNOWN
    finally:
        os.close(fd)
    return LOCK_FREE if l_type == fcntl.F_UNLCK else LOCK_RUNNING


def profile_running(profile):
    """True when a browser is known to run on `profile` (LOCK_UNKNOWN is False).

    For display only (status, restart toast). A caller about to write into
    the profile (clean-prefs, the last re-check before writing prefs.js in
    H6) must call lock_state() and treat LOCK_UNKNOWN as "maybe running"
    (defer and retry, or warn): a symlinked .parentlock, which the probe
    refuses to follow, can hide a running browser.
    """
    return lock_state(profile) == LOCK_RUNNING


# ============================================================================
# inputs
# ============================================================================

# The opacity DMS gives every window: that of the first global window-rule
# (no `match` child) of $XDG_CONFIG_HOME/niri/dms/windowrules.kdl that sets
# one, as v0 did. An `exclude` child does not make a rule local: in niri a
# rule without `match` applies to every window but the excluded ones.
# Without the file, without such a rule, or with an unreadable value:
# DEFAULT_OPACITY (fully opaque, so no glass). The value is clamped to [0, 1].
# The file is read only, never written (rule 8).
# Known limits (all rare, hand-written cases):
#   - a bare `match` (no property) matches every window in niri, but its
#     rule is still taken as local here (v0 did the same);
#   - with several global rules niri applies the LAST opacity, we take the
#     FIRST (validated decision; DMS writes a single global rule);
#   - the reader is best effort: a file niri (KDL v1) rejects outright, e.g.
#     an integer `opacity 1`, `.5` or KDL v2 syntax, still yields a value,
#     which then does not reflect what niri shows (niri keeps its previous
#     config).
DEFAULT_OPACITY = 1.0
MODES = ("dark", "light")
# Nesting deeper than this is skipped, not parsed (no RecursionError).
KDL_MAX_DEPTH = 64

KdlNode = collections.namedtuple("KdlNode", "name args props children")
# args: [(kind, text)] with kind "word" (bare value: number, keyword, identifier)
# or "str"; props: {key: (kind, text)}; children: [KdlNode] or None.
_KDL_TERM = ("term", None)
_KDL_SLASHDASH = ("slashdash", None)
_KDL_NEWLINES = "\n\r\x0b\x0c\x85\u2028\u2029"
_KDL_WORD_STOP = set('{}();="\\\ufeff' + _KDL_NEWLINES)
_KDL_STRING_START = re.compile(r'(r?)(#*)("(?:"")?)')
_KDL_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", '"': '"', "/": "/",
                "b": "\b", "f": "\f", "s": " "}
_HEX_COLOR = re.compile(r"#([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?|#([0-9a-fA-F]{3})")

Colors = collections.namedtuple("Colors", "mode surface")


def _kdl_skip_block_comment(text, i):
    """Index just past the (nested) /* ... */ comment starting at `i`."""
    depth = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            depth += 1
            i += 2
        elif text.startswith("*/", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return n


def _kdl_string(text, i, match):
    """(token, end index) for the string whose opening `match` is at `i`.

    Handles "...", "\"\"\"...\"\"\"" and the raw forms r"...", r#"..."# (KDL 1)
    and #"..."# (KDL 2). An unterminated string runs to the end of the text.
    """
    raw = bool(match.group(1) or match.group(2))
    close = match.group(3) + match.group(2)
    start = match.end()
    n = len(text)
    if raw:
        j = text.find(close, start)
        if j < 0:
            return ("str", text[start:]), n
        return ("str", text[start:j]), j + len(close)
    out = []
    j = start
    while j < n:
        c = text[j]
        if c == "\\" and j + 1 < n:
            out.append(_KDL_ESCAPES.get(text[j + 1], text[j + 1]))
            j += 2
            continue
        if text.startswith(close, j):
            return ("str", "".join(out)), j + len(close)
        out.append(c)
        j += 1
    return ("str", "".join(out)), n


def kdl_tokens(text):
    """Tokens of a KDL (v1 or v2) text: ("word", s), ("str", s), ("{", None),
    ("}", None), ("=", None), _KDL_TERM (newline or ';'), _KDL_SLASHDASH.

    Drops // and nested /* */ comments, (type) annotations and escaped line
    continuations. Never fails: garbage becomes words.
    """
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in _KDL_NEWLINES or c == ";":
            tokens.append(_KDL_TERM)
            i += 1
        elif c.isspace() or c == "\ufeff":
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] not in _KDL_NEWLINES:
                i += 1
        elif text.startswith("/*", i):
            i = _kdl_skip_block_comment(text, i)
        elif text.startswith("/-", i):
            tokens.append(_KDL_SLASHDASH)
            i += 2
        elif c == "\\":
            # Line continuation: "\", blanks, an optional // comment, a newline.
            i += 1
            while i < n and text[i] not in _KDL_NEWLINES and text[i].isspace():
                i += 1
            if text.startswith("//", i):
                while i < n and text[i] not in _KDL_NEWLINES:
                    i += 1
            if text.startswith("\r\n", i):
                i += 2
            elif i < n and text[i] in _KDL_NEWLINES:
                i += 1
        elif c in "{}=":
            tokens.append((c, None))
            i += 1
        elif c == "(":
            end = text.find(")", i)
            i = n if end < 0 else end + 1
        elif c == ")":
            i += 1
        else:
            match = _KDL_STRING_START.match(text, i)
            if match:
                token, i = _kdl_string(text, i, match)
                tokens.append(token)
                continue
            j = i + 1
            while j < n:
                d = text[j]
                if d in _KDL_WORD_STOP or d.isspace():
                    break
                if d == "/" and text[j + 1:j + 2] in ("/", "*", "-"):
                    break
                j += 1
            tokens.append(("word", text[i:j]))
            i = j
    return tokens


def kdl_parse(text):
    """The top-level KdlNode list of a KDL text, best effort.

    A /- (slashdash) drops the next node, argument, property or children
    block. A stray "}" at the top level is ignored; an unclosed block ends at
    the end of the text. Blocks nested deeper than KDL_MAX_DEPTH are skipped.
    """
    tokens = kdl_tokens(text)
    n = len(tokens)
    pos = 0

    def skip_block():
        # tokens[pos - 1] was "{": skip to its matching "}".
        nonlocal pos
        depth = 1
        while pos < n and depth:
            kind = tokens[pos][0]
            depth += 1 if kind == "{" else -1 if kind == "}" else 0
            pos += 1

    def value():
        # Consume one value token (or nothing) and return it.
        nonlocal pos
        if pos < n and tokens[pos][0] in ("word", "str"):
            pos += 1
            return tokens[pos - 1]
        return None

    def nodes(depth):
        nonlocal pos
        result = []
        while pos < n:
            kind = tokens[pos][0]
            if kind in ("term", "="):
                pos += 1
            elif kind == "}":
                pos += 1
                if depth:
                    return result
            elif kind == "slashdash":
                pos += 1
                while pos < n and tokens[pos][0] == "term":
                    pos += 1
                if pos < n and tokens[pos][0] != "}":
                    node(depth)
            else:
                result.append(node(depth))
        return result

    def children(depth):
        nonlocal pos
        pos += 1  # the "{"
        if depth >= KDL_MAX_DEPTH:
            skip_block()
            return []
        return nodes(depth + 1)

    def node(depth):
        nonlocal pos
        name = None
        if tokens[pos][0] in ("word", "str"):
            name = tokens[pos][1]
            pos += 1
        elif tokens[pos][0] == "=":
            pos += 1
        args = []
        props = {}
        kids = None
        while pos < n:
            kind = tokens[pos][0]
            if kind == "term":
                pos += 1
                break
            if kind == "}":
                break
            if kind == "{":
                block = children(depth)
                if kids is None:
                    kids = block
                break
            if kind == "slashdash":
                pos += 1
                if pos < n and tokens[pos][0] == "{":
                    children(depth)
                    continue
                value()
                if pos < n and tokens[pos][0] == "=":
                    pos += 1
                    value()
                continue
            if kind == "=":
                pos += 1
                continue
            item = value()
            if pos < n and tokens[pos][0] == "=":
                pos += 1
                prop = value()
                if prop is not None:
                    props[item[1]] = prop
            else:
                args.append(item)
        return KdlNode(name, args, props, kids)

    return nodes(0)


def kdl_number(token):
    """The finite float of a bare KDL number token, or None."""
    if not token or token[0] != "word":
        return None
    try:
        number = float(token[1].replace("_", ""))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def global_opacity(text):
    """Opacity of the first global window-rule of a niri KDL text that sets
    one (see DEFAULT_OPACITY), clamped to [0, 1]."""
    for rule in kdl_parse(text):
        if rule.name != "window-rule" or rule.children is None:
            continue
        if any(child.name == "match" for child in rule.children):
            continue
        for child in rule.children:
            if child.name == "opacity" and child.args:
                number = kdl_number(child.args[0])
                if number is not None:
                    return min(1.0, max(0.0, number))
    return DEFAULT_OPACITY


def dms_opacity(env=None):
    """DMS's global window opacity from $XDG_CONFIG_HOME/niri/dms/windowrules.kdl
    (DEFAULT_OPACITY when the file is missing or has no usable rule)."""
    path = os.path.join(xdg_dir("XDG_CONFIG_HOME", env), DMS_RULES_REL)
    try:
        text = read_text(path)
    except (OSError, ValueError):
        return DEFAULT_OPACITY
    return global_opacity(text)


def dms_colors(env=None, mode=None):
    """Colors(mode, surface) from $XDG_CACHE_HOME/dms/dms-colors.json.

    `mode` ("dark" | "light") forces the palette; by default it is the file's
    "mode" key, "dark" when unusable. surface is colors[mode]["surface"] as
    lowercase #rrggbb (an #rrggbbaa value loses its alpha, #rgb is expanded);
    DEFAULT_SURFACES[mode] when the file is missing, corrupt or lacks a valid
    colour (the dark one is v0's DEFAULT_SURFACE).
    A leading UTF-8 BOM is accepted.
    """
    path = os.path.join(xdg_dir("XDG_CACHE_HOME", env), DMS_COLORS_REL)
    try:
        doc = json.loads(read_text(path).lstrip("\ufeff"))
    except (OSError, ValueError, RecursionError):
        doc = None
    if not isinstance(doc, dict):
        doc = {}
    if mode not in MODES:
        mode = doc.get("mode") if doc.get("mode") in MODES else "dark"
    surface = DEFAULT_SURFACES[mode]
    colors = doc.get("colors")
    palette = colors.get(mode) if isinstance(colors, dict) else None
    value = palette.get("surface") if isinstance(palette, dict) else None
    if isinstance(value, str):
        match = _HEX_COLOR.fullmatch(value.strip())
        if match:
            digits = match.group(1) or "".join(c * 2 for c in match.group(2))
            surface = "#" + digits.lower()
    return Colors(mode, surface)

# ============================================================================
# settings
# ============================================================================

# A domain as the settings and the generated regexps accept it: lowercase
# ASCII labels of letters, digits and "-", separated by dots.
_DOMAIN_LABEL = re.compile(r"[a-z0-9-]{1,63}")
# my-internet style name (key without ".css") and css-mapping.json target,
# as in schema.json defs.site_name / defs.site_domain (a host).
_SITE_NAME = re.compile(r"[+-]?[a-z0-9][a-z0-9.-]*")
_SITE_HOST = re.compile(r"[a-z0-9][a-z0-9.-]*")
# Full stops that URL parsers treat as ".": ideographic, fullwidth, halfwidth.
_IDEOGRAPHIC_DOTS = ("\u3002", "\uff0e", "\uff61")
_TRUE_WORDS = ("true", "1", "yes", "on")
_FALSE_WORDS = ("false", "0", "no", "off")


def normalize_domain(value):
    """The bare host of a user-entered domain or URL, or None when unusable.

    "https://user@Sub.Example.com:8080/path?q" -> "sub.example.com": the
    scheme, user info, port, path and a leading "*." are dropped, and the
    result is lowercased. Otherwise the host is kept as entered, like v0
    did: "www.x.com" stays "www.x.com" (an exclusion covers that host and its
    subdomains, so "www.com" never turns into "com"). An internationalised
    name gets the ASCII form Firefox shows (close to UTS-46
    nontransitional: NFKC, lowercase, NFC, then "xn--" + Punycode per
    non-ASCII label, so U+00DF is kept: "fa\\u00df.de" -> "xn--fa-hia.de").
    IPv6 literals and anything left with characters outside [a-z0-9.-] or
    an empty label give None.
    """
    if not isinstance(value, str):
        return None
    host = value.strip()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = re.split(r"[/?#]", host, maxsplit=1)[0]
    host = host.rpartition("@")[2]
    if host.startswith("["):
        return None
    host = unicodedata.normalize("NFC", unicodedata.normalize("NFKC", host).lower())
    for dot in _IDEOGRAPHIC_DOTS:
        host = host.replace(dot, ".")
    host = host.split(":", 1)[0].strip(".")
    while host.startswith("*."):
        host = host[2:]
    if not host.isascii():
        try:
            host = ".".join(label if label.isascii()
                            else "xn--" + label.encode("punycode").decode("ascii")
                            for label in host.split("."))
        except UnicodeError:
            return None
    if not host or len(host) > 253:
        return None
    if not all(_DOMAIN_LABEL.fullmatch(label) for label in host.split(".")):
        return None
    return host


def normalize_style_name(value):
    """A my-internet style name ("github.com", "+x.org", "-google.com") from a
    settings value: surrounding whitespace and a ".css" suffix are dropped,
    the result is lowercased. None when it does not fit defs.site_name.
    """
    if not isinstance(value, str):
        return None
    name = value.strip()
    if name.lower().endswith(".css"):
        name = name[:-4]
    name = name.strip().lower()
    return name if _SITE_NAME.fullmatch(name) else None


def _setting_bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    return default


def _setting_opacity(value, default):
    """A [0, 1] opacity (the contract's range: logic.js divides the DMS
    slider's int percent by 100). As a safety net, a whole number from 2 to
    100 is still read as a percentage (85 -> 0.85); any other value is
    clamped to [0, 1] (1.5 -> 1). Unusable values (not a number, NaN,
    infinite, too large for a float) give `default`."""
    if isinstance(value, bool):
        return default
    if isinstance(value, str):
        value = value.strip()
    if not isinstance(value, (int, float, str)):
        return default
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    if number > 1.0 and number <= 100.0 and number == int(number):
        number /= 100.0
    return min(1.0, max(0.0, number))


def _setting_items(value, field):
    """The items of a list setting: a JSON array, or the comma separated
    string v0 used. An item may be an object (ListSettingWithInput stores
    {"domain": ...}): its `field` value is taken."""
    if isinstance(value, str):
        value = re.split(r"[,\s]+", value)
    if not isinstance(value, (list, tuple)):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            item = item.get(field)
        if isinstance(item, str):
            items.append(item)
    return items


def _unique(items):
    seen = set()
    out = []
    for item in items:
        if item is not None and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def settings_from_json(value):
    """The complete, normalised settings dict from the --settings value.

    `value` is the JSON text (or an already parsed object). Every key of
    SETTINGS_DEFAULTS is present in the result, in that order; unknown keys
    are ignored and a missing or unusable value takes its default:
      - booleans also accept 0/1 and "true"/"false" (and yes/no, on/off);
      - opacity is clamped to [0, 1] (see _setting_opacity: a whole
        number from 2 to 100 is a percentage);
      - siteTheme must be one of SITE_THEMES;
      - excluded: normalize_domain() of each entry (strings or {"domain"}
        objects), invalid ones dropped, duplicates removed;
      - disabledStyles: normalize_style_name() of each entry (strings or
        {"name"} objects).
    v0 migration (H4): the v0 key excludedSites ([{"domain": ...}]) is merged
    into excluded (after it); pagesTransparent keeps its meaning (master
    switch of page transparency).
    Raises ValueError for text that is not JSON or not a JSON object.
    """
    if isinstance(value, bytes):
        value = value.decode("utf-8", "surrogateescape")
    if isinstance(value, str):
        try:
            doc = json.loads(value) if value.strip() else {}
        except RecursionError:
            raise ValueError("--settings is nested too deeply")
    else:
        doc = value
    if doc is None:
        doc = {}
    if not isinstance(doc, dict):
        raise ValueError("--settings must be a JSON object")
    out = collections.OrderedDict()
    for key, default in SETTINGS_DEFAULTS.items():
        raw = doc.get(key)
        if key == "opacity":
            out[key] = _setting_opacity(raw, default)
        elif key == "siteTheme":
            theme = raw.strip().lower() if isinstance(raw, str) else None
            out[key] = theme if theme in SITE_THEMES else default
        elif key == "excluded":
            items = _setting_items(raw, "domain") + _setting_items(
                doc.get(V0_SETTING_EXCLUDED), "domain")
            out[key] = _unique(normalize_domain(item) for item in items)
        elif key == "disabledStyles":
            out[key] = _unique(normalize_style_name(item) for item in _setting_items(raw, "name"))
        else:
            out[key] = _setting_bool(raw, default)
    return out


# ============================================================================
# render
# ============================================================================

# Pure functions: settings + inputs -> file contents. Nothing here reads or
# writes a file. When glass is inactive the generated stylesheets are kept
# but neutral (a header comment only), so the @import lines stay valid.

_CHROME_GLASS = (
    "body {{\n"
    "  background: rgba({r}, {g}, {b}, {a}) !important;\n"
    "}}\n"
    ":root, #main-window, #browser, #appcontent, #navigator-toolbox,\n"
    "#TabsToolbar, #nav-bar, #PersonalToolbar,\n"
    "#tabbrowser-tabbox, #tabbrowser-tabpanels,\n"
    ".browserContainer, .browserStack, browser {{\n"
    "  background: transparent !important;\n"
    "  border: none !important;\n"
    "}}\n"
)
# privateGlass=false: private windows get an opaque tint. "temporary" only:
# "permanent" is the always-private mode, which must stay like normal windows.
_CHROME_PRIVATE_OPAQUE = (
    ":root[privatebrowsingmode=\"temporary\"] body {{\n"
    "  background: rgba({r}, {g}, {b}, 1) !important;\n"
    "}}\n"
)
# Generic page rule (v0): every web page gets transparent html and body.
_CONTENT_GENERIC = (
    "@-moz-document regexp(\"https?://{lookahead}.*\") {{\n"
    "  html, body {{ background: transparent !important; }}\n"
    "}}\n"
)
# readerOpaque=false: reader view in glass. --main-background is set on body.
_CONTENT_READER_GLASS = (
    "@-moz-document url-prefix(\"about:reader\") {\n"
    "  :root, body { background: transparent !important; }\n"
    "  body { --main-background: transparent !important; }\n"
    "}\n"
)
# newTabGlass=true. about:privatebrowsing paints on <html>, hence ":root, body".
_CONTENT_NEWTAB_GLASS = (
    "@-moz-document url(\"about:newtab\"), url(\"about:home\"), "
    "url(\"about:privatebrowsing\") {\n"
    "  :root { --newtab-background-color: transparent !important; }\n"
    "  :root, body { background: transparent !important; }\n"
    "}\n"
)
# readerOpaque=true: pdf.js back to its own background. A bare rule, last in
# the file (after the generic rule and the site styles).
_CONTENT_PDF_OPAQUE = (
    "body:has(> #outerContainer #viewerContainer) {\n"
    "  background-color: var(--body-bg-color) !important;\n"
    "}\n"
)
_NIRI_RULE = (
    "// Firefox-family browsers paint their own translucency (glass backgrounds,\n"
    "// opaque text, images and videos): niri must not dim the whole window.\n"
    "window-rule {{\n"
    "    match app-id=r#\"^({app_ids})$\"#\n"
    "    opacity 1.0\n"
    "}}\n"
)
_NIRI_NO_RULE = (
    "// No rule: glass is inactive, the browsers follow DMS's global window rule.\n"
)


def _clamp01(value, default=DEFAULT_OPACITY):
    """`value` clamped to [0, 1] and rounded to the 4 decimals the CSS is
    written with (format_number), so the glass state and the written tint
    always agree (0.99999 is 1: opaque)."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return round(min(1.0, max(0.0, number)), 4)


def effective_opacity(settings, dms_value, forced=None):
    """(opacity, source) of the glass: `forced` (sync --opacity) when given,
    else the settings override when opacityOverride is on, else DMS's global
    opacity `dms_value`. source is "forced", "override" or "dms"."""
    if forced is not None:
        return _clamp01(forced), "forced"
    if settings["opacityOverride"]:
        return _clamp01(settings["opacity"]), "override"
    return _clamp01(dms_value), "dms"


def glass_state(settings, opacity, off=False):
    """(active, reason): reason is one of REASONS, "active" when active.
    Checked in this order: --off, the widget toggle, DMS blur, opacity 1."""
    if off:
        return False, "forced_off"
    if not settings["glassEnabled"]:
        return False, "toggled_off"
    if not settings["blur"]:
        return False, "blur_disabled"
    if _clamp01(opacity) >= 1.0:
        return False, "opaque"
    return True, "active"


def format_number(value):
    """Short decimal text of a number in [0, 1]: 0.85 -> "0.85", 1.0 -> "1"."""
    return ("%.4f" % value).rstrip("0").rstrip(".")


def surface_rgb(surface, mode="dark"):
    """(r, g, b) of a "#rrggbb" (or "#rgb", "#rrggbbaa": alpha ignored)
    surface; that of DEFAULT_SURFACES[mode] when unusable."""
    match = _HEX_COLOR.fullmatch(surface.strip()) if isinstance(surface, str) else None
    if not match:
        match = _HEX_COLOR.fullmatch(DEFAULT_SURFACES.get(mode, DEFAULT_SURFACE))
    digits = match.group(1) or "".join(c * 2 for c in match.group(2))
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def css_rx_escape(domain):
    """`domain` (validated: [a-z0-9.-]) as regexp text inside a CSS string:
    a dot becomes \\\\. (CSS unescapes it to \\.). A hyphen is NOT escaped:
    Firefox compiles @-moz-document regexp() in Unicode mode, where "\\-" is
    a syntax error, and an invalid regexp() matches EVERY page (measured on
    Firefox 160; v0 used re.escape and had that bug)."""
    return domain.replace(".", "\\\\.")


def css_rx_alt(domains):
    """Alternation of escaped domains, longest first (then by name, so the
    output is deterministic)."""
    return "|".join(css_rx_escape(d) for d in sorted(set(domains), key=lambda d: (-len(d), d)))


def exclusion_lookahead(excluded):
    """Negative lookahead (CSS string text) refusing `excluded` domains and
    their subdomains right after "https?://"; "" when there are none."""
    domains = [d for d in excluded if d]
    if not domains:
        return ""
    return "(?!(?:[^/]*\\\\.)?(?:%s)(?:[:/]|$))" % css_rx_alt(domains)


def _css_head(note):
    return "%s\n/* %s */\n" % (V1_CSS_HEADER, note)


def chrome_css(settings, opacity, surface, mode="dark", off=False):
    """Text of chrome/dms-glass-chrome.css (imported by userChrome.css)."""
    active, reason = glass_state(settings, opacity, off)
    if not active:
        return _css_head("glass inactive (%s): neutral file" % reason)
    opacity = _clamp01(opacity)
    r, g, b = surface_rgb(surface, mode)
    text = _css_head("glass active: opacity %s, surface #%02x%02x%02x"
                     % (format_number(opacity), r, g, b))
    text += _CHROME_GLASS.format(r=r, g=g, b=b, a=format_number(opacity))
    if not settings["privateGlass"]:
        text += _CHROME_PRIVATE_OPAQUE.format(r=r, g=g, b=b)
    return text


def content_css(settings, opacity, sites_css="", off=False):
    """Text of chrome/dms-glass-content.css (imported by userContent.css).

    `sites_css` is the output of sites_build_css() (already validated), put
    after the generic and special-page rules and before the PDF rule.
    """
    active, reason = glass_state(settings, opacity, off)
    if not active:
        return _css_head("glass inactive (%s): neutral file" % reason)
    if not settings["pagesTransparent"]:
        return _css_head("page transparency disabled: neutral file")
    parts = [_css_head("page backgrounds are transparent (the DMS tint is behind them); "
                       "images, videos and text stay opaque")]
    parts.append(_CONTENT_GENERIC.format(lookahead=exclusion_lookahead(settings["excluded"])))
    if not settings["readerOpaque"]:
        parts.append(_CONTENT_READER_GLASS)
    if settings["newTabGlass"]:
        parts.append(_CONTENT_NEWTAB_GLASS)
    if sites_css and sites_css.strip():
        parts.append(sites_css if sites_css.endswith("\n") else sites_css + "\n")
    if settings["readerOpaque"]:
        parts.append(_CONTENT_PDF_OPAQUE)
    return "\n".join(parts)


def userjs_prefs(settings, opacity, off=False):
    """[(pref, JS literal)] of the user.js block, in PREFS order.

    The stylesheet pref is always on (the imported files must load);
    transparent browser only while glass is active with transparent pages;
    the colour-scheme override follows siteTheme: "follow" -> isLight
    (1 light, 0 dark), "dark" -> 0, "none" -> not written (its original
    value is restored from the state by sync, H3).
    """
    active, _ = glass_state(settings, opacity, off)
    prefs = [
        (PREF_STYLESHEETS, "true"),
        (PREF_TRANSPARENT, "true" if active and settings["pagesTransparent"] else "false"),
    ]
    theme = settings["siteTheme"]
    if theme == "follow":
        scheme = COLOR_SCHEME_LIGHT if settings["isLight"] else COLOR_SCHEME_DARK
        prefs.append((PREF_COLOR_SCHEME, str(scheme)))
    elif theme == "dark":
        prefs.append((PREF_COLOR_SCHEME, str(COLOR_SCHEME_DARK)))
    return prefs


def userjs_block(settings, opacity, off=False):
    """The v1 managed block of user.js (marker lines included, "\\n" ends)."""
    lines = [V1_USERJS_BEGIN]
    lines += ['user_pref("%s", %s);' % pref for pref in userjs_prefs(settings, opacity, off)]
    lines.append(V1_USERJS_END)
    return "\n".join(lines) + "\n"


def niri_kdl(rule_needed):
    """Text of $XDG_CONFIG_HOME/niri/dms-browser-glass.kdl.

    With `rule_needed` (decided by sync, H1) it holds a window-rule giving the
    APP_IDS (anchored regexp) opacity 1.0; without, only comments.
    """
    head = V1_NIRI_HEADER + "\n"
    if not rule_needed:
        return head + _NIRI_NO_RULE
    app_ids = "|".join(app_id.replace(".", "\\.") for app_id in APP_IDS)
    return head + _NIRI_RULE.format(app_ids=app_ids)


# ============================================================================
# sites
# ============================================================================

# Site styles of sameerasw/my-internet (MIT), embedded in data/ (no network).
# The matching ports v0 browser-glass-sites build:
#   - "x.com" / "+x.com" / "www.x.com": x.com and its subdomains, except the
#     subdomains a more specific style claims ("gist.x.com"); the plain name
#     wins over "+x.com";
#   - "-x.com": x.<any TLD> and www.x.<any TLD> (the last label is dropped:
#     "-google.com.br" covers google.com.<any TLD>);
#   - css-mapping.json: extra hosts (www. implied) for a style, unless a
#     dedicated style already covers them;
#   - every other web page gets the generic style example.com.css ("force
#     styling"), through a negative lookahead of all the domains above;
#   - only features whose name says transparen/glass/translucent are kept;
#   - excluded domains (and subdomains) get nothing. An exclusion is the
#     host as entered: "www.x.com" refuses www.x.com and its subdomains, not
#     x.com (v0 did the same).
# Disabled styles (settings.disabledStyles): the style loses its own block
# but its domains stay "known", so they do not fall back to the generic
# style; a disabled "gist.x.com" leaves gist.x.com without any style (x.com's
# block keeps refusing it). genericStyle=false drops the generic block,
# including for the extra hosts css-mapping.json gives to example.com.css.
# Differences with v0 (see tests/py/test_sites.py): hyphens are not escaped
# (css_rx_escape), keys are normalised and invalid mapping targets dropped
# (sites_load), the alternations are ordered deterministically, the comments
# are in English, and disabled or broken styles only lose their own block.
# data/styles.json is the upstream file minus the keys hitting the
# project's name denylist (tests/py/test_leaks.py); the data updater must
# keep applying it.
SITES_STYLES_FILE = "styles.json"
SITES_MAPPING_FILE = "css-mapping.json"
SITES_GENERIC_KEY = "example.com.css"
SITES_KEEP = re.compile(r"transparen|glass|translucent", re.I)
SITES_HEADER = "/* Site styles: sameerasw/my-internet (MIT); generated, do not edit */"
SITES_GENERIC_COMMENT = "/* Other sites: generic style (example.com.css) */"

# styles: {key "name.css": {feature: css}} in file order, keys normalised;
# mapping: {key "name.css": [host]} from css-mapping.json.
Sites = collections.namedtuple("Sites", "styles mapping")
# What build and list share: the effective dedicated styles.
#   suffix  {domain: key}   plain / "+" / "www." styles
#   dash    {base: key}     "-" styles (base = name without "-" and last label)
#   mapped  [(key, [host])] mapping entries whose style has css, file order
#   css     {key: css}      kept css of every style with some
_SitesIndex = collections.namedtuple("_SitesIndex", "suffix dash mapped css")


def _site_key_name(key):
    """Normalised style name of a styles.json / css-mapping.json key, or None."""
    if not isinstance(key, str):
        return None
    name = key.strip()
    if name.lower().endswith(".css"):
        name = name[:-4]
    name = name.strip().lower()
    return name if _SITE_NAME.fullmatch(name) else None


def sites_load(data_dir):
    """Sites from `data_dir`/styles.json (required) and css-mapping.json
    (optional: missing or corrupt gives no mapping, as in v0).

    Keys lose surrounding whitespace (around the name and the ".css",
    upstream has "bestbuy.com .css") and are lowercased; a key that still
    fails defs.site_name is dropped, and when a normalised key collides with
    an untouched one the untouched key wins. Features that are not strings
    are dropped. Mapping targets are stripped and lowercased; targets that
    fail defs.site_domain ("-cifraclub.com.br") are dropped.
    Raises OSError or ValueError when styles.json is unusable.
    """
    doc = json.loads(read_text(os.path.join(data_dir, SITES_STYLES_FILE), DATA_READ_LIMIT))
    website = doc.get("website") if isinstance(doc, dict) else None
    if not isinstance(website, dict):
        raise ValueError("styles.json has no \"website\" object")
    entries = []
    untouched = set()
    for key, features in website.items():
        name = _site_key_name(key)
        if name is None or not isinstance(features, dict):
            continue
        norm = name + ".css"
        features = collections.OrderedDict(
            (f, css) for f, css in features.items() if isinstance(f, str) and isinstance(css, str))
        entries.append((norm, features, norm == key))
        if norm == key:
            untouched.add(norm)
    styles = collections.OrderedDict()
    for norm, features, is_untouched in entries:
        if is_untouched or (norm not in untouched and norm not in styles):
            styles[norm] = features
    mapping = collections.OrderedDict()
    try:
        raw = json.loads(read_text(os.path.join(data_dir, SITES_MAPPING_FILE), DATA_READ_LIMIT))
    except (OSError, ValueError, RecursionError):
        raw = {}
    for key, targets in (raw.items() if isinstance(raw, dict) else ()):
        name = _site_key_name(key)
        if name is None or not isinstance(targets, list):
            continue
        hosts = mapping.setdefault(name + ".css", [])
        for target in targets:
            host = target.strip().lower() if isinstance(target, str) else ""
            if _SITE_HOST.fullmatch(host) and host not in hosts:
                hosts.append(host)
    return Sites(styles, mapping)


def _sites_feature_css(features):
    return "\n".join(css for name, css in features.items() if SITES_KEEP.search(name))


def _sites_index(sites, generic=True):
    """The _SitesIndex of `sites` (the generic style left out when not `generic`)."""
    suffix = {}
    dash = {}
    css = {}
    for key, features in sites.styles.items():
        if key == SITES_GENERIC_KEY and not generic:
            continue
        text = _sites_feature_css(features)
        if not text.strip():
            continue
        css[key] = text
        name = key[:-4]
        if name.startswith("-"):
            base = name[1:].rsplit(".", 1)[0]
            if _SITE_HOST.fullmatch(base):
                dash[base] = key
        else:
            domain = name.lstrip("+")
            domain = domain[4:] if domain.startswith("www.") else domain
            if not _SITE_HOST.fullmatch(domain):
                continue
            # The plain name wins over "+" (the extension stops on it).
            if domain not in suffix or not name.startswith("+"):
                suffix[domain] = key
    mapped = []
    for key, targets in sites.mapping.items():
        if key not in css:
            continue
        hosts = [t for t in targets if not _covered(t, suffix)]
        if hosts:
            mapped.append((key, hosts))
    return _SitesIndex(suffix, dash, mapped, css)


def _covered(host, domains):
    """True when `host` is one of `domains` or a subdomain of one."""
    if host in domains:
        return True
    labels = host.split(".")
    return any(".".join(labels[i:]) in domains for i in range(1, len(labels)))


def _deeper_domains(suffix):
    """{domain: [suffix domains that are subdomains of it]}."""
    deeper = collections.defaultdict(list)
    for domain in suffix:
        labels = domain.split(".")
        for i in range(1, len(labels)):
            parent = ".".join(labels[i:])
            if parent in suffix:
                deeper[parent].append(domain)
    return deeper


def sites_build_css(sites, excluded=(), disabled=(), generic=True, problems=None):
    """userContent CSS of the site styles: one @-moz-document regexp() block
    per dedicated style, per mapping entry, then the generic style. "" when
    there is nothing to emit.

    `excluded`: domains (normalize_domain) refused by every block.
    `disabled`: style names (normalize_style_name) whose block is left out;
    their domains still count as known, so the generic style does not take
    over a site whose dedicated style was turned off.
    `generic`: emit the generic style (example.com.css) for the other sites.
    A style whose css fails sites_validate() is treated like a disabled one;
    "<key>: <problem>" strings are appended to `problems` when given.
    """
    index = _sites_index(sites, generic)
    excluded = [d for d in (normalize_domain(x) for x in excluded) if d]
    skip = {name + ".css" for name in (normalize_style_name(x) for x in disabled) if name}
    for key, text in sorted(index.css.items()):
        errors = sites_validate(text)
        if errors:
            skip.add(key)
            if problems is not None:
                problems.extend("%s: %s" % (key, error) for error in errors)
    neg_excl = exclusion_lookahead(excluded)
    end = "(?:[:/].*)?"
    any_sub = "(?:[^/]*\\\\.)?"
    www = "(?:www\\\\.)?"
    out = [SITES_HEADER]

    def block(comment, rx, text):
        out.append('/* %s */\n@-moz-document regexp("%s") {\n%s\n}' % (comment, rx, text))

    deeper = _deeper_domains(index.suffix)
    for domain, key in sorted(index.suffix.items()):
        if key in skip:
            continue
        neg = ""
        if deeper.get(domain):
            neg = "(?!%s(?:%s)(?:[:/]|$))" % (any_sub, css_rx_alt(deeper[domain]))
        block(key, "https?://%s%s%s%s%s" % (neg_excl, neg, any_sub, css_rx_escape(domain), end),
              index.css[key])
    for base, key in sorted(index.dash.items()):
        if key in skip:
            continue
        block(key, "https?://%s%s%s\\\\.[^./:]+%s" % (neg_excl, www, css_rx_escape(base), end),
              index.css[key])
    for key, hosts in index.mapped:
        if key in skip:
            continue
        block("%s (mapping)" % key,
              "https?://%s%s(?:%s)%s" % (neg_excl, www, css_rx_alt(hosts), end), index.css[key])
    if generic and SITES_GENERIC_KEY in index.css and SITES_GENERIC_KEY not in skip:
        known = []
        if index.suffix:
            known.append("%s(?:%s)(?:[:/]|$)" % (any_sub, css_rx_alt(index.suffix)))
        if index.dash:
            known.append("%s(?:%s)\\\\.[^./:]+(?:[:/]|$)" % (www, css_rx_alt(index.dash)))
        hosts = [h for _, mapped_hosts in index.mapped for h in mapped_hosts]
        if hosts:
            known.append("%s(?:%s)(?:[:/]|$)" % (www, css_rx_alt(hosts)))
        lookahead = "(?!%s)" % "|".join(known) if known else ""
        out.append('%s\n@-moz-document regexp("https?://%s%s.*") {\n%s\n}' % (
            SITES_GENERIC_COMMENT, neg_excl, lookahead, index.css[SITES_GENERIC_KEY]))
    if len(out) == 1:
        return ""
    return "\n\n".join(out) + "\n"


def sites_list(sites):
    """The dedicated styles as the contract's sites.json: [{name, domains}],
    sorted by domain then name. The generic style, styles without kept css
    and styles shadowed by another one (a "+x.com" next to "x.com") are not
    listed: turning them off would change nothing."""
    index = _sites_index(sites, generic=False)
    extra = collections.defaultdict(list)
    for key, hosts in index.mapped:
        extra[key].extend(hosts)
    rows = []
    for domain, key in index.suffix.items():
        rows.append((domain, key, [domain, "*." + domain]))
    for base, key in index.dash.items():
        rows.append((base, key, [base + ".*", "www." + base + ".*"]))
    rows.sort(key=lambda row: (row[0], row[1]))
    return [{"name": key[:-4], "domains": _unique(domains + extra.get(key, []))}
            for _, key, domains in rows]


# CSS scanning for sites_validate. A style is wrapped in its own
# @-moz-document block, so the scan must see the stylesheet's structure
# exactly as Firefox does (CSS Syntax 3, sections 3.3 to 4.3); otherwise a
# style could close its block early and style every page, excluded sites and
# about: pages included. What counts:
#   - preprocessing: CRLF, CR and FF are newlines, NUL is U+FFFD;
#   - comments, and strings (a string also ends, broken, at a newline);
#   - an escape (backslash + any code point but a newline) is a name
#     character, outside strings too: "\{" is part of an identifier;
#   - url( + an unquoted argument is ONE token up to ")": braces, quotes and
#     "/*" inside it are not structure;
#   - identifiers, at-keywords and function names are compared after
#     unescaping ("@\69mport" is @import, "r\65gexp(" is regexp();
#   - {} () [] must nest properly (a "}" inside "( )" does not close a
#     block for Firefox, so a mismatch is refused rather than guessed).
# Plain words are skipped by the regex engine itself, which keeps the scan
# of the ~1 MB embedded data fast.
_CSS_NAME = "[A-Za-z0-9_\\-\x80-\U0010ffff]"
_CSS_ESC = "\\\\(?:[0-9A-Fa-f]{1,6}[ \\t\\n]?|[^\\n])"
_CSS_SCAN = re.compile(
    "(?P<comment>/\\*)"
    "|(?P<quote>[\"'])"
    "|(?P<open>[{(\\[])"
    "|(?P<close>[})\\]])"
    "|(?P<sigil>[@#])(?P<name>(?:%(n)s|%(e)s)+)"
    "|(?<![A-Za-z0-9_\\-\x80-\U0010ffff#@])"
    "(?P<word>%(n)s*%(e)s(?:%(n)s|%(e)s)*|[Uu][Rr][Ll](?=\\()|[Rr][Ee][Gg][Ee][Xx][Pp](?=\\())"
    "(?P<call>\\()?" % {"n": _CSS_NAME, "e": _CSS_ESC})
_CSS_STRING_END = {
    '"': re.compile(r'(?:[^"\\\n]|\\[\s\S]|\\\Z)*("|\n|\Z)'),
    "'": re.compile(r"(?:[^'\\\n]|\\[\s\S]|\\\Z)*('|\n|\Z)"),
}
_CSS_URL_END = re.compile(r"(?:[^)\\]|\\[\s\S]|\\\Z)*(\)|\Z)")
_CSS_SPACES = re.compile(r"[ \t\n]*")
_CSS_PAIRS = {"}": "{", ")": "(", "]": "["}
_CSS_ESCAPE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?|(\r\n|[\n\r\f])|([\s\S]))")
_ASCII_LOWER = {c: c + 32 for c in range(65, 91)}
# Regexp tokens for the Unicode-mode check (what Firefox's regexp() uses).
_JS_RX_TOKEN = re.compile(
    r"\\(?:u\{[0-9A-Fa-f]+\}|u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|c[A-Za-z]|[pP]\{[^}]*\}"
    r"|k<[^>]*>|[0-9]+|[\s\S]?)"
    r"|\((?:\?(?:<[=!]|<[A-Za-z_$][\w$]*>|[:=!])?)?"
    r"|\)|\[|\]|\{(?:[0-9]+(?:,[0-9]*)?\})?|\}|[*+?^$|]")
_JS_RX_ESCAPES = set("^$\\.*+?()[]{}|/fnrtvdDsSwWbB0")
_JS_RX_CLASS_ESCAPES = (_JS_RX_ESCAPES - set("B")) | {"-"}


def css_preprocess(text):
    """`text` after CSS input preprocessing (CRLF, CR, FF -> LF; NUL -> U+FFFD)."""
    return (text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
            .replace("\0", "\ufffd"))


def css_unescape(text):
    """The value of CSS string or name content `text` (backslash escapes
    resolved)."""
    def repl(match):
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "\ufffd"
        if match.group(2):
            return ""
        return match.group(3)
    return _CSS_ESCAPE.sub(repl, text)


def _css_name_is(raw, word):
    """True when the CSS name `raw` (escapes allowed) is `word`, compared
    ASCII case-insensitively as CSS does."""
    value = css_unescape(raw) if "\\" in raw else raw
    return value.translate(_ASCII_LOWER) == word


def js_regexp_problem(pattern):
    """Why `pattern` is not a valid JavaScript regexp in Unicode mode, or None.

    Checked: what Python's re accepts but Unicode mode refuses (identity
    escapes of non-syntax characters such as "\\-" outside a class or "\\a";
    incomplete \\x \\u \\c escapes; lone "{" "}" "]"; "(?" groups other than
    (?: (?= (?! (?<= (?<! (?<name>; possessive or doubled quantifiers; a
    quantifier on an assertion or on nothing; decimal escapes that are not
    a backreference to an existing group), and a few things Python refuses
    anyway. Python's re.compile() covers the rest. Erring on the side of
    refusing is safe: a refused style is only left out.
    """
    tokens = list(_JS_RX_TOKEN.finditer(pattern))
    groups = 0
    in_class = False
    for match in tokens:
        token = match.group()
        if in_class:
            in_class = token != "]"
        elif token == "[":
            in_class = True
        elif token == "(" or (token.startswith("(?<") and token[3] not in "=!"):
            groups += 1
    in_class = False
    stack = []
    # What the previous token was, for the quantifier checks: "atom", "quant"
    # (a quantifier), "lazy" (a quantifier and its "?"), "none" (nothing to
    # repeat: start, "(", "|", an assertion).
    prev = "none"
    prev_end = 0
    for match in tokens:
        token = match.group()
        if match.start() > prev_end:
            prev = "atom"
        prev_end = match.end()
        if in_class:
            if token == "]":
                in_class = False
                prev = "atom"
            elif token.startswith("\\"):
                if len(token) == 1:
                    return "trailing backslash"
                if token[1].isdigit() and token != "\\0":
                    return "invalid class escape %r at %d" % (token, match.start())
                if len(token) == 2 and token[1] not in _JS_RX_CLASS_ESCAPES:
                    return "invalid escape %r at %d" % (token, match.start())
            continue
        if token.startswith("\\"):
            if len(token) == 1:
                return "trailing backslash"
            if token[1].isdigit():
                if token[1] == "0":
                    if len(token) > 2:
                        return "invalid escape %r at %d" % (token, match.start())
                elif int(token[1:]) > groups:
                    return "backreference %r to a missing group at %d" % (token, match.start())
            elif len(token) == 2 and token[1] not in _JS_RX_ESCAPES:
                return "invalid escape %r at %d" % (token, match.start())
            prev = "none" if token in ("\\b", "\\B") else "atom"
        elif token == "[":
            in_class = True
        elif token == "]":
            return "lone ']' at %d" % match.start()
        elif token == "{" or token == "}":
            return "lone %r at %d" % (token, match.start())
        elif token.startswith("("):
            if token == "(?":
                return "unsupported group '(?' at %d" % match.start()
            stack.append(token)
            prev = "none"
        elif token == ")":
            if not stack:
                return "lone ')' at %d" % match.start()
            opener = stack.pop()
            prev = "none" if opener in ("(?=", "(?!", "(?<=", "(?<!") else "atom"
        elif token in ("^", "$", "|"):
            prev = "none"
        elif token == "?" and prev == "quant":
            prev = "lazy"
        else:  # * + ? {n,m}
            if prev != "atom":
                return "nothing to repeat at %d" % match.start()
            prev = "quant"
    if in_class:
        return "unterminated class"
    if stack:
        return "unterminated group"
    return None


def sites_validate(css):
    """Problems found in a stylesheet (a list of strings, [] when fine).

    The stylesheet is scanned as Firefox tokenizes it (see above), and
    refused for: {} () [] that do not nest properly, an unterminated
    comment, string or url(), an @import (it could pull in anything), and
    each regexp() whose argument is not a string, or whose pattern
    (CSS-unescaped) does not compile with Python's re or breaks JavaScript
    Unicode-mode rules (Firefox: an invalid regexp() matches EVERY page).
    Positions are offsets in the preprocessed text (css_preprocess).
    """
    css = css_preprocess(css)
    problems = []
    stack = []
    pos = 0
    n = len(css)
    while pos < n:
        match = _CSS_SCAN.search(css, pos)
        if not match:
            break
        start = match.start()
        pos = match.end()
        kind = match.lastgroup
        if kind == "comment":
            end = css.find("*/", pos)
            if end < 0:
                problems.append("unterminated comment at %d" % start)
                break
            pos = end + 2
        elif kind == "quote":
            pos = _css_string(css, start, problems)
        elif kind == "open":
            stack.append(match.group())
        elif kind == "close":
            if stack and stack[-1] == _CSS_PAIRS[match.group()]:
                stack.pop()
            else:
                problems.append("unbalanced %r at %d" % (match.group(), start))
        elif match.group("sigil"):
            if match.group("sigil") == "@" and _css_name_is(match.group("name"), "import"):
                problems.append("@import at %d" % start)
        elif match.group("call"):
            word = match.group("word")
            gap = _CSS_SPACES.match(css, pos).end()
            quoted = css[gap:gap + 1] in ('"', "'")
            if _css_name_is(word, "url") and not quoted:
                url = _CSS_URL_END.match(css, pos)
                if not url.group(1):
                    problems.append("unterminated url( at %d" % start)
                pos = url.end()
                continue
            stack.append("(")
            if _css_name_is(word, "regexp"):
                if quoted:
                    pos = _css_string(css, gap, problems, _check_regexp)
                else:
                    problems.append("regexp() without a string at %d" % start)
    if stack:
        problems.append("%d unclosed %s" % (len(stack), " ".join(repr(c) for c in stack)))
    return problems


def _css_string(css, start, problems, check=None):
    """Scan the string starting with the quote at `start`; returns the
    position after it. `check(value, problems)` is applied to its value."""
    quote = css[start]
    string = _CSS_STRING_END[quote].match(css, start + 1)
    if string.group(1) != quote:
        problems.append("unterminated string at %d" % start)
        return string.end()
    if check is not None:
        check(css_unescape(css[start + 1:string.start(1)]), problems)
    return string.end()


def _check_regexp(pattern, problems):
    if not pattern:
        problems.append("empty regexp()")
        return
    try:
        re.compile(pattern)
    except (re.error, RecursionError, OverflowError) as exc:
        problems.append("regexp %r...: %s" % (pattern[:40], exc))
        return
    problem = js_regexp_problem(pattern)
    if problem:
        problems.append("regexp %r...: %s" % (pattern[:40], problem))


# ============================================================================
# edits
# ============================================================================

# Text edits of the user's files. Pure functions: text in, text out.
_LINE = re.compile(r"[^\n]*\n|[^\n]+")
_CHARSET_AT_START = re.compile(r'@charset "[^"\n]*";')
_USERJS_OWN_PREF = re.compile(
    r'\s*user_pref\(\s*"(?:%s)"\s*,' % "|".join(re.escape(p) for p in PREFS))


def _lines(text):
    """Lines of `text`, each keeping its "\\n" (split on "\\n" only)."""
    return _LINE.findall(text)


def _line_body(line):
    """A line without its "\\n" / "\\r\\n" and trailing blanks."""
    return line.rstrip("\n").rstrip("\r").rstrip()


def _newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def _import_matcher(import_line):
    """Regex recognising `import_line` (@import "name.css";) and its usual
    variants: url(...), single quotes, other spacing, any case of @import."""
    name = re.search(r'"([^"]+)"', import_line).group(1)
    return re.compile(
        r"\s*@import\s+(?:url\(\s*)?(?P<q>[\"']?)%s(?P=q)\s*\)?\s*;\s*" % re.escape(name), re.I)


def _split_bom(text):
    """(bom, rest): a leading U+FEFF is kept apart so that the first line is
    recognised like the others and the BOM is put back untouched."""
    if text.startswith("\ufeff"):
        return "\ufeff", text[1:]
    return "", text


# What may come before an effective @import: blanks, comments, @charset,
# other @import and @layer statements (CSS Cascade 5).
_CSS_PRELUDE = re.compile(
    r"(?:\s+|/\*[\s\S]*?\*/|@(?:charset|import|layer)\b[^;{}]*;)*", re.I)


def has_import(text, import_line):
    """True when a whole line of `text` imports what `import_line` imports."""
    matcher = _import_matcher(import_line)
    return any(matcher.fullmatch(_line_body(line)) for line in _lines(_split_bom(text)[1]))


def _import_in_place(text, matcher):
    """True when a line matching `matcher` sits where Firefox honours it:
    in the leading prelude, and not before an @charset rule."""
    prelude = _CSS_PRELUDE.match(text).end()
    offset = 0
    for line in _lines(text):
        stop = offset + len(line)
        if offset >= prelude:
            return False
        if matcher.fullmatch(_line_body(line)) and stop <= prelude:
            return not re.search(r"@charset\b", text[stop:prelude], re.I)
        offset = stop
    return False


def ensure_import(text, import_line):
    """`text` (userChrome.css / userContent.css) with `import_line`.

    Unchanged when an equivalent line is already there in a place Firefox
    honours (v0 and v1 write the same line). Otherwise any misplaced copy is
    removed and the line goes first, or right after a leading @charset rule
    (which must stay the very first thing of the file), with the file's own
    line ending. A leading BOM stays first.

    Known normalisation: a file whose @charset rule has no line ending gets
    one; strip_import() then leaves it (the P3 backup restores bytes).
    """
    bom, text = _split_bom(text)
    matcher = _import_matcher(import_line)
    if _import_in_place(text, matcher):
        return bom + text
    text = strip_import(text, import_line)
    nl = _newline_of(text)
    charset = _CHARSET_AT_START.match(text)
    if charset:
        pos = charset.end()
        if text.startswith("\r\n", pos):
            pos += 2
        elif text.startswith("\n", pos):
            pos += 1
        else:
            return bom + text[:pos] + nl + import_line + nl + text[pos:]
        return bom + text[:pos] + import_line + nl + text[pos:]
    return bom + import_line + nl + text


def strip_import(text, import_line):
    """`text` without the lines importing what `import_line` imports (the
    rest, a leading BOM included, is kept byte for byte)."""
    bom, text = _split_bom(text)
    matcher = _import_matcher(import_line)
    return bom + "".join(
        line for line in _lines(text) if not matcher.fullmatch(_line_body(line)))


def _block_spans(lines, markers):
    """[(start, end)] line ranges (end exclusive) of the managed blocks.

    A block runs from a begin marker line to its own end marker line. A begin
    marker without its end marker (before the next begin marker or the end
    of the file) only takes the lines right after it that set one of PREFS:
    the rest of the file is never eaten. A lone end marker is a span of its
    own.
    """
    begins = dict(markers)
    ends = set(begins.values())
    spans = []
    i = 0
    n = len(lines)
    while i < n:
        body = _line_body(lines[i])
        if body in begins:
            end_marker = begins[body]
            j = i + 1
            while j < n and _line_body(lines[j]) != end_marker and _line_body(lines[j]) not in begins:
                j += 1
            if j < n and _line_body(lines[j]) == end_marker:
                spans.append((i, j + 1))
                i = j + 1
                continue
            j = i + 1
            while j < n and _USERJS_OWN_PREF.match(lines[j]):
                j += 1
            spans.append((i, j))
            i = j
            continue
        if body in ends:
            spans.append((i, i + 1))
        i += 1
    return spans


def strip_block(text, markers=USERJS_BLOCK_MARKERS):
    """`text` (user.js) without any managed block, v0 or v1 (see _block_spans).
    A leading BOM is kept."""
    bom, text = _split_bom(text)
    lines = _lines(text)
    drop = set()
    for start, end in _block_spans(lines, markers):
        drop.update(range(start, end))
    return bom + "".join(line for i, line in enumerate(lines) if i not in drop)


def replace_block(text, block, markers=USERJS_BLOCK_MARKERS):
    """`text` (user.js) with `block` (userjs_block()) as its only managed block.

    The block takes the place of the first existing one (v0 or v1), the
    others are removed; without any, it is appended at the end. The block
    uses the file's line ending. A leading BOM is kept.
    """
    bom, text = _split_bom(text)
    nl = _newline_of(text)
    if nl != "\n":
        block = block.replace("\n", nl)
    lines = _lines(text)
    spans = _block_spans(lines, markers)
    if not spans:
        if text and not text.endswith("\n"):
            text += nl
        return bom + text + block
    drop = set()
    for start, end in spans:
        drop.update(range(start, end))
    first = spans[0][0]
    out = []
    for i, line in enumerate(lines):
        if i == first:
            if out and not out[-1].endswith("\n"):
                out[-1] += nl
            out.append(block)
        if i not in drop:
            if i > first and out and not out[-1].endswith("\n"):
                out[-1] += nl
            out.append(line)
    return bom + "".join(out)

# ============================================================================
# state
# ============================================================================

# $XDG_STATE_HOME/dms/browserGlass/
#   state.lock   flock'ed (LOCK_EX) by every mutating command (sync, uninstall)
#   state.json   STATE_VERSION document, written atomically and only when
#                its text changes (sorted keys, no timestamps), so a sync
#                that changes nothing writes nothing:
#     version         STATE_VERSION
#     profiles        {profile_id: record}
#       path, family, variant   where the profile was last seen
#       prefs_original  {pref: {"absent": true} | {"value": JS literal}}
#                       read from prefs.js on first contact (H2)
#       owned_prefs     prefs our user.js block sets
#       restore_prefs   prefs that left the block (siteTheme "none", H3) and
#                       still wait for their original value in prefs.js
#                       (written only while the browser is closed)
#       applied_hash    hash of what the last sync wrote (None if a write failed)
#       instance        "pid:starttime" of the browser running on the profile
#                       ("?" when unknown), None when it is closed
#       glass_loaded_since_start   that browser started with glass CSS (H1)
#     backups         {profile_id: backup record}, also kept as
#                     backup/<profile_id>/meta.json
#       path, chrome_dir (the chrome folder existed before us)
#       files {name: {"existed", "mode", "sha256"}}
#       prefs_original  the profile's prefs_original at first contact (H2):
#                       meta.json is never rewritten, so the originals
#                       survive a lost or corrupt state.json
#     niri            {"include_added", "config_eol"}
#     created_dirs    folders made for the state, removed by uninstall
#     synced          a sync ran since the last uninstall (first_run)
#   backup/<profile_id>/{userChrome.css,userContent.css,user.js}
#                original files without any v0/v1 addition (H4), taken once
#                before the first write, never overwritten
#   pending/<profile_id>.json
#                written by uninstall for a profile whose prefs.js cleanup
#                waits for the browser to close (H6): {version, path, plan
#                ([[pref, literal or null]], or null for the v0 rule applied
#                at write time), prefs_original, created_dirs}. The detached
#                cleaner removes it (and the emptied folders) once done; a
#                sync taking the profile back (re-enable while the browser
#                runs) reuses its prefs_original instead of reading prefs.js,
#                which still holds our values; a later uninstall or
#                clean-prefs picks it up again if the cleaner died. A state
#                whose only content is pending/ counts as removed.
STATE_VERSION = 1
BACKUP_META = "meta.json"
PENDING_DIR = "pending"
_PID = re.compile(r"[0-9a-f]{12}")
# Environment knobs (tests use them to stay fast).
ENV_LOCK_TIMEOUT = "BG_LOCK_TIMEOUT"   # seconds to wait for state.lock
ENV_POLL_INTERVAL = "BG_POLL_INTERVAL"  # seconds between clean-prefs probes
ENV_POLL_MAX = "BG_POLL_MAX"            # seconds before clean-prefs gives up
ENV_SWEEP_GRACE = "BG_SWEEP_GRACE"      # seconds uninstall --if-gone waits
ENV_PLUGIN_RECHECK = "BG_PLUGIN_RECHECK"  # seconds sync --if-plugin waits to trust a missing file
DEFAULT_LOCK_TIMEOUT = 2.0
# uninstall waits longer: it runs once, unattended (plugin disabled or its
# folder deleted), and must not fail because a sync is still running.
UNINSTALL_LOCK_TIMEOUT = 120.0
# A plugin update or reinstall replaces the folder within seconds: the sweep
# waits that long before it trusts a missing plugin.json.
DEFAULT_SWEEP_GRACE = 4.0
# A git checkout deletes and recreates a modified plugin.json: sync
# --if-plugin looks again after this long before it refuses.
DEFAULT_PLUGIN_RECHECK = 0.5
DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_POLL_MAX = 7 * 24 * 3600.0
LOCK_RETRY_STEP = 0.05
# A stale temporary file is swept only when older than this (seconds): a
# clean-prefs running outside the state lock may own a fresh one.
STALE_TMP_AGE = 600
# Temporary files write_if_changed() leaves behind after a hard stop.
# Only our own prefix, a file name we write and the exact mkstemp alphabet.
_STALE_TMP = re.compile(
    re.escape(TMP_PREFIX)
    + r"(?:userChrome\.css|userContent\.css|user\.js|prefs\.js|dms-glass-chrome\.css|"
    r"dms-glass-content\.css|config\.kdl|dms-browser-glass\.kdl|state\.json|meta\.json|"
    r"[0-9a-f]{12}\.json)"
    r"\.[a-z0-9_]{8}" + re.escape(TMP_SUFFIX))
# One user_pref line of prefs.js / user.js: name and raw value literal.
_PREF_LINE = re.compile(r'\s*user_pref\(\s*"((?:[^"\\\n]|\\.)*)"\s*,\s*(.*?)\s*\)\s*;\s*')
# Files of a profile we edit, relative to the profile folder.
PROFILE_FILES = (
    (USERCHROME_CSS, os.path.join(CHROME_DIR, USERCHROME_CSS)),
    (USERCONTENT_CSS, os.path.join(CHROME_DIR, USERCONTENT_CSS)),
    (USER_JS, USER_JS),
)
_FILE_IMPORT = {USERCHROME_CSS: V1_IMPORT_CHROME, USERCONTENT_CSS: V1_IMPORT_CONTENT}
_V0_GLASS_PREFIX = V0_CSS_HEADER_GLASS.split("{opacity}")[0]
_V1_GLASS_MARK = "/* glass active"

WARN_WRITE_FAILED = "write_failed"
WARN_READ_FAILED = "read_failed"
WARN_DATA_UNAVAILABLE = "data_unavailable"
WARN_SITE_STYLE = "site_style_invalid"
WARN_STATE_CORRUPT = "state_corrupt"
WARN_BACKUP_FAILED = "backup_failed"
WARN_BACKUP_KEPT = "backup_kept"
WARN_FORK_FAILED = "fork_failed"
WARN_PROFILE_MISSING = "profile_missing"
WARN_DANGLING_LINK = "dangling_link"
WARN_STATE_UNAVAILABLE = "state_unavailable"


class StateBusy(Exception):
    """state.lock is held by another browserGlass command."""


class StateNewer(Exception):
    """state.json was written by a newer browserGlass: never overwrite it."""


def env_seconds(env, name, default):
    """A positive number of seconds from `env`[name], else `default`."""
    try:
        value = float(env.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value >= 0 else default


def state_dir(env=None):
    return os.path.join(xdg_dir("XDG_STATE_HOME", env), STATE_DIR_REL)


def v0_cache_dir(env=None):
    return os.path.join(xdg_dir("XDG_CACHE_HOME", env), V0_CACHE_REL)


def niri_dir(env=None):
    return os.path.join(xdg_dir("XDG_CONFIG_HOME", env), NIRI_DIR_REL)


def make_dirs_tracked(path, mode=0o700):
    """os.makedirs(path) returning the folders it created, top first."""
    missing = []
    current = os.path.abspath(path)
    while not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    created = []
    for folder in reversed(missing):
        try:
            os.mkdir(folder, mode)
        except FileExistsError:
            continue
        created.append(folder)
    return created


def state_lock(folder, env=None, default_timeout=DEFAULT_LOCK_TIMEOUT):
    """An fd holding flock(LOCK_EX) on `folder`/state.lock.

    Non-blocking attempts every LOCK_RETRY_STEP for $BG_LOCK_TIMEOUT seconds
    (else `default_timeout`), then StateBusy. The lock file is checked to still be the one at the path
    once locked (uninstall removes it while a sync waits). Raises OSError.
    """
    env = os.environ if env is None else env
    path = os.path.join(folder, STATE_LOCK)
    deadline = time.monotonic() + env_seconds(env, ENV_LOCK_TIMEOUT, default_timeout)
    while True:
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        except FileNotFoundError:
            make_dirs_tracked(folder)
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                raise
            if time.monotonic() >= deadline:
                raise StateBusy()
            time.sleep(LOCK_RETRY_STEP)
            continue
        try:
            same = os.stat(path, follow_symlinks=False).st_ino == os.fstat(fd).st_ino
        except FileNotFoundError:
            same = False
        if same:
            return fd
        os.close(fd)


def new_state(synced=False):
    return {"version": STATE_VERSION, "profiles": {}, "backups": {},
            "niri": {"include_added": False, "config_eol": True}, "created_dirs": [],
            "synced": synced, "last_sync": None}


# Settings whose effect last_sync["glass"] already records (blur and isLight
# through reason and mode, opacity through glass.opacity): left out, so a
# change that alters no output (the slider moved while the override is off)
# leaves state.json untouched.
_LAST_SYNC_SKIP = ("blur", "isLight", "opacity")
_WARNING_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
OPACITY_SOURCES = ("dms", "override", "forced")


def last_sync_record(settings, glass, warnings):
    """state.json "last_sync": what the last FULL sync (no --profile)
    decided, shown by status and report so that they describe what is on
    disk: the settings that change the output (minus _LAST_SYNC_SKIP), the
    status.glass document and the warning codes of that sync. A sync whose
    settings differ but whose output is the same still rewrites state.json
    when one of the recorded settings (excluded, disabledStyles...) changed."""
    return {"settings": {k: v for k, v in settings.items() if k not in _LAST_SYNC_SKIP},
            "glass": dict(glass),
            "warning_codes": _unique(w["code"] for w in warnings)}


def _norm_glass(value):
    if not isinstance(value, dict):
        return None
    active, reason, opacity = value.get("active"), value.get("reason"), value.get("opacity")
    source, surface, mode = value.get("opacity_source"), value.get("surface"), value.get("mode")
    if not isinstance(active, bool) or reason not in REASONS or (reason == "active") != active:
        return None
    if isinstance(opacity, bool) or not isinstance(opacity, (int, float)) \
            or not math.isfinite(opacity) or not 0.0 <= opacity <= 1.0:
        return None
    if source not in OPACITY_SOURCES or mode not in MODES or not isinstance(surface, str) \
            or not re.fullmatch(r"#[0-9a-f]{6}", surface):
        return None
    return collections.OrderedDict([
        ("active", active), ("reason", reason), ("opacity", float(opacity)),
        ("opacity_source", source), ("surface", surface), ("mode", mode)])


def _norm_last_sync(value):
    """last_sync_record() read back from state.json; None when unusable."""
    if not isinstance(value, dict) or not isinstance(value.get("settings"), dict):
        return None
    glass = _norm_glass(value.get("glass"))
    if glass is None:
        return None
    settings = settings_from_json(value["settings"])
    codes = value.get("warning_codes")
    codes = codes if isinstance(codes, list) else []
    return {"settings": {k: v for k, v in settings.items() if k not in _LAST_SYNC_SKIP},
            "glass": glass,
            "warning_codes": _unique(c for c in codes
                                     if isinstance(c, str) and _WARNING_CODE.fullmatch(c))[:32]}


def _norm_prefs_original(value):
    out = {}
    if isinstance(value, dict):
        for pref in PREFS:
            item = value.get(pref)
            if isinstance(item, dict) and isinstance(item.get("value"), str):
                out[pref] = {"value": item["value"]}
            elif isinstance(item, dict):
                out[pref] = {"absent": True}
    return out


def _norm_pref_list(value):
    if not isinstance(value, list):
        return []
    return [p for p in PREFS if p in value]


def _norm_record(value):
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        return None
    family = value.get("family")
    variant = value.get("variant")
    instance = value.get("instance")
    applied = value.get("applied_hash")
    return {
        "path": value["path"],
        "family": family if family in FAMILIES else None,
        "variant": variant if variant in VARIANTS else None,
        "prefs_original": _norm_prefs_original(value.get("prefs_original")),
        "owned_prefs": _norm_pref_list(value.get("owned_prefs")),
        "restore_prefs": _norm_pref_list(value.get("restore_prefs")),
        "applied_hash": applied if isinstance(applied, str) else None,
        "instance": instance if isinstance(instance, str) else None,
        "glass_loaded_since_start": value.get("glass_loaded_since_start") is True,
    }


def _norm_backup(value):
    if not isinstance(value, dict) or not isinstance(value.get("files"), dict):
        return None
    files = {}
    for name, _ in PROFILE_FILES:
        item = value["files"].get(name)
        if not isinstance(item, dict):
            continue
        mode = item.get("mode")
        digest = item.get("sha256")
        files[name] = {
            "existed": item.get("existed") is True,
            "mode": mode if isinstance(mode, int) and not isinstance(mode, bool) else None,
            "sha256": digest if isinstance(digest, str) else None,
        }
    path = value.get("path")
    originals = value.get("prefs_original")
    return {"path": path if isinstance(path, str) else None,
            "chrome_dir": value.get("chrome_dir") is True, "files": files,
            "prefs_original": _norm_prefs_original(originals) if isinstance(originals, dict) else None}


def state_load(folder, warnings):
    """(state, existed) from `folder`/state.json. A missing file gives a new
    state (existed False); an unreadable or corrupt one a new state plus a
    "state_corrupt" warning (existed True; the profile records are then
    rebuilt from backup/*/meta.json). Unknown fields are dropped. A file of
    a newer STATE_VERSION raises StateNewer: it is never overwritten."""
    path = os.path.join(folder, STATE_FILE)
    try:
        doc = json.loads(read_text(path))
    except FileNotFoundError:
        return new_state(), False
    except (OSError, ValueError, RecursionError) as exc:
        warnings.append(make_warning(WARN_STATE_CORRUPT, "state.json unusable, starting afresh (%s)"
                                     % (getattr(exc, "strerror", None) or exc.__class__.__name__)))
        return new_state(synced=True), True
    state = new_state(synced=True)
    version = doc.get("version") if isinstance(doc, dict) else None
    if isinstance(version, int) and not isinstance(version, bool) and version > STATE_VERSION:
        raise StateNewer(version)
    if version != STATE_VERSION:
        warnings.append(make_warning(WARN_STATE_CORRUPT, "state.json has an unknown layout, starting afresh"))
        return state, True
    state["synced"] = doc.get("synced") is not False
    for key, norm in (("profiles", _norm_record), ("backups", _norm_backup)):
        items = doc.get(key)
        for pid, value in (items.items() if isinstance(items, dict) else ()):
            value = norm(value)
            if value is not None and _PID.fullmatch(pid):
                state[key][pid] = value
    niri = doc.get("niri")
    if isinstance(niri, dict):
        state["niri"]["include_added"] = niri.get("include_added") is True
        state["niri"]["config_eol"] = niri.get("config_eol") is not False
    created = doc.get("created_dirs")
    if isinstance(created, list):
        state["created_dirs"] = [d for d in created if isinstance(d, str) and os.path.isabs(d)]
    state["last_sync"] = _norm_last_sync(doc.get("last_sync"))
    return state, True


def state_text(state):
    return json.dumps(state, sort_keys=True, indent=1) + "\n"


def state_save(folder, state, warnings):
    """Write state.json when its text changed; a failure is a warning.
    Returns True when state.json holds `state` afterwards."""
    path = os.path.join(folder, STATE_FILE)
    text = state_text(state)
    before = len(warnings)
    try:
        write_if_changed(path, text, warnings, mode=0o600)
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "state.json not written: %s"
                                     % (exc.strerror or exc)))
    return len(warnings) == before


def backup_records(sdir, state):
    """Add to state["backups"] the backup/<pid>/meta.json records it lacks
    (state.json lost, corrupt or from before the backup)."""
    try:
        names = os.listdir(os.path.join(sdir, BACKUP_DIR))
    except OSError:
        return
    for pid in sorted(names):
        if not _PID.fullmatch(pid) or pid in state["backups"]:
            continue
        try:
            record = _norm_backup(json.loads(read_text(os.path.join(backup_folder(sdir, pid), BACKUP_META))))
        except (OSError, ValueError, RecursionError):
            record = None
        if record is not None:
            state["backups"][pid] = record


# ---- pending prefs.js cleanups (H6) ------------------------------------------

def pending_folder(sdir):
    return os.path.join(sdir, PENDING_DIR)


def pending_file(sdir, pid):
    return os.path.join(pending_folder(sdir), pid + ".json")


def _norm_plan(value):
    if not isinstance(value, list):
        return None
    plan = []
    for item in value:
        if (isinstance(item, list) and len(item) == 2 and item[0] in PREFS
                and (item[1] is None or isinstance(item[1], str))):
            plan.append((item[0], item[1]))
    return plan


def _norm_pending(value):
    if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
        return None
    if not isinstance(value.get("path"), str) or not os.path.isabs(value["path"]):
        return None
    originals = value.get("prefs_original")
    created = value.get("created_dirs")
    return {
        "path": value["path"],
        "plan": _norm_plan(value.get("plan")),
        "prefs_original": _norm_prefs_original(originals) if isinstance(originals, dict) else None,
        "created_dirs": [d for d in created if isinstance(d, str) and os.path.isabs(d)]
        if isinstance(created, list) else [],
    }


def pending_load(sdir):
    """{pid: pending record} of `sdir`/pending/ (unusable files are ignored)."""
    out = {}
    try:
        names = os.listdir(pending_folder(sdir))
    except OSError:
        return out
    for name in sorted(names):
        pid = name[:-len(".json")]
        if not name.endswith(".json") or not _PID.fullmatch(pid):
            continue
        try:
            record = _norm_pending(json.loads(read_text(os.path.join(pending_folder(sdir), name))))
        except (OSError, ValueError, RecursionError):
            record = None
        if record is not None:
            out[pid] = record
    return out


def pending_text(path, plan, originals, created_dirs):
    return state_text({
        "version": STATE_VERSION, "path": path,
        "plan": None if plan is None else [list(item) for item in plan],
        "prefs_original": originals, "created_dirs": sorted(set(created_dirs)),
    })


def pending_drop(sdir, pid, created_dirs=(), tidy=True):
    """Remove pending/<pid>.json; with `tidy` also the folders it leaves
    empty: pending/, the state folder and `created_dirs` (deepest first)."""
    try:
        os.unlink(pending_file(sdir, pid))
    except FileNotFoundError:
        pass
    _rmdir_quiet(pending_folder(sdir))
    if tidy:
        _rmdir_quiet(sdir)
        for folder in sorted(set(created_dirs), key=len, reverse=True):
            _rmdir_quiet(folder)


def _rmdir_quiet(path):
    try:
        os.rmdir(path)
    except OSError:
        pass


# ---- profile files ------------------------------------------------------------

def strip_ours(name, text):
    """`text` of the profile file `name` without any v0 or v1 addition."""
    if name == USER_JS:
        return strip_block(text)
    return strip_import(text, _FILE_IMPORT[name])


def apply_ours(name, text, block):
    """`text` of the profile file `name` with our v1 addition."""
    if name == USER_JS:
        return replace_block(text, block)
    return ensure_import(text, _FILE_IMPORT[name])


def read_optional(path):
    """read_text(path), or None when the file does not exist. Raises OSError."""
    try:
        return read_text(path)
    except FileNotFoundError:
        return None


def css_has_glass(text):
    """True when a generated chrome stylesheet (v0 or v1) carries glass."""
    if not text:
        return False
    return text.startswith(_V0_GLASS_PREFIX) or _V1_GLASS_MARK in text


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def backup_folder(sdir, pid):
    return os.path.join(sdir, BACKUP_DIR, pid)


def backup_take(sdir, pid, path, texts, prefs_original=None):
    """Back up the profile files (`texts`: {name: current text or None})
    without our additions into backup/<pid>/, once, with the profile's
    `prefs_original` (H2) in meta.json. Returns the backup record. Raises
    OSError."""
    folder = backup_folder(sdir, pid)
    meta_path = os.path.join(folder, BACKUP_META)
    if os.path.isdir(folder):
        try:
            record = _norm_backup(json.loads(read_text(meta_path)))
        except FileNotFoundError:
            # A hard stop before meta.json was written: profile files are
            # only written once the backup is complete, so this folder
            # protects nothing yet and is taken again.
            shutil.rmtree(folder)
            record = False
        except (OSError, ValueError, RecursionError):
            record = None
        if record:
            return record  # never overwrite an existing backup
        if record is None:
            raise OSError(errno.EEXIST, "backup folder without a usable %s" % BACKUP_META, folder)
    files = {}
    originals = {}
    for name, rel in PROFILE_FILES:
        text = texts.get(name)
        if text is None:
            files[name] = {"existed": False, "mode": None, "sha256": None}
            continue
        original = strip_ours(name, text)
        if original != text and not original.strip():
            # Only our addition: v0 created the file.
            files[name] = {"existed": False, "mode": None, "sha256": None}
            continue
        mode = stat.S_IMODE(os.stat(os.path.join(path, rel)).st_mode)
        files[name] = {"existed": True, "mode": mode, "sha256": _sha256(original)}
        originals[name] = original
    chrome = os.path.join(path, CHROME_DIR)
    chrome_dir = False
    if os.path.isdir(chrome):
        # The user's folder (even empty) unless only v0 made it.
        ours = {CHROME_CSS_NAME, CONTENT_CSS_NAME}
        entries = os.listdir(chrome)
        chrome_dir = not entries
        for entry in entries:
            if entry in (USERCHROME_CSS, USERCONTENT_CSS):
                if files[entry]["existed"]:
                    chrome_dir = True
            elif entry not in ours:
                chrome_dir = True
    record = {"path": path, "chrome_dir": chrome_dir, "files": files,
              "prefs_original": prefs_original}
    os.makedirs(os.path.join(sdir, BACKUP_DIR), mode=0o700, exist_ok=True)
    os.mkdir(folder, 0o700)
    try:
        for name, original in originals.items():
            write_if_changed(os.path.join(folder, name), original, mode=0o600, make_dirs=False)
        write_if_changed(meta_path, state_text(record), mode=0o600, make_dirs=False)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return record


def backup_read(sdir, pid, name, record):
    """The backed-up original text of `name`, or None when it is unusable."""
    item = record["files"].get(name)
    if not item or not item["existed"]:
        return None
    try:
        text = read_text(os.path.join(backup_folder(sdir, pid), name), limit=None)
    except (OSError, ValueError):
        return None
    if item["sha256"] is not None and _sha256(text) != item["sha256"]:
        return None
    return text


# ---- prefs.js -----------------------------------------------------------------

def parse_prefs(text):
    """{pref: raw value literal} of the user_pref lines of `text` (last wins)."""
    out = {}
    for line in _lines(text or ""):
        match = _PREF_LINE.fullmatch(_line_body(line))
        if match:
            out[match.group(1)] = match.group(2)
    return out


def block_prefs(text):
    """{pref: value} set inside the managed user.js blocks (v0 or v1) of `text`."""
    lines = _lines(_split_bom(text or "")[1])
    out = {}
    for start, end in _block_spans(lines, USERJS_BLOCK_MARKERS):
        out.update(parse_prefs("".join(lines[start:end])))
    return {p: v for p, v in out.items() if p in PREFS}


def has_v0_block(text):
    """True when `text` (user.js) holds a v0 managed block (or a stray v0 marker)."""
    lines = _lines(_split_bom(text or "")[1])
    return bool(_block_spans(lines, ((V0_USERJS_BEGIN, V0_USERJS_END),)))


def prefs_originals(prefs_text, userjs_text):
    """H2: the original value of each of PREFS from prefs.js. A value equal
    to the one an existing managed block sets came from us (a lost v1
    state): it is recorded as absent. With a v0 block in user.js, any value
    v0 could have written is ours (V0_PREF_VALUES, as prefs_originals_v0):
    v0 rewrote all of PREFS on every sync, and prefs.js may still hold an
    older v0 value (content-override 1 written in light mode while the
    block now says 0, when the browser saved its prefs after a switch)."""
    if has_v0_block(userjs_text):
        return prefs_originals_v0(prefs_text)
    current = parse_prefs(prefs_text)
    ours = block_prefs(userjs_text)
    out = {}
    for pref in PREFS:
        value = current.get(pref)
        if value is None or ours.get(pref) == value:
            out[pref] = {"absent": True}
        else:
            out[pref] = {"value": value}
    return out


def prefs_originals_v0(prefs_text):
    """H2 without a v1 record: a value v0 could have written is ours."""
    current = parse_prefs(prefs_text)
    out = {}
    for pref in PREFS:
        value = current.get(pref)
        if value is None or value in V0_PREF_VALUES[pref]:
            out[pref] = {"absent": True}
        else:
            out[pref] = {"value": value}
    return out


def prefs_restore(text, plan):
    """`text` (prefs.js) after `plan`: [(pref, value literal or None)].
    None deletes the pref's lines, a value replaces the first one (or is
    appended) and deletes the others."""
    lines = _lines(text)
    nl = _newline_of(text)
    for pref, value in plan:
        hits = []
        for i, line in enumerate(lines):
            match = _PREF_LINE.fullmatch(_line_body(line))
            if match and match.group(1) == pref:
                hits.append(i)
        new_line = None if value is None else 'user_pref("%s", %s);' % (pref, value)
        if new_line is not None and not hits:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += nl
            lines.append(new_line + nl)
            continue
        out = []
        for i, line in enumerate(lines):
            if i not in hits:
                out.append(line)
            elif new_line is not None and i == hits[0]:
                ending = line[len(line.rstrip("\r\n")):]
                out.append(new_line + ending)
        lines = out
    return "".join(lines)


def prefs_plan_v0(text):
    """Without a v1 state (H2): delete only the lines carrying a value v0 wrote."""
    current = parse_prefs(text)
    return [(p, None) for p in PREFS if current.get(p) in V0_PREF_VALUES[p]]


def prefs_plan_record(record, prefs):
    """Restore `prefs` to their original values of `record`."""
    plan = []
    for pref in PREFS:
        if pref in prefs:
            item = record["prefs_original"].get(pref, {"absent": True})
            plan.append((pref, item.get("value")))
    return plan


def prefs_apply(profile, plan, warnings=None, family=None, pid=None):
    """Apply `plan` to `profile`/prefs.js (never created, never deleted).
    Returns True when the file changed. Raises OSError."""
    path = os.path.join(profile, PREFS_JS)
    text = read_optional(path)
    if text is None or not plan:
        return False
    new = prefs_restore(text, plan)
    if new == text:
        return False
    return write_if_changed(path, new, warnings, family, pid, make_dirs=False)


def lock_instance(profile):
    """(lock_state, instance key): the key ("pid:starttime" of the process
    holding .parentlock, "?" when it cannot be told) changes when the browser
    restarts; None while the profile is free."""
    state = lock_state(profile)
    if state == LOCK_FREE:
        return state, None
    key = "?"
    try:
        fd = os.open(os.path.join(profile, PARENT_LOCK),
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    except (OSError, ValueError):
        fd = None
    if fd is not None:
        try:
            info = _getlk(fd)
            if info[0] != fcntl.F_UNLCK and info[4] > 0:
                pid = info[4]
                stat_text = read_text(os.path.join(PROC_DIR, str(pid), "stat"), limit=4096)
                fields = stat_text[stat_text.rindex(")") + 2:].split()
                key = "%d:%s" % (pid, fields[19])
        except (OSError, ValueError, IndexError):
            pass
        finally:
            os.close(fd)
    return state, key


def sweep_stale_tmp(folders, now=None):
    """Remove the stale *.tmp files write_if_changed() may have left behind."""
    now = time.time() if now is None else now
    for folder in sorted(set(folders)):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if not _STALE_TMP.fullmatch(name):
                continue
            full = os.path.join(folder, name)
            try:
                st = os.lstat(full)
                if stat.S_ISREG(st.st_mode) and now - st.st_mtime >= STALE_TMP_AGE:
                    os.unlink(full)
            except OSError:
                pass


def _target_dir(path):
    return os.path.dirname(os.path.realpath(path))


# ---- niri ---------------------------------------------------------------------

def _is_include_line(line):
    return _line_body(line).strip() in NIRI_INCLUDE_LINES


_NIRI_OFF_INCLUDE = re.compile(r'(?://+|/-)\s*include\b.*"%s"' % re.escape(NIRI_OUT_NAME))


def _kdl_commented_lines(lines):
    """Indexes of `lines` that start inside a (nested) /* */ comment. Strings
    and // comments are skipped so a "/*" inside them opens nothing."""
    inside = set()
    depth = 0
    for index, line in enumerate(lines):
        if depth:
            inside.add(index)
        i, n = 0, len(line)
        while i < n:
            if line.startswith("/*", i):
                depth += 1
                i += 2
            elif depth and line.startswith("*/", i):
                depth -= 1
                i += 2
            elif depth:
                i += 1
            elif line.startswith("//", i):
                break
            elif line[i] == '"':
                i += 1
                while i < n and line[i] != '"':
                    i += 2 if line[i] == "\\" else 1
                i += 1
            else:
                i += 1
    return inside


def _live_includes(lines):
    """Indexes of our include lines that are not inside a block comment."""
    commented = _kdl_commented_lines(lines)
    return [i for i, line in enumerate(lines) if _is_include_line(line) and i not in commented]


def niri_add_include(text):
    """(new text, had_eol) with our include line appended (v0 layout).
    Nothing is added when the user commented an include of our file out."""
    lines = _lines(text)
    if _live_includes(lines):
        return text, True
    commented = _kdl_commented_lines(lines)
    for i, line in enumerate(lines):
        if _NIRI_OFF_INCLUDE.match(_line_body(line).strip()) or (_is_include_line(line) and i in commented):
            return text, True
    eol = not text or text.endswith("\n")
    nl = _newline_of(text)
    return text + ("" if eol else nl) + nl + V1_NIRI_INCLUDE + nl, eol


def niri_strip_include(text, config_eol=True):
    """`text` without our live include line(s) and the blank line before
    each. Without `config_eol` (the file had no final newline before we
    appended), the final newline goes only when our include was last."""
    lines = _lines(text)
    live = set(_live_includes(lines))
    if not live:
        return text
    out = []
    for i, line in enumerate(lines):
        if i in live:
            if out and not _line_body(out[-1]):
                out.pop()
            continue
        out.append(line)
    result = "".join(out)
    if not config_eol and (len(lines) - 1) in live and result.endswith("\n"):
        result = result[:-2] if result.endswith("\r\n") else result[:-1]
    return result


# ============================================================================
# cmd_* / main
# ============================================================================


class UsageError(Exception):
    """A command-line problem: error line, exit EXIT_USAGE."""


def _opacity_arg(raw):
    """argparse type of --opacity: a finite number in [0, 1]."""
    try:
        value = float(raw)
    except ValueError:
        value = float("nan")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError("expected a number between 0 and 1, got %r" % raw)
    return value


class _Parser(argparse.ArgumentParser):
    """argparse printing the contract's error line instead of its usage text."""

    def error(self, message):
        raise UsageError(message)


def build_parser():
    parser = _Parser(
        prog=PROG, description="browserGlass backend for the DMS plugin " + PLUGIN_ID)
    parser.add_argument("--version", action="version", version=PROG + " " + VERSION)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p = sub.add_parser("sync", help="apply the glass state to every profile")
    p.add_argument("--settings", required=True, metavar="JSON",
                   help="plugin settings as one JSON object")
    p.add_argument("--data", metavar="DIR", help="directory holding styles.json and css-mapping.json")
    p.add_argument("--profile", action="append", default=[], metavar="DIR",
                   help="only sync this profile directory (repeatable)")
    p.add_argument("--opacity", type=_opacity_arg, metavar="X", help="force the opacity (0..1)")
    p.add_argument("--off", action="store_true", help="force glass inactive")
    p.add_argument("--if-plugin", metavar="FILE",
                   help="refuse (nothing written) when FILE, the plugin's plugin.json, is missing")

    p = sub.add_parser("status", help="read-only state of browsers, profiles and glass")
    p.add_argument("--json", action="store_true", required=True, help="JSON output")

    p = sub.add_parser("uninstall", help="remove everything browserGlass wrote (v0 and v1)")
    p.add_argument("--if-gone", metavar="FILE",
                   help="wait $BG_SWEEP_GRACE seconds, then do nothing (exit 3) if FILE exists")

    p = sub.add_parser("clean-prefs", help="internal: wait for the browser, then clean prefs.js")
    p.add_argument("profiles", nargs="+", metavar="PROFILE")

    sub.add_parser("report", help="anonymous plain-text report")

    p = sub.add_parser("sites", help="list the dedicated site styles")
    p.add_argument("--json", action="store_true", required=True, help="JSON output")
    p.add_argument("--data", metavar="DIR", help="directory holding styles.json and css-mapping.json")
    return parser


def _print_json(doc):
    sys.stdout.write(json.dumps(doc) + "\n")
    sys.stdout.flush()


def _fail(message, code=EXIT_ERROR):
    _print_json({"error": message})
    return code


def _oserror_text(exc):
    return exc.strerror or str(exc) or exc.__class__.__name__


def _busy_message():
    return "another browserGlass command holds the state lock; try again"


def _newer_message(exc):
    return ("state.json was written by a newer browserGlass (state version %s); "
            "left untouched" % exc.args[0])


def _select_profiles(args, env, state, warnings):
    """The profiles a sync works on: every discovered one, or the --profile
    folders (which need not be discovered: a minimal record is used)."""
    found = find_profiles(env)
    if not args.profile:
        return found
    by_real = {os.path.realpath(p.path): p for p in found}
    out = []
    seen = set()
    for raw in args.profile:
        path = os.path.normpath(os.path.abspath(raw))
        real = os.path.realpath(path)
        if real in seen:
            continue
        if not os.path.isdir(path):
            warnings.append(make_warning(WARN_PROFILE_MISSING, "profile folder not found: %s"
                                         % os.path.basename(path)))
            continue
        seen.add(real)
        known = by_real.get(real)
        if known is None:
            pid = profile_id(path)
            rec = state["profiles"].get(pid) or {}
            known = Profile(pid, rec.get("family"), rec.get("variant"), os.path.dirname(path),
                            path, os.path.basename(path), False, "arg")
        out.append(known)
    return out


def _read_profile_texts(path):
    """{name: text or None} of the profile files. Raises OSError."""
    return {name: read_optional(os.path.join(path, rel)) for name, rel in PROFILE_FILES}


def _sync_profile(ctx, profile):
    """Sync one profile. Returns True when one of its files changed."""
    sdir, state, warnings = ctx["sdir"], ctx["state"], ctx["warnings"]
    pid, family, path = profile.id, profile.family, profile.path
    chrome_dir = os.path.join(path, CHROME_DIR)
    chrome_path = os.path.join(chrome_dir, CHROME_CSS_NAME)
    content_path = os.path.join(chrome_dir, CONTENT_CSS_NAME)
    try:
        texts = _read_profile_texts(path)
        ctx["disk_glass"][pid] = css_has_glass(read_optional(chrome_path))
    except (OSError, ValueError) as exc:
        warnings.append(make_warning(WARN_READ_FAILED, "profile skipped, a file could not be read: %s"
                                     % _oserror_text(exc), family, pid))
        return False
    record = state["profiles"].get(pid)
    fresh = record is None
    try:
        prefs_text = read_optional(os.path.join(path, PREFS_JS))
    except (OSError, ValueError):
        prefs_text = None
    if fresh:
        record = {
            "path": path, "family": family, "variant": profile.variant,
            "prefs_original": _first_contact_originals(ctx, pid, prefs_text, texts[USER_JS]),
            "owned_prefs": [p for p in PREFS if p in block_prefs(texts[USER_JS])],
            "restore_prefs": [], "applied_hash": None, "instance": None,
            "glass_loaded_since_start": False,
        }
        pend = ctx["pending"].get(pid)
        if pend is not None:
            # The deferred cleanup is dropped below: its prefs become H3
            # restores (kept by the block, restored once the browser closes).
            plan = pend["plan"] if pend["plan"] is not None else prefs_plan_v0(prefs_text)
            record["restore_prefs"] = [p for p in PREFS if p in dict(plan)]
    if pid not in state["backups"]:
        try:
            state["backups"][pid] = backup_take(sdir, pid, path, texts, record["prefs_original"])
        except OSError as exc:
            warnings.append(make_warning(WARN_BACKUP_FAILED, "profile skipped, no backup could be taken: %s"
                                         % _oserror_text(exc), family, pid))
            return False
    if pid in ctx["pending"]:
        # Taken back from a deferred uninstall (re-enabled while the
        # browser ran): the record now holds the originals; the pending
        # file goes once state.json is saved.
        ctx["taken_back"].add(pid)
    record["path"] = path
    if family is not None:
        record["family"] = family
    if profile.variant is not None:
        record["variant"] = profile.variant
    state["profiles"][pid] = record

    writes = [
        (chrome_path, ctx["chrome"], None),
        (content_path, ctx["content"], None),
    ]
    for name, rel in PROFILE_FILES:
        writes.append((os.path.join(path, rel), apply_ours(name, texts[name] or "", ctx["block"]),
                       0o600 if name == USER_JS else None))
    changed = False
    clean = True
    for target, text, mode in writes:
        ctx["folders"].add(os.path.dirname(target))
        ctx["folders"].add(_target_dir(target))
        before = len(warnings)
        if os.path.islink(target) and not os.path.exists(target):
            # Writing would create folders at the link's target, outside the
            # profile, that uninstall could not tell from the user's.
            warnings.append(make_warning(WARN_DANGLING_LINK, "%s is a dangling symlink, left unchanged"
                                         % os.path.basename(target), family, pid))
            clean = False
            continue
        try:
            if write_if_changed(target, text, warnings, family, pid, mode=mode):
                changed = True
        except OSError as exc:
            warnings.append(make_warning(WARN_WRITE_FAILED, "%s not written: %s"
                                         % (os.path.basename(target), _oserror_text(exc)), family, pid))
        if len(warnings) != before:
            clean = False
    record["applied_hash"] = ctx["hash"] if clean else None

    # H3: prefs that left the block get their original value back in
    # prefs.js, only while the browser is closed (it rewrites the file).
    owned = ctx["block_prefs"]
    if not fresh:
        # H3: a pref owned again whose original was already put back gets
        # its current value (the user's latest choice) as the new original.
        current = parse_prefs(prefs_text)
        for pref in owned:
            if pref not in record["owned_prefs"] and pref not in record["restore_prefs"]:
                value = current.get(pref)
                if value is None or ctx["block_values"].get(pref) == value:
                    record["prefs_original"][pref] = {"absent": True}
                else:
                    record["prefs_original"][pref] = {"value": value}
    restore = set(record["restore_prefs"]) | (set(record["owned_prefs"]) - set(owned))
    restore -= set(owned)
    record["owned_prefs"] = [p for p in PREFS if p in owned]
    if restore and lock_state(path) == LOCK_FREE:
        before = len(warnings)
        try:
            if prefs_apply(path, prefs_plan_record(record, restore), warnings, family, pid):
                changed = True
            if len(warnings) == before:
                restore = set()
        except (OSError, ValueError) as exc:
            warnings.append(make_warning(WARN_WRITE_FAILED, "prefs.js not written: %s"
                                         % _oserror_text(exc), family, pid))
    ctx["folders"].add(path)
    record["restore_prefs"] = [p for p in PREFS if p in restore]
    return changed


def _first_contact_originals(ctx, pid, prefs_text, userjs_text):
    """H2 originals of a profile without a state record: from a pending
    deferred uninstall (prefs.js may still hold our values), else from the
    backup's meta.json (state.json lost or corrupt), else from prefs.js."""
    pend = ctx["pending"].get(pid)
    if pend is not None:
        if pend["prefs_original"] is not None:
            return copy.deepcopy(pend["prefs_original"])
        return prefs_originals_v0(prefs_text)
    backup = ctx["state"]["backups"].get(pid)
    if backup is not None and backup["prefs_original"] is not None:
        return copy.deepcopy(backup["prefs_original"])
    return prefs_originals(prefs_text, userjs_text)


def _h1_rule_needed(ctx, active):
    """H1: probe every known profile and decide whether the niri rule stays.

    A browser started while glass CSS was on disk keeps it until it
    restarts; while one runs (LOCK_UNKNOWN counts as running) the opacity
    1.0 rule stays, or it would be darkened twice. Returns (rule_needed,
    {pid: lock state})."""
    states = {}
    needed = active
    for pid, record in sorted(ctx["state"]["profiles"].items()):
        lstate, key = lock_instance(record["path"])
        states[pid] = lstate
        if lstate == LOCK_FREE:
            record["instance"] = None
            record["glass_loaded_since_start"] = False
            continue
        if key != record["instance"]:
            disk = ctx["disk_glass"].get(pid)
            if disk is None:
                try:
                    disk = css_has_glass(read_optional(
                        os.path.join(record["path"], CHROME_DIR, CHROME_CSS_NAME)))
                except (OSError, ValueError):
                    disk = True
            record["instance"] = key
            record["glass_loaded_since_start"] = bool(disk)
        if record["glass_loaded_since_start"]:
            needed = True
    return needed, states


def _sync_niri(ctx, rule_needed):
    """Write the niri file and our include line. Returns True on a change."""
    warnings, state = ctx["warnings"], ctx["state"]
    folder = niri_dir(ctx["env"])
    if not os.path.isdir(folder):
        return False
    changed = False
    out_path = os.path.join(folder, NIRI_OUT_NAME)
    config_path = os.path.join(folder, NIRI_CONFIG_NAME)
    ctx["folders"].update((folder, _target_dir(out_path), _target_dir(config_path)))
    try:
        changed = write_if_changed(out_path, niri_kdl(rule_needed), warnings) or changed
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not written: %s"
                                     % (NIRI_OUT_NAME, _oserror_text(exc))))
    try:
        text = read_optional(config_path)
        if text is not None:
            new, eol = niri_add_include(text)
            if new != text and write_if_changed(config_path, new, warnings, make_dirs=False):
                state["niri"]["include_added"] = True
                state["niri"]["config_eol"] = eol
                changed = True
    except (OSError, ValueError) as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not updated: %s"
                                     % (NIRI_CONFIG_NAME, _oserror_text(exc))))
    return changed


def _remove_v0_cache(env, warnings):
    """Delete the v0 site-styles cache (H4). Returns True when it was there."""
    path = v0_cache_dir(env)
    try:
        if os.path.islink(path) or os.path.isfile(path):
            os.unlink(path)
            return True
        if os.path.isdir(path):
            shutil.rmtree(path)
            return True
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "v0 cache not removed: %s" % _oserror_text(exc)))
    return False


def plugin_gone(manifest, env=None):
    """True when `manifest` (sync --if-plugin, the daemon's plugin.json) is
    missing: the plugin folder was deleted or is being deleted. When its
    folder is still there, the manifest is looked for again after
    $BG_PLUGIN_RECHECK seconds: an update that deletes and recreates
    plugin.json (a git checkout) is not a removal."""
    if os.path.lexists(manifest):
        return False
    if os.path.isdir(os.path.dirname(os.path.abspath(manifest))):
        env = os.environ if env is None else env
        time.sleep(env_seconds(env, ENV_PLUGIN_RECHECK, DEFAULT_PLUGIN_RECHECK))
        return not os.path.lexists(manifest)
    return True


def _plugin_gone_message():
    return ("plugin_gone: the plugin folder (--if-plugin) is gone or being removed; "
            "nothing was written")


def _dir_ids(paths):
    """{path: (st_dev, st_ino)} of the folders among `paths` that exist."""
    ids = {}
    for path in paths:
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode):
            ids[path] = (st.st_dev, st.st_ino)
    return ids


def _ancestors(path):
    """`path` and its parents, deepest first, up to (not including) "/"."""
    out = []
    current = os.path.abspath(path)
    while os.path.dirname(current) != current:
        out.append(current)
        current = os.path.dirname(current)
    return out


def _undo_state_folder(sdir, before, lock_fd):
    """Take back what a refused sync made for its lock, then release it:
    state.lock and the folders that are not the ones `before` (_dir_ids)
    saw, when empty. The sweep's uninstall may have removed the state
    folder while the sync waited for the lock, and state_lock() then made
    it again. state.lock is unlinked while still locked: a command that
    locks the orphaned file afterwards sees it is no longer at the path
    (state_lock() checks) and tries again."""
    now = _dir_ids(_ancestors(sdir))
    try:
        if now.get(sdir) is not None and now.get(sdir) != before.get(sdir):
            try:
                os.unlink(os.path.join(sdir, STATE_LOCK))
            except OSError:
                pass
    finally:
        os.close(lock_fd)
    for folder in _ancestors(sdir):
        if folder in now and now[folder] != before.get(folder):
            _rmdir_quiet(folder)


def cmd_sync(args, env):
    try:
        settings = settings_from_json(args.settings)
    except ValueError as exc:
        raise UsageError("invalid --settings: %s" % exc)
    # The plugin's uninstall sweep may run while a sync the daemon launched
    # just before the folder was deleted is starting or waiting for the
    # lock: that sync must not write everything back. Checked again under
    # the lock, which the sweep's uninstall holds while it cleans.
    if args.if_plugin and plugin_gone(args.if_plugin, env):
        return _fail(_plugin_gone_message())
    warnings = []
    sdir = state_dir(env)
    before = _dir_ids(_ancestors(sdir))
    try:
        created = make_dirs_tracked(sdir)
        lock_fd = state_lock(sdir, env)
    except StateBusy:
        return _fail(_busy_message())
    except OSError as exc:
        return _fail("state folder unusable: %s" % _oserror_text(exc))
    if args.if_plugin and plugin_gone(args.if_plugin, env):
        _undo_state_folder(sdir, before, lock_fd)
        return _fail(_plugin_gone_message())
    try:
        try:
            state, _ = state_load(sdir, warnings)
        except StateNewer as exc:
            return _fail(_newer_message(exc))
        backup_records(sdir, state)
        first_run = not state["synced"]
        state["synced"] = True
        for folder in created:
            if folder not in state["created_dirs"]:
                state["created_dirs"].append(folder)
        opacity, source = effective_opacity(settings, dms_opacity(env), args.opacity)
        active, reason = glass_state(settings, opacity, args.off)
        mode = "light" if settings["isLight"] else "dark"
        colors = dms_colors(env, mode)
        sites_css = ""
        if args.data and active and settings["pagesTransparent"]:
            try:
                sites = sites_load(args.data)
            except (OSError, ValueError, RecursionError) as exc:
                warnings.append(make_warning(WARN_DATA_UNAVAILABLE, "site styles unavailable: %s"
                                             % (getattr(exc, "strerror", None) or exc)))
            else:
                problems = []
                sites_css = sites_build_css(sites, settings["excluded"], settings["disabledStyles"],
                                            settings["genericStyle"], problems)
                for problem in problems:
                    warnings.append(make_warning(WARN_SITE_STYLE, "site style skipped: %s" % problem))
        chrome = chrome_css(settings, opacity, colors.surface, mode, args.off)
        content = content_css(settings, opacity, sites_css, args.off)
        block = userjs_block(settings, opacity, args.off)
        ctx = {
            "env": env, "sdir": sdir, "state": state, "warnings": warnings,
            "chrome": chrome, "content": content, "block": block,
            "block_prefs": [p for p, _ in userjs_prefs(settings, opacity, args.off)],
            "hash": _sha256("\0".join((chrome, content, block)))[:16],
            "disk_glass": {}, "folders": {sdir},
            "block_values": parse_prefs(block), "pending": pending_load(sdir),
            "taken_back": set(),
        }
        changed = []
        for profile in _select_profiles(args, env, state, warnings):
            if _sync_profile(ctx, profile) and profile.id not in changed:
                changed.append(profile.id)
            if profile.family == "zen" and zen_transparency(profile.path):
                warnings.append(zen_warning(profile.id))
        rule_needed, lock_states = _h1_rule_needed(ctx, active)
        niri_changed = _sync_niri(ctx, rule_needed)
        _remove_v0_cache(env, warnings)
        sweep_stale_tmp(ctx["folders"])
        if not args.profile:
            # A --profile sync (captures, tests) leaves the global record
            # alone: status keeps describing the real profiles.
            state["last_sync"] = last_sync_record(settings, collections.OrderedDict([
                ("active", active), ("reason", reason), ("opacity", opacity),
                ("opacity_source", source), ("surface", colors.surface), ("mode", mode)]),
                warnings)
        if state_save(sdir, state, warnings):
            for pid in sorted(ctx["taken_back"]):
                try:
                    pending_drop(sdir, pid, tidy=False)
                except OSError:
                    pass
    finally:
        os.close(lock_fd)
    _print_json({
        "glass": active,
        "opacity": opacity,
        "reason": reason,
        "first_run": first_run,
        "changed": changed,
        # LOCK_UNKNOWN counts as running, as in H1 and the deferred prefs.
        "running_changed": [pid for pid in changed if lock_states.get(pid, LOCK_FREE) != LOCK_FREE],
        "niri_changed": bool(niri_changed),
        "warnings": warnings,
    })
    return EXIT_OK


# ---- uninstall ----------------------------------------------------------------

def _remove_file(path):
    """Delete a file we own; True when it was there."""
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


def _uninstall_file(ctx, profile_path, pid, family, name, rel, backup):
    """Put one profile file back. Returns (removed, restored, done): `done`
    is False when the file still needs work (skipped as read-only)."""
    warnings = ctx["warnings"]
    path = os.path.join(profile_path, rel)
    current = read_optional(path)
    if current is None:
        return False, False, True
    stripped = strip_ours(name, current)
    removed = stripped != current
    item = backup["files"].get(name) if backup else None
    if item is not None and item["existed"]:
        original = backup_read(ctx["sdir"], pid, name, backup)
        if original is not None and stripped in (original, strip_ours(
                name, apply_ours(name, original, ctx["any_block"]))):
            if current != original and not write_if_changed(path, original, warnings, family, pid,
                                                            make_dirs=False):
                return False, False, False  # read-only: the user's choice, keep its mode
            if item["mode"] is not None:
                target = os.path.realpath(path)
                if stat.S_IMODE(os.stat(target).st_mode) != item["mode"]:
                    os.chmod(target, item["mode"])
            return removed, original != stripped, True
        ctx["keep_backup"].add(pid)
        if removed:
            warnings.append(make_warning(
                WARN_BACKUP_KEPT, "%s was edited since the backup; our lines were removed and the "
                "original kept in the state folder" % name, family, pid))
    if not removed:
        return False, False, True
    if not stripped.strip() and not os.path.islink(path):
        _remove_file(path)
    elif not write_if_changed(path, stripped, warnings, family, pid, make_dirs=False):
        return False, False, False
    return True, False, True


def _uninstall_profile(ctx, pid, path, family, record):
    """Remove our traces from one profile. Returns (removed, restored, done,
    traces): `done` is False when something was left (a warning says what)."""
    warnings = ctx["warnings"]
    backup = ctx["state"]["backups"].get(pid)
    removed = restored = False
    done = True
    chrome = os.path.join(path, CHROME_DIR)
    for name in (CHROME_CSS_NAME, CONTENT_CSS_NAME):
        try:
            if _remove_file(os.path.join(chrome, name)):
                removed = True
        except OSError as exc:
            warnings.append(make_warning(WARN_WRITE_FAILED, "%s not removed: %s"
                                         % (name, _oserror_text(exc)), family, pid))
            done = False
    traces = removed or not done
    for name, rel in PROFILE_FILES:
        before = len(warnings)
        try:
            r, s, ok = _uninstall_file(ctx, path, pid, family, name, rel, backup)
        except (OSError, ValueError) as exc:
            warnings.append(make_warning(WARN_WRITE_FAILED, "%s not cleaned: %s"
                                         % (name, _oserror_text(exc)), family, pid))
            r = s = False
            ok = False
        if not ok or any(w["code"] != WARN_BACKUP_KEPT for w in warnings[before:]):
            done = False
            traces = True
        removed = removed or r
        restored = restored or s
        traces = traces or r
    # chrome/ goes only when we made it: the backup says it was not there
    # (or held only v0 files); without a backup, only when we left traces.
    if (backup is not None and not backup["chrome_dir"]) or (backup is None and removed):
        _rmdir_quiet(chrome)
    return removed, restored, done, traces


def _uninstall_plan(ctx, pid, path, record, traces):
    """(plan, originals) of the prefs.js cleanup of one profile. `plan` is
    a list, None for the v0 rule applied when the file is written, or []."""
    if record is not None:
        return (prefs_plan_record(record, set(record["owned_prefs"]) | set(record["restore_prefs"])),
                record["prefs_original"])
    pend = ctx["pending"].get(pid)
    if pend is not None:
        return pend["plan"], pend["prefs_original"]
    backup = ctx["state"]["backups"].get(pid)
    if backup is not None and backup["prefs_original"] is not None:
        # state.json lost or corrupt: every pref may have been ours.
        synth = {"prefs_original": backup["prefs_original"]}
        return prefs_plan_record(synth, set(PREFS)), backup["prefs_original"]
    return (None if traces else []), None


def _clean_prefs_now(path, plan, warnings=None, family=None, pid=None):
    """Apply `plan` (None: the v0 rule, decided on the current file) to the
    prefs.js of a free profile. Returns (changed, done). Raises OSError."""
    prefs_path = os.path.join(path, PREFS_JS)
    text = read_optional(prefs_path)
    if text is None:
        return False, True
    if plan is None:
        plan = prefs_plan_v0(text)
    new = prefs_restore(text, plan)
    if new == text:
        return False, True
    sink = [] if warnings is None else warnings
    before = len(sink)
    changed = write_if_changed(prefs_path, new, sink, family, pid, make_dirs=False)
    return changed, changed or len(sink) == before


def _cleaner_lock(sdir):
    """flock on `sdir`/state.lock for the detached cleaner, never waiting:
    an fd, or None while another command holds it. Raises OSError (the
    state folder is gone: the job was taken over)."""
    fd = os.open(os.path.join(sdir, STATE_LOCK), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if os.stat(os.path.join(sdir, STATE_LOCK), follow_symlinks=False).st_ino == os.fstat(fd).st_ino:
            return fd
    except OSError as exc:
        if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, errno.ENOENT):
            os.close(fd)
            raise
    os.close(fd)
    return None


def _clean_job(sdir, job):
    """One attempt at a deferred job: "done", "wait" or "drop"."""
    path = job["path"]
    if job["pending"] and not os.path.exists(pending_file(sdir, job["pid"])):
        return "drop"  # taken back by a sync, or done by another cleaner
    if lock_state(path) != LOCK_FREE:
        return "wait"
    fd = None
    if job["pending"]:
        try:
            fd = _cleaner_lock(sdir)
        except OSError:
            return "drop"
        if fd is None:
            return "wait"
    try:
        if job["pending"]:
            record = pending_load(sdir).get(job["pid"])
            if record is None:
                return "drop"
        if lock_state(path) != LOCK_FREE:
            return "wait"  # restarted meanwhile: wait for this run too
        if os.path.isdir(path):
            _, ok = _clean_prefs_now(path, job["plan"])
            if not ok:
                return "drop"  # read-only: the pending file stays for a retry
        if job["pending"]:
            pending_drop(sdir, job["pid"], record["created_dirs"], tidy=False)
            _tidy_state_dir(sdir, record["created_dirs"])
        return "done"
    except (OSError, ValueError):
        return "drop"
    finally:
        if fd is not None:
            os.close(fd)


def _tidy_state_dir(sdir, created_dirs):
    """Remove the state folder once only our lock file is left in it, then
    the folders made for it (deepest first)."""
    try:
        if os.listdir(sdir) != [STATE_LOCK]:
            return
        os.unlink(os.path.join(sdir, STATE_LOCK))
    except OSError:
        return
    _rmdir_quiet(sdir)
    for folder in sorted(set(created_dirs), key=len, reverse=True):
        _rmdir_quiet(folder)


def _clean_prefs_wait(sdir, jobs, env):
    """H6: poll each job ({pid, path, plan, pending}) until its browser is
    closed, re-check right before writing, then clean its prefs.js. A job
    with a pending/<pid>.json file runs under the state lock and removes
    that file once done; when the file is gone (a sync took the profile
    back) the job is dropped. Gives up after $BG_POLL_MAX seconds, leaving
    the pending files for a later uninstall or clean-prefs. Needs no file of
    its own (works from `python3 -I -c`)."""
    interval = env_seconds(env, ENV_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    deadline = time.monotonic() + env_seconds(env, ENV_POLL_MAX, DEFAULT_POLL_MAX)
    waiting = list(jobs)
    while waiting:
        waiting = [job for job in waiting if _clean_job(sdir, job) == "wait"]
        if not waiting or time.monotonic() >= deadline:
            break
        time.sleep(interval)


def _close_inherited_fds():
    try:
        fds = [int(name) for name in os.listdir("/proc/self/fd")]
    except (OSError, ValueError):
        try:
            limit = os.sysconf("SC_OPEN_MAX")
        except (OSError, ValueError):
            limit = 65536
        os.closerange(3, max(limit, 65536))
        return
    for fd in fds:
        if fd > 2:
            try:
                os.close(fd)
            except OSError:
                pass


def _spawn_clean_prefs(sdir, jobs, env):
    """Fork a detached (setsid) child running _clean_prefs_wait(jobs).
    Returns True in the parent once forked; the child never returns."""
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid:
        try:
            os.waitpid(pid, 0)  # the first child exits at once
        except OSError:
            pass
        return True
    code = 0
    try:
        os.setsid()
        os.chdir("/")  # never pin the caller's folder (a deleted plugin dir)
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
        _close_inherited_fds()
        if os.fork():
            os._exit(0)  # the grandchild is reparented, nothing waits for us
        _clean_prefs_wait(sdir, jobs, env)
    except BaseException:
        code = 1
    finally:
        os._exit(code)


def _clear_state_dir(sdir, keep):
    """Remove the entries of `sdir` except the names in `keep`."""
    for name in os.listdir(sdir):
        if name in keep:
            continue
        full = os.path.join(sdir, name)
        if os.path.isdir(full) and not os.path.islink(full):
            shutil.rmtree(full)
        else:
            os.unlink(full)


def cmd_uninstall(args, env):
    if args.if_gone:
        # The plugin's sweep: its folder looked deleted at unload. An update
        # or a reinstall brings plugin.json back within the grace period.
        time.sleep(env_seconds(env, ENV_SWEEP_GRACE, DEFAULT_SWEEP_GRACE))
        if os.path.lexists(args.if_gone):
            return EXIT_KEPT
    warnings = []
    sdir = state_dir(env)
    state_existed = os.path.isdir(sdir)
    lock_fd = None
    if state_existed:
        try:
            lock_fd = state_lock(sdir, env, UNINSTALL_LOCK_TIMEOUT)
        except StateBusy:
            return _fail(_busy_message())
        except OSError as exc:
            # Best effort without the lock: the profiles matter more.
            warnings.append(make_warning(WARN_STATE_UNAVAILABLE, "state lock unusable, going on "
                                         "without it: %s" % _oserror_text(exc)))
    try:
        if state_existed:
            try:
                state, _ = state_load(sdir, warnings)
            except StateNewer as exc:
                return _fail(_newer_message(exc))
            backup_records(sdir, state)
        else:
            state = new_state()
        ctx = {"env": env, "sdir": sdir, "state": state, "warnings": warnings,
               "keep_backup": set(), "pending": pending_load(sdir) if state_existed else {},
               "any_block": "%s\n%s\n" % (V1_USERJS_BEGIN, V1_USERJS_END)}
        targets = collections.OrderedDict()
        for profile in find_profiles(env):
            targets[profile.id] = (profile.path, profile.family)
        known = [(pid, r["path"], r["family"]) for pid, r in sorted(state["profiles"].items())]
        known += [(pid, r["path"], None) for pid, r in sorted(ctx["pending"].items())]
        known += [(pid, b["path"], None) for pid, b in sorted(state["backups"].items())]
        for pid, path, family in known:
            if pid not in targets and path and os.path.isdir(path):
                targets[pid] = (path, family)

        removed, restored, pending, jobs = [], [], [], []
        unfinished = set()
        deferred = {}
        for pid, (path, family) in targets.items():
            record = state["profiles"].get(pid)
            before = len(warnings)
            try:
                r, s, done, traces = _uninstall_profile(ctx, pid, path, family, record)
                plan, originals = _uninstall_plan(ctx, pid, path, record, traces)
                if plan != []:
                    if lock_state(path) == LOCK_FREE:
                        changed, ok = _clean_prefs_now(path, plan, warnings, family, pid)
                        s = s or changed
                        done = done and ok
                    else:
                        deferred[pid] = (path, plan, originals)
                        pending.append(pid)
                        if not r:
                            s = True
            except (OSError, ValueError) as exc:
                warnings.append(make_warning(WARN_WRITE_FAILED, "profile not cleaned: %s"
                                             % _oserror_text(exc), family, pid))
                r = s = False
                done = False
            if not done or any(w["code"] != WARN_BACKUP_KEPT for w in warnings[before:]):
                unfinished.add(pid)
            if r:
                removed.append(pid)
            if s:
                restored.append(pid)

        niri_changed = False
        folder = niri_dir(env)
        try:
            niri_changed = _remove_file(os.path.join(folder, NIRI_OUT_NAME))
            config_path = os.path.join(folder, NIRI_CONFIG_NAME)
            text = read_optional(config_path)
            if text is not None:
                eol = state["niri"]["config_eol"] or not state["niri"]["include_added"]
                new = niri_strip_include(text, eol)
                if new != text:
                    if write_if_changed(config_path, new, warnings, make_dirs=False):
                        niri_changed = True
        except (OSError, ValueError) as exc:
            warnings.append(make_warning(WARN_WRITE_FAILED, "niri config not cleaned: %s"
                                         % _oserror_text(exc)))
        v0_cache_removed = _remove_v0_cache(env, warnings)

        # Deferred prefs.js cleanups (H6) are recorded in pending/<pid>.json
        # so their originals outlive the state and a killed cleaner.
        created = []
        if deferred and not state_existed:
            try:
                created = make_dirs_tracked(sdir)
            except OSError:
                created = []
        created_dirs = sorted(set(state["created_dirs"]) | set(created))
        for pid, (path, plan, originals) in deferred.items():
            has_file = False
            try:
                make_dirs_tracked(pending_folder(sdir))
                has_file = write_if_changed(pending_file(sdir, pid),
                                            pending_text(path, plan, originals, created_dirs),
                                            warnings, mode=0o600) or os.path.isfile(pending_file(sdir, pid))
            except OSError as exc:
                warnings.append(make_warning(WARN_WRITE_FAILED, "pending prefs.js cleanup not recorded: %s"
                                             % _oserror_text(exc), None, pid))
            jobs.append({"pid": pid, "path": path, "plan": plan, "pending": has_file})
        for pid in ctx["pending"]:
            if pid not in deferred and pid not in unfinished:
                pending_drop(sdir, pid, tidy=False)

        state_removed = False
        if os.path.isdir(sdir):
            keep_names = {STATE_LOCK, PENDING_DIR} if deferred else set()
            if unfinished or ctx["keep_backup"]:
                # Keep what a retry needs: the records and backups of the
                # unfinished profiles, the backups of edited files.
                for pid in list(state["backups"]):
                    if pid in unfinished:
                        continue
                    if pid in ctx["keep_backup"]:
                        # Its prefs were restored: meta's originals are stale.
                        state["backups"][pid]["prefs_original"] = None
                        _drop_meta_originals(sdir, pid, warnings)
                        continue
                    shutil.rmtree(backup_folder(sdir, pid), ignore_errors=True)
                    del state["backups"][pid]
                state["profiles"] = {p: r for p, r in state["profiles"].items() if p in unfinished}
                state["niri"] = {"include_added": False, "config_eol": True}
                state["synced"] = False
                state_save(sdir, state, warnings)
            else:
                try:
                    _clear_state_dir(sdir, keep_names)
                    if not keep_names:
                        os.rmdir(sdir)
                    state_removed = state_existed
                except OSError as exc:
                    warnings.append(make_warning(WARN_WRITE_FAILED, "state folder not removed: %s"
                                                 % _oserror_text(exc)))
                if not keep_names:
                    for folder in sorted(set(created_dirs), key=len, reverse=True):
                        if folder != sdir:
                            _rmdir_quiet(folder)
        if jobs:
            try:
                _spawn_clean_prefs(sdir, jobs, env)
            except OSError as exc:
                warnings.append(make_warning(WARN_FORK_FAILED, "prefs.js cleanup after the browser "
                                             "closes could not start: %s" % _oserror_text(exc)))
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
    _print_json({
        "removed": removed,
        "restored": restored,
        "pending": pending,
        "niri_changed": niri_changed,
        "state_removed": state_removed,
        "v0_cache_removed": v0_cache_removed,
        "warnings": warnings,
    })
    return EXIT_OK


def _drop_meta_originals(sdir, pid, warnings):
    meta = os.path.join(backup_folder(sdir, pid), BACKUP_META)
    try:
        doc = json.loads(read_text(meta))
        if isinstance(doc, dict) and doc.get("prefs_original") is not None:
            doc["prefs_original"] = None
            write_if_changed(meta, state_text(doc), warnings, mode=0o600, make_dirs=False)
    except (OSError, ValueError, RecursionError):
        pass


def cmd_clean_prefs(args, env):
    """Wait until each profile is free, then clean its prefs.js. Prints nothing."""
    warnings = []
    sdir = state_dir(env)
    try:
        state, _ = state_load(sdir, warnings)
    except (OSError, StateNewer):
        state = new_state()
    pendings = pending_load(sdir)
    jobs = []
    for raw in args.profiles:
        path = os.path.normpath(os.path.abspath(raw))
        if not os.path.isdir(path):
            continue
        pid = profile_id(path)
        record = state["profiles"].get(pid)
        if record is not None:
            plan = prefs_plan_record(record, set(record["owned_prefs"]) | set(record["restore_prefs"]))
        elif pid in pendings:
            plan = pendings[pid]["plan"]
        else:
            plan = None
        if plan != []:
            jobs.append({"pid": pid, "path": path, "plan": plan, "pending": pid in pendings})
    _clean_prefs_wait(sdir, jobs, env)
    return EXIT_OK


# ---- status / report / sites (read-only) ------------------------------------
# None of these writes anything: no state folder is created, no lock taken
# (state.lock is not needed to read a file replaced atomically), and the
# lock probe only opens .parentlock read-only.
#
# status describes what is on disk, as one moment: glass.* is what the last
# full sync (no --profile) decided and recorded in state.json "last_sync",
# applied compares each profile's files with that sync's output, niri.rule
# reads the rule file it wrote. Live DMS inputs (windowrules.kdl, the
# colours, blur) are only read before any full sync, to preview what one
# would do; afterwards the daemon re-syncs on their change and then reads
# status again.
#
# H1 contract for the daemon (P5): niri.rule true while glass.active is false
# means the opacity rule is still there. While a running profile that loaded
# glass holds it, status emits niri_rule_held for that profile and counts it
# in restart_needed (keep polling). Once no holder is left, status emits
# niri_rule_stale instead (restart_needed false): the daemon then runs sync,
# which drops the rule.

WARN_RULE_HELD = "niri_rule_held"
WARN_RULE_STALE = "niri_rule_stale"
ENV_DMS_SHELL_DIR = "BG_DMS_SHELL_DIR"  # folder holding DMS's VERSION file (report)
DMS_SHELL_DIRS = ("/usr/share/quickshell/dms", "/usr/local/share/quickshell/dms",
                  "/etc/xdg/quickshell/dms")
DATA_DIR_REL = "dms/plugins/" + PLUGIN_ID + "/data"  # under $XDG_CONFIG_HOME
COMPATIBILITY_INI = "compatibility.ini"
# The files whose change a running browser only sees after a restart
# (prefs.js is the browser's own; it rewrites it).
RESTART_FILES = (
    os.path.join(CHROME_DIR, CHROME_CSS_NAME),
    os.path.join(CHROME_DIR, CONTENT_CSS_NAME),
    os.path.join(CHROME_DIR, USERCHROME_CSS),
    os.path.join(CHROME_DIR, USERCONTENT_CSS),
    USER_JS,
)
# Version shapes the report may show; anything else is "unknown", so that a
# VERSION or compatibility.ini file can never carry free text into it.
# DMS: 2.1.2, v1.7.0, 1.7.0-12-gabcdef0 (git describe). Browsers (the part
# of LastVersion before "_"): 128.0.3, 129.0b5, 115.9.0esr, 1.7.6b (Zen),
# 1.0.1-a.19 (old Zen).
_REPORT_VERSION = re.compile(r"v?\d{1,4}(?:\.\d{1,4}){0,3}(?:-\d{1,6}-g[0-9a-f]{7,12})?")
_COMPAT_VERSION = re.compile(
    r"^LastVersion=(\d{1,4}(?:\.\d{1,4}){0,3}(?:(?:a|b|esr)\d{0,3}|-[ab]\.\d{1,3})?)"
    r"(?:_[^\r\n]*)?\r?$", re.M)


def tilde_path(path, env=None):
    """`path` relative to $HOME as the contract's tilde_path ("~/...")."""
    rel = os.path.relpath(os.path.normpath(path), home_dir(env))
    return "~" if rel == "." else "~/" + rel


def process_start(key):
    """Epoch seconds by which the process of a lock_instance() key
    ("pid:starttime") had surely started, or None when it cannot be told.
    /proc gives the start in clock ticks since boot, rounded down: one
    tick is added, so a file written just before the start is never taken
    for one written after it."""
    try:
        tick = 1.0 / os.sysconf("SC_CLK_TCK")
        ticks = int(key.split(":")[1])
        boot = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME)
        return boot + (ticks + 1) * tick
    except (AttributeError, IndexError, ValueError, OSError, ZeroDivisionError):
        return None


def files_changed_since(profile, since):
    """True when one of RESTART_FILES of `profile` changed after `since`."""
    for rel in RESTART_FILES:
        try:
            if os.stat(os.path.join(profile, rel)).st_mtime > since:
                return True
        except OSError:
            continue
    return False


def profile_applied(path, record):
    """True when the generated files and the user.js block of the profile
    folder `path` are those of `record`'s last sync (applied_hash)."""
    if record is None or record["applied_hash"] is None:
        return False
    try:
        chrome = read_text(os.path.join(path, CHROME_DIR, CHROME_CSS_NAME))
        content = read_text(os.path.join(path, CHROME_DIR, CONTENT_CSS_NAME))
        for name, rel in PROFILE_FILES:
            if name in _FILE_IMPORT:
                text = read_text(os.path.join(path, rel))
                if ensure_import(text, _FILE_IMPORT[name]) != text:
                    return False
        userjs = read_text(os.path.join(path, USER_JS)).replace("\r\n", "\n")
    except (OSError, ValueError):
        return False
    lines = _lines(_split_bom(userjs)[1])
    spans = _block_spans(lines, USERJS_BLOCK_MARKERS)
    if len(spans) != 1:
        return False
    start, end = spans[0]
    block = "".join(lines[start:end])
    if replace_block(userjs, block) != userjs:
        return False
    return _sha256("\0".join((chrome, content, block)))[:16] == record["applied_hash"]


def glass_holders(state):
    """[(pid, record, lock state)] of the running profiles that still have
    glass loaded (H1, read-only twin of _h1_rule_needed: LOCK_UNKNOWN counts
    as running, as there)."""
    out = []
    for pid, record in sorted(state["profiles"].items()):
        lstate, key = lock_instance(record["path"])
        if lstate == LOCK_FREE:
            continue
        if key != record["instance"]:
            try:
                loaded = css_has_glass(read_optional(
                    os.path.join(record["path"], CHROME_DIR, CHROME_CSS_NAME)))
            except (OSError, ValueError):
                loaded = True
        else:
            loaded = record["glass_loaded_since_start"]
        if loaded:
            out.append((pid, record, lstate))
    return out


def niri_status(env):
    """{config, include, rule} as the contract's status.niri."""
    folder = niri_dir(env)
    try:
        config = read_optional(os.path.join(folder, NIRI_CONFIG_NAME))
    except (OSError, ValueError):
        config = None
    try:
        rule = read_optional(os.path.join(folder, NIRI_OUT_NAME)) == niri_kdl(True)
    except (OSError, ValueError):
        rule = False
    return {"config": config is not None,
            "include": bool(config is not None and _live_includes(_lines(config))),
            "rule": rule}


def _status_glass(state, env):
    """(status.glass, settings shown): those of the last full sync, else
    (no sync yet, or an unusable record) a preview from the default
    settings and the live DMS inputs."""
    last = state.get("last_sync")
    if last is not None:
        return collections.OrderedDict(last["glass"]), settings_from_json(last["settings"])
    settings = settings_from_json({})
    opacity, source = effective_opacity(settings, dms_opacity(env))
    active, reason = glass_state(settings, opacity)
    mode = "light" if settings["isLight"] else "dark"
    return collections.OrderedDict([
        ("active", active), ("reason", reason), ("opacity", opacity),
        ("opacity_source", source), ("surface", dms_colors(env, mode).surface),
        ("mode", mode)]), settings


def collect_status(env):
    """(status document of the contract's status spec, settings shown,
    {profile id: profile folder}, warning codes of the last full sync)."""
    warnings = []
    try:
        state, _ = state_load(state_dir(env), warnings)
    except StateNewer as exc:
        warnings.append(make_warning(WARN_STATE_UNAVAILABLE, _newer_message(exc)))
        state = new_state()
    glass, settings = _status_glass(state, env)
    # The DMS opacity read now: the settings page shows it beside the one the
    # glass uses (an override or a forced value replaces it)
    glass["dms_opacity"] = dms_opacity(env)
    niri = niri_status(env)

    browsers = []
    by_key = {}
    folders = {}
    for profile in find_profiles(env):
        folders[profile.id] = profile.path
        lstate, key = lock_instance(profile.path)
        running = lstate == LOCK_RUNNING
        start = process_start(key) if running else None
        restart = start is not None and files_changed_since(profile.path, start)
        record = state["profiles"].get(profile.id)
        group_key = (profile.family, profile.variant, profile.root)
        group = by_key.get(group_key)
        if group is None:
            group = {"family": profile.family, "variant": profile.variant,
                     "root": tilde_path(profile.root, env), "running": False,
                     "restart_needed": False, "profiles": []}
            by_key[group_key] = group
            browsers.append(group)
        group["running"] = group["running"] or running
        group["restart_needed"] = group["restart_needed"] or restart
        group["profiles"].append({
            "id": profile.id, "name": profile.name, "path": tilde_path(profile.path, env),
            "default": bool(profile.default), "running": running, "restart_needed": restart,
            "applied": profile_applied(profile.path, record),
        })
        if profile.family == "zen" and zen_transparency(profile.path):
            warnings.append(zen_warning(profile.id))

    held = []
    if niri["rule"] and not glass["active"]:
        held = glass_holders(state)
        if not held:
            warnings.append(make_warning(
                WARN_RULE_STALE, "the niri opacity rule is no longer needed; the next sync removes it"))
    for pid, record, lstate in held:
        message = "the niri opacity rule stays until this browser restarts"
        if lstate != LOCK_RUNNING:
            message += " (its lock state is unknown: it may still be running)"
        warnings.append(make_warning(WARN_RULE_HELD, message, record["family"], pid))
    doc = collections.OrderedDict([
        ("version", VERSION),
        ("glass", glass),
        ("niri", niri),
        ("restart_needed", bool(held) or any(b["restart_needed"] for b in browsers)),
        ("browsers", browsers),
        ("warnings", warnings),
    ])
    last = state.get("last_sync")
    return doc, settings, folders, list(last["warning_codes"]) if last else []


def cmd_status(args, env):
    doc, _, _, _ = collect_status(env)
    _print_json(doc)
    return EXIT_OK


def _yes(value):
    return "yes" if value else "no"


def _bool_word(value):
    return "true" if value else "false"


def dms_version(env):
    """DMS's version from its VERSION file, "unknown" when not found."""
    override = env.get(ENV_DMS_SHELL_DIR) or ""
    if os.path.isabs(override):
        folders = (override,)
    else:
        folders = (os.path.join(xdg_dir("XDG_CONFIG_HOME", env), "quickshell", "dms"),) + DMS_SHELL_DIRS
    for folder in folders:
        try:
            text = read_text(os.path.join(folder, "VERSION"), limit=256).strip()
        except (OSError, ValueError):
            continue
        return text if _REPORT_VERSION.fullmatch(text) else "unknown"
    return "unknown"


def browser_version(profile):
    """The browser version that last ran `profile` (compatibility.ini), or None."""
    try:
        match = _COMPAT_VERSION.search(read_text(os.path.join(profile, COMPATIBILITY_INI), limit=65536))
    except (OSError, ValueError):
        return None
    return match.group(1) if match else None


def report_lines(doc, settings, folders, env, sync_codes=()):
    """The anonymous report (contract report_lines): versions, glass, niri,
    profile counts per browser, settings and warning codes (those of status
    then those the last full sync raised, e.g. write_failed). No path, name,
    profile id or message is ever printed."""
    glass, niri = doc["glass"], doc["niri"]
    counts = collections.OrderedDict()
    versions = collections.OrderedDict()
    for family in FAMILIES:
        for variant in VARIANTS:
            counts[(family, variant)] = [0, 0, 0]
    for browser in doc["browsers"]:
        key = (browser["family"], browser["variant"])
        for profile in browser["profiles"]:
            row = counts[key]
            row[0] += 1
            row[1] += profile["running"]
            row[2] += profile["restart_needed"]
            found = versions.setdefault(key, [])
            version = browser_version(folders[profile["id"]])
            if version is not None and version not in found:
                found.append(version)
    names = []
    for key in counts:
        if key in versions:
            found = versions[key]
            names.append("%s %s %s" % (key + ("+".join(sorted(found)) if found else "unknown",)))
    held = any(w["code"] == WARN_RULE_HELD for w in doc["warnings"])
    codes = _unique([w["code"] for w in doc["warnings"]] + list(sync_codes))
    profiles = [p for b in doc["browsers"] for p in b["profiles"]]
    lines = [
        "browserGlass report",
        "version: " + doc["version"],
        "python: %d.%d.%d" % sys.version_info[:3],
        "dms: " + dms_version(env),
        "browsers: " + (", ".join(names) or "none"),
        "glass: %s (reason %s, opacity %s, source %s, mode %s)" % (
            "active" if glass["active"] else "inactive", glass["reason"],
            format_number(glass["opacity"]), glass["opacity_source"], glass["mode"]),
        "niri: config %s, include %s, rule %s%s" % (
            _yes(niri["config"]), _yes(niri["include"]), _yes(niri["rule"]),
            " (held until a browser restarts)" if held else ""),
        "restart needed: " + _yes(doc["restart_needed"]),
        "applied: %d of %d profiles" % (sum(p["applied"] for p in profiles), len(profiles)),
        "profiles:",
    ]
    for (family, variant), (total, running, restart) in counts.items():
        if total:
            lines.append("  %s %s: %d (%d running, %d restart needed)"
                         % (family, variant, total, running, restart))
    parts = []
    for key, value in settings.items():
        if key in ("blur", "isLight", "opacity"):
            continue
        if isinstance(value, bool):
            parts.append("%s=%s" % (key, _bool_word(value)))
        elif isinstance(value, list):
            parts.append("%s=%d" % (key, len(value)))
        else:
            parts.append("%s=%s" % (key, value))
    lines.append("settings: " + " ".join(parts))
    lines.append("warnings: " + (", ".join(codes) or "none"))
    return lines


def cmd_report(args, env):
    doc, settings, folders, sync_codes = collect_status(env)
    sys.stdout.write("\n".join(report_lines(doc, settings, folders, env, sync_codes)) + "\n")
    sys.stdout.flush()
    return EXIT_OK


def cmd_sites(args, env):
    folder = args.data or os.path.join(xdg_dir("XDG_CONFIG_HOME", env), DATA_DIR_REL)
    try:
        sites = sites_load(folder)
    except (OSError, ValueError, RecursionError) as exc:
        return _fail("site styles unavailable: %s" % (getattr(exc, "strerror", None) or exc))
    _print_json(sites_list(sites))
    return EXIT_OK


COMMANDS = {
    "sync": cmd_sync,
    "status": cmd_status,
    "uninstall": cmd_uninstall,
    "clean-prefs": cmd_clean_prefs,
    "report": cmd_report,
    "sites": cmd_sites,
}


def main(argv=None, env=None):
    env = os.environ if env is None else env
    try:
        args = build_parser().parse_args(argv)
        command = COMMANDS.get(args.command)
        if command is None:
            return _fail("%s: not implemented yet" % args.command)
        return command(args, env)
    except UsageError as exc:
        return _fail(str(exc), EXIT_USAGE)
    except KeyboardInterrupt:
        return _fail("interrupted")
    except (OSError, ValueError) as exc:
        return _fail("%s: %s" % (exc.__class__.__name__, getattr(exc, "strerror", None) or exc))


if __name__ == "__main__":
    sys.exit(main())

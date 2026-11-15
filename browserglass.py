#!/usr/bin/env python3
"""browserglass - single-file backend of the DMS plugin browserGlass.

Applies the DMS "glass" look (translucent tinted background, opaque text,
images and videos) to Firefox-family browsers (Firefox, LibreWolf, Zen,
Floorp, Waterfox; native, Flatpak and Snap) under niri.

Commands (one JSON line on stdout unless stated otherwise; the frozen output
contract is tests/fixtures/contract/schema.json, an error is {"error": "..."}
with exit status 1, or 2 for a usage error):
  sync (--settings JSON | --settings-file FILE) [--data DIR] [--profile DIR]...
       [--opacity X] [--off] [--if-plugin FILE] [--plugin-dir DIR]
                                (--settings-file: the same JSON read from
                                FILE, which is then deleted; the daemon's
                                way, as an argv is public;
                                --if-plugin: refused with a "plugin_gone:"
                                error, nothing written, when FILE, the
                                daemon's plugin.json, is missing or DMS's
                                plugin_settings.json has the plugin
                                disabled;
                                --plugin-dir: the plugin folder, whose
                                extension/ is the companion add-on, deposited
                                while liveControl is on; without it the
                                add-on is left as it is)
  status --json
  uninstall [--if-gone FILE]    (--if-gone: waits $BG_SWEEP_GRACE seconds, then
                                exits 3, printing nothing, if FILE exists again)
  clean-prefs PROFILE...        (internal: waits for the browser, cleans prefs.js;
                                prints nothing, exit 0)
  report                        (anonymous plain text)
  sites --json [--data DIR]
  native-host [--data DIR] [ARG]...
                                (internal: run by the browser for the companion
                                add-on; native messaging frames on stdin and
                                stdout, never a JSON line, see section native)
  active-site --json --pid PID --app-id ID [--window-id ID | --title T]
              [--data DIR]
                                (the site of a browser window: {"host",
                                "domain", "source", "age"}, or one of the
                                spec's {"error": ...} answers, exit 0 both)

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
import functools
import hashlib
import io
import json
import math
import os
import pwd
import re
import shlex
import shutil
import socket
import stat
import struct
import sys
import tempfile
import time
import unicodedata

# ============================================================================
# consts
# ============================================================================

VERSION = "1.2.0"
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
ZEN_THEMES_JSON = "zen-themes.json"  # Zen's mod registry, see ZEN_MOD_FILES
# Generated stylesheets (same names in v0 and v1).
CHROME_CSS_NAME = "dms-glass-chrome.css"
CONTENT_CSS_NAME = "dms-glass-content.css"

# niri side (relative to $XDG_CONFIG_HOME, default ~/.config).
NIRI_DIR_REL = "niri"
NIRI_CONFIG_NAME = "config.kdl"
NIRI_OUT_NAME = "dms-browser-glass.kdl"
DMS_RULES_REL = "niri/dms/windowrules.kdl"   # read only, never written
DMS_FIREFOX_CSS_REL = "dms/firefox.css"      # DMS file, never touched
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

# Embedded data (relative to the --data folder, <plugin>/data).
PSL_FILE = "public_suffix_list.dat"   # Mozilla Public Suffix List (section psl)

# Companion add-on and native messaging host (section companion).
# The add-on's sources sit in <plugin>/<EXTENSION_DIR>; the sync zips them
# into <profile>/extensions/<COMPANION_XPI> (the file name must be the gecko
# id). The browser starts the host through the manifest
# $HOME/<NATIVE_MANIFEST_REL>/<NATIVE_MANIFEST_NAME> (Firefox and LibreWolf
# both read it; never ~/.config/...), which points at the wrapper
# $XDG_STATE_HOME/<STATE_DIR_REL>/<HOST_WRAPPER>. The host's sockets and
# files live in $XDG_RUNTIME_DIR/<RUNTIME_DIR_NAME>.
EXTENSION_DIR = "extension"
COMPANION_ID = "browserglass@companion"
COMPANION_XPI = COMPANION_ID + ".xpi"
EXTENSIONS_DIR = "extensions"  # relative to a profile directory
NATIVE_HOST_NAME = "browserglass"
NATIVE_MANIFEST_REL = ".mozilla/native-messaging-hosts"  # relative to $HOME
NATIVE_MANIFEST_NAME = NATIVE_HOST_NAME + ".json"
HOST_WRAPPER = "native-host"
RUNTIME_DIR_NAME = "browserGlass"
# Attributes the add-on sets on <html> of a web page: OFF while the page's
# site is excluded, LIVE once the add-on knows the list (see extension/),
# TONE the page's measured tone, "light" (dark text) or "dark" (light text).
ATTR_OFF = "data-browserglass-off"
ATTR_LIVE = "data-browserglass-live"
ATTR_TONE = "data-browserglass-tone"
# The add-on also sets CANVAS on the large elements that paint the page's
# background once it turned a light page dark (darkPages): they become glass.
ATTR_CANVAS = "data-browserglass-canvas"
# ... and BAR on a navigation bar along an edge of the window (a header, a
# bottom bar, a sidebar; see _CONTENT_LAYERS): a light veil over a blur.
ATTR_BAR = "data-browserglass-bar"

# ---- v0 markers (byte-exact copies of what v0 wrote; do not "fix") ---------
# Non-ASCII characters are written as escapes so this file stays pure ASCII
# and survives being fed to `python3 -I -c STDIN_BOOTSTRAP` under any locale.
# Encoded as UTF-8 they are byte-identical to the strings in v0
# browser-glass-sync / browser-glass-sites (checked by tests/py/test_contract.py).

# v0 cache of the my-internet styles (relative to $XDG_CACHE_HOME); removed
# by uninstall. Files inside: styles.json, css-mapping.json, .fetched
V0_CACHE_REL = "dms/browserGlass"

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

# v0 plugin settings keys (pluginData) that v1 migrates.
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
# install leave userChrome.css, userContent.css and config.kdl untouched.
V1_IMPORT_CHROME = V0_IMPORT_CHROME
V1_IMPORT_CONTENT = V0_IMPORT_CONTENT
V1_NIRI_INCLUDE = V0_NIRI_INCLUDE

# All markers recognised by uninstall (v0 and v1).
USERJS_BLOCK_MARKERS = (
    (V0_USERJS_BEGIN, V0_USERJS_END),
    (V1_USERJS_BEGIN, V1_USERJS_END),
)
NIRI_INCLUDE_LINES = (V1_NIRI_INCLUDE,)

# ---- Prefs -------------------------------------------------------------------
PREF_STYLESHEETS = "toolkit.legacyUserProfileCustomizations.stylesheets"
PREF_TRANSPARENT = "browser.tabs.allow_transparent_browser"
PREF_COLOR_SCHEME = "layout.css.prefers-color-scheme.content-override"
# Companion add-on prefs (liveControl): load an unsigned add-on, and load the
# ones placed in the profile folder without a prompt (bit 1 = profile scope).
PREF_SIGNATURES = "xpinstall.signatures.required"
PREF_AUTODISABLE = "extensions.autoDisableScopes"
PREF_STARTUP_SCAN = "extensions.startupScanScopes"
# Prefs whose original prefs.js value is recorded in the state on first
# contact and restored on uninstall (instead of deleting the line).
PREFS = (PREF_STYLESHEETS, PREF_TRANSPARENT, PREF_COLOR_SCHEME,
         PREF_SIGNATURES, PREF_AUTODISABLE, PREF_STARTUP_SCAN)
# The companion prefs (written only while the add-on is deposited in the profile).
COMPANION_PREFS = (PREF_SIGNATURES, PREF_AUTODISABLE, PREF_STARTUP_SCAN)
# Browser defaults of the two scope prefs (prefs.js has no line at the default).
AUTODISABLE_DEFAULT = 15
STARTUP_SCAN_DEFAULT = 0
SCOPE_PROFILE = 1  # the profile scope bit of both scope prefs
# Values v0 could have written (JS literal text). Without a v1 state, uninstall
# only removes prefs.js lines carrying one of these values. v0 never wrote
# the companion prefs.
V0_PREF_VALUES = {
    PREF_STYLESHEETS: ("true",),
    PREF_TRANSPARENT: ("true", "false"),
    PREF_COLOR_SCHEME: ("0", "1"),
    PREF_SIGNATURES: (),
    PREF_AUTODISABLE: (),
    PREF_STARTUP_SCAN: (),
}
# layout.css.prefers-color-scheme.content-override values.
COLOR_SCHEME_DARK = 0
COLOR_SCHEME_LIGHT = 1
COLOR_SCHEME_BROWSER = 2  # "automatic": follow the browser's light/dark theme

# ---- Browser families, profile roots and niri app-ids ----------------------
FAMILIES = ("firefox", "librewolf", "zen", "floorp", "waterfox")
VARIANTS = ("native", "flatpak", "snap")

# base: "home" ($HOME) or "config" ($XDG_CONFIG_HOME, default $HOME/.config;
# Firefox >= 147 and v0 both honour XDG_CONFIG_HOME). rel is relative to base.
# Convention for the XDG layouts: every app gets its legacy dot-dir AND
# an XDG directory. Where the native XDG layout is known (mozilla/firefox,
# librewolf/librewolf, zen) the Flatpak sandbox gets the same path under
# config/; elsewhere, and in addition for LibreWolf, the plain
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

# /proc/PID/comm values accepted by the `lock` symlink fallback: exact
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
    ("liveControl", True),
    ("darkPages", True),
])
# The largest `sync --settings-file` the script reads (bytes)
SETTINGS_FILE_MAX = 4 * 1024 * 1024
# The file in $XDG_RUNTIME_DIR the daemon passes to `sync --settings-file`
# (logic.js SETTINGS_FILE_NAME); uninstall removes one a sync never read
SYNC_SETTINGS_NAME = "browserGlass-sync-settings.json"

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
    return write_bytes_if_changed(path, text.encode("utf-8", "surrogateescape"),
                                  warnings, family, profile, mode, make_dirs)


def write_bytes_if_changed(path, data, warnings=None, family=None, profile=None,
                           mode=None, make_dirs=True):
    """write_if_changed() for `data` (bytes), compared byte for byte."""
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


# ---- Zen transparency mods ---------------------------------------------------
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
    or pref enabled. Never raises."""
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

# Is a browser running on a profile?
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


# ============================================================================
# inputs
# ============================================================================

# The opacity DMS gives every window: that of the first global window-rule
# (no `match` child) of $XDG_CONFIG_HOME/niri/dms/windowrules.kdl that sets
# one, as v0 did. An `exclude` child does not make a rule local: in niri a
# rule without `match` applies to every window but the excluded ones.
# Without the file, without such a rule, or with an unreadable value:
# DEFAULT_OPACITY (fully opaque, so no glass). The value is clamped to [0, 1].
# The file is read only, never written.
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


def _kdl_string(text, match):
    """(token, end index) for the string whose opening is `match`.

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
                token, i = _kdl_string(text, match)
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


def plugin_disabled(env=None):
    """True when $XDG_CONFIG_HOME/dms/plugin_settings.json says DMS has
    browserGlass disabled: its entry has "enabled": false, which DMS's
    disablePlugin writes and which makes the daemon's onDestruction run the
    uninstall (logic.js teardownAction, enabled === false). False when the
    file is missing, unreadable, not a JSON object or has no such value: no
    uninstall ran then."""
    path = os.path.join(xdg_dir("XDG_CONFIG_HOME", env), DMS_PLUGIN_SETTINGS_REL)
    try:
        doc = json.loads(read_text(path).lstrip("\ufeff"))
    except (OSError, ValueError, RecursionError):
        return False
    if not isinstance(doc, dict):
        return False
    entry = doc.get(PLUGIN_ID)
    return isinstance(entry, dict) and entry.get("enabled") is False


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


def dms_surfaces(env=None):
    """{mode: surface} of both DMS modes (see dms_colors)."""
    return {mode: dms_colors(env, mode).surface for mode in MODES}

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


def read_settings_file(path):
    """The --settings JSON text of `sync --settings-file PATH`, then PATH is
    deleted (read or not). The daemon writes it in $XDG_RUNTIME_DIR (mode
    700) just before the sync: the excluded sites never go in an argv,
    which every local user can read in /proc/PID/cmdline. It must be a
    regular file of this user (no symlink) of at most SETTINGS_FILE_MAX
    bytes. Raises ValueError otherwise, or when it cannot be read.
    """
    try:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        except OSError as exc:
            raise ValueError(_oserror_text(exc))
        with os.fdopen(fd, "rb") as handle:
            st = os.fstat(handle.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
                raise ValueError("not a regular file of this user")
            data = handle.read(SETTINGS_FILE_MAX + 1)
        if len(data) > SETTINGS_FILE_MAX:
            raise ValueError("larger than %d bytes" % SETTINGS_FILE_MAX)
        return data.decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise ValueError(_oserror_text(exc))
    finally:
        try:
            if stat.S_ISREG(os.lstat(path).st_mode):
                os.unlink(path)
        except OSError:
            pass


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
    v0 migration: the v0 key excludedSites ([{"domain": ...}]) is merged
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

# The tint is written for both DMS modes and picked by the browser's own
# light/dark theme, so it always matches the toolbar text colour and follows
# a theme switch live (a stylesheet is only re-read on restart).
_CHROME_TINT = (
    "{selector} {{\n"
    "  background: rgba({dark}, {a}) !important;\n"
    "}}\n"
    "@media (prefers-color-scheme: light) {{\n"
    "  {selector} {{\n"
    "    background: rgba({light}, {a}) !important;\n"
    "  }}\n"
    "}}\n"
)
_CHROME_GLASS = (
    ":root, #main-window, #browser, #appcontent, #navigator-toolbox,\n"
    "#TabsToolbar, #nav-bar, #PersonalToolbar,\n"
    "#tabbrowser-tabbox, #tabbrowser-tabpanels,\n"
    ".browserContainer, .browserStack, browser {\n"
    "  background: transparent !important;\n"
    "  border: none !important;\n"
    "}\n"
)
# privateGlass=false: private windows get an opaque tint. "temporary" only:
# "permanent" is the always-private mode, which must stay like normal windows.
_CHROME_PRIVATE_SELECTOR = ':root[privatebrowsingmode="temporary"] body'
# Generic page rule: web pages get transparent html and body. Under a light
# browser theme every page does (the tint is light, like most pages). Under a
# dark one only pages that say they have a dark mode do: a light-only page
# (dark text, no dark mode) would be unreadable on the dark tint, so it keeps
# its own background. A page says so with <meta name="color-scheme"> naming
# "dark", or a dark-mode marker on <html> (_DARK_PAGE_MARKERS).
_DARK_PAGE_MARKERS = (
    ':has(> head > meta[name="color-scheme" i][content~="dark" i])',
    '[data-theme~="dark" i]', '[data-theme-mode="dark" i]', '[data-color-mode="dark" i]',
    '[data-bs-theme="dark" i]', '[data-mode="dark" i]', '[dark]', '.dark', '.dark-mode',
    '.theme-dark',
    ':has(> body > #outerContainer #viewerContainer)',  # pdf.js: light-dark() colours
)
# :where(): no added specificity, so the opaque PDF rule still wins.
_DARK_PAGE_WHERE = ":where(%s)" % ", ".join(_DARK_PAGE_MARKERS)
_DARK_PAGE_ROOT = ":root" + _DARK_PAGE_WHERE
# With liveControl a page the companion add-on measured (ATTR_TONE) counts
# as one with a dark version: the tone tint (_CONTENT_TONE) makes it legible.
_DARK_PAGE_TONE_WHERE = ":where(%s)" % ", ".join(_DARK_PAGE_MARKERS + ("[%s]" % ATTR_TONE,))
_DARK_PAGE_TONE_ROOT = ":root" + _DARK_PAGE_TONE_WHERE


def _content_generic(dark_root):
    """The rules of the generic page block (_content_block, regexp
    "https?://<exclusion lookahead>.*"), `dark_root` the root condition of
    a page made see-through under a dark theme."""
    return ("  @media not (prefers-color-scheme: dark) {\n"
            "    html, body { background: transparent !important; }\n"
            "  }\n"
            "  @media (prefers-color-scheme: dark) {\n"
            "    " + dark_root + ",\n"
            "    " + dark_root + " > body { background: transparent !important; }\n"
            "  }\n")


_CONTENT_GENERIC = _content_generic(_DARK_PAGE_ROOT)
_CONTENT_GENERIC_TONE = _content_generic(_DARK_PAGE_TONE_ROOT)  # liveControl
# Tone tint (liveControl, a block with the regexp "https?://.*", after the
# site styles): a page whose measured tone is not the theme's gets the
# glass of its own tone on <html>, the DMS surface of that mode at
# SITES_TONE_OPACITY, and the bar variable to match: a light page under a
# dark theme gets a light glass, a dark page under a light theme a dark one.
# "html:root[...]" (0,2,1) beats the "html" and ":root" backgrounds of the
# site styles (html { background: transparent !important }).
# A page that declares a dark version (_DARK_PAGE_MARKERS) never gets the
# light glass, whatever was measured: a single-page app (YouTube) may show
# little text when the add-on first measures it.
SITES_TONE_OPACITY = 0.88
_CONTENT_TONE = (
    "  @media (prefers-color-scheme: dark) {{\n"
    "    html:root[" + ATTR_TONE + "=\"light\"]:not(" + _DARK_PAGE_WHERE + ") {{\n"
    "      background: rgba({light}, {a}) !important;\n"
    "      --browserglass-bar: rgba({light}, {bar});\n"
    "    }}\n"
    "  }}\n"
    "  @media not (prefers-color-scheme: dark) {{\n"
    "    html:root[" + ATTR_TONE + "=\"dark\"] {{\n"
    "      background: rgba({dark}, {a}) !important;\n"
    "      --browserglass-bar: rgba({dark}, {bar});\n"
    "    }}\n"
    "  }}\n"
)
# Dark pages (darkPages, with liveControl; a block with the regexp
# "https?://.*", after the tone tint): under a dark theme, the root of a page
# without a dark version carries the two colours the companion add-on turns
# it dark with (its Dark Reader engine, extension/vendor/), the DMS dark
# surface and the light one for the text. The add-on reads them: a page
# without them (an excluded one, a light theme, a page with a dark version)
# is left as it is. The large elements that paint the page's background,
# which the add-on marks once the page is dark, become glass (_CONTENT_LAYERS).
_CONTENT_DARKEN = (
    "  @media (prefers-color-scheme: dark) {{\n"
    "    html:root:not(" + _DARK_PAGE_WHERE + ") {{\n"
    "      --browserglass-darken-bg: {dark_hex};\n"
    "      --browserglass-darken-fg: {light_hex};\n"
    "    }}\n"
    "  }}\n"
)
# Page layers (with liveControl, a block with the regexp "https?://.*"),
# which the companion add-on marks:
# - the page's own background (ATTR_CANVAS): with the root and the body
#   see-through, the lowest layer that paints an opaque background colour
#   over most of the window (a fixed full-window container, a wrapper):
#   glass;
# - a navigation bar (ATTR_BAR): fixed or sticky along an edge of the
#   window (a header, a bottom bar, a sidebar), or laid along one in a page
#   that does not scroll (a web app's shell), whatever its own colours.
#   Every site gets the same: the DMS surface at NAV_BAR_OPACITY over a
#   strong blur, the dark one on a dark (or darkened) page, the light one
#   on a light page, by the theme otherwise. The page is tinted already,
#   so a light veil keeps the bar close to the browser's own toolbar (a
#   bar at 0.35 over the 0.8 tint shows about 0.87), while what scrolls
#   under it stays blurred enough to read the bar.
# Two ids in :not() outweigh the selectors of the generic and site styles
# (user !important rules too, so specificity decides).
NAV_BAR_OPACITY = 0.35
NAV_BAR_BLUR = "blur(40px) saturate(1.5)"
_BAR_SELECTOR = "[" + ATTR_BAR + "]:not(#browserglass-a):not(#browserglass-b)"
_CONTENT_LAYERS = (
    "  [" + ATTR_CANVAS + "] {{ background-color: transparent !important; }}\n"
    "  " + _BAR_SELECTOR + " {{\n"
    "    background: rgba({dark}, {nav}) !important;\n"
    "    backdrop-filter: " + NAV_BAR_BLUR + " !important;\n"
    "  }}\n"
    "  @media not (prefers-color-scheme: dark) {{\n"
    "    " + _BAR_SELECTOR + " {{ background: rgba({light}, {nav}) !important; }}\n"
    "  }}\n"
    "  html:root[" + ATTR_TONE + "=\"dark\"] " + _BAR_SELECTOR
    + " {{ background: rgba({dark}, {nav}) !important; }}\n"
    "  html:root[" + ATTR_TONE + "=\"light\"] " + _BAR_SELECTOR
    + " {{ background: rgba({light}, {nav}) !important; }}\n"
)
# --browserglass-bar: the DMS surface (the tint's colour) at SITES_BAR_OPACITY,
# for site parts that float over the page (data/sites/), with the light
# surface while the theme is light, like the chrome tint.
SITES_BAR_OPACITY = 0.8
# Rules of a block with the regexp "https?://.*" (_content_block).
_CONTENT_BAR_VAR = (
    "  :root {{ --browserglass-bar: rgba({dark}, {a}); }}\n"
    "  @media (prefers-color-scheme: light) {{\n"
    "    :root {{ --browserglass-bar: rgba({light}, {a}); }}\n"
    "  }}\n"
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


def inclusion_lookahead(domains):
    """Positive lookahead (CSS string text) accepting only `domains` and
    their subdomains right after "https?://" (the live section's blocks);
    "" when there are none."""
    domains = [d for d in domains if d]
    if not domains:
        return ""
    return "(?=(?:[^/]*\\\\.)?(?:%s)(?:[:/]|$))" % css_rx_alt(domains)


# ---- live gating (liveControl) ----------------------------------------------
#
# With liveControl, every rule of the http(s) blocks (generic rule, bar
# variable, site styles) applies only while <html> does not carry ATTR_OFF:
# the companion add-on sets it on a page excluded after the browser started,
# which turns glass off there without a restart. The blocks of the domains
# excluded at sync time come back in the live section (content_live_section),
# gated on ATTR_LIVE and not ATTR_OFF: the add-on sets ATTR_LIVE on every
# page it handles, so a domain taken off the list since the browser started
# gets its glass back. Without the add-on (a private window included, where
# it does not run) neither attribute is ever set: the normal blocks apply as
# in v1.0 and the live section is inert. With liveControl off nothing is
# gated and there is no live section (the v1.0 stylesheet, byte for byte).
#
# Shadow trees: user rules apply inside them, but for selectors their
# elements are neither :root nor under it (a combinator stops at the shadow
# root), so they cannot see the root's attributes. The normal gate lets
# them through (GATE_SHADOW_TOP in the wrapper, GATE_SHADOW_TREE in
# @scope): shadow content is styled as in v1.0,
# and stays so under ATTR_OFF (a limit). The live gate does not: an
# excluded site's shadow content stays unstyled, as in v1.0, ATTR_LIVE
# included (until a restart). In the wrapper, "& *" tests the branch on
# every ancestor, so it must not climb to the root there: GATE_SHADOW_TREE
# would (a match in depth squared), GATE_SHADOW_TOP only looks at the
# parent. On Firefox 160, restyling 14000 elements with a "*" rule at
# depth 40 / 80 (timer granularity 0.5 ms): 8 / 12.5 ms, against 4 / 5.5
# ungated and 13 / 29 with GATE_SHADOW_TREE in the wrapper; linear in the
# depth, at no size cost.
#
# Gating, "nesting run" (measured on Firefox 160: same cascade as the
# original, specificity unchanged, about +39 % size on the embedded data):
#   - each run of consecutive style rules of a rule list goes inside one
#     ":where(<root condition>){ ... }" (with the shadow branch for the
#     normal gate), and each complex selector of the run gets ":where(&,& *)"
#     on its subject compound, before a pseudo-element: it matches only at
#     or under a root meeting the condition, with zero added specificity;
#   - group rules (_GATE_GROUP_RULES) stay outside the wrapper and are gated
#     recursively; inside @scope, where a wrapper selector would be relative
#     to the scope root (and could never match <html>), each selector gets the
#     plain ":where(C, C *)" instead (the shadow branch added the same way),
#     and each declaration (Firefox applies it to the scope root) goes in
#     ":where(:scope:where(C, C *)){ ... }", the implicit ":where(:scope)"
#     rule made explicit;
#   - every other at-rule (@keyframes, @font-face, @page, @property, the
#     statements) is copied as it is (the live section leaves out those
#     with a block, @keyframes apart: see _Nest), and so is what Firefox
#     drops at rule-list level with its {} block (a prelude starting with
#     "--x:", or holding a ";", like a declaration left outside a rule, or
#     with a complex selector starting with a combinator): inside the
#     wrapper it would be a declaration of the root or a nested rule, so it
#     would apply; a ";" before a rule is skipped by Firefox, and so it
#     stays where it is;
#   - a selector list starting with a "--x" type selector (it never
#     matches) stays outside the wrapper, which would make it "--x:", a
#     declaration eating the next rules: its other selectors get the plain
#     ":where(C, C *)", as in @scope;
#   - a style rule's own body is never touched: its nested rules are relative
#     to it, so already gated.
# Text is only inserted, never removed or reordered (but for the at-rules
# the live section leaves out). The input is a site style that passed
# sites_validate, or one of this file's own rules.
GATE_NORMAL_ROOT = ":root:not([%s])" % ATTR_OFF
GATE_LIVE_ROOT = ":root[%s]:not([%s])" % (ATTR_LIVE, ATTR_OFF)
# Any element of a shadow tree, none of the document tree.
GATE_SHADOW_TREE = ":not(:root,:root *)"
# The top elements of a shadow tree (no parent element), never the root:
# with "& *" it lets every element of a shadow tree through, testing each
# ancestor in constant time (see "Shadow trees" above).
GATE_SHADOW_TOP = ":not(:root,* *)"
# The root condition of a site style under a dark theme (_scheme_gated), for
# each gate it is built with (None: liveControl off): the page declares a
# dark version, or with liveControl carries the add-on's measured tone. The
# shadow branch and the at-rules follow the gate's (see _Nest), but a
# shadow tree cannot see the root's markers or tone: the generic style
# leaves it out (as v1.0 did), the dedicated ones keep it (see
# _scheme_gated).
GATE_DARK = {
    None: _DARK_PAGE_ROOT,
    GATE_NORMAL_ROOT: GATE_NORMAL_ROOT + _DARK_PAGE_TONE_WHERE,
    GATE_LIVE_ROOT: GATE_LIVE_ROOT + _DARK_PAGE_TONE_WHERE,
}
_GATE_SHADOW_CONDS = frozenset((GATE_NORMAL_ROOT, GATE_DARK[None], GATE_DARK[GATE_NORMAL_ROOT]))
_GATE_LIVE_CONDS = frozenset((GATE_LIVE_ROOT, GATE_DARK[GATE_LIVE_ROOT]))
_GATE_GROUP_RULES = frozenset(("media", "supports", "layer", "container", "scope",
                               "starting-style", "document", "-moz-document"))
_GATE_KEYFRAMES = frozenset(("keyframes", "-webkit-keyframes", "-moz-keyframes"))
# Pseudo-elements also written with one colon (CSS 2).
_GATE_LEGACY_PSEUDO_ELEMENTS = frozenset(("before", "after", "first-line", "first-letter"))
# One token at a time, as far as structure and selectors need: comments,
# strings (a newline ends one, broken), unquoted url(), identifiers (escapes
# included), whitespace, any other single character.
_GATE_TOK = re.compile(
    r"(?P<comment>/\*[\s\S]*?(?:\*/|\Z))"
    r"|(?P<string>\"(?:[^\"\\\n\r\f]|\\[\s\S])*(?:\"|(?=[\n\r\f])|\Z)"
    r"|'(?:[^'\\\n\r\f]|\\[\s\S])*(?:'|(?=[\n\r\f])|\Z))"
    r"|(?P<url>[Uu][Rr][Ll]\((?![ \t\n\r\f]*[\"'])(?:[^)\\]|\\[\s\S])*(?:\)|\Z))"
    r"|(?P<ident>(?:[A-Za-z0-9_\-\x80-\U0010ffff]"
    r"|\\(?:[0-9A-Fa-f]{1,6}[ \t\n\r\f]?|[^\n\r\f]))+)"
    r"|(?P<ws>[ \t\n\r\f]+)"
    r"|(?P<ch>[\s\S])")
# A run of _GATE_TOK tokens that bracket and stop scans skip as a whole:
# identifiers (not a url( token), whitespace, single characters other than
# brackets, quotes, "/", a backslash and ";" (each of those goes through
# _GATE_TOK).
_GATE_SKIP = re.compile(
    r"(?:(?![Uu][Rr][Ll]\((?![ \t\n\r\f]*[\"']))"
    r"(?:(?:[A-Za-z0-9_\-\x80-\U0010ffff]|\\(?:[0-9A-Fa-f]{1,6}[ \t\n\r\f]?|[^\n\r\f]))+"
    r"|[^{}()\[\]\"'/\\;A-Za-z0-9_\-\x80-\U0010ffff]))+")
# The same for css_gate_selector_list: identifiers and single characters
# with no role in a selector's structure (not whitespace, ",", a combinator,
# ":", a bracket, a quote, "/" or a backslash).
_GATE_SEL_PLAIN = re.compile(
    r"(?:(?![Uu][Rr][Ll]\((?![ \t\n\r\f]*[\"']))"
    r"(?:(?:[A-Za-z0-9_\-\x80-\U0010ffff]|\\(?:[0-9A-Fa-f]{1,6}[ \t\n\r\f]?|[^\n\r\f]))+"
    r"|[^ \t\n\r\f,>+~|:()\[\]\"'/\\A-Za-z0-9_\-\x80-\U0010ffff]))+")
_GATE_WS = re.compile(r"[ \t\n\r\f]*")
# A custom-property-looking name and its colon. At rule-list level Firefox
# drops it up to the end of the next {} block (a ";" does not end it), like
# a prelude starting with a combinator; inside @scope it is a declaration,
# which ends at the next top-level ";" or "}".
_GATE_BAD_DECL = re.compile(
    r"--(?:[A-Za-z0-9_\-\x80-\U0010ffff]|\\[\s\S])*[ \t\n\r\f]*:")


def _gate_name(raw):
    """CSS name `raw` unescaped and ASCII-lowercased, as CSS compares it."""
    return (css_unescape(raw) if "\\" in raw else raw).translate(_ASCII_LOWER)


def _gate_block_end(text, pos, end):
    """Position after the bracket matching the one at `pos` (end when it
    is never closed before `end`)."""
    depth = 0
    while pos < end:
        skip = _GATE_SKIP.match(text, pos)
        if skip:
            pos = skip.end()
            continue
        match = _GATE_TOK.match(text, pos)
        pos = match.end()
        char = match.group("ch")
        if char is None:
            continue
        if char in "{([":
            depth += 1
        elif char in "})]":
            depth -= 1
            if depth == 0:
                return pos
    return end


def _gate_prelude_end(text, pos, end, stops):
    """Position of the first top-level character of `stops` from `pos`,
    `end` when there is none before it."""
    depth = 0
    while pos < end:
        skip = _GATE_SKIP.match(text, pos, end)
        if skip:
            pos = skip.end()
            continue
        match = _GATE_TOK.match(text, pos)
        char = match.group("ch")
        if char is not None:
            if depth == 0 and char in stops:
                return match.start()
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
        pos = match.end()
    return end


def css_gate_selector_list(sel, gate, skip_first=False):
    """`sel` (a selector list) with `gate` inserted in each complex selector
    (but the first one with `skip_first`), at the end of its subject
    compound (after the last top-level combinator: whitespace, ">", "+",
    "~", "||") and before its first pseudo-element ("::x", or a legacy
    ":before" not followed by "("). Comments are skipped; strings, url(),
    escapes, () and [] are nesting."""
    inserts, _ = _gate_selector_scan(sel)
    out = []
    pos = 0
    for item, at in inserts:
        if item or not skip_first:
            out += [sel[pos:at], gate]
            pos = at
    out.append(sel[pos:])
    return "".join(out)


def _gate_selector_relative(sel):
    """Whether a complex selector of the selector list `sel` starts with a
    combinator (">", "+", "~"): a relative selector, which Firefox reads in
    a nested rule or @scope only (at rule-list level it drops the rule)."""
    return _gate_selector_scan(sel)[1]


def _gate_selector_scan(sel):
    """([(item, position)], relative) for css_gate_selector_list: where the
    gate goes in each non-empty complex selector of `sel` (`item` its index
    in the list), and _gate_selector_relative(sel)."""
    inserts = []
    item = 0
    starting = True  # nothing but whitespace and comments yet in this item
    relative = False
    depth = 0
    pe_at = last_end = None
    gap = False
    pos, end = 0, len(sel)
    while pos < end:
        plain = _GATE_SEL_PLAIN.match(sel, pos)
        if plain:
            # one or more tokens of a compound: no role of their own
            if depth == 0:
                if gap and last_end is not None:
                    pe_at = None  # descendant combinator: a new compound starts
                gap = starting = False
                last_end = plain.end()
            pos = plain.end()
            continue
        match = _GATE_TOK.match(sel, pos)
        pos = match.end()
        kind, char = match.lastgroup, match.group("ch")
        if kind == "comment":
            continue
        if kind == "ws":
            gap = gap or depth == 0
            continue
        if depth == 0:
            if char == ",":
                if last_end is not None:
                    inserts.append((item, pe_at if pe_at is not None else last_end))
                item += 1
                starting = True
                pe_at = last_end = None
                gap = False
                pos = _GATE_WS.match(sel, pos).end()  # whitespace after: no role
                continue
            relative = relative or (starting and char in (">", "+", "~"))
            starting = False
            column = char == "|" and sel.startswith("|", pos)
            if char in (">", "+", "~") or column:
                pe_at, gap = None, False
                # the second "|" of "||", and the whitespace after: no role
                pos = _GATE_WS.match(sel, pos + column).end()
                continue
            if gap and last_end is not None:
                pe_at = None  # descendant combinator: a new compound starts
            gap = False
            if char == ":" and pe_at is None and pos < end:
                nxt = _GATE_TOK.match(sel, pos)
                if nxt.group("ch") == ":":
                    pe_at = match.start()
                elif (nxt.group("ident")
                      and _gate_name(nxt.group("ident")) in _GATE_LEGACY_PSEUDO_ELEMENTS
                      and not sel.startswith("(", nxt.end())):
                    pe_at = match.start()
        if char is not None and char in "([":
            depth += 1
        elif char is not None and char in ")]":
            depth = max(0, depth - 1)
        if depth == 0:
            last_end = match.end()
    if last_end is not None:
        inserts.append((item, pe_at if pe_at is not None else last_end))
    return inserts, relative


class _Nest:
    """The texts css_gate_rules inserts for the root condition `cond` (with
    the shadow branch for GATE_NORMAL_ROOT and its GATE_DARK conditions
    unless `shadow` is false: see "live gating" above)."""

    def __init__(self, cond, shadow=True):
        shadow = shadow and cond in _GATE_SHADOW_CONDS
        top = "," + GATE_SHADOW_TOP if shadow else ""
        tree = "," + GATE_SHADOW_TREE if shadow else ""
        self.open = ":where(%s%s){" % (cond, top)  # wraps a run of style rules
        self.amp = ":where(&,& *)"          # each selector of the run
        self.plain = ":where(%s, %s *%s)" % (cond, cond, tree)  # each selector in @scope
        self.scope_open = ":where(:scope%s){" % self.plain  # each declaration in @scope
        # the at-rules with a block that cannot be gated are left out of
        # the live section, which applies on excluded domains without
        # ATTR_LIVE too (only @keyframes stay: used by name, by gated rules)
        self.ungated_at_rules = cond not in _GATE_LIVE_CONDS


def css_gate_rules(text, root_cond, shadow=True):
    """The rule list `text` gated on the root condition `root_cond`
    (GATE_NORMAL_ROOT, GATE_LIVE_ROOT, a GATE_DARK one), without the shadow
    branch when `shadow` is false: see "live gating" above. Memoized:
    sync gates the same site styles again for its restart render."""
    return _gate_rules_memo(text, root_cond, shadow)


@functools.lru_cache(maxsize=4096)
def _gate_rules_memo(text, root_cond, shadow):
    return _gate_rule_list(text, _Nest(root_cond, shadow), 0, len(text))


def _gate_rule_list(text, nest, pos, end, scoped=False):
    """text[pos:end] (a rule list) gated with the texts of `nest` (a _Nest):
    a nesting run, or inside @scope (`scoped`) the plain selector gate."""
    final = []
    run = []

    def flush():
        if run:
            # the run's trailing whitespace goes after the wrapper (easier
            # to read); its comments stay inside: harmless
            tail = []
            while run[-1].isspace():
                tail.insert(0, run.pop())
            final.append(nest.open + "".join(run) + "}" + "".join(tail))
            del run[:]

    def outside(piece):
        flush()
        final.append(piece)

    while pos < end:
        match = _GATE_TOK.match(text, pos)
        kind = match.lastgroup
        char = match.group("ch")
        if kind in ("ws", "comment") or char == ";":
            # a ";" before a rule (or a declaration) is skipped by Firefox
            (run if run else final).append(match.group())
            pos = match.end()
            continue
        if char == "}":  # stray: copied, the structure stays the same
            outside(char)
            pos = match.end()
            continue
        if char == "@":
            name = _GATE_TOK.match(text, match.end()) if match.end() < end else None
            name = _gate_name(name.group("ident") or "") if name and name.end() <= end else ""
            stop = _gate_prelude_end(text, pos, end, "{;}")
            if stop >= end or text[stop] != "{":
                stop = min(stop + (1 if stop < end and text[stop] == ";" else 0), end)
                outside(text[pos:stop])
                pos = stop
                continue
            close = _gate_block_end(text, stop, end)
            if name in _GATE_GROUP_RULES:
                inner = _gate_rule_list(text, nest, stop + 1, close - 1, scoped or name == "scope")
                outside(text[pos:stop + 1] + inner + "}")
            elif nest.ungated_at_rules or name in _GATE_KEYFRAMES:
                outside(text[pos:close])
            else:
                flush()  # left out (see _Nest)
            pos = close
            continue
        stop = _gate_prelude_end(text, pos, end, "{;}")
        if scoped and (_GATE_BAD_DECL.match(text, pos, end) or stop >= end or text[stop] != "{"):
            # inside @scope: a declaration (of the scope root), up to ";" or "}"
            stop = _gate_prelude_end(text, pos, end, ";}")
            stop = stop + 1 if stop < end and text[stop] == ";" else stop
            final.append(nest.scope_open + text[pos:stop] + "}")
            pos = stop
            continue
        has_semicolon = stop < end and text[stop] == ";"
        if has_semicolon:
            stop = _gate_prelude_end(text, stop, end, "{}")
        if stop >= end or text[stop] != "{":
            outside(text[pos:stop])
            pos = stop
            continue
        close = _gate_block_end(text, stop, end)
        prelude = text[pos:stop]
        if not scoped and (has_semicolon or _GATE_BAD_DECL.match(prelude)
                           or _gate_selector_relative(prelude)):
            outside(prelude + text[stop:close])  # dropped by Firefox, block included: kept so
        elif prelude.startswith("--"):
            # a "--x" type selector first (it never matches): the others
            # gated, outside any wrapper (the gate after it would be "--x:")
            outside(css_gate_selector_list(prelude, nest.plain, skip_first=True)
                    + text[stop:close])
        else:
            piece = css_gate_selector_list(prelude, nest.plain if scoped else nest.amp)
            (final if scoped else run).append(piece + text[stop:close])
        pos = close
    flush()
    return "".join(final)


def live_gate(settings):
    """The root condition the normal http(s) blocks are gated on:
    GATE_NORMAL_ROOT with liveControl, None (not gated) without."""
    return GATE_NORMAL_ROOT if settings["liveControl"] else None


def _css_head(note):
    return "%s\n/* %s */\n" % (V1_CSS_HEADER, note)


def chrome_css(settings, opacity, surfaces, off=False):
    """Text of chrome/dms-glass-chrome.css (imported by userChrome.css).

    `surfaces` maps "dark" and "light" to the DMS surface of that mode
    (DEFAULT_SURFACES for a missing or unusable one): the dark tint is the
    default, the light one applies while the browser's theme is light.
    """
    active, reason = glass_state(settings, opacity, off)
    if not active:
        return _css_head("glass inactive (%s): neutral file" % reason)
    opacity = _clamp01(opacity)
    surfaces = surfaces if isinstance(surfaces, dict) else {}
    rgb = {mode: surface_rgb(surfaces.get(mode), mode) for mode in MODES}
    rgb_text = {mode: "%d, %d, %d" % rgb[mode] for mode in MODES}
    text = _css_head("glass active: opacity %s, surface dark #%02x%02x%02x, light #%02x%02x%02x"
                     % ((format_number(opacity),) + rgb["dark"] + rgb["light"]))
    text += _CHROME_TINT.format(selector="body", a=format_number(opacity), **rgb_text)
    text += _CHROME_GLASS
    if not settings["privateGlass"]:
        text += _CHROME_TINT.format(selector=_CHROME_PRIVATE_SELECTOR, a="1", **rgb_text)
    return text


def _content_block(rx, rules, gate=None):
    """@-moz-document regexp("`rx`") block holding `rules` ("\\n" ends),
    gated on the root condition `gate` when given (css_gate_rules)."""
    if gate:
        rules = css_gate_rules(rules, gate)
    return '@-moz-document regexp("%s") {\n%s}\n' % (rx, rules)


def content_css(settings, opacity, sites_css="", off=False, surfaces=None, sites=None):
    """Text of chrome/dms-glass-content.css (imported by userContent.css).

    `sites_css` is the output of sites_build_css() (already validated, and
    gated on live_gate(settings)), put after the generic and special-page
    rules and before the PDF rule, behind the --browserglass-bar variable
    (`surfaces` as in chrome_css). With liveControl the http(s) rules are
    gated, a page the add-on measured counts as one with a dark version and
    gets the tone tint (_CONTENT_TONE) after the site styles, and the live
    section (content_live_section, with the site styles of `sites`, a Sites
    or None) comes before the PDF rule.
    """
    active, reason = glass_state(settings, opacity, off)
    if not active:
        return _css_head("glass inactive (%s): neutral file" % reason)
    if not settings["pagesTransparent"]:
        return _css_head("page transparency disabled: neutral file")
    gate = live_gate(settings)
    parts = [_css_head("page backgrounds are transparent (the DMS tint is behind them); "
                       "images, videos and text stay opaque")]
    parts.append(_content_block("https?://%s.*" % exclusion_lookahead(settings["excluded"]),
                                _CONTENT_GENERIC_TONE if gate else _CONTENT_GENERIC, gate))
    if not settings["readerOpaque"]:
        parts.append(_CONTENT_READER_GLASS)
    if settings["newTabGlass"]:
        parts.append(_CONTENT_NEWTAB_GLASS)
    surfaces = surfaces if isinstance(surfaces, dict) else {}
    rgb = {mode: "%d, %d, %d" % surface_rgb(surfaces.get(mode), mode) for mode in MODES}
    bar = format_number(SITES_BAR_OPACITY)
    if sites_css and sites_css.strip():
        parts.append(_content_block("https?://.*", _CONTENT_BAR_VAR.format(a=bar, **rgb), gate))
        parts.append(sites_css if sites_css.endswith("\n") else sites_css + "\n")
    if gate:
        # one block for every page: ATTR_TONE comes with the add-on, which
        # also sets ATTR_OFF on an excluded page (see "live gating")
        parts.append(_content_block("https?://.*", _CONTENT_TONE.format(
            a=format_number(SITES_TONE_OPACITY), bar=bar, **rgb), gate))
        parts.append(_content_block("https?://.*", _CONTENT_LAYERS.format(nav=format_number(NAV_BAR_OPACITY), **rgb), gate))
        if settings["darkPages"]:
            hexes = {mode + "_hex": "#%02x%02x%02x" % surface_rgb(surfaces.get(mode), mode)
                     for mode in MODES}
            parts.append(_content_block("https?://.*", _CONTENT_DARKEN.format(**hexes), gate))
        live = content_live_section(settings, sites)
        if live:
            parts.append(live)
    if settings["readerOpaque"]:
        parts.append(_CONTENT_PDF_OPAQUE)
    return "\n".join(parts)


# Comment line of the live section.
_CONTENT_LIVE_COMMENT = ("/* Live: the domains excluded at sync, back while the companion "
                         "add-on says they are not */")


def content_live_section(settings, sites):
    """The live section of the content stylesheet (see "live gating"): the
    generic page rule and the site style blocks of the domains of
    settings["excluded"], restricted to them (inclusion_lookahead) and gated
    on GATE_LIVE_ROOT. `sites` is a Sites (None: the generic rule only).
    "" when no domain is excluded.

    A site block is kept when its regexp matches a probe URL https://H/,
    for each probe host H: each excluded domain D, www.D and x0.D, the same
    for each dedicated or mapped host of the site styles that D covers, and
    the hosts of the dash styles D covers (_live_hosts). Only the blocks
    that may match one (_sites_block_rows) have their regexp compiled.
    """
    domains = [d for d in settings["excluded"] if d]
    if not domains:
        return ""
    look = inclusion_lookahead(domains)
    out = [_CONTENT_LIVE_COMMENT + "\n"
           + _content_block("https?://%s.*" % look, _CONTENT_GENERIC_TONE, GATE_LIVE_ROOT)]
    if sites is not None:
        generic = settings["genericStyle"]
        hosts = _live_hosts(_sites_index(sites, generic), domains)
        rows = _sites_block_rows(sites, (), settings["disabledStyles"], generic)
        for comment, tail, body, may_match in rows:
            if not any(may_match(host) for host in hosts):
                continue
            rx = re.compile(css_unescape("https?://" + tail))
            if any(rx.fullmatch("https://%s/" % host) for host in hosts):
                out.append(_sites_block_text(comment, "https?://" + look + tail, body,
                                             GATE_LIVE_ROOT) + "\n")
    return "\n".join(out)


def userjs_prefs(settings, opacity, off=False, profile=None, companion=None):
    """[(pref, JS literal)] of the user.js block, in PREFS order.

    The stylesheet pref is always on (the imported files must load);
    transparent browser only while glass is active with transparent pages;
    the colour-scheme override follows siteTheme: "follow" -> 2 (sites follow
    the browser's theme, live, like the chrome tint), "dark" -> 0, "none" ->
    not written (its original value is restored from the state by sync).
    `profile` (a Profile, None for any) is the profile the block is for.
    `companion`, None when the companion add-on is not deposited in the
    profile, holds the original prefs.js values ({pref: JS literal or None})
    the companion prefs are derived from (companion_prefs).
    """
    active, _ = glass_state(settings, opacity, off)
    prefs = [
        (PREF_STYLESHEETS, "true"),
        (PREF_TRANSPARENT, "true" if active and settings["pagesTransparent"] else "false"),
    ]
    theme = settings["siteTheme"]
    if theme == "follow":
        prefs.append((PREF_COLOR_SCHEME, str(COLOR_SCHEME_BROWSER)))
    elif theme == "dark":
        prefs.append((PREF_COLOR_SCHEME, str(COLOR_SCHEME_DARK)))
    if companion is not None:
        prefs += companion_prefs(companion)
    return prefs


def userjs_block_text(prefs):
    """The v1 managed block of user.js holding `prefs` ([(pref, JS literal)],
    marker lines included, "\\n" ends)."""
    lines = [V1_USERJS_BEGIN]
    lines += ['user_pref("%s", %s);' % pref for pref in prefs]
    lines.append(V1_USERJS_END)
    return "\n".join(lines) + "\n"


def userjs_block(settings, opacity, off=False, profile=None):
    """The v1 managed block of user.js (marker lines included, "\\n" ends)."""
    return userjs_block_text(userjs_prefs(settings, opacity, off, profile))


def niri_kdl(rule_needed):
    """Text of $XDG_CONFIG_HOME/niri/dms-browser-glass.kdl.

    With `rule_needed` (decided by sync: true while a running browser has
    glass loaded, or glass is active) it holds a window-rule giving the
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
# are in English, disabled or broken styles only lose their own block, and
# the generic style keeps background images (_GENERIC_NO_BACKGROUND).
# data/styles.json is the upstream file minus the keys hitting the
# project's name denylist (tests/py/test_leaks.py); the data updater must
# keep applying it.
SITES_STYLES_FILE = "styles.json"
SITES_MAPPING_FILE = "css-mapping.json"
SITES_GENERIC_KEY = "example.com.css"
SITES_KEEP = re.compile(r"transparen|glass|translucent", re.I)
SITES_HEADER = "/* Site styles: sameerasw/my-internet (MIT); generated, do not edit */"
# browserGlass's own site css: data/sites/<style name>.css, one plain file per
# style, added as the style's last feature (its name matches SITES_KEEP). It
# extends the my-internet style of that name, or is a new style on its own.
SITES_OWN_DIR = "sites"
SITES_OWN_FEATURE = "browserGlass additions"
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
    (optional: missing or corrupt gives no mapping, as in v0), plus
    browserGlass's own `data_dir`/sites/*.css (_sites_own).

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
    for key, css in _sites_own(data_dir):
        styles.setdefault(key, collections.OrderedDict())[SITES_OWN_FEATURE] = css
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


def _sites_own(data_dir):
    """[(key, css)] of data_dir/sites/*.css, sorted by name; files whose name
    is not a style name, or that cannot be read, are skipped."""
    folder = os.path.join(data_dir, SITES_OWN_DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    out = []
    for name in names:
        key = _site_key_name(name) if name.endswith(".css") else None
        if key is None or key + ".css" != name:
            continue
        try:
            css = read_text(os.path.join(folder, name), DATA_READ_LIMIT).strip()
        except OSError:
            continue
        if css:
            out.append((name, css))
    return out


def _sites_feature_css(features):
    return "\n".join(css for name, css in features.items() if SITES_KEEP.search(name))


# The generic style's own "background: none" also wipes the background
# images of the elements it lists (a photo behind a <section> hero): the
# generic style only loses its background colours (its background-color
# rule stays), images keep showing.
_GENERIC_NO_BACKGROUND = re.compile(r"^[ \t]*background:[ \t]*none[ \t]*!important;[ \t]*\n", re.M)


def _sites_index(sites, generic=True):
    """The _SitesIndex of `sites` (the generic style left out when not `generic`)."""
    suffix = {}
    dash = {}
    css = {}
    for key, features in sites.styles.items():
        if key == SITES_GENERIC_KEY and not generic:
            continue
        text = _sites_feature_css(features)
        if key == SITES_GENERIC_KEY:
            text = _GENERIC_NO_BACKGROUND.sub("", text)
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


def sites_build_css(sites, excluded=(), disabled=(), generic=True, problems=None, gate=None):
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
    `gate`: the root condition the rules of every block are gated on
    (live_gate; None: not gated by liveControl). Every block is also gated
    on the colour scheme (_scheme_gated), with or without `gate`.
    """
    blocks = _sites_blocks(sites, excluded, disabled, generic, problems)
    if not blocks:
        return ""
    out = [SITES_HEADER]
    out += [_sites_block_text(comment, "https?://" + tail, body, gate)
            for comment, tail, body in blocks]
    return "\n\n".join(out) + "\n"


def _sites_block_text(comment, rx, body, gate=None):
    """One site style block: `comment` line, then `body` in an
    @-moz-document regexp("`rx`") block, gated on the colour scheme and
    `gate` (_scheme_gated; the generic style without the shadow branch
    under a dark theme)."""
    return '%s\n@-moz-document regexp("%s") {\n%s\n}' % (
        comment, rx, _scheme_gated(body, gate, comment != SITES_GENERIC_COMMENT))


def _sites_blocks(sites, excluded=(), disabled=(), generic=True, problems=None):
    """The blocks of sites_build_css (same arguments) as
    [(comment, rx_tail, body)]: `comment` is the block's comment line, the
    block's regexp is "https?://" + `rx_tail` (CSS string text), `body` its
    rules, not gated."""
    return [row[:3] for row in _sites_block_rows(sites, excluded, disabled, generic, problems)]


@functools.lru_cache(maxsize=2048)
def _sites_errors(text):
    """sites_validate(text) as a tuple, memoized: the live section and the
    restart render build the same blocks again."""
    return tuple(sites_validate(text))


def _sites_block_rows(sites, excluded=(), disabled=(), generic=True, problems=None):
    """_sites_blocks with a fourth item per block, `may_match(host)`: False
    when the block's regexp cannot match https://host/ (a test cheaper than
    the regexp, for content_live_section)."""
    index = _sites_index(sites, generic)
    excluded = [d for d in (normalize_domain(x) for x in excluded) if d]
    skip = {name + ".css" for name in (normalize_style_name(x) for x in disabled) if name}
    for key, text in sorted(index.css.items()):
        errors = _sites_errors(text)
        if errors:
            skip.add(key)
            if problems is not None:
                problems.extend("%s: %s" % (key, error) for error in errors)
    neg_excl = exclusion_lookahead(excluded)
    end = "(?:[:/].*)?"
    any_sub = "(?:[^/]*\\\\.)?"
    www = "(?:www\\\\.)?"
    out = []

    def block(comment, tail, text, may_match):
        out.append(("/* %s */" % comment, tail, text, may_match))

    deeper = _deeper_domains(index.suffix)
    for domain, key in sorted(index.suffix.items()):
        if key in skip:
            continue
        neg = ""
        if deeper.get(domain):
            neg = "(?!%s(?:%s)(?:[:/]|$))" % (any_sub, css_rx_alt(deeper[domain]))
        block(key, "%s%s%s%s%s" % (neg_excl, neg, any_sub, css_rx_escape(domain), end),
              index.css[key], lambda host, d=domain: host == d or host.endswith("." + d))
    for base, key in sorted(index.dash.items()):
        if key in skip:
            continue
        block(key, "%s%s%s\\\\.[^./:]+%s" % (neg_excl, www, css_rx_escape(base), end),
              index.css[key], lambda host, b="." + base + ".": b in "." + host)
    for key, hosts in index.mapped:
        if key in skip:
            continue
        block("%s (mapping)" % key,
              "%s%s(?:%s)%s" % (neg_excl, www, css_rx_alt(hosts), end),
              index.css[key], lambda host, hs=frozenset(hosts):
              host in hs or (host.startswith("www.") and host[4:] in hs))
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
        out.append((SITES_GENERIC_COMMENT, "%s%s.*" % (neg_excl, lookahead),
                    index.css[SITES_GENERIC_KEY], lambda host: True))
    return out


def _live_hosts(index, domains):
    """Probe hosts of content_live_section for the excluded `domains`: each
    domain and each host of `index` (a _SitesIndex: dedicated and mapped
    hosts) it covers, bare, with "www." and with another subdomain; and for
    each dash style base B (it matches (www.)B.L, L one label), B.L with L
    the domain's last label when the domain covers it, bare and with "www."."""
    known = list(index.suffix) + [h for _, hosts in index.mapped for h in hosts]
    hosts = set()
    for domain in domains:
        for host in [domain] + [h for h in known if _covered(h, [domain])]:
            hosts.update((host, "www." + host, "x0." + host))
        last = domain.rsplit(".", 1)[-1]
        for base in index.dash:
            host = base + "." + last
            if _covered(host, [domain]):
                hosts.update((host, "www." + host))
    return sorted(hosts)


def _scheme_gated(css, gate=None, shadow=True):
    """The site style `css` gated on `gate` (live_gate, GATE_LIVE_ROOT, None)
    under a light theme; under a dark one on GATE_DARK[gate], so only on
    pages that declare a dark version (as the generic content rule), or
    with liveControl carry the add-on's tone: a light-only page asked for
    dark keeps its light backgrounds behind its dark text instead of showing
    it on the dark tint. One gating per branch (css_gate_rules: rules on
    the root itself match too), never two nested: the scheme and live
    conditions share the envelope. Shadow trees cannot see the root: under
    a dark theme they get the style on every page (the dark branch's
    shadow branch, not under GATE_LIVE_ROOT) when `shadow` is true (a
    dedicated style, as before the scheme gating), none when it is false
    (the generic style, as in v1.0)."""
    light = css_gate_rules(css, gate) if gate else css
    dark = css_gate_rules(css, GATE_DARK[gate], shadow)
    return ("@media not (prefers-color-scheme: dark) {\n%s\n}\n"
            "@media (prefers-color-scheme: dark) {\n%s\n}" % (light, dark))


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
# psl
# ============================================================================

# Mozilla's Public Suffix List (MPL-2.0, data/PSL-LICENSE), embedded as
# data/<PSL_FILE>: no network, no system file. Both sections are read, ICANN
# (co.uk) and PRIVATE (github.io). Rules are kept in the ASCII form
# normalize_domain() gives (an IDN label as "xn--" Punycode), the form
# Firefox shows a host in. data/<PSL_FILE> is the upstream list minus the
# lines the data updater drops (tools/update_styles.py, through the
# denylist); it must keep applying it.
# rules: {"co.uk"}; wildcards: {"ck"} for "*.ck"; exceptions: {"www.ck"} for
# "!www.ck".
Psl = collections.namedtuple("Psl", "rules wildcards exceptions")
# Fewer rules than this, or no "com" rule: the file is taken as corrupt.
PSL_MIN_RULES = 1000
# Characters a rule never holds (normalize_domain would cut a URL at them).
_PSL_BAD_RULE = re.compile(r"[/?#@:\[\]*!\\]")
_IPV4 = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}")
# {absolute path: ((mtime_ns, size, inode), Psl)}
_PSL_CACHE = {}


class PslError(ValueError):
    """The embedded Public Suffix List is missing, unreadable or corrupt."""


def psl_parse(text):
    """The Psl of the list `text` (the public_suffix_list.dat format).

    One rule per line, its first whitespace-separated word; "//" comments
    and blank lines are skipped, and so is a rule normalize_domain()
    rejects. "*.x" is a wildcard rule, "!x" an exception rule.
    """
    rules, wildcards, exceptions = set(), set(), set()
    for line in text.splitlines():
        words = line.split()
        if not words or words[0].startswith("//"):
            continue
        rule, target = words[0], rules
        if rule.startswith("!"):
            rule, target = rule[1:], exceptions
        elif rule.startswith("*."):
            rule, target = rule[2:], wildcards
        if rule.startswith(".") or _PSL_BAD_RULE.search(rule):
            continue
        name = normalize_domain(rule)
        if name is not None:
            target.add(name)
    return Psl(frozenset(rules), frozenset(wildcards), frozenset(exceptions))


def psl_load(data_dir):
    """The Psl of `data_dir`/<PSL_FILE>, parsed once per path (again only
    when the file changes). Raises PslError, with a message naming the
    file, when it is missing, unreadable, not UTF-8 or corrupt: the caller
    turns that into a warning.
    """
    path = os.path.abspath(os.path.join(data_dir, PSL_FILE))
    try:
        st = os.stat(path)
        signature = (st.st_mtime_ns, st.st_size, st.st_ino)
        cached = _PSL_CACHE.get(path)
        if cached is not None and cached[0] == signature:
            return cached[1]
        text = read_text(path, DATA_READ_LIMIT)
    except OSError as exc:
        raise PslError("%s: %s" % (PSL_FILE, exc.strerror or exc))
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise PslError("%s: not UTF-8" % PSL_FILE)
    psl = psl_parse(text)
    count = len(psl.rules) + len(psl.wildcards) + len(psl.exceptions)
    if count < PSL_MIN_RULES or "com" not in psl.rules:
        raise PslError("%s: corrupt (%d rules)" % (PSL_FILE, count))
    _PSL_CACHE[path] = (signature, psl)
    return psl


def _psl_suffix_size(labels, psl):
    """Number of labels in the public suffix of `labels`: the standard PSL
    algorithm (an exception rule prevails, then the longest normal or
    wildcard rule, else the implicit "*" rule)."""
    n = len(labels)
    for i in range(n):
        if ".".join(labels[i:]) in psl.exceptions:
            return n - i - 1
    for i in range(n):
        if ".".join(labels[i:]) in psl.rules or (
                i + 1 < n and ".".join(labels[i + 1:]) in psl.wildcards):
            return n - i
    return 1


def psl_registrable(name, psl):
    """The registrable domain (public suffix plus one label) of the ASCII
    host `name`, or None when `name` is itself a public suffix (standard
    PSL semantics, as tests/test_psl.txt of the PSL repository checks)."""
    labels = name.split(".")
    size = _psl_suffix_size(labels, psl)
    return ".".join(labels[-size - 1:]) if len(labels) > size else None


def registrable_domain(host, psl):
    """The domain the launcher excludes for the page host `host`.

    The host is normalised like normalize_domain() does (lowercase, port
    and trailing dot dropped, IDN to "xn--" Punycode), then reduced to its
    registrable domain: "account.proton.me" -> "proton.me", "a.b.co.uk" ->
    "b.co.uk", "user.github.io" -> "user.github.io". An IPv4 address and
    "localhost" are returned unchanged, and so is a bare public suffix
    ("co.uk", "github.io"): never all the sites under a public suffix.
    None when the host is unusable, the caller's "unsupported": an IPv6
    literal (bracketed or not), a leading dot, an empty label, characters
    outside [a-z0-9.-] after normalisation (a "*" included), or a
    non-string.
    """
    if not isinstance(host, str):
        return None
    host = host.strip()
    bare = re.split(r"[/?#]", host.split("://", 1)[-1], maxsplit=1)[0].rpartition("@")[2]
    # The checks run on the NFKC form normalize_domain() works on, so that
    # a full-width "\uff0a", "\uff0e" or "\uff1a" cannot get past them. "*"
    # is refused here: normalize_domain() drops a leading "*." of user
    # input, which would turn the page host "*.com" into "com".
    folded = unicodedata.normalize("NFKC", bare)
    for dot in _IDEOGRAPHIC_DOTS:
        folded = folded.replace(dot, ".")
    if folded.startswith((".", "[")) or folded.count(":") > 1 or "*" in folded:
        return None
    name = normalize_domain(bare)
    if name is None:
        return None
    if name == "localhost" or _IPV4.fullmatch(name):
        return name
    return psl_registrable(name, psl) or name


# ============================================================================
# session
# ============================================================================

# The site of the browser window niri has focused, for the launcher's
# blist/unblist (`active-site`, read-only). The companion add-on's report
# wins while its host is alive (<runtime>/active-<pid>.json, written by the
# native host); otherwise the browser's own session file is read: Firefox
# rewrites sessionstore-backups/recovery.jsonlz4 every
# browser.sessionstore.interval ms (15 s by default) while it runs. Nothing
# read here is ever logged or written anywhere: only the answer goes to
# stdout.

# niri app-id -> browser family (every APP_IDS entry, see test_session)
APP_FAMILY = {
    "firefox": "firefox",
    "firefox-esr": "firefox",
    "org.mozilla.firefox": "firefox",
    "librewolf": "librewolf",
    "io.gitlab.librewolf-community": "librewolf",
    "zen": "zen",
    "zen-browser": "zen",
    "zen-beta": "zen",
    "app.zen_browser.zen": "zen",
    "floorp": "floorp",
    "one.ablaze.floorp": "floorp",
    "waterfox": "waterfox",
    "net.waterfox.waterfox": "waterfox",
}
# How a private window's title ends ("<page> \u2014 Mozilla Firefox Private
# Browsing"; LibreWolf, Zen, Floorp and Waterfox share the Firefox strings),
# compared case-insensitively. French: "... Navigation priv\u00e9e".
PRIVATE_TITLE_SUFFIXES = (
    "private browsing",
    "navigation priv\u00e9e",
)
# A window title is "<tab title> \u2014 <brand>" (an em dash; a hyphen-minus
# where a build uses one).
TITLE_BRAND_SEPARATORS = (" \u2014 ", " - ")
# Answers of active-site (contract spec active_site)
SITE_ERRORS = ("no_browser", "private", "not_web", "no_session", "ambiguous",
               "unsupported", "outdated")
ACTIVE_FILE = "active-%d.json"   # in the runtime folder, by the native host
HOST_SOCKET = "host-%d.sock"     # idem: the host listens there while alive
ACTIVE_FILE_VERSION = 1
ACTIVE_FILE_LIMIT = 64 * 1024
SOCKET_PROBE_TIMEOUT = 0.3  # seconds

# mozlz4 (Firefox's jsonlz4 files): MOZLZ4_MAGIC, the decoded size as a
# uint32 LE, then one LZ4 block (no frame, no checksum).
MOZLZ4_MAGIC = b"mozLz40\0"
MOZLZ4_MAX = 256 << 20  # decoded size refused above this (corrupt header)
# Newest readable wins: recovery.jsonlz4 while the browser runs (baklz4 is
# the previous copy), sessionstore.jsonlz4 after a clean quit.
SESSION_FILES = (
    os.path.join("sessionstore-backups", "recovery.jsonlz4"),
    os.path.join("sessionstore-backups", "recovery.baklz4"),
    "sessionstore.jsonlz4",
)


class Lz4Error(ValueError):
    pass


def _lz4_length(src, i, value):
    """LZ4's extended length: add bytes from src[i] while they are 255."""
    while True:
        b = src[i]
        i += 1
        value += b
        if b != 255:
            return value, i


def lz4_block_decode(src, size):
    """The `size` bytes that the LZ4 block `src` decodes to.

    Raises Lz4Error on any corruption (truncation, an offset before the
    start, a length that disagrees with `size`): never loops, never returns
    a wrong length.
    """
    out = bytearray()
    n = len(src)
    i = 0
    try:
        while True:
            token = src[i]
            i += 1
            lit = token >> 4
            if lit == 15:
                lit, i = _lz4_length(src, i, lit)
            if i + lit > n:
                raise Lz4Error("literals past the end")
            if len(out) + lit > size:
                raise Lz4Error("longer than the header says")
            out += src[i:i + lit]
            i += lit
            if i >= n:  # the last sequence holds literals only
                break
            off = src[i] | (src[i + 1] << 8)
            i += 2
            if off == 0 or off > len(out):
                raise Lz4Error("bad offset")
            mlen = token & 15
            if mlen == 15:
                mlen, i = _lz4_length(src, i, mlen)
            mlen += 4
            # Checked before the copy: a run of 255 bytes would otherwise
            # build ~255 output bytes per input byte first
            if len(out) + mlen > size:
                raise Lz4Error("longer than the header says")
            start = len(out) - off
            if mlen <= off:
                out += out[start:start + mlen]
            else:  # overlapping copy: repeat the last `off` bytes
                chunk = bytes(out[start:])
                reps, rest = divmod(mlen, off)
                out += chunk * reps + chunk[:rest]
    except IndexError:
        raise Lz4Error("truncated block")
    if len(out) != size:
        raise Lz4Error("shorter than the header says")
    return bytes(out)


def mozlz4_read(path):
    """The decoded bytes of the mozlz4 file `path` (OSError, Lz4Error)."""
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", path)
        head = f.read(12)
        if len(head) < 12 or head[:8] != MOZLZ4_MAGIC:
            raise Lz4Error("not a mozlz4 file")
        size = int.from_bytes(head[8:12], "little")
        if size > MOZLZ4_MAX:
            raise Lz4Error("decoded size too large")
        # An LZ4 block never takes more than size + size/255 + 16 bytes
        data = f.read(size + size // 255 + 17)
    return lz4_block_decode(data, size)


def session_read(profile):
    """The session state (a dict) of the newest readable session file of
    `profile`, or None. Only ever called for a running profile."""
    found = []
    for rel in SESSION_FILES:
        path = os.path.join(profile, rel)
        try:
            found.append((os.stat(path).st_mtime, path))
        except (OSError, ValueError):
            pass
    for _, path in sorted(found, reverse=True):
        try:
            state = json.loads(mozlz4_read(path).decode("utf-8"))
        except (OSError, ValueError, RecursionError):  # Lz4Error, bad JSON, bad UTF-8
            continue
        if isinstance(state, dict):
            return state
    return None


def title_strip_brand(title):
    """The tab title in the niri window title "<tab title> \u2014 <brand>"
    (the whole title when it has no separator)."""
    for sep in TITLE_BRAND_SEPARATORS:
        if sep in title:
            return title.rsplit(sep, 1)[0]
    return title


def title_is_private(title):
    folded = title.strip().lower()
    return any(folded.endswith(s) for s in PRIVATE_TITLE_SUFFIXES)


def title_hash(text):
    """The first 16 hex digits of the SHA-256 of `text` (UTF-8): what the
    add-on reports for a tab title (extension/background.js titleHash)."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def url_host(url):
    """(host, None) for an http(s) URL, the host as normalize_domain() gives
    it; else (None, "not_web") (about:, view-source:, file:, data:,
    moz-extension:...) or (None, "unsupported") (an IPv6 or unusable host)."""
    if not isinstance(url, str):
        return None, "not_web"
    match = re.match(r"(?i)https?://([^/?#\\]*)", url)
    if not match:
        return None, "not_web"
    netloc = match.group(1).rpartition("@")[2]
    if netloc.startswith("[") or netloc.count(":") > 1:
        return None, "unsupported"
    host = normalize_domain(netloc)
    return (host, None) if host else (None, "unsupported")


def _nth(items, one_based):
    """items[one_based - 1] when that is a dict (session indexes are
    1-based), else None."""
    if (not isinstance(items, list) or isinstance(one_based, bool)
            or not isinstance(one_based, int) or not 1 <= one_based <= len(items)):
        return None
    item = items[one_based - 1]
    return item if isinstance(item, dict) else None


def _tab_entry(tab):
    """The history entry a session tab shows: entries[index - 1]."""
    return _nth(tab.get("entries"), tab.get("index"))


def _is_one(value):
    return value == 1 and not isinstance(value, bool)


def _title_hits(state, want):
    """{url_host(url): url} of the tabs of `state` whose current entry has
    the title `want`."""
    hits = {}
    windows = state.get("windows")
    for win in windows if isinstance(windows, list) else ():
        tabs = win.get("tabs") if isinstance(win, dict) else None
        for tab in tabs if isinstance(tabs, list) else ():
            entry = _tab_entry(tab) if isinstance(tab, dict) else None
            if entry and entry.get("title") == want:
                url = entry.get("url")
                hits.setdefault(url_host(url), url)
    return hits


def session_active_tab(state, title):
    """(url, None) of the tab the user looks at in the session `state`, or
    (None, error) with error "ambiguous" or "no_session".

    Only state["windows"] is read: the open windows, private ones left out
    by the browser. A tab or window switch does not schedule a session
    write, so the selected indexes can be stale; the title niri shows is
    current. 1. Every tab whose current entry has the title `title` minus
    its brand: one host among them -> that tab; several -> "ambiguous".
    2. No match (or no title): the selected tab of the selected window, but
    only when a window has zIndex 1 (the most recent one): when it is
    missing, the most recent window was private and selectedWindow points
    at another one.
    """
    windows = state.get("windows")
    if not isinstance(windows, list) or not any(isinstance(w, dict) for w in windows):
        return None, "no_session"
    hits = _title_hits(state, title_strip_brand(title)) if title else {}
    if len(hits) == 1:
        return next(iter(hits.values())), None
    if hits:
        return None, "ambiguous"
    if not any(isinstance(w, dict) and _is_one(w.get("zIndex")) for w in windows):
        return None, "ambiguous"
    win = _nth(windows, state.get("selectedWindow"))
    tab = _nth(win.get("tabs"), win.get("selected")) if win else None
    entry = _tab_entry(tab) if tab else None
    if entry is None:
        return None, "ambiguous"
    return entry.get("url"), None


def session_age(state, now=None):
    """Seconds since the session `state` was written (session.lastUpdate,
    in ms), or None."""
    session = state.get("session")
    last = session.get("lastUpdate") if isinstance(session, dict) else None
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return None
    try:
        last = float(last)
    except OverflowError:  # an int beyond the float range
        return None
    if not math.isfinite(last):
        return None
    now = time.time() if now is None else now
    return round(max(0.0, now - last / 1000.0), 1)


def profile_of_pid(pid, env=None):
    """The Profile (of find_profiles) whose .parentlock the process `pid`
    holds open (PROC_DIR/<pid>/fd), or None. The open lock proves the
    profile is the one this browser runs on, whatever its family."""
    fd_dir = os.path.join(PROC_DIR, str(pid), "fd")
    try:
        names = os.listdir(fd_dir)
    except (OSError, ValueError):
        return None
    held = set()
    for name in names:
        try:
            target = os.readlink(os.path.join(fd_dir, name))
        except (OSError, ValueError):
            continue
        if target.endswith("/" + PARENT_LOCK):
            held.add(os.path.realpath(os.path.dirname(target)))
    if not held:
        return None
    for profile in find_profiles(env):
        if os.path.realpath(profile.path) in held:
            return profile
    return None


def _socket_alive(path):
    """True when the Unix socket `path` accepts a connection (closed at once)."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(SOCKET_PROBE_TIMEOUT)
        sock.connect(path)
        return True
    except (OSError, ValueError):
        return False
    finally:
        sock.close()


def companion_active(pid, title, env):
    """What the companion reported for the browser `pid`: (host, None) with
    host "" for a non-web page, (None, "ambiguous" | "outdated"), or None
    when there is no live report (no file, a dead host, no title to check
    it against).

    The report counts only when the browser process is alive, its host's
    socket accepts a connection and the reported title hash equals the hash
    of the niri title minus its brand: a private tab (never reported) or a
    stale focus gives another hash, hence "ambiguous".
    """
    # A report planted by another user is never read (_runtime_dir_ours).
    folder = runtime_dir(env)
    if folder is None or not title or not _runtime_dir_ours(folder):
        return None
    try:
        doc = json.loads(read_text(os.path.join(folder, ACTIVE_FILE % pid), ACTIVE_FILE_LIMIT))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(doc, dict) or doc.get("browser_pid") != pid or isinstance(
            doc.get("browser_pid"), bool):
        return None
    if not os.path.isdir(os.path.join(PROC_DIR, str(pid))):
        return None
    if not _socket_alive(os.path.join(folder, HOST_SOCKET % pid)):
        return None
    if doc.get("outdated") is True or doc.get("version") != ACTIVE_FILE_VERSION:
        return None, "outdated"
    host = doc.get("host")
    if not isinstance(host, str):
        return None, "ambiguous"
    # The stripped title, or the whole one for a build whose window title
    # has no brand (a page title holding " - " is then cut wrongly)
    if doc.get("title_hash") in (title_hash(title_strip_brand(title)), title_hash(title)):
        return host, None
    if not any(sep in title for sep in TITLE_BRAND_SEPARATORS):
        # The brand alone ("Mozilla Firefox"): a page with no title, such
        # as about:newtab, whose tab title the add-on hashed. Not a web
        # page when the add-on says so, else the session file decides.
        return ("", None) if host == "" else None
    return None, "ambiguous"


def _session_of(pid, family, title, env):
    """(state, None) of the session file of the browser `pid`, or (None,
    error). The profile is the one `pid` holds the lock of; failing that,
    the running profiles of `family`, and among several the only one with
    a tab titled like the window. A profile no browser runs on is never
    read."""
    profile = profile_of_pid(pid, env)
    if profile is not None:
        state = session_read(profile.path)
        return (state, None) if state is not None else (None, "no_session")
    states = []
    for p in find_profiles(env):
        if p.family == family and lock_state(p.path) == LOCK_RUNNING:
            state = session_read(p.path)
            if state is not None:
                states.append(state)
    if len(states) > 1 and title:
        want = title_strip_brand(title)
        states = [s for s in states if _title_hits(s, want)] or states
    if not states:
        return None, "no_session"
    return (states[0], None) if len(states) == 1 else (None, "ambiguous")


def active_site(pid, app_id, title, env, psl_of):
    """The active-site answer (contract spec active_site) for the niri
    window of process `pid`, app-id `app_id` and title `title` (or None).
    `psl_of()` gives the Psl, loaded only once a host is known."""
    family = APP_FAMILY.get(app_id)
    if family is None or pid <= 0:
        return {"error": "no_browser"}
    if title and title_is_private(title):
        return {"error": "private"}
    report = companion_active(pid, title, env)
    if report is not None:
        host, error = report
        if error:
            return {"error": error}
        source, age = "companion", None
        host, error = url_host("http://" + host) if host else (None, "not_web")
    else:
        state, error = _session_of(pid, family, title, env)
        if error:
            return {"error": error}
        url, error = session_active_tab(state, title)
        if error:
            return {"error": error}
        source, age = "session", session_age(state)
        host, error = url_host(url)
    if error:
        return {"error": error}
    psl = psl_of()
    domain = registrable_domain(host, psl)
    # A host that is itself a public suffix (github.io, a PRIVATE-section
    # entry): excluding it would exclude every site under it
    if domain is None or (domain != "localhost" and not _IPV4.fullmatch(domain)
                          and psl_registrable(domain, psl) is None):
        return {"error": "unsupported"}
    return {"host": host, "domain": domain, "source": source, "age": age}


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
    one; strip_import() then leaves it (the backup in backup/<pid>/ restores the bytes).
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
# companion
# ============================================================================

# Pure functions: the bytes of the companion add-on, the text of the native
# messaging manifest and of the host wrapper. Writing them is the sync's job.

# Fixed zip metadata, so that the same sources always give the same bytes and
# a sync that changes nothing writes nothing (the xpi is compared byte for
# byte). 1980-01-01 is the earliest date a zip entry can hold.
_XPI_DATE = (1980, 1, 1, 0, 0, 0)
_XPI_MODE = 0o100644  # regular file, rw-r--r--
_XPI_SYSTEM = 3       # "made by" Unix, whatever the platform
_XPI_MAX_BYTES = 4 * 1024 * 1024


def _xpi_sources(ext_dir):
    """Sorted (zip name, path) of the regular files under `ext_dir`.
    Hidden files and folders, symlinks and anything else are left out."""
    def fail(exc):
        raise exc
    out = []
    for top, dirs, files in os.walk(ext_dir, onerror=fail, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")
                         and not os.path.islink(os.path.join(top, d)))
        for name in files:
            path = os.path.join(top, name)
            if name.startswith(".") or not stat.S_ISREG(os.lstat(path).st_mode):
                continue
            rel = os.path.relpath(path, ext_dir).split(os.sep)
            out.append(("/".join(rel), path))
    out.sort()
    return out


def companion_xpi(ext_dir):
    """The companion add-on as xpi bytes, built from the files of `ext_dir`
    (<plugin>/extension). Deterministic: stored (not deflated) entries in
    sorted name order, with a fixed date, mode and creator system, so two
    builds of the same sources are identical. manifest.json must sit at the
    root of `ext_dir`. Raises OSError when the folder is unreadable and
    ValueError when manifest.json is missing or the add-on is too large."""
    import zipfile  # here: ~9 ms that only a sync building the xpi pays
    sources = _xpi_sources(ext_dir)
    # The messages name the folder only (sync warnings never hold a path).
    label = os.path.basename(os.path.normpath(ext_dir)) + "/"
    if "manifest.json" not in (name for name, _ in sources):
        raise ValueError("%s: no manifest.json" % label)
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, path in sources:
            with open(path, "rb") as f:
                data = f.read(_XPI_MAX_BYTES + 1)
            total += len(data)
            if total > _XPI_MAX_BYTES:
                raise ValueError("%s: larger than %d bytes" % (label, _XPI_MAX_BYTES))
            info = zipfile.ZipInfo(name, date_time=_XPI_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = _XPI_SYSTEM
            info.external_attr = _XPI_MODE << 16
            zf.writestr(info, data)
    return buf.getvalue()


# Per-profile companion states (contract companion_state). "outdated" is
# told by status only (the running host speaks another protocol).
COMPANION_OFF = "off"
COMPANION_UNSUPPORTED = "unsupported_variant"
COMPANION_NO_PLUGIN = "no_plugin_dir"
COMPANION_ENFORCED = "signing_enforced"
COMPANION_REFUSED = "signing_required"
COMPANION_REMOVED = "removed_by_user"
COMPANION_PENDING = "pending_restart"
COMPANION_INSTALLED = "installed"
COMPANION_OUTDATED = "outdated"
COMPANION_DEPOSITED = (COMPANION_PENDING, COMPANION_INSTALLED)
# Variants whose browser runs in a sandbox the host cannot run from (D6).
COMPANION_SANDBOXED = ("flatpak", "snap")
# Firefox channels that require signed add-ons (MOZ_REQUIRE_SIGNING): the
# xpi would be deleted at startup, so nothing is deposited.
SIGNED_CHANNELS = ("release", "esr", "beta")
# Firefox channels built without MOZ_REQUIRE_SIGNING (Nightly, Developer
# Edition, a local build): with our pref they never delete the add-on.
UNSIGNED_CHANNELS = ("nightly", "aurora", "default")
# Families built without MOZ_REQUIRE_SIGNING (checked on LibreWolf 160).
# On these builds and channels only the user removes the add-on.
UNSIGNED_FAMILIES = ("librewolf",)
# Where distributions and Mozilla's tarball install Firefox. A profile that
# never ran has no compatibility.ini to name its build: its channel is that of
# these builds ($BG_FIREFOX_BUILDS, colon-separated, replaces the list).
FIREFOX_BUILDS = ("/usr/lib64/firefox", "/usr/lib/firefox", "/usr/lib64/firefox-esr",
                  "/usr/lib/firefox-esr", "/opt/firefox")
ENV_FIREFOX_BUILDS = "BG_FIREFOX_BUILDS"
EXTENSIONS_JSON = "extensions.json"
CHANNEL_PREFS_REL = os.path.join("defaults", "pref", "channel-prefs.js")
_EXTENSIONS_JSON_LIMIT = 64 * 1024 * 1024
_COMPAT_LINE = re.compile(r"^(LastVersion|LastPlatformDir)=([^\r\n]{1,4096}?)\r?$", re.M)
_CHANNEL_PREF = re.compile(
    r'^\s*pref\(\s*"app\.update\.channel"\s*,\s*"([A-Za-z0-9_.-]{1,64})"\s*\)', re.M)
_SCOPE_LITERAL = re.compile(r"-?\d{1,10}")


def companion_prefs(originals):
    """[(pref, JS literal)] of the companion prefs for the original prefs.js
    values `originals` ({pref: JS literal or None}): unsigned add-ons
    allowed, and of the two scope prefs only the profile bit changes (no
    sideload prompt, an existing profile scans its extensions/ folder at
    the next start); a missing or odd value counts as the default."""
    def scope(pref, default):
        value = originals.get(pref)
        if value is not None and _SCOPE_LITERAL.fullmatch(value):
            return int(value)
        return default
    return [
        (PREF_SIGNATURES, "false"),
        (PREF_AUTODISABLE, str(scope(PREF_AUTODISABLE, AUTODISABLE_DEFAULT) & ~SCOPE_PROFILE)),
        (PREF_STARTUP_SCAN, str(scope(PREF_STARTUP_SCAN, STARTUP_SCAN_DEFAULT) | SCOPE_PROFILE)),
    ]


def companion_guard(originals, prefs):
    """[(pref, JS literal)] of the companion prefs `prefs` at their value of
    `originals` (record["prefs_original"]), the browser default for one
    absent or odd: what the block holds for them while their restore in
    prefs.js waits for the browser to close."""
    defaults = {PREF_SIGNATURES: "true", PREF_AUTODISABLE: str(AUTODISABLE_DEFAULT),
                PREF_STARTUP_SCAN: str(STARTUP_SCAN_DEFAULT)}
    out = []
    for pref in COMPANION_PREFS:
        if pref in prefs:
            value = originals.get(pref, {}).get("value")
            valid = value in ("true", "false") if pref == PREF_SIGNATURES \
                else value is not None and _SCOPE_LITERAL.fullmatch(value)
            out.append((pref, value if valid else defaults[pref]))
    return out


def companion_xpi_path(profile_path):
    return os.path.join(profile_path, EXTENSIONS_DIR, COMPANION_XPI)


def compat_values(profile_path):
    """{"LastVersion", "LastPlatformDir"} found in the profile's
    compatibility.ini (missing keys left out; {} without the file)."""
    try:
        text = read_text(os.path.join(profile_path, "compatibility.ini"), limit=65536)
    except (OSError, ValueError):
        return {}
    out = {}
    for key, value in _COMPAT_LINE.findall(text):
        out.setdefault(key, value)
    return out


def browser_channel(compat):
    """The update channel of the browser build that last ran the profile
    (`compat`: compat_values()), None when it cannot be read."""
    folder = compat.get("LastPlatformDir")
    if not folder or not os.path.isabs(folder):
        return None
    return _channel_of(folder)


def _channel_of(folder):
    try:
        match = _CHANNEL_PREF.search(read_text(os.path.join(folder, CHANNEL_PREFS_REL), limit=65536))
    except (OSError, ValueError):
        return None
    return match.group(1) if match else None


def installed_firefox_signed(env=None):
    """True when a Firefox build installed in FIREFOX_BUILDS is on a channel
    that requires signed add-ons."""
    env = os.environ if env is None else env
    builds = env.get(ENV_FIREFOX_BUILDS)
    folders = FIREFOX_BUILDS if builds is None else [f for f in builds.split(":") if os.path.isabs(f)]
    return any(_channel_of(f) in SIGNED_CHANNELS for f in folders)


def companion_registered(profile_path):
    """True when the profile's extensions.json names the companion add-on."""
    try:
        text = read_text(os.path.join(profile_path, EXTENSIONS_JSON), limit=_EXTENSIONS_JSON_LIMIT)
    except (OSError, ValueError):
        return False
    return ('"%s"' % COMPANION_ID) in text


def _mtime(path):
    try:
        return os.stat(path).st_mtime
    except OSError:
        return None


def companion_refused(profile_path, comp):
    """True when the browser deleted the add-on we deposited: it started
    since (compatibility.ini or extensions.json newer than the deposit),
    the xpi is gone and extensions.json does not name it."""
    if comp is None or comp["dropped"] is None:
        return False
    if os.path.lexists(companion_xpi_path(profile_path)):
        return False
    started = [m for m in (_mtime(os.path.join(profile_path, "compatibility.ini")),
                           _mtime(os.path.join(profile_path, EXTENSIONS_JSON)))
               if m is not None and m > comp["dropped"]]
    return bool(started) and not companion_registered(profile_path)


def companion_can_refuse(family, compat):
    """False when the build that last ran the profile (`compat`:
    compat_values()) never deletes an unsigned add-on: an add-on gone from
    it was removed by the user. True when unknown."""
    if family in UNSIGNED_FAMILIES:
        return False
    return not (family == "firefox" and browser_channel(compat) in UNSIGNED_CHANNELS)


def companion_state(profile_path, family, variant, comp, enabled, available, compat=None, env=None):
    """The companion state of one profile (COMPANION_*, never "outdated").
    `comp` is the profile's record["companion"], `enabled` liveControl,
    `available` whether the add-on can be deposited (sync: --plugin-dir and
    a built xpi; status: we deposited it)."""
    if not enabled:
        return COMPANION_OFF
    if variant in COMPANION_SANDBOXED:
        return COMPANION_UNSUPPORTED
    compat = compat_values(profile_path) if compat is None else compat
    if family == "firefox" and browser_channel(compat) in SIGNED_CHANNELS:
        return COMPANION_ENFORCED
    if family == "firefox" and not compat and installed_firefox_signed(env):
        # Never ran: the Firefox installed here is the one that will.
        return COMPANION_ENFORCED
    if comp is not None and not os.path.lexists(companion_xpi_path(profile_path)) \
            and (comp["seen"] or (not companion_can_refuse(family, compat)
                                  and companion_refused(profile_path, comp))):
        # Seen registered then gone, or gone from a build that never deletes
        # it: removed in about:addons. Left out until liveControl is turned
        # off and on (or an uninstall).
        return COMPANION_REMOVED
    if comp is not None and comp["refused"] is not None \
            and comp["refused"] == (compat.get("LastVersion") or ""):
        return COMPANION_REFUSED
    if companion_refused(profile_path, comp):
        return COMPANION_REFUSED
    if not available:
        return COMPANION_NO_PLUGIN
    if os.path.isfile(companion_xpi_path(profile_path)) and companion_registered(profile_path):
        return COMPANION_INSTALLED
    return COMPANION_PENDING


def native_manifest_text(wrapper_path):
    """The native messaging manifest (<NATIVE_MANIFEST_NAME>) that lets the
    companion add-on, and only it, start the host at `wrapper_path`, an
    absolute path (ValueError otherwise)."""
    if not isinstance(wrapper_path, str) or not os.path.isabs(wrapper_path):
        raise ValueError("the native host path must be absolute: %r" % (wrapper_path,))
    doc = collections.OrderedDict([
        ("name", NATIVE_HOST_NAME),
        ("description", "Browser Glass helper"),
        ("path", wrapper_path),
        ("type", "stdio"),
        ("allowed_extensions", [COMPANION_ID]),
    ])
    return json.dumps(doc, indent=2) + "\n"


def host_wrapper_text(plugin_dir):
    """The /bin/sh wrapper the browser runs as the native host: it runs this
    file from the absolute `plugin_dir` (ValueError otherwise) with the
    browser's own arguments (manifest path, add-on id) after
    `native-host --data <plugin_dir>/data`. Paths are shell-quoted."""
    if not isinstance(plugin_dir, str) or not os.path.isabs(plugin_dir):
        raise ValueError("the plugin folder must be absolute: %r" % (plugin_dir,))
    plugin_dir = os.path.normpath(plugin_dir)
    script = os.path.join(plugin_dir, PROG + ".py")
    data = os.path.join(plugin_dir, "data")
    return ("#!/bin/sh\n"
            "# browserGlass: native messaging host of the companion add-on"
            " (generated, do not edit).\n"
            "exec python3 -I -B %s native-host --data %s \"$@\"\n"
            % (shlex.quote(script), shlex.quote(data)))


# ============================================================================
# native
# ============================================================================

# The native messaging host (`native-host`): the browser starts it for the
# companion add-on and it lives as long as the browser, blocked in select()
# on stdin and its socket (no timer). Frames on stdin and stdout: a 4-byte
# length in native byte order, then UTF-8 JSON. stdout carries frames only;
# diagnostics go to stderr (the browser console) and never name a site or a
# title.
#
# $XDG_RUNTIME_DIR/<RUNTIME_DIR_NAME>/ (mode 700) holds, per browser process
# (its pid, the host's parent):
#   host-<pid>.sock    the host listens there: a sync (live_push) connects,
#                      sends one line {"excluded": [domain...]} and reads
#                      back {"acked": seq} once the add-on has applied it
#   active-<pid>.json  {"version": 1, "browser_pid", "host", "domain",
#                      "title_hash", "ts"}: the site of the browser's focused
#                      tab (read by active-site); {"version": 1,
#                      "browser_pid", "outdated": true, "ts"} when the add-on
#                      speaks another protocol (it was updated and only a
#                      restart loads the new one)
#   ack-<pid>.json     {"seq", "ts"}: the last list the add-on applied
# A host removes its own files when the browser closes (EOF on stdin), and
# exits quietly when the folder disappears (uninstall).

NM_PROTO = 1
NM_MAX_MESSAGE = 1024 * 1024   # larger incoming frame: the host exits
LIVE_LINE_MAX = 256 * 1024     # a socket request, {"excluded": [...]} + "\n"
LIVE_CLIENT_TIMEOUT = 1.0      # seconds to read a socket request
LIVE_ACK_TIMEOUT = 1.0         # seconds to wait for the add-on's "applied"
LIVE_CONNECT_TIMEOUT = 0.3     # seconds for live_push to reach one host
_RUNTIME_NAMES = {"host": "host-%d.sock", "active": "active-%d.json", "ack": "ack-%d.json"}
_HOST_SOCKET = re.compile(r"host-([0-9]{1,10})\.sock")
_TITLE_HASH = re.compile(r"[0-9a-f]{16}")


class NmError(ValueError):
    """A native messaging frame the host cannot go on after (too large, or
    cut short)."""


class _RuntimeGone(Exception):
    """The runtime folder, or the host's socket in it, is gone."""


def runtime_dir(env=None):
    """$XDG_RUNTIME_DIR/<RUNTIME_DIR_NAME>, else /run/user/<uid>/... when
    that folder exists; None when there is no runtime folder (no live
    control then)."""
    env = os.environ if env is None else env
    base = env.get("XDG_RUNTIME_DIR") or ""
    if not os.path.isabs(base):
        base = "/run/user/%d" % os.getuid()
        if not os.path.isdir(base):
            return None
    return os.path.join(os.path.normpath(base), RUNTIME_DIR_NAME)


def runtime_file(rdir, kind, pid):
    """The runtime file `kind` ("host" socket, "active" or "ack") of the
    browser process `pid` in the runtime folder `rdir`."""
    return os.path.join(rdir, _RUNTIME_NAMES[kind] % pid)


def _runtime_dir_ours(rdir):
    """True when `rdir` is a real folder (no symlink) of this user."""
    try:
        st = os.lstat(rdir)
    except OSError:
        return False
    return stat.S_ISDIR(st.st_mode) and st.st_uid == os.getuid()


def _read_upto(stream, size):
    """Up to `size` bytes of the binary `stream`, fewer only at its end."""
    chunks = []
    while size > 0:
        chunk = stream.read(size)
        if not chunk:
            break
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def nm_read(stream):
    """The next native messaging message of the binary `stream`: None at
    the end of the stream, {} for a frame that is not UTF-8 JSON (ignored by
    the host), else the decoded value. Raises NmError for a frame larger
    than NM_MAX_MESSAGE or cut short."""
    head = _read_upto(stream, 4)
    if not head:
        return None
    if len(head) < 4:
        raise NmError("truncated frame header")
    size = struct.unpack("=I", head)[0]
    if size > NM_MAX_MESSAGE:
        raise NmError("message of %d bytes refused" % size)
    body = _read_upto(stream, size)
    if len(body) < size:
        raise NmError("truncated frame")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}


def nm_write(stream, doc):
    """Write `doc` to the binary `stream` as one native messaging frame."""
    data = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


def live_domains(value):
    """The plain host names of the list `value` the add-on may receive:
    normalize_domain() of each entry (no scheme, port, path or IPv6), the
    unusable ones and duplicates dropped, in order. [] for a non-list."""
    if not isinstance(value, list):
        return []
    return _unique(normalize_domain(item) for item in value)


def _host_log(message):
    """A diagnostic of the native host, on stderr (the browser console)."""
    try:
        sys.stderr.write("%s native-host: %s\n" % (PROG, message))
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def _socket_line(conn, limit, timeout):
    """The first line (without "\\n") the socket `conn` sends within
    `timeout` seconds, or what it sent before closing; None when it sends
    more than `limit` bytes without one, too slowly, or fails."""
    deadline = time.monotonic() + timeout
    buf = b""
    while b"\n" not in buf:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        try:
            conn.settimeout(left)
            chunk = conn.recv(65536)
        except OSError:  # socket.timeout included
            return None
        if not chunk:
            break
        buf += chunk
        if len(buf.split(b"\n", 1)[0]) > limit:
            return None
    return buf.split(b"\n", 1)[0]


class _NativeHost:
    """One run of the native messaging host for the browser `bpid`."""

    def __init__(self, env, data_dir, stdin, stdout, bpid):
        self.env = env
        self.data_dir = data_dir
        self.stdin = stdin
        self.stdout = stdout
        self.bpid = bpid
        self.rdir = runtime_dir(env)
        self.listener = None
        self.sock_path = None
        self.sock_ino = None
        self.written = set()
        self.seq = 0
        self.applied = 0
        self.current = []
        self.outdated = False
        self.done = False
        self.psl = None

    # -- runtime folder ---------------------------------------------------

    def listen(self):
        """Bind host-<bpid>.sock in the runtime folder (made, mode 700,
        when missing; a stale socket of the same name is replaced). The
        socket is bound under a temporary name, made mode 600 and listening
        before it is renamed: live_push never finds it refusing (it would
        take it for a dead host's). One retry when the folder vanished in
        between (the last host of another browser removing it)."""
        rdir = self.rdir
        path = runtime_file(rdir, "host", self.bpid)
        for attempt in (0, 1):
            try:
                os.mkdir(rdir, 0o700)
            except FileExistsError:
                pass
            if not _runtime_dir_ours(rdir):
                raise OSError(errno.EPERM, "not a folder of this user", rdir)
            if stat.S_IMODE(os.lstat(rdir).st_mode) != 0o700:
                os.chmod(rdir, 0o700)
            tmp = os.path.join(rdir, "%s%d.%s%s" % (TMP_PREFIX, self.bpid, os.urandom(4).hex(),
                                                     TMP_SUFFIX))
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
            try:
                sock.bind(tmp)
                try:
                    os.chmod(tmp, 0o600)
                    sock.listen(8)
                    ino = os.stat(tmp).st_ino
                    os.rename(tmp, path)
                except BaseException:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            except FileNotFoundError:
                sock.close()
                if attempt:
                    raise
                continue
            except BaseException:
                sock.close()
                raise
            break
        self.sock_ino = ino
        self.listener = sock
        self.sock_path = path

    def check_runtime(self):
        """Raise _RuntimeGone when our socket left the runtime folder."""
        if self.listener is None:
            return
        try:
            same = os.stat(self.sock_path).st_ino == self.sock_ino
        except OSError:
            same = False
        if not same:
            raise _RuntimeGone()

    def write_runtime(self, kind, doc):
        """Write the runtime file `kind` of this browser (atomic, mode 600);
        nothing without a socket. The folder is never made again here."""
        if self.listener is None:
            return
        self.check_runtime()  # replaced: these names are the new host's
        path = runtime_file(self.rdir, kind, self.bpid)
        try:
            write_if_changed(path, json.dumps(doc) + "\n", mode=0o600, make_dirs=False)
        except FileNotFoundError:
            raise _RuntimeGone()
        except OSError as exc:
            _host_log("%s file not written: %s" % (kind, _oserror_text(exc)))
            return
        self.written.add(path)

    def cleanup(self):
        """At the end: our socket and files go, then the folder if empty."""
        if self.listener is None:
            return
        self.listener.close()
        try:
            self.check_runtime()
            paths = [self.sock_path] + sorted(self.written)
        except _RuntimeGone:
            # Replaced by another host of the same browser: the socket and
            # the active-/ack- names are its files now. With no socket
            # left (uninstall emptied the folder), a file this host wrote
            # after that goes, so the folder does too.
            paths = [] if os.path.lexists(self.sock_path) else sorted(self.written)
        for path in paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(self.rdir)
        except OSError:
            pass

    # -- messages ---------------------------------------------------------

    def send(self, doc):
        nm_write(self.stdout, doc)

    def send_list(self, domains):
        """Send the exclusion list `domains`; returns its seq."""
        self.current = domains
        self.seq += 1
        self.send({"type": "excluded", "seq": self.seq, "domains": domains})
        return self.seq

    def startup_list(self):
        """The exclusion list of the last full sync (state.json, read
        without the lock: sync saves it before it pushes)."""
        try:
            state, _ = state_load(state_dir(self.env), [])
        except Exception:  # unreadable or newer: no list yet
            return []
        last = state.get("last_sync")
        return live_domains(last["settings"].get("excluded")) if last else []

    def domain_of(self, host):
        """registrable_domain() of `host`; the host itself when the public
        suffix list is unavailable (never more than that host)."""
        if self.psl is None:
            try:
                self.psl = psl_load(self.data_dir) if self.data_dir else False
            except PslError:
                self.psl = False
        if self.psl is False:
            return normalize_domain(host)
        return registrable_domain(host, self.psl)

    def on_message(self, msg):
        if not isinstance(msg, dict):
            return
        kind = msg.get("type")
        if kind == "hello":
            proto = msg.get("proto")
            if self.outdated or isinstance(proto, bool) or proto != NM_PROTO:
                self.outdated = True
                self.write_runtime("active", {"version": 1, "browser_pid": self.bpid,
                                              "outdated": True, "ts": time.time()})
            else:
                self.send_list(self.current)
        elif self.outdated:
            return  # another protocol: nothing else is understood
        elif kind == "active":
            host = msg.get("host")
            host = host.lower() if isinstance(host, str) and len(host) <= 253 else ""
            title_hash = msg.get("title_hash")
            if not isinstance(title_hash, str) or not _TITLE_HASH.fullmatch(title_hash):
                title_hash = ""
            self.write_runtime("active", {
                "version": 1, "browser_pid": self.bpid, "host": host,
                "domain": self.domain_of(host) if host else "",
                "title_hash": title_hash, "ts": time.time()})
        elif kind == "applied":
            seq = msg.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool) and self.applied < seq <= self.seq:
                self.applied = seq

    def read_stdin(self):
        """Handle the next message on stdin; at its end, done."""
        msg = nm_read(self.stdin)
        if msg is None:
            self.done = True
            return
        self.on_message(msg)
        self.check_runtime()

    def wait_applied(self, seq):
        """True once the add-on applied the list `seq`, within
        LIVE_ACK_TIMEOUT (other messages are handled meanwhile)."""
        import select
        deadline = time.monotonic() + LIVE_ACK_TIMEOUT
        while self.applied < seq and not self.done:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.stdin], [], [], left)[0]:
                return False
            self.read_stdin()
        return self.applied >= seq

    def serve_client(self):
        """One sync's push: relay its list, then answer {"acked": seq} once
        the add-on applied it (nothing when it does not in time)."""
        try:
            conn, _ = self.listener.accept()
        except OSError:
            return
        with conn:
            line = _socket_line(conn, LIVE_LINE_MAX, LIVE_CLIENT_TIMEOUT)
            if line is None or self.outdated:
                return
            try:
                doc = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError, RecursionError):
                return
            if not isinstance(doc, dict) or not isinstance(doc.get("excluded"), list):
                return
            seq = self.send_list(live_domains(doc["excluded"]))
            if not self.wait_applied(seq):
                return
            self.write_runtime("ack", {"seq": seq, "ts": time.time()})
            try:
                conn.settimeout(LIVE_CLIENT_TIMEOUT)
                conn.sendall((json.dumps({"acked": seq}) + "\n").encode("ascii"))
            except OSError:
                pass
        self.check_runtime()

    def run(self):
        """Serve until the browser closes stdin."""
        import select
        if self.rdir is not None:
            try:
                self.listen()
            except OSError as exc:
                _host_log("no live control: %s" % _oserror_text(exc))
        # Read after the socket is bound: a sync that pushes before the bind
        # saved its list to state.json first, one that pushes after it
        # reaches the socket.
        self.current = self.startup_list()
        self.send({"type": "hello", "proto": NM_PROTO})
        while not self.done:
            fds = [self.stdin] + ([self.listener] if self.listener is not None else [])
            ready = select.select(fds, [], [])[0]
            if self.stdin in ready:
                self.read_stdin()
            elif ready:
                self.serve_client()


def native_host(env, data_dir, stdin, stdout, bpid):
    """Run the native host for the browser process `bpid` on the binary
    streams `stdin` / `stdout`. Returns the exit status: 0 at the end of
    stdin or when the runtime folder disappears, 1 after a bad frame or an
    error (reported on stderr only)."""
    import signal

    def stop(signum, frame):
        raise SystemExit(EXIT_OK)

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, stop)
    host = _NativeHost(env, data_dir, stdin, stdout, bpid)
    code = EXIT_OK
    try:
        host.run()
    except _RuntimeGone:
        pass  # uninstalled or replaced: cleanup() leaves the new host's files
    except BrokenPipeError:
        pass  # the browser went away
    except NmError as exc:
        _host_log(str(exc))
        code = EXIT_ERROR
    except Exception as exc:
        _host_log("%s: %s" % (exc.__class__.__name__, getattr(exc, "strerror", None) or exc))
        code = EXIT_ERROR
    finally:  # SIGTERM (SystemExit) included
        host.cleanup()
    return code


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
#                       read from prefs.js on first contact
#       owned_prefs     prefs our user.js block sets
#       restore_prefs   prefs that left the block (siteTheme "none") and
#                       still wait for their original value in prefs.js
#                       (written only while the browser is closed)
#       applied_hash    hash of what the last sync wrote (None if a write failed)
#       instance        "pid:starttime" of the browser running on the profile
#                       ("?" when unknown), None when it is closed
#       glass_loaded_since_start   that browser started with glass CSS
#                       (it holds the niri rule until it restarts)
#       restart_hash    applied_hash without the exclusion list (what only a
#                       restart applies), excl_hash the exclusion list's hash
#                       (both None when applied_hash is; see profile_output)
#       live            None, or {instance, restart_hash, excl_hash, mtime}:
#                       what the running browser `instance` has, the
#                       exclusion list pushed live and acknowledged, valid
#                       while no RESTART_FILES is newer than mtime (see
#                       live_push)
#       companion       None, or {dropped, build, refused, ext_dir, seen}: dropped
#                       the mtime of the add-on we deposited (None when none
#                       is), build the browser's LastVersion then, refused
#                       the LastVersion of a browser that deleted it
#                       (signing_required: no new deposit until it changes,
#                       "" when unknown), ext_dir we created extensions/,
#                       seen a sync found it registered, or found it removed
#                       by the user (gone since: removed_by_user, no new
#                       deposit until liveControl is turned off and on)
#     backups         {profile_id: backup record}, also kept as
#                     backup/<profile_id>/meta.json
#       path, chrome_dir (the chrome folder existed before us), ext_dir
#       (we created extensions/, as in the companion record)
#       files {name: {"existed", "mode", "sha256"}}
#       prefs_original  the profile's prefs_original at first contact:
#                       meta.json is only rewritten to add the original of
#                       a pref it lacks (a v1.0 backup: the companion
#                       prefs) or to record ext_dir, so the originals
#                       survive a lost or corrupt state.json; a backup
#                       whose originals an uninstall dropped (null) is
#                       refilled from the record at the next sync
#     niri            {"include_added", "config_eol"}
#     created_dirs    folders made for the state, removed by uninstall once
#                     empty; also kept in state-dirs.json
#     native          {"manifests", "created_dirs"}: the native messaging
#                     manifests we wrote and the folders made for them
#                     (explicit paths, uninstall never globs); the folders
#                     are also kept in native-dirs.json
#     synced          a sync ran since the last uninstall (first_run)
#   native-dirs.json
#                the folders made for the native messaging manifest (a JSON
#                list), next to the host wrapper, so they survive a lost or
#                corrupt state.json; removed with the wrapper
#   state-dirs.json
#                a copy of state.created_dirs (a JSON list), read when
#                state.json is missing or corrupt; removed with the state
#                folder (a pending file carries its own copy)
#   backup/<profile_id>/{userChrome.css,userContent.css,user.js}
#                original files without any v0/v1 addition, taken once
#                before the first write, never overwritten
#   pending/<profile_id>.json
#                written by uninstall for a profile whose prefs.js cleanup
#                waits for the browser to close: {version, path, plan
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
NATIVE_DIRS = "native-dirs.json"
STATE_DIRS = "state-dirs.json"
PENDING_DIR = "pending"
_PID = re.compile(r"[0-9a-f]{12}")
# Environment knobs (tests use them to stay fast).
ENV_LOCK_TIMEOUT = "BG_LOCK_TIMEOUT"   # seconds to wait for state.lock
ENV_POLL_INTERVAL = "BG_POLL_INTERVAL"  # seconds between clean-prefs probes
ENV_POLL_MAX = "BG_POLL_MAX"            # seconds before clean-prefs gives up
ENV_TERM_GRACE = "BG_TERM_GRACE"        # seconds the cleaner keeps polling after SIGTERM
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
# At logout or shutdown the cleaner gets SIGTERM with the browser: it then
# polls this often, for this long, to run the cleanup once the lock frees.
# Started by the plugin, it stays in the shell's service, which a restart
# stops with the browser still open and kills after its stop timeout (10 s
# for dms.service): the grace stays well below it, so a shell restart is
# never held up long (the pending file stays for the next sync).
TERM_POLL_INTERVAL = 0.2
DEFAULT_TERM_GRACE = 4.0
LOCK_RETRY_STEP = 0.05
# A stale temporary file is swept only when older than this (seconds): a
# clean-prefs running outside the state lock may own a fresh one.
STALE_TMP_AGE = 600
# Temporary files write_if_changed() leaves behind after a hard stop.
# Only our own prefix, a file name we write and the exact mkstemp alphabet.
_STALE_TMP = re.compile(
    re.escape(TMP_PREFIX)
    + r"(?:userChrome\.css|userContent\.css|user\.js|prefs\.js|dms-glass-chrome\.css|"
    r"dms-glass-content\.css|config\.kdl|dms-browser-glass\.kdl|state\.json|state-dirs\.json|"
    r"native-dirs\.json|meta\.json|"
    r"[0-9a-f]{12}\.json|browserglass@companion\.xpi|browserglass\.json|native-host)"
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
            "native": {"manifests": [], "created_dirs": []},
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


def _norm_str(value):
    return value if isinstance(value, str) else None


def _norm_live(value):
    """A profile record's "live" field read back; None when unusable."""
    if not isinstance(value, dict):
        return None
    out = {key: value.get(key) for key in ("instance", "restart_hash", "excl_hash")}
    if not all(isinstance(v, str) for v in out.values()):
        return None
    mtime = value.get("mtime")
    if not isinstance(mtime, (int, float)) or isinstance(mtime, bool):
        return None
    try:
        mtime = float(mtime)  # an int too large for a float raises
    except OverflowError:
        return None
    if not math.isfinite(mtime):
        return None
    out["mtime"] = mtime
    return out


def _norm_record(value):
    if not isinstance(value, dict) or not _abs_path(value.get("path")):
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
        "restart_hash": _norm_str(value.get("restart_hash")),
        "excl_hash": _norm_str(value.get("excl_hash")),
        "live": _norm_live(value.get("live")),
        "companion": _norm_companion(value.get("companion")),
    }


def _norm_companion(value):
    if not isinstance(value, dict):
        return None
    dropped = value.get("dropped")
    if isinstance(dropped, bool) or not isinstance(dropped, (int, float)):
        dropped = None
    else:
        try:
            dropped = float(dropped)
        except OverflowError:
            dropped = None
        if dropped is not None and not math.isfinite(dropped):
            dropped = None
    return {"dropped": dropped, "build": _norm_str(value.get("build")),
            "refused": _norm_str(value.get("refused")), "ext_dir": value.get("ext_dir") is True,
            "seen": value.get("seen") is True}


def _abs_path(value):
    """True for a usable absolute path string (no NUL, which os calls reject)."""
    return isinstance(value, str) and "\x00" not in value and os.path.isabs(value)


def _abs_paths(value):
    return [d for d in value if _abs_path(d)] if isinstance(value, list) else []


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
            "mode": (mode if isinstance(mode, int) and not isinstance(mode, bool)
                     and 0 <= mode <= 0o777 else None),
            "sha256": digest if isinstance(digest, str) else None,
        }
    path = value.get("path")
    originals = value.get("prefs_original")
    return {"path": path if _abs_path(path) else None,
            "chrome_dir": value.get("chrome_dir") is True, "ext_dir": value.get("ext_dir") is True,
            "companion_removed": value.get("companion_removed") is True, "files": files,
            "prefs_original": _norm_prefs_original(originals) if isinstance(originals, dict) else None}


def state_load(folder, warnings):
    """(state, existed) from `folder`/state.json. A missing file gives a new
    state (existed False); an unreadable or corrupt one a new state plus a
    "state_corrupt" warning (existed True; the profile records are then
    rebuilt from backup/*/meta.json, created_dirs from STATE_DIRS). Unknown
    fields are dropped. A file of a newer STATE_VERSION raises StateNewer:
    it is never overwritten."""
    path = os.path.join(folder, STATE_FILE)
    try:
        doc = json.loads(read_text(path))
    except FileNotFoundError:
        return _state_dirs_load(folder, new_state()), False
    except (OSError, ValueError, RecursionError) as exc:
        warnings.append(make_warning(WARN_STATE_CORRUPT, "state.json unusable, starting afresh (%s)"
                                     % (getattr(exc, "strerror", None) or exc.__class__.__name__)))
        return _state_dirs_load(folder, new_state(synced=True)), True
    state = new_state(synced=True)
    version = doc.get("version") if isinstance(doc, dict) else None
    if isinstance(version, int) and not isinstance(version, bool) and version > STATE_VERSION:
        raise StateNewer(version)
    if version != STATE_VERSION:
        warnings.append(make_warning(WARN_STATE_CORRUPT, "state.json has an unknown layout, starting afresh"))
        return _state_dirs_load(folder, state), True
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
        state["created_dirs"] = _abs_paths(created)
    native = doc.get("native")
    if isinstance(native, dict):
        state["native"] = {"manifests": _abs_paths(native.get("manifests")),
                           "created_dirs": _abs_paths(native.get("created_dirs"))}
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
    saved = len(warnings) == before
    if saved:
        _state_dirs_save(folder, state["created_dirs"], warnings)
    return saved


def _state_dirs_load(folder, state):
    """`state` with the folders kept in STATE_DIRS added to its
    created_dirs (state.json missing or corrupt)."""
    try:
        doc = json.loads(read_text(os.path.join(folder, STATE_DIRS), limit=65536))
    except (OSError, ValueError, RecursionError):
        return state
    for path in _abs_paths(doc):
        if path not in state["created_dirs"]:
            state["created_dirs"].append(path)
    return state


def _state_dirs_save(folder, created_dirs, warnings):
    """Keep `created_dirs` in STATE_DIRS, removed when there are none."""
    path = os.path.join(folder, STATE_DIRS)
    created_dirs = sorted(set(_abs_paths(list(created_dirs))))
    try:
        if created_dirs:
            write_if_changed(path, state_text(created_dirs), warnings, mode=0o600, make_dirs=False)
        else:
            _remove_file(path)
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not written: %s"
                                     % (STATE_DIRS, _oserror_text(exc))))


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


# ---- pending prefs.js cleanups (deferred while the browser runs) -------------

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
    if not _abs_path(value.get("path")):
        return None
    originals = value.get("prefs_original")
    created = value.get("created_dirs")
    return {
        "path": value["path"],
        "plan": _norm_plan(value.get("plan")),
        "prefs_original": _norm_prefs_original(originals) if isinstance(originals, dict) else None,
        "created_dirs": _abs_paths(created),
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
    except (OSError, ValueError):
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
    `prefs_original` in meta.json. Returns the backup record. Raises
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
    record = {"path": path, "chrome_dir": chrome_dir, "ext_dir": False, "companion_removed": False,
              "files": files, "prefs_original": prefs_original}
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
    """The original value of each of PREFS from prefs.js. A value equal
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
    """prefs_originals() without a v1 record: a value v0 could have written
    is ours."""
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
    """Without a v1 state: delete only the lines carrying a value v0 wrote."""
    current = parse_prefs(text)
    return [(p, None) for p in PREFS if current.get(p) in V0_PREF_VALUES[p]]


def prefs_plan_lost(text, ours):
    """Without any record (state.json, pending file and backup all lost),
    with `ours` ({pref: value} of the managed block taken out of user.js):
    delete the lines carrying a value v0 wrote or the one the block set
    (prefs_originals' rule). A pref of the block missing from prefs.js is
    deleted too: a running browser writes the block's value at exit. The
    two scope prefs get back a value the block's came from instead
    (_scope_original), deleted only when the default gives the block's."""
    current = parse_prefs(text)
    plan = []
    for p in PREFS:
        if current.get(p) in V0_PREF_VALUES[p]:
            plan.append((p, None))
        elif p in ours and current.get(p) in (None, ours[p]):
            plan.append((p, _scope_original(p, ours[p])))
    return plan


def _scope_original(pref, literal):
    """An original value of a scope pref the block set to `literal`
    (companion_prefs only flips SCOPE_PROFILE), None (delete the line) when
    `literal` is the one the default gives, or for any other pref. A guess
    (lost state only): it takes the browser's own default to be
    AUTODISABLE_DEFAULT / STARTUP_SCAN_DEFAULT, so a browser whose default
    differs gets a user value where it had none."""
    if pref not in (PREF_AUTODISABLE, PREF_STARTUP_SCAN) \
            or not isinstance(literal, str) or not _SCOPE_LITERAL.fullmatch(literal):
        return None
    value = int(literal)
    if pref == PREF_AUTODISABLE:
        return None if value == AUTODISABLE_DEFAULT & ~SCOPE_PROFILE else str(value | SCOPE_PROFILE)
    return None if value == STARTUP_SCAN_DEFAULT | SCOPE_PROFILE else str(value & ~SCOPE_PROFILE)


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
    given = p.add_mutually_exclusive_group(required=True)
    given.add_argument("--settings", metavar="JSON",
                       help="plugin settings as one JSON object")
    given.add_argument("--settings-file", metavar="FILE",
                       help="read the settings JSON from FILE, then delete it (the daemon's"
                       " way: an argv is public)")
    p.add_argument("--data", metavar="DIR", help="directory holding styles.json and css-mapping.json")
    p.add_argument("--profile", action="append", default=[], metavar="DIR",
                   help="only sync this profile directory (repeatable)")
    p.add_argument("--opacity", type=_opacity_arg, metavar="X", help="force the opacity (0..1)")
    p.add_argument("--off", action="store_true", help="force glass inactive")
    p.add_argument("--if-plugin", metavar="FILE",
                   help="refuse (nothing written) when FILE, the plugin's plugin.json, is missing "
                        "or DMS has the plugin disabled")
    p.add_argument("--plugin-dir", type=os.path.abspath, metavar="DIR",
                   help="plugin folder: install its companion add-on (liveControl)")

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

    p = sub.add_parser("native-host", help="internal: the companion add-on's native messaging host")
    p.add_argument("--data", metavar="DIR", help="directory holding public_suffix_list.dat")
    # What the browser passes: the manifest's path and the add-on's id.
    p.add_argument("extra", nargs="*", metavar="ARG", help=argparse.SUPPRESS)

    p = sub.add_parser("active-site", help="the site shown in a browser window (read-only)")
    p.add_argument("--json", action="store_true", required=True, help="JSON output")
    p.add_argument("--pid", type=int, required=True, metavar="PID",
                   help="process id of the niri window (the browser's main process)")
    p.add_argument("--app-id", required=True, metavar="ID", help="app-id of the niri window")
    which = p.add_mutually_exclusive_group()
    which.add_argument("--title", metavar="T", help="title of the niri window")
    # What the daemon passes instead of the title: an argv is readable by
    # every local user (/proc/PID/cmdline), so the title is asked of niri.
    which.add_argument("--window-id", type=int, metavar="ID",
                   help="id of the niri window: its title is read from niri ($NIRI_SOCKET)")
    p.add_argument("--data", metavar="DIR", help="directory holding " + PSL_FILE)
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


# ---- live push ----------------------------------------------------------------
#
# A running browser re-reads the stylesheets and user.js only when it
# restarts, except for the exclusion list, which the companion extension
# applies live. The profile record keeps "live" {instance, restart_hash,
# excl_hash, mtime}: what the running instance (its lock_instance() key)
# has, the restart part loaded at its start and the exclusion list loaded
# then or pushed and acknowledged since, and the newest mtime of the
# profile's RESTART_FILES right after the writes of the sync that pushed
# (taken before the push: an edit while the push waits for acks must not
# end up inside it; one that does makes the record unknown). A closed or restarted
# browser drops it (_h1_rule_needed; status also checks the key). While it
# matches the record and none of the RESTART_FILES changed after `mtime`
# (live_applied), files written after the start need no restart; any later
# write, ours or the user's (their own rules in userChrome.css or
# userContent.css, user.js outside our block), asks for one again.

_INSTANCE_KEY = re.compile(r"([0-9]{1,10}):[0-9]+")


def live_push(env, domains):
    """Send the exclusion list `domains` to the native hosts of the running
    browsers. Returns (delivered, acked): the number of hosts the list was
    sent to, and the frozenset of browser pids whose host acknowledged that
    the list is applied.

    Acks are per browser pid, not per profile: one host runs per browser
    process (it is a child of the process holding the profile's
    .parentlock), and a profile's lock_instance() key starts with that pid,
    so an ack covers exactly the profile that process runs (_live_update).

    Every host-<pid>.sock of the runtime folder gets the list (each browser
    must know it), all at once: one line {"excluded": [...]}, then up to
    LIVE_ACK_TIMEOUT seconds in all for the {"acked": seq} lines. A socket
    nobody listens on any more (a host that died) goes, with its pid's
    active-/ack- files; a starting host renames its socket into place only
    once it listens (_NativeHost.listen), so a refusal means a dead one."""
    rdir = runtime_dir(env)
    if rdir is None or not _runtime_dir_ours(rdir):
        return 0, frozenset()
    try:
        names = os.listdir(rdir)
    except OSError:
        return 0, frozenset()
    pids = sorted(int(m.group(1)) for m in map(_HOST_SOCKET.fullmatch, names) if m)
    if not pids:
        return 0, frozenset()
    import select
    line = (json.dumps({"excluded": list(domains)}) + "\n").encode("ascii")
    waiting = {}
    acked = set()
    try:
        for pid in pids:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
            try:
                sock.settimeout(LIVE_CONNECT_TIMEOUT)
                sock.connect(runtime_file(rdir, "host", pid))
                sock.sendall(line)
            except (ConnectionRefusedError, FileNotFoundError):
                sock.close()
                for kind in ("host", "active", "ack"):
                    try:
                        os.unlink(runtime_file(rdir, kind, pid))
                    except OSError:
                        pass
                continue
            except OSError:  # busy or broken: not delivered
                sock.close()
                continue
            waiting[sock] = (pid, b"")
        delivered = len(waiting)
        deadline = time.monotonic() + LIVE_ACK_TIMEOUT
        while waiting:
            left = deadline - time.monotonic()
            ready = select.select(list(waiting), [], [], left)[0] if left > 0 else []
            if not ready:
                break
            for sock in ready:
                pid, buf = waiting.pop(sock)
                try:
                    chunk = sock.recv(4096)
                except OSError:
                    chunk = b""
                buf += chunk
                if chunk and b"\n" not in buf and len(buf) < 4096:
                    waiting[sock] = (pid, buf)
                    continue
                sock.close()
                try:
                    reply = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError):
                    continue
                seq = reply.get("acked") if isinstance(reply, dict) else None
                if isinstance(seq, int) and not isinstance(seq, bool):
                    acked.add(pid)
    finally:
        for sock in waiting:
            sock.close()
    return delivered, frozenset(acked)


def _live_push_safe(env, domains):
    """live_push() as (delivered, acked pids), where any failure or unusable
    result counts as nothing delivered: the push is best effort, and sync
    must still save its state after it."""
    try:
        delivered, acked = live_push(env, list(domains))
        acked = frozenset(pid for pid in acked if isinstance(pid, int) and not isinstance(pid, bool))
        if not isinstance(delivered, int) or isinstance(delivered, bool):
            delivered = 0
    except Exception:  # a broken push is no acknowledgement
        return 0, frozenset()
    return max(delivered, len(acked)), acked


def instance_browser_pid(key):
    """The browser pid of a lock_instance() key, None for "?" or None."""
    match = _INSTANCE_KEY.fullmatch(key) if isinstance(key, str) else None
    return int(match.group(1)) if match else None


def restart_files_mtime(path):
    """Newest st_mtime of the RESTART_FILES of the profile folder `path`,
    0.0 when none of them exists."""
    newest = 0.0
    for rel in RESTART_FILES:
        try:
            newest = max(newest, os.stat(os.path.join(path, rel)).st_mtime)
        except OSError:
            continue
    return newest


def _live_current(path, live, key):
    """True when the live record `live` is that of the running instance
    `key` and no RESTART_FILES of `path` changed after it was taken."""
    return bool(live is not None and key is not None and live["instance"] == key
                and not files_changed_since(path, live["mtime"]))


def instance_loaded(path, record, key):
    """(restart_hash, excl_hash) that the running instance `key` of the
    profile folder `path` has, None when it cannot be told: its live record
    while no file changed after it, else `record`'s last sync when no
    RESTART_FILES changed since the instance started and the files are
    still that sync's."""
    live = record.get("live")
    if _live_current(path, live, key):
        return live["restart_hash"], live["excl_hash"]
    if record.get("restart_hash") is None or record.get("excl_hash") is None:
        return None
    start = process_start(key) if instance_browser_pid(key) is not None else None
    if start is None or files_changed_since(path, start) or not profile_applied(path, record):
        return None
    return record["restart_hash"], record["excl_hash"]


def live_applied(path, record, key):
    """True when the running instance `key` of the profile folder `path`
    has what `record`'s last sync wrote (the restart part since its start,
    the exclusion list live) and nothing was written after that."""
    live = record.get("live") if record is not None else None
    return bool(_live_current(path, live, key)
                and record.get("applied_hash") is not None
                and live["restart_hash"] == record.get("restart_hash")
                and live["excl_hash"] == record.get("excl_hash"))


def _live_applied_now(record):
    """live_applied() for the instance a sync just recorded."""
    return live_applied(record["path"], record, record["instance"])


def _live_update(ctx, acked):
    """Record, after the writes and the push, what each probed running
    instance (ctx["instances"], probed before the writes) now has.

    An acknowledged push gives it the exclusion list of this sync on top of
    what it had loaded. Without an acknowledgement its live record stays
    only while it records the list this sync wrote: the outcome of a push
    of another list is unknown (delivered, the ack lost or late), so the
    record goes. An instance whose loaded files cannot be told gets none
    (a restart is needed, as in v1.0), and so does one whose RESTART_FILES
    changed between this sync's writes and the end of the push: that
    change, not this sync's, may be what it has not loaded."""
    for pid, (key, loaded, written) in sorted(ctx["instances"].items()):
        record = ctx["state"]["profiles"][pid]
        bpid = instance_browser_pid(key)
        if bpid is None or key != record["instance"]:
            continue  # unknown, or restarted since the probe
        live = record["live"]
        if loaded is None or record["excl_hash"] is None:
            record["live"] = None
        elif bpid in acked:
            if written is None or restart_files_mtime(record["path"]) != written:
                record["live"] = None
            else:
                record["live"] = {"instance": key, "restart_hash": loaded[0],
                                  "excl_hash": record["excl_hash"], "mtime": written}
        elif live is not None and live["excl_hash"] != record["excl_hash"]:
            record["live"] = None


# ---- per-profile output -------------------------------------------------------
#
# The stylesheets are the same for every profile; the user.js block is
# rendered per profile (userjs_prefs takes the Profile), and so are its
# prefs and the hashes. profile_output() is the one seam, and today it
# gives the same block to every profile. The companion prefs extend it:
# family and variant come with the Profile; the channel (read from the
# profile's compatibility.ini through its path), the companion state and
# the profile's original values (record["prefs_original"], for the scopes
# derived from them) need the path or the record, which _sync_profile
# passes to the seam. applied_hash_of() is the one formula of applied_hash,
# for the seam and for profile_applied() alike.
#
# Two fingerprints, besides applied_hash, tell a change a running browser
# picks up live from one that needs a restart:
#   restart_hash  every output, the content stylesheet rendered with an
#                 empty exclusion list (what only a restart applies)
#   excl_hash     the normalised exclusion list (what a live push applies)
# The bare stylesheet costs a second site styles build: it is rendered only
# when a profile's output changed. Unchanged output (same applied_hash and
# excl_hash) keeps the record's restart_hash, that of the files on disk.

def _render_content(settings, opacity, sites, off, surfaces, problems=None):
    """content_css() with the site styles of `sites` (sites_load(), None for
    none) built for `settings`; site style problems go to `problems`."""
    sites_css = ""
    if sites is not None:
        sites_css = sites_build_css(sites, settings["excluded"], settings["disabledStyles"],
                                    settings["genericStyle"], problems, live_gate(settings))
    return content_css(settings, opacity, sites_css, off, surfaces, sites)


def sync_base(settings, opacity, off, chrome, content, restart_content=None):
    """The profile-independent part of what sync writes, for profile_output().

    `restart_content` is the content stylesheet rendered with the same
    inputs but an empty exclusion list, or a function without arguments
    that renders it (called at most once, only when a profile needs it);
    None: `content`, which is it when the list is empty. restart_hash is
    computed from it, so a change of the exclusion list alone never
    changes restart_hash, whatever the renderers make of the list."""
    if restart_content is None:
        restart_content = content
    return {
        "settings": settings, "opacity": opacity, "off": off,
        "chrome": chrome, "content": content,
        "hash_prefix": _hash_prefix(chrome, content),
        "restart_content": restart_content, "restart_prefix": None,
        "excl_hash": _sha256("\n".join(sorted(settings["excluded"])))[:16],
    }


def _hash_prefix(chrome, content):
    """sha256 state after "chrome\0content\0": a profile only adds its block."""
    return hashlib.sha256(("%s\0%s\0" % (chrome, content)).encode("utf-8", "surrogateescape"))


def _prefix_hash(prefix, text):
    digest = prefix.copy()
    digest.update(text.encode("utf-8", "surrogateescape"))
    return digest.hexdigest()[:16]


def applied_hash_of(chrome, content, block, prefix=None):
    """applied_hash of the stylesheets `chrome`, `content` and the user.js
    block `block`: sha256 of "chrome\0content\0block", first 16 hex digits.
    `prefix` is _hash_prefix(chrome, content) when already computed."""
    return _prefix_hash(prefix if prefix is not None else _hash_prefix(chrome, content), block)


def _restart_prefix(base):
    """_hash_prefix() of the chrome and the bare content stylesheet,
    rendered on first use."""
    if base["restart_prefix"] is None:
        content = base["restart_content"]
        if callable(content):
            content = content()
        base["restart_prefix"] = _hash_prefix(base["chrome"], content)
    return base["restart_prefix"]


def profile_output(base, profile, record=None, companion=None, guard=()):
    """What sync writes to `profile` (a Profile) and its fingerprints:
    {chrome, content, block, block_prefs, block_values, hash, restart_hash,
    excl_hash}. hash is applied_hash (applied_hash_of), the one
    profile_applied() finds again on disk. `record` is the profile's state
    record, None for a new one: an output it already describes keeps its
    restart_hash. `companion` goes to userjs_prefs(). `guard`
    (companion_guard) ends the block but is not in block_prefs: those
    prefs are not owned."""
    prefs = userjs_prefs(base["settings"], base["opacity"], base["off"], profile, companion)
    block = userjs_block_text(prefs + list(guard))
    applied = applied_hash_of(base["chrome"], base["content"], block, base["hash_prefix"])
    if (record is not None and record.get("restart_hash") is not None
            and record.get("applied_hash") == applied
            and record.get("excl_hash") == base["excl_hash"]):
        restart = record["restart_hash"]
    else:
        restart = _prefix_hash(_restart_prefix(base), block)
    return {
        "chrome": base["chrome"], "content": base["content"], "block": block,
        "block_prefs": [p for p, _ in prefs], "block_values": parse_prefs(block),
        "hash": applied, "restart_hash": restart, "excl_hash": base["excl_hash"],
    }


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
            "restart_hash": None, "excl_hash": None, "live": None, "companion": None,
        }
        backup = state["backups"].get(pid)
        if backup is not None and backup["companion_removed"]:
            # Removed by the user before state.json was lost.
            record["companion"] = {"dropped": None, "build": compat_values(path).get("LastVersion"),
                                   "refused": None, "ext_dir": backup["ext_dir"], "seen": True}
        pend = ctx["pending"].get(pid)
        if pend is not None:
            # The deferred cleanup is dropped below: its prefs become
            # restore_prefs (kept by the block, restored once the browser closes).
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
        # file goes once state.json is saved, its state folders kept.
        ctx["taken_back"].add(pid)
        for folder in ctx["pending"][pid]["created_dirs"]:
            if folder not in state["created_dirs"]:
                state["created_dirs"].append(folder)
    record["path"] = path
    if family is not None:
        record["family"] = family
    if profile.variant is not None:
        record["variant"] = profile.variant
    state["profiles"][pid] = record

    comp_state, comp_originals = _companion_plan(ctx, profile, record, fresh, prefs_text)
    # Companion prefs leaving the block while the browser runs: it writes
    # its values (unsigned add-ons allowed) to prefs.js, restored only once
    # it is closed. Until then the block holds the originals: user.js
    # overrides prefs.js at every start.
    guard = []
    if comp_originals is None:
        waiting = [p for p in COMPANION_PREFS
                   if p in record["owned_prefs"] or p in record["restore_prefs"]]
        if waiting and lock_state(path) != LOCK_FREE:
            guard = companion_guard(record["prefs_original"], waiting)
    out = profile_output(ctx["base"], profile, None if fresh else record, comp_originals, guard)
    # What a running browser has loaded, probed before anything is written
    # (the writes would make every file newer than its start). Only an
    # exclusion change can be applied live, and only a live record can
    # carry over: otherwise any write needs a restart, nothing to probe.
    if not fresh and (out["excl_hash"] != record["excl_hash"] or record["live"] is not None):
        lstate, key = lock_instance(path)
        if lstate != LOCK_FREE:
            # (key, loaded, RESTART_FILES mtime right after the writes)
            ctx["instances"][pid] = (key, instance_loaded(path, record, key), None)
    writes = [
        (chrome_path, out["chrome"], None),
        (content_path, out["content"], None),
    ]
    for name, rel in PROFILE_FILES:
        writes.append((os.path.join(path, rel), apply_ours(name, texts[name] or "", out["block"]),
                       0o600 if name == USER_JS else None))
    changed = False
    clean = True
    # A dangling chrome/ link would make the writes create its target
    # folders outside the profile.
    chrome_dangling = os.path.islink(chrome_dir) and not os.path.exists(chrome_dir)
    if chrome_dangling:
        warnings.append(make_warning(WARN_DANGLING_LINK, "%s is a dangling symlink, left unchanged"
                                     % CHROME_DIR, family, pid))
        clean = False
    for target, text, mode in writes:
        if chrome_dangling and os.path.dirname(target) == chrome_dir:
            continue
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
    if _companion_files(ctx, profile, record, comp_state):
        changed = True
    if pid in ctx["instances"]:
        # The live record's baseline, taken now and not after the push.
        ctx["instances"][pid] = ctx["instances"][pid][:2] + (restart_files_mtime(path),)
    record["applied_hash"] = out["hash"] if clean else None
    record["restart_hash"] = out["restart_hash"] if clean else None
    record["excl_hash"] = out["excl_hash"] if clean else None

    # Prefs that left the block get their original value back in
    # prefs.js, only while the browser is closed (it rewrites the file).
    owned = out["block_prefs"]
    if not fresh:
        # A pref owned again whose original was already put back gets
        # its current value (the user's latest choice) as the new original.
        current = parse_prefs(prefs_text)
        # A companion pref never owned (a v1.0 install) has no value of ours
        # in prefs.js: whatever it holds is the user's, even our own value.
        for pref in owned:
            if pref not in record["owned_prefs"] and pref not in record["restore_prefs"]:
                value = current.get(pref)
                if value is None or (out["block_values"].get(pref) == value
                                     and pref not in COMPANION_PREFS):
                    record["prefs_original"][pref] = {"absent": True}
                else:
                    record["prefs_original"][pref] = {"value": value}
    _backup_add_originals(sdir, pid, state["backups"].get(pid), record["prefs_original"], warnings,
                          family)
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
    """prefs.js originals of a profile without a state record: from a pending
    deferred uninstall (prefs.js may still hold our values), else from the
    backup's meta.json (state.json lost or corrupt), else from prefs.js."""
    pend = ctx["pending"].get(pid)
    backup = ctx["state"]["backups"].get(pid)
    if pend is not None:
        if pend["prefs_original"] is None:
            return prefs_originals_v0(prefs_text)
        out = copy.deepcopy(pend["prefs_original"])
    elif backup is not None and backup["prefs_original"] is not None:
        out = copy.deepcopy(backup["prefs_original"])
    else:
        return prefs_originals(prefs_text, userjs_text)
    # A v1.0 pending file or backup lacks the companion prefs, which v1.0
    # never wrote: prefs.js holds the user's values.
    for pref, item in prefs_originals(prefs_text, userjs_text).items():
        out.setdefault(pref, item)
    return out


def _backup_add_originals(sdir, pid, backup, originals, warnings, family=None):
    """Add to the backup record `backup` (and its meta.json) the original
    of each pref of `originals` it lacks: a v1.0 backup has no companion
    prefs, and a lost state.json must still restore them. Never replaces
    an original already there. A backup whose originals were dropped (kept
    by an uninstall, its prefs restored) takes all of `originals`."""
    if backup is None:
        return
    if backup["prefs_original"] is None:
        backup["prefs_original"] = {}
    missing = {p: v for p, v in originals.items() if p not in backup["prefs_original"]}
    if not missing:
        return
    backup["prefs_original"].update(copy.deepcopy(missing))
    meta = os.path.join(backup_folder(sdir, pid), BACKUP_META)
    try:
        doc = json.loads(read_text(meta))
        if isinstance(doc, dict) and doc.get("prefs_original") is None:
            doc["prefs_original"] = {}
        if isinstance(doc, dict) and isinstance(doc.get("prefs_original"), dict):
            for pref, item in missing.items():
                doc["prefs_original"].setdefault(pref, item)
            write_if_changed(meta, state_text(doc), warnings, mode=0o600, make_dirs=False)
    except (OSError, ValueError, RecursionError) as exc:
        reason = _oserror_text(exc) if isinstance(exc, OSError) else "unreadable"
        warnings.append(make_warning(WARN_BACKUP_FAILED, "%s not updated: %s"
                                     % (BACKUP_META, reason), family, pid))


def _companion_plan(ctx, profile, record, fresh, prefs_text):
    """(state, originals) of the companion add-on in one profile, before
    its files are written. `originals` ({pref: JS literal or None}, the
    original prefs.js values the companion prefs are derived from) is None
    when the block holds no companion pref. Without --plugin-dir the
    add-on is left as it is (R15): a deposit of ours keeps its prefs."""
    path = profile.path
    comp = record["companion"]
    compat = compat_values(path)
    state = companion_state(path, profile.family, profile.variant, comp,
                            ctx["base"]["settings"]["liveControl"], ctx["xpi"] is not None, compat,
                            ctx["env"])
    if state == COMPANION_REFUSED and comp["dropped"] is not None:
        # Deleted by the browser (signing required): no new deposit until
        # its build changes.
        comp["refused"] = compat.get("LastVersion") or ""
        comp["dropped"] = None
    elif state == COMPANION_REMOVED:
        comp["seen"] = True  # the mark outlives the deposit it was read from
    elif state in COMPANION_DEPOSITED and comp is not None:
        comp["refused"] = None
    ctx["companion"][profile.id] = state
    keep = (state == COMPANION_NO_PLUGIN and comp is not None and comp["dropped"] is not None
            and os.path.lexists(companion_xpi_path(path)))
    if state not in COMPANION_DEPOSITED and not keep:
        return state, None
    current = parse_prefs(prefs_text)
    originals = {}
    for pref in COMPANION_PREFS:
        if fresh or pref in record["owned_prefs"] or pref in record["restore_prefs"]:
            originals[pref] = record["prefs_original"].get(pref, {"absent": True}).get("value")
        else:
            # the original a pref that leaves the block is restored to
            originals[pref] = current.get(pref)
    return state, originals


def companion_remove(profile_path, comp, keep_seen=False):
    """Remove the companion add-on from the profile folder, and
    extensions/ when we created it and it is now empty. Updates `comp`
    (record["companion"], or None; its "seen" mark is cleared unless
    `keep_seen`). Returns True when the xpi was there. Raises OSError."""
    target = companion_xpi_path(profile_path)
    removed = _remove_file(target)
    if comp is not None:
        comp["dropped"] = None
        comp["seen"] = comp["seen"] and keep_seen
        if comp["ext_dir"]:
            _rmdir_quiet(os.path.dirname(target))
            comp["ext_dir"] = os.path.isdir(os.path.dirname(target))
    return removed


def _companion_files(ctx, profile, record, state):
    """Deposit (or remove) the companion add-on of one profile for its
    `state`. Returns True when a file changed."""
    warnings, pid, family, path = ctx["warnings"], profile.id, profile.family, profile.path
    if state == COMPANION_NO_PLUGIN:
        return False
    target = companion_xpi_path(path)
    folder = os.path.dirname(target)
    ctx["folders"].add(folder)
    backup = ctx["state"]["backups"].get(pid)
    changed = False
    try:
        if record["companion"] is None and (state in COMPANION_DEPOSITED
                                            or _ext_dir_ours(folder, backup)):
            record["companion"] = {"dropped": None, "build": compat_values(path).get("LastVersion"),
                                   "refused": None, "ext_dir": _ext_dir_ours(folder, backup),
                                   "seen": False}
        if state in COMPANION_DEPOSITED:
            comp = record["companion"]
            if make_dirs_tracked(folder):
                comp["ext_dir"] = True
            changed = write_bytes_if_changed(target, ctx["xpi"], warnings, family, pid,
                                             mode=0o644, make_dirs=False)
            if changed or comp["dropped"] is None:
                comp["dropped"] = os.stat(target).st_mtime
                comp["build"] = compat_values(path).get("LastVersion")
            if state == COMPANION_INSTALLED:
                comp["seen"] = True
        else:
            changed = companion_remove(path, record["companion"],
                                       keep_seen=state == COMPANION_REMOVED)
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not written: %s"
                                     % (COMPANION_XPI, _oserror_text(exc)), family, pid))
    comp = record["companion"]
    if comp is not None and comp == {"dropped": None, "build": comp["build"], "refused": None,
                                     "ext_dir": False, "seen": False} \
            and state not in COMPANION_DEPOSITED:
        record["companion"] = None
    _backup_mark(ctx["sdir"], pid, backup, "ext_dir", comp is not None and comp["ext_dir"],
                 warnings, family)
    _backup_mark(ctx["sdir"], pid, backup, "companion_removed", state == COMPANION_REMOVED,
                 warnings, family)
    return changed


def _ext_dir_ours(folder, backup):
    """True when we created the profile's extensions/ `folder`, read when no
    companion record says it (state.json lost or corrupt): the profile's
    backup says so, or the folder holds nothing but our add-on."""
    if backup is not None and backup["ext_dir"]:
        return True
    try:
        return os.listdir(folder) == [COMPANION_XPI]
    except OSError:
        return False


def _backup_mark(sdir, pid, backup, key, value, warnings, family=None):
    """Keep the flag `key` ("ext_dir": we created extensions/;
    "companion_removed": the user removed the add-on) in the backup record
    `backup` and its meta.json, where it survives a lost or corrupt
    state.json."""
    if backup is None or backup[key] == value:
        return
    backup[key] = value
    meta = os.path.join(backup_folder(sdir, pid), BACKUP_META)
    try:
        doc = json.loads(read_text(meta))
        if isinstance(doc, dict):
            doc[key] = value
            write_if_changed(meta, state_text(doc), warnings, mode=0o600, make_dirs=False)
    except (OSError, ValueError, RecursionError) as exc:
        reason = _oserror_text(exc) if isinstance(exc, OSError) else "unreadable"
        warnings.append(make_warning(WARN_BACKUP_FAILED, "%s not updated: %s"
                                     % (BACKUP_META, reason), family, pid))


def native_manifest_path(env=None):
    """~/.mozilla/native-messaging-hosts/<NATIVE_MANIFEST_NAME>, read by
    Firefox and LibreWolf alike."""
    return os.path.join(home_dir(env), NATIVE_MANIFEST_REL, NATIVE_MANIFEST_NAME)


def _manifest_is_ours(path):
    """True when `path` is a native messaging manifest of our host."""
    try:
        doc = json.loads(read_text(path, limit=65536))
    except (OSError, ValueError, RecursionError):
        return False
    return (isinstance(doc, dict) and doc.get("name") == NATIVE_HOST_NAME
            and doc.get("allowed_extensions") == [COMPANION_ID])


def native_remove(env, state, sdir, warnings):
    """Remove the native messaging manifests recorded in `state` (and ours
    at the default path), the folders made for them and the host wrapper.
    The wrapper stays while a manifest that names it could not be removed:
    the next sync or uninstall retries both (uninstall still clears the
    state folder that holds it). Returns True when a file went."""
    native = state["native"]
    _native_dirs_load(sdir, native)
    paths = list(native["manifests"])
    default = native_manifest_path(env)
    if default not in paths:
        paths.append(default)
    removed = False
    kept = []
    unrecorded = None
    for path in paths:
        try:
            if _manifest_is_ours(path) and _remove_file(path):
                removed = True
                if path not in native["manifests"]:
                    unrecorded = path
        except OSError as exc:
            kept.append(path)
            warnings.append(make_warning(WARN_WRITE_FAILED, "%s not removed: %s"
                                         % (NATIVE_MANIFEST_NAME, _oserror_text(exc))))
    for folder in sorted(native["created_dirs"], key=len, reverse=True):
        _rmdir_quiet(folder)
    if unrecorded is not None and not native["created_dirs"]:
        # Ours, but no state.json says it (lost or corrupt) nor which
        # folders were made for it: they go once empty
        # (native-messaging-hosts/, then ~/.mozilla/).
        folder = os.path.dirname(unrecorded)
        _rmdir_quiet(folder)
        _rmdir_quiet(os.path.dirname(folder))
    native["manifests"] = kept
    native["created_dirs"] = [d for d in native["created_dirs"] if os.path.isdir(d)]
    _native_dirs_save(sdir, native, warnings)
    if kept:
        return removed
    try:
        if _remove_file(os.path.join(sdir, HOST_WRAPPER)):
            removed = True
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not removed: %s"
                                     % (HOST_WRAPPER, _oserror_text(exc))))
    return removed


def _native_dirs_load(sdir, native):
    """Add to native["created_dirs"] the folders kept in NATIVE_DIRS (they
    survive a lost or corrupt state.json)."""
    try:
        doc = json.loads(read_text(os.path.join(sdir, NATIVE_DIRS), limit=65536))
    except (OSError, ValueError, RecursionError):
        return
    for folder in _abs_paths(doc):
        if folder not in native["created_dirs"]:
            native["created_dirs"].append(folder)


def _native_dirs_save(sdir, native, warnings):
    """Keep native["created_dirs"] in NATIVE_DIRS, removed once empty."""
    path = os.path.join(sdir, NATIVE_DIRS)
    try:
        if native["created_dirs"]:
            write_if_changed(path, state_text(sorted(native["created_dirs"])), warnings, mode=0o600,
                             make_dirs=False)
        else:
            _remove_file(path)
    except OSError as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "%s not written: %s"
                                     % (NATIVE_DIRS, _oserror_text(exc))))


def _native_dirs_ours(manifest):
    """The folders holding nothing but our `manifest` (its folder, then
    the one above), made for it by a sync whose record is lost."""
    folder = os.path.dirname(manifest)
    parent = os.path.dirname(folder)
    try:
        if os.listdir(folder) != [os.path.basename(manifest)] or not _manifest_is_ours(manifest):
            return []
        return [parent, folder] if os.listdir(parent) == [os.path.basename(folder)] else [folder]
    except OSError:
        return []


def _sync_native(ctx, plugin_dir):
    """Full syncs: write the native messaging manifest and the host
    wrapper while a native profile has the add-on deposited, else remove
    them. With liveControl on and no --plugin-dir they are left as they
    are (R15); with liveControl off they are removed, --plugin-dir or not."""
    state, warnings, env, sdir = ctx["state"], ctx["warnings"], ctx["env"], ctx["sdir"]
    enabled = ctx["base"]["settings"]["liveControl"]
    if enabled and ctx["xpi"] is None:
        return False
    if not (enabled and any(s in COMPANION_DEPOSITED for s in ctx["companion"].values())):
        return native_remove(env, state, sdir, warnings)
    native = state["native"]
    wrapper = os.path.join(sdir, HOST_WRAPPER)
    manifest = native_manifest_path(env)
    folder = os.path.dirname(manifest)
    changed = False
    try:
        changed = write_if_changed(wrapper, host_wrapper_text(plugin_dir), warnings, mode=0o755)
        _native_dirs_load(sdir, native)
        made = make_dirs_tracked(folder)
        if manifest not in native["manifests"] and not native["created_dirs"]:
            # No record of ours (the state folder lost): folders holding
            # nothing but our manifest are ours.
            made += _native_dirs_ours(manifest)
        for folder_made in made:
            if folder_made not in native["created_dirs"]:
                native["created_dirs"].append(folder_made)
        _native_dirs_save(sdir, native, warnings)
        if manifest not in native["manifests"]:
            native["manifests"].append(manifest)
        ctx["folders"].add(folder)
        if write_if_changed(manifest, native_manifest_text(wrapper), warnings, mode=0o644,
                            make_dirs=False):
            changed = True
    except (OSError, ValueError) as exc:
        warnings.append(make_warning(WARN_WRITE_FAILED, "native messaging host not written: %s"
                                     % (getattr(exc, "strerror", None) or exc)))
    return changed


def _sync_xpi(plugin_dir, warnings):
    """The companion xpi built from <plugin_dir>/extension, None without
    --plugin-dir or when it cannot be built (a warning)."""
    if not plugin_dir:
        return None
    try:
        return companion_xpi(os.path.join(plugin_dir, EXTENSION_DIR))
    except (OSError, ValueError) as exc:
        warnings.append(make_warning(WARN_DATA_UNAVAILABLE, "companion add-on unavailable: %s"
                                     % (getattr(exc, "strerror", None) or exc)))
        return None


def _h1_rule_needed(ctx, active):
    """Probe every known profile and decide whether the niri rule stays.

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
            record["live"] = None
            continue
        if record["live"] is not None and record["live"]["instance"] != key:
            record["live"] = None  # restarted: it loaded the files anew
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
    """Delete the v0 site-styles cache. Returns True when it was there."""
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
    return ("plugin_gone: the plugin folder (--if-plugin) is gone or being removed, "
            "or DMS has the plugin disabled; nothing was written")


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
    if args.settings_file is not None:
        try:
            text = read_settings_file(args.settings_file)
        except ValueError as exc:
            raise UsageError("invalid --settings-file: %s" % exc)
    else:
        text = args.settings
    try:
        settings = settings_from_json(text)
    except ValueError as exc:
        raise UsageError("invalid --settings: %s" % exc)
    # The plugin's uninstall sweep may run while a sync the daemon launched
    # just before the folder was deleted is starting or waiting for the
    # lock: that sync must not write everything back. Checked again under
    # the lock, which the sweep's uninstall holds while it cleans.
    if args.if_plugin and (plugin_gone(args.if_plugin, env) or plugin_disabled(env)):
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
    # Disabling the plugin does not kill a sync the daemon already started
    # (Proc.release only drops its callback), and the uninstall run from
    # onDestruction may take the lock first: under the lock, the DMS
    # settings say whether that uninstall happened. DMS writes
    # "enabled": false (synchronous atomic write, SettingsData
    # pluginSettingsFile blockWrites) before it unloads the plugin, so before
    # onDestruction starts the uninstall: no marker of our own is needed,
    # and none is left behind.
    if args.if_plugin and (plugin_gone(args.if_plugin, env) or plugin_disabled(env)):
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
        sites = None
        if args.data and active and settings["pagesTransparent"]:
            try:
                sites = sites_load(args.data)
            except (OSError, ValueError, RecursionError) as exc:
                warnings.append(make_warning(WARN_DATA_UNAVAILABLE, "site styles unavailable: %s"
                                             % (getattr(exc, "strerror", None) or exc)))
        surfaces = dms_surfaces(env)
        chrome = chrome_css(settings, opacity, surfaces, args.off)
        problems = []
        content = _render_content(settings, opacity, sites, args.off, surfaces, problems)
        for problem in problems:
            warnings.append(make_warning(WARN_SITE_STYLE, "site style skipped: %s" % problem))
        # restart_hash: the content rendered for real with no exclusion
        # (everything the exclusion list adds left out, whatever its form).
        # Rendered only when a profile's output changed (_restart_prefix).
        restart_content = None
        if settings["excluded"]:
            bare = copy.copy(settings)
            bare["excluded"] = []

            def restart_content():
                return _render_content(bare, opacity, sites, args.off, surfaces)

        ctx = {
            "env": env, "sdir": sdir, "state": state, "warnings": warnings,
            "base": sync_base(settings, opacity, args.off, chrome, content, restart_content),
            "disk_glass": {}, "folders": {sdir}, "instances": {},
            "pending": pending_load(sdir), "taken_back": set(),
            "xpi": _sync_xpi(args.plugin_dir, warnings) if settings["liveControl"] else None,
            "companion": {},
        }
        changed = []
        for profile in _select_profiles(args, env, state, warnings):
            if _sync_profile(ctx, profile) and profile.id not in changed:
                changed.append(profile.id)
            if profile.family == "zen" and zen_transparency(profile.path):
                warnings.append(zen_warning(profile.id))
        if not args.profile:
            _sync_native(ctx, args.plugin_dir)
        rule_needed, lock_states = _h1_rule_needed(ctx, active)
        niri_changed = _sync_niri(ctx, rule_needed)
        _remove_v0_cache(env, warnings)
        sweep_stale_tmp(ctx["folders"])
        # The push follows the writes (a browser that restarts meanwhile
        # loads the new files) and comes before state.json is saved, under
        # the lock: its acknowledgements decide what the running browsers
        # have applied live. A --profile sync (captures, tests) does not
        # push: its settings are not those of the running browsers. Nor
        # does a sync with liveControl off (the add-on is not installed).
        if not args.profile:
            # A --profile sync (captures, tests) leaves the global record
            # alone: status keeps describing the real profiles.
            state["last_sync"] = last_sync_record(settings, collections.OrderedDict([
                ("active", active), ("reason", reason), ("opacity", opacity),
                ("opacity_source", source), ("surface", colors.surface), ("mode", mode)]),
                warnings)
        delivered, acked = 0, frozenset()
        if not args.profile and settings["liveControl"]:
            # Saved before the push too: a host starting meanwhile reads its
            # first list from state.json once its socket is bound, so it
            # gets this list either way (a failure is reported below).
            state_save(sdir, state, [])
            delivered, acked = _live_push_safe(env, settings["excluded"])
        _live_update(ctx, acked)
        saved = state_save(sdir, state, warnings)
        if saved:
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
        # LOCK_UNKNOWN counts as running, as in _h1_rule_needed and the deferred prefs.
        # A running profile whose change it has applied live (the exclusion
        # list, acknowledged by its host) needs no restart, as long as the
        # state recording it was saved: status reads it back from there.
        "running_changed": [pid for pid in changed if lock_states.get(pid, LOCK_FREE) != LOCK_FREE
                            and not (saved and _live_applied_now(state["profiles"][pid]))],
        "niri_changed": bool(niri_changed),
        # The push: browsers whose host got the list, and of those, the
        # ones whose add-on acknowledged it.
        "live": {"hosts": delivered, "acked": len(acked)},
        # The companion add-on of each synced profile, with --plugin-dir.
        **({"companion": [{"profile": pid, "state": st} for pid, st in sorted(ctx["companion"].items())]}
           if args.plugin_dir else {}),
        "warnings": warnings,
    })
    return EXIT_OK


# ---- uninstall ----------------------------------------------------------------

def _remove_file(path):
    """Delete a file we own; True when it was there."""
    try:
        os.unlink(path)
        return True
    except (FileNotFoundError, ValueError):
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
                    os.chmod(target, item["mode"] & 0o777)
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


def _uninstall_profile(ctx, pid, path, family):
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


def _uninstall_plan(ctx, pid, path, record, traces, userjs_text):
    """(plan, originals) of the prefs.js cleanup of one profile. `plan` is
    a list, None for the v0 rule applied when the file is written, or [].
    `userjs_text` is user.js as it was before uninstall stripped it."""
    if record is not None:
        return (prefs_plan_record(record, set(record["owned_prefs"]) | set(record["restore_prefs"])),
                record["prefs_original"])
    pend = ctx["pending"].get(pid)
    if pend is not None:
        return pend["plan"], pend["prefs_original"]
    backup = ctx["state"]["backups"].get(pid)
    if backup is not None and backup["prefs_original"] is not None:
        # state.json lost or corrupt: every pref may have been ours.
        # A pref missing from the originals (a v1.0 backup: the companion
        # prefs) was never recorded, so it is left alone.
        synth = {"prefs_original": backup["prefs_original"]}
        return prefs_plan_record(synth, set(backup["prefs_original"])), backup["prefs_original"]
    ours = block_prefs(userjs_text)
    if ours:
        # Nothing recorded (no backup, or one whose originals an earlier
        # uninstall dropped), but user.js held our block (read before
        # it was stripped): its values in prefs.js are ours, the companion
        # prefs and content-override 2 included (the v0 rule misses them).
        try:
            text = read_optional(os.path.join(path, PREFS_JS)) or ""
        except (OSError, ValueError):
            text = ""
        plan = prefs_plan_lost(text, ours)
        originals = prefs_originals(text, userjs_text)
        # The guessed scope originals go in the originals too: a sync that
        # takes the profile back keeps the same guess (_first_contact_originals).
        originals.update((p, {"value": v}) for p, v in plan if v is not None)
        return plan, originals
    return (None if traces else []), None


PREF_EXT_UUIDS = "extensions.webextensions.uuids"
PREF_EXT_MIGRATED = "extensions.webextensions.ExtensionStorageIDB.migrated." + COMPANION_ID
_EXT_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# The companion's storage folders under <profile>/storage/default/.
_EXT_STORAGE = ("moz-extension+++%s^userContextId=4294967295", "moz-extension+++%s")


def companion_residues(text):
    """(`text` (prefs.js) without what the browser recorded for the
    companion add-on, its moz-extension uuid or None). Only our own key
    leaves extensions.webextensions.uuids: the other add-ons' stay."""
    current = parse_prefs(text)
    plan = []
    uuid = None
    if PREF_EXT_MIGRATED in current:
        plan.append((PREF_EXT_MIGRATED, None))
    raw = current.get(PREF_EXT_UUIDS)
    if raw is not None:
        try:
            inner = json.loads(raw)
            doc = json.loads(inner, object_pairs_hook=collections.OrderedDict) \
                if isinstance(inner, str) else None
        except (ValueError, RecursionError):
            doc = None
        if isinstance(doc, dict) and COMPANION_ID in doc:
            value = doc.pop(COMPANION_ID)
            if isinstance(value, str) and _EXT_UUID.fullmatch(value):
                uuid = value
            literal = json.dumps(json.dumps(doc, separators=(",", ":"), ensure_ascii=False),
                                 ensure_ascii=False)
            plan.append((PREF_EXT_UUIDS, literal))
    return (prefs_restore(text, plan) if plan else text), uuid


def companion_residues_in(path):
    """The prefs.js text of the profile `path` when it holds a record of
    the companion add-on (companion_residues), else None (unreadable too)."""
    try:
        text = read_optional(os.path.join(path, PREFS_JS))
    except (OSError, ValueError):
        return None
    return text if text is not None and companion_residues(text)[0] != text else None


def companion_storage_remove(path, uuid):
    """Remove the companion's storage folders of the profile `path`."""
    for name in _EXT_STORAGE:
        folder = os.path.join(path, "storage", "default", name % uuid)
        if os.path.isdir(folder) and not os.path.islink(folder):
            shutil.rmtree(folder, ignore_errors=True)


_RUNTIME_ENTRY = re.compile(r"host-[0-9]{1,10}\.sock|(?:active|ack)-[0-9]{1,10}\.json")
RUNTIME_REMOVE_TRIES = 3


def runtime_remove(env):
    """Remove the runtime folder ($XDG_RUNTIME_DIR/<RUNTIME_DIR_NAME>) and
    the files of ours in it. True when it was there and went."""
    rdir = runtime_dir(env)
    if rdir is None or not _runtime_dir_ours(rdir):
        return False
    # A live host may write a file between the listing and the rmdir (it
    # sees its socket gone at its next write and stops): list again.
    for attempt in range(RUNTIME_REMOVE_TRIES):
        try:
            names = os.listdir(rdir)
        except OSError:
            return False
        for name in names:
            if _RUNTIME_ENTRY.fullmatch(name) or (name.startswith(TMP_PREFIX) and name.endswith(TMP_SUFFIX)):
                try:
                    os.unlink(os.path.join(rdir, name))
                except OSError:
                    pass
        try:
            os.rmdir(rdir)
        except OSError as exc:
            if exc.errno != errno.ENOTEMPTY or attempt == RUNTIME_REMOVE_TRIES - 1:
                return False
            continue
        return True
    return False


def _clean_prefs_now(path, plan, warnings=None, family=None, pid=None):
    """Apply `plan` (None: the v0 rule, decided on the current file) to the
    prefs.js of a free profile. Returns (changed, done). Raises OSError."""
    prefs_path = os.path.join(path, PREFS_JS)
    text = read_optional(prefs_path)
    if text is None:
        return False, True
    if plan is None:
        plan = prefs_plan_v0(text)
    new, uuid = companion_residues(prefs_restore(text, plan))
    if uuid is not None:
        companion_storage_remove(path, uuid)
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
    # An uninstall job whose pending file could not be written ("unrecorded")
    # has no file for a sync to drop: a sync that took the profile back
    # (plugin enabled again) cancels it through its state.json record.
    unrecorded = job.get("unrecorded", False)
    fd = None
    if job["pending"] or unrecorded:
        try:
            fd = _cleaner_lock(sdir)
        except OSError:
            if job["pending"]:
                return "drop"
            # No state folder to lock (none to sync into): read it unlocked.
        else:
            if fd is None:
                return "wait"
    try:
        if job["pending"]:
            record = pending_load(sdir).get(job["pid"])
            if record is None:
                return "drop"
        elif unrecorded and _state_stamp(sdir) != job.get("state_stamp") \
                and _state_has_profile(sdir, job["pid"]):
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


def _state_stamp(sdir):
    """(inode, mtime, size) of `sdir`/state.json, None when missing. A sync
    replaces the file (os.replace), so a new stamp means it wrote it."""
    try:
        st = os.stat(os.path.join(sdir, STATE_FILE))
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def _state_has_profile(sdir, pid):
    """True when a sync recorded `pid` in `sdir`/state.json (a newer state
    counts: a newer version synced it). The records an unfinished
    uninstall keeps are saved with "synced" false and do not count."""
    try:
        state, _ = state_load(sdir, [])
    except StateNewer:
        return True
    return pid in state["profiles"] and state["synced"]


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


def _clean_prefs_wait(sdir, jobs, env, wake=None):
    """Poll each job ({pid, path, plan, pending}) until its browser is
    closed, re-check right before writing, then clean its prefs.js. A job
    with a pending/<pid>.json file runs under the state lock and removes
    that file once done; when the file is gone (a sync took the profile
    back) the job is dropped; an "unrecorded" job is dropped when a sync
    wrote state.json since the uninstall and recorded its profile. Gives
    up after $BG_POLL_MAX seconds, leaving the pending files for a later
    uninstall or clean-prefs. `wake` is the
    read end of the signal wakeup pipe of the detached cleaner: on SIGTERM
    or SIGHUP (logout, shutdown: the browser closes on the same signal) it
    polls every TERM_POLL_INTERVAL for $BG_TERM_GRACE seconds at most, then
    exits. Needs no file of its own (works from `python3 -I -c`)."""
    interval = env_seconds(env, ENV_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    deadline = time.monotonic() + env_seconds(env, ENV_POLL_MAX, DEFAULT_POLL_MAX)
    waiting = list(jobs)
    tidy = next((job["tidy"] for job in jobs if "tidy" in job), None)
    while waiting or tidy is not None:
        waiting = [job for job in waiting if _clean_job(sdir, job) == "wait"]
        if not waiting and tidy is not None and _tidy_after_jobs(sdir, tidy):
            tidy = None
        now = time.monotonic()
        if (not waiting and tidy is None) or now >= deadline:
            break
        if wake is None:
            time.sleep(interval)
        elif _wait_signal(wake, min(interval, deadline - now)):
            interval = TERM_POLL_INTERVAL
            grace = env_seconds(env, ENV_TERM_GRACE, DEFAULT_TERM_GRACE)
            deadline = min(deadline, time.monotonic() + grace)


def _wait_signal(fd, timeout):
    """Wait up to `timeout` seconds for a byte on the non-blocking signal
    wakeup pipe `fd`; drain it. True when a signal came."""
    import select
    if not select.select([fd], [], [], max(timeout, 0))[0]:
        return False
    try:
        while os.read(fd, 64):
            pass
    except OSError:
        pass  # EAGAIN: drained
    return True


def _tidy_after_jobs(sdir, created_dirs):
    """Under the state lock, remove what an uninstall left for jobs whose
    pending file could not be written: the empty pending/ folder, then the
    state folder and `created_dirs` (_tidy_state_dir). False while another
    command holds the lock."""
    try:
        fd = _cleaner_lock(sdir)
    except OSError:
        return True  # the state folder is gone: nothing left to tidy
    if fd is None:
        return False
    try:
        _rmdir_quiet(pending_folder(sdir))
        _tidy_state_dir(sdir, created_dirs)
    finally:
        os.close(fd)
    return True


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


def _term_wakeup():
    """Catch SIGTERM and SIGHUP in the detached cleaner: each one writes a
    byte to a non-blocking pipe instead of killing it. Returns the read end
    (for _clean_prefs_wait), or None when the pipe cannot be made."""
    import signal
    try:
        rfd, wfd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    signal.set_wakeup_fd(wfd, warn_on_full_buffer=False)
    for signum in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, lambda *_: None)
    return rfd


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
        _clean_prefs_wait(sdir, jobs, env, _term_wakeup())
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


def sync_settings_remove(env):
    """Remove $XDG_RUNTIME_DIR/<SYNC_SETTINGS_NAME> when it is a regular
    file of this user: the settings of a sync that never ran (the daemon
    went within the debounce). True when it went."""
    base = env.get("XDG_RUNTIME_DIR") or ""
    if not os.path.isabs(base):
        return False
    path = os.path.join(os.path.normpath(base), SYNC_SETTINGS_NAME)
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            return False
        os.unlink(path)
    except OSError:
        return False
    return True


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

        removed, restored, pending, jobs, xpi_removed = [], [], [], [], []
        unfinished = set()
        deferred = {}
        for pid, (path, family) in targets.items():
            record = state["profiles"].get(pid)
            before = len(warnings)
            try:
                try:
                    userjs_text = read_optional(os.path.join(path, USER_JS))
                except (OSError, ValueError):
                    userjs_text = None
                r, s, done, traces = _uninstall_profile(ctx, pid, path, family)
                try:
                    comp = record["companion"] if record is not None else None
                    backup = state["backups"].get(pid)
                    if companion_remove(path, comp):
                        xpi_removed.append(pid)
                        if comp is None:
                            # No record says who made extensions/: ours
                            # was in it, so it goes once empty.
                            _rmdir_quiet(os.path.dirname(companion_xpi_path(path)))
                    if comp is None and backup is not None and backup["ext_dir"]:
                        _rmdir_quiet(os.path.dirname(companion_xpi_path(path)))
                except OSError as exc:
                    warnings.append(make_warning(WARN_WRITE_FAILED, "%s not removed: %s"
                                                 % (COMPANION_XPI, _oserror_text(exc)), family, pid))
                    done = False
                if record is not None and record["companion"] is not None \
                        and not record["companion"]["ext_dir"]:
                    record["companion"] = None
                plan, originals = _uninstall_plan(ctx, pid, path, record, traces, userjs_text)
                if plan == []:
                    # Only the companion's residues, if any: now, or once
                    # the browser closes (it rewrites prefs.js).
                    residues = None
                    if lock_state(path) == LOCK_FREE:
                        changed, ok = _clean_prefs_now(path, [], warnings, family, pid)
                        s = s or changed
                        done = done and ok
                    else:
                        residues = companion_residues_in(path)
                    if residues is not None:
                        # No pref of ours (no record, no trace): what
                        # prefs.js holds is the user's, should a sync take
                        # the profile back meanwhile.
                        if originals is None:
                            originals = prefs_originals(residues, None)
                        deferred[pid] = (path, [], originals)
                        pending.append(pid)
                        if not r:
                            s = True
                else:
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
        # The native host goes now, whatever the branch: no manifest is left
        # to start the wrapper (state.json lists every one we wrote).
        native_host_removed = native_remove(env, state, sdir, warnings)
        runtime_removed = runtime_remove(env)
        sync_settings_remove(env)

        # Deferred prefs.js cleanups are recorded in pending/<pid>.json
        # so their originals outlive the state and a killed cleaner.
        created = []
        if deferred and not state_existed:
            try:
                created = make_dirs_tracked(sdir)
            except OSError:
                created = []
        # Every record of the state folders: the state's (or STATE_DIRS'),
        # the earlier pending files' (a second uninstall, a cleaner that
        # gave up) and the folders made just now; a state.json saved below
        # keeps them all.
        created_dirs = set(state["created_dirs"]) | set(created)
        for record in ctx["pending"].values():
            created_dirs.update(record["created_dirs"])
        created_dirs = sorted(created_dirs)
        state["created_dirs"] = list(created_dirs)
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
            job = {"pid": pid, "path": path, "plan": plan, "pending": has_file}
            if not has_file:
                # No record to drop at the end: the cleaner tidies what it
                # can once its jobs are over, and drops the job if a sync
                # records the profile again first. The profile stays
                # unfinished, so state.json keeps its record and backup (a
                # later uninstall removes them): a sync that takes it back
                # finds the user's originals there.
                job["tidy"] = created_dirs
                job["unrecorded"] = True
                unfinished.add(pid)
            jobs.append(job)
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
                        state["backups"][pid]["companion_removed"] = False
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
            # What the uninstall left in state.json (a stale record when the
            # state folder could not be written): only a later write by a
            # sync cancels an unrecorded job.
            stamp = _state_stamp(sdir)
            for job in jobs:
                if job.get("unrecorded"):
                    job["state_stamp"] = stamp
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
        "xpi_removed": xpi_removed,
        "native_host_removed": native_host_removed,
        "runtime_removed": runtime_removed,
        "warnings": warnings,
    })
    return EXIT_OK


def _drop_meta_originals(sdir, pid, warnings):
    """Drop the prefs originals and the companion removal mark of a backup
    an uninstall keeps."""
    meta = os.path.join(backup_folder(sdir, pid), BACKUP_META)
    try:
        doc = json.loads(read_text(meta))
        if isinstance(doc, dict) and (doc.get("prefs_original") is not None
                                      or "companion_removed" in doc):
            doc["prefs_original"] = None
            doc.pop("companion_removed", None)
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
        if plan != [] or pid in pendings:  # [] still clears the companion's residues
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
# Contract for the daemon on the niri rule (held while a running browser
# has glass loaded): niri.rule true while glass.active is false
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
    folder `path` are those of `record`'s last sync (applied_hash, the
    profile's own: see profile_output). An exclusion list applied live
    keeps it true: the files are still those of that sync."""
    if record is None or record["applied_hash"] is None:
        return False
    try:
        # Our own files: the content CSS grows with the exclusion list.
        chrome = read_text(os.path.join(path, CHROME_DIR, CHROME_CSS_NAME), DATA_READ_LIMIT)
        content = read_text(os.path.join(path, CHROME_DIR, CONTENT_CSS_NAME), DATA_READ_LIMIT)
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
    return applied_hash_of(chrome, content, block) == record["applied_hash"]


def glass_holders(state):
    """[(pid, record, lock state)] of the running profiles that still have
    glass loaded (read-only twin of _h1_rule_needed: LOCK_UNKNOWN counts
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
    enabled = settings["liveControl"]
    rdir = runtime_dir(env)

    browsers = []
    by_key = {}
    folders = {}
    states = []
    for profile in find_profiles(env):
        folders[profile.id] = profile.path
        lstate, key = lock_instance(profile.path)
        running = lstate == LOCK_RUNNING
        start = process_start(key) if running else None
        record = state["profiles"].get(profile.id)
        applied = profile_applied(profile.path, record)
        # Files written after the start that this browser applied live (the
        # exclusion list, acknowledged by its host, nothing written since)
        # need no restart.
        restart = (start is not None and files_changed_since(profile.path, start)
                   and not (applied and live_applied(profile.path, record, key)))
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
        comp = record["companion"] if record is not None else None
        cstate = companion_state(profile.path, profile.family, profile.variant, comp, enabled,
                                 comp is not None and comp["dropped"] is not None, env=env)
        if cstate in COMPANION_DEPOSITED and running \
                and companion_outdated(rdir, instance_browser_pid(key)):
            cstate = COMPANION_OUTDATED
        states.append(cstate)
        group["profiles"].append({
            "id": profile.id, "name": profile.name, "path": tilde_path(profile.path, env),
            "default": bool(profile.default), "running": running, "restart_needed": restart,
            "applied": applied, "companion": cstate,
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
    live = companion_host_pids(rdir)
    hosts = len(live)
    if not enabled:
        summary = "off"
    elif any(not companion_outdated(rdir, pid) for pid in live):
        # A host whose add-on speaks another protocol relays nothing: the
        # browser needs one more restart (waiting_restart).
        summary = "connected"
    elif any(st in COMPANION_DEPOSITED or st == COMPANION_OUTDATED for st in states):
        summary = "waiting_restart"
    elif COMPANION_REMOVED in states:
        summary = "removed"
    else:
        summary = "unavailable"
    doc = collections.OrderedDict([
        ("version", VERSION),
        ("glass", glass),
        ("niri", niri),
        ("companion", collections.OrderedDict([
            ("enabled", enabled), ("state", summary), ("hosts", hosts),
            ("manifest", _manifest_is_ours(native_manifest_path(env)))])),
        ("restart_needed", bool(held) or any(b["restart_needed"] for b in browsers)),
        ("browsers", browsers),
        ("warnings", warnings),
    ])
    last = state.get("last_sync")
    return doc, settings, folders, list(last["warning_codes"]) if last else []


def companion_host_pids(rdir):
    """The browser pids whose native host has a socket in the runtime
    folder `rdir` and a live process (never connected to: status stays
    read-only)."""
    if rdir is None or not _runtime_dir_ours(rdir):
        return []
    try:
        names = os.listdir(rdir)
    except OSError:
        return []
    return sorted(int(m.group(1)) for m in map(_HOST_SOCKET.fullmatch, names)
                  if m and os.path.isdir("/proc/%s" % m.group(1)))


def companion_outdated(rdir, bpid):
    """True when the host of the running browser process `bpid` says the
    add-on speaks another protocol (active-<pid>.json "outdated")."""
    if rdir is None or bpid is None or not _runtime_dir_ours(rdir) \
            or not os.path.isdir("/proc/%d" % bpid):
        return False
    try:
        doc = json.loads(read_text(runtime_file(rdir, "active", bpid), limit=65536))
    except (OSError, ValueError, RecursionError):
        return False
    return isinstance(doc, dict) and doc.get("outdated") is True


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
        "companion: %s (hosts %d, manifest %s, profiles %s)" % (
            doc["companion"]["state"], doc["companion"]["hosts"], _yes(doc["companion"]["manifest"]),
            ", ".join("%s %d" % (st, n) for st, n in sorted(collections.Counter(
                p["companion"] for p in profiles).items())) or "none"),
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


def cmd_native_host(args, env):
    """Run by the browser (through the wrapper): native messaging frames on
    stdin and stdout, never a JSON line (see section native). The browser
    process is the parent: the wrapper exec()s python3."""
    return native_host(env, args.data, sys.stdin.buffer.raw, sys.stdout.buffer, os.getppid())


NIRI_IPC_TIMEOUT = 1.0          # seconds for niri to list its windows
NIRI_REPLY_MAX = 16 * 1024 * 1024


def niri_window(window_id, env):
    """The niri window `window_id` (a dict: title, app_id, pid...) as niri's
    IPC socket ($NIRI_SOCKET) lists it, or None when niri has no such
    window. Raises OSError or ValueError when niri cannot be asked."""
    path = env.get("NIRI_SOCKET")
    if not path:
        raise OSError(errno.ENOENT, "NIRI_SOCKET is not set")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(NIRI_IPC_TIMEOUT)
        sock.connect(path)
        sock.sendall(b'"Windows"\n')
        line = _socket_line(sock, NIRI_REPLY_MAX, NIRI_IPC_TIMEOUT)
    if line is None:
        raise ValueError("no answer from niri")
    reply = json.loads(line.decode("utf-8"))
    ok = reply.get("Ok") if isinstance(reply, dict) else None
    windows = ok.get("Windows") if isinstance(ok, dict) else None
    if not isinstance(windows, list):
        raise ValueError("unexpected answer from niri")
    for w in windows:
        if isinstance(w, dict) and w.get("id") == window_id and not isinstance(w.get("id"), bool):
            return w
    return None


def cmd_active_site(args, env):
    """The answers of the active_site spec, errors included, exit 0; exit 1
    only when the public suffix list cannot be read, or niri cannot be asked
    for the title of --window-id."""
    folder = args.data or os.path.join(xdg_dir("XDG_CONFIG_HOME", env), DATA_DIR_REL)
    title = args.title
    if args.window_id is not None:
        try:
            window = niri_window(args.window_id, env)
        except (OSError, ValueError) as exc:  # UnicodeDecodeError, JSONDecodeError included
            return _fail("niri window list unavailable: %s" % (
                _oserror_text(exc) if isinstance(exc, OSError) else exc))
        if window is None:  # closed meanwhile
            _print_json({"error": "no_browser"})
            return EXIT_OK
        title = window.get("title") if isinstance(window.get("title"), str) else None
    try:
        doc = active_site(args.pid, args.app_id, title, env, lambda: psl_load(folder))
    except PslError as exc:
        return _fail("public suffix list unavailable: %s" % exc)
    _print_json(doc)
    return EXIT_OK


COMMANDS = {
    "sync": cmd_sync,
    "status": cmd_status,
    "uninstall": cmd_uninstall,
    "clean-prefs": cmd_clean_prefs,
    "report": cmd_report,
    "sites": cmd_sites,
    "native-host": cmd_native_host,
    "active-site": cmd_active_site,
}


def main(argv=None, env=None):
    env = os.environ if env is None else env
    try:
        args = build_parser().parse_args(argv)
        return COMMANDS[args.command](args, env)
    except UsageError as exc:
        return _fail(str(exc), EXIT_USAGE)
    except KeyboardInterrupt:
        return _fail("interrupted")
    except (OSError, ValueError) as exc:
        return _fail("%s: %s" % (exc.__class__.__name__, getattr(exc, "strerror", None) or exc))


if __name__ == "__main__":
    sys.exit(main())

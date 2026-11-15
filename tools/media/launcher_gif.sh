#!/bin/sh
# The launcher GIF (screenshots/launcher.gif), end to end: step 6 of the
# shot list in capture.sh. It drives the live DMS session, the real
# launcher and the real browserGlass daemon (whose syncs write the real
# browsers' files), so it runs only after `capture.sh save-state`, and it
# always ends with restore.sh, which also puts the browserGlass entry of
# plugin_settings.json back and syncs. The page is shown by a throwaway
# LibreWolf (MEDIA_BROWSER=librewolf, fake HOME) whose companion add-on
# talks to the real daemon through the real $XDG_RUNTIME_DIR.
#
# Usage: MEDIA_DIR=DIR launcher_gif.sh [OUT.gif]   (default screenshots/launcher.gif)
#
# Environment (all optional): MEDIA_OUTPUT (default DP-2), MEDIA_W and
# MEDIA_H (window size, logical px, default 1920 x 960), MEDIA_CROP (ffmpeg
# W:H:X:Y in pixels; default: the window plus MEDIA_CROP_ABOVE pixels above
# it, default 300, where the toasts drop, never above MEDIA_BAR_INSET
# logical px from the top, default 60: the DMS bar stays out), MEDIA_FPS
# (default 8),
# MEDIA_WAIT (seconds for the page, default 6), MEDIA_SYNC_ARGS (extra
# arguments of the throwaway sync, for example "--opacity 0.8").
#
# Sequence (D9: typing through openQuery, the launcher's own display):
#   1. No real browser profile running (a settled status, checked before
#      and after the colour change): the ocean wallpaper and dark mode
#      make the daemon write the real profiles' glass CSS, which a running
#      browser loads only on restart, so its restart toast would show.
#      Do not disturb, idle inhibit, the last (empty) workspace of
#      MEDIA_OUTPUT, the ocean wallpaper, dark mode.
#   2. Throwaway LibreWolf on http://news.glass-demo.test:8765/ (demo page
#      served on 127.0.0.1, the name resolved by the profile's user.js),
#      floated and centred; its native host's socket must show up.
#   3. Frames in the background; openQuery "g", "gs" (the commands),
#      "gs b", "gs blist" (Exclude glass-demo.test); close + glass blist,
#      which is what Enter on that item runs (executeItem closes the
#      launcher, then the daemon's glassCommand path): the page turns opaque
#      live, toast "glass-demo.test excluded". Then "gs unblist", close +
#      glass unblist: the glass comes back. After each command the window
#      must still have the focus and excludedSites must differ from the
#      saved ones by glass-demo.test alone, else the run stops; if the
#      steps end less than 2 s before the frames do, the run stops too.
#   4. compose.sh gif; stop the browser and the server, remove the profile,
#      restore.sh.
# The toasts are in the shell's language: with DMS in French, say so under
# the GIF in the README. Check every frame (MEDIA_DIR/frames/launcher)
# before committing the GIF: no personal data, no other window or tab.
# Two frames come from the real session and need a decision: "g" lists
# the matching installed apps and other plugins' results, and the "gs"
# list shows "Excluded: N sites", N being the real excludedSites count
# (no domain). Drop the run if either is not fit to publish. A run that
# stops early deletes its frames.

set -eu

MEDIA_DIR=${MEDIA_DIR:?set MEDIA_DIR to the folder of capture.sh save-state}
# Absolute: the native manifest names a wrapper under it
MEDIA_DIR=$(cd "$MEDIA_DIR" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
PLUGIN=$(cd "$HERE/../.." && pwd)
STATE="$MEDIA_DIR/state.env"
OUT=${1:-$PLUGIN/screenshots/launcher.gif}
MEDIA_BROWSER=librewolf
MEDIA_OUTPUT=${MEDIA_OUTPUT:-DP-2}
export MEDIA_DIR MEDIA_BROWSER MEDIA_OUTPUT
PORT=8765
URL="http://news.glass-demo.test:$PORT/"
FPS=${MEDIA_FPS:-8}
SECONDS_TOTAL=21

get() {
    grep -m1 "^$1=" "$STATE" 2>/dev/null | cut -d= -f2-
}

plugin_settings=${DMS_PLUGIN_SETTINGS:-$(get PLUGIN_SETTINGS)}
# Refuse without a recorded session: restore.sh needs it, and the saved
# browserGlass entry above all (the run changes it through the daemon).
copy=$(get PLUGIN_SETTINGS_COPY)
if [ ! -r "$STATE" ] || [ -z "$copy" ] || [ ! -r "$copy" ]; then
    echo "launcher_gif.sh: run capture.sh save-state first (no $STATE with a saved browserGlass entry)" >&2
    exit 1
fi

cap() {
    "$HERE/capture.sh" "$@"
}
ipc() {
    dms ipc call "$@" >/dev/null
}
wid=
frames_pid=
server_pid=
cleanup() {
    rc=$?
    set +e
    trap - EXIT INT TERM
    dms ipc call launcher close >/dev/null 2>&1
    if [ -n "$frames_pid" ]; then
        kill "$frames_pid" 2>/dev/null
        wait "$frames_pid" 2>/dev/null
    fi
    # Frames of a run that stopped early may show anything: never kept
    # (after its last screenshot and crops, a second or so)
    if [ "$rc" != 0 ] && [ -e "$MEDIA_DIR/frames/launcher" ]; then
        sleep 2
        rm -rf "${MEDIA_DIR:?}/frames/launcher"
    fi
    cap stop
    if [ -n "$server_pid" ]; then
        kill "$server_pid" 2>/dev/null
        wait "$server_pid" 2>/dev/null
    fi
    if port_busy; then
        echo "launcher_gif.sh: something still listens on 127.0.0.1:$PORT" >&2
        rc=1
    fi
    rm -rf "${MEDIA_DIR:?}/home"/.librewolf
    if sh "$HERE/restore.sh" "$STATE"; then
        exit "$rc"
    fi
    exit 1
}
port_busy() {
    python3 -I -c 'import socket, sys
s = socket.socket()
s.settimeout(1)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)' "$PORT"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# The run's window must be the focused one: the glass commands act on the
# window in focus, and anything else would exclude a real site.
require_focus() {
    now=$(niri msg -j focused-window | python3 -I -c 'import json, sys
w = json.load(sys.stdin)
print(w["id"] if w else "")')
    if [ "$now" != "$wid" ]; then
        echo "launcher_gif.sh: the throwaway window lost the focus; stopping" >&2
        exit 1
    fi
}
# excludedSites against the saved entry: "added" (glass-demo.test alone
# more) or "same"; the answer names no domain. DMS saves the file a moment
# after the command: wait for it (at most 4 s).
require_excluded() {
    n=0
    until [ "$(python3 -I -B "$HERE/plugin_settings.py" excluded "$plugin_settings" "$copy" glass-demo.test)" = "$1" ]; do
        n=$((n + 1))
        if [ $n -ge 16 ]; then
            echo "launcher_gif.sh: excludedSites is not '$1' against the saved entry; stopping" >&2
            exit 1
        fi
        sleep 0.25
    done
}

# "yes" when the daemon's status lists no running real browser profile.
# The IPC answers with the last status and asks for a fresh one: ask until
# two answers in a row agree (at most 10 s), and an error or a document
# without a browsers list is a "no".
no_real_browser() {
    prev=
    n=0
    while :; do
        now=$(dms ipc call browserGlass status 2>/dev/null | python3 -I -c 'import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(print("no"))
if not isinstance(d, dict) or "error" in d or not isinstance(d.get("browsers"), list):
    sys.exit(print("no"))
running = [p for b in d["browsers"] for p in b.get("profiles", []) if p.get("running")]
print("no" if running or d.get("restart_needed") else "yes")')
        [ "$now" = "$prev" ] && break
        n=$((n + 1))
        [ $n -lt 10 ] || break
        prev=$now
        sleep 1
    done
    [ "$now" = yes ] && [ "$now" = "$prev" ]
}
require_no_real_browser() {
    if ! no_real_browser; then
        echo "launcher_gif.sh: a real browser profile is running (or no settled status): close every browser during the capture" >&2
        exit 1
    fi
}

# 1. The session. No restart toast in the GIF: the colour change below
#    rewrites the real profiles' glass CSS, which a running browser loads
#    only on restart, so no real browser profile may run.
require_no_real_browser
if port_busy; then
    echo "launcher_gif.sh: 127.0.0.1:$PORT is in use (an old demo server?)" >&2
    exit 1
fi

niri msg action power-on-monitors
ipc notifications enableDoNotDisturbIndefinitely
ipc inhibit enable
niri msg action focus-monitor "$MEDIA_OUTPUT"
idx=$(niri msg -j workspaces | python3 -I -c 'import json, sys
out = sys.argv[1]
ws = [w for w in json.load(sys.stdin) if w["output"] == out and w["active_window_id"] is None]
print(max(w["idx"] for w in ws) if ws else "")' "$MEDIA_OUTPUT")
[ -n "$idx" ] || { echo "launcher_gif.sh: no empty workspace on $MEDIA_OUTPUT" >&2; exit 1; }
niri msg action focus-workspace "$idx"
sh "$HERE/gen_wallpaper.sh" "$MEDIA_DIR/wallpapers" ocean >/dev/null
ipc wallpaper set "$MEDIA_DIR/wallpapers/wallpaper-ocean.png"
ipc theme dark
sleep 3
# A browser started meanwhile would now wait for a restart
require_no_real_browser

# 2. The throwaway browser and its page
cap profile >/dev/null
# Not through cap(): $! is then the process that execs the server
"$HERE/capture.sh" serve "$PORT" >"$MEDIA_DIR/server.log" 2>&1 &
server_pid=$!
# The opacity comes from the niri rules of LibreWolf (MEDIA_SYNC_ARGS, for
# example "--opacity 0.8", forces one): without glass the GIF shows nothing.
# shellcheck disable=SC2086 # word splitting of the sync arguments is wanted
glass_on=$(cap glass --settings "$(cat "$HERE/demo-settings.json")" ${MEDIA_SYNC_ARGS:-} \
    | python3 -I -c 'import json, sys
print(str(json.load(sys.stdin).get("glass")).lower())')
if [ "$glass_on" != true ]; then
    echo "launcher_gif.sh: no glass for the throwaway LibreWolf (no niri opacity rule?): set MEDIA_SYNC_ARGS=\"--opacity 0.8\"" >&2
    exit 1
fi
cap browser "$URL"
n=0
until wid=$(cap window) && [ -n "$wid" ]; do
    n=$((n + 1))
    [ $n -lt 60 ] || { echo "launcher_gif.sh: no browser window" >&2; exit 1; }
    sleep 0.5
done
cap place "${MEDIA_W:-1920}" "${MEDIA_H:-960}"
# The host's socket, named after the browser's pid, in the real runtime dir
host_up() {
    for pid in $(cap pids); do
        [ -S "${XDG_RUNTIME_DIR:?}/browserGlass/host-$pid.sock" ] && return 0
    done
    return 1
}
n=0
until host_up; do
    n=$((n + 1))
    [ $n -lt 40 ] || { echo "launcher_gif.sh: the companion's native host did not start" >&2; exit 1; }
    sleep 0.5
done
sleep "${MEDIA_WAIT:-6}"
# Alone on its workspace
others=$(niri msg -j windows | python3 -I -c 'import json, sys
wins = json.load(sys.stdin)
mine = [w for w in wins if str(w["id"]) == sys.argv[1]][0]
print(sum(1 for w in wins if w["workspace_id"] == mine["workspace_id"] and w is not mine))' "$wid")
[ "$others" = 0 ] || { echo "launcher_gif.sh: other windows on the workspace" >&2; exit 1; }
require_focus

# 3. The frames and the launcher
# The crop: MEDIA_CROP, else capture.sh frames' default (the window and
# the toast strip above it, below the bar)
"$HERE/capture.sh" frames launcher "$SECONDS_TOTAL" "$FPS" &
frames_pid=$!
frames_start=$(date +%s)
sleep 1.5
ipc launcher openQuery "g"
sleep 0.5
ipc launcher openQuery "gs"
sleep 2
ipc launcher openQuery "gs b"
sleep 0.6
ipc launcher openQuery "gs blist"
sleep 2.2
ipc launcher close
sleep 0.3
require_focus
ipc browserGlass glass blist
require_excluded added
require_focus
sleep 3
ipc launcher openQuery "gs unblist"
sleep 2.2
ipc launcher close
sleep 0.3
require_focus
ipc browserGlass glass unblist
require_excluded same
require_focus
# The last step must be in the frames, with a hold after it
if [ $(($(date +%s) - frames_start)) -gt $((SECONDS_TOTAL - 2)) ]; then
    echo "launcher_gif.sh: the steps overran the ${SECONDS_TOTAL} s of frames (the unblist would be cut); stopping" >&2
    exit 1
fi
wait "$frames_pid"
frames_pid=

# 4. The GIF, then everything back (cleanup)
sh "$HERE/compose.sh" gif "$MEDIA_DIR/frames/launcher" "$OUT"

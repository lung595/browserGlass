#!/bin/sh
# Helpers for the screenshot run (see CONTRIBUTING.md, "Screenshots").
# Everything lives under $MEDIA_DIR (a throwaway folder); the real browser
# profiles and the real browserGlass state are never touched:
#   $MEDIA_DIR/home      fake HOME of the throwaway browser and of the sync
#   $MEDIA_DIR/media-profile  throwaway Firefox profile
#   $MEDIA_DIR/www       served copy of demo/ (+ the generated fallback clip)
#   $MEDIA_DIR/shots     raw window captures
#
# Usage: MEDIA_DIR=DIR capture.sh COMMAND [ARGS]
#   save-state [--force]    record the live session in $MEDIA_DIR/state.env
#                           (+ copies in $MEDIA_DIR/orig) for restore.sh;
#                           refuses to overwrite an earlier record
#   profile                 create the throwaway profile (user.js, en-US)
#   clip                    generate the fallback clip www/clip.webm
#   serve PORT              serve www/ on 127.0.0.1:PORT (foreground)
#   glass [SYNC ARGS]       browserglass.py sync --profile <profile> with an
#                           isolated state; DMS colours and rules are copied
#                           read-only from the live session
#   browser URL...          start the throwaway browser (background)
#   stop                    stop the throwaway browser
#   window                  print the niri id of the throwaway browser window
#   take NAME "SYNC ARGS" URL...   sync + restart + place + shot
#   place [W H]             float it on $MEDIA_OUTPUT (default DP-2), W x H
#                           (place and shot act on window $MEDIA_WID if set)
#   shot NAME               capture the focused window to shots/NAME.png
#   crop-settings           cut shots/settings-tall.png into set-status,
#                           set-appearance and set-sites (SETTINGS_CROPS)
#   hold PROFILE_DIR        hold the fcntl lock of PROFILE_DIR/.parentlock
#                           (foreground) the way a running browser does
#
# Shot list (the run behind screenshots/; restore.sh undoes every step):
#   0. capture.sh save-state; restore.sh --dry-run "$MEDIA_DIR/state.env".
#      Do not disturb on, idle inhibit on, an empty workspace on DP-2.
#      gen_wallpaper.sh "$MEDIA_DIR/wallpapers"; clip; profile;
#      serve 8765 (in the background).
#   1. Open the demo as http://localhost:8765/ (not 127.0.0.1: the video
#      embed refuses to play without a proper host name). URLS below:
#        DEMO=http://localhost:8765/
#        WIKI=https://en.wikipedia.org/wiki/Stained_glass
#        DOCS=https://docs.python.org/3/   (excluded in demo-settings.json)
#   2. dms ipc call wallpaper set <wallpapers/wallpaper-ocean.png>, dark
#      mode, MEDIA_SETTINGS=tools/media/demo-settings.json, then
#        take hero-after - $DEMO          take hero-before --off $DEMO
#        take color-ocean - $DEMO
#        take opacity-90 "--opacity 0.9" $DEMO   (and 0.7, 0.5)
#        take site-wiki - $WIKI           take site-excluded - $DOCS
#      wallpaper-sunset / wallpaper-forest: take color-sunset / color-forest
#      - $DEMO. Light mode (dms ipc call theme light) and a copy of
#      demo-settings.json with "isLight": true: take mode-light - $DEMO.
#   3. Settings: niri msg output DP-2 scale 1; dms ipc call settings
#      openWith plugin:browserGlass; MEDIA_WID=<settings window> place
#      1100 2120; shot settings-tall; crop-settings. Scale back to 1.5.
#   4. Widget: add {"id": "browserGlass", "enabled": true} first in the
#      bar's rightWidgets (settings.json, restored by restore.sh), open its
#      popout (dms ipc call widget toggle browserGlass), capture DP-2 with
#      dms screenshot output and crop the bar corner + popout to
#      widget-raw.png (ffmpeg crop=590:578:3250:0 of the 3840x2160 shot). Restart badge: hold one profile of the real browser
#      (its folder from browserglass.py status --json; nothing is written
#      there) while dms ipc call browserGlass toggle runs twice (off, on):
#      the files change under a "running" browser, the badge and the toast
#      show; crop the same corner to widget-restart.png (590:612:3250:0,
#      the popout is one row taller), stop hold (Ctrl-C, or kill the
#      python3 it execs), then dms ipc call browserGlass sync. Settings or
#      widget QML changed since the shell started: dms restart first.
#   5. compose.sh "$MEDIA_DIR/shots" <wallpaper-ocean.png> screenshots;
#      restore.sh "$MEDIA_DIR/state.env"; stop; kill the server; remove
#      $MEDIA_DIR/media-profile.

set -eu

MEDIA_DIR=${MEDIA_DIR:?set MEDIA_DIR to a throwaway folder}
HERE=$(cd "$(dirname "$0")" && pwd)
PLUGIN=$(cd "$HERE/../.." && pwd)
FAKE_HOME="$MEDIA_DIR/home"
PROFILE="$MEDIA_DIR/media-profile"
WWW="$MEDIA_DIR/www"
SHOTS="$MEDIA_DIR/shots"
REAL_CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}
REAL_CACHE=${XDG_CACHE_HOME:-$HOME/.cache}
FIREFOX_BIN=${BG_FIREFOX:-/usr/lib64/firefox/firefox}

cmd=${1:-}
[ $# -gt 0 ] && shift

# Environment of the throwaway browser: built from scratch, fake HOME.
browser_env() {
    env -i \
        HOME="$FAKE_HOME" \
        PATH=/usr/local/bin:/usr/bin:/bin \
        LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 \
        XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
        WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" \
        DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
        XDG_CONFIG_HOME="$FAKE_HOME/.config" \
        XDG_CACHE_HOME="$FAKE_HOME/.cache" \
        XDG_DATA_HOME="$FAKE_HOME/.local/share" \
        XDG_STATE_HOME="$FAKE_HOME/.local/state" \
        MOZ_ENABLE_WAYLAND=1 \
        MOZ_CRASHREPORTER_DISABLE=1 \
        "$@"
}

case "$cmd" in
save-state)
    # Everything restore.sh puts back, read before the first change.
    orig="$MEDIA_DIR/orig"
    state="$MEDIA_DIR/state.env"
    # A second run after a change would record the changed session and
    # overwrite the only copy of the original: run restore.sh first.
    if [ "${1:-}" != "--force" ] && { [ -e "$state" ] || [ -e "$orig" ]; }; then
        echo "save-state: $state or $orig exists (restore.sh first, or --force)" >&2
        exit 1
    fi
    mkdir -p "$orig"
    cp -p "$REAL_CONFIG/niri/dms/windowrules.kdl" "$orig/windowrules.kdl"
    cp -p "$REAL_CONFIG/dms/settings.json" "$orig/settings.json"
    cp -p "$REAL_CACHE/dms/dms-colors.json" "$orig/dms-colors.json"
    {
        echo "WALLPAPER=$(dms ipc call wallpaper get)"
        outs=$(niri msg -j outputs | python3 -I -c 'import json, sys; print(" ".join(sorted(json.load(sys.stdin))))')
        echo "WALLPAPER_OUTPUTS=$outs"
        for out in $outs; do
            echo "WALLPAPER_$out=$(dms ipc call wallpaper getFor "$out")"
        done
        echo "THEME_MODE=$(dms ipc call theme getMode)"
        echo "BLUR_ENABLED=$(dms ipc call settings get blurEnabled)"
        echo "DND=$(dms ipc call notifications getDoNotDisturb)"
        case "$(dms ipc call inhibit status)" in
            *enabled*) echo "IDLE_INHIBIT=true" ;;
            *) echo "IDLE_INHIBIT=false" ;;
        esac
        python3 -I -c 'import json, sys
d = json.load(open(sys.argv[1]))
print("COLORS_MODE=%s" % d["mode"])
print("COLORS_SURFACE=%s" % d["colors"][d["mode"]]["surface"])' "$orig/dms-colors.json"
        echo "WINDOWRULES_COPY=$orig/windowrules.kdl"
        echo "SETTINGS_COPY=$orig/settings.json"
        echo "MEDIA_DIR=$MEDIA_DIR"
        python3 -I -c 'import json, subprocess
msg = lambda a: json.loads(subprocess.check_output(["niri", "msg", "-j", a]))
ws = msg("workspaces")
print("FOCUS_WORKSPACES=" + " ".join("%s:%d" % (w["output"], w["idx"]) for w in ws if w["is_active"]))
print("FOCUS_OUTPUT=" + "".join(w["output"] for w in ws if w["is_focused"]))
win = msg("focused-window")
print("FOCUS_WINDOW=%s" % (win["id"] if win else ""))
outs = msg("outputs")
print("OUTPUT_SCALES=" + " ".join("%s:%s" % (k, outs[k]["logical"]["scale"]) for k in sorted(outs)))'
    } > "$state"
    echo "$state"
    ;;
profile)
    rm -rf "$PROFILE"
    mkdir -p "$PROFILE" "$FAKE_HOME"
    cat > "$PROFILE/user.js" <<'PREFS'
// Throwaway profile for the browserGlass screenshots.
user_pref("intl.locale.requested", "en-US");
user_pref("intl.accept_languages", "en-US, en");
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("startup.homepage_override_url", "");
user_pref("browser.startup.page", 0);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.sessionstore.max_resumed_crashes", 0);
user_pref("toolkit.startup.max_resumed_crashes", -1);
user_pref("toolkit.startup.recent_crashes", 0);
user_pref("browser.startup.couldRestoreSession.count", -1);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.toolbars.bookmarks.visibility", "never");
user_pref("identity.fxaccounts.enabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("app.normandy.enabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("app.update.auto", false);
user_pref("browser.discovery.enabled", false);
user_pref("browser.uitour.enabled", false);
user_pref("extensions.pocket.enabled", false);
user_pref("browser.newtabpage.activity-stream.feeds.topsites", false);
user_pref("browser.newtabpage.activity-stream.feeds.section.topstories", false);
user_pref("browser.newtabpage.activity-stream.showSponsored", false);
user_pref("browser.newtabpage.activity-stream.showSponsoredTopSites", false);
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.addons", false);
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.features", false);
user_pref("browser.messaging-system.whatsNewPanel.enabled", false);
user_pref("messaging-system.rsexperimentloader.enabled", false);
user_pref("browser.vpn_promo.enabled", false);
user_pref("browser.preferences.moreFromMozilla", false);
user_pref("browser.ml.chat.enabled", false);
user_pref("browser.translations.automaticallyPopup", false);
user_pref("sidebar.revamp", false);
user_pref("sidebar.verticalTabs", false);
user_pref("signon.rememberSignons", false);
user_pref("media.autoplay.default", 0);
user_pref("media.autoplay.blocking_policy", 0);
user_pref("browser.download.panel.shown", true);
user_pref("browser.urlbar.suggest.searches", false);
user_pref("browser.tabs.firefox-view", false);
user_pref("media.videocontrols.picture-in-picture.video-toggle.enabled", false);
user_pref("media.videocontrols.picture-in-picture.enabled", false);
PREFS
    # The streaming video embed keeps Firefox's network status bubble up in
    # the bottom-left corner: hide that bubble only. browserglass.py sync
    # adds its own @import above this rule.
    mkdir -p "$PROFILE/chrome"
    printf '%s\n' '#statuspanel { display: none !important; }' > "$PROFILE/chrome/userChrome.css"
    # The pointer may rest over a link: no Wikipedia hover previews.
    printf '%s\n' '.mwe-popups { display: none !important; }' > "$PROFILE/chrome/userContent.css"
    echo "$PROFILE"
    ;;
clip)
    mkdir -p "$WWW"
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc2=s=1280x720:r=30:d=12" \
        -c:v libvpx-vp9 -b:v 1500k -an "$WWW/clip.webm"
    ;;
serve)
    mkdir -p "$WWW"
    cp -r "$HERE/demo/." "$WWW/"
    exec python3 -I -m http.server --bind 127.0.0.1 --directory "$WWW" "${1:-8765}"
    ;;
glass)
    # Isolated sync: fake HOME/XDG dirs; the DMS inputs are copies.
    mkdir -p "$FAKE_HOME/.config/niri/dms" "$FAKE_HOME/.cache/dms"
    cp "$REAL_CONFIG/niri/dms/windowrules.kdl" "$FAKE_HOME/.config/niri/dms/windowrules.kdl"
    cp "$REAL_CACHE/dms/dms-colors.json" "$FAKE_HOME/.cache/dms/dms-colors.json"
    env HOME="$FAKE_HOME" \
        XDG_CONFIG_HOME="$FAKE_HOME/.config" \
        XDG_CACHE_HOME="$FAKE_HOME/.cache" \
        XDG_STATE_HOME="$FAKE_HOME/.local/state" \
        XDG_DATA_HOME="$FAKE_HOME/.local/share" \
        python3 -I "$PLUGIN/browserglass.py" sync --data "$PLUGIN/data" --profile "$PROFILE" "$@"
    ;;
browser)
    mkdir -p "$FAKE_HOME"
    browser_env setsid "$FIREFOX_BIN" -no-remote -profile "$PROFILE" "$@" \
        >"$MEDIA_DIR/browser.log" 2>&1 &
    echo $! > "$MEDIA_DIR/browser.pid"
    ;;
stop)
    # Close the window (a clean quit: no crash counter, no troubleshoot
    # mode prompt), then make sure every process of the profile is gone.
    wid=$("$0" window)
    [ -n "$wid" ] && niri msg action close-window --id "$wid" 2>/dev/null
    n=0
    while [ -n "$("$0" pids)" ] && [ $n -lt 50 ]; do
        sleep 0.2
        n=$((n + 1))
    done
    for sig in TERM KILL; do
        pids=$("$0" pids)
        [ -n "$pids" ] || break
        # shellcheck disable=SC2086
        kill -s "$sig" $pids 2>/dev/null || true
        sleep 1
    done
    rm -f "$MEDIA_DIR/browser.pid"
    ;;
pids)
    # Processes of the throwaway profile: started with -profile, or
    # restarted by Firefox itself (XRE_PROFILE_PATH in the environment).
    python3 -I -c '
import os, sys
prof = sys.argv[1].encode()
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as f:
            cmd = f.read() + b"\0"
        with open("/proc/%s/environ" % pid, "rb") as f:
            env = b"\0" + f.read()
    except OSError:
        continue
    if b"-profile\0" + prof + b"\0" in cmd or b"\0XRE_PROFILE_PATH=" + prof + b"\0" in env:
        print(pid)' "$PROFILE"
    ;;
window)
    # The window whose process runs the throwaway profile.
    pids=$("$0" pids)
    niri msg -j windows | python3 -I -c '
import json, sys
pids = {int(p) for p in sys.argv[1].split()}
for w in json.load(sys.stdin):
    if w.get("pid") in pids:
        print(w["id"])
        break' "$pids"
    ;;
take)
    # take NAME "SYNC ARGS" URL...: re-sync the throwaway profile with the
    # settings of the JSON file $MEDIA_SETTINGS plus SYNC ARGS (for example
    # "--opacity 0.7" or "--off"; "-" for none), restart
    # the browser (it only reads its CSS at start-up), wait for the page
    # ($MEDIA_WAIT seconds), place the window, capture it.
    name=${1:?name}
    sync_args=${2:?sync args}
    shift 2
    "$0" stop
    # shellcheck disable=SC2086 # word splitting of the sync arguments is wanted
    [ "$sync_args" = "-" ] && sync_args=
    "$0" glass --settings "$(cat "${MEDIA_SETTINGS:?settings JSON file}")" $sync_args >/dev/null
    "$0" browser "$@"
    n=0
    until [ -n "$("$0" window)" ] || [ $n -ge 60 ]; do
        sleep 0.5
        n=$((n + 1))
    done
    "$0" place "${MEDIA_W:-1920}" "${MEDIA_H:-960}"
    sleep "${MEDIA_WAIT:-10}"
    "$0" shot "$name"
    ;;
place)
    # Move the throwaway window to $MEDIA_OUTPUT (its active workspace,
    # chosen empty beforehand), float it at W x H logical px, centre it.
    wid=${MEDIA_WID:-$("$0" window)}
    [ -n "$wid" ] || { echo "no throwaway browser window" >&2; exit 1; }
    niri msg action move-window-to-monitor --id "$wid" "${MEDIA_OUTPUT:-DP-2}"
    niri msg action move-window-to-floating --id "$wid"
    niri msg action set-window-width --id "$wid" "${1:-1920}"
    niri msg action set-window-height --id "$wid" "${2:-960}"
    sleep 0.3
    niri msg action center-window --id "$wid"
    niri msg action focus-window --id "$wid"
    ;;
shot)
    # `dms screenshot window` renders the window alone (glass over black):
    # capture its whole output instead, then crop to the window, so the
    # wallpaper shows through and neither the bar nor popups are kept.
    mkdir -p "$SHOTS"
    wid=${MEDIA_WID:-$("$0" window)}
    [ -n "$wid" ] || { echo "no throwaway browser window" >&2; exit 1; }
    geo=$(python3 -I -c '
import json, subprocess, sys
wid = int(sys.argv[1])
msg = lambda *a: json.loads(subprocess.check_output(("niri", "msg", "-j") + a))
win = [w for w in msg("windows") if w["id"] == wid][0]
ws = [w for w in msg("workspaces") if w["id"] == win["workspace_id"]][0]
out = msg("outputs")[ws["output"]]
scale = out["logical"]["scale"]
lay = win["layout"]
x, y = lay["tile_pos_in_workspace_view"]
ox, oy = lay["window_offset_in_tile"]
w, h = lay["window_size"]
r = lambda v: int(round(v * scale))
print(ws["output"], r(w), r(h), r(x + ox), r(y + oy))' "$wid")
    set -- "${1:?name}" $geo
    # Screens may have been powered off by the idle timer.
    niri msg action power-on-monitors
    sleep "${MEDIA_SETTLE:-2}"
    dms screenshot output -o "$2" -d "$SHOTS" --filename ".full-$1.png" --no-clipboard --no-notify >/dev/null
    ffmpeg -hide_banner -loglevel error -y -i "$SHOTS/.full-$1.png" \
        -vf "crop=$3:$4:$5:$6" -frames:v 1 "$SHOTS/$1.png"
    rm -f "$SHOTS/.full-$1.png"
    echo "$SHOTS/$1.png"
    ;;
crop-settings)
    # The settings page, captured whole (shots/settings-tall.png), cut into
    # its sections: "W X Y_STATUS H_STATUS Y_APPEARANCE H_APPEARANCE
    # Y_SITES H_SITES" in pixels (the values of the 1100x2120 capture).
    # shellcheck disable=SC2086 # the list is split on purpose
    set -- ${SETTINGS_CROPS:-760 334 0 548 552 416 976 802}
    w=$1
    x=$2
    shift 2
    for part in status appearance sites; do
        ffmpeg -hide_banner -loglevel error -y -i "$SHOTS/settings-tall.png" \
            -vf "crop=$w:$2:$x:$1" -frames:v 1 "$SHOTS/set-$part.png"
        echo "$SHOTS/set-$part.png"
        shift 2
    done
    ;;
hold)
    # A write lock on .parentlock, as a running browser holds it: status
    # then reports that profile running. Opens the existing file without
    # creating, truncating or writing it; the lock goes with the process.
    exec python3 -I -c '
import fcntl, os, signal, sys
fd = os.open(os.path.join(sys.argv[1], ".parentlock"), os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("holding", flush=True)
signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
signal.sigwait({signal.SIGINT, signal.SIGTERM})' "${1:?profile folder}"
    ;;
*)
    sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac

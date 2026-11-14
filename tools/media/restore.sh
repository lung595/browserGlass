#!/bin/sh
# Restore the live DMS/niri session after a media capture run.
#
# Usage: restore.sh [--dry-run] STATE_FILE   (or BG_MEDIA_STATE=STATE_FILE)
#
# STATE_FILE holds KEY=VALUE lines written before any change (see
# capture.sh save-state): WALLPAPER, WALLPAPER_OUTPUTS, WALLPAPER_<output>,
# THEME_MODE, BLUR_ENABLED, DND, IDLE_INHIBIT, COLORS_MODE, COLORS_SURFACE,
# WINDOWRULES_COPY, SETTINGS_COPY, FOCUS_WORKSPACES (output:idx ...),
# FOCUS_OUTPUT, FOCUS_WINDOW, OUTPUT_SCALES (output:scale ...), MEDIA_DIR
# (the throwaway folder: its wallpapers leave DMS's colour seed cache,
# matugen-seeds.json, whose entries are keyed by image path). Missing
# keys are skipped. Nothing in this script names a real path: every value
# comes from the state file.
#
# --dry-run prints the commands instead of running them, then runs the
# read-only checks. Exit status: 0 when every check passes, 1 otherwise.

set -u

DRY=0
if [ "${1:-}" = "--dry-run" ]; then
    DRY=1
    shift
fi
STATE=${1:-${BG_MEDIA_STATE:-}}
if [ -z "$STATE" ] || [ ! -r "$STATE" ]; then
    echo "usage: restore.sh [--dry-run] STATE_FILE" >&2
    exit 2
fi

get() {
    grep -m1 "^$1=" "$STATE" | cut -d= -f2-
}

run() {
    if [ "$DRY" = 1 ]; then
        echo "would run: $*"
    else
        "$@" >/dev/null 2>&1 || echo "warning: failed: $*" >&2
    fi
}

CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
CACHE_HOME=${XDG_CACHE_HOME:-$HOME/.cache}
RULES="$CONFIG_HOME/niri/dms/windowrules.kdl"
SETTINGS="$CONFIG_HOME/dms/settings.json"
COLORS="$CACHE_HOME/dms/dms-colors.json"

# 1. Wallpaper: one global value, or one per output when they differ.
wall=$(get WALLPAPER)
outputs=$(get WALLPAPER_OUTPUTS)
per_output=0
for out in $outputs; do
    value=$(get "WALLPAPER_$out")
    if [ -n "$value" ] && [ "$value" != "$wall" ]; then
        per_output=1
    fi
done
if [ "$per_output" = 1 ]; then
    for out in $outputs; do
        value=$(get "WALLPAPER_$out")
        [ -n "$value" ] && run dms ipc call wallpaper setFor "$out" "$value"
    done
elif [ -n "$wall" ]; then
    run dms ipc call wallpaper set "$wall"
fi

# 2. Theme mode, blur, do-not-disturb, idle inhibit.
mode=$(get THEME_MODE)
case "$mode" in
    dark|light) run dms ipc call theme "$mode" ;;
esac
blur=$(get BLUR_ENABLED)
case "$blur" in
    true|false) run dms ipc call settings set blurEnabled "$blur" ;;
esac
dnd=$(get DND)
case "$dnd" in
    true) run dms ipc call notifications enableDoNotDisturbIndefinitely ;;
    false) run dms ipc call notifications disableDoNotDisturb ;;
esac
inhibit=$(get IDLE_INHIBIT)
case "$inhibit" in
    true) run dms ipc call inhibit enable ;;
    false) run dms ipc call inhibit disable ;;
esac

# 3. DMS window rules: only put the saved copy back if they differ.
copy=$(get WINDOWRULES_COPY)
if [ -n "$copy" ] && [ -r "$copy" ] && ! cmp -s "$copy" "$RULES"; then
    run cp -p "$copy" "$RULES"
fi

# 4. DMS settings file, after the theme calls (switching the mode also
#    turns matugenSmartMode off): written in place when it differs, which
#    keeps its inode and ACL; DMS watches it and reloads. This also undoes
#    a bar widget added for one shot (`settings set` takes no arrays).
settings_copy=$(get SETTINGS_COPY)
if [ -n "$settings_copy" ] && [ -r "$settings_copy" ]; then
    if [ "$DRY" = 1 ]; then
        cmp -s "$settings_copy" "$SETTINGS" || echo "would run: cat $settings_copy > $SETTINGS"
    else
        # The theme calls above save settings.json again a moment later
        # (matugenSmartMode): wait, then write until the copy holds.
        tries=0
        while [ "$tries" -lt 5 ]; do
            sleep 3
            cmp -s "$settings_copy" "$SETTINGS" && break
            cat "$settings_copy" > "$SETTINGS" || echo "warning: failed: write $SETTINGS" >&2
            tries=$((tries + 1))
        done
    fi
fi

# 5. Output scales (changed for a while to fit a tall window), then the
#    niri focus: each output's workspace, then the focused output/window.
for pair in $(get OUTPUT_SCALES); do
    run niri msg output "${pair%%:*}" scale "${pair##*:}"
done
for pair in $(get FOCUS_WORKSPACES); do
    out=${pair%%:*}
    idx=${pair##*:}
    run niri msg action focus-monitor "$out"
    run niri msg action focus-workspace "$idx"
done
focus_out=$(get FOCUS_OUTPUT)
[ -n "$focus_out" ] && run niri msg action focus-monitor "$focus_out"
focus_win=$(get FOCUS_WINDOW)
[ -n "$focus_win" ] && run niri msg action focus-window --id "$focus_win"

# 6. DMS's colour seed cache remembers every wallpaper it was given, keyed
#    by path: drop the throwaway ones (a cache entry, nothing else uses it).
media_dir=$(get MEDIA_DIR)
SEEDS="$CACHE_HOME/dms/matugen-seeds.json"
prune_seeds() {
    python3 -I -c 'import json, os, sys
path, prefix, dry = sys.argv[1], sys.argv[2].rstrip("/") + "/", sys.argv[3] == "1"
try:
    with open(path) as f:
        doc = json.load(f)
except (OSError, ValueError):
    sys.exit(0)
entries = doc.get("entries") if isinstance(doc, dict) else None
if not isinstance(entries, dict):
    sys.exit(0)
gone = [k for k in entries if k.startswith(prefix)]
if not gone:
    sys.exit(0)
if dry:
    print("would drop %d colour seed cache entries" % len(gone))
    sys.exit(0)
for k in gone:
    del entries[k]
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(doc, f)
os.chmod(tmp, os.stat(path).st_mode & 0o7777)
os.replace(tmp, path)' "$SEEDS" "$media_dir" "$DRY"
}
seeds_left() {
    python3 -I -c 'import json, sys
try:
    entries = json.load(open(sys.argv[1])).get("entries") or {}
except (OSError, ValueError, AttributeError):
    entries = {}
print(sum(1 for k in entries if k.startswith(sys.argv[2].rstrip("/") + "/")))' "$SEEDS" "$media_dir"
}
[ -n "$media_dir" ] && prune_seeds

# 7. Checks. The colours are regenerated from the wallpaper: wait for them.
colors_now() {
    python3 -I -c 'import json, sys
d = json.load(open(sys.argv[1]))
print(d["mode"], d["colors"][d["mode"]]["surface"])' "$COLORS" 2>/dev/null
}
want_colors="$(get COLORS_MODE) $(get COLORS_SURFACE)"
tries=0
while [ "$DRY" = 0 ] && [ "$(colors_now)" != "$want_colors" ] && [ $tries -lt 60 ]; do
    tries=$((tries + 1))
    sleep 0.5
done

status=0
check() {
    if [ "$2" = "$3" ]; then
        if [ ${#2} -gt 80 ]; then echo "ok   $1: identical"; else echo "ok   $1: $2"; fi
    else
        echo "FAIL $1: now '$2', saved '$3'"
        status=1
    fi
}
check wallpaper "$(dms ipc call wallpaper get 2>/dev/null)" "$wall"
for out in $outputs; do
    want=$(get "WALLPAPER_$out")
    [ -n "$want" ] && check "wallpaper $out" "$(dms ipc call wallpaper getFor "$out" 2>/dev/null)" "$want"
done
[ -n "$mode" ] && check "theme mode" "$(dms ipc call theme getMode 2>/dev/null)" "$mode"
[ -n "$blur" ] && check blurEnabled "$(dms ipc call settings get blurEnabled 2>/dev/null)" "$blur"
[ -n "$dnd" ] && check "do not disturb" "$(dms ipc call notifications getDoNotDisturb 2>/dev/null)" "$dnd"
if [ -n "$inhibit" ]; then
    case "$(dms ipc call inhibit status 2>/dev/null)" in
        *enabled*) now=true ;;
        *) now=false ;;
    esac
    check "idle inhibit" "$now" "$inhibit"
fi
scales_now() {
    niri msg -j outputs 2>/dev/null | python3 -I -c 'import json, sys
d = json.load(sys.stdin)
print(" ".join("%s:%s" % (k, d[k]["logical"]["scale"]) for k in sorted(d)))'
}
scales=$(get OUTPUT_SCALES)
[ -n "$scales" ] && check "output scales" "$(scales_now)" "$(printf '%s\n' $scales | sort | tr '\n' ' ' | sed 's/ $//')"
check "dms-colors mode+surface" "$(colors_now)" "$want_colors"
if [ -n "$copy" ]; then
    if cmp -s "$copy" "$RULES"; then
        echo "ok   windowrules.kdl: identical (cmp)"
    else
        echo "FAIL windowrules.kdl differs from the saved copy"
        status=1
    fi
fi
if [ -n "$settings_copy" ]; then
    if cmp -s "$settings_copy" "$SETTINGS"; then
        echo "ok   settings.json: identical (cmp)"
    else
        echo "FAIL settings.json differs from the saved copy"
        status=1
    fi
fi
if [ -n "$media_dir" ] && [ "$DRY" = 0 ]; then
    # DMS may write the cache again a moment after the wallpaper change
    sleep 2
    prune_seeds
    check "colour seed cache entries of the media folder" "$(seeds_left)" 0
fi
exit $status

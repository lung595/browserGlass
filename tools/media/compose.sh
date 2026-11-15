#!/bin/sh
# Build the README media from the raw captures of capture.sh.
#
# Usage: compose.sh SHOTS_DIR WALLPAPER OUT_DIR
#   SHOTS_DIR  raw captures (capture.sh shots/): hero-before, hero-after,
#              color-ocean, color-sunset, color-forest, mode-light,
#              opacity-90, opacity-70, opacity-50, site-wiki, site-excluded
#              (browser windows, 2:1), set-status, set-appearance,
#              set-sites (settings sections), widget-raw (popout),
#              widget-restart (popout with the restart badge, optional)
#   WALLPAPER  the generated demo wallpaper (gen_wallpaper.sh) for registry.png
#   OUT_DIR    the screenshots/ folder
#
#        compose.sh gif FRAMES_DIR OUT.gif [WIDTH]
#   One GIF from the timed frames of capture.sh frames (NNNNN.png and
#   times.txt): each frame lasts until the next one was taken, the last
#   one $MEDIA_GIF_HOLD seconds (default 1.5); resampled to
#   $MEDIA_GIF_FPS (default 10) frames a second, WIDTH pixels wide
#   (default 1280), two-pass palette. Must stay under 8 MB: a larger
#   result is made again narrower (three tries), else removed (exit 1).
# Needs ffmpeg (drawtext, blend, xfade, palettegen, paletteuse).

set -eu

if [ "${1:-}" = gif ]; then
    frames=${2:?usage: compose.sh gif FRAMES_DIR OUT.gif [WIDTH]}
    out=${3:?usage: compose.sh gif FRAMES_DIR OUT.gif [WIDTH]}
    width=${4:-1280}
    limit=8000000
    list="$frames/frames.ffconcat"
    # The concat list, and the GIF's length (printed): the fps filter would
    # either drop the last frame's duration or, with the last file listed
    # twice, hold it longer, so the output is cut at that length (-t).
    total=$(python3 -I -c 'import os, sys
folder, hold = sys.argv[1], float(sys.argv[2])
rows = [line.split() for line in open(os.path.join(folder, "times.txt")) if line.strip()]
if not rows:
    sys.exit("compose.sh gif: no frame in times.txt")
lines = ["ffconcat version 1.0"]
for i, (n, t) in enumerate(rows):
    nxt = float(rows[i + 1][1]) if i + 1 < len(rows) else float(t) + hold
    lines += ["file %05d.png" % int(n), "duration %.3f" % max(0.01, nxt - float(t))]
lines.append("file %05d.png" % int(rows[-1][0]))
with open(os.path.join(folder, "frames.ffconcat"), "w") as f:
    f.write("\n".join(lines) + "\n")
print("%.3f" % (float(rows[-1][1]) - float(rows[0][1]) + hold))' "$frames" "${MEDIA_GIF_HOLD:-1.5}")
    mkdir -p "$(dirname "$out")"
    tries=0
    while :; do
        ffmpeg -hide_banner -loglevel error -y -f concat -i "$list" -filter_complex \
            "[0]fps=${MEDIA_GIF_FPS:-10},scale=$width:-2:flags=lanczos,split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle" \
            -t "$total" -loop 0 "$out"
        size=$(wc -c < "$out")
        [ "$size" -lt "$limit" ] && break
        tries=$((tries + 1))
        if [ "$tries" -ge 3 ]; then
            rm -f "$out" "$list"
            echo "compose.sh gif: still $size bytes at $width px wide (limit $limit)" >&2
            exit 1
        fi
        width=$((width * 3 / 4 / 2 * 2))
    done
    rm -f "$list"
    echo "$out: $size bytes, $width px wide"
    exit 0
fi

SHOTS=${1:?usage: compose.sh SHOTS_DIR WALLPAPER OUT_DIR}
WALL=${2:?usage: compose.sh SHOTS_DIR WALLPAPER OUT_DIR}
OUT=${3:?usage: compose.sh SHOTS_DIR WALLPAPER OUT_DIR}
mkdir -p "$OUT"

FONT="Noto Sans\\:style=Bold"
ff() { ffmpeg -hide_banner -loglevel error -y "$@"; }

# drawtext filter: a pill label. $1 text, $2 x, $3 y, $4 size, $5 an
# optional timeline condition (drawn only while it holds)
label() {
    printf "drawtext=font='%s':text='%s':fontsize=%s:fontcolor=white:expansion=none:box=1:boxcolor=0x000000@0.55:boxborderw=%s:x=%s:y=%s" \
        "$FONT" "$1" "$4" "$(($4 / 2))" "$2" "$3"
    [ -z "${5:-}" ] || printf ":enable='%s'" "$5"
}

# White vertical separator at the seam of an hstack. $1 x, $2 width
seam() {
    printf "drawbox=x=%s:y=0:w=%s:h=ih:color=white@0.9:t=fill" "$1" "$2"
}

# GIF from a filtergraph output [v]: two-pass palette, no dithering noise
# on the large flat areas. $1 inputs+graph, $2 output
gif() {
    graph=$1
    out=$2
    shift 2
    ff "$@" -filter_complex "$graph;[v]split[a][b];[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle" \
        -loop 0 "$out"
}

# --- hero.png: one window, before (left) and after (right) -------------------
ff -i "$SHOTS/hero-before.png" -i "$SHOTS/hero-after.png" -filter_complex "
[0]scale=2560:1280:flags=lanczos,crop=1280:1280:0:0[l];
[1]scale=2560:1280:flags=lanczos,crop=1280:1280:1280:0[r];
[l][r]hstack=2,$(seam 1278 4),$(label Before 1280-tw-48 h-th-56 40),$(label After 1328 h-th-56 40)" \
    -frames:v 1 "$OUT/hero.png"

# --- hero-split.gif: the split line slides across and back ------------------
# Before on the right of the line, after on its left; 0-3 s sweep, hold,
# 4-7 s back, hold.
gif "[0]scale=1280:640:flags=lanczos,format=gbrp[b];
[1]scale=1280:640:flags=lanczos,format=gbrp[a];
[a][b]blend=all_expr='if(lt(abs(X-W*clip(if(lt(T,4),T/3,(7-T)/3),0,1)),2),255,if(lt(X,W*clip(if(lt(T,4),T/3,(7-T)/3),0,1)),A,B))',format=rgb24[v]" \
    "$OUT/hero-split.gif" \
    -loop 1 -framerate 15 -t 8 -i "$SHOTS/hero-before.png" \
    -loop 1 -framerate 15 -t 8 -i "$SHOTS/hero-after.png"

# --- colors-follow-dms.gif: three wallpapers, the tint follows --------------
# The frames cross-fade unlabelled; one label is drawn on top afterwards and
# switches at the middle of each fade (no ghosted text).
gif "[0]scale=1280:640:flags=lanczos[o];
[1]scale=1280:640:flags=lanczos[s];
[2]scale=1280:640:flags=lanczos[f];
[3]scale=1280:640:flags=lanczos[o2];
[o][s]xfade=transition=fade:duration=0.6:offset=1.6[x1];
[x1][f]xfade=transition=fade:duration=0.6:offset=3.2[x2];
[x2][o2]xfade=transition=fade:duration=0.6:offset=4.8,
$(label Ocean 32 h-th-32 26 'lt(t,1.9)'),
$(label Sunset 32 h-th-32 26 'between(t,1.9,3.5)*lt(t,3.5)'),
$(label Forest 32 h-th-32 26 'between(t,3.5,5.1)*lt(t,5.1)'),
$(label Ocean 32 h-th-32 26 'gte(t,5.1)'),format=rgb24[v]" \
    "$OUT/colors-follow-dms.gif" \
    -loop 1 -framerate 10 -t 2.2 -i "$SHOTS/color-ocean.png" \
    -loop 1 -framerate 10 -t 2.2 -i "$SHOTS/color-sunset.png" \
    -loop 1 -framerate 10 -t 2.2 -i "$SHOTS/color-forest.png" \
    -loop 1 -framerate 10 -t 0.8 -i "$SHOTS/color-ocean.png"

# --- light-dark.png ------------------------------------------------------------
ff -i "$SHOTS/color-ocean.png" -i "$SHOTS/mode-light.png" -filter_complex "
[0]scale=1280:640:flags=lanczos,$(label Dark 32 h-th-32 30)[d];
[1]scale=1280:640:flags=lanczos,$(label Light 32 h-th-32 30)[l];
[d][l]hstack=2,$(seam 1278 4)" -frames:v 1 "$OUT/light-dark.png"

# --- opacity-90-70-50.png ------------------------------------------------------
ff -i "$SHOTS/opacity-90.png" -i "$SHOTS/opacity-70.png" -i "$SHOTS/opacity-50.png" -filter_complex "
[0]scale=1280:640:flags=lanczos,$(label 90% 32 h-th-32 30)[a];
[1]scale=1280:640:flags=lanczos,$(label 70% 32 h-th-32 30)[b];
[2]scale=1280:640:flags=lanczos,$(label 50% 32 h-th-32 30)[c];
[a][b][c]hstack=3,$(seam 1278 4),$(seam 2558 4)" -frames:v 1 "$OUT/opacity-90-70-50.png"

# --- excluded-site.png: a styled glass site next to an excluded one ------------
ff -i "$SHOTS/site-wiki.png" -i "$SHOTS/site-excluded.png" -filter_complex "
[0]scale=1280:640:flags=lanczos,$(label 'Glass (dedicated style)' 32 h-th-32 26)[a];
[1]scale=1280:640:flags=lanczos,$(label 'Excluded site' 32 h-th-32 26)[b];
[a][b]hstack=2,$(seam 1278 4)" -frames:v 1 "$OUT/excluded-site.png"

# --- registry.png: 1792x1008 card, the glass window over the wallpaper --------
ff -i "$WALL" -i "$SHOTS/hero-after.png" -filter_complex "
[0]scale=1792:1008:flags=lanczos[bg];
[1]scale=1600:800:flags=lanczos[w];
[bg][w]overlay=96:104" -frames:v 1 "$OUT/registry.png"

# --- settings and widget: the captures as they are ------------------------------
for part in status appearance sites; do
    ff -i "$SHOTS/set-$part.png" -frames:v 1 "$OUT/settings-$part.png"
done
ff -i "$SHOTS/widget-raw.png" -frames:v 1 "$OUT/widget-menu.png"
# The restart badge on the bar icon and the popout's restart line
if [ -e "$SHOTS/widget-restart.png" ]; then
    ff -i "$SHOTS/widget-restart.png" -frames:v 1 "$OUT/widget-restart.png"
fi

ls -l "$OUT"

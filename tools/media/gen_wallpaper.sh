#!/bin/sh
# Generate the neutral demo wallpapers used for the screenshots: a soft
# gradient plus a few large blurred shapes, 3840x2160 PNG, in three colour
# variants (ocean, sunset, forest). Nothing personal, nothing downloaded.
#
# Usage: gen_wallpaper.sh OUT_DIR [VARIANT...]
#   VARIANT: ocean | sunset | forest (default: all three)
# Writes OUT_DIR/wallpaper-<variant>.png. Needs ffmpeg (lavfi).

set -eu

OUT=${1:?usage: gen_wallpaper.sh OUT_DIR [VARIANT...]}
shift
[ $# -gt 0 ] || set -- ocean sunset forest
mkdir -p "$OUT"

# Rendered small then upscaled: the shapes are blurred anyway.
W=960
H=540

# Fixed seeds (gradients, noise): the same files on every run.
# variant -> "gradient colours | shape1 rgb | shape2 rgb | shape3 rgb"
palette() {
    case "$1" in
        ocean)  echo "0x0b1d3a:0x1c5d8f:0x0e7c86|40:170:220|90:60:200|20:200:170" ;;
        sunset) echo "0x2a0f2e:0x8f2d56:0xd8763a|250:150:60|210:60:110|120:40:160" ;;
        forest) echo "0x0d2016:0x2f6b3a:0x8a9a3b|120:200:90|30:140:110|220:190:80" ;;
        *) echo "unknown variant: $1" >&2; return 1 ;;
    esac
}

# geq expression: one colour channel = background + 3 soft discs.
channel() {
    # $1 = channel index (1..3) inside "r:g:b"
    c1=$(echo "$S1" | cut -d: -f"$1")
    c2=$(echo "$S2" | cut -d: -f"$1")
    c3=$(echo "$S3" | cut -d: -f"$1")
    base=$2
    printf "%s" "if(lt(hypot(X-0.28*W,Y-0.35*H),0.22*W),$c1,if(lt(hypot(X-0.72*W,Y-0.62*H),0.18*W),$c2,if(lt(hypot(X-0.55*W,Y-0.18*H),0.10*W),$c3,$base(X,Y))))"
}

for variant in "$@"; do
    spec=$(palette "$variant")
    colors=$(echo "$spec" | cut -d'|' -f1)
    S1=$(echo "$spec" | cut -d'|' -f2)
    S2=$(echo "$spec" | cut -d'|' -f3)
    S3=$(echo "$spec" | cut -d'|' -f4)
    c0=$(echo "$colors" | cut -d: -f1)
    c1=$(echo "$colors" | cut -d: -f2)
    c2=$(echo "$colors" | cut -d: -f3)
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "gradients=s=${W}x${H}:c0=$c0:c1=$c1:c2=$c2:n=3:type=linear:x0=0:y0=0:x1=$W:y1=$H:d=1:speed=0:seed=1" \
        -vf "format=rgb24,geq=r='$(channel 1 r)':g='$(channel 2 g)':b='$(channel 3 b)',gblur=sigma=70:steps=3,scale=3840:2160:flags=bicubic,noise=alls=3:allf=u:all_seed=1,format=rgb24" \
        -frames:v 1 "$OUT/wallpaper-$variant.png"
    echo "$OUT/wallpaper-$variant.png"
done

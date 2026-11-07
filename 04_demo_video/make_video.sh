#!/bin/sh
# Build the pitch video from source:
#   06_pitch_deck/src/animated.html   animated slides (rendered here at 30 fps)
#   demo_pump09_annotated.mp4         demo recording (record_demo.mjs), normal speed
#   voiceover/voiceover.mp3           ElevenLabs v3 voice-over, normal speed
# Usage: ./make_video.sh [OUTPUT.mp4]   (default: pitch_final.mp4; the output must not exist)
set -eu
cd "$(dirname "$0")"
OUT=${1:-pitch_final.mp4}
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
node render_anim.mjs "$TMP/frames" 30
"$FF" -nostdin -v error -framerate 30 -i "$TMP/frames/%05d.jpg" -c:v libx264 -crf 16 -pix_fmt yuv420p "$TMP/slides.mp4"
python3 build_video.py "$OUT" --slides-video "$TMP/slides.mp4" --demo demo_pump09_annotated.mp4 --voiceover voiceover/voiceover.mp3 --speed 1.05

#!/bin/bash
# Generates synthetic test footage for the end-to-end pipeline test.
# All content is locally synthesized (macOS `say` + ffmpeg lavfi) -- no
# copyrighted or external media involved.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAW="$DIR/raw"
TMP="$DIR/.tmp_gen"
rm -rf "$TMP"
mkdir -p "$RAW" "$TMP"

say_wav() {
  local text="$1" out="$2"
  say -v Samantha -o "$TMP/$out.aiff" "$text"
  ffmpeg -y -v error -i "$TMP/$out.aiff" -ar 44100 -ac 1 "$TMP/$out.wav"
}

silence_wav() {
  local dur="$1" out="$2"
  ffmpeg -y -v error -f lavfi -i "anullsrc=r=44100:cl=mono" -t "$dur" "$TMP/$out.wav"
}

# --- Talking-head clip: intro, filler-heavy line, a repeated false-start take, outro ---
say_wav "Hi everyone, welcome back to the channel." p1
say_wav "Today we're going to talk about, um, a really cool topic that I think you'll enjoy." p2
say_wav "The most important thing to remember is safety first." p3a
say_wav "The most important thing to remember is safety first." p3b
say_wav "The most important thing to remember is safety first, always." p3c
say_wav "Thanks so much for watching, see you next time." p4

silence_wav 2.5 sil_long
silence_wav 1.0 sil_mid
silence_wav 0.3 sil_short

cat > "$TMP/concat_audio.txt" <<EOF
file '$TMP/p1.wav'
file '$TMP/sil_long.wav'
file '$TMP/p2.wav'
file '$TMP/sil_long.wav'
file '$TMP/p3a.wav'
file '$TMP/sil_short.wav'
file '$TMP/p3b.wav'
file '$TMP/sil_short.wav'
file '$TMP/p3c.wav'
file '$TMP/sil_long.wav'
file '$TMP/p4.wav'
file '$TMP/sil_mid.wav'
EOF
ffmpeg -y -v error -f concat -safe 0 -i "$TMP/concat_audio.txt" -c copy "$TMP/talking_head_audio.wav"

DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$TMP/talking_head_audio.wav")
ffmpeg -y -v error -f lavfi -i "color=c=steelblue:s=640x360:r=30:d=${DURATION}" \
  -i "$TMP/talking_head_audio.wav" \
  -c:v libx264 -preset veryfast -crf 23 -c:a aac -shortest \
  "$RAW/01_talking_head.mp4"

# --- B-roll clip: static color shots, two of them longer than the 8s default max_shot_length ---
ffmpeg -y -v error -f lavfi -i "color=c=red:s=640x360:r=30:d=10" -c:v libx264 -preset veryfast -crf 23 "$TMP/shot_red.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=green:s=640x360:r=30:d=3" -c:v libx264 -preset veryfast -crf 23 "$TMP/shot_green.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=blue:s=640x360:r=30:d=12" -c:v libx264 -preset veryfast -crf 23 "$TMP/shot_blue.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=yellow:s=640x360:r=30:d=4" -c:v libx264 -preset veryfast -crf 23 "$TMP/shot_yellow.mp4"

cat > "$TMP/concat_video.txt" <<EOF
file '$TMP/shot_red.mp4'
file '$TMP/shot_green.mp4'
file '$TMP/shot_blue.mp4'
file '$TMP/shot_yellow.mp4'
EOF
ffmpeg -y -v error -f concat -safe 0 -i "$TMP/concat_video.txt" -c copy "$RAW/02_broll.mp4"

rm -rf "$TMP"
echo "Generated sample footage in $RAW:"
ls -la "$RAW"

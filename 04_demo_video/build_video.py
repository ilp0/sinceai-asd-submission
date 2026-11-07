#!/usr/bin/env python3
"""Assemble the pitch video: animated slides, 0.5 s crossfade, demo recording, voice-over.

    python3 build_video.py OUTPUT.mp4 --slides-video SLIDES.mp4 --demo DEMO.mp4 --voiceover VO.mp3 [--speed 1.05]

--speed plays the voice-over (pitch kept, FFmpeg atempo) and the demo recording faster by the same
factor, so that they stay in sync. The animated slides are already timed to the sped-up voice-over
(cue times in 06_pitch_deck/src/animated.html). The demo audio is removed. The video ends at the
longer of the picture and the voice-over (the last frame holds).
"""
import argparse, pathlib, subprocess, tempfile

FF = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FP = "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
VF = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,fps=30,format=yuv420p"


def run(cmd):
    subprocess.run([FF, "-nostdin", "-v", "error", "-y", *map(str, cmd)], check=True)


def duration(f):
    return float(subprocess.run([FP, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                                capture_output=True, text=True, check=True).stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--slides-video", required=True, help="animated slides MP4 (render_anim.mjs frames)")
    ap.add_argument("--demo", required=True, help="demo recording MP4 at normal speed")
    ap.add_argument("--voiceover", required=True, help="voice-over audio at normal speed")
    ap.add_argument("--speed", type=float, default=1.05)
    a = ap.parse_args()
    out = pathlib.Path(a.output).resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; choose a new name")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        slides, demo, vo, pic = tmp / "slides.mp4", tmp / "demo.mp4", tmp / "vo.wav", tmp / "picture.mp4"
        run(["-i", a.slides_video, "-an", "-vf", VF, "-c:v", "libx264", "-crf", "18", slides])
        run(["-i", a.demo, "-an", "-vf", f"setpts=PTS/{a.speed},{VF}", "-c:v", "libx264", "-crf", "18", demo])
        run(["-i", a.voiceover, "-af", f"atempo={a.speed}", "-ar", "48000", vo])
        run(["-i", slides, "-i", demo, "-filter_complex",
             f"[0:v][1:v]xfade=transition=fade:duration=0.5:offset={duration(slides) - 0.5:.3f},format=yuv420p[v]",
             "-map", "[v]", "-c:v", "libx264", "-crf", "18", pic])
        total = max(duration(pic), duration(vo))
        run(["-i", pic, "-i", vo, "-filter_complex", "[0:v]tpad=stop=-1:stop_mode=clone[v];[1:a]apad[a]",
             "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
    print(out)


if __name__ == "__main__":
    main()

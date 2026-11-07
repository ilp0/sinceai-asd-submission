# Demo video

`pitch_final.mp4` is the submission video: 1920×1080, 30 fps, 119.6 s (under the 2 min limit).

## Files

| File | Content |
|---|---|
| `pitch_final.mp4` | The video to submit. |
| `demo_pump09_annotated.mp4` | Screen recording of the demo dashboard (PUMP-09, 60 min/s, cursor and captions), normal speed, 33 s. Made with `record_demo.mjs`. |
| `voiceover/voiceover.mp3` | Voice-over from ElevenLabs (model Eleven v3, voice "Aapo - Friendly and approachable"), normal speed, 125.5 s. |
| `voiceover/voiceover_script.md` | Script, delivery notes and the facts behind each line. |
| `voiceover/voiceover_elevenlabs_v3.txt`, `voiceover/voiceover_demo_elevenlabs_v3.txt` | The text pasted into ElevenLabs v3. |
| `make_video.sh` | Builds the video from source. |
| `build_video.py` | Joins slides, demo and voice-over (1.05× speed, 0.5 s crossfade). |
| `render_anim.mjs` | Renders `../06_pitch_deck/src/animated.html` frame by frame in headless Chrome. `FORMAT=png` with a list of times writes stills. |
| `record_demo.mjs` | Records the demo dashboard (`../demo`, served on 127.0.0.1:8797) in headless Chrome with a cursor and captions. |

## Build

```sh
./make_video.sh pitch_new.mp4
```

Needs Google Chrome, Node, and FFmpeg with the `xfade` and `atempo` filters (`/opt/homebrew/opt/ffmpeg-full`). Takes about 3 minutes. The animated slides are timed to the voice-over at 1.05×; if the voice-over changes, change the cue times in `animated.html`.

To record the demo again, start the demo (`../demo/run.sh`) and run `node record_demo.mjs <out_dir>`. Then make the MP4 from `<out_dir>/frames.ffconcat`:

```sh
cd <out_dir> && ffmpeg -f concat -safe 0 -i frames.ffconcat -vf "fps=30,format=yuv420p" -c:v libx264 -crf 18 ../demo_pump09_annotated.mp4
```

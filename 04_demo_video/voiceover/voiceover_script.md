# Voice-over script — pitch video

Audience: other hackathon builders. They do not know the challenge or our project.
Final result: one ElevenLabs v3 clip, `voiceover.mp3` (125.5 s). The build plays it at 1.05× (119.5 s), and the animated slides (`06_pitch_deck/src/animated.html`) are timed to the narration cues at that speed. The slide times below are the first plan.
Speech rate for the word budget: about 2.6 words per second.

---

## 1. Title — 9 s (19 words)

> We're Team ASD. Business Turku's challenge: make existing industrial machines intelligent, without replacing them, by spotting pump faults early.

## 2. Approach — 12 s (30 words)

> We took Timestral, a pretrained time-series transformer, removed its forecasting head, and fine-tuned it with LoRA as a fault classifier. Each of thirteen fault types learns which sensors to watch.

## 3. Benchmark — 14 s (34 words)

> Tested on the two official validation pumps plus five we generated, our challenge score is 81.8 against the baseline's 65.6. We catch 88 percent of faults and name the right type twice as often.

## 4. Use case — 12 s (28 words)

> When an alert fires, a language model reads the pump's operating manual and writes repair steps. A second pass checks every manual reference before the operator sees it.

## 5. Cost — 12 s (28 words)

> The model has 26 million parameters, so it runs on-site and the data stays there. Training touched only 1.4 million weights: one A100, five hours, under nine dollars.

## 6. Generalizability — 10 s (27 words)

> Nothing here is pump-specific. We trained on seven public pumps plus 250 pump-weeks we simulated ourselves. Any annotated time series and its manual fit the same pipeline.

## 7. Reliability and safety — 14 s (30 words)

> Operators set one threshold to trade missed faults against false alarms. Each alert shows which sensors caused it, and advice appears only after it is verified against the real manual.

## 8. Demo — 2 s (4 words)

> Here it is, live.

Total: 200 words in 85 s.

---

## Delivery notes

- Stress the numbers on slide 3 ("sixty-five point six", "eighty-one point eight") and leave a short pause after each one.
- Say "Timestral" as "time-stral". Say "LoRA" as "lora", one word.
- Slides 2 and 3 are the densest. If the reading is too fast, add 2 s to each and remove 2 s from slide 6 and 2 s from slide 1. The total must stay at or below 87 s, because the demo needs 33 s.

## Facts behind each line

| Line | Fact | Source |
|---|---|---|
| Challenge | Add intelligence to existing machines without a replacement; find emerging faults early; 1 Hz pump telemetry | `README.md` (submission) |
| Timestral, head removed, LoRA | Timestral-28M backbone, quantile forecast head deleted, LoRA rank 32 / alpha 64 on attention | `05_source_code/src/data_analysis_experiment_6_model/README.md`, `configs/rp3-3h-r32.yaml` |
| 13 fault types, sensors to watch | Multi-label sigmoid head with class attention pooling: each fault type has its own attention over the sensor rows | same README, section 1.4 |
| Three hours of telemetry (not spoken) | 180 min at 10 s cells | `configs/rp3-3h-r32.yaml` |
| 65.6 → 81.8, 88 %, type 38 % → 75 % | Organizer scorer, 7 validation pumps, B1 mode-aware z-score baseline | `optimize/results/persistence-v1/report.md`, `submission/README.md` (experiment repo) |
| 26 million parameters | 26.5 M in the default configuration | experiment 6 README, section 2 |
| 1.4 million trained weights | Calculated, not measured: rank-32 LoRA (4 × 276 480) + query token (384) + head (312 909) = 1 419 213. Run `run.py describe` on the round-3 config to confirm. | experiment 6 README, section 2 |
| One A100, five hours, under nine dollars | 3h pod: A100 SXM, 5.01 h, $8.97 | `runpod/pods.json` (experiment 6 worktree) |
| Seven public pumps + 250 simulated pump-weeks | PUMP-01..07 plus generated sets train (100) and train2 (147) from the organizer simulator `build()` | `configs/runpod-full2.yaml`, experiment 4 README |
| Language model + second check | Writer call and checker call of the same local LLM; a rejected step goes back to the writer | `demo/README.md` |
| Sensors that caused the alert | Sensor-removal (occlusion) test for each alert | submission `README.md` |

## ElevenLabs text

The voice-over was made with **Eleven v3**. Paste-ready text: `voiceover_elevenlabs_v3.txt` (slides) and `voiceover_demo_elevenlabs_v3.txt` (demo). Source of the markup rules: ElevenLabs docs, "Best practices" (`https://elevenlabs.io/docs/best-practices/prompting/controls`), read on 7 November 2026. Eleven v3 does not support break tags, so the files use `[short pause]` between slides and ellipses (`...`) for short pauses.

Changes from the plain script, for correct speech:

- Numbers are words: "eighty-one point eight", "sixty-five point six", "one point four million". The docs recommend this.
- Respelled names: "Time-stral" for Timestral, "Lora" for LoRA, "A-S-D" for ASD, "A one hundred" for A100.
- "TWICE" is in capitals for emphasis.

Generated file: `voiceover.mp3`, ElevenLabs voice "Aapo - Friendly and approachable", Eleven v3, 125.5 s, slides and demo text in one clip.

## Demo recording — 33 s (`demo_pump09_annotated.mp4`)

The recording replays PUMP-09 at 60 min/s and has its own captions at the bottom. The voice-over adds to the captions; it does not read them aloud. Times come from the caption changes in the video.

| Time | Caption on screen | What happens | Voice-over |
|---|---|---|---|
| 0–5 s | Select the pump | Cursor selects PUMP-09 | This is a replay of validation pump nine, at one hour per second. |
| 5–16 s | Timestral reads the last 3 h of all sensors every 10 s | Replay starts; probability chart fills; misalignment rises | Every ten seconds, our fine-tuned Timestral model reads the last three hours from all sensors. The chart shows each fault probability as the replay runs. |
| 16–24 s | Timestral detects misalignment … / One probability for each of 13 fault types / The model shows its evidence … | Alert at Day 1 06:20, 100 %; advice with 5 steps and manual clauses; strongest signal: vibration velocity | Misalignment stays above ninety percent for fifteen minutes, so an alert fires. The model also shows its evidence: vibration velocity. |
| 24–29 s | Ask a question about the alert | "What are the alignment limits?" → 0.05 mm, clause §9.3 | The advice cites the pump manual, and the operator can ask follow-up questions. |
| 29–33 s | (none), then Monitoring continues | Acknowledge; replay continues; PUMP-09 "Under watch" | The operator acknowledges, and monitoring continues. |

Assembly: `../make_video.sh` renders the animated slides, plays `voiceover.mp3` and the demo recording at 1.05×, adds a 0.5 s crossfade from the slides to the demo, and writes the video. The demo narration starts with the demo picture at 88.0 s (85.92 s "Here's a demo in action" at 1.05×). Total: 119.6 s.

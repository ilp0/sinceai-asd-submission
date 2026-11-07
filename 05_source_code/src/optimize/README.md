# Optimize: alert threshold and running average of the experiment-6 probabilities

This folder tests how the frozen experiment-6 models turn class probabilities into alerts. The model weights do not change. An Optuna grid study searches the alert threshold and the length of a causal running average of the probabilities. The objective is the organizer composite score on the 7 validation pumps. Every trial also records the full scorer output and per-fault-type telemetry.

## Search space

| Parameter | Values |
|---|---|
| Model | `3h` = `rp3-3h-r32-v1/checkpoint_last_step11500`, `6h` = `rp3-6h-r32-v1/checkpoint_last_step14750` (the last checkpoints of the training, not chosen on validation) |
| Threshold | 0.7, 0.8, 0.85, 0.9, 0.95, 0.99 |
| Running average | 5, 15, 30, 60 s: trailing mean of each class probability over (t − w, t] |

Fixed rules: cooldown 720 min per fault type, 5 min gap between alerts of one pump, persistence one window. The grid has 2 × 6 × 4 = 48 trials (`thr-window-v1`). `--thresholds`, `--windows` and `--persistence-min` change the grid; see "Studies run" for the later grids.

The probabilities come at the finest time step of each model: one window ends at every cell, which is every 10 s for the 3h model and every 20 s for the 6h model. A running average shorter than the step holds one sample, so 5 s (both models) and 15 s (6h model) are equal to the raw probability.

## Files

| File | Purpose |
|---|---|
| `predict_val.py` | Window probabilities of one frozen checkpoint on the 7 validation pumps, one parquet file per pump in `predictions/<run>/` (git-ignored). Runs on CUDA, MPS or CPU. |
| `jobs/opt-predict.ts` | `lr` job: one RunPod A100 pod, upload, both predictions, copy back, terminate. |
| `alerts.py` | Causal running average, the alert rule (same result as `mlhead.benchmark.alerts_from_predictions`, checked by `python alerts.py <exp6> <prediction file>`), scorer calls and per-type tables. |
| `study.py` | The Optuna study, the files in `results/<study>/`, TensorBoard logs and `report.md`. |
| `per_class.py` | One threshold per fault type (or off) by coordinate ascent, with leave-one-pump-out validation. `results/per-class-<model>-v1/`. |
| `lopo.py` | Leave-one-pump-out estimate of the setting selection of a finished study (`--model` limits the choice to one model). `results/<study>/lopo*.md`. |
| `predict_test_fine.py` | Test-pump predictions at the 10 s stride with the frozen rule (`results/submission-fine/RULE_FROZEN.json`); `jobs/test-fine.ts` runs it as an `lr` job. |
| `occlusion.py` | Evidence for each alert: the alert window is predicted again without each sensor row. A row is decisive when the probability without it is below 0.9. Writes `occlusion_<split>.csv` and `predictions_<split>_explained.csv`. |
| `occlusion_check.py` | Validation occlusion against the label `evidence_channels`, per event. |
| `study.db` | Optuna storage (SQLite). |

## Studies run on 7 November 2026

| Study | Grid | Best on all 7 pumps |
|---|---|---|
| `thr-window-v1` | 2 models × 6 thresholds (0.7–0.99) × 4 windows (5–60 s), persistence one window | 6h, 0.99, 30 s: 77.4 |
| `thr-window-high-v1` | 2 models × 7 thresholds (0.99–0.9995) × 6 windows (30–600 s) | 3h, 0.995, 60 s: 81.0 |
| `per-class-3h-v1`, `per-class-6h-v1` | one threshold per fault type, LOPO | fit 85.5 / 87.6, LOPO 73.3 / 70.2 (no gain over a common threshold) |
| `persistence-v1` | 2 models × 7 thresholds (0.8–0.995) × 3 windows (raw, 60, 180 s) × 7 persistence values (0–30 min) | 3h, 0.9, raw, 10 min: 83.2; LOPO (3h only) 77.6 |

The 6h-only studies `thr-window-6h-v1` and `thr-window-6h-high-v1` ran before the 3h predictions were ready.

## Commands

Run from this folder. The venv `.venv` (git-ignored) has optuna, pandas, torch (CPU), tensorboardX and matplotlib.

```bash
lr run jobs/opt-predict.ts          # predictions on RunPod (lr status opt-predict)
.venv/bin/python study.py --study thr-window-v1
.venv/bin/tensorboard --logdir tensorboard --host 127.0.0.1 --port 6008
```

On the Mac without a pod (about 3 h on MPS):

```bash
../data_analysis_expriment_1/.venv/bin/python predict_val.py --run rp3-3h-r32-v1 --checkpoint checkpoint_last_step11500
```

## Telemetry of each trial

- Every organizer metric for three groups: `all` (7 pumps), `val-orig` (PUMP-08/09), `val-new` (5 generated pumps).
- Per true fault type: events, detected, type-correct, recall, type recall, timeliness, median delay after the detectable time, repeats.
- Per predicted fault type: scored alert bursts, and how many fall inside an event window of the same type, inside a window of another type only, or outside every window (false alert).
- Per model and running-average window: the window-level AUPRC of each class.
- The alert file in the organizer format and the per-event scorer result.

## Limitations

- The study selects and scores on the same 26 validation events. The best values are optimistic. Each fault type has 1 to 3 validation events, so the per-type values are noisy.
- The experiment-6 data folders and the run checkpoints are only in the worktree `.claude/worktrees/timestral-multiclass-prediction-c697e7/` (git-ignored). The scripts find them there.
- The test pumps (PUMP-10..12) are not used.

## Conclusions and caveats (7 November 2026, after an independent review)

- **Size of the evidence.** The 7 validation pumps have 24 observable events; 15 of them are on the 5 generated pumps. One event is worth about 3 composite points. Differences of less than about 3 points between settings are noise, and the best of about 300 trials is optimistic.
- **Expected score.** Report the leave-one-pump-out values, not the best trial: 77.6 for the 3h model (`persistence-v1`), 73.2 for the 6h model.
- **Persistence matters most.** With the 3h model, thresholds 0.85–0.9 and 10–30 min persistence score 77.3–83.2 (all windows; 79.5–83.2 without a running average). The values are not monotone in persistence. A running average adds nothing when persistence is used.
- **Per-class thresholds** gave no gain out of sample (LOPO 73.3 against 73.9 for the 3h model, 70.2 against 69.7 for the 6h model). This was tested with persistence one window only.
- **Stride 60 s → 10 s with the current rule (3h, 0.9, 15 min).** No new parameter was tuned, but the rule, the model and the 15 min value were all chosen earlier on these same pumps. The change gives +3.7 for the 3h model (78.1 → 81.8) and −2.1 for the 6h model (77.5 → 75.4). At 60 s, persistence 10/15/20/30 min already gives 80.4/78.1/77.8/81.2. Thus the stride gain is within the noise; it is not a proven improvement.
- **Official pumps only (PUMP-08/09, 9 events).** The 3h rule scores 79.2 at 10 s and 74.8 at 60 s; the 6h model 80.5–80.6; the B1 baseline 78.2. The choice of 3h over 6h comes mostly from the generated pumps.
- **Precision loss** comes mostly from repeat alerts on detected events (best trial: 1 false-alert episode, 7 excess repeat episodes), not from false alarms.
- **Test pumps.** No test labels are read. Freeze the alert rule before you look at the test alert counts: a change after that counts as tuning on test data.

## Gap boundary amendment (7 November 2026)

`fast_alerts(..., gap_inclusive=True)` drops an alert at exactly the gap (5:00) after the previous alert of the pump. The scorer merges alerts that are 5:00 or less apart, and a mixed-type burst gets no fault-type credit. `predict_test_fine.py` uses it; the studies keep the default (`False`, same as experiment 6). Validation: no change (74 alerts, 81.82). Test: 2 PUMP-11 SENSOR_STUCK alerts move by 10 s, and no mixed-type burst remains. Old files: `results/submission-fine/before-gap-fix/`. Record: `RULE_FROZEN.json` → `amendments`.

## Occlusion evidence (reviewed 7 November 2026)

`occlusion.py` predicts each alert window again without each sensor row. A row is decisive when the class probability without it is below 0.9. This shows which input the model's alert depends on, not a proven physical cause. `occlusion_check.py` compares the validation result with the organizer label `evidence_channels`, per event.

- **Validation:** 18 of 25 alerts have a decisive row. Per event (6 matched events, 22 alerts; COMMUNICATION_LOSS left out, its label channel is the gateway): the first decisive row is a label channel in 5 of 5 events with a decisive row; the strongest attention row in 5 of 6 events; the largest-drop row in 4 of 6. Only removal finds the stuck `bearing_temp_c` of the SENSOR_STUCK event (attention names `flow_m3_h`). Six events: an indication only.
- **Test:** 28 of 34 alerts have a decisive row; 15 of the 44 decisive rows are rows that every training pump has.
- **Out-of-distribution removals:** every training pump has the 4 derived rows, `discharge_pressure_kpa`, `motor_current_a`, `fluid_temp_c` and `ambient_temp_c` (`ALWAYS_PRESENT` in `occlusion.py`). The model never saw an input without these rows; the evidence text marks them "[removal unseen in training]".
- **Limits:** near 0.9, small drops count as decisive; near 1.0 the probability saturates (`logit_drop` in the CSV helps); one row at a time misses redundant pairs; only the last window of the 15 min rule is tested.

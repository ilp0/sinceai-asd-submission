# Predictions

| File | Content |
|---|---|
| `predictions_test.csv` | **The file to submit.** 34 alerts on the test pumps PUMP-10 (9), PUMP-11 (10) and PUMP-12 (15), in the format of `submission_template/predictions_template.csv`. The `evidence` column names the sensor signals that the model's alert depends on (sensor-removal test). |
| `predictions_validation.csv` | The same method on the validation pumps PUMP-08 and PUMP-09, for the local score. |
| `RULE_FROZEN.json` | The model and the alert rule, recorded before any test alert was made, and one recorded amendment (the gap boundary, see below). |
| `occlusion/occlusion_<split>.csv` | The sensor-removal test of each alert: one row for each alert and sensor row. |

Made on 7 November 2026 with `src/optimize/predict_test_fine.py` (alerts) and `src/optimize/occlusion.py` (evidence text).

## Method

- **Model:** Timestral-28M backbone with LoRA (rank 32, alpha 64) and a multi-label fault head (13 fault types). Experiment 6 round 3, run `rp3-3h-r32-v1`: 3 h input window at 10 s cells. Checkpoint `checkpoint_last_step11500`, the last checkpoint of the training, not a checkpoint chosen on validation.
- **Predictions:** one probability per fault type every 10 s. This is the finest time step of the model: a window ends at every cell.
- **Alert rule:** the class probability stays at or above 0.9 for 15 minutes (90 consecutive predictions); a 12 h cooldown per fault type; a 5 min minimum gap between alerts of one pump. No running average.
- **Gap boundary (amendment of 7 November 2026):** an alert at exactly 5:00 after the previous alert of the pump is dropped. The organizer scorer merges alerts that are 5:00 or less apart into one burst, and a burst with mixed fault types gets no fault-type credit. The old rule kept an alert at exactly 5:00. The fix changes no validation alert (score 81.8). In the test file, it moves 2 PUMP-11 SENSOR_STUCK alerts by 10 s, so they do not merge with a DISCHARGE_RESTRICTION alert. No test labels were read. The old and the new alert times are in `RULE_FROZEN.json` → `amendments`.
- **Causal:** a window at issue time t contains only data at or before t. Each pump is normalized with the first 24 h of its own window, and no alert occurs in these 24 h.
- **No test data in any decision:** no test labels, test events, benign windows or maintenance records were read. The rule was frozen (`RULE_FROZEN.json`) before the test alerts were made.

## Validation score (organizer scorer)

The model, the threshold, the persistence and the 10 s step were all selected on these validation pumps, so the scores are optimistic. The validation set has 24 observable events (9 on PUMP-08/09, 15 on 5 generated pumps); one event is worth about 3 composite points.

| Method | All 7 validation pumps | PUMP-08/09 | 5 generated pumps | Precision | False alerts / pump-day | Event recall | Fault-type recall |
|---|---|---|---|---|---|---|---|
| Organizer baseline B1 | 65.6 | 78.0 | 57.8 | 0.85 | 0.06 | 0.71 | 0.38 |
| Same model and rule, 60 s step (earlier submission) | 78.1 | 74.8 | 79.9 | 0.58 | 0.33 | 0.92 | 0.75 |
| **This submission (10 s step)** | **81.8** | 79.2 | 83.3 | 0.75 | 0.14 | 0.88 | 0.75 |

- **Expected score on new pumps:** about 77.6. This is the leave-one-pump-out estimate: for each pump, the setting was chosen on the other 6 pumps (`src/optimize/results/persistence-v1/lopo_3h.md`).
- The change from the 60 s to the 10 s step adds no parameter, but its gain (+3.7) is about one event. The same change lowered the 6h model from 77.5 to 75.4. Treat it as equal or slightly better, not as a proven gain.
- On PUMP-08/09 alone, B1 (78.0) and the 6h model (80.6) are near this submission (79.2). The 3h model was chosen mostly because of the generated pumps.

To score the validation file again, run this command from the organizer package folder:

```bash
python -m retrofit_sim score --predictions <path>/predictions_validation.csv --events data/full/events_validation.csv --assets data/full/assets.csv --benign data/full/benign_windows_train_validation.csv --split validation
```

## Which signals the model's alert depends on (occlusion)

For each alert, the alert window is predicted again without each sensor row. A row is *decisive* when the class probability without it falls below 0.9: without that signal, the alert would not occur in that window. The evidence text names up to 2 decisive rows and the total number when there are more, or says that no single row is decisive. It also names the row with the strongest attention weight.

- **Test:** 28 of 34 alerts have a decisive row. Examples: suction pressure for SUCTION_STRAINER_CLOGGING (8 of 8), vibration crest factor for most BEARING_WEAR alerts, discharge pressure, motor power and flow for DISCHARGE_RESTRICTION.
- **Validation, per event, against the organizer labels (`evidence_channels`):** 6 matched events (22 alerts; COMMUNICATION_LOSS is left out because its label channel is the gateway, not a sensor). The first decisive row is a label channel in 5 of the 5 events that have a decisive row. The strongest attention row is a label channel in 5 of 6 events. Only removal found the stuck instrument of the SENSOR_STUCK event (`bearing_temp_c`). Six events are an indication only.

What the evidence does not show:

- **Not a proven physical cause.** It shows which input the model uses. Example: one test BEARING_WEAR alert names suction pressure as decisive.
- **Some removals are out of distribution.** Training has pumps without most instruments, but every training pump has the 4 derived rows (running, data present, communication loss, out of range), discharge pressure, motor current, fluid temperature and ambient temperature. For these rows the model never saw the input without the row, and the evidence text marks them "[removal unseen in training]". 15 of the 44 decisive test rows are of this kind, including the only evidence for both PUMP-11 SENSOR_STUCK alerts (discharge pressure).
- **"Decisive" depends on the probability.** Near 0.9, small drops count; near 1.0, the probability is saturated (all 6 test alerts without a decisive row have p ≥ 0.989). `occlusion_<split>.csv` also gives the drop in logits. One row at a time does not find redundant pairs, for example motor power and motor current.
- **Only the last window is tested.** The rule needs 15 min (90 windows); without the row, the alert could still occur some windows later.
- To run `occlusion.py` in this package, put the organizer package at `src/raw/<package>/RETROFIT_AI_PARTICIPANTS_2026/`. The experiment-6 code finds it there; it does not read `RETROFIT_PKG`.
- The alerts themselves do not change: same pumps, times, fault types and confidences.

## Limitations

- Small validation set (24 events, 1–3 per fault type). The rule and the run were selected on it.
- Most lost precision comes from repeat alerts on detected events, not from false alarms.
- The test pumps include a vessel and a plant that are not in the training or validation data. The score on the test pumps can be lower.
- The confidence values are model probabilities. They are calibrated well above 0.9 only.

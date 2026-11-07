# Threshold and running-average study `thr-window-6h-high-v1`

Created 2026-11-07 20:11 EET by `optimize/study.py`. Objective: organizer composite score on all 7 validation pumps (PUMP-08/09 and 5 generated pumps, 24 observable events). Selection and score use the same validation events, so the best values are optimistic.

Models (frozen last checkpoints of experiment 6, round 3):

- 6h: `rp3-6h-r32-v1` `checkpoint_last_step14750` (step 14750), 360 min context, predictions every 20 s

Fixed rules: {"cooldown_minutes": 720, "global_gap_minutes": 5, "persistence_s": 0}. Persistence 0 s means one window. A running-average window shorter than the prediction stride holds one sample (the raw probability).

## Top 10 settings

| # | Model | Threshold | Window | Composite all | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6h | 0.99 | 180 s | **78.5** | 80.5 | 77.6 | 0.83 | 0.83 | 0.83 | 0.67 | 0.78 | 0.08 | 64 |
| 2 | 6h | 0.993 | 300 s | **77.5** | 80.5 | 75.8 | 0.88 | 1.00 | 0.79 | 0.58 | 0.75 | 0.00 | 57 |
| 3 | 6h | 0.99 | 30 s | **77.4** | 83.0 | 74.2 | 0.75 | 0.63 | 0.92 | 0.67 | 0.88 | 0.27 | 82 |
| 4 | 6h | 0.99 | 60 s | **76.6** | 76.4 | 76.8 | 0.76 | 0.68 | 0.88 | 0.67 | 0.81 | 0.20 | 75 |
| 5 | 6h | 0.993 | 30 s | **76.5** | 84.8 | 71.8 | 0.75 | 0.66 | 0.88 | 0.67 | 0.84 | 0.22 | 76 |
| 6 | 6h | 0.99 | 300 s | **76.3** | 80.5 | 74.0 | 0.83 | 0.86 | 0.79 | 0.62 | 0.75 | 0.06 | 61 |
| 7 | 6h | 0.993 | 180 s | **76.3** | 80.5 | 73.9 | 0.83 | 0.86 | 0.79 | 0.62 | 0.75 | 0.06 | 61 |
| 8 | 6h | 0.99 | 120 s | **76.1** | 77.7 | 75.6 | 0.80 | 0.77 | 0.83 | 0.62 | 0.78 | 0.12 | 68 |
| 9 | 6h | 0.995 | 30 s | **75.9** | 78.3 | 74.8 | 0.77 | 0.71 | 0.83 | 0.67 | 0.78 | 0.16 | 70 |
| 10 | 6h | 0.995 | 60 s | **75.9** | 78.3 | 74.7 | 0.77 | 0.71 | 0.83 | 0.67 | 0.78 | 0.16 | 69 |

## Reference: current submission rule on the same predictions

Threshold 0.9, persistence 15 min, no running average (the rule of `submission/predictions_test.csv`).

| Model | Composite all | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| 6h | 75.4 | 80.6 | 72.6 | 0.83 | 0.83 | 0.54 | 0.08 |

## Model 6h: best setting threshold 0.99, window 180 s (composite 78.5)

### Composite (all pumps) by threshold and window

| Threshold | 30 s | 60 s | 120 s | 180 s | 300 s | 600 s |
|---|---|---|---|---|---|---|
| 0.99 | 77.4 | 76.6 | 76.1 | 78.5 | 76.3 | 72.5 |
| 0.993 | 76.5 | 75.3 | 74.2 | 76.3 | 77.5 | 72.4 |
| 0.995 | 75.9 | 75.9 | 74.2 | 75.7 | 75.6 | 72.3 |
| 0.997 | 72.8 | 72.7 | 72.4 | 72.3 | 72.3 | 67.1 |
| 0.998 | 70.9 | 70.9 | 72.3 | 68.9 | 68.8 | 67.5 |
| 0.999 | 72.1 | 66.7 | 67.5 | 67.5 | 65.5 | 62.5 |
| 0.9995 | 64.5 | 65.5 | 66.3 | 63.5 | 62.5 | 58.8 |

### Per fault type at the best setting

Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of that type; wrong = inside the window of another type; outside = false alert).

| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |
|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 2 | 2 | 1.00 | -1.3 | 11 | 11 | 0 | 0 | 0.936 |
| SUCTION_STRAINER_CLOGGING | 3 | 3 | 3 | 0.97 | 8.9 | 13 | 12 | 1 | 0 | 0.879 |
| CAVITATION | 0 | – | – | – | – | 0 | 0 | 0 | 0 | – |
| DISCHARGE_RESTRICTION | 2 | 1 | 1 | 0.50 | 1.0 | 4 | 4 | 0 | 0 | 0.616 |
| MISALIGNMENT | 3 | 3 | 1 | 0.83 | 8.3 | 9 | 8 | 1 | 0 | 0.734 |
| IMBALANCE | 1 | 1 | 1 | 1.00 | 2.8 | 6 | 2 | 4 | 0 | 0.720 |
| IMPELLER_WEAR | 1 | 1 | 1 | 1.00 | 3.7 | 9 | 6 | 3 | 0 | 0.630 |
| AIR_ENTRAINMENT | 2 | 2 | 2 | 1.00 | 0.5 | 2 | 2 | 0 | 0 | 0.957 |
| SENSOR_DRIFT | 2 | 1 | 1 | 0.31 | 45.6 | 3 | 2 | 1 | 0 | 0.524 |
| SENSOR_STUCK | 2 | 1 | 1 | 0.38 | 13.9 | 1 | 1 | 0 | 0 | 0.619 |
| SENSOR_CALIBRATION_SHIFT | 1 | 0 | 0 | 0.00 | – | 3 | 0 | 3 | 0 | 0.263 |
| SENSOR_NOISE_SPIKES | 2 | 2 | 0 | 0.97 | 4.8 | 0 | 0 | 0 | 0 | 0.132 |
| COMMUNICATION_LOSS | 3 | 3 | 3 | 1.00 | 0.2 | 3 | 3 | 0 | 0 | 0.999 |

## Best setting for each fault type

Type score = harmonic mean of type recall (events of the type detected with the correct type) and type precision (alert bursts that name the type and fall inside an event window of that type). Ties go to the higher threshold. A hint for per-class thresholds; few events per type, so the values are noisy.

| Fault type | Events | Model | Threshold | Window | Type recall | Type precision | Type score | Outside alerts |
|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 6h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |
| SUCTION_STRAINER_CLOGGING | 3 | 6h | 0.999 | 30 s | 1.00 | 1.00 | 1.00 | 0 |
| CAVITATION | 0 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | 2 | 6h | 0.9995 | 600 s | 0.50 | 1.00 | 0.67 | 0 |
| MISALIGNMENT | 3 | 6h | 0.9995 | 180 s | 0.67 | 1.00 | 0.80 | 0 |
| IMBALANCE | 1 | 6h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |
| IMPELLER_WEAR | 1 | 6h | 0.9995 | 300 s | 1.00 | 1.00 | 1.00 | 0 |
| AIR_ENTRAINMENT | 2 | 6h | 0.9995 | 300 s | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_DRIFT | 2 | 6h | 0.9995 | 120 s | 0.50 | 1.00 | 0.67 | 0 |
| SENSOR_STUCK | 2 | 6h | 0.993 | 30 s | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_CALIBRATION_SHIFT | 1 | 6h | 0.9995 | 600 s | 0.00 | 0.00 | 0.00 | 0 |
| SENSOR_NOISE_SPIKES | 2 | 6h | 0.9995 | 600 s | 0.00 | 0.00 | 0.00 | 0 |
| COMMUNICATION_LOSS | 3 | 6h | 0.997 | 60 s | 1.00 | 1.00 | 1.00 | 0 |

## Files

- `trials.csv`: every trial with all organizer metrics per group (`all/`, `val-orig/`, `val-new/`).
- `per_type_events.csv`, `per_type_alerts.csv`, `per_type_joined.csv`: per fault type for every trial.
- `window_auprc.csv`: window-level AUPRC per model, window and fault type (independent of the threshold).
- `alerts/`, `per_event/`: alert file (organizer format) and per-event scorer result of every trial.
- `composite_*.png`, `per_type_*.png`: figures. TensorBoard: `optimize/tensorboard/thr-window-6h-high-v1/`.
- Optuna storage: `optimize/study.db` (study `thr-window-6h-high-v1`).

# Threshold and running-average study `thr-window-high-v1`

Created 2026-11-07 20:18 EET by `optimize/study.py`. Objective: organizer composite score on all 7 validation pumps (PUMP-08/09 and 5 generated pumps, 24 observable events). Selection and score use the same validation events, so the best values are optimistic.

Models (frozen last checkpoints of experiment 6, round 3):

- 3h: `rp3-3h-r32-v1` `checkpoint_last_step11500` (step 11500), 180 min context, predictions every 10 s
- 6h: `rp3-6h-r32-v1` `checkpoint_last_step14750` (step 14750), 360 min context, predictions every 20 s

Fixed rules: {"cooldown_minutes": 720, "global_gap_minutes": 5, "persistence_s": 0}. Persistence 0 s means one window. A running-average window shorter than the prediction stride holds one sample (the raw probability).

## Top 10 settings

| # | Model | Threshold | Window | Composite all | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3h | 0.995 | 60 s | **81.0** | 81.1 | 80.9 | 0.85 | 0.87 | 0.83 | 0.71 | 0.77 | 0.06 | 61 |
| 2 | 3h | 0.993 | 300 s | **80.3** | 83.3 | 78.6 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 58 |
| 3 | 3h | 0.99 | 600 s | **80.3** | 83.3 | 78.6 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 59 |
| 4 | 3h | 0.993 | 600 s | **80.3** | 83.3 | 78.5 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 57 |
| 5 | 3h | 0.995 | 120 s | **80.2** | 83.3 | 78.5 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 58 |
| 6 | 3h | 0.995 | 180 s | **80.2** | 83.3 | 78.5 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 58 |
| 7 | 3h | 0.997 | 30 s | **80.2** | 83.3 | 78.4 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 58 |
| 8 | 3h | 0.997 | 60 s | **80.2** | 83.3 | 78.4 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 56 |
| 9 | 3h | 0.998 | 30 s | **80.2** | 83.3 | 78.4 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 56 |
| 10 | 3h | 0.995 | 300 s | **80.1** | 83.3 | 78.3 | 0.84 | 0.90 | 0.79 | 0.71 | 0.76 | 0.04 | 55 |

## Reference: current submission rule on the same predictions

Threshold 0.9, persistence 15 min, no running average (the rule of `submission/predictions_test.csv`).

| Model | Composite all | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| 3h | 81.8 | 79.2 | 83.3 | 0.75 | 0.88 | 0.75 | 0.14 |
| 6h | 75.4 | 80.6 | 72.6 | 0.83 | 0.83 | 0.54 | 0.08 |

## Model 3h: best setting threshold 0.995, window 60 s (composite 81.0)

### Composite (all pumps) by threshold and window

| Threshold | 30 s | 60 s | 120 s | 180 s | 300 s | 600 s |
|---|---|---|---|---|---|---|
| 0.99 | 76.5 | 76.4 | 77.5 | 78.1 | 79.5 | 80.3 |
| 0.993 | 75.9 | 78.9 | 78.8 | 79.5 | 80.3 | 80.3 |
| 0.995 | 77.0 | 81.0 | 80.2 | 80.2 | 80.1 | 79.9 |
| 0.997 | 80.2 | 80.2 | 80.1 | 79.5 | 79.3 | 76.8 |
| 0.998 | 80.2 | 79.5 | 79.3 | 76.8 | 76.8 | 76.5 |
| 0.999 | 76.9 | 76.8 | 76.8 | 77.5 | 77.5 | 69.2 |
| 0.9995 | 77.5 | 76.7 | 72.7 | 66.3 | 63.5 | 64.0 |

### Per fault type at the best setting

Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of that type; wrong = inside the window of another type; outside = false alert).

| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |
|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 2 | 2 | 1.00 | 0.1 | 11 | 11 | 0 | 0 | 0.960 |
| SUCTION_STRAINER_CLOGGING | 3 | 3 | 3 | 0.97 | 13.8 | 10 | 10 | 0 | 0 | 0.879 |
| CAVITATION | 0 | – | – | – | – | 0 | 0 | 0 | 0 | – |
| DISCHARGE_RESTRICTION | 2 | 1 | 1 | 0.48 | 2.9 | 4 | 4 | 0 | 0 | 0.509 |
| MISALIGNMENT | 3 | 2 | 1 | 0.53 | 36.9 | 8 | 6 | 2 | 0 | 0.619 |
| IMBALANCE | 1 | 1 | 0 | 1.00 | 1.7 | 9 | 2 | 7 | 0 | 0.287 |
| IMPELLER_WEAR | 1 | 1 | 1 | 1.00 | 3.9 | 6 | 6 | 0 | 0 | 0.684 |
| AIR_ENTRAINMENT | 2 | 2 | 2 | 1.00 | 0.4 | 2 | 2 | 0 | 0 | 0.870 |
| SENSOR_DRIFT | 2 | 1 | 1 | 0.46 | 13.8 | 3 | 3 | 0 | 0 | 0.658 |
| SENSOR_STUCK | 2 | 2 | 2 | 1.00 | 1.0 | 4 | 3 | 1 | 0 | 0.619 |
| SENSOR_CALIBRATION_SHIFT | 1 | 1 | 0 | 0.21 | 81.3 | 0 | 0 | 0 | 0 | 0.374 |
| SENSOR_NOISE_SPIKES | 2 | 1 | 1 | 0.50 | 0.2 | 1 | 1 | 0 | 0 | 0.477 |
| COMMUNICATION_LOSS | 3 | 3 | 3 | 1.00 | 0.0 | 3 | 3 | 0 | 0 | 1.000 |

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
| SUCTION_STRAINER_CLOGGING | 3 | 3h | 0.9995 | 120 s | 1.00 | 1.00 | 1.00 | 0 |
| CAVITATION | 0 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | 2 | 6h | 0.9995 | 600 s | 0.50 | 1.00 | 0.67 | 0 |
| MISALIGNMENT | 3 | 6h | 0.9995 | 180 s | 0.67 | 1.00 | 0.80 | 0 |
| IMBALANCE | 1 | 6h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |
| IMPELLER_WEAR | 1 | 3h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |
| AIR_ENTRAINMENT | 2 | 3h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_DRIFT | 2 | 6h | 0.9995 | 120 s | 0.50 | 1.00 | 0.67 | 0 |
| SENSOR_STUCK | 2 | 3h | 0.9995 | 120 s | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_CALIBRATION_SHIFT | 1 | 6h | 0.9995 | 600 s | 0.00 | 0.00 | 0.00 | 0 |
| SENSOR_NOISE_SPIKES | 2 | 3h | 0.9995 | 60 s | 0.50 | 1.00 | 0.67 | 0 |
| COMMUNICATION_LOSS | 3 | 3h | 0.9995 | 600 s | 1.00 | 1.00 | 1.00 | 0 |

## Files

- `trials.csv`: every trial with all organizer metrics per group (`all/`, `val-orig/`, `val-new/`).
- `per_type_events.csv`, `per_type_alerts.csv`, `per_type_joined.csv`: per fault type for every trial.
- `window_auprc.csv`: window-level AUPRC per model, window and fault type (independent of the threshold).
- `alerts/`, `per_event/`: alert file (organizer format) and per-event scorer result of every trial.
- `composite_*.png`, `per_type_*.png`: figures. TensorBoard: `optimize/tensorboard/thr-window-high-v1/`.
- Optuna storage: `optimize/study.db` (study `thr-window-high-v1`).

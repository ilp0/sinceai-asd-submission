# Threshold and running-average study `persistence-v1`

Created 2026-11-07 20:24 EET by `optimize/study.py`. Objective: organizer composite score on all 7 validation pumps (PUMP-08/09 and 5 generated pumps, 24 observable events). Selection and score use the same validation events, so the best values are optimistic.

Models (frozen last checkpoints of experiment 6, round 3):

- 3h: `rp3-3h-r32-v1` `checkpoint_last_step11500` (step 11500), 180 min context, predictions every 10 s
- 6h: `rp3-6h-r32-v1` `checkpoint_last_step14750` (step 14750), 360 min context, predictions every 20 s

Fixed rules: {"cooldown_minutes": 720, "global_gap_minutes": 5}. Persistence 0 min means one window. A running-average window shorter than the prediction stride holds one sample (the raw probability).

## Top 10 settings

| # | Model | Threshold | Window | Persistence | Composite all | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3h | 0.9 | 0 s | 10 min | **83.2** | 77.4 | 86.5 | 0.81 | 0.73 | 0.92 | 0.75 | 0.88 | 0.16 | 78 |
| 2 | 3h | 0.85 | 0 s | 30 min | **83.2** | 77.4 | 86.6 | 0.84 | 0.81 | 0.88 | 0.75 | 0.84 | 0.10 | 73 |
| 3 | 3h | 0.9 | 60 s | 30 min | **83.2** | 79.2 | 85.4 | 0.84 | 0.81 | 0.88 | 0.75 | 0.84 | 0.10 | 73 |
| 4 | 3h | 0.9 | 0 s | 20 min | **83.1** | 79.2 | 85.4 | 0.84 | 0.81 | 0.88 | 0.75 | 0.84 | 0.10 | 71 |
| 5 | 3h | 0.85 | 0 s | 20 min | **82.8** | 75.7 | 86.9 | 0.81 | 0.73 | 0.92 | 0.75 | 0.86 | 0.16 | 78 |
| 6 | 3h | 0.8 | 0 s | 30 min | **82.5** | 75.7 | 86.3 | 0.81 | 0.73 | 0.92 | 0.75 | 0.86 | 0.16 | 83 |
| 7 | 3h | 0.85 | 180 s | 30 min | **81.9** | 75.7 | 85.3 | 0.80 | 0.71 | 0.92 | 0.75 | 0.86 | 0.18 | 89 |
| 8 | 3h | 0.9 | 60 s | 20 min | **81.8** | 77.4 | 84.4 | 0.81 | 0.75 | 0.88 | 0.75 | 0.84 | 0.14 | 76 |
| 9 | 3h | 0.9 | 0 s | 15 min | **81.8** | 79.2 | 83.3 | 0.81 | 0.75 | 0.88 | 0.75 | 0.84 | 0.14 | 74 |
| 10 | 3h | 0.95 | 60 s | 3 min | **81.7** | 81.3 | 82.0 | 0.78 | 0.66 | 0.96 | 0.75 | 0.89 | 0.24 | 85 |

## Reference: current submission rule on the same predictions

Threshold 0.9, persistence 15 min, no running average (the rule of `submission/predictions_test.csv`).

| Model | Composite all | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| 3h | 81.8 | 79.2 | 83.3 | 0.75 | 0.88 | 0.75 | 0.14 |
| 6h | 75.4 | 80.6 | 72.6 | 0.83 | 0.83 | 0.54 | 0.08 |

## Model 3h: best setting threshold 0.9, window 0 s, persistence 10 min (composite 83.2)

### Composite (all pumps) by threshold and window (best persistence)

| Threshold | 0 s | 60 s | 180 s |
|---|---|---|---|
| 0.8 | 82.5 | 78.9 | 76.4 |
| 0.85 | 83.2 | 81.6 | 81.9 |
| 0.9 | 83.2 | 83.2 | 81.7 |
| 0.95 | 79.5 | 81.7 | 80.6 |
| 0.98 | 80.0 | 80.2 | 80.1 |
| 0.99 | 80.0 | 80.3 | 80.3 |
| 0.995 | 79.9 | 81.0 | 80.2 |

### Composite (all pumps) by threshold and persistence (best window)

| Threshold | 0 min | 3 min | 5 min | 10 min | 15 min | 20 min | 30 min |
|---|---|---|---|---|---|---|---|
| 0.8 | 61.1 | 72.5 | 75.1 | 77.5 | 78.9 | 81.6 | 82.5 |
| 0.85 | 63.9 | 75.5 | 75.6 | 80.5 | 81.3 | 82.8 | 83.2 |
| 0.9 | 72.3 | 79.6 | 80.9 | 83.2 | 81.8 | 83.1 | 83.2 |
| 0.95 | 80.6 | 81.7 | 78.9 | 78.1 | 78.8 | 79.5 | 79.5 |
| 0.98 | 77.7 | 78.1 | 79.5 | 80.0 | 79.8 | 80.2 | 80.1 |
| 0.99 | 78.1 | 80.3 | 80.3 | 80.2 | 79.9 | 79.3 | 76.5 |
| 0.995 | 81.0 | 80.1 | 79.9 | 78.9 | 76.5 | 76.5 | 74.1 |

### Per fault type at the best setting

Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of that type; wrong = inside the window of another type; outside = false alert).

| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |
|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 2 | 2 | 1.00 | -0.1 | 11 | 11 | 0 | 0 | 0.963 |
| SUCTION_STRAINER_CLOGGING | 3 | 3 | 3 | 0.97 | 13.9 | 13 | 13 | 0 | 0 | 0.875 |
| CAVITATION | 0 | – | – | – | – | 0 | 0 | 0 | 0 | – |
| DISCHARGE_RESTRICTION | 2 | 2 | 1 | 0.97 | 2.2 | 8 | 4 | 4 | 0 | 0.517 |
| MISALIGNMENT | 3 | 3 | 1 | 0.82 | 12.4 | 9 | 6 | 2 | 1 | 0.617 |
| IMBALANCE | 1 | 1 | 0 | 1.00 | 1.3 | 10 | 2 | 8 | 0 | 0.156 |
| IMPELLER_WEAR | 1 | 1 | 1 | 1.00 | 3.2 | 7 | 6 | 1 | 0 | 0.650 |
| AIR_ENTRAINMENT | 2 | 2 | 2 | 1.00 | 0.5 | 5 | 2 | 3 | 0 | 0.861 |
| SENSOR_DRIFT | 2 | 1 | 1 | 0.46 | 13.7 | 5 | 5 | 0 | 0 | 0.616 |
| SENSOR_STUCK | 2 | 2 | 2 | 1.00 | 1.0 | 3 | 3 | 0 | 0 | 0.610 |
| SENSOR_CALIBRATION_SHIFT | 1 | 1 | 1 | 0.90 | 15.9 | 3 | 1 | 2 | 0 | 0.371 |
| SENSOR_NOISE_SPIKES | 2 | 1 | 1 | 0.50 | 0.3 | 1 | 1 | 0 | 0 | 0.439 |
| COMMUNICATION_LOSS | 3 | 3 | 3 | 1.00 | 0.2 | 3 | 3 | 0 | 0 | 1.000 |

## Model 6h: best setting threshold 0.85, window 0 s, persistence 30 min (composite 80.9)

### Composite (all pumps) by threshold and window (best persistence)

| Threshold | 0 s | 60 s | 180 s |
|---|---|---|---|
| 0.8 | 78.6 | 77.5 | 76.2 |
| 0.85 | 80.9 | 79.1 | 78.3 |
| 0.9 | 78.9 | 80.4 | 77.8 |
| 0.95 | 79.9 | 76.0 | 79.9 |
| 0.98 | 76.0 | 76.8 | 77.5 |
| 0.99 | 77.8 | 77.5 | 78.5 |
| 0.995 | 76.4 | 75.9 | 75.7 |

### Composite (all pumps) by threshold and persistence (best window)

| Threshold | 0 min | 3 min | 5 min | 10 min | 15 min | 20 min | 30 min |
|---|---|---|---|---|---|---|---|
| 0.8 | 67.4 | 72.6 | 71.0 | 74.7 | 75.6 | 76.4 | 78.6 |
| 0.85 | 66.4 | 72.4 | 73.6 | 74.5 | 76.6 | 78.5 | 80.9 |
| 0.9 | 68.7 | 77.4 | 75.5 | 78.6 | 78.1 | 78.9 | 80.4 |
| 0.95 | 77.3 | 79.9 | 79.9 | 76.0 | 76.0 | 76.3 | 76.2 |
| 0.98 | 77.5 | 76.8 | 76.0 | 74.5 | 72.1 | 73.1 | 72.3 |
| 0.99 | 78.5 | 77.8 | 77.8 | 72.3 | 72.3 | 72.0 | 67.5 |
| 0.995 | 76.4 | 75.6 | 72.3 | 69.8 | 69.8 | 64.5 | 59.9 |

### Per fault type at the best setting

Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of that type; wrong = inside the window of another type; outside = false alert).

| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |
|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 2 | 2 | 1.00 | 0.4 | 11 | 11 | 0 | 0 | 0.935 |
| SUCTION_STRAINER_CLOGGING | 3 | 3 | 3 | 0.97 | 8.6 | 13 | 12 | 1 | 0 | 0.875 |
| CAVITATION | 0 | – | – | – | – | 0 | 0 | 0 | 0 | – |
| DISCHARGE_RESTRICTION | 2 | 2 | 1 | 1.00 | -2.1 | 4 | 4 | 0 | 0 | 0.618 |
| MISALIGNMENT | 3 | 3 | 1 | 0.84 | 3.2 | 9 | 8 | 1 | 0 | 0.735 |
| IMBALANCE | 1 | 1 | 1 | 1.00 | 3.6 | 4 | 2 | 2 | 0 | 0.715 |
| IMPELLER_WEAR | 1 | 1 | 1 | 0.98 | 8.0 | 9 | 5 | 4 | 0 | 0.630 |
| AIR_ENTRAINMENT | 2 | 2 | 2 | 1.00 | 1.3 | 2 | 2 | 0 | 0 | 0.951 |
| SENSOR_DRIFT | 2 | 1 | 1 | 0.43 | 21.4 | 4 | 3 | 1 | 0 | 0.512 |
| SENSOR_STUCK | 2 | 0 | 0 | 0.00 | – | 0 | 0 | 0 | 0 | 0.594 |
| SENSOR_CALIBRATION_SHIFT | 1 | 1 | 1 | 0.89 | 16.5 | 7 | 2 | 5 | 0 | 0.261 |
| SENSOR_NOISE_SPIKES | 2 | 2 | 0 | 0.98 | 5.1 | 0 | 0 | 0 | 0 | 0.124 |
| COMMUNICATION_LOSS | 3 | 3 | 3 | 1.00 | 0.6 | 3 | 3 | 0 | 0 | 0.999 |

## Best setting for each fault type

Type score = harmonic mean of type recall (events of the type detected with the correct type) and type precision (alert bursts that name the type and fall inside an event window of that type). Ties go to the higher threshold. A hint for per-class thresholds; few events per type, so the values are noisy.

| Fault type | Events | Model | Threshold | Window | Type recall | Type precision | Type score | Outside alerts |
|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 6h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |
| SUCTION_STRAINER_CLOGGING | 3 | 3h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |
| CAVITATION | 0 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | 2 | 6h | 0.8 | 180 s, p 0 min | 1.00 | 0.55 | 0.71 | 0 |
| MISALIGNMENT | 3 | 6h | 0.995 | 180 s, p 30 min | 0.67 | 1.00 | 0.80 | 0 |
| IMBALANCE | 1 | 6h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |
| IMPELLER_WEAR | 1 | 6h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |
| AIR_ENTRAINMENT | 2 | 3h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_DRIFT | 2 | 6h | 0.995 | 180 s, p 15 min | 0.50 | 1.00 | 0.67 | 0 |
| SENSOR_STUCK | 2 | 3h | 0.995 | 180 s, p 20 min | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_CALIBRATION_SHIFT | 1 | 3h | 0.95 | 180 s, p 5 min | 1.00 | 0.50 | 0.67 | 0 |
| SENSOR_NOISE_SPIKES | 2 | 3h | 0.85 | 0 s, p 0 min | 1.00 | 1.00 | 1.00 | 0 |
| COMMUNICATION_LOSS | 3 | 3h | 0.995 | 180 s, p 30 min | 1.00 | 1.00 | 1.00 | 0 |

## Files

- `trials.csv`: every trial with all organizer metrics per group (`all/`, `val-orig/`, `val-new/`).
- `per_type_events.csv`, `per_type_alerts.csv`, `per_type_joined.csv`: per fault type for every trial.
- `window_auprc.csv`: window-level AUPRC per model, window and fault type (independent of the threshold).
- `alerts/`, `per_event/`: alert file (organizer format) and per-event scorer result of every trial.
- `composite_*.png`, `per_type_*.png`: figures. TensorBoard: `optimize/tensorboard/persistence-v1/`.
- Optuna storage: `optimize/study.db` (study `persistence-v1`).

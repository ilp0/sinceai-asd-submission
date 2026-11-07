# Threshold and running-average study `thr-window-6h-v1`

Created 2026-11-07 20:07 EET by `optimize/study.py`. Objective: organizer composite score on all 7 validation pumps (PUMP-08/09 and 5 generated pumps, 24 observable events). Selection and score use the same validation events, so the best values are optimistic.

Models (frozen last checkpoints of experiment 6, round 3):

- 6h: `rp3-6h-r32-v1` `checkpoint_last_step14750` (step 14750), 360 min context, predictions every 20 s

Fixed rules: {"cooldown_minutes": 720, "global_gap_minutes": 5, "persistence_s": 0}. Persistence 0 s means one window. A running-average window shorter than the prediction stride holds one sample (the raw probability).

## Top 10 settings

| # | Model | Threshold | Window | Composite all | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6h | 0.99 | 30 s | **77.4** | 83.0 | 74.2 | 0.75 | 0.63 | 0.92 | 0.67 | 0.88 | 0.27 | 82 |
| 2 | 6h | 0.99 | 60 s | **76.6** | 76.4 | 76.8 | 0.76 | 0.68 | 0.88 | 0.67 | 0.81 | 0.20 | 75 |
| 3 | 6h | 0.99 | 5 s | **73.4** | 76.9 | 71.2 | 0.66 | 0.51 | 0.92 | 0.67 | 0.88 | 0.43 | 96 |
| 4 | 6h | 0.99 | 15 s | **73.4** | 76.9 | 71.2 | 0.66 | 0.51 | 0.92 | 0.67 | 0.88 | 0.43 | 96 |
| 5 | 6h | 0.95 | 60 s | **70.3** | 70.1 | 70.1 | 0.56 | 0.40 | 0.96 | 0.67 | 0.94 | 0.71 | 127 |
| 6 | 6h | 0.95 | 30 s | **69.5** | 69.2 | 69.5 | 0.55 | 0.39 | 0.96 | 0.67 | 0.94 | 0.73 | 134 |
| 7 | 6h | 0.95 | 5 s | **67.9** | 70.8 | 66.2 | 0.53 | 0.36 | 1.00 | 0.62 | 0.98 | 0.86 | 145 |
| 8 | 6h | 0.95 | 15 s | **67.9** | 70.8 | 66.2 | 0.53 | 0.36 | 1.00 | 0.62 | 0.98 | 0.86 | 145 |
| 9 | 6h | 0.9 | 60 s | **67.6** | 70.8 | 65.7 | 0.54 | 0.37 | 1.00 | 0.58 | 0.98 | 0.84 | 145 |
| 10 | 6h | 0.85 | 60 s | **65.3** | 62.2 | 67.2 | 0.46 | 0.30 | 0.96 | 0.71 | 0.94 | 1.10 | 164 |

## Reference: current submission rule on the same predictions

Threshold 0.9, persistence 15 min, no running average (the rule of `submission/predictions_test.csv`).

| Model | Composite all | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| 6h | 75.4 | 80.6 | 72.6 | 0.83 | 0.83 | 0.54 | 0.08 |

## Model 6h: best setting threshold 0.99, window 30 s (composite 77.4)

### Composite (all pumps) by threshold and window

| Threshold | 5 s | 15 s | 30 s | 60 s |
|---|---|---|---|---|
| 0.7 | 51.3 | 51.3 | 50.9 | 52.6 |
| 0.8 | 56.1 | 56.1 | 60.1 | 62.4 |
| 0.85 | 55.5 | 55.5 | 62.2 | 65.3 |
| 0.9 | 61.6 | 61.6 | 64.4 | 67.6 |
| 0.95 | 67.9 | 67.9 | 69.5 | 70.3 |
| 0.99 | 73.4 | 73.4 | 77.4 | 76.6 |

### Per fault type at the best setting

Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of that type; wrong = inside the window of another type; outside = false alert).

| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |
|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 2 | 2 | 1.00 | 2.8 | 12 | 11 | 1 | 0 | 0.935 |
| SUCTION_STRAINER_CLOGGING | 3 | 3 | 3 | 0.97 | 8.9 | 14 | 13 | 1 | 0 | 0.877 |
| CAVITATION | 0 | – | – | – | – | 0 | 0 | 0 | 0 | – |
| DISCHARGE_RESTRICTION | 2 | 2 | 1 | 1.00 | -1.0 | 6 | 4 | 2 | 0 | 0.617 |
| MISALIGNMENT | 3 | 3 | 1 | 0.87 | 1.6 | 11 | 8 | 2 | 1 | 0.735 |
| IMBALANCE | 1 | 1 | 0 | 1.00 | 1.3 | 8 | 2 | 5 | 1 | 0.718 |
| IMPELLER_WEAR | 1 | 1 | 1 | 1.00 | 2.6 | 13 | 7 | 6 | 0 | 0.629 |
| AIR_ENTRAINMENT | 2 | 2 | 2 | 1.00 | 0.4 | 3 | 2 | 0 | 1 | 0.953 |
| SENSOR_DRIFT | 2 | 1 | 1 | 0.31 | 45.5 | 4 | 2 | 2 | 0 | 0.516 |
| SENSOR_STUCK | 2 | 2 | 2 | 1.00 | 4.7 | 2 | 2 | 0 | 0 | 0.604 |
| SENSOR_CALIBRATION_SHIFT | 1 | 0 | 0 | 0.00 | – | 6 | 0 | 6 | 0 | 0.262 |
| SENSOR_NOISE_SPIKES | 2 | 2 | 0 | 1.00 | 4.7 | 0 | 0 | 0 | 0 | 0.128 |
| COMMUNICATION_LOSS | 3 | 3 | 3 | 1.00 | 0.1 | 3 | 3 | 0 | 0 | 0.999 |

## Best setting for each fault type

Type score = harmonic mean of type recall (events of the type detected with the correct type) and type precision (alert bursts that name the type and fall inside an event window of that type). Ties go to the higher threshold. A hint for per-class thresholds; few events per type, so the values are noisy.

| Fault type | Events | Model | Threshold | Window | Type recall | Type precision | Type score | Outside alerts |
|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | 2 | 6h | 0.99 | 15 s | 1.00 | 0.92 | 0.96 | 0 |
| SUCTION_STRAINER_CLOGGING | 3 | 6h | 0.99 | 60 s | 1.00 | 0.93 | 0.96 | 0 |
| CAVITATION | 0 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | 2 | 6h | 0.9 | 30 s | 1.00 | 0.50 | 0.67 | 0 |
| MISALIGNMENT | 3 | 6h | 0.99 | 60 s | 0.33 | 0.80 | 0.47 | 1 |
| IMBALANCE | 1 | 6h | 0.99 | 60 s | 1.00 | 0.25 | 0.40 | 1 |
| IMPELLER_WEAR | 1 | 6h | 0.99 | 60 s | 1.00 | 0.64 | 0.78 | 0 |
| AIR_ENTRAINMENT | 2 | 6h | 0.99 | 60 s | 1.00 | 0.67 | 0.80 | 1 |
| SENSOR_DRIFT | 2 | 6h | 0.99 | 60 s | 0.50 | 0.67 | 0.57 | 0 |
| SENSOR_STUCK | 2 | 6h | 0.99 | 30 s | 1.00 | 1.00 | 1.00 | 0 |
| SENSOR_CALIBRATION_SHIFT | 1 | 6h | 0.8 | 60 s | 1.00 | 0.35 | 0.52 | 3 |
| SENSOR_NOISE_SPIKES | 2 | 6h | 0.95 | 60 s | 0.50 | 1.00 | 0.67 | 0 |
| COMMUNICATION_LOSS | 3 | 6h | 0.99 | 60 s | 1.00 | 1.00 | 1.00 | 0 |

## Files

- `trials.csv`: every trial with all organizer metrics per group (`all/`, `val-orig/`, `val-new/`).
- `per_type_events.csv`, `per_type_alerts.csv`, `per_type_joined.csv`: per fault type for every trial.
- `window_auprc.csv`: window-level AUPRC per model, window and fault type (independent of the threshold).
- `alerts/`, `per_event/`: alert file (organizer format) and per-event scorer result of every trial.
- `composite_*.png`, `per_type_*.png`: figures. TensorBoard: `optimize/tensorboard/thr-window-6h-v1/`.
- Optuna storage: `optimize/study.db` (study `thr-window-6h-v1`).

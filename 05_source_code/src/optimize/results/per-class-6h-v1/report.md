# Per-class thresholds, model 6h (`per-class-6h-v1`)

Model `rp3-6h-r32-v1` `checkpoint_last_step14750`, predictions every 20 s. Rules: {"cooldown_minutes": 720, "global_gap_minutes": 5}, persistence one window. Levels per class: 0.9, 0.95, 0.97, 0.98, 0.99, 0.993, 0.995, 0.997, 0.999, off. Windows searched: [30, 60, 180] s.

## Scores (organizer composite)

`fit` = chosen and scored on the same 7 pumps (optimistic). `lopo` = for each pump, chosen on the other 6 pumps and applied to it; the 7 held-out alert sets scored together.

| Method | All 7 | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|
| global_fit | **78.5** | 80.5 | 77.6 | 0.83 | 0.83 | 0.83 | 0.67 | 0.78 | 0.08 | 64 |
| global_lopo | **69.7** | 73.1 | 67.6 | 0.69 | 0.61 | 0.79 | 0.58 | 0.75 | 0.24 | 72 |
| per_class_fit | **87.5** | 89.1 | 86.9 | 0.90 | 0.85 | 0.96 | 0.79 | 0.89 | 0.08 | 76 |
| per_class_lopo | **70.2** | 70.2 | 70.2 | 0.70 | 0.63 | 0.79 | 0.58 | 0.75 | 0.22 | 66 |

Global fit: threshold 0.99, window 180 s.

## Per-class thresholds chosen on all 7 pumps (window 180 s)

The fold columns show the value chosen without each pump: a stable class has the same value in most folds.

| Fault type | Fit | new-01 | new-02 | new-03 | new-04 | new-05 | PUMP-08 | PUMP-09 | Events | Detected | Type correct | Alerts | Correct | Wrong | Outside |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | **0.99** | 0.99 | 0.997 | 0.99 | 0.99 | 0.99 | off | 0.99 | 2 | 2 | 2 | 11 | 11 | 0 | 0 |
| SUCTION_STRAINER_CLOGGING | **0.95** | 0.95 | 0.97 | 0.95 | 0.97 | 0.995 | 0.97 | 0.95 | 3 | 3 | 3 | 16 | 13 | 3 | 0 |
| CAVITATION | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | **0.9** | 0.9 | 0.999 | 0.9 | 0.9 | 0.99 | 0.999 | 0.9 | 2 | 2 | 2 | 9 | 5 | 4 | 0 |
| MISALIGNMENT | **0.99** | 0.99 | 0.9 | 0.99 | 0.99 | 0.99 | 0.9 | off | 3 | 3 | 1 | 9 | 8 | 1 | 0 |
| IMBALANCE | **0.999** | 0.99 | off | 0.999 | 0.999 | 0.995 | off | 0.999 | 1 | 1 | 1 | 2 | 2 | 0 | 0 |
| IMPELLER_WEAR | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 1 | 1 | 1 | 9 | 6 | 3 | 0 |
| AIR_ENTRAINMENT | **0.99** | 0.99 | 0.995 | 0.99 | 0.99 | 0.99 | 0.995 | 0.99 | 2 | 2 | 2 | 2 | 2 | 0 | 0 |
| SENSOR_DRIFT | **0.97** | 0.97 | 0.99 | 0.97 | 0.97 | 0.97 | 0.97 | 0.97 | 2 | 1 | 1 | 5 | 4 | 1 | 0 |
| SENSOR_STUCK | **0.9** | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 2 | 2 | 2 | 2 | 2 | 0 | 0 |
| SENSOR_CALIBRATION_SHIFT | **0.97** | 0.97 | 0.99 | 0.99 | 0.95 | 0.97 | 0.99 | 0.97 | 1 | 1 | 0 | 7 | 0 | 7 | 0 |
| SENSOR_NOISE_SPIKES | **0.9** | 0.9 | 0.99 | 0.9 | 0.9 | 0.9 | 0.95 | 0.9 | 2 | 2 | 1 | 1 | 1 | 0 | 0 |
| COMMUNICATION_LOSS | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 3 | 3 | 3 | 3 | 3 | 0 | 0 |

Fold windows: GEN-val6-45001-01: 180 s, GEN-val6-45001-02: 60 s, GEN-val6-45001-03: 180 s, GEN-val6-45001-04: 180 s, GEN-val6-45001-05: 180 s, PUMP-08: 60 s, PUMP-09: 180 s

Done in 165 s.

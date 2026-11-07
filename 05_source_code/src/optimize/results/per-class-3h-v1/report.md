# Per-class thresholds, model 3h (`per-class-3h-v1`)

Model `rp3-3h-r32-v1` `checkpoint_last_step11500`, predictions every 10 s. Rules: {"cooldown_minutes": 720, "global_gap_minutes": 5}, persistence one window. Levels per class: 0.9, 0.95, 0.97, 0.98, 0.99, 0.993, 0.995, 0.997, 0.999, off. Windows searched: [30, 60, 180] s.

## Scores (organizer composite)

`fit` = chosen and scored on the same 7 pumps (optimistic). `lopo` = for each pump, chosen on the other 6 pumps and applied to it; the 7 held-out alert sets scored together.

| Method | All 7 | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |
|---|---|---|---|---|---|---|---|---|---|---|
| global_fit | **81.2** | 81.3 | 81.2 | 0.77 | 0.64 | 0.96 | 0.75 | 0.89 | 0.27 | 87 |
| global_lopo | **73.9** | 77.4 | 72.0 | 0.69 | 0.61 | 0.79 | 0.71 | 0.77 | 0.24 | 74 |
| per_class_fit | **85.5** | 78.2 | 89.8 | 0.88 | 0.85 | 0.92 | 0.75 | 0.86 | 0.08 | 80 |
| per_class_lopo | **73.3** | 74.5 | 72.7 | 0.73 | 0.65 | 0.83 | 0.62 | 0.77 | 0.22 | 78 |

Global fit: threshold 0.95, window 300 s.

## Per-class thresholds chosen on all 7 pumps (window 60 s)

The fold columns show the value chosen without each pump: a stable class has the same value in most folds.

| Fault type | Fit | new-01 | new-02 | new-03 | new-04 | new-05 | PUMP-08 | PUMP-09 | Events | Detected | Type correct | Alerts | Correct | Wrong | Outside |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BEARING_WEAR | **0.993** | 0.993 | 0.993 | 0.993 | 0.99 | 0.99 | 0.993 | 0.993 | 2 | 2 | 2 | 11 | 11 | 0 | 0 |
| SUCTION_STRAINER_CLOGGING | **0.99** | 0.98 | 0.99 | 0.99 | 0.97 | 0.97 | 0.99 | 0.99 | 3 | 3 | 3 | 12 | 12 | 0 | 0 |
| CAVITATION | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | – | – | – | – | – | – | – |
| DISCHARGE_RESTRICTION | **0.95** | 0.95 | 0.95 | 0.993 | 0.9 | 0.9 | 0.993 | 0.95 | 2 | 2 | 1 | 10 | 4 | 6 | 0 |
| MISALIGNMENT | **off** | off | 0.95 | off | off | off | off | off | 3 | 3 | 0 | – | – | – | – |
| IMBALANCE | **0.9** | 0.9 | off | 0.9 | 0.9 | 0.9 | 0.9 | 0.9 | 1 | 1 | 1 | 15 | 2 | 13 | 0 |
| IMPELLER_WEAR | **0.95** | 0.95 | 0.95 | 0.95 | 0.99 | 0.99 | 0.95 | 0.95 | 1 | 1 | 1 | 9 | 7 | 2 | 0 |
| AIR_ENTRAINMENT | **0.995** | 0.995 | 0.995 | 0.995 | 0.9 | 0.995 | 0.995 | 0.995 | 2 | 2 | 2 | 2 | 2 | 0 | 0 |
| SENSOR_DRIFT | **0.97** | 0.97 | 0.97 | 0.97 | 0.99 | 0.95 | 0.9 | 0.97 | 2 | 1 | 1 | 6 | 6 | 0 | 0 |
| SENSOR_STUCK | **0.9** | 0.9 | 0.9 | 0.9 | 0.9 | 0.99 | 0.99 | 0.9 | 2 | 2 | 2 | 4 | 3 | 1 | 0 |
| SENSOR_CALIBRATION_SHIFT | **0.95** | 0.97 | 0.95 | 0.95 | 0.95 | 0.99 | 0.99 | 0.95 | 1 | 1 | 1 | 7 | 1 | 5 | 1 |
| SENSOR_NOISE_SPIKES | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 2 | 1 | 1 | 1 | 1 | 0 | 0 |
| COMMUNICATION_LOSS | **0.99** | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 0.99 | 3 | 3 | 3 | 3 | 3 | 0 | 0 |

Fold windows: GEN-val6-45001-01: 60 s, GEN-val6-45001-02: 60 s, GEN-val6-45001-03: 60 s, GEN-val6-45001-04: 180 s, GEN-val6-45001-05: 180 s, PUMP-08: 60 s, PUMP-09: 60 s

Done in 169 s.

# Leave-one-pump-out: study `persistence-v1`

294 trials can be selected. For each pump, the setting comes from the other 6 pumps. The grid itself (threshold, window and persistence values, the models) was designed after earlier studies on all 7 pumps, so this estimate is still a little optimistic.

| Estimate | All 7 | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| Best trial on all 7 (optimistic) | 83.2 | 77.4 | 86.5 | 0.73 | 0.92 | 0.75 | 0.16 |
| LOPO (held out) | **71.6** | 75.7 | 69.2 | 0.58 | 0.79 | 0.67 | 0.29 |

Best trial on all 7: model=3h, threshold=0.9, window_s=0, persistence_min=10.0

| Held-out pump | Selected setting | Composite on the other 6 |
|---|---|---|
| val-new-45001/GEN-val6-45001-01 | model=6h, threshold=0.95, window_s=180, persistence_min=5.0 | 83.94 |
| val-new-45001/GEN-val6-45001-02 | model=3h, threshold=0.85, window_s=0, persistence_min=30.0 | 83.58 |
| val-new-45001/GEN-val6-45001-03 | model=3h, threshold=0.9, window_s=0, persistence_min=10.0 | 83.05 |
| val-new-45001/GEN-val6-45001-04 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 80.99 |
| val-new-45001/GEN-val6-45001-05 | model=3h, threshold=0.99, window_s=180, persistence_min=3.0 | 85.34 |
| val-orig/PUMP-08 | model=3h, threshold=0.9, window_s=0, persistence_min=10.0 | 83.71 |
| val-orig/PUMP-09 | model=3h, threshold=0.85, window_s=0, persistence_min=20.0 | 85.75 |

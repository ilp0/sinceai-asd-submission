# Leave-one-pump-out: study `persistence-v1` model 6h

147 trials can be selected. For each pump, the setting comes from the other 6 pumps. The grid itself (threshold, window and persistence values, the models) was designed after earlier studies on all 7 pumps, so this estimate is still a little optimistic.

| Estimate | All 7 | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |
|---|---|---|---|---|---|---|---|
| Best trial on all 7 (optimistic) | 80.9 | 80.5 | 81.3 | 0.84 | 0.88 | 0.67 | 0.08 |
| LOPO (held out) | **73.2** | 80.5 | 69.7 | 0.70 | 0.79 | 0.62 | 0.16 |

Best trial on all 7: model=6h, threshold=0.85, window_s=0, persistence_min=30.0

| Held-out pump | Selected setting | Composite on the other 6 |
|---|---|---|
| val-new-45001/GEN-val6-45001-01 | model=6h, threshold=0.95, window_s=180, persistence_min=5.0 | 83.94 |
| val-new-45001/GEN-val6-45001-02 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 79.9 |
| val-new-45001/GEN-val6-45001-03 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 80.87 |
| val-new-45001/GEN-val6-45001-04 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 80.99 |
| val-new-45001/GEN-val6-45001-05 | model=6h, threshold=0.99, window_s=180, persistence_min=0.0 | 83.34 |
| val-orig/PUMP-08 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 78.46 |
| val-orig/PUMP-09 | model=6h, threshold=0.85, window_s=0, persistence_min=30.0 | 83.81 |

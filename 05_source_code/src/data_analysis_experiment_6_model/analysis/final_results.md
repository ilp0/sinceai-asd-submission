# Experiment 6, round 3 against causal B1

Threshold 0.9. Fixed rule: persistence 15 min. Old rule: persistence 3 min. Organizer scorer.
`best_on_val` is chosen on the same validation pumps: optimistic.

| Run | Checkpoint | Rule | All 7 | PUMP-08/09 | val-new | Precision (all) | False alerts/day (all) | Recall (all) |
|---|---|---|---|---|---|---|---|---|
| **B1** | — | — | 65.0 | 78.2 | 57.0 | 0.85 | 0.06 | 0.71 |
| rp3-3h-r32-v1 | last 11500 | fixed_p15 | 78.1 | 74.8 | 79.9 | 0.58 | 0.33 | 0.92 |
| rp3-3h-r32-v1 | last 11500 | old_p3 | 69.9 | 64.6 | 72.9 | 0.41 | 0.67 | 0.96 |
| rp3-3h-r32-v1 | mean_last3 [11000, 11250, 11500] | fixed_p15 | 79.3 | 78.9 | 79.5 | 0.68 | 0.22 | 0.89 |
| rp3-3h-r32-v1 | mean_last3 [11000, 11250, 11500] | old_p3 | 70.5 | 62.7 | 75.1 | 0.43 | 0.61 | 0.93 |
| rp3-3h-r32-v1 | best_on_val 9000 | fixed_p15 | 82.4 | 80.9 | 83.3 | 0.70 | 0.20 | 0.96 |
| rp3-3h-r32-v1 | best_on_val 9000 | old_p3 | 71.7 | 65.0 | 75.6 | 0.45 | 0.55 | 0.92 |
| rp3-6h-r32-v1 | last 14750 | fixed_p15 | 77.5 | 80.6 | 76.2 | 0.72 | 0.16 | 0.88 |
| rp3-6h-r32-v1 | last 14750 | old_p3 | 68.4 | 72.2 | 66.4 | 0.36 | 0.84 | 0.96 |
| rp3-6h-r32-v1 | mean_last3 [14250, 14500, 14750] | fixed_p15 | 78.0 | 78.5 | 78.0 | 0.72 | 0.17 | 0.88 |
| rp3-6h-r32-v1 | mean_last3 [14250, 14500, 14750] | old_p3 | 69.6 | 72.8 | 67.9 | 0.39 | 0.76 | 0.97 |
| rp3-6h-r32-v1 | best_on_val 11250 | fixed_p15 | 81.6 | 74.7 | 85.6 | 0.69 | 0.20 | 0.92 |
| rp3-6h-r32-v1 | best_on_val 11250 | old_p3 | 75.1 | 75.2 | 74.9 | 0.48 | 0.53 | 1.00 |
| rp3-12h-r32-v1 | last 5750 | fixed_p15 | 68.1 | 58.9 | 73.3 | 0.67 | 0.18 | 0.75 |
| rp3-12h-r32-v1 | last 5750 | old_p3 | 56.9 | 57.0 | 56.7 | 0.30 | 0.98 | 0.88 |
| rp3-12h-r32-v1 | mean_last3 [5250, 5500, 5750] | fixed_p15 | 65.9 | 59.8 | 69.4 | 0.62 | 0.22 | 0.74 |
| rp3-12h-r32-v1 | mean_last3 [5250, 5500, 5750] | old_p3 | 55.3 | 48.8 | 59.0 | 0.33 | 0.82 | 0.81 |
| rp3-12h-r32-v1 | best_on_val 3250 | fixed_p15 | 69.8 | 68.6 | 70.4 | 0.63 | 0.22 | 0.79 |
| rp3-12h-r32-v1 | best_on_val 3250 | old_p3 | 58.6 | 56.6 | 59.9 | 0.36 | 0.78 | 0.88 |

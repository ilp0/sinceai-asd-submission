# UNKNOWN alerts on top of the frozen rule

| setting                                                |   composite |   unknown_alerts |   detected_by_unknown |   recall |   precision |   false_per_day |   chosen_in_folds |
|:-------------------------------------------------------|------------:|-----------------:|----------------------:|---------:|------------:|----------------:|------------------:|
| {"sum_thr": 0.6, "persistence_min": 60, "quiet_h": 24} |       82.59 |                8 |                     1 |    0.917 |       0.71  |           0.184 |                 6 |
| {"sum_thr": 1.3, "persistence_min": 30, "quiet_h": 24} |       82.59 |                6 |                     1 |    0.917 |       0.71  |           0.184 |                 0 |
| {"sum_thr": 1.0, "persistence_min": 60, "quiet_h": 24} |       82.59 |                6 |                     1 |    0.917 |       0.71  |           0.184 |                 0 |
| {"sum_thr": 0.8, "persistence_min": 60, "quiet_h": 24} |       82.59 |                7 |                     1 |    0.917 |       0.71  |           0.184 |                 0 |
| base (frozen rule)                                     |       81.82 |                0 |                     0 |    0.875 |       0.75  |           0.143 |                 1 |
| {"sum_thr": 1.6, "persistence_min": 60, "quiet_h": 12} |       81.82 |                0 |                     0 |    0.875 |       0.75  |           0.143 |                 0 |
| {"sum_thr": 1.6, "persistence_min": 60, "quiet_h": 24} |       81.82 |                0 |                     0 |    0.875 |       0.75  |           0.143 |                 0 |
| {"sum_thr": 1.6, "persistence_min": 30, "quiet_h": 12} |       81.47 |                3 |                     2 |    0.917 |       0.733 |           0.163 |                 0 |
| {"sum_thr": 1.6, "persistence_min": 30, "quiet_h": 24} |       81.47 |                2 |                     2 |    0.917 |       0.733 |           0.163 |                 0 |
| {"sum_thr": 1.3, "persistence_min": 15, "quiet_h": 12} |       81.41 |               13 |                     1 |    0.917 |       0.667 |           0.224 |                 0 |
| {"sum_thr": 1.0, "persistence_min": 30, "quiet_h": 12} |       81.41 |               13 |                     1 |    0.917 |       0.667 |           0.224 |                 0 |
| {"sum_thr": 1.3, "persistence_min": 30, "quiet_h": 12} |       81.03 |               11 |                     2 |    0.917 |       0.688 |           0.204 |                 0 |

Base: 81.82. LOPO with the choice among base + 30 UNKNOWN settings: 81.82.

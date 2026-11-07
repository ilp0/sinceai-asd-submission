# Source code and predictions

| Folder | Content |
|---|---|
| `predictions/` | **The test predictions** (`predictions_test.csv`, PUMP-10..12, organizer format, 34 alerts; the evidence text names the signals that the model's alert depends on), the same method on the validation pumps, the frozen alert rule and the occlusion results. |
| `src/data_analysis_experiment_6_model/` | The model: Timestral-28M backbone with LoRA and a multi-label fault head (13 fault types). Training, evaluation, benchmark and RunPod scripts. See its `README.md` and `HANDOVER.md`. |
| `src/optimize/` | The alert-rule study: threshold, running average and persistence, Optuna grid studies, per-class thresholds, leave-one-pump-out estimates, and `predict_test_fine.py`, which made the test predictions. See its `README.md`. |

Not included (data and dependencies): the organizer data package, the experiment-6 training data, the Timestral-28M base weights (experiment 2 `base_model/`, `vendor/`), the trained checkpoint `runs/rp3-3h-r32-v1/checkpoint_last_step11500.pt` (121 MB), the prediction parquet files and the Python environments.

## Reproduce the test predictions

The scripts expect the experiment-repository layout: `raw/<package>/RETROFIT_AI_PARTICIPANTS_2026/`, the base model in `data_analysis_experiment_2_lora/`, and the checkpoint under `data_analysis_experiment_6_model/runs/rp3-3h-r32-v1/`. `optimize/alerts.py` also reads `RETROFIT_PKG`, but the experiment-6 code (`analysis/predict_test.py`) finds the package only under `raw/`, so keep that layout (in this package: `src/raw/`).

```bash
cd src/optimize
python predict_test_fine.py predict --asset PUMP-10     # also PUMP-11, PUMP-12 (about 17 min each on an M5 Pro, MPS)
python predict_test_fine.py alerts --split test         # -> results/submission-fine/predictions_test.csv
python occlusion.py --split test                        # -> predictions_test_explained.csv (= predictions/predictions_test.csv)
```

Python 3.12 with torch, pandas, pyarrow, PyYAML, scipy and safetensors. The study scripts also need optuna, tensorboardX and matplotlib.

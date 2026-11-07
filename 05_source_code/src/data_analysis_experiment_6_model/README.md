# Experiment 5: Timestral-28M with a multi-label fault head

> **Note for the submission (8 November 2026).** We wrote this README for experiment 5, before any training. Experiment 6 trained this code on RunPod GPUs, so the status line below and the defaults (15 min input, rank-8 LoRA) are historical. The submitted model is run `rp3-3h-r32-v1` (`configs/rp3-3h-r32.yaml`: 3 h input at 10 s cells, LoRA rank 32, data `configs/runpod-full2.yaml`), checkpoint `checkpoint_last_step11500`. For experiment 6, read section 7 and `HANDOVER.md`. For the alert rule and the scores, read `../../predictions/README.md`. This package does not contain `configs/generated.yaml` and `lumi/`. `analysis/final_results.md` scores B1 with the experiment-1 re-implementation (65.0 on all 7 validation pumps); the other documents give 65.6 for the organizer B1.

This experiment removes the quantile forecasting head of Timestral-28M. A new head gives one probability for each fault type in the benchmark taxonomy. Each output is an independent sigmoid, so several faults can be active at the same time. The input is the last 15 minutes of telemetry from one pump.

Status (7 November 2026): code, configuration, LUMI scripts and tests are complete. No training has run. The only executed model passes are a forward and backward pass on CPU (`run.py smoke`) and an untrained prediction in the tests. No optimizer step occurred.

## 1. Architecture

```
15 min of 1 Hz telemetry, one pump                            (900 cells per row)
  │  per asset: robust z-score from the first 24 h of RUNNING data
  │  rows = available channels (≤ 14) + 4 derived rows; left-pad to 928 cells (29 patches of 32)
  ▼
┌──────────────────────── Timestral-28M backbone (pretrained) ────────────────────────┐
│ causal per-patch scaling + asinh → patch embedding  [values | missing flags] → 384  │
│ token sequence per row:  Enc_1 … Enc_29  ;  Q   (Q = pretrained forecast-query)     │
│ 12 blocks: time attention inside a row; variate attention across the rows of one    │
│ window in blocks 4, 8 and 12. Q reads every valid patch of its row.                 │
└──────────────────────────────────────────────────────────────────────────────────────┘
  │  quantile head (residual MLP 384 → 1 536 → 672 = 32 steps × 21 quantiles) is deleted
  ▼  per row r:  Q_out (384) ⊕ channel embedding (32) ⊕ 6 window statistics
Row projection  Linear → GELU → Dropout                          h_r ∈ R^256
  ▼
Class attention pooling: class k has a query q_k
  a_k,r = softmax_r( q_k · W_K h_r )        p_k = Σ_r a_k,r W_V h_r
  ▼
LayerNorm → shared MLP → per-class linear output  → 13 logits → sigmoid → P(fault_k active at t)
```

### 1.1 Input window

- Each window ends at an issue time t. It contains the cells in (t − 15 min, t]. The model reads no data after t, so it obeys the benchmark rule for causal alerts. A test checks this rule.
- `input.sample_period_s` sets the grid. The default is 1 s (900 cells). With 10 s, a window has 90 cells and 3 patches.
- Timestral uses patches of 32 cells. The loader adds unobserved cells on the left up to the next multiple of 32. Timestral ignores leading unobserved patches.
- One window is a group of rows. There is one row for each instrument that the asset has (`assets.csv: channels_available`). Missing instruments add no row.
- There are four derived rows: `running`, `row_present` (0 during gateway outages), and the `COMM_LOSS` and `OUT_OF_RANGE` quality bits. Missing samples stay as missing flags. They are not filled.

### 1.2 Normalization

Timestral normalizes each patch with causal statistics from its own window. This removes the absolute level of a signal, and the level is often the evidence for a fault, for example a high vibration value. The experiment therefore does two things:

1. Before the backbone, each channel becomes a robust z-score: (x − median) / (1.4826 × MAD). The statistics come from the first 24 h of RUNNING data of that asset. This is the same idea as baseline B1. No window ends inside these 24 h.
2. The head also receives six window statistics per row in z units: mean, standard deviation, last value, minimum, maximum and observed fraction. These keep the level information that the backbone removes.

### 1.3 Backbone pass

The backbone pass uses the same code path as the Timestral forecast without covariates (`_predict_context_only`), with one decoder token instead of a forecast horizon. The pretrained forecast-query token becomes a per-row summary token, similar to a CLS token. The time mask is causal between context patches. The summary token reads all valid patches of its row. Variate attention connects only rows with the same group id, so rows of different windows in one batch never mix.

### 1.4 Head

- Timestral treats rows as interchangeable. It does not know which row is vibration and which row is pressure. A learned channel embedding gives each row its identity.
- Class attention pooling gives each fault type its own attention over the rows. For example, bearing wear can attend to vibration rows and strainer clogging can attend to suction pressure. The attention weights are exported as the "strongest row" evidence for each alert.
- The output bias of each class starts at the log-odds of its expected positive rate. This keeps the first steps stable.
- The alternative `head.pooling: mean` uses a masked mean over rows and one linear output layer.

## 2. What is trained

| Part | `frozen` | `lora` (default) | `full` |
|---|---|---|---|
| Patch embedding, 12 transformer blocks | fixed | fixed, plus rank-8 LoRA on attention QKV and output (276 480 parameters) | trained at `backbone_learning_rate` |
| Forecast-query token (summary token, 384) | trained (`train_query_token`) | trained | trained |
| Last N blocks (`unfreeze_last_blocks`) | optional | optional | – |
| New head (312 909 parameters) | trained | trained | trained |
| Removed quantile head | – | – | – |

Measured with `run.py describe` on the default configuration: 26 530 509 parameters in total and 589 773 trainable (head 312 909, backbone LoRA and query token 276 864).

Training objective:

- Masked binary cross-entropy summed over the 13 classes. `loss.type: focal` selects focal loss.
- A (window, class) target has three states: 1 (positive), 0 (negative), or ignored (no loss).
- `pos_weight: auto` sets each class weight to (1 − r) / r, clipped to 1–20. Here r is the positive rate that the batch sampler produces, not the raw rate.
- Optimizer: AdamW, linear warmup, then cosine decay, gradient clipping at 1.0. Head, LoRA and query token use `learning_rate`. Other backbone weights use `backbone_learning_rate`.
- Model selection: `early_stopping.metric` of the config (experiment-5 configs: macro AUPRC; RunPod configs: `bench_all/composite_max`, the best composite over the benchmark thresholds on the validation assets). A check occurs every `eval_every` steps. Early stopping uses `patience_evals`. The best checkpoint is `runs/<name>/best.pt`.

### 2.1 Labels

At issue time t, class k is positive when an observable event of type k is active:

| Setting | Effect |
|---|---|
| `labels.start: detectable` (default) | positive from `detectable_utc`; the time from onset to detectable is ignored |
| `labels.start: onset` / `scoring` | positive from the onset, or from the start of the scoring window: max(onset, detectable − 6 h) |
| end | `end_utc`, or the end of the asset window for open-ended events; `end_pad_minutes` extends it |
| `lead_minutes` > 0 | positive when the event is active at any time in [t, t + lead]; this is an early-warning target |
| `ignore_unobservable` | events with `observable = False` mask their class for their full duration |
| `post_end_ignore_classes` | for 30 min after the end of an episode without repair (cavitation, air entrainment, sensor faults), the class is ignored, because the scorer still matches alerts there |

Labels of different classes are independent. For example, a calibration shift during bearing wear gives two positive targets in the same window.

### 2.2 Batches

`StepBatchSampler` draws `positive_fraction` of each batch from windows with at least one positive class. It draws `benign_fraction` from labelled benign windows, which are hard negatives such as start-up, load change and heavy weather. It draws the rest uniformly. Batch s depends only on (seed, s), so a resumed run sees the same batches.

## 3. Datasets and configuration

All settings are in YAML. A file can contain `inherit: base.yaml`. Every command accepts `--set key.path=value`.

| Configuration file | Train assets | Validation assets |
|---|---|---|
| `configs/base.yaml` | public PUMP-01..07 (26 observable events) | public PUMP-08, PUMP-09 (9 events) |
| `configs/generated.yaml` | public PUMP-01..07 plus the experiment-4 generated train set (100 pump-weeks, 288 observable events) | public PUMP-08, PUMP-09 plus the generated selection set (20 pump-weeks) |
| `configs/smoke.yaml` | PUMP-01 only, CPU, two steps | PUMP-08 |

Important settings:

| Key | Default | Meaning |
|---|---|---|
| `input.minutes` | 15 | input length |
| `input.sample_period_s` | 1 | grid period; larger values average cells |
| `input.channels`, `input.derived` | all 14 telemetry channels, 4 derived rows | backbone rows |
| `backbone.mode` | `lora` | `frozen`, `lora` or `full` |
| `backbone.path` | experiment-2 `base_model` | another Timestral export, for example 209M (also change `head.*` sizes if needed) |
| `head.pooling`, `head.token_pool`, `head.row_stats` | `class_attention`, `query`, true | head variants |
| `labels.classes`, `labels.start`, `labels.lead_minutes` | 13 types, `detectable`, 0 | targets |
| `data.sources`, `train_assets`, `val_assets`, `locked_assets` | see `base.yaml` | data sources and roles (glob patterns) |
| `data.train_stride_s`, `data.sampler.*` | 60 s, 0.5, 0.1 | candidate windows and batch mix |
| `train.*`, `loss.*` | see `base.yaml` | optimization |

The test assets (`public/PUMP-10..12` and `gen-test/*`) match `data.locked_assets`. The loader does not open a locked asset, and it stops with an error if a train or validation pattern selects one. `lumi/sync.sh` does not copy their telemetry.

Window counts for `base.yaml` (`run.py describe`):

| Role | Windows | Windows with ≥ 1 positive class | Benign windows |
|---|---:|---:|---:|
| train (60 s stride) | 60 487 | 51 828 | 11 317 |
| validation (60 s stride) | 17 282 | 14 981 | 4 170 |

## 4. Commands

Run from this directory. On the Mac, use `../../../data_analysis_expriment_1/.venv/bin/python` from the main checkout or any environment with torch, pandas, pyarrow and PyYAML.

```bash
python run.py prepare  --config configs/base.yaml    # per-asset caches under cache/<fingerprint>/
python run.py describe --config configs/base.yaml    # window counts, labels, parameter counts
python run.py smoke    --config configs/smoke.yaml   # one forward and backward pass, no optimizer step
python -m pytest -q tests                            # needs the smoke cache
python run.py train    --config configs/base.yaml [--stop-after-steps N]
python run.py evaluate --config configs/base.yaml    # predictions_val_best.parquet, metrics_val_best.json
python run.py alerts   --config configs/base.yaml    # alerts_val_best.csv in the submission format
```

Score the alert file with the organizer scorer (see `BENCHMARK_RULES.md`). Only the public validation assets can be scored there.

## 5. LUMI

The settings come from experiment 2: project `project_462001520`, container `lumi-multitorch-full-u24r72f21m50t211-20261028_090706.sif`, and one MI250X GCD per job.

1. Copy the code, base model, vendored Timestral and data to `/scratch/project_462001520/pump-timestral/mlhead-v1`. Use `lumi/sync.sh` for public data or `lumi/sync.sh generated` for the generated data too.
2. Build the caches on a CPU node with `sbatch lumi/prepare.sbatch configs/base.yaml`.
3. Run `ACTION=smoke sbatch lumi/train.sbatch configs/base.yaml` and compare its output with the CPU smoke result.
4. Train with `sbatch lumi/train.sbatch configs/base.yaml`. A resubmitted job continues from `runs/<name>/checkpoint.pt`.

Make sure that the container has PyYAML before the first job. Run `python -c "import yaml"` in the container to check. If it is missing, add it with `pip install --user pyyaml`. The default precision is fp32. Compare `run.precision=bf16` against fp32 before you use it.

The machine rules require a long-running job to run as an `lr` job. Before the real training starts, wrap `train --stop-after-steps` segments in an `lr` job, as experiment 2 did (`jobs/campaign.ts`). The checkpoint and the deterministic sampler already support segmented runs.

## 6. Limitations

- **Few events.** The public train split has 26 observable events across 13 classes. Each class has 1 to 4 events, often from one pump. Windows are many but correlated: the 60 487 training windows contain only 26 independent examples. A model trained on public data alone can learn pump identity instead of fault signatures. The generated set (`configs/generated.yaml`) increases this to about 314 train events.
- **Long events dominate.** Pre-existing and slow faults (bearing wear, impeller wear) cover days. Short episodes (cavitation, air entrainment, communication loss) cover minutes. Use per-class metrics, not only the macro value.
- **Pre-existing faults enter the baseline.** If a fault is present from the window start, the 24 h baseline contains it, and the z-scores hide it. Baseline B1 has the same problem.
- **15 minutes is short for slow faults.** Slow drifts such as bearing wear and strainer clogging develop over hours or days. In a 15-minute window, only the level in asset z units (row statistics) shows them, not the trend. Compare with `input.minutes: 60` or more at a coarser `sample_period_s`.
- **Validation was already inspected** in experiments 1 to 4. It is not a blind test.
- **Window metrics are not the benchmark score.** Use `run.py alerts` and the organizer scorer for the composite score.
- **Licence.** Fine-tuned weights are derivatives of Timestral-28M and stay under its modified MIT licence.

## 7. Experiment 6: fixed alert rule (7 November 2026)

User decision, 7 November 2026: the final results use **threshold 0.9 and persistence 15 windows** (15 minutes at
the 60 s validation stride). A class must stay at or above the threshold for 15 consecutive minutes before an alert
is issued. All other rules stay as in `configs/base.yaml`.

- Evidence: `analysis/gap_persistence.py` (results in `analysis/gap_persistence.json`, `logs/gap-persistence.log`).
  Mean of 26 round-3 checkpoints (3h and 6h, step 8000 on): composite on all 7 validation pumps 69.5 with
  persistence 3, 76.4 with persistence 15. Leave-one-pump-out chose persistence 15 or 30 for every pump and gave 75.1.
- Rejected: a 12 h alert gap per pump. It suppresses real second events (recall 0.92 to 0.65; composite 64.3).
- Round 3 is complete (7 November 2026). `configs/base.yaml` now has `predict.persistence_windows: 15`
  (15 min at the 60 s stride); `configs/rp3-12h-r32.yaml` has 22 (15 min at its 40 s stride). The rounds 1–3 ran with
  the old value 3; their config fingerprints therefore changed, and they must not be resumed. The `lr` items `zz-1-evaluate` and `zz-2-benchmark` use the old rule; `analysis/final_score.py` scores
  all saved checkpoints again with the fixed rule.
- Final table: `analysis/final_score.py` writes `analysis/final_results.md` (B1 from `analysis/hybrid.py`).
- `best.pt` was chosen with the old rule (`bench_all/composite_max`). For the submission model, also keep the last
  checkpoint (`runs/<run>/checkpoint.pt` on the pod; `pullRun` does not copy it).

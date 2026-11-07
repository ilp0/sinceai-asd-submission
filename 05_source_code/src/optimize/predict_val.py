"""Fine-stride window probabilities of a frozen experiment-6 checkpoint on the 7 validation pumps.

    python predict_val.py --run rp3-3h-r32-v1 --checkpoint checkpoint_last_step11500 [--stride-s 10]
    python predict_val.py --run rp3-6h-r32-v1 --checkpoint checkpoint_last_step14750 [--stride-s 20]

The default stride is the cell period of the model (10 s for 3h, 20 s for 6h): a window ends at every cell, which is
the finest time resolution the model has. The checkpoints are the last ones saved by training (frozen, not chosen on
validation). Output: <out>/<run>/<asset key with '/' -> '__'>.parquet, one file per pump, written atomically; a pump
whose file exists is skipped, so a restarted process continues. <out>/<run>/DONE marks a complete set.

Causal: each window contains only cells at or before its issue time (WindowDataset.__getitem__); the asset baseline is
the first 24 h of the asset window, and no window ends inside those 24 h (same as training and predict_test.py).
Labels (y_*) come from build_labels with the run config, as in the cached training data; they are for telemetry only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
CANDIDATES = [HERE.parent / "data_analysis_experiment_6_model",
              HERE.parent / ".claude/worktrees/timestral-multiclass-prediction-c697e7/data_analysis_experiment_6_model"]


def find_exp(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    for c in CANDIDATES:
        if (c / "data" / "validation").exists():
            return c
    raise SystemExit("experiment-6 folder with data/validation not found; pass --exp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp")
    ap.add_argument("--run", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--stride-s", type=int, default=None)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default=str(HERE / "predictions"))
    ap.add_argument("--assets", nargs="*", help="asset keys (default: all validation pumps)")
    a = ap.parse_args()

    exp = find_exp(a.exp)
    sys.path.insert(0, str(exp))
    sys.path.insert(0, str(exp / "analysis"))
    from mlhead.config import load_config
    from mlhead.data import build_labels, discover_assets
    from mlhead.model import TimestralMultiLabel
    from mlhead.train import compact_predictions, predict_windows
    from predict_test import AssetWindows

    class LabelledWindows(AssetWindows):
        """AssetWindows (arrays in memory) with the training labels and benign flags of each pump."""

        def __init__(self, cfg, specs, stride_s):
            super().__init__(cfg, specs, stride_s)
            lb = [build_labels(s, cfg) for s in specs]
            self.labels = [y for y, _ in lb]
            self.benign = [b for _, b in lb]
            self.window_labels = np.stack([self.labels[i][e] for i, e in self.index])
            self.has_positive = (self.window_labels == 1).any(1)
            self.is_benign = np.array([self.benign[i][e] for i, e in self.index])

        def __getstate__(self):          # keep the in-memory arrays when a DataLoader worker pickles the dataset
            return self.__dict__.copy()

    if torch.cuda.is_available():
        dev = torch.device("cuda")
    elif torch.backends.mps.is_available():
        dev = torch.device("mps")
    else:
        dev = torch.device("cpu")
    cfg = load_config(exp / "configs" / f"{a.run.rsplit('-v', 1)[0]}.yaml")
    cfg["run"]["precision"] = "fp32"
    cfg["run"]["num_workers"] = a.workers if a.workers is not None else (8 if dev.type == "cuda" else 0)
    cfg["train"]["eval_batch_size"] = a.batch
    period = int(cfg["input"]["sample_period_s"])
    stride = a.stride_s or period
    if stride % period:
        raise SystemExit(f"stride {stride} s is not a multiple of the cell period {period} s")

    model = TimestralMultiLabel(cfg)
    st = torch.load(exp / "runs" / a.run / f"{a.checkpoint}.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(st["model"])
    model.to(dev)
    out = Path(a.out) / a.run
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(run=a.run, checkpoint=a.checkpoint, step=int(st["step"]), stride_s=stride, period_s=period,
                minutes=cfg["input"]["minutes"], device=str(dev), batch=a.batch)
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta), flush=True)

    specs = discover_assets(cfg, ("val",))["val"]
    if a.assets:
        specs = [s for s in specs if s.key in a.assets]
    t_all = time.time()
    for s in specs:
        f = out / (s.key.replace("/", "__") + ".parquet")
        if f.exists():
            print(json.dumps(dict(asset=s.key, skipped="exists")), flush=True)
            continue
        t = time.time()
        ds = LabelledWindows(cfg, [s], stride)
        pred = compact_predictions(predict_windows(model, ds, cfg, dev))
        tmp = f.with_suffix(".tmp")
        pred.to_parquet(tmp, index=False)
        tmp.replace(f)
        print(json.dumps(dict(asset=s.key, windows=len(pred), seconds=round(time.time() - t, 1))), flush=True)
    if all((out / (s.key.replace("/", "__") + ".parquet")).exists() for s in discover_assets(cfg, ("val",))["val"]):
        (out / "DONE").write_text(json.dumps(dict(meta, seconds=round(time.time() - t_all, 1))))
    print(json.dumps(dict(done=(out / "DONE").exists(), seconds=round(time.time() - t_all, 1))), flush=True)


if __name__ == "__main__":
    main()

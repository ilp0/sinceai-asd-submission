"""Submission predictions at the 10 s stride: frozen 3h model -> window probabilities -> alerts (organizer format).

    python predict_test_fine.py predict --asset PUMP-10          # one test pump -> test_predictions/<run>/PUMP-10.parquet
    python predict_test_fine.py alerts  --split test             # all 3 test pumps -> results/submission-fine/predictions_test.csv
    python predict_test_fine.py alerts  --split validation       # PUMP-08/09 from predictions/<run>/ (check, scored)

Model: experiment 6 round 3, rp3-3h-r32-v1, checkpoint_last_step11500 (last checkpoint, not chosen on validation).
Rule (selected on the validation pumps, 7 Nov 2026; optimize/results/persistence-v1): threshold 0.9, persistence 15 min
(90 windows at the 10 s stride), no running average, cooldown 720 min per fault type, 5 min gap between alerts of
one pump. This is the rule of submission/predictions_test.csv; only the stride changes (60 s -> 10 s).

Causal: a window at issue time t contains only cells at or before t; each pump is normalized with the first 24 h of
its own window and no window ends inside those 24 h (analysis/predict_test.py AssetWindows). The test pumps are read
from telemetry and assets.csv only: no test events, benign windows or maintenance records are opened.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
# The experiment-6 folder: the worktree in the experiment repository, else a sibling folder (submission package layout).
EXP = next((p for p in (HERE.parent / ".claude/worktrees/timestral-multiclass-prediction-c697e7/data_analysis_experiment_6_model",
                        HERE.parent / "data_analysis_experiment_6_model") if p.exists()),
           HERE.parent / "data_analysis_experiment_6_model")
RUN, CHECKPOINT = "rp3-3h-r32-v1", "checkpoint_last_step11500"
RULE = dict(threshold=0.9, persistence_min=15, cooldown_minutes=720, global_gap_minutes=5,
            gap_inclusive=True)  # fix of 7 Nov 2026, see RULE_FROZEN.json "amendments"
STRIDE_S = 10
SPLITS = {"test": ["PUMP-10", "PUMP-11", "PUMP-12"], "validation": ["PUMP-08", "PUMP-09"]}
TEST_DIR = HERE / "test_predictions" / RUN
OUT_DIR = HERE / "results" / "submission-fine"


def predict(asset: str, batch: int) -> dict:
    import torch
    sys.path.insert(0, str(EXP))
    sys.path.insert(0, str(EXP / "analysis"))
    from mlhead.config import load_config
    from mlhead.model import TimestralMultiLabel
    from mlhead.train import compact_predictions, predict_windows
    from predict_test import DATA, AssetWindows, specs_for

    if asset not in SPLITS["test"]:
        raise SystemExit(f"{asset} is not a test pump")
    f = TEST_DIR / f"{asset}.parquet"
    if f.exists():
        return dict(asset=asset, skipped="exists")
    dev = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    cfg = load_config(EXP / "configs" / "rp3-3h-r32.yaml")
    cfg["run"]["num_workers"], cfg["run"]["precision"] = 0, "fp32"
    cfg["train"]["eval_batch_size"] = batch
    model = TimestralMultiLabel(cfg)
    st = torch.load(EXP / "runs" / RUN / f"{CHECKPOINT}.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(st["model"])
    model.to(dev)
    t = time.time()
    ds = AssetWindows(cfg, specs_for(pd.read_csv(DATA / "assets.csv"), [asset], "test"), STRIDE_S)
    pred = compact_predictions(predict_windows(model, ds, cfg, dev))
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    pred.to_parquet(tmp, index=False)
    tmp.replace(f)
    meta = dict(run=RUN, checkpoint=CHECKPOINT, step=int(st["step"]), stride_s=STRIDE_S, device=str(dev))
    (TEST_DIR / "meta.json").write_text(json.dumps(meta, indent=1))
    return dict(asset=asset, windows=len(pred), seconds=round(time.time() - t, 1), device=str(dev))


def alerts(split: str) -> dict:
    sys.path.insert(0, str(EXP))
    sys.path.insert(0, str(EXP / "analysis"))
    from alerts import fast_alerts
    from predict_test import ACTIONS
    if split == "test":
        files = [TEST_DIR / f"{a}.parquet" for a in SPLITS["test"]]
    else:
        files = [HERE / "predictions" / RUN / f"val-orig__{a}.parquet" for a in SPLITS["validation"]]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"missing predictions: {missing}")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["asset"] = df["asset"].astype(str)
    df = df.sort_values(["asset", "time"], kind="stable").reset_index(drop=True)
    al = fast_alerts(df, RULE["threshold"], RULE["persistence_min"] * 60 // STRIDE_S,
                     RULE["cooldown_minutes"], RULE["global_gap_minutes"],
                     gap_inclusive=RULE["gap_inclusive"])
    al["recommended_action"] = al.fault_type.map(ACTIONS).fillna("Review the evidence channel and inspect the pump.")
    al["evidence"] = [f"{e}; class probability above 0.9 for 15 min (model rp3-3h-r32, 3 h window, 10 s steps)"
                      for e in al.evidence]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"predictions_{split}.csv"
    al.to_csv(out, index=False)
    res = dict(split=split, alerts=len(al), file=str(out), per_pump=al.groupby("asset_id").size().to_dict())
    if split == "validation":
        from alerts import Truth
        r = Truth(EXP).score(al, "val-orig")
        res["score_08_09"] = {k: r[k] for k in ("composite_score", "alert_precision", "event_recall",
                                                 "fault_type_recall", "false_alerts_per_asset_day")}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["predict", "alerts"])
    ap.add_argument("--asset")
    ap.add_argument("--split", choices=list(SPLITS), default="test")
    ap.add_argument("--batch", type=int, default=128)
    a = ap.parse_args()
    print(json.dumps(predict(a.asset, a.batch) if a.action == "predict" else alerts(a.split), default=str), flush=True)


if __name__ == "__main__":
    main()

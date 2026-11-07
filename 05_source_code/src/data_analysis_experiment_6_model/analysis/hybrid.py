"""Hybrid alerts: the experiment-6 model for some fault classes, causal B1 for the others.

    python analysis/hybrid.py runs/rp3-6h-r32-v1/predictions/val_step02750.parquet [more ...] [--out ...]

Two alert sources, both causal:
  model  window probabilities of a saved prediction file -> the training-time alert rules (threshold thr)
  B1     the organizer B1 detector exactly as in experiment 1 (regime z-scores from the first 24 h,
         no alerts in the first 24 h, k=6 chosen on training pumps, persistence 10, 12 h cooldown per type)
A router gives each of the 13 fault classes one source: model, B1 or both. The two alert lists are joined and
a 12 h cooldown per (pump, fault type) removes duplicates (as experiment 1 merge_cooldown).

Results per prediction file (organizer scorer, 7 validation pumps and PUMP-08/09):
  model_only / b1_only     each source alone
  sensor_b1                fixed rule chosen BEFORE any scoring: SENSOR classes from B1, MACHINE classes from model
  selected                 greedy router + threshold selected on all 7 pumps (optimistic)
  lopo_cv                  router + threshold selected on 6 pumps, applied to the 7th. Still somewhat optimistic:
                           the prediction file (checkpoint step) itself was chosen on all 7 pumps
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP / "analysis"))
from mlhead.benchmark import MACHINE, alerts_from_predictions  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from postprocess import KEYS, Pumps  # noqa: E402

PKG = next((EXP.parent / "raw").glob("*/RETROFIT_AI_PARTICIPANTS_2026"))
sys.path.insert(0, str(PKG / "src"))
from retrofit_sim.baselines import b1_threshold, regime_frame, zscores  # noqa: E402

CONFIG = EXP / "configs/rp3-6h-r32.yaml"
B1_K, B1_PERSIST, COMMISSION_H, COOLDOWN = 6.0, 10, 24, pd.Timedelta(hours=12)
THRESHOLDS = [0.9, 0.95, 0.98]
OPTIONS = ("model", "b1", "both")
CACHE = EXP / "analysis" / "b1_val_alerts.parquet"


def b1_alerts(pumps: Pumps) -> pd.DataFrame:
    """B1 on every validation pump, from that pump's own features_1min.parquet (labels are not read)."""
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    out = []
    for key, spec in pumps.specs.items():
        base = next(d for d in Path(spec.telemetry_dir).parents if (d / "features_1min.parquet").exists())
        assets = pd.read_csv(base / "assets.csv")
        a = assets[assets.asset_id == spec.asset_id]
        if len(a) != 1:
            raise FileNotFoundError(f"{key}: asset not in {base}/assets.csv")
        feat = pd.read_parquet(base / "features_1min.parquet", filters=[("asset_id", "==", spec.asset_id)])
        z = zscores(regime_frame(feat, a))
        start = pd.to_datetime(a.window_start_utc.iloc[0], utc=True)
        z = z[pd.to_datetime(z.window_start_utc, utc=True) >= start + pd.Timedelta(hours=COMMISSION_H)]
        out.append(b1_threshold(z, k=B1_K, persist=B1_PERSIST))
    al = pd.concat(out, ignore_index=True)
    al["alert_time_utc"] = pd.to_datetime(al.alert_time_utc, utc=True)
    al = cooldown(al)
    al.to_parquet(CACHE, index=False)
    return al


def cooldown(al: pd.DataFrame) -> pd.DataFrame:
    if al.empty:
        return al
    al = al.sort_values(["asset_id", "alert_time_utc"], kind="stable").reset_index(drop=True)
    last, keep = {}, []
    for i, (a, f, t) in enumerate(zip(al.asset_id, al.fault_type, al.alert_time_utc)):
        if (a, f) not in last or t - last[(a, f)] >= COOLDOWN:
            keep.append(i)
            last[(a, f)] = t
    return al.loc[keep].reset_index(drop=True)


def combine(model: pd.DataFrame, b1: pd.DataFrame, route: dict) -> pd.DataFrame:
    m = model[model.fault_type.map(lambda c: route.get(c, "model") in ("model", "both"))]
    b = b1[b1.fault_type.map(lambda c: route.get(c, "model") in ("b1", "both"))]   # B1-only types (UNKNOWN): "model" = drop
    al = pd.concat([m, b], ignore_index=True)
    al["alert_time_utc"] = pd.to_datetime(al.alert_time_utc, utc=True)
    return cooldown(al[list(b1.columns.intersection(al.columns))])


def select(pumps, model_by_thr, b1, keys, classes):
    """Greedy router (2 passes over the classes) for each threshold; best composite on `keys`."""
    best = None
    for thr, model in model_by_thr.items():
        route = {c: "model" for c in classes}
        cur = pumps.score(combine(model, b1, route), keys)["composite_score"]
        for _ in range(2):
            for c in classes:
                for opt in OPTIONS:
                    if opt == route[c]:
                        continue
                    trial = dict(route, **{c: opt})
                    s = pumps.score(combine(model, b1, trial), keys)["composite_score"]
                    if s > cur + 1e-9:
                        cur, route = s, trial
        if best is None or cur > best[0]:
            best = (cur, thr, route)
    return best


def evaluate(pred, pumps, b1):
    cfg = pumps.cfg
    classes = list(cfg["labels"]["classes"]) + sorted(set(b1.fault_type) - set(cfg["labels"]["classes"]))
    keys = sorted(pred.asset.unique())
    orig = [k for k in keys if k.startswith("val-orig/")]
    model_by_thr = {t: alerts_from_predictions(cfg, pred, threshold=t) for t in THRESHOLDS}
    fixed = {c: ("model" if c in MACHINE else "b1") for c in classes}
    res = {}

    def both(al):
        return {"all7": {k: pumps.score(al, keys)[k] for k in KEYS}, "08/09": {k: pumps.score(al, orig)[k] for k in KEYS}}

    res["model_only"] = both(model_by_thr[0.9])
    res["b1_only"] = both(b1)
    res["sensor_b1"] = dict(both(combine(model_by_thr[0.9], b1, fixed)), route=fixed)
    c, thr, route = select(pumps, model_by_thr, b1, keys, classes)
    res["selected"] = dict(both(combine(model_by_thr[thr], b1, route)), threshold=thr, route=route)
    held, folds = [], []
    for k in keys:
        rest = [x for x in keys if x != k]
        c, thr, route = select(pumps, model_by_thr, b1, rest, classes)
        al = combine(model_by_thr[thr], b1, route)
        held.append(al[al.asset_id == pumps.specs[k].asset_id])
        folds.append(dict(held_out=k, threshold=thr, selection_composite=round(c, 2),
                          b1_classes=sorted(x for x, v in route.items() if v != "model")))
        print("  fold", json.dumps(folds[-1]), flush=True)
    res["lopo_cv"] = dict(both(pd.concat(held, ignore_index=True)), folds=folds)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", nargs="+")
    ap.add_argument("--out", default=str(EXP / "analysis" / "hybrid.json"))
    a = ap.parse_args()
    cfg = load_config(CONFIG)
    pumps = Pumps(cfg)
    b1 = b1_alerts(pumps)
    out = Path(a.out)
    results = json.loads(out.read_text()) if out.exists() else {}
    for f in a.predictions:
        pred = pd.read_parquet(EXP / f if not Path(f).is_absolute() else f)
        pred["asset"] = pred["asset"].astype(str)
        print(f"== {f}", flush=True)
        r = evaluate(pred, pumps, b1)
        results[f] = r
        print(f"  {'':12} {'all7':>6} {'08/09':>6}   F1  prec  FA/day type")
        for k in ("model_only", "b1_only", "sensor_b1", "selected", "lopo_cv"):
            v, o = r[k]["all7"], r[k]["08/09"]
            print(f"  {k:12} {v['composite_score']:6.1f} {o['composite_score']:6.1f} {v['event_f1']:5.2f} "
                  f"{v['alert_precision']:5.2f} {v['false_alerts_per_asset_day']:5.2f} {v['fault_type_recall']:5.2f}", flush=True)
        out.write_text(json.dumps(results, indent=1, default=str))
    print(f"-> {out}")


if __name__ == "__main__":
    main()

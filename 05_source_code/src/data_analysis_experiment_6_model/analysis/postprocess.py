"""Offline alert-rule selection on saved window predictions, with leave-one-pump-out cross-validation.

    python analysis/postprocess.py runs/rp-3h-r32-v1/predictions/val_step00750.parquet [more files ...]
        [--average]            # mean probability of all files (one checkpoint ensemble) instead of one by one
        [--out analysis/postprocess_<name>.json] [--quick]

The model is fixed. Only the rules that turn window probabilities into alerts change (threshold,
persistence, causal smoothing, global gap between alerts, weak classes off). The rules use no data after the
alert time, so they keep the causal rule of BENCHMARK_RULES.md.

Three numbers per prediction file, all scored with the organizer scorer on the 7 validation pumps:
  default    the training-time rules (persistence 3, cooldown 720 min, gap 5 min) at threshold 0.9
  selected   the grid point with the best composite on all 7 pumps (optimistic: selected on the same events)
  lopo_cv    for each pump, the grid point with the best composite on the other 6 pumps is applied to it;
             the 7 held-out alert sets are scored together (an honest estimate of the rule selection)
The checkpoint itself was also selected on these pumps, so even lopo_cv is somewhat optimistic.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
from mlhead.benchmark import _scorer, alerts_from_predictions  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from mlhead.data import discover_assets  # noqa: E402
from mlhead.metrics import average_precision  # noqa: E402

CONFIG = EXP / "configs/rp-3h-r32.yaml"      # data sources and labels are the same in all six run configs
GRID = dict(threshold=[0.8, 0.85, 0.9, 0.93, 0.95, 0.97, 0.98, 0.99],
            persistence_windows=[3, 10, 30],
            smooth_windows=[1, 15],
            global_gap_minutes=[5, 120, 720],
            cooldown_minutes=[720],
            disable_weak=[False, True])
QUICK = dict(GRID, threshold=[0.9, 0.95, 0.98], smooth_windows=[1], persistence_windows=[3, 10])
WEAK_AUPRC = 0.15          # disable_weak: classes whose window AUPRC on the selection pumps is below this
KEYS = ["composite_score", "event_f1", "event_recall", "alert_precision", "false_alerts_per_asset_day",
        "timeliness", "fault_type_recall", "class_recall", "events_scored", "true_positive_events",
        "false_alert_episodes", "excess_repeat_episodes"]


class Pumps:
    """Labels of the validation pumps and the organizer scorer for any subset of them."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.specs = {s.key: s for s in discover_assets(cfg, ("val",))["val"]}
        self.score_fn = _scorer(cfg)

    def score(self, alerts: pd.DataFrame, keys: list[str]) -> dict:
        sp = [self.specs[k] for k in keys]
        ids = {s.asset_id for s in sp}
        r = self.score_fn(alerts[alerts.asset_id.isin(ids)], pd.concat([s.events for s in sp], ignore_index=True),
                          pd.DataFrame([s.info for s in sp]), pd.concat([s.benign for s in sp], ignore_index=True))
        r["alert_burden"] = max(0.0, 1.0 - r["false_alerts_per_asset_day"] / 2.0)
        return r


def weak_classes(pred: pd.DataFrame, classes: list[str], keys: list[str]) -> list[str]:
    part = pred[pred.asset.isin(keys)]
    out = []
    for c in classes:
        y, p = part[f"y_{c}"].to_numpy(), part[f"p_{c}"].to_numpy()
        m = y >= 0
        ap = average_precision((y[m] == 1).astype(int), p[m]) if m.any() else float("nan")
        if np.isnan(ap) or ap < WEAK_AUPRC:     # no positives on the selection pumps counts as weak
            out.append(c)
    return out


def grid_points(grid: dict) -> list[dict]:
    names = list(grid)
    return [dict(zip(names, v)) for v in itertools.product(*grid.values())]


def evaluate(pred: pd.DataFrame, pumps: Pumps, grid: dict, log=print) -> dict:
    cfg, classes = pumps.cfg, pumps.cfg["labels"]["classes"]
    keys = sorted(pred.asset.unique())
    points = grid_points(grid)

    def alerts_for(pt: dict, disabled: list[str]) -> pd.DataFrame:
        rules = {k: v for k, v in pt.items() if k != "disable_weak"}
        rules["disabled_classes"] = disabled if pt["disable_weak"] else []
        return alerts_from_predictions(cfg, pred, rules=rules)

    # Alerts of one pump depend only on that pump's windows and the rules; the weak-class set depends on
    # which pumps select it, so alerts are cached per (point, weak set).
    cache = {}

    def alerts_cached(i: int, disabled: tuple) -> pd.DataFrame:
        k = (i, disabled if points[i]["disable_weak"] else ())
        if k not in cache:
            cache[k] = alerts_for(points[i], list(disabled))
        return cache[k]

    weak_all = tuple(weak_classes(pred, classes, keys))
    default = pumps.score(alerts_from_predictions(cfg, pred, threshold=0.9), keys)
    # Selected on all pumps (optimistic).
    scored = []
    for i in range(len(points)):
        r = pumps.score(alerts_cached(i, weak_all), keys)
        scored.append((r["composite_score"], i, r))
    best_c, best_i, best_r = max(scored, key=lambda x: (x[0], -x[1]))
    # Leave one pump out.
    held, folds = [], []
    for k in keys:
        rest = [x for x in keys if x != k]
        weak = tuple(weak_classes(pred, classes, rest))
        fold = max(((pumps.score(alerts_cached(i, weak), rest)["composite_score"], -i) for i in range(len(points))))
        i = -fold[1]
        a = alerts_cached(i, weak)
        held.append(a[a.asset_id == pumps.specs[k].asset_id])
        folds.append(dict(held_out=k, point=points[i], disabled=list(weak) if points[i]["disable_weak"] else [],
                          selection_composite=round(fold[0], 2)))
        log(json.dumps(dict(held_out=k, selection_composite=round(fold[0], 2), point=points[i])))
    cv = pumps.score(pd.concat(held, ignore_index=True), keys)
    groups = {"val-orig": [k for k in keys if k.startswith("val-orig/")]}
    out = dict(
        default={k: default[k] for k in KEYS},
        selected=dict(point=points[best_i], disabled=list(weak_all) if points[best_i]["disable_weak"] else [],
                      **{k: best_r[k] for k in KEYS}),
        lopo_cv={k: cv[k] for k in KEYS},
        lopo_folds=folds,
        val_orig={name: {k: pumps.score(a, g)[k] for k in KEYS} for name, a in
                  (("default", alerts_from_predictions(cfg, pred, threshold=0.9)), ("selected", alerts_cached(best_i, weak_all)),
                   ("lopo_cv", pd.concat(held, ignore_index=True))) for g in groups.values()},
        grid_size=len(points))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("predictions", nargs="+")
    ap.add_argument("--average", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    cfg = load_config(CONFIG)
    pumps = Pumps(cfg)
    grid = QUICK if a.quick else GRID
    frames = {f: pd.read_parquet(EXP / f if not Path(f).is_absolute() else f) for f in a.predictions}
    for df in frames.values():
        df["asset"] = df["asset"].astype(str)
    if a.average:
        base = next(iter(frames.values()))
        ps = [c for c in base if c.startswith("p_")]
        avg = base.copy()
        avg[ps] = np.mean([f.set_index(["asset", "time"]).loc[list(zip(base.asset, base.time)), ps].to_numpy()
                           for f in frames.values()], axis=0)
        frames = {"average(" + ",".join(Path(f).stem for f in frames) + ")": avg}
    results = {}
    for name, pred in frames.items():
        print(f"== {name}")
        results[name] = evaluate(pred, pumps, grid)
        r = results[name]
        print("                 composite   F1  recall  prec  FA/day  timely  type  class")
        for k in ("default", "selected", "lopo_cv"):
            v = r[k]
            print(f"  {k:<10} all7 {v['composite_score']:8.1f} {v['event_f1']:5.2f} {v['event_recall']:6.2f} "
                  f"{v['alert_precision']:5.2f} {v['false_alerts_per_asset_day']:6.2f} {v['timeliness']:6.2f} "
                  f"{v['fault_type_recall']:5.2f} {v['class_recall']:5.2f}")
        for k, v in r["val_orig"].items():
            print(f"  {k:<10} 08/09 {v['composite_score']:7.1f} {v['event_f1']:5.2f} {v['event_recall']:6.2f} "
                  f"{v['alert_precision']:5.2f} {v['false_alerts_per_asset_day']:6.2f} {v['timeliness']:6.2f} "
                  f"{v['fault_type_recall']:5.2f} {v['class_recall']:5.2f}")
        print("  selected point:", json.dumps(r["selected"]["point"]), "disabled:", r["selected"]["disabled"])
    out = Path(a.out) if a.out else EXP / "analysis" / "postprocess.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev.update(results)
    out.write_text(json.dumps(prev, indent=1, default=str))
    print(f"-> {out}")


if __name__ == "__main__":
    main()

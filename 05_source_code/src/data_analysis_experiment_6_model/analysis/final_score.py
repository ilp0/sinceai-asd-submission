"""Final experiment-6 table: round-3 runs against causal B1, with the fixed alert rule chosen on 7 Nov 2026.

    python analysis/final_score.py [RUN ...]      # default: the three rp3 runs

Fixed rule (user decision 7 Nov 2026, from analysis/gap_persistence.py): threshold 0.9, persistence 15 minutes
(15 windows at the 60 s stride of 3h/6h; 22 windows at the 40 s stride of 12h), all other rules as in configs/base.yaml. The old default
(persistence 3) is shown for comparison. Leave-one-pump-out on 26 checkpoints chose persistence 15 or 30 for every
pump (analysis/gap_persistence.json), so this rule is not fitted to one pump.

Rows per run (organizer scorer; groups: all 7 validation pumps, PUMP-08/09, val-new 45001):
  last          the last saved checkpoint (no selection)
  mean_last3    mean score of the last 3 checkpoints (no selection; less noise)
  best_on_val   the checkpoint with the best "all" composite under the fixed rule (OPTIMISTIC: chosen on these pumps)
B1: analysis/hybrid.py b1_alerts (experiment-1 causal B1, k=6 chosen on training pumps).
Output: analysis/final_results.json and analysis/final_results.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP / "analysis"))
from hybrid import b1_alerts  # noqa: E402
from mlhead.benchmark import alerts_from_predictions  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from postprocess import Pumps  # noqa: E402

THRESHOLD = 0.9
FIXED = dict(persistence_windows=15)
OLD = dict(persistence_windows=3)
RUNS = ["rp3-3h-r32-v1", "rp3-6h-r32-v1", "rp3-12h-r32-v1"]
METRICS = ["composite_score", "event_f1", "alert_precision", "event_recall", "false_alerts_per_asset_day",
           "timeliness", "fault_type_recall", "class_recall"]


def main():
    runs = sys.argv[1:] or RUNS
    cfg = load_config(EXP / "configs/rp3-6h-r32.yaml")
    pumps = Pumps(cfg)
    keys = sorted(pumps.specs)
    groups = {"all": keys, "08/09": [k for k in keys if k.startswith("val-orig/")],
              "val-new": [k for k in keys if k.startswith("val-new")]}

    def score(al):
        return {g: {m: float(pumps.score(al, ks)[m]) for m in METRICS} for g, ks in groups.items()}

    res = {"B1": {"all rules": score(b1_alerts(pumps))}}
    for run in runs:
        files = sorted((EXP / "runs" / run / "predictions").glob("val_step*.parquet"))
        per = {}
        for f in files:
            pred = pd.read_parquet(f)
            pred["asset"] = pred["asset"].astype(str)
            stride_s = pred.groupby("asset").time.apply(lambda t: pd.to_datetime(t).diff().median()).median().total_seconds()
            per_min = lambda r: {"persistence_windows": max(1, round(r["persistence_windows"] * 60 / stride_s))}
            per[int(f.stem[8:])] = {name: score(alerts_from_predictions(cfg, pred, threshold=THRESHOLD, rules=per_min(r)))
                                    for name, r in (("fixed_p15", FIXED), ("old_p3", OLD))}
        steps = sorted(per)
        mean = lambda ss, rule: {g: {m: float(np.mean([per[s][rule][g][m] for s in ss])) for m in METRICS} for g in groups}
        best = max(steps, key=lambda s: per[s]["fixed_p15"]["all"]["composite_score"])
        res[run] = {
            "last": dict(step=steps[-1], **{rule: per[steps[-1]][rule] for rule in ("fixed_p15", "old_p3")}),
            "mean_last3": dict(steps=steps[-3:], **{rule: mean(steps[-3:], rule) for rule in ("fixed_p15", "old_p3")}),
            "best_on_val": dict(step=best, **{rule: per[best][rule] for rule in ("fixed_p15", "old_p3")}),
            "checkpoints": len(steps)}
        print(f"done {run}: {len(steps)} checkpoints, last step {steps[-1]}", flush=True)
    (EXP / "analysis" / "final_results.json").write_text(json.dumps(res, indent=1))

    lines = ["# Experiment 6, round 3 against causal B1", "",
             f"Threshold {THRESHOLD}. Fixed rule: persistence 15 min. Old rule: persistence 3 min. Organizer scorer.",
             "`best_on_val` is chosen on the same validation pumps: optimistic.", "",
             "| Run | Checkpoint | Rule | All 7 | PUMP-08/09 | val-new | Precision (all) | False alerts/day (all) | Recall (all) |",
             "|---|---|---|---|---|---|---|---|---|"]
    b = res["B1"]["all rules"]
    lines.append(f"| **B1** | — | — | {b['all']['composite_score']:.1f} | {b['08/09']['composite_score']:.1f} | "
                 f"{b['val-new']['composite_score']:.1f} | {b['all']['alert_precision']:.2f} | "
                 f"{b['all']['false_alerts_per_asset_day']:.2f} | {b['all']['event_recall']:.2f} |")
    for run in runs:
        for row in ("last", "mean_last3", "best_on_val"):
            r = res[run][row]
            ck = r.get("step", r.get("steps"))
            for rule in ("fixed_p15", "old_p3"):
                v = r[rule]
                lines.append(f"| {run} | {row} {ck} | {rule} | {v['all']['composite_score']:.1f} | "
                             f"{v['08/09']['composite_score']:.1f} | {v['val-new']['composite_score']:.1f} | "
                             f"{v['all']['alert_precision']:.2f} | {v['all']['false_alerts_per_asset_day']:.2f} | "
                             f"{v['all']['event_recall']:.2f} |")
    (EXP / "analysis" / "final_results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

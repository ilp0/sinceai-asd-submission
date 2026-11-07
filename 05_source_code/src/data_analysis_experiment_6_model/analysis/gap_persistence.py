"""Alert rules test: a 12 h alert gap per pump and a minimum persistence (minutes above the threshold).

    python analysis/gap_persistence.py RUN [RUN ...] [--from-step 8000] [--threshold 0.9]

For every saved prediction file of the runs (step >= --from-step) and every rule (gap x persistence), the
alerts are scored with the organizer scorer on all 7 validation pumps, PUMP-08/09 and val-new. The table gives the
mean over the checkpoints (no step selection). The validation predictions have one window per minute
(eval_stride_s 60), so persistence N windows = N minutes.

The 12 h gap comes from the scorer constant REMINDER (repeat alerts within 12 h are penalised), not from tuning.
The persistence values are a small grid; choosing one of them on these pumps is a selection, so the script also
reports leave-one-pump-out (rule chosen on 6 pumps, applied to the 7th, all checkpoints pooled).
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
sys.path.insert(0, str(EXP / "analysis"))
from mlhead.benchmark import alerts_from_predictions  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from postprocess import Pumps  # noqa: E402

GAPS = [5, 720]                 # minutes: 5 = current default, 720 = scorer REMINDER
PERSIST = [3, 15, 30, 60]       # minutes (= windows at 60 s stride); 3 = current default
METRICS = ["composite_score", "event_recall", "alert_precision", "false_alerts_per_asset_day", "timeliness",
           "fault_type_recall"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--from-step", type=int, default=8000)
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--out", default=str(EXP / "analysis" / "gap_persistence.json"))
    a = ap.parse_args()
    cfg = load_config(EXP / "configs/rp3-6h-r32.yaml")
    pumps = Pumps(cfg)
    keys = sorted(pumps.specs)
    groups = {"all": keys, "08/09": [k for k in keys if k.startswith("val-orig/")],
              "val-new": [k for k in keys if k.startswith("val-new")]}
    rules = list(itertools.product(GAPS, PERSIST))
    rows, alerts_by = [], {}
    for run in a.runs:
        files = sorted((EXP / "runs" / run / "predictions").glob("val_step*.parquet"))
        files = [f for f in files if int(f.stem[8:]) >= a.from_step]
        for f in files:
            pred = pd.read_parquet(f)
            pred["asset"] = pred["asset"].astype(str)
            stride = pred.groupby("asset").time.apply(lambda t: pd.to_datetime(t).diff().median()).median()
            assert stride == pd.Timedelta(minutes=1), f"{f}: window stride {stride}, persistence would not be minutes"
            for gap, per in rules:
                al = alerts_from_predictions(cfg, pred, threshold=a.threshold,
                                             rules=dict(global_gap_minutes=gap, persistence_windows=per))
                alerts_by[(run, f.stem, gap, per)] = al
                for g, ks in groups.items():
                    r = pumps.score(al, ks)
                    rows.append(dict(run=run, ckpt=f.stem, gap=gap, persist=per, group=g, **{m: r[m] for m in METRICS},
                                     repeats=r["excess_repeat_episodes"], false_episodes=r["false_alert_episodes"]))
            print(f"done {run} {f.stem}", flush=True)
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    for run in a.runs + ["ALL"]:
        d = df if run == "ALL" else df[df.run == run]
        n = d.ckpt.nunique() if run != "ALL" else d.groupby("run").ckpt.nunique().sum()
        print(f"\n== {run}: mean over {n} checkpoints, threshold {a.threshold}")
        t = d.pivot_table(index=["gap", "persist"], columns="group", values="composite_score", aggfunc="mean").round(1)
        x = d[d.group == "all"].groupby(["gap", "persist"])[["alert_precision", "false_alerts_per_asset_day", "repeats",
                                                              "false_episodes", "event_recall", "timeliness",
                                                              "fault_type_recall"]].mean().round(2)
        print(t.join(x).to_string())
    # Leave one pump out: for each held-out pump, the rule with the best mean composite on the other 6 pumps
    # (all checkpoints of all runs); its alerts on the held-out pump are pooled per checkpoint and scored.
    ck = sorted({(r, c) for r, c, _, _ in alerts_by})
    sel_cache = {}
    def rest_score(rule, rest):
        k = (rule, tuple(rest))
        if k not in sel_cache:
            sel_cache[k] = np.mean([pumps.score(alerts_by[(r, c) + rule], rest)["composite_score"] for r, c in ck])
        return sel_cache[k]
    chosen = {}
    for k in keys:
        rest = [x for x in keys if x != k]
        chosen[k] = max(rules, key=lambda rule: rest_score(rule, rest))
    lopo = {g: [] for g in groups}
    for r, c in ck:
        al = pd.concat([alerts_by[(r, c) + chosen[k]].pipe(lambda x: x[x.asset_id == pumps.specs[k].asset_id]) for k in keys])
        for g, ks in groups.items():
            lopo[g].append(pumps.score(al, ks)["composite_score"])
    print("\nLOPO chosen rules (gap, persist):", {k.split('/')[1]: v for k, v in chosen.items()})
    print("LOPO composite, mean over checkpoints:", {g: round(float(np.mean(v)), 1) for g, v in lopo.items()})
    Path(a.out).write_text(json.dumps(dict(rows=rows, lopo_chosen={k: list(v) for k, v in chosen.items()},
                                           lopo={g: float(np.mean(v)) for g, v in lopo.items()}), indent=1, default=str))
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()

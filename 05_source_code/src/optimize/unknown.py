"""UNKNOWN alerts on top of the frozen rule: "something is wrong, cause unclear".

    .venv/bin/python unknown.py

Base: the frozen submission rule (3h model, 10 s predictions, threshold 0.9, persistence 15 min, cooldown 720 min,
gap 5 min). Extra UNKNOWN candidate at time t when, for `persistence` minutes in a row, the sum of the 13 class
probabilities is >= `sum_thr` while no single class is >= 0.9 (so the base rule cannot alert). event_class = the group
(MACHINE or SENSOR) with the larger probability sum. An UNKNOWN alert is dropped within `quiet_h` hours of any alert of
the same pump (base or UNKNOWN) and within 5 min of a base alert. Everything is causal except the quiet window around
LATER base alerts, which is why `after_base` is a grid option: False = only earlier alerts suppress (causal).
Selection: composite on the 7 validation pumps, plus leave-one-pump-out. Output: results/unknown-v1/.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from alerts import CLASSES, MACHINE, Truth, fast_alerts, load_predictions
from retrofit_sim import scoring
from study import EXP

HERE = Path(__file__).resolve().parent
RUN, STRIDE = "rp3-3h-r32-v1", 10
GRID = dict(sum_thr=[0.6, 0.8, 1.0, 1.3, 1.6], persistence_min=[15, 30, 60], quiet_h=[12, 24])


def unknown_alerts(df: pd.DataFrame, base: pd.DataFrame, sum_thr: float, persistence_min: int, quiet_h: int):
    P = np.stack([df[f"p_{c}"].to_numpy(np.float64) for c in CLASSES], 1)
    mach = np.array([c in MACHINE for c in CLASSES])
    rows = []
    n_p = persistence_min * 60 // STRIDE
    quiet = pd.Timedelta(hours=quiet_h)
    for asset, idx in df.groupby("asset", sort=False).indices.items():
        p = P[idx]
        ok = (p.sum(1) >= sum_thr) & (p.max(1) < 0.9)
        i = np.arange(len(idx))
        run = i - np.maximum.accumulate(np.where(ok, -1, i))
        aid = asset.split("/", 1)[1]
        times = pd.to_datetime(df["time"].to_numpy()[idx], utc=True)
        prev = sorted(pd.to_datetime(base[base.asset_id == aid].alert_time_utc, utc=True))
        last = None
        for k in np.flatnonzero(run >= n_p):
            t = times[k]
            earlier = [b for b in prev if b <= t]
            if earlier and t - earlier[-1] < quiet:
                continue
            if last is not None and t - last < quiet:
                continue
            ms, ss = p[k][mach].sum(), p[k][~mach].sum()
            rows.append(dict(asset_id=aid, alert_time_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             event_class="MACHINE" if ms >= ss else "SENSOR", fault_type="UNKNOWN",
                             confidence=round(float(min(1.0, p[k].sum())), 4),
                             evidence=f"Sum of fault probabilities {p[k].sum():.2f} for {persistence_min} min, no single type >= 0.9",
                             recommended_action="Inspect the pump: abnormal behaviour, cause unclear."))
            last = t
    return pd.DataFrame(rows, columns=base.columns[:7] if len(base.columns) >= 7 else None)


def main():
    out = HERE / "results" / "unknown-v1"
    out.mkdir(parents=True, exist_ok=True)
    df, _ = load_predictions(HERE / "predictions" / RUN)
    truth = Truth(EXP)
    keys = sorted(truth.specs)
    base = fast_alerts(df, 0.9, 90, 720, 5)

    def score(al, ks):
        ev, assets, bn = truth.subset(ks)
        return scoring.score(al[al.asset_id.isin(set(assets.asset_id))], ev, assets, bn)

    pts = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    sets = [None] + [pd.concat([base, unknown_alerts(df, base, **pt)], ignore_index=True) for pt in pts]
    names = ["base (frozen rule)"] + [json.dumps(pt) for pt in pts]
    rows = []
    for n, al in zip(names, sets):
        al = base if al is None else al
        r = score(al, keys)
        unk = al[al.fault_type == "UNKNOWN"]
        pe = pd.DataFrame(r["per_event"])
        rows.append(dict(setting=n, composite=round(r["composite_score"], 2), unknown_alerts=len(unk),
                         recall=round(r["event_recall"], 3), precision=round(r["alert_precision"], 3),
                         class_recall=round(r["class_recall"], 3), false_per_day=round(r["false_alerts_per_asset_day"], 3),
                         detected_by_unknown=int((pe.predicted_fault_type == "UNKNOWN").sum()),
                         **{f"fold_{k.split('/')[-1]}": score(al, [x for x in keys if x != k])["composite_score"] for k in keys}))
    tab = pd.DataFrame(rows)
    # LOPO: for each held-out pump, choose among all settings (base included) on the other 6.
    held = []
    tab["chosen_in_folds"] = 0
    for k in keys:
        col = f"fold_{k.split('/')[-1]}"
        i = int(tab[col].idxmax())
        al = base if i == 0 else sets[i]
        held.append(al[al.asset_id == truth.specs[k].asset_id])
        tab.loc[i, "chosen_in_folds"] += 1
    lopo = score(pd.concat(held, ignore_index=True), keys)
    tab.to_csv(out / "unknown.csv", index=False)
    show = tab.sort_values("composite", ascending=False)[["setting", "composite", "unknown_alerts", "detected_by_unknown",
                                                          "recall", "precision", "false_per_day", "chosen_in_folds"]]
    txt = (show.head(12).to_markdown(index=False) + f"\n\nBase: {rows[0]['composite']}. LOPO with the choice among base + "
           f"{len(pts)} UNKNOWN settings: {lopo['composite_score']:.2f}.\n")
    (out / "report.md").write_text("# UNKNOWN alerts on top of the frozen rule\n\n" + txt)
    print(txt)


if __name__ == "__main__":
    main()

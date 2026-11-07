"""Occlusion evidence for each alert: which sensor rows the model's class probability depends on.

    python occlusion.py --split validation      # results/submission-fine/predictions_validation.csv
    python occlusion.py --split test            # results/submission-fine/predictions_test.csv

For each alert (pump, time, fault type), the window that ends at the alert time is predicted again, once with all rows
and once without each row. drop = p(all rows) - p(without the row); logit_drop is the same in logits (it is not
saturated near 1.0). A large drop means that the model's alert depends on that signal. This shows what the model uses,
not a proven physical cause. The rows are mixed inside the backbone (variate attention), so attention weights alone
are not proof; removal is a direct test on the model. It uses only the window of the alert (data at or before the alert
time) and reads no labels.

Removal imitates a pump without that instrument. Training has such pumps for most rows, but not for the rows in
ALWAYS_PRESENT: for these rows the input without the row is out of distribution, and the evidence text says so.
Only the last window of the alert is tested; the 15 min rule needs 90 windows, so without the row the alert could
still occur some windows later.

Outputs (the alerts themselves do not change: same pumps, times, fault types and confidences):
  results/submission-fine/occlusion_<split>.csv            one row per (alert, sensor row)
  results/submission-fine/predictions_<split>_explained.csv the alert file with an occlusion evidence text
A row is "decisive" when the probability without it is below the alert threshold 0.9: without that signal, this alert
would not occur at this time. The evidence text names up to --top decisive rows, or says that no single row is decisive.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from predict_test_fine import CHECKPOINT, EXP, OUT_DIR, RUN, STRIDE_S

# Rows present on every training asset: the 4 derived rows (configs/base.yaml "derived") and 4 sensor rows that every
# original and generated training-side asset has (independent review, 7 Nov 2026, 294 assets counted).
ALWAYS_PRESENT = {"running", "row_present", "comm_loss_flag", "out_of_range_flag",
                  "ambient_temp_c", "discharge_pressure_kpa", "fluid_temp_c", "motor_current_a"}
ROW_TEXT = {"comm_loss_flag": "communication-loss flag", "out_of_range_flag": "out-of-range flag",
            "row_present": "data-present flag", "running": "running state"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["validation", "test"], required=True)
    ap.add_argument("--top", type=int, default=2, help="signals named in the evidence text")
    a = ap.parse_args()

    import torch
    sys.path.insert(0, str(EXP))
    sys.path.insert(0, str(EXP / "analysis"))
    from mlhead.config import load_config
    from mlhead.data import collate, row_vocabulary
    from mlhead.model import TimestralMultiLabel
    from mlhead.train import to_device
    from predict_test import DATA, AssetWindows, specs_for

    alerts = pd.read_csv(OUT_DIR / f"predictions_{a.split}.csv")
    dev = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
    cfg = load_config(EXP / "configs" / "rp3-3h-r32.yaml")
    cfg["run"]["num_workers"], cfg["run"]["precision"] = 0, "fp32"
    classes, vocab = cfg["labels"]["classes"], row_vocabulary(cfg)
    model = TimestralMultiLabel(cfg)
    st = torch.load(EXP / "runs" / RUN / f"{CHECKPOINT}.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(st["model"])
    model.to(dev).eval()
    assets = pd.read_csv(DATA / "assets.csv")

    t0 = time.time()
    rows, texts = [], []
    for aid, g in alerts.groupby("asset_id", sort=False):
        ds = AssetWindows(cfg, specs_for(assets, [aid], a.split), STRIDE_S)
        m = ds.meta[0]
        start, period = pd.Timestamp(m["t0"]), m["period_s"]
        pos = {int(e): j for j, (_, e) in enumerate(ds.index)}
        for i, al in g.iterrows():
            t = pd.Timestamp(al.alert_time_utc)
            e = int(round((t - start).total_seconds() / period)) - 1
            item = ds[pos[e]]
            assert ds.issue_time(pos[e]) == t, (aid, t, ds.issue_time(pos[e]))
            names = [vocab[r] for r in item["row_ids"]]
            variants = [item]
            for r in range(len(names)):
                keep = np.arange(len(names)) != r
                variants.append(dict(item, values=item["values"][keep], observed=item["observed"][keep],
                                     row_ids=item["row_ids"][keep], stats=item["stats"][keep]))
            with torch.no_grad():
                logits, _ = model(to_device(collate(variants), dev))
            lg = logits.float().cpu().numpy()[:, classes.index(al.fault_type)]
            p = 1.0 / (1.0 + np.exp(-lg))
            base = float(p[0])
            for r, name in enumerate(names):
                rows.append(dict(alert=i, asset_id=aid, alert_time_utc=al.alert_time_utc, fault_type=al.fault_type,
                                 confidence=al.confidence, p_all=round(base, 4), row=name,
                                 p_without=round(float(p[r + 1]), 4), drop=round(base - float(p[r + 1]), 4),
                                 logit_drop=round(float(lg[0] - lg[r + 1]), 3),
                                 seen_absent_in_training=name not in ALWAYS_PRESENT))
            thr = 0.9                                   # the alert threshold of the frozen rule
            ranked = sorted(zip(names, p[1:]), key=lambda x: x[1])
            decisive_all = [(n, q) for n, q in ranked if q < thr]
            decisive = decisive_all[: a.top]
            for rr in rows[-len(names):]:
                rr["decisive"] = rr["p_without"] < thr
            ev = str(al.evidence)
            assert "strongest row " in ev and "depends on" not in ev, ("expected the plain alert file", aid, t)
            attn = ev.split("strongest row ", 1)[1].split(";", 1)[0]

            def name(n):
                return ROW_TEXT.get(n, n) + (" [removal unseen in training]" if n in ALWAYS_PRESENT else "")
            if decisive:
                head = ("The model's alert depends on: " + ", ".join(f"{name(n)} (probability {base:.2f} -> {q:.2f} "
                                                                      "without it)" for n, q in decisive))
                if len(decisive_all) > len(decisive):
                    head += f"; {len(decisive_all)} decisive signals in all"
            else:
                n, q = ranked[0]
                head = (f"No single signal is decisive (probability stays >= 0.9 without each one); largest effect: "
                        f"{name(n)} ({base:.2f} -> {q:.2f})")
            texts.append((i, f"{head}. Strongest attention row: {attn}. Class probability >= 0.9 for 15 min."))
    occ = pd.DataFrame(rows)
    occ.to_csv(OUT_DIR / f"occlusion_{a.split}.csv", index=False)
    out = alerts.copy()
    for i, txt in texts:
        out.loc[i, "evidence"] = txt
    out.to_csv(OUT_DIR / f"predictions_{a.split}_explained.csv", index=False)

    base = occ.groupby("alert").first()
    gap = (base.p_all - base.confidence).abs()
    summary = dict(split=a.split, alerts=len(alerts), windows=len(occ) + len(alerts), seconds=round(time.time() - t0, 1),
                   p_all_vs_confidence_max_abs=round(float(gap.max()), 4),
                   alerts_with_decisive_row=int(occ.groupby("alert").decisive.any().sum()),
                   decisive_rows_not_seen_absent=int((occ.decisive & ~occ.seen_absent_in_training).sum()),
                   decisive_rows=int(occ.decisive.sum()),
                   top_row_by_type=occ.loc[occ.groupby("alert").drop.idxmax()].groupby("fault_type").row
                   .agg(lambda s: s.value_counts().to_dict()).to_dict())
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

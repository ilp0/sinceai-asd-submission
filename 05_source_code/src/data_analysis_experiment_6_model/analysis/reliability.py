"""Reliability comparison on the public validation pumps (PUMP-08/09): causal B1 versus the models.

    python analysis/reliability.py runs/r32-15m-mac-v1/benchmark_predictions_step1500.parquet:15m \
                                   runs/r32-3h-mac-v1/benchmark_predictions_step1000.parquet:3h

Alert reliability uses the organizer scorer at several thresholds. Probability reliability
(calibration) uses the window labels in the prediction file. Output: analysis/reliability.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
from mlhead.benchmark import alerts_from_predictions  # noqa: E402
from mlhead.config import load_config  # noqa: E402

DATA = EXP.parent / "raw/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026"
sys.path.insert(0, str(DATA / "src"))
from retrofit_sim.scoring import score  # noqa: E402

THRESHOLDS = [0.5, 0.7, 0.8, 0.9, 0.95]
KEYS = ["composite_score", "event_f1", "event_recall", "alert_precision", "true_positive_events",
        "false_alert_episodes", "excess_repeat_episodes", "false_alerts_per_asset_day",
        "nuisance_alerts_in_benign_windows", "alert_bursts", "fault_type_recall", "class_recall",
        "timeliness", "median_lead_time_h", "median_delay_after_detectable_h"]


def wilson(k: float, n: float, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def summarize(r: dict) -> dict:
    out = {k: (round(r[k], 3) if isinstance(r[k], float) else r[k]) for k in KEYS}
    n, tp = r["events_scored"], r["true_positive_events"]
    pe = pd.DataFrame(r["per_event"])
    out["recall_ci95"] = wilson(tp, n)
    out["fault_type_ci95"] = wilson(int(pe.type_correct.sum()), n)
    out["class_ci95"] = wilson(int(pe.class_correct.sum()), n)
    denom = tp + r["false_alert_episodes"] + r["excess_repeat_episodes"]
    out["precision_ci95"] = wilson(tp, denom)
    out["first_alert_delay_h"] = {f"{e['asset_id']} {e['fault_type']}": (None if e["delay_after_detectable_h"] is None
                                  else round(e["delay_after_detectable_h"], 2)) for e in r["per_event"]}
    out["predicted_type"] = {f"{e['asset_id']} {e['fault_type']}": e["predicted_fault_type"] for e in r["per_event"]}
    return out


def calibration(pred: pd.DataFrame, classes: list[str], bins: int = 10) -> dict:
    p = np.concatenate([pred[f"p_{c}"].to_numpy() for c in classes])
    y = np.concatenate([pred[f"y_{c}"].to_numpy() for c in classes])
    m = y >= 0
    p, y = p[m], y[m].astype(float)
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    table, ece = [], 0.0
    for b in range(bins):
        s = idx == b
        if s.sum():
            conf, acc = float(p[s].mean()), float(y[s].mean())
            ece += s.mean() * abs(conf - acc)
            table.append(dict(bin=f"{edges[b]:.1f}-{edges[b+1]:.1f}", n=int(s.sum()),
                              mean_predicted=round(conf, 3), observed_positive=round(acc, 3)))
    return dict(ece=round(float(ece), 4), brier=round(float(((p - y) ** 2).mean()), 4),
                targets=int(m.sum()), positive_rate=round(float(y.mean()), 4), table=table)


def main() -> None:
    cfg = load_config(EXP / "configs/r32-3h.yaml")
    ev = pd.read_csv(DATA / "data/full/events_validation.csv")
    assets = pd.read_csv(DATA / "data/full/assets.csv")
    assets = assets[assets.split == "validation"]
    benign = pd.read_csv(DATA / "data/full/benign_windows_train_validation.csv")
    res = {}
    b1 = pd.read_csv(EXP.parent / "data_analysis_expriment_1/outputs/alerts_causal_B1.csv")
    b1 = b1[b1.asset_id.isin(assets.asset_id)]
    res["B1"] = {"alerts": summarize(score(b1, ev, assets, benign))}
    for arg in sys.argv[1:]:
        path, name = arg.rsplit(":", 1)
        pred = pd.read_parquet(EXP / path)
        pred = pred[pred.asset.str.startswith("public/")]
        res[name] = {"alerts": {f"{t:g}": summarize(score(alerts_from_predictions(cfg, pred, t), ev, assets, benign))
                                for t in THRESHOLDS},
                     "calibration": calibration(pred, cfg["labels"]["classes"])}
    (EXP / "analysis/reliability.json").write_text(json.dumps(res, indent=1, default=str))
    rows = [("B1", "-", res["B1"]["alerts"])] + [(n, t, v) for n in res if n != "B1" for t, v in res[n]["alerts"].items()]
    print("model thr composite recall precision FA/day nuisance excess type class timeliness")
    for n, t, v in rows:
        print(n, t, v["composite_score"], v["event_recall"], v["alert_precision"], v["false_alerts_per_asset_day"],
              v["nuisance_alerts_in_benign_windows"], v["excess_repeat_episodes"], v["fault_type_recall"],
              v["class_recall"], v["timeliness"])
    for n in res:
        if "calibration" in res[n]:
            c = res[n]["calibration"]
            print(n, "ECE", c["ece"], "Brier", c["brier"], "positive rate", c["positive_rate"])


if __name__ == "__main__":
    main()

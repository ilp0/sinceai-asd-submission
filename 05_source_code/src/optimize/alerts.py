"""Window probabilities -> causal running average -> alerts -> organizer score and per-fault-type telemetry.

All functions use only data at or before each alert time:
  smooth()       trailing mean over (t - window_s, t] of each class probability, per pump
  fast_alerts()  the experiment-6 alert rule (mlhead.benchmark.alerts_from_predictions): threshold, persistence,
                 cooldown per class, global gap between alerts of one pump. Same output, but it jumps over the
                 candidates that the cooldown or the gap drop (test: check_equivalence()).
"""
from __future__ import annotations

import heapq
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# Organizer package (scorer): $RETROFIT_PKG, else raw/*/RETROFIT_AI_PARTICIPANTS_2026 in the repository root.
PKG = Path(os.environ["RETROFIT_PKG"]) if os.environ.get("RETROFIT_PKG") else \
    next((REPO / "raw").glob("*/RETROFIT_AI_PARTICIPANTS_2026"))
sys.path.insert(0, str(PKG / "src"))
from retrofit_sim import scoring  # noqa: E402

CLASSES = ["BEARING_WEAR", "SUCTION_STRAINER_CLOGGING", "CAVITATION", "DISCHARGE_RESTRICTION", "MISALIGNMENT",
           "IMBALANCE", "IMPELLER_WEAR", "AIR_ENTRAINMENT", "SENSOR_DRIFT", "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT",
           "SENSOR_NOISE_SPIKES", "COMMUNICATION_LOSS"]
MACHINE = set(CLASSES[:8])
SCALARS = ["composite_score", "event_f1", "event_recall", "alert_precision", "false_alerts_per_asset_day",
           "alert_burden", "timeliness", "fault_type_recall", "class_recall", "recall_machine", "recall_sensor",
           "early_warning_rate", "median_lead_time_h", "median_delay_after_detectable_h", "events_scored",
           "true_positive_events", "false_alert_episodes", "false_alerts_raw", "excess_repeat_episodes",
           "repeat_alerts", "nuisance_alerts_in_benign_windows", "alert_bursts", "alerts_scored"]


# ----------------------------------------------------------------------------------------------- predictions
def load_predictions(folder: Path) -> tuple[pd.DataFrame, dict]:
    files = sorted(folder.glob("*.parquet"))
    if not (folder / "DONE").exists():
        raise SystemExit(f"{folder}: prediction set incomplete (no DONE marker)")
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df["asset"] = df["asset"].astype(str)
    df = df.sort_values(["asset", "time"], kind="stable").reset_index(drop=True)
    return df, json.loads((folder / "meta.json").read_text())


def smooth(df: pd.DataFrame, window_s: int) -> pd.DataFrame:
    """Trailing (causal) mean of every p_* column over (t - window_s, t] per pump. A window shorter than the
    stride holds one sample: the raw probability."""
    pcols = [f"p_{c}" for c in CLASSES]
    out = df.copy()
    parts = []
    for _, g in df.groupby("asset", sort=False):
        r = g.set_index("time")[pcols].rolling(f"{int(window_s)}s", closed="right", min_periods=1).mean()
        parts.append(r.to_numpy(np.float32))
    out[pcols] = np.concatenate(parts)
    return out


# ---------------------------------------------------------------------------------------------- alert rule
def fast_alerts(df: pd.DataFrame, threshold: float, persistence_windows: int = 1, cooldown_minutes: float = 720,
                global_gap_minutes: float = 5, class_thresholds: dict | None = None,
                disabled_classes: tuple = (), gap_inclusive: bool = False) -> pd.DataFrame:
    """Same result as mlhead.benchmark.alerts_from_predictions (smooth_windows=1) on the same frame.

    gap_inclusive=True also drops an alert at exactly global_gap_minutes after the previous one. The organizer scorer
    merges alerts that are <= 5 min apart into one burst, so an alert at exactly 5:00 would join the previous burst
    (a mixed-type burst gets no fault-type credit). The default False keeps the experiment-6 behaviour."""
    class_thresholds = class_thresholds or {}
    gap = np.timedelta64(int(global_gap_minutes * 60e9), "ns")
    cool = np.timedelta64(int(cooldown_minutes * 60e9), "ns")
    rows = []
    for asset, g in df.groupby("asset", sort=False):
        times = g["time"].to_numpy(dtype="datetime64[ns]") if g["time"].dt.tz is None else \
            g["time"].dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
        idx = np.arange(len(g))
        cand = {}
        for c in CLASSES:
            if c in disabled_classes:
                continue
            p = g[f"p_{c}"].to_numpy(np.float64)
            above = p >= class_thresholds.get(c, threshold)
            run = idx - np.maximum.accumulate(np.where(above, -1, idx))
            ii = np.flatnonzero(run >= persistence_windows)
            if len(ii):
                cand[c] = (times[ii], p[ii], ii)
        heap = [(v[0][0], -v[1][0], c, 0) for c, v in cand.items()]
        heapq.heapify(heap)
        last = None
        while heap:
            t, negp, c, k = heapq.heappop(heap)
            tc, pc, ic = cand[c]
            if last is not None and (t - last <= gap if gap_inclusive else t - last < gap):
                k2 = max(k + 1, int(np.searchsorted(tc, last + gap, "right" if gap_inclusive else "left")))
            else:
                i = int(ic[k])
                ev = g[f"evidence_{c}"].iloc[i] if f"evidence_{c}" in g else ""
                rows.append(dict(asset_id=str(asset).split("/", 1)[1], alert_time_utc=pd.Timestamp(t, tz="UTC"),
                                 event_class="MACHINE" if c in MACHINE else "SENSOR", fault_type=c,
                                 confidence=round(-negp, 4),
                                 evidence=f"Timestral multi-label head: p={-negp:.2f}; strongest row {ev}",
                                 recommended_action="Review the evidence channel and inspect the pump."))
                last = t
                k2 = max(k + 1, int(np.searchsorted(tc, t + cool, "left")))   # cooldown 0: next candidate
            if k2 < len(tc):
                heapq.heappush(heap, (tc[k2], -pc[k2], c, k2))
    res = pd.DataFrame(rows, columns=["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence",
                                      "evidence", "recommended_action"])
    res = res.sort_values(["alert_time_utc", "asset_id"], kind="stable").reset_index(drop=True)
    res["alert_time_utc"] = pd.to_datetime(res.alert_time_utc, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return res


# ----------------------------------------------------------------------------------------- labels / scoring
class Truth:
    """Events, benign windows and asset rows of the 7 validation pumps (the experiment-6 data folders)."""

    GROUPS = {"all": lambda k: True, "val-orig": lambda k: k.startswith("val-orig/"),
              "val-new": lambda k: k.startswith("val-new")}

    def __init__(self, exp: Path):
        sys.path.insert(0, str(exp))
        from mlhead.config import load_config
        from mlhead.data import discover_assets
        cfg = load_config(exp / "configs/rp3-3h-r32.yaml")
        self.specs = {s.key: s for s in discover_assets(cfg, ("val",))["val"]}
        self.key_of = {s.asset_id: k for k, s in self.specs.items()}

    def subset(self, keys):
        sp = [self.specs[k] for k in keys]
        return (pd.concat([s.events for s in sp], ignore_index=True), pd.DataFrame([s.info for s in sp]),
                pd.concat([s.benign for s in sp], ignore_index=True))

    def score(self, alerts: pd.DataFrame, group: str = "all") -> dict:
        keys = [k for k in self.specs if self.GROUPS[group](k)]
        ev, assets, bn = self.subset(keys)
        ids = set(assets.asset_id)
        r = scoring.score(alerts[alerts.asset_id.isin(ids)], ev, assets, bn)
        r["alert_burden"] = max(0.0, 1.0 - r["false_alerts_per_asset_day"] / 2.0)
        return r

    def event_windows(self) -> pd.DataFrame:
        """Scoring windows of every event (observable or not), as in retrofit_sim.scoring.score."""
        ev, assets, _ = self.subset(list(self.specs))
        ws = dict(zip(assets.asset_id, scoring._ts(assets.window_start_utc)))
        we = dict(zip(assets.asset_id, scoring._ts(assets.window_end_utc)))
        ev = ev.copy()
        for c in ("onset_utc", "detectable_utc", "end_utc"):
            ev[c] = scoring._ts(ev[c])
        rows = []
        for _, e in ev.iterrows():
            s = max(e.onset_utc, ws[e.asset_id])
            if pd.notna(e.detectable_utc):
                s = max(s, e.detectable_utc - scoring.PRE_TOL)
            if pd.isna(e.end_utc):
                end = we[e.asset_id]
            else:
                soft = e.fault_type in scoring.SOFT_END or e.event_class == "SENSOR"
                end = min(e.end_utc + (scoring.POST_TOL if soft else pd.Timedelta(0)), we[e.asset_id])
            rows.append(dict(asset_id=e.asset_id, fault_type=e.fault_type, w_start=s, w_end=end,
                             observable=str(e.observable).lower() in ("true", "1")))
        return pd.DataFrame(rows)


def alert_type_table(alerts: pd.DataFrame, windows: pd.DataFrame, asset_days: float) -> pd.DataFrame:
    """Per predicted fault type: scored bursts and where they fall.
    correct_type  inside a scoring window of an event of the same type
    wrong_type    inside the window of another event type only
    outside       outside every event window (false alert)"""
    if not len(alerts):
        return pd.DataFrame(columns=["fault_type", "bursts", "correct_type", "wrong_type", "outside",
                                     "outside_per_asset_day", "type_precision"])
    bu = scoring.bursts(scoring.load_predictions(alerts))
    out = []
    for _, b in bu.iterrows():
        w = windows[(windows.asset_id == b.asset_id) & (windows.w_start <= b.alert_time_utc) &
                    (b.alert_time_utc <= windows.w_end)]
        kind = "outside" if not len(w) else ("correct_type" if (w.fault_type == b.fault_type).any() else "wrong_type")
        out.append((b.fault_type, kind))
    t = pd.DataFrame(out, columns=["fault_type", "kind"])
    tab = t.pivot_table(index="fault_type", columns="kind", aggfunc="size", fill_value=0)
    for k in ("correct_type", "wrong_type", "outside"):
        if k not in tab:
            tab[k] = 0
    tab["bursts"] = tab[["correct_type", "wrong_type", "outside"]].sum(1)
    tab["outside_per_asset_day"] = tab["outside"] / asset_days
    tab["type_precision"] = tab["correct_type"] / tab["bursts"]
    return tab.reset_index()[["fault_type", "bursts", "correct_type", "wrong_type", "outside",
                              "outside_per_asset_day", "type_precision"]]


def event_type_table(per_event: list[dict]) -> pd.DataFrame:
    """Per true fault type: events, detection, type-correct detection, timeliness, delay."""
    pe = pd.DataFrame(per_event)
    if not len(pe):
        return pd.DataFrame()
    g = pe.groupby("fault_type")
    return pd.DataFrame(dict(
        events=g.size(), detected=g.detected.sum(), type_correct=g.type_correct.sum(),
        recall=g.detected.mean(), type_recall=g.type_correct.mean(), timeliness=g.timeliness.mean(),
        median_delay_h=g.delay_after_detectable_h.median(), repeats=g.repeats.sum())).reset_index()


def average_precision(y: np.ndarray, p: np.ndarray) -> float:
    if y.sum() == 0:
        return float("nan")
    o = np.argsort(-p, kind="stable")
    y = y[o]
    tp = np.cumsum(y)
    prec = tp / np.arange(1, len(y) + 1)
    return float((prec * y).sum() / y.sum())


def check_equivalence(exp: Path, pred_file: Path) -> None:
    """fast_alerts == alerts_from_predictions on a saved 60 s prediction file, at several rules."""
    sys.path.insert(0, str(exp))
    from mlhead.benchmark import alerts_from_predictions
    from mlhead.config import load_config
    cfg = load_config(exp / "configs/rp3-3h-r32.yaml")
    df = pd.read_parquet(pred_file)
    df["asset"] = df["asset"].astype(str)
    for thr, pw, gap in [(0.5, 1, 5), (0.7, 3, 5), (0.9, 15, 5), (0.99, 1, 120), (0.8, 2, 0)]:
        a = alerts_from_predictions(cfg, df, threshold=thr, rules=dict(persistence_windows=pw, global_gap_minutes=gap,
                                                                        cooldown_minutes=720))
        b = fast_alerts(df, thr, pw, 720, gap)
        key = ["asset_id", "alert_time_utc", "fault_type", "confidence"]
        a = a.sort_values(key).reset_index(drop=True)[key]
        b = b.sort_values(key).reset_index(drop=True)[key]
        ok = a.equals(b)
        print(f"thr={thr} persistence={pw} gap={gap}: {len(a)} vs {len(b)} alerts, equal={ok}")
        if not ok:
            raise SystemExit("fast_alerts differs from alerts_from_predictions")


if __name__ == "__main__":
    check_equivalence(Path(sys.argv[1]), Path(sys.argv[2]))

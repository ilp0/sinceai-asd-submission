"""Benchmark score (BENCHMARK_RULES.md section 4) with the organizer's own scorer.

Every window of the benchmark assets is predicted at `stride_s`. The probabilities become alerts
(`alerts_from_predictions`: threshold, persistence, cooldown, 5-min cross-class rule), and
`retrofit_sim.scoring.score` scores them against the labelled events and benign windows of the
same assets. Settings come from the optional `benchmark:` section of the configuration; the defaults
below apply when it is absent:

    benchmark:
      enabled: true
      assets: ["*"]                                  # fnmatch on validation asset keys
      stride_s: 60
      scorer_src: ../raw/.../RETROFIT_AI_PARTICIPANTS_2026/src
      thresholds: [0.5, 0.7, 0.9, 0.99]              # every metric is scored at every threshold

Scoring groups: one per source (for example "val-orig", "val-new-45001") and "all" (every benchmark
asset in one scorer call; asset IDs must be unique across sources). With one source, only "all".
Scalar keys: "<group>/<metric>@<threshold>", plus "<group>/composite_max" and "<group>/best_threshold".
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .config import resolve
from .data import WindowDataset, discover_assets, matches

DEFAULTS = dict(
    enabled=True,
    assets=["*"],
    stride_s=60,
    scorer_src="../raw/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026/src",
    thresholds=[0.5, 0.7, 0.9, 0.99],
)
MACHINE = {"BEARING_WEAR", "SUCTION_STRAINER_CLOGGING", "CAVITATION", "DISCHARGE_RESTRICTION",
           "MISALIGNMENT", "IMBALANCE", "IMPELLER_WEAR", "AIR_ENTRAINMENT"}
# Scalar results of retrofit_sim.scoring.score that go to TensorBoard and history.
SCALARS = ["composite_score", "event_f1", "event_recall", "alert_precision", "false_alerts_per_asset_day",
           "alert_burden", "timeliness", "fault_type_recall", "class_recall", "recall_machine", "recall_sensor",
           "early_warning_rate", "median_lead_time_h", "events_scored", "true_positive_events",
           "false_alert_episodes", "excess_repeat_episodes", "nuisance_alerts_in_benign_windows", "alert_bursts"]


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("benchmark") or {})}


def _scorer(cfg: dict):
    src = str(resolve(settings(cfg)["scorer_src"]))
    if src not in sys.path:
        sys.path.insert(0, src)
    from retrofit_sim.scoring import score
    return score


RULE_DEFAULTS = dict(global_gap_minutes=5, smooth_windows=1, class_thresholds=None, disabled_classes=())


def alert_rules(cfg: dict, rules: dict | None = None) -> dict:
    """Alert rules: `predict` settings of the config, then `rules` overrides. Extra keys (all optional):
    global_gap_minutes  a candidate this soon after the previous kept alert of the asset (any class) is dropped
    smooth_windows      trailing (causal) mean of the probability over this many windows before the threshold
    class_thresholds    {class: threshold} replaces the common threshold for these classes
    disabled_classes    classes that never raise an alert"""
    r = {**RULE_DEFAULTS, **{k: v for k, v in cfg["predict"].items() if k != "max_windows"}, **(rules or {})}
    return r


def alerts_from_predictions(cfg: dict, df: pd.DataFrame, threshold: float | None = None,
                            rules: dict | None = None) -> pd.DataFrame:
    """Window probabilities -> submission-format alerts. Uses only windows at or before each alert time.

    Per asset and class: `persistence_windows` consecutive windows at or above the threshold make a
    candidate. Candidates are kept in time order. A kept alert starts `cooldown_minutes` of quiet for
    its class. A candidate within `global_gap_minutes` (default 5) of the previous kept alert is dropped:
    the scorer merges alerts within 5 min into one burst, and a burst with mixed types earns no type credit.
    See `alert_rules` for the optional settings."""
    r = alert_rules(cfg, rules)
    thr = r["threshold"] if threshold is None else threshold
    class_thr = dict(r["class_thresholds"] or {})
    gap = pd.Timedelta(minutes=r["global_gap_minutes"])
    cooldown = pd.Timedelta(minutes=r["cooldown_minutes"])
    sw = int(r["smooth_windows"])
    df = df.sort_values(["asset", "time"])
    alerts = []
    for asset, g in df.groupby("asset", observed=True):
        cand = []
        times = list(g.time)
        idx = np.arange(len(g))
        for c in cfg["labels"]["classes"]:
            if c in r["disabled_classes"]:
                continue
            p = g[f"p_{c}"].to_numpy(np.float64)
            if sw > 1:
                p = pd.Series(p).rolling(sw, min_periods=1).mean().to_numpy()
            # Run length of consecutive windows at or above the threshold, ending at each window.
            run = idx - np.maximum.accumulate(np.where(p >= class_thr.get(c, thr), -1, idx))
            for i in np.flatnonzero(run >= r["persistence_windows"]):
                cand.append((times[i], -float(p[i]), c, int(i)))
        kept, quiet_until = [], {}
        for t, negp, c, i in sorted(cand):
            if t < quiet_until.get(c, t):
                continue
            if kept and t - kept[-1]["alert_time_utc"] < gap:
                continue
            ev = g[f"evidence_{c}"].iloc[i] if f"evidence_{c}" in g else ""
            kept.append(dict(asset_id=str(asset).split("/", 1)[1], alert_time_utc=t,
                             event_class="MACHINE" if c in MACHINE else "SENSOR", fault_type=c,
                             confidence=round(-negp, 4),
                             evidence=f"Timestral multi-label head: p={-negp:.2f}; strongest row {ev}",
                             recommended_action="Review the evidence channel and inspect the pump."))
            quiet_until[c] = t + cooldown
        alerts += kept
    res = pd.DataFrame(alerts, columns=["asset_id", "alert_time_utc", "event_class", "fault_type", "confidence",
                                        "evidence", "recommended_action"])
    res["alert_time_utc"] = pd.to_datetime(res.alert_time_utc, utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return res


class Benchmark:
    """Holds the benchmark windows and the label tables; `run(model)` returns the score."""

    def __init__(self, cfg: dict):
        self.cfg, self.s = cfg, settings(cfg)
        specs = [s for s in discover_assets(cfg, ("val",))["val"] if matches(s.key, self.s["assets"])]
        if not specs:
            raise ValueError(f"no validation asset matches benchmark.assets {self.s['assets']}")
        self.ds = WindowDataset(cfg, "val", self.s["stride_s"], keys=[s.key for s in specs])
        # One scoring group per source (asset IDs are only unique inside a source) and "all".
        self.keys = [s.key for s in specs]
        per_src = {}
        for s in specs:
            per_src.setdefault(s.key.split("/", 1)[0], []).append(s)
        groups = {"all": specs}
        if len(per_src) > 1:
            groups = {**per_src, "all": specs}
            ids = [s.asset_id for s in specs]
            if len(ids) != len(set(ids)):
                raise ValueError("benchmark asset IDs repeat across sources; the 'all' group needs unique IDs")
        self.groups = {}
        for name, items in groups.items():
            self.groups[name] = dict(
                prefixes=tuple(sorted({s.key.split("/", 1)[0] + "/" for s in items})),
                assets=pd.DataFrame([s.info for s in items]),
                events=pd.concat([s.events for s in items], ignore_index=True),
                benign=pd.concat([s.benign for s in items], ignore_index=True))
        self.score_fn = _scorer(cfg)

    def thresholds(self) -> list[float]:
        return sorted(set(self.s["thresholds"]) | {self.cfg["predict"]["threshold"]})

    def score_predictions(self, pred: pd.DataFrame) -> dict:
        """Every scorer metric at every threshold, for every scoring group."""
        out, details = {}, {}
        for name, g in self.groups.items():
            part = pred[pred.asset.str.startswith(g["prefixes"])]
            best = (-1.0, None)
            for thr in self.thresholds():
                alerts = alerts_from_predictions(self.cfg, part, thr)
                r = self.score_fn(alerts, g["events"], g["assets"], g["benign"])
                r["alert_burden"] = max(0.0, 1.0 - r["false_alerts_per_asset_day"] / 2.0)
                for k in SCALARS:
                    v = r.get(k)
                    if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
                        out[f"{name}/{k}@{thr:g}"] = float(v)
                if r["composite_score"] > best[0]:
                    best = (float(r["composite_score"]), thr)
                details[f"{name}@{thr:g}"] = dict(result={k: v for k, v in r.items() if k != "per_event"},
                                                  per_event=r["per_event"], alerts=alerts)
            out[f"{name}/composite_max"], out[f"{name}/best_threshold"] = best
        return dict(scalars=out, details=details)

    def run(self, model, device, pred: pd.DataFrame | None = None) -> dict:
        """Score `pred` (window predictions that contain the benchmark windows at the same stride),
        or predict the benchmark windows first."""
        from .train import predict_windows
        if pred is None:
            pred = predict_windows(model, self.ds, self.cfg, device)
        else:
            pred = pred[pred.asset.isin(self.keys)]
        res = self.score_predictions(pred)
        res["predictions"] = pred
        return res

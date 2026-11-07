"""Window-level and segment-level metrics for independent per-class probabilities (numpy only)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def auroc(y: np.ndarray, s: np.ndarray) -> float:
    pos, neg = y.sum(), len(y) - y.sum()
    if pos == 0 or neg == 0:
        return float("nan")
    ranks = pd.Series(s).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    if y.sum() == 0:
        return float("nan")
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    tp = np.cumsum(y)
    precision = tp / np.arange(1, len(y) + 1)
    return float((precision * y).sum() / y.sum())


def segments(flags: np.ndarray) -> list[tuple[int, int]]:
    """[start, stop) runs of True."""
    d = np.diff(np.concatenate([[0], flags.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def evaluate_predictions(df: pd.DataFrame, classes: list[str], threshold: float, stride_s: float,
                         window_weight: float = 1.0) -> dict:
    """`df`: one row per window with asset, time, p_<class>, y_<class> (1/0/-1 ignored).

    Segment recall: a contiguous run of positive windows of one class on one asset counts as hit
    when any window in it reaches `threshold`. False windows per asset-day: windows above
    threshold whose label is 0, divided by the asset-days covered."""
    out, per_class = {}, {}
    days = df.groupby("asset").time.agg(lambda t: (t.max() - t.min()).total_seconds() / 86400 + stride_s / 86400).sum()
    for c in classes:
        p, y = df[f"p_{c}"].to_numpy(), df[f"y_{c}"].to_numpy()
        m = y >= 0
        r = dict(positives=int((y == 1).sum()), auroc=auroc(y[m], p[m]), auprc=average_precision(y[m], p[m]))
        hits = total = 0
        for _, g in df.sort_values("time").groupby("asset"):
            yy, pp = g[f"y_{c}"].to_numpy(), g[f"p_{c}"].to_numpy()
            for a, b in segments(yy == 1):
                total += 1
                hits += int((pp[a:b] >= threshold).any())
        r["segments"], r["segment_recall"] = total, (hits / total if total else float("nan"))
        r["false_windows_per_asset_day"] = float(window_weight * ((p >= threshold) & (y == 0)).sum() / max(days, 1e-9))
        per_class[c] = r
    for k in ("auroc", "auprc", "segment_recall"):
        vals = [v[k] for v in per_class.values() if not np.isnan(v[k])]
        out[f"macro_{k}"] = float(np.mean(vals)) if vals else float("nan")
        out[f"n_classes_{k}"] = len(vals)
    out["false_windows_per_asset_day"] = float(sum(v["false_windows_per_asset_day"] for v in per_class.values()))
    out["per_class"] = per_class
    return out

"""Data: dense per-asset caches, per-window labels and packed batches for the Timestral backbone.

Time convention. Grid cell i of an asset covers [t0 + i*p, t0 + (i+1)*p) for sample period p.
A window that ends at cell i uses cells i-L+1 .. i and is issued at t_end(i) = t0 + (i+1)*p.
Its label is the event state at t_end(i). All inputs are at or before t_end(i): the window is causal.
"""
from __future__ import annotations

import fnmatch
import glob
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .config import data_fingerprint, resolve

DERIVED = ("running", "row_present", "comm_loss_flag", "out_of_range_flag")
PATCH = 32  # Timestral-28M patch size; checked against the backbone config at model build
N_STATS = 6


# --------------------------------------------------------------------------- sources


@dataclass
class AssetSpec:
    key: str            # "<source>/<asset_id>"
    asset_id: str
    telemetry_dir: Path
    info: dict          # assets.csv row
    events: pd.DataFrame
    benign: pd.DataFrame


def _read_first(root: Path, names: list[str], kind: str) -> pd.DataFrame:
    frames = [pd.read_csv(root / n) for n in names if (root / n).exists()]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    if kind == "events" and "event_id" in df:
        df = df.drop_duplicates("event_id")
    return df


def _source_roots(src: dict) -> list[tuple[str, Path]]:
    if "root_glob" in src:
        roots = sorted(Path(p) for p in glob.glob(str(resolve(src["root_glob"]))) if Path(p).is_dir())
        return [(f"{src['name']}-{r.name}", r) for r in roots]
    return [(src["name"], resolve(src["root"]))]


def matches(key: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(key, p) for p in patterns)


def discover_assets(cfg: dict, roles: tuple[str, ...] = ("train", "val")) -> dict[str, list[AssetSpec]]:
    """Asset specs per role. Locked assets are never opened; an overlap of roles is an error."""
    d = cfg["data"]
    pats = {"train": d["train_assets"], "val": d["val_assets"]}
    out: dict[str, list[AssetSpec]] = {r: [] for r in roles}
    for src in d["sources"]:
        for name, root in _source_roots(src):
            assets = pd.read_csv(root / src.get("assets", "assets.csv"))
            events = _read_first(root, src.get("events", []), "events")
            benign = _read_first(root, src.get("benign", []), "benign")
            for row in assets.to_dict("records"):
                key = f"{name}/{row['asset_id']}"
                if matches(key, d["locked_assets"]):
                    if any(matches(key, pats[r]) for r in pats):
                        raise ValueError(f"{key} is locked but selected for training or validation")
                    continue
                hit = [r for r in pats if matches(key, pats[r])]
                if len(hit) > 1:
                    raise ValueError(f"{key} matches both train and val patterns")
                if not hit or hit[0] not in roles:
                    continue
                aid = row["asset_id"]
                out[hit[0]].append(AssetSpec(
                    key=key, asset_id=aid,
                    telemetry_dir=root / src.get("telemetry", "telemetry") / f"asset_id={aid}",
                    info=row,
                    events=events[events.asset_id == aid] if len(events) else events,
                    benign=benign[benign.asset_id == aid] if len(benign) else benign,
                ))
    return out


# --------------------------------------------------------------------------- caching


def _ts(x) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _grid(spec: AssetSpec, cfg: dict):
    p = int(cfg["input"]["sample_period_s"])
    t0 = _ts(spec.info["window_start_utc"])
    t1 = _ts(spec.info["window_end_utc"])
    n = int((t1 - t0).total_seconds() // p)
    return p, t0, t1, n


def _cell_index(times: pd.Series, t0: pd.Timestamp, p: int) -> np.ndarray:
    return ((times - t0).dt.total_seconds().to_numpy() // p).astype(np.int64)


def _bin_mean(idx: np.ndarray, vals: np.ndarray, n: int) -> np.ndarray:
    """NaN-aware mean of `vals` (rows, C) into n cells."""
    out = np.zeros((n, vals.shape[1]), np.float64)
    cnt = np.zeros((n, vals.shape[1]), np.float64)
    ok = ~np.isnan(vals)
    np.add.at(out, idx, np.where(ok, vals, 0.0))
    np.add.at(cnt, idx, ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, out / cnt, np.nan).astype(np.float32)


def build_asset_arrays(spec: AssetSpec, cfg: dict) -> tuple[np.ndarray, dict]:
    """Dense (n, C_used) float32 array on the asset grid, NaN = not observed, plus metadata."""
    inp = cfg["input"]
    p, t0, t1, n = _grid(spec, cfg)
    available = set(str(spec.info.get("channels_available", "")).split("|"))
    channels = [c for c in inp["channels"] if c in available]
    derived = [c for c in inp["derived"] if c in DERIVED]
    tel = pd.read_parquet(spec.telemetry_dir, columns=["timestamp_utc", "operating_mode", "quality_flags", *channels])
    tel["timestamp_utc"] = pd.to_datetime(tel["timestamp_utc"], utc=True)
    tel = tel[(tel.timestamp_utc >= t0) & (tel.timestamp_utc < t1)]
    idx = _cell_index(tel.timestamp_utc, t0, p)
    raw = tel[channels].to_numpy(np.float64) if channels else np.zeros((len(tel), 0))
    qf = tel.quality_flags.to_numpy(np.int64)
    der_cols = {
        "running": (tel.operating_mode.astype(str) == "RUNNING").to_numpy(np.float64),
        "row_present": np.ones(len(tel)),
        "comm_loss_flag": ((qf & 1) > 0).astype(np.float64),
        "out_of_range_flag": ((qf & 2) > 0).astype(np.float64),
    }
    vals = _bin_mean(idx, raw, n)
    der = _bin_mean(idx, np.stack([der_cols[c] for c in derived], 1) if derived else np.zeros((len(tel), 0)), n)
    if "row_present" in derived:
        # Fraction of expected rows present in the cell; 0 (observed) during gateway outages.
        j = derived.index("row_present")
        cnt = np.bincount(idx, minlength=n)[:n].astype(np.float32)
        der[:, j] = np.minimum(cnt / p, 1.0)

    norm = inp["normalization"]
    stats = {}
    if norm["method"] == "asset_baseline" and channels:
        base_n = int(norm["baseline_hours"] * 3600 // p)
        base = vals[:base_n]
        running = der_cols["running"]
        run_cells = _bin_mean(idx, running[:, None], n)[:base_n, 0] > 0.5
        for j, c in enumerate(channels):
            col = base[:, j]
            sel = col[run_cells & ~np.isnan(col)] if norm.get("running_only", True) else col[~np.isnan(col)]
            if sel.size < 30:
                sel = col[~np.isnan(col)]
            if sel.size == 0:
                med, scale = 0.0, 1.0
            else:
                med = float(np.median(sel))
                scale = float(1.4826 * np.median(np.abs(sel - med)))
                scale = max(scale, norm.get("min_scale_fraction", 0.01) * abs(med), 1e-3)
            vals[:, j] = (vals[:, j] - med) / scale
            stats[c] = dict(median=med, scale=scale, n=int(sel.size))
    elif norm["method"] != "none":
        raise ValueError(f"unknown normalization {norm['method']!r}")
    arr = np.concatenate([vals, der], axis=1).astype(np.float32)
    meta = dict(key=spec.key, asset_id=spec.asset_id, t0=t0.isoformat(), t1=t1.isoformat(), period_s=p,
                n=n, rows=channels + derived, norm=stats,
                info={k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in spec.info.items()})
    return arr, meta


def build_labels(spec: AssetSpec, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """(n, K) int8 labels at each cell's issue time t_end(i): 1 positive, 0 negative, -1 ignored.
    Also (n,) bool: issue time inside a labelled benign window."""
    lab = cfg["labels"]
    classes = lab["classes"]
    p, t0, t1, n = _grid(spec, cfg)
    t_end = t0 + pd.to_timedelta((np.arange(n) + 1) * p, unit="s")
    y = np.zeros((n, len(classes)), np.int8)
    pos_iv, ign_iv = [], []
    for e in spec.events.to_dict("records") if len(spec.events) else []:
        if e["fault_type"] not in classes:
            continue
        k = classes.index(e["fault_type"])
        onset = _ts(e["onset_utc"])
        end = _ts(e["end_utc"]) if pd.notna(e.get("end_utc")) else t1
        end = end + pd.Timedelta(minutes=lab.get("end_pad_minutes", 0))
        observable = str(e.get("observable")).lower() == "true" and pd.notna(e.get("detectable_utc"))
        if not observable:
            if lab.get("ignore_unobservable", True):
                ign_iv.append((k, onset, end))
            continue
        det = _ts(e["detectable_utc"])
        start = {"detectable": det, "onset": onset,
                 "scoring": max(onset, det - pd.Timedelta(hours=6))}[lab["start"]]
        start = start - pd.Timedelta(minutes=lab.get("lead_minutes", 0))
        if lab.get("ignore_pre_detectable", True) and onset < start:
            ign_iv.append((k, onset, start))
        pos_iv.append((k, start, end))
        # The scorer still matches alerts up to 30 min after episodes that end without a repair
        # (cavitation, air entrainment, sensor faults): no loss there instead of a negative target.
        if e["fault_type"] in lab.get("post_end_ignore_classes", []) and pd.notna(e.get("end_utc")):
            ign_iv.append((k, end, end + pd.Timedelta(minutes=lab.get("post_end_ignore_minutes", 30))))
    for k, a, b in ign_iv:
        y[(t_end >= a) & (t_end < b), k] = -1
    for k, a, b in pos_iv:  # positives win over ignore regions of the same class
        y[(t_end >= a) & (t_end < b), k] = 1
    benign = np.zeros(n, bool)
    for b in spec.benign.to_dict("records") if len(spec.benign) else []:
        benign |= (t_end >= _ts(b["start_utc"])) & (t_end < _ts(b["end_utc"]))
    return y, benign


def asset_dir(root: Path, role: str, key: str) -> Path:
    """One cache folder per asset key: stable whatever the role patterns select."""
    return root / role / hashlib.sha256(key.encode()).hexdigest()[:16]


def prepare(cfg: dict, log=print) -> Path:
    """Write cache/<fingerprint>/<role>/<n>/{values,labels,benign}.npy + meta.json for every train/val asset."""
    root = resolve(cfg["data"]["cache_dir"]) / data_fingerprint(cfg)
    specs = discover_assets(cfg)
    for role, items in specs.items():
        for spec in items:
            d = asset_dir(root, role, spec.key)
            if (d / "meta.json").exists():
                continue
            d.mkdir(parents=True, exist_ok=True)
            arr, meta = build_asset_arrays(spec, cfg)
            y, benign = build_labels(spec, cfg)
            np.save(d / "values.npy", arr)
            np.save(d / "labels.npy", y)
            np.save(d / "benign.npy", benign)
            meta["positive_cells"] = {c: int((y[:, k] == 1).sum()) for k, c in enumerate(cfg["labels"]["classes"])}
            (d / "meta.tmp").write_text(json.dumps(meta, indent=1, default=str))
            (d / "meta.tmp").replace(d / "meta.json")  # meta.json last: marks the asset as complete
            log(json.dumps(dict(role=role, asset=spec.key, cells=meta["n"], rows=meta["rows"],
                                positives={k: v for k, v in meta["positive_cells"].items() if v})))
    (root / "config.json").write_text(json.dumps({k: cfg[k] for k in ("input", "labels", "data")}, indent=1))
    return root


# --------------------------------------------------------------------------- windows


def row_vocabulary(cfg: dict) -> list[str]:
    """Global row identities for the channel embedding."""
    return list(cfg["input"]["channels"]) + [c for c in cfg["input"]["derived"] if c in DERIVED]


class WindowDataset(torch.utils.data.Dataset):
    """Windows of `input.minutes` ending every `stride` seconds on each asset of one role."""

    def __init__(self, cfg: dict, role: str, stride_s: int | None = None, keys: list[str] | None = None):
        self.cfg = cfg
        self.role = role
        root = resolve(cfg["data"]["cache_dir"]) / data_fingerprint(cfg)
        # Only the assets that the current role patterns select (never locked or stale ones).
        selected = [s.key for s in discover_assets(cfg, (role,))[role]]
        keys = [k for k in selected if keys is None or k in keys]
        dirs = [asset_dir(root, role, k) for k in keys]
        missing = [k for k, d in zip(keys, dirs) if not (d / "meta.json").exists()]
        if not keys or missing:
            raise FileNotFoundError(f"assets not cached for role {role}: {missing or 'none selected'}; "
                                    "run `run.py prepare` first")
        vocab = row_vocabulary(cfg)
        self.meta = [json.loads((d / "meta.json").read_text()) for d in dirs]
        self._dirs = dirs
        self._values = None   # memory maps open lazily in each DataLoader worker (spawn/forkserver safe)
        self.labels = [np.load(d / "labels.npy") for d in dirs]
        self.benign = [np.load(d / "benign.npy") for d in dirs]
        self.row_ids = [np.array([vocab.index(r) for r in m["rows"]], np.int64) for m in self.meta]
        p = self.meta[0]["period_s"]
        self.period = p
        self.length = int(cfg["input"]["minutes"] * 60 // p)
        self.padded = int(math.ceil(self.length / PATCH) * PATCH)
        stride = max(1, int((stride_s or cfg["data"]["train_stride_s"]) // p))
        first_ok = self.length - 1
        if cfg["input"].get("skip_baseline_period", True) and cfg["input"]["normalization"]["method"] != "none":
            first_ok = max(first_ok, int(cfg["input"]["normalization"]["baseline_hours"] * 3600 // p) - 1)
        idx = []
        for a, m in enumerate(self.meta):
            ends = np.arange(first_ok, m["n"], stride)
            idx.append(np.stack([np.full_like(ends, a), ends], 1))
        self.index = np.concatenate(idx)
        lab = np.stack([self.labels[a][e] for a, e in self.index])
        self.window_labels = lab                          # (W, K) int8
        self.has_positive = (lab == 1).any(1)
        self.is_benign = np.array([self.benign[a][e] for a, e in self.index])

    @property
    def values(self) -> list[np.ndarray]:
        if self._values is None:
            self._values = [np.load(d / "values.npy", mmap_mode="r") for d in self._dirs]
        return self._values

    def __getstate__(self):
        state = self.__dict__.copy()
        state["_values"] = None   # never pickle array contents into workers
        return state

    def __len__(self):
        return len(self.index)

    def issue_time(self, j: int) -> pd.Timestamp:
        a, e = self.index[j]
        m = self.meta[a]
        return pd.Timestamp(m["t0"]) + pd.Timedelta(seconds=(int(e) + 1) * m["period_s"])

    def __getitem__(self, j: int) -> dict:
        a, e = (int(v) for v in self.index[j])
        L, P = self.length, self.padded
        win = np.asarray(self.values[a][e - L + 1: e + 1], np.float32).T  # (C, L); never reads past e
        obs = ~np.isnan(win)
        z = np.where(obs, win, 0.0).astype(np.float32)
        stats = np.zeros((win.shape[0], N_STATS), np.float32)
        cnt = obs.sum(1)
        has = cnt > 0
        if has.any():
            w = win[has]
            last_idx = L - 1 - np.argmax(obs[has][:, ::-1], axis=1)
            with np.errstate(all="ignore"):
                stats[has] = np.stack([
                    np.nanmean(w, 1), np.nanstd(w, 1), w[np.arange(len(w)), last_idx],
                    np.nanmin(w, 1), np.nanmax(w, 1), cnt[has] / L], 1)
        stats = np.arcsinh(np.nan_to_num(stats))
        values = np.zeros((win.shape[0], P), np.float32)
        observed = np.zeros((win.shape[0], P), bool)
        values[:, P - L:] = z            # left padding = unobserved leading cells
        observed[:, P - L:] = obs
        y = self.labels[a][e]
        return dict(values=values, observed=observed, row_ids=self.row_ids[a], stats=stats,
                    labels=(y == 1).astype(np.float32), label_mask=(y >= 0).astype(np.float32), window=j)


def collate(items: list[dict]) -> dict:
    """Pack rows of all windows: (R, P) values, group ids per row, (B, K) labels."""
    counts = [len(it["row_ids"]) for it in items]
    return dict(
        values=torch.from_numpy(np.concatenate([it["values"] for it in items])),
        observed=torch.from_numpy(np.concatenate([it["observed"] for it in items])),
        row_ids=torch.from_numpy(np.concatenate([it["row_ids"] for it in items])),
        stats=torch.from_numpy(np.concatenate([it["stats"] for it in items])),
        group_ids=torch.repeat_interleave(torch.arange(len(items)), torch.tensor(counts)),
        labels=torch.from_numpy(np.stack([it["labels"] for it in items])),
        label_mask=torch.from_numpy(np.stack([it["label_mask"] for it in items])),
        window=torch.tensor([it["window"] for it in items]),
    )


class StepBatchSampler(torch.utils.data.Sampler):
    """Deterministic batches from step `start` to `stop`: batch s depends only on (seed, s), so a
    resumed run sees the same batches. Mix: positive windows, benign windows, uniform rest."""

    def __init__(self, ds: WindowDataset, batch_size: int, seed: int, start: int, stop: int,
                 positive_fraction: float, benign_fraction: float):
        self.ds, self.bs, self.seed, self.start, self.stop = ds, batch_size, seed, start, stop
        self.pos = np.flatnonzero(ds.has_positive)
        self.ben = np.flatnonzero(ds.is_benign & ~ds.has_positive)
        self.pf = positive_fraction if len(self.pos) else 0.0
        self.bf = benign_fraction if len(self.ben) else 0.0

    def __len__(self):
        return max(0, self.stop - self.start)

    def batch(self, step: int) -> list[int]:
        rng = np.random.default_rng([self.seed, step])
        n_pos = rng.binomial(self.bs, self.pf)
        n_ben = rng.binomial(self.bs - n_pos, min(1.0, self.bf / (1 - self.pf))) if self.bf and self.pf < 1 else 0
        n_any = self.bs - n_pos - n_ben
        parts = [rng.choice(self.pos, n_pos), rng.choice(self.ben, n_ben) if n_ben else [],
                 rng.integers(0, len(self.ds), n_any)]
        return [int(i) for part in parts for i in part]

    def __iter__(self):
        for s in range(self.start, self.stop):
            yield self.batch(s)

    def expected_positive_rate(self) -> np.ndarray:
        """Per-class positive share of labelled targets under this sampler (for pos_weight)."""
        y = self.ds.window_labels

        def rate(sel):
            if len(sel) == 0:
                return np.zeros(y.shape[1])
            s = y[sel]
            return (s == 1).sum(0) / np.maximum((s >= 0).sum(0), 1)

        rest = 1 - self.pf - self.bf
        return self.pf * rate(self.pos) + self.bf * rate(self.ben) + rest * rate(np.arange(len(y)))

"""Submission predictions: one trained checkpoint -> window probabilities -> alerts in the organizer format.

    python analysis/predict_test.py --split test        # PUMP-10..12 -> submission CSV (no labels are read)
    python analysis/predict_test.py --split validation  # PUMP-08/09, scored with the organizer scorer (check)

Model: experiment 6 round 3, run rp3-3h-r32-v1 (3 h context at 10 s cells, LoRA 32/64), checkpoint
`runs/<run>/<checkpoint>.pt`. The checkpoint is the last one saved, not one chosen on validation.
Alert rule (user decision 7 Nov 2026, chosen on validation pumps only): threshold 0.9, persistence 15 windows at the
60 s stride (15 min), 12 h cooldown per class, 5 min gap between alerts of one asset (configs/base.yaml otherwise).

Causality: the 24 h asset baseline (robust z-score) uses the first 24 h of the asset window, and no window ends
inside those 24 h. Each window contains only cells at or before its issue time (WindowDataset.__getitem__), so an
alert at time t uses only data with timestamps <= t. Test assets are built directly from telemetry and assets.csv:
the training loader's locked-asset check stays in place, and no events, benign windows or maintenance records of
the test assets are opened.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
from mlhead.benchmark import alerts_from_predictions, _scorer  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from mlhead.data import AssetSpec, PATCH, WindowDataset, build_asset_arrays, row_vocabulary  # noqa: E402
from mlhead.model import TimestralMultiLabel  # noqa: E402
from mlhead.train import predict_windows  # noqa: E402

PKG = next((EXP.parent / "raw").glob("*/RETROFIT_AI_PARTICIPANTS_2026"))
DATA = PKG / "data" / "full"
SPLITS = {"test": ["PUMP-10", "PUMP-11", "PUMP-12"], "validation": ["PUMP-08", "PUMP-09"]}
RULES = dict(threshold=0.9, persistence_windows=15, cooldown_minutes=720, global_gap_minutes=5)
STRIDE_S = 60

ACTIONS = {
    "BEARING_WEAR": "Check bearing temperature and vibration trend; plan bearing inspection and lubrication at the next stop.",
    "SUCTION_STRAINER_CLOGGING": "Compare suction pressure with the regime baseline; inspect and clean the suction strainer.",
    "CAVITATION": "Check suction pressure and NPSH margin; reduce speed or open the suction side if possible.",
    "DISCHARGE_RESTRICTION": "Check discharge valve position and downstream line for restriction or fouling.",
    "MISALIGNMENT": "Check vibration at running-speed harmonics; plan a shaft alignment check.",
    "IMBALANCE": "Check 1x running-speed vibration; inspect the impeller for deposits or damage.",
    "IMPELLER_WEAR": "Compare head and flow with the pump curve; plan an impeller inspection.",
    "AIR_ENTRAINMENT": "Check suction tank level and suction-side leaks; vent the pump casing.",
    "SENSOR_DRIFT": "Verify the instrument against a reference reading before acting on its value.",
    "SENSOR_STUCK": "Check the transmitter and its wiring; the reading does not follow the process.",
    "SENSOR_CALIBRATION_SHIFT": "Recalibrate or cross-check the instrument; do not act on its value until verified.",
    "SENSOR_NOISE_SPIKES": "Check instrument wiring, grounding and connectors for intermittent faults.",
    "COMMUNICATION_LOSS": "Check the gateway and fieldbus connection of the pump.",
}


class AssetWindows(WindowDataset):
    """WindowDataset over arrays built in memory for named assets (no cache, no labels)."""

    def __init__(self, cfg: dict, specs: list[AssetSpec], stride_s: int):
        self.cfg, self.role = cfg, "predict"
        vocab = row_vocabulary(cfg)
        built = [build_asset_arrays(s, cfg) for s in specs]
        self._values = [a for a, _ in built]
        self.meta = [m for _, m in built]
        self._dirs = []
        K = len(cfg["labels"]["classes"])
        self.labels = [np.full((m["n"], K), -1, np.int8) for m in self.meta]   # unknown: never read for test
        self.benign = [np.zeros(m["n"], bool) for m in self.meta]
        self.row_ids = [np.array([vocab.index(r) for r in m["rows"]], np.int64) for m in self.meta]
        p = self.meta[0]["period_s"]
        self.period = p
        self.length = int(cfg["input"]["minutes"] * 60 // p)
        self.padded = int(math.ceil(self.length / PATCH) * PATCH)
        stride = max(1, int(stride_s // p))
        first_ok = self.length - 1
        if cfg["input"].get("skip_baseline_period", True) and cfg["input"]["normalization"]["method"] != "none":
            first_ok = max(first_ok, int(cfg["input"]["normalization"]["baseline_hours"] * 3600 // p) - 1)
        self.index = np.concatenate([np.stack([np.full_like(e, a), e], 1)
                                     for a, m in enumerate(self.meta)
                                     for e in [np.arange(first_ok, m["n"], stride)]])
        self.window_labels = np.stack([self.labels[a][e] for a, e in self.index])
        self.has_positive = (self.window_labels == 1).any(1)
        self.is_benign = np.zeros(len(self.index), bool)

    @property
    def values(self):
        return self._values


def specs_for(assets: pd.DataFrame, ids: list[str], split: str) -> list[AssetSpec]:
    out = []
    for aid in ids:
        row = assets[assets.asset_id == aid].iloc[0].to_dict()
        out.append(AssetSpec(key=f"{split}/{aid}", asset_id=aid, telemetry_dir=DATA / "telemetry" / f"asset_id={aid}",
                             info=row, events=pd.DataFrame(), benign=pd.DataFrame()))
    return out


def device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=list(SPLITS), required=True)
    ap.add_argument("--run", default="rp3-3h-r32-v1")
    ap.add_argument("--checkpoint", default="checkpoint_last_step11500")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    run = EXP / "runs" / a.run
    cfg = load_config(EXP / "configs" / f"{a.run.rsplit('-v', 1)[0]}.yaml")
    cfg["run"]["num_workers"] = 0
    cfg["run"]["precision"] = "fp32"
    cfg["predict"].update(RULES)
    dev = device()
    model = TimestralMultiLabel(cfg)
    st = torch.load(run / f"{a.checkpoint}.pt", map_location="cpu", weights_only=False)
    model.load_state_dict(st["model"])
    model.to(dev)
    print(json.dumps(dict(run=a.run, checkpoint=a.checkpoint, step=st["step"], device=str(dev), rules=RULES)), flush=True)

    assets = pd.read_csv(DATA / "assets.csv")
    specs = specs_for(assets, SPLITS[a.split], a.split)
    t = time.time()
    ds = AssetWindows(cfg, specs, STRIDE_S)
    print(f"{len(ds)} windows on {len(specs)} assets", flush=True)
    pred = predict_windows(model, ds, cfg, dev)
    print(f"predicted in {time.time() - t:.0f} s", flush=True)

    alerts = alerts_from_predictions(cfg, pred)
    alerts["recommended_action"] = alerts.fault_type.map(ACTIONS).fillna("Review the evidence channel and inspect the pump.")
    alerts["evidence"] = [f"{e}; class probability above 0.9 for 15 min (model rp3-3h-r32, 3 h window)"
                          for e in alerts.evidence]
    out = Path(a.out) if a.out else EXP / "analysis" / f"predictions_{a.split}_{a.run}_{a.checkpoint}.csv"
    alerts.to_csv(out, index=False)
    pred.to_parquet(out.with_suffix(".windows.parquet"), index=False)
    print(f"{len(alerts)} alerts -> {out}")
    print(alerts.groupby(["asset_id", "fault_type"]).size().to_string())

    if a.split == "validation":
        score = _scorer(cfg)
        r = score(alerts, pd.read_csv(DATA / "events_validation.csv"), assets[assets.asset_id.isin(SPLITS[a.split])],
                  pd.read_csv(DATA / "benign_windows_train_validation.csv").query("asset_id in @SPLITS['validation']"))
        print(json.dumps({k: v for k, v in r.items() if k != "per_event"}, default=str, indent=1))


if __name__ == "__main__":
    main()

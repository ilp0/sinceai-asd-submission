"""Build the replay files of the demo from the organizer data and the submitted model output.

Inputs (defaults point at the experiment repository next to this repository):
- organizer data `data/full/` (1-min features, asset table),
- the 10 s window probabilities of the submitted model on PUMP-08/09
  (rp3-3h-r32-v1, checkpoint_last_step11500; `optimize/predictions/rp3-3h-r32-v1/val-orig__<pump>.parquet`,
  made by `05_source_code/src/optimize/predict_val.py`).

The alerts are made here with the submitted alert rule: `fast_alerts` from `05_source_code/src/optimize/alerts.py`
with `RULE` and `STRIDE_S` from `05_source_code/src/optimize/predict_test_fine.py`. The script checks that the
result is equal to `05_source_code/src/optimize/results/submission-fine/predictions_validation.csv`.

Output: `site/data/<asset>.json` (signals, probabilities) and `site/data/alerts.json`.
The data are synthetic: "RETROFIT AI 2026 synthetic pump benchmark, Since AI Hackathon 2026" (CC BY 4.0).

Run:  .venv/bin/python build_data.py [--exp-repo PATH]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PUMPS = ["PUMP-08", "PUMP-09"]
CLASSES = [
    "BEARING_WEAR", "SUCTION_STRAINER_CLOGGING", "CAVITATION", "DISCHARGE_RESTRICTION",
    "MISALIGNMENT", "IMBALANCE", "IMPELLER_WEAR", "AIR_ENTRAINMENT", "SENSOR_DRIFT",
    "SENSOR_STUCK", "SENSOR_CALIBRATION_SHIFT", "SENSOR_NOISE_SPIKES", "COMMUNICATION_LOSS",
]
# key, label, unit
CHANNELS = [
    ("flow_m3_h", "Flow", "m³/h"),
    ("suction_pressure_kpa", "Suction pressure", "kPa"),
    ("discharge_pressure_kpa", "Discharge pressure", "kPa"),
    ("motor_speed_rpm", "Motor speed", "rpm"),
    ("motor_current_a", "Motor current", "A"),
    ("motor_power_kw", "Motor power", "kW"),
    ("vibration_rms_mm_s", "Vibration velocity", "mm/s"),
    ("vibration_accel_rms_g", "Vibration accel.", "g"),
    ("vibration_crest_factor", "Crest factor", ""),
    ("bearing_temp_c", "Bearing temp.", "°C"),
    ("motor_winding_temp_c", "Winding temp.", "°C"),
    ("fluid_temp_c", "Fluid temp.", "°C"),
    ("ambient_temp_c", "Ambient temp.", "°C"),
]
LABEL = {k: (l, u) for k, l, u in CHANNELS}
PUMP_TEXT = {
    "PUMP-08": {"name": "SW cooling pump No. 2", "short": "SW-2", "manual": "PUMP-08"},
    "PUMP-09": {"name": "Cooling-tower pump CW-2", "short": "CW-2", "manual": "PUMP-09"},
}


def r(v, nd=3):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), nd)


def build_pump(asset: str, org: Path, probs: pd.DataFrame, assets: pd.DataFrame) -> dict:
    a = assets.set_index("asset_id").loc[asset]
    t0 = pd.Timestamp(a.window_start_utc)
    t1 = pd.Timestamp(a.window_end_utc)
    minutes = pd.date_range(t0, t1, freq="1min", inclusive="left")
    avail = [c for c in a.channels_available.split("|") if c in LABEL]
    avail = [k for k, _, _ in CHANNELS if k in avail]

    f = pd.read_parquet(org / "features_1min.parquet", filters=[("asset_id", "==", asset)])
    f["t"] = pd.to_datetime(f.window_start_utc, utc=True)
    f = f.set_index("t").sort_index().reindex(minutes)
    series = {k: [r(v, 3) for v in f[f"{k}__mean"].ffill(limit=10)] for k in avail}
    running = [r(v, 2) for v in f.running_fraction.fillna(0)]
    modes = f.operating_mode.astype("string").fillna("NO_DATA")
    mode_names = sorted(modes.unique())
    mode = [mode_names.index(m) for m in modes]

    # model probabilities: 10 s windows, shown as the last window of each minute (no window in the first 24 h)
    p = probs[probs.asset == f"val-orig/{asset}"].copy()
    p["t"] = pd.to_datetime(p.time, utc=True).dt.floor("1min")
    p = p.drop_duplicates("t", keep="last").set_index("t").reindex(minutes)
    first = int(p[f"p_{CLASSES[0]}"].first_valid_index().value - t0.value) // 60_000_000_000
    prob = {c: [r(v, 3) for v in p[f"p_{c}"].iloc[first:].ffill()] for c in CLASSES}

    # baseline: median of the first 24 h while running
    base_mask = (np.arange(len(minutes)) < 1440) & (f.running_fraction.fillna(0).values >= 0.95)
    baseline = {k: r(f[f"{k}__mean"][base_mask].median(), 3) for k in avail}

    info = {
        "asset_id": asset, **PUMP_TEXT[asset],
        "site": a.site, "system": a.system, "profile": a.profile, "control": a.control,
        "tier": a.instrumentation_tier, "fluid": a.fluid,
        "rated": {
            "flow_m3_h": float(a.pump_rated_flow_m3_h), "head_m": float(a.pump_rated_head_m),
            "motor_kw": float(a.motor_rated_kw), "current_a": float(a.motor_rated_current_a),
            "rpm": float(a.motor_rated_rpm), "vibration_alarm_mm_s": float(a.vibration_alarm_mm_s),
            "vibration_trip_mm_s": float(a.vibration_trip_mm_s), "bearing": str(a.bearing_designation),
        },
    }
    data = {
        **info, "t0": t0.strftime("%Y-%m-%dT%H:%M:%SZ"), "minutes": len(minutes),
        "channels": [{"key": k, "label": LABEL[k][0], "unit": LABEL[k][1]} for k in avail],
        "series": series, "running": running, "modes": mode_names, "mode": mode,
        "prob_first": first, "prob": prob, "baseline": baseline,
    }
    return data, info, f, baseline, t0


def snapshot(f: pd.DataFrame, at: pd.Timestamp, baseline: dict, avail: list[str]) -> list[dict]:
    win = f.loc[at - pd.Timedelta("15min"): at]
    out = []
    for k in avail:
        now = r(win[f"{k}__mean"].mean(), 3)
        b = baseline.get(k)
        delta = None if now is None or not b else r(100 * (now - b) / abs(b), 1)
        out.append({"key": k, "label": LABEL[k][0], "unit": LABEL[k][1], "now": now, "baseline": b, "delta_pct": delta})
    return out


def main():
    import os
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-repo", type=Path, default=HERE.parent.parent / "SinceAI-BusinessTurku-ASD")
    args = ap.parse_args()
    exp = args.exp_repo
    pkg = exp / "raw/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026"
    org = pkg / "data/full"
    pred_dir = exp / "optimize/predictions/rp3-3h-r32-v1"

    # the submitted alert rule and its code
    src = HERE.parent / "05_source_code/src/optimize"
    os.environ.setdefault("RETROFIT_PKG", str(pkg))
    sys.path.insert(0, str(src))
    from alerts import fast_alerts
    from predict_test_fine import RULE, STRIDE_S

    assets = pd.read_csv(org / "assets.csv")
    probs = pd.concat([pd.read_parquet(pred_dir / f"val-orig__{a}.parquet") for a in PUMPS], ignore_index=True)
    probs["asset"] = probs["asset"].astype(str)
    probs = probs.sort_values(["asset", "time"], kind="stable").reset_index(drop=True)
    sub = fast_alerts(probs, RULE["threshold"], RULE["persistence_min"] * 60 // STRIDE_S,
                      RULE["cooldown_minutes"], RULE["global_gap_minutes"])
    ref = pd.read_csv(src / "results/submission-fine/predictions_validation.csv")
    key = ["asset_id", "alert_time_utc", "fault_type", "confidence"]
    same = sub[key].reset_index(drop=True).equals(ref[key].reset_index(drop=True))
    print(f"alerts from the submitted rule: {len(sub)}, equal to the submitted validation file: {same}")
    if not same:
        raise SystemExit("The alerts differ from the submitted validation file.")
    sub["t"] = pd.to_datetime(sub.alert_time_utc, utc=True)
    sub["evidence_signal"] = sub.evidence.str.extract(r"strongest row (\S+)")[0]

    out_dir = HERE / "site" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    alerts = []
    for asset in PUMPS:
        data, info, f, baseline, t0 = build_pump(asset, org, probs, assets)
        (out_dir / f"{asset}.json").write_text(json.dumps(data, separators=(",", ":")))
        avail = [c["key"] for c in data["channels"]]
        for i, al in enumerate(sub[sub.asset_id == asset].sort_values("t").itertuples(), 1):
            minute = int((al.t - t0).total_seconds() // 60)
            at = al.t.floor("1min")
            others = []
            pi = minute - data["prob_first"]
            if 0 <= pi < len(data["prob"][CLASSES[0]]):
                others = sorted(((c, data["prob"][c][pi]) for c in CLASSES if c != al.fault_type and data["prob"][c][pi]),
                                key=lambda x: -x[1])[:3]
            alerts.append({
                "id": f"{asset}-A{i:02d}", "asset_id": asset, "time": al.t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "minute": minute, "event_class": al.event_class, "fault_type": al.fault_type,
                "confidence": round(float(al.confidence), 4),
                "evidence_signal": None if pd.isna(al.evidence_signal) else str(al.evidence_signal),
                "rule": "class probability >= 0.9 for 15 min, 12 h cooldown per fault type",
                "other_probabilities": [{"fault_type": c, "p": p} for c, p in others],
                "values": snapshot(f, at, baseline, avail),
            })
        print(f"{asset}: {data['minutes']} min, channels {len(avail)}, prob from minute {data['prob_first']}")
    alerts.sort(key=lambda a: (a["minute"], a["asset_id"]))
    (out_dir / "alerts.json").write_text(json.dumps(alerts, indent=1))
    print(f"alerts: {len(alerts)}")


if __name__ == "__main__":
    main()

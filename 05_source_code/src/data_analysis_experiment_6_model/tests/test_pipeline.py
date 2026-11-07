"""Fast checks. They need the smoke cache: `python run.py prepare --config configs/smoke.yaml`.
No test runs an optimizer step."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))

from mlhead.config import load_config  # noqa: E402
from mlhead.data import AssetSpec, WindowDataset, build_labels, discover_assets  # noqa: E402
from mlhead.metrics import auroc, average_precision  # noqa: E402

SMOKE = EXP / "configs/smoke.yaml"


def cfg(*overrides):
    return load_config(SMOKE, list(overrides))


def test_inherit_and_override():
    c = cfg("train.learning_rate=0.001", "input.minutes=30")
    assert c["run"]["name"] == "smoke" and c["backbone"]["mode"] == "lora"   # inherited
    assert c["train"]["learning_rate"] == 0.001 and c["input"]["minutes"] == 30


def test_locked_assets_are_never_selected():
    c = cfg('data.val_assets=["public/PUMP-1*"]')
    with pytest.raises(ValueError, match="locked"):
        discover_assets(c)
    keys = [s.key for r in discover_assets(cfg()).values() for s in r]
    assert not any(k.endswith(("PUMP-10", "PUMP-11", "PUMP-12")) for k in keys)


def _spec(events):
    info = dict(window_start_utc="2025-01-01T00:00:00Z", window_end_utc="2025-01-01T06:00:00Z")
    return AssetSpec("x/A", "A", Path("."), info, pd.DataFrame(events), pd.DataFrame())


def test_labels_independent_and_masked():
    c = cfg("input.sample_period_s=60")
    ev = [dict(fault_type="BEARING_WEAR", onset_utc="2025-01-01T01:00:00Z", detectable_utc="2025-01-01T02:00:00Z",
               end_utc=None, observable=True),
          dict(fault_type="SENSOR_DRIFT", onset_utc="2025-01-01T02:30:00Z", detectable_utc="2025-01-01T03:00:00Z",
               end_utc="2025-01-01T04:00:00Z", observable=True),
          dict(fault_type="CAVITATION", onset_utc="2025-01-01T00:10:00Z", detectable_utc=None,
               end_utc="2025-01-01T00:20:00Z", observable=False)]
    y, _ = build_labels(_spec(ev), c)
    k = {n: i for i, n in enumerate(c["labels"]["classes"])}
    t = lambda h, m=0: h * 60 + m - 1                      # cell whose issue time is hh:mm
    assert y[t(1, 30), k["BEARING_WEAR"]] == -1            # onset .. detectable: ignored
    assert y[t(2), k["BEARING_WEAR"]] == 1
    assert y[t(5, 59), k["BEARING_WEAR"]] == 1             # open-ended: to the window end
    assert y[t(3, 30), k["SENSOR_DRIFT"]] == 1 and y[t(3, 30), k["BEARING_WEAR"]] == 1   # both at once
    assert y[t(4), k["SENSOR_DRIFT"]] == -1                # 30 min after a non-repair end: ignored
    assert y[t(4, 30), k["SENSOR_DRIFT"]] == 0
    assert y[t(0, 15), k["CAVITATION"]] == -1              # unobservable: ignored


def test_lead_minutes_shifts_start():
    c = cfg("input.sample_period_s=60", "labels.lead_minutes=30")
    ev = [dict(fault_type="IMBALANCE", onset_utc="2025-01-01T01:00:00Z", detectable_utc="2025-01-01T01:00:00Z",
               end_utc="2025-01-01T02:00:00Z", observable=True)]
    y, _ = build_labels(_spec(ev), c)
    k = c["labels"]["classes"].index("IMBALANCE")
    assert y[29, k] == 1                                    # issue time 00:30 = detectable - 30 min
    assert y[:29, k].max() == 0


def test_window_is_causal_and_left_padded():
    c = cfg()
    ds = WindowDataset(c, "train", 600)
    j = len(ds) // 2
    a, e = ds.index[j]
    item = ds[j]
    L, P = ds.length, ds.padded
    raw = np.asarray(ds.values[a][e - L + 1: e + 1]).T
    np.testing.assert_array_equal(item["observed"][:, P - L:], ~np.isnan(raw))
    assert not item["observed"][:, : P - L].any()
    # Changing data after the issue cell does not change the window.
    vals = np.array(ds.values[a])
    vals[e + 1:] = 1e6
    ds.values[a] = vals
    np.testing.assert_array_equal(ds[j]["values"], item["values"])
    assert ds.issue_time(j) == pd.Timestamp(ds.meta[a]["t0"]) + pd.Timedelta(seconds=int(e) + 1)


def test_metrics():
    y = np.array([0, 0, 1, 1])
    assert auroc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auroc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert average_precision(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0


def test_untrained_predict_and_alert_export(tmp_path):
    import torch
    from mlhead.metrics import evaluate_predictions
    from mlhead.train import build, export_alerts, predict_windows
    c = cfg()
    torch.manual_seed(0)
    model, dev = build(c)
    ds = WindowDataset(c, "val", 1800)
    pred = predict_windows(model, ds, c, dev, max_windows=24)
    assert 12 <= len(pred) <= 24 and pred.filter(like="p_").stack().between(0, 1).all()
    m = evaluate_predictions(pred, c["labels"]["classes"], 0.5, 1800)
    assert "macro_auroc" in m
    f = tmp_path / "pred.parquet"
    pred.to_parquet(f)
    c["predict"]["threshold"] = 0.0
    alerts = export_alerts(c, f, tmp_path / "alerts.csv")
    assert set(alerts.event_class) <= {"MACHINE", "SENSOR"}
    t = pd.to_datetime(alerts.alert_time_utc)
    assert (t.diff().dropna() >= pd.Timedelta(minutes=5)).all()   # no mixed-type bursts


def test_dataset_loads_only_selected_assets():
    c = cfg('data.train_assets=["public/PUMP-01", "public/PUMP-08"]', 'data.val_assets=[]')
    with pytest.raises(FileNotFoundError):     # PUMP-08 is cached only under "val"
        WindowDataset(c, "train", 600)
    ds = WindowDataset(cfg(), "train", 600)
    assert [m["key"] for m in ds.meta] == ["public/PUMP-01"]


def test_benchmark_scores_with_organizer_scorer():
    import torch
    from mlhead.benchmark import Benchmark
    from mlhead.train import build, predict_windows
    c = cfg("benchmark.stride_s=1800", "data.eval_stride_s=1800", "benchmark.thresholds=[0.5, 0.7, 0.9, 0.99]")
    torch.manual_seed(0)
    model, dev = build(c)
    b = Benchmark(c)
    assert [m["key"] for m in b.ds.meta] == ["public/PUMP-08"] and list(b.groups) == ["all"]
    r = b.run(model, dev)
    s = r["scalars"]
    for thr in ("0.5", "0.7", "0.9", "0.99"):
        for k in ("composite_score", "event_f1", "timeliness", "fault_type_recall", "class_recall", "alert_burden"):
            assert f"all/{k}@{thr}" in s
        assert 0 <= s[f"all/composite_score@{thr}"] <= 100
    assert s["all/events_scored@0.9"] == 4      # PUMP-08 has 4 observable validation events
    assert s["all/composite_max"] == max(s[f"all/composite_score@{t}"] for t in ("0.5", "0.7", "0.9", "0.99"))
    # Reuse of a validation prediction pass gives the same score as a separate benchmark pass.
    pred = predict_windows(model, WindowDataset(c, "val", 1800), c, dev)
    assert b.run(model, dev, pred)["scalars"] == s


RUN_CONFIGS = sorted((EXP / "configs").glob("rp-*.yaml"))


def test_runpod_configs():
    from mlhead.config import data_fingerprint
    assert len(RUN_CONFIGS) == 6
    cs = [load_config(f) for f in RUN_CONFIGS]
    assert len({c["run"]["name"] for c in cs}) == 6
    assert {(c["input"]["minutes"], c["backbone"]["lora"]["rank"], c["backbone"]["lora"]["alpha"]) for c in cs} == {
        (m, r, 2 * r) for m in (180, 360, 720) for r in (32, 64)}
    for c in cs:
        assert c["input"]["minutes"] * 60 // c["input"]["sample_period_s"] == 1080
        assert c["run"]["device"] == "cuda"
        assert c["train"]["eval_every"] == c["train"]["checkpoint_every"] == 250
        assert c["benchmark"]["thresholds"] == [0.5, 0.7, 0.9, 0.99]
    # Runs with the same context share one cache.
    assert len({data_fingerprint(c) for c in cs}) == 3


@pytest.mark.skipif(not (EXP / "data/manifest.json").exists(), reason="data/ not built (make_data.py)")
def test_experiment6_data_roles_and_lock():
    c = load_config(RUN_CONFIGS[0])
    specs = discover_assets(c)
    keys = [s.key for r in specs.values() for s in r]
    assert len(specs["train"]) == 27 and len(specs["val"]) == 7
    assert not any(k.endswith(("PUMP-10", "PUMP-11", "PUMP-12")) or "test" in k.split("/")[0] for k in keys)
    assert not {s.asset_id for s in specs["train"]} & {s.asset_id for s in specs["val"]}
    assert sum(len(s.events) for s in specs["val"]) == 26


def test_round2_full_data_configs():
    from mlhead.config import data_fingerprint
    cs = [load_config(f) for f in sorted((EXP / "configs").glob("rp2-*.yaml"))]
    assert len(cs) == 3 and len({c["run"]["name"] for c in cs}) == 3
    for c in cs:
        assert c["input"]["minutes"] * 60 // c["input"]["sample_period_s"] == 1080
        assert c["train"]["eval_every"] == 250 and c["benchmark"]["thresholds"] == [0.5, 0.7, 0.9, 0.99]
        assert c["data"]["val_assets"] == ["val-orig/*", "val-new-*/*"]
        assert not any("test" in s.get("root", s.get("root_glob", "")) for s in c["data"]["sources"])
    # Round 2 caches differ from round 1 (other sources).
    assert data_fingerprint(cs[0]) != data_fingerprint(load_config(EXP / "configs/rp-3h-r32.yaml"))


def test_round3_double_data_configs():
    """Round 3: round-2 data + experiment-4 train2; no re-simulated copies of the validation pumps PUMP-08/09."""
    from mlhead.data import discover_assets
    cs = [load_config(f) for f in sorted((EXP / "configs").glob("rp3-*.yaml"))]
    assert len(cs) == 3 and len({c["run"]["name"] for c in cs}) == 3
    for c in cs:
        assert c["input"]["minutes"] * 60 // c["input"]["sample_period_s"] == 1080
        assert c["data"]["val_assets"] == ["val-orig/*", "val-new-*/*"]
        assert not any("test" in s.get("root", s.get("root_glob", "")) for s in c["data"]["sources"])
    if not (EXP / "../data_analysis_experiment_4_generated/build/train2").exists():
        return
    a = discover_assets(cs[0])
    ids = [s.asset_id for s in a["train"]]
    assert not [i for i in ids if i.endswith(("-P08", "-P09")) or i.startswith("PUMP-0") and i[-1] in "89"]
    assert sum(i.startswith("GEN-train2-") or "train2" in s.key for i, s in zip(ids, a["train"])) >= 140
    assert not {s.asset_id for s in a["val"]} & set(ids)

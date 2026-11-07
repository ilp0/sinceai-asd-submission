"""Experiment 6: build the training / validation data layout (organizer folder format, as mlhead/data.py reads it).

  data/training/original/    public PUMP-01..07 (organizer data/full, filtered to these assets)
  data/training/new/<set>-<seed>/   20 experiment-4 generated pumps from the set "train" (10 own fleet files, 10 stress
                             tier), chosen for fault-type coverage; item folders filtered to the chosen pumps
  data/validation/original/  public PUMP-08, PUMP-09
  data/validation/new/<seed>/       5 new generated pumps (seed 45001, used by no other set), never in training

Files are APFS clones (`cp -c`), so copies use no extra disk until changed. PUMP-10..12 are never copied.
Run: <venv python> make_data.py   (idempotent: each target folder is rebuilt)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
MAIN = Path("/Users/ilpo/git/SinceAI-BusinessTurku-ASD")       # main checkout (experiment 4 lives there)
PKG = MAIN / "raw/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026"
FULL = PKG / "data/full"
EXP4 = MAIN / "data_analysis_experiment_4_generated"
PY = MAIN / "data_analysis_expriment_1/.venv/bin/python"
DATA = HERE / "data"
LOCKED = {"PUMP-10", "PUMP-11", "PUMP-12"}
TRAIN_ORIG = [f"PUMP-0{i}" for i in range(1, 8)]
VAL_ORIG = ["PUMP-08", "PUMP-09"]
NEW_TRAIN_SET = "train"
N_PER_SOURCE = {"own": 10, "stress": 10}     # 20 new training pumps (user decision, 7 Nov 2026)
VAL_NEW_SEED, VAL_NEW_N = 45001, 5
ITEM_PARTS = ["public", "private", "summary.json"]          # not forecasts/, series etc.


def write_manifest(d: Path, src_manifest: Path, keep: list[str]):
    """Organizer manifest format (retrofit_sim.dataset.manifest) for the files now in d and the kept pumps only."""
    import hashlib
    src = json.loads(src_manifest.read_text())
    files = []
    for f in sorted(d.rglob("*")):
        if f.is_file() and f.name != "manifest.json":
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            files.append({"path": str(f.relative_to(d)), "bytes": f.stat().st_size, "sha256": h})
    m = {k: src[k] for k in ("dataset", "synthetic", "tier", "generator_version")}
    m.update(file_count=len(files), total_bytes=sum(f["bytes"] for f in files),
             telemetry_rows={a: n for a, n in src.get("telemetry_rows", {}).items() if a in keep},
             filtered_by="data_analysis_experiment_6_model/make_data.py (subset of the source manifest)",
             files=files)
    (d / "manifest.json").write_text(json.dumps(m, indent=2))


def clone(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-cR", str(src), str(dst)], check=True)


def reset(d: Path):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)


def original_subset(dst: Path, assets: list[str], split: str):
    assert not LOCKED & set(assets)
    reset(dst)
    for a in assets:
        clone(FULL / "telemetry" / f"asset_id={a}", dst / "telemetry" / f"asset_id={a}")
    for f in sorted(FULL.glob("*.csv")):
        if f.name.startswith("events_") and f.name != f"events_{split}.csv":
            continue
        df = pd.read_csv(f)
        if "asset_id" in df:
            df = df[df.asset_id.isin(assets)]
        df.to_csv(dst / f.name, index=False, lineterminator="\n")
    for f in ("features_1min.parquet", "vibration_snapshots.parquet"):
        t = pq.read_table(FULL / f).to_pandas()
        t[t.asset_id.isin(assets)].to_parquet(dst / f, index=False)
    for f in FULL.glob("*.md"):
        shutil.copy2(f, dst / f.name)
    shutil.copy2(FULL / "schema.json", dst / "schema.json")
    write_manifest(dst, FULL / "manifest.json", assets)
    return {"assets": assets, "events": int(len(pd.read_csv(dst / f"events_{split}.csv")))}


def _events(root: Path) -> pd.DataFrame:
    for n in ("private/events_stress_all.csv", "public/events_train.csv"):
        if (root / n).exists():
            return pd.read_csv(root / n)
    return pd.DataFrame(columns=["asset_id", "fault_type"])


def choose_pumps(items: list[dict]) -> dict[str, list[str]]:
    """Greedy, deterministic: per source, take the pump whose fault types are rarest among the pumps chosen so far."""
    chosen, counts = {}, {}
    for source, n in N_PER_SOURCE.items():
        pool = []
        for it in items:
            if it["source"] != source:
                continue
            ev = _events(EXP4 / it["output"])
            for aid in pd.read_csv(EXP4 / it["output"] / "public/assets.csv").asset_id:
                pool.append((it["key"], aid, list(ev[ev.asset_id == aid].fault_type)))
        for _ in range(n):
            gain = lambda c: sum(1.0 / (1 + counts.get(t, 0)) for t in set(c[2]))
            best = max(pool, key=lambda c: (gain(c), len(c[2]), c[0], c[1]))
            pool.remove(best)
            chosen.setdefault(best[0], []).append(best[1])
            for t in best[2]:
                counts[t] = counts.get(t, 0) + 1
    return chosen


def _filter_item(dst: Path, keep: list[str]):
    for d in (dst / "public/telemetry").iterdir():
        if d.name.split("=", 1)[1] not in keep:
            shutil.rmtree(d)
    for f in list((dst / "public").glob("*.csv")) + list((dst / "private").glob("*.csv")):
        df = pd.read_csv(f)
        if "asset_id" in df:
            f.unlink()
            df[df.asset_id.isin(keep)].to_csv(f, index=False, lineterminator="\n")
    for f in list((dst / "public").glob("*.parquet")) + list((dst / "private").glob("*.parquet")):
        t = pd.read_parquet(f)
        f.unlink()
        t[t.asset_id.isin(keep)].to_parquet(f, index=False)
    for part in ("public", "private"):
        write_manifest(dst / part, dst / part / "manifest.json", keep)


def new_items(dst_root: Path):
    reset(dst_root)
    doc = json.loads((EXP4 / "sets.json").read_text())
    items = [it for it in doc["items"] if it["set"] == NEW_TRAIN_SET]
    assert all(it["set"] != "test" for it in items)
    chosen = choose_pumps(items)
    out = []
    for it in items:
        if it["key"] not in chosen:
            continue
        src = EXP4 / it["output"]
        dst = dst_root / f"{it['set']}-{it['seed']}"
        for p in ITEM_PARTS:
            clone(src / p, dst / p)
        _filter_item(dst, chosen[it["key"]])
        ev = _events(dst)
        out.append({"folder": dst.name, "set": it["set"], "source": it["source"], "seed": it["seed"],
                    "pumps": chosen[it["key"]], "events": int(len(ev)),
                    "by_type": ev.fault_type.value_counts().to_dict()})
    return out


def validation_new(dst_root: Path):
    reset(dst_root)
    fleet = dst_root / f"fleet_{VAL_NEW_SEED}.yaml"
    out = dst_root / str(VAL_NEW_SEED)
    subprocess.run([str(PY), str(EXP4 / "fleet_sampler.py"), "--set", "val6", "--seed", str(VAL_NEW_SEED),
                    "--n", str(VAL_NEW_N), "--out", str(fleet)], check=True, cwd=EXP4)
    r = subprocess.run([str(PY), str(EXP4 / "generate_set.py"), "--fleet-config", str(fleet), "--seed", str(VAL_NEW_SEED),
                        "--output", str(out)], check=True, cwd=EXP4, capture_output=True, text=True)
    s = json.loads(r.stdout.strip().splitlines()[-1])
    if s["plan_problems"]:
        raise RuntimeError(s["plan_problems"])
    return {"folder": str(VAL_NEW_SEED), "seed": VAL_NEW_SEED, "pumps": s["n_assets"], "assets": s["assets"],
            "events": s["n_events"], "by_type": s["by_type"]}


def main():
    used = {it["seed"] for it in json.loads((EXP4 / "sets.json").read_text())["items"]}
    assert VAL_NEW_SEED not in used
    m = {"training": {"original": original_subset(DATA / "training/original", TRAIN_ORIG, "train"),
                      "new": new_items(DATA / "training/new")},
         "validation": {"original": original_subset(DATA / "validation/original", VAL_ORIG, "validation"),
                        "new": validation_new(DATA / "validation/new")},
         "excluded": ["PUMP-10..12 (hidden test)", "experiment-4 set 'test' (locked)"]}
    (DATA / "manifest.json").write_text(json.dumps(m, indent=2))
    tn = m["training"]["new"]
    print(json.dumps({"training_original": m["training"]["original"],
                      "training_new": {"items": len(tn), "pumps": sum(len(x["pumps"]) for x in tn), "events": sum(x["events"] for x in tn),
                                       "by_type": pd.concat([pd.Series(x["by_type"], dtype=int) for x in tn]).groupby(level=0).sum().to_dict()},
                      "validation_original": m["validation"]["original"],
                      "validation_new": m["validation"]["new"]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())

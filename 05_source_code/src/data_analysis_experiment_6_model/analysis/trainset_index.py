"""Index of the round-3 data (training + validation pumps) for the data explorer in ../visualizer.

    python analysis/trainset_index.py [--config configs/rp3-6h-r32.yaml]

Writes analysis/trainset/{assets,events,benign}.parquet: one row per pump with its source, split and data folder,
and the labels exactly as the training code reads them (mlhead.data.discover_assets). Locked pumps
(PUMP-10..12, experiment-4 test) are never listed: discover_assets skips them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
from mlhead.config import load_config  # noqa: E402
from mlhead.data import discover_assets  # noqa: E402

OUT = EXP / "analysis" / "trainset"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/rp3-6h-r32.yaml")
    a = ap.parse_args()
    cfg = load_config(EXP / a.config)
    specs = discover_assets(cfg, ("train", "val"))
    rows, events, benign = [], [], []
    for role, split in (("train", "train"), ("val", "validation")):
        for s in specs[role]:
            root = Path(s.telemetry_dir).parent.parent          # <root>/telemetry/asset_id=X
            info = dict(s.info)
            # STRESS-NN repeats across generated seeds: the explorer uses the unique key as asset_id and keeps
            # the id inside the files as file_asset_id.
            info.update(split=split, asset_id=s.key, file_asset_id=s.asset_id, source=s.key.split("/")[0],
                        data_root=str(root), telemetry_dir=str(s.telemetry_dir))
            rows.append(info)
            for df, out in ((s.events, events), (s.benign, benign)):
                if len(df):
                    out.append(df.assign(asset_id=s.key, file_asset_id=s.asset_id))
    assets = pd.DataFrame(rows)
    dup = assets.asset_id[assets.asset_id.duplicated()]
    if len(dup):
        raise ValueError(f"pump keys are not unique: {sorted(set(dup))[:5]}")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in (("assets", assets), ("events", pd.concat(events, ignore_index=True)),
                     ("benign", pd.concat(benign, ignore_index=True))):
        df = df.copy()
        for c in df.columns:
            if df[c].dtype == object and not c.endswith("_utc"):
                df[c] = df[c].astype(str).where(df[c].notna(), None)
        df.to_parquet(OUT / f"{name}.parquet", index=False)
    ev = pd.concat(events, ignore_index=True)
    src = assets.source.str.replace(r"-\d+$", "", regex=True)
    print(assets.groupby(["split", src]).size().to_string())
    print(f"events {len(ev)} (observable {ev.observable.astype(str).str.lower().isin(['true', '1']).sum()}) -> {OUT}")


if __name__ == "__main__":
    main()

"""Write the causal B1 baseline into TensorBoard as a reference run (runs/B1-causal), with the same tags as
the model runs, so that B1 shows as a flat line in every bench_* chart.

    python analysis/b1_tensorboard.py [--max-step 16000] [--every 250]

B1 has no probability threshold: the same B1 value is written for every model threshold tag (@0.5 ... @0.99),
and composite_max = B1 composite. B1 alerts: analysis/hybrid.py b1_alerts (recomputed from each validation
pump's features, identical to experiment 1 on PUMP-08/09; k=6 chosen on training pumps).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(EXP / "analysis"))
from hybrid import CONFIG, b1_alerts  # noqa: E402
from mlhead.benchmark import SCALARS  # noqa: E402
from mlhead.config import load_config  # noqa: E402
from postprocess import Pumps  # noqa: E402

RUN = EXP / "runs" / "B1-causal"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-step", type=int, default=16000)
    ap.add_argument("--every", type=int, default=250)
    a = ap.parse_args()
    cfg = load_config(CONFIG)
    pumps = Pumps(cfg)
    b1 = b1_alerts(pumps)
    keys = sorted(pumps.specs)
    groups = {"all": keys}
    for k in keys:
        groups.setdefault(k.split("/")[0], []).append(k)
    thresholds = cfg["benchmark"]["thresholds"]
    scalars = {}
    for name, g in groups.items():
        r = pumps.score(b1, g)
        for k in SCALARS:
            v = r.get(k)
            if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
                for thr in thresholds:
                    scalars[f"bench_{name}/{k}@{thr:g}"] = float(v)
        scalars[f"bench_{name}/composite_max"] = float(r["composite_score"])
    from torch.utils.tensorboard import SummaryWriter
    if (RUN / "tensorboard").exists():
        shutil.rmtree(RUN / "tensorboard")
    RUN.mkdir(parents=True, exist_ok=True)
    tb = SummaryWriter(str(RUN / "tensorboard"))
    for step in range(a.every, a.max_step + 1, a.every):
        for k, v in scalars.items():
            tb.add_scalar(k, v, step)
    tb.close()
    (RUN / "b1_scalars.json").write_text(json.dumps(scalars, indent=1))
    for name in groups:
        print(f"B1 {name:16} composite {scalars[f'bench_{name}/composite_max']:.2f}")
    print(f"-> {RUN}/tensorboard ({len(scalars)} tags, steps {a.every}..{a.max_step})")


if __name__ == "__main__":
    main()

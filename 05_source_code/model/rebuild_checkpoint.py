"""Rebuild the submitted checkpoint from the public Timestral-28M weights and the trained weights in this folder.

    python rebuild_checkpoint.py            # -> ../src/data_analysis_experiment_6_model/runs/rp3-3h-r32-v1/checkpoint_last_step11500.pt

The trained file holds only the trained parameters (LoRA rank 32 / alpha 64, the forecast_query token and the
multi-label head; 1 419 213 values). All other weights are the unchanged Timestral-28M weights. The script builds the
model from `configs/rp3-3h-r32.yaml` (which loads the base weights), loads the trained file on top, and writes a
checkpoint in the format that `analysis/predict_test.py` and `optimize/predict_test_fine.py` read
(`{"model": state_dict, "step": 11500}`; no optimizer state).

Needs: Python 3.12, torch, safetensors, PyYAML, huggingface_hub (imported by the timestral package), and next to
`src/data_analysis_experiment_6_model/` the folder `src/data_analysis_experiment_2_lora/` with
  base_model/  config.json + model.safetensors of mistralai/Timestral-28M (revision 49b26409ac87b5935539a5d8ffe7f397b720db47)
  vendor/      the `timestral` package (github.com/mistralai/timestral) and `timestral_ft` (Timestral-ft LoRA code)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "rp3-3h-r32-v1_step11500_trained.safetensors"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exp", default=str(HERE.parent / "src" / "data_analysis_experiment_6_model"),
                    help="experiment-6 folder (contains mlhead/ and configs/)")
    ap.add_argument("--weights", default=str(WEIGHTS))
    ap.add_argument("--out", default=None, help="default: <exp>/runs/rp3-3h-r32-v1/checkpoint_last_step11500.pt")
    a = ap.parse_args()

    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file

    exp = Path(a.exp).resolve()
    sys.path.insert(0, str(exp))
    from mlhead.config import load_config, resolve
    from mlhead.model import TimestralMultiLabel

    with safe_open(a.weights, framework="pt") as f:
        meta = f.metadata()
    cfg = load_config(exp / meta["config"])
    base = resolve(cfg["backbone"]["path"]) / "model.safetensors"
    if not base.exists():
        raise SystemExit(f"base weights not found: {base} (see the docstring)")
    sha = hashlib.sha256(base.read_bytes()).hexdigest()
    if sha != meta["base_model_sha256"]:
        print(f"warning: base weights SHA-256 {sha} differs from the training base {meta['base_model_sha256']}")

    model = TimestralMultiLabel(cfg)
    trained = load_file(a.weights)
    trainable = {n for n, p in model.named_parameters() if p.requires_grad}
    if set(trained) != trainable:
        raise SystemExit(f"trained keys do not match the trainable parameters: "
                         f"missing {sorted(trainable - set(trained))[:5]}, unexpected {sorted(set(trained) - trainable)[:5]}")
    result = model.load_state_dict(trained, strict=False)
    if result.unexpected_keys:
        raise SystemExit(f"unexpected keys: {result.unexpected_keys[:5]}")

    out = Path(a.out) if a.out else exp / "runs" / meta["run"] / f"{meta['checkpoint']}.pt"
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(dict(model=model.state_dict(), step=int(meta["step"]),
                    rebuilt_from=dict(trained=Path(a.weights).name, base_sha256=sha)), out)
    print(json.dumps(dict(out=str(out), step=int(meta["step"]), trained_parameters=sum(v.numel() for v in trained.values()),
                          total_parameters=sum(p.numel() for p in model.parameters()), base_sha256_ok=sha == meta["base_model_sha256"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

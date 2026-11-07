"""Experiment 5 command line.

    python run.py prepare  --config configs/base.yaml          # build per-asset caches (CPU)
    python run.py describe --config configs/base.yaml          # windows, labels, parameter counts
    python run.py smoke    --config configs/smoke.yaml         # one forward/backward pass, no optimizer step
    python run.py train    --config configs/base.yaml [--stop-after-steps N]   # resumable
    python run.py evaluate --config configs/base.yaml [--checkpoint best|checkpoint]
    python run.py alerts   --config configs/base.yaml          # submission-format CSV from val predictions
    python run.py benchmark --config configs/base.yaml [--checkpoint best]  # BENCHMARK_RULES score -> TensorBoard

Every command accepts repeated `--set key.path=value` overrides.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mlhead.config import load_config  # noqa: E402


def describe(cfg: dict) -> None:
    import numpy as np
    from mlhead.data import WindowDataset
    from mlhead.train import build
    classes = cfg["labels"]["classes"]
    for role, stride in (("train", cfg["data"]["train_stride_s"]), ("val", cfg["data"]["eval_stride_s"])):
        ds = WindowDataset(cfg, role, stride)
        y = ds.window_labels
        print(json.dumps(dict(role=role, assets=len(ds.meta), windows=len(ds), input_cells=ds.length,
                              padded_cells=ds.padded, patches=ds.padded // 32,
                              rows_per_window=[len(m["rows"]) for m in ds.meta],
                              windows_with_positive=int(ds.has_positive.sum()), benign_windows=int(ds.is_benign.sum()),
                              positive_windows={c: int((y[:, k] == 1).sum()) for k, c in enumerate(classes)},
                              ignored_windows={c: int((y[:, k] == -1).sum()) for k, c in enumerate(classes)})))
    cfg["run"]["device"] = "cpu"
    model, _ = build(cfg)
    print(json.dumps(dict(parameters=model.count_parameters(), mode=cfg["backbone"]["mode"])))
    print(model.head)


def smoke(cfg: dict) -> None:
    """Gradient-flow check: one batch, forward and backward, no optimizer step (no training)."""
    import torch
    from mlhead.data import StepBatchSampler, WindowDataset, collate
    from mlhead.model import masked_loss
    from mlhead.train import build, to_device
    model, dev = build(cfg)
    ds = WindowDataset(cfg, "train")
    sampler = StepBatchSampler(ds, cfg["train"]["batch_size"], cfg["run"]["seed"], 0, 1, 0.5, 0.0)
    batch = to_device(collate([ds[i] for i in sampler.batch(0)]), dev)
    before = {n: p.detach().clone() for n, p in model.named_parameters()}
    logits, attn = model(batch)
    loss = masked_loss(logits, batch["labels"], batch["label_mask"], cfg["loss"], None)
    loss.backward()
    grads = {n: p.grad for n, p in model.named_parameters() if p.requires_grad}
    assert torch.isfinite(loss), "loss is not finite"
    assert all(g is None or torch.isfinite(g).all() for g in grads.values()), "non-finite gradient"
    groups = {"head": "head.", "lora": "lora_", "query_token": "forecast_query"}
    flow = {k: any(s in n and g is not None and g.abs().sum() > 0 for n, g in grads.items()) for k, s in groups.items()}
    frozen_ok = all(p.grad is None for n, p in model.named_parameters() if not p.requires_grad)
    unchanged = all(torch.equal(before[n], p) for n, p in model.named_parameters())
    print(json.dumps(dict(loss=float(loss.detach()), logits_shape=list(logits.shape), rows=int(batch["values"].shape[0]),
                          padded_cells=int(batch["values"].shape[1]), attention_shape=None if attn is None else list(attn.shape),
                          gradient_flow=flow, frozen_without_grad=frozen_ok, weights_unchanged=unchanged,
                          parameters=model.count_parameters())))


def benchmark_checkpoint(cfg: dict, which: str) -> None:
    """Score one saved checkpoint with the organizer scorer; log under bench/ at the checkpoint step."""
    from mlhead.benchmark import Benchmark
    from mlhead.train import load_trained, log_scalars, run_dir, tensorboard_writer, write_json
    model, dev, step = load_trained(cfg, which)
    b = Benchmark(cfg).run(model, dev)
    out = run_dir(cfg)
    b["predictions"].to_parquet(out / f"benchmark_predictions_step{step}.parquet", index=False)
    for src, d in b["details"].items():
        write_json(out / f"benchmark_{src}_step{step}.json", dict(result=d["result"], per_event=d["per_event"]))
        d["alerts"].to_csv(out / f"benchmark_alerts_{src}_step{step}.csv", index=False)
    tb = tensorboard_writer(out, [])
    if tb:
        log_scalars(tb, dict(step=step, **{f"bench_{k}": v for k, v in b["scalars"].items()}))
        tb.close()
    print(json.dumps(dict(step=step, **{k: round(v, 4) for k, v in b["scalars"].items() if "composite" in k})))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["prepare", "describe", "smoke", "train", "evaluate", "alerts", "benchmark"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--set", action="append", default=[], dest="overrides")
    ap.add_argument("--stop-after-steps", type=int)
    ap.add_argument("--checkpoint", default="best", choices=["best", "checkpoint"])
    a = ap.parse_args()
    cfg = load_config(a.config, a.overrides)
    if a.action == "prepare":
        from mlhead.data import prepare
        print(prepare(cfg))
    elif a.action == "describe":
        describe(cfg)
    elif a.action == "smoke":
        smoke(cfg)
    elif a.action == "train":
        from mlhead.train import train
        train(cfg, a.stop_after_steps)
    elif a.action == "evaluate":
        from mlhead.train import evaluate
        evaluate(cfg, a.checkpoint)
    elif a.action == "benchmark":
        benchmark_checkpoint(cfg, a.checkpoint)
    else:
        from mlhead.train import export_alerts, run_dir
        d = run_dir(cfg)
        res = export_alerts(cfg, d / f"predictions_val_{a.checkpoint}.parquet", d / f"alerts_val_{a.checkpoint}.csv")
        print(f"{len(res)} alerts -> {d / f'alerts_val_{a.checkpoint}.csv'}")


if __name__ == "__main__":
    main()

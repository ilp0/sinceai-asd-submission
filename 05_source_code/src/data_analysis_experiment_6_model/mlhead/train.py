"""Resumable training, evaluation and alert export."""
from __future__ import annotations

import contextlib
import json
import os
import math
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .config import data_fingerprint, fingerprint, resolve
from .data import StepBatchSampler, WindowDataset, collate, row_vocabulary
from .metrics import evaluate_predictions
from .benchmark import Benchmark, alerts_from_predictions
from .benchmark import settings as bench_settings
from .model import TimestralMultiLabel, masked_loss

def run_dir(cfg: dict) -> Path:
    return resolve(cfg["run"]["output_root"]) / cfg["run"]["name"]


def device_of(cfg: dict) -> torch.device:
    d = cfg["run"]["device"]
    if d == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("run.device=cuda but no GPU is visible")
    if d == "cuda" and cfg["run"].get("tf32", True):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    return torch.device(d)


def autocast(cfg: dict, device: torch.device):
    if cfg["run"]["precision"] == "bf16":
        return torch.autocast(device_type=device.type, dtype=torch.bfloat16)
    return contextlib.nullcontext()


def to_device(batch: dict, device: torch.device) -> dict:
    return {k: v.to(device, non_blocking=True) for k, v in batch.items()}


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def write_json(path: Path, value) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str))
    tmp.replace(path)


def lr_lambda(tc: dict):
    warm, total = tc["warmup_steps"], tc["max_steps"]

    def f(step):
        if step < warm:
            return (step + 1) / max(1, warm)
        if tc["schedule"] == "constant":
            return 1.0
        prog = (step - warm) / max(1, total - warm)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, prog)))
    return f


@torch.no_grad()
def predict_windows(model, ds: WindowDataset, cfg: dict, device, max_windows=None, seed=0) -> pd.DataFrame:
    """Probabilities, labels and the top evidence row per class for each window."""
    model.eval()
    idx = np.arange(len(ds))
    stride_factor = 1
    if max_windows and len(idx) > max_windows:
        # Every k-th window (not a random sample): positive runs stay contiguous in time.
        stride_factor = int(math.ceil(len(idx) / max_windows))
        idx = idx[::stride_factor]
    loader = torch.utils.data.DataLoader(
        torch.utils.data.Subset(ds, idx), batch_size=cfg["train"].get("eval_batch_size") or cfg["train"]["batch_size"] * 2,
        shuffle=False,
        num_workers=cfg["run"]["num_workers"], collate_fn=collate)
    classes, vocab = cfg["labels"]["classes"], np.array(row_vocabulary(cfg), dtype=object)
    # Batch results stay on the CPU as arrays; the frame is built once at the end. (A per-window,
    # per-class loop with one GPU read each made a 60 000-window pass take several minutes.)
    wins, probs, ys, evid = [], [], [], []
    for batch in loader:
        b = to_device(batch, device)
        with autocast(cfg, device):
            logits, attn = model(b)
        probs.append(torch.sigmoid(logits.float()).cpu().numpy())
        ys.append(np.where(batch["label_mask"].numpy() > 0, batch["labels"].numpy(), -1).astype(np.int8))
        # Copies: a view keeps the worker's shared-memory file descriptor open ("Too many open files").
        wins.append(batch["window"].numpy().copy())
        if attn is not None:
            # Padded rows have attention 0, so the argmax over all slots is the strongest valid row.
            top = attn.float().argmax(-1).cpu().numpy()                                   # (B, K)
            counts = torch.bincount(batch["group_ids"]).numpy()
            start = np.cumsum(counts) - counts
            evid.append(vocab[batch["row_ids"].numpy()[start[:, None] + top]])
    model.train()
    w = np.concatenate(wins) if wins else np.zeros(0, np.int64)
    a, e = ds.index[w, 0], ds.index[w, 1]
    t0 = np.array([pd.Timestamp(m["t0"]).value for m in ds.meta], np.int64)
    period = np.array([m["period_s"] for m in ds.meta], np.int64)
    cols = dict(asset=np.array([m["key"] for m in ds.meta], dtype=object)[a],
                time=pd.to_datetime(t0[a] + (e + 1) * period[a] * 1_000_000_000, utc=True))
    prob, y = (np.concatenate(probs), np.concatenate(ys)) if probs else (np.zeros((0, len(classes))),) * 2
    ev = np.concatenate(evid) if evid else None
    for k, c in enumerate(classes):
        cols[f"p_{c}"] = prob[:, k].astype(float)
        cols[f"y_{c}"] = y[:, k].astype(int)
        if ev is not None:
            cols[f"evidence_{c}"] = ev[:, k]
    df = pd.DataFrame(cols)
    df.attrs["stride_factor"] = stride_factor
    return df


def compact_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    """float32 probabilities, int8 labels, categorical evidence (about 5x smaller files)."""
    out = pred.copy()
    for c in out.columns:
        if c.startswith("p_"):
            out[c] = out[c].astype(np.float32)
        elif c.startswith("y_"):
            out[c] = out[c].astype(np.int8)
        elif c.startswith("evidence_") or c == "asset":
            out[c] = out[c].astype("category")
    return out


def build(cfg: dict):
    dev = device_of(cfg)
    seed_all(cfg["run"]["seed"])
    model = TimestralMultiLabel(cfg).to(dev)
    return model, dev


def clean_history(path: Path) -> list[dict]:
    """History records of the run that the checkpoint continues: steps 1, 2, 3 ... in order.
    Lines of an aborted duplicate process (a restart from step 1) are dropped."""
    kept = []
    for line in path.read_text().splitlines() if path.exists() else []:
        d = json.loads(line)
        if d["step"] == (kept[-1]["step"] if kept else 0) + 1:
            kept.append(d)
    return kept


def tensorboard_writer(out: Path, history: list[dict]):
    """SummaryWriter that first adds events for history steps that have none yet (or None)."""
    try:
        from torch.utils.tensorboard import SummaryWriter
    except ImportError:
        print("warning: tensorboard is not installed; no TensorBoard events are written")
        return None
    marker = out / "tensorboard" / "last_step.txt"
    done = int(marker.read_text()) if marker.exists() else 0
    tb = SummaryWriter(str(out / "tensorboard"))
    for rec in history:
        if rec["step"] > done:
            log_scalars(tb, rec)
    return tb


def log_scalars(tb, rec: dict) -> None:
    for k, v in rec.items():
        if isinstance(v, (int, float)) and k != "step":
            tb.add_scalar(k if "/" in k else f"train/{k}", v, rec["step"])
    if isinstance(rec.get("val/per_class"), dict):
        for c, m in rec["val/per_class"].items():
            for k in ("auprc", "auroc"):
                if isinstance(m.get(k), float) and not math.isnan(m[k]):
                    tb.add_scalar(f"val_{k}/{c}", m[k], rec["step"])
    tb.flush()
    (Path(tb.log_dir) / "last_step.txt").write_text(str(rec["step"]))


def train(cfg: dict, stop_after_steps: int | None = None, log=print) -> dict:
    tc, out = cfg["train"], run_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    # One training process per run directory: a second one (for example after a supervisor restart)
    # waits here, then resumes from the checkpoint that the first one wrote.
    import fcntl
    lock = open(out / "train.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    cfg_fp = fingerprint({k: v for k, v in cfg.items() if not k.startswith("_")})
    ckpt_path, summary_path = out / "checkpoint.pt", out / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    if summary.get("completed"):
        log(json.dumps(dict(already_completed=True, **{k: summary[k] for k in ("step", "best_step", "best_metric")})))
        return summary
    if summary and summary.get("config_fingerprint") != cfg_fp:
        raise RuntimeError(f"{out} holds a run with a different configuration; change run.name")
    if not ckpt_path.exists():
        (out / "config.json").write_text(json.dumps(cfg, indent=2, default=str))

    model, dev = build(cfg)
    train_ds = WindowDataset(cfg, "train", cfg["data"]["train_stride_s"])
    val_ds = WindowDataset(cfg, "val", cfg["data"]["eval_stride_s"])
    sc = cfg["data"]["sampler"]
    probe = StepBatchSampler(train_ds, tc["batch_size"], cfg["run"]["seed"], 0, 0, sc["positive_fraction"], sc["benign_fraction"])
    rate = torch.tensor(probe.expected_positive_rate(), dtype=torch.float32)
    lc = cfg["loss"]
    pos_weight = None
    if lc["pos_weight"] == "auto":
        pos_weight = ((1 - rate) / rate.clamp(min=1e-6)).clamp(1.0, lc["max_pos_weight"]).to(dev)
    elif lc["pos_weight"] not in (None, "none"):
        pos_weight = torch.tensor(lc["pos_weight"], dtype=torch.float32, device=dev)

    opt = torch.optim.AdamW(model.parameter_groups(tc), betas=(0.9, 0.999))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda(tc))
    step, best, best_step, bad_evals = 0, -float("inf"), None, 0
    if ckpt_path.exists():
        st = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        if st.get("config_fingerprint") != cfg_fp:
            raise RuntimeError(f"{ckpt_path} was written with a different configuration; change run.name")
        model.load_state_dict(st["model"])
        opt.load_state_dict(st["optimizer"])
        sched.load_state_dict(st["scheduler"])
        torch.set_rng_state(st["torch_rng"])
        if dev.type == "cuda" and st.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(st["cuda_rng"])
        step, best, best_step, bad_evals = st["step"], st["best"], st["best_step"], st["bad_evals"]
        log(json.dumps(dict(resumed_step=step)))
    else:
        model.head.set_prior(rate)

    info = dict(parameters=model.count_parameters(), train_windows=len(train_ds), val_windows=len(val_ds),
                train_assets=[m["key"] for m in train_ds.meta], val_assets=[m["key"] for m in val_ds.meta],
                expected_positive_rate=dict(zip(cfg["labels"]["classes"], rate.tolist())),
                pos_weight=None if pos_weight is None else pos_weight.tolist(),
                data_fingerprint=data_fingerprint(cfg), config_fingerprint=cfg_fp,
                torch=torch.__version__, hip=getattr(torch.version, "hip", None),
                device_name=torch.cuda.get_device_name() if dev.type == "cuda" else str(dev))
    log(json.dumps(info))
    hist_path = out / "history.jsonl"
    history_records = [r for r in clean_history(hist_path) if r["step"] <= step]
    hist_path.write_text("".join(json.dumps(r, default=str) + "\n" for r in history_records))
    tb = tensorboard_writer(out, history_records)

    stop = tc["max_steps"] if stop_after_steps is None else min(tc["max_steps"], stop_after_steps)
    micro = StepBatchSampler(train_ds, tc["batch_size"], cfg["run"]["seed"],
                             step * tc["grad_accumulation"], stop * tc["grad_accumulation"],
                             sc["positive_fraction"], sc["benign_fraction"])
    loader = torch.utils.data.DataLoader(train_ds, batch_sampler=micro, num_workers=cfg["run"]["num_workers"],
                                         collate_fn=collate, pin_memory=dev.type == "cuda",
                                         persistent_workers=cfg["run"]["num_workers"] > 0)
    bench = Benchmark(cfg) if bench_settings(cfg)["enabled"] else None
    # The benchmark windows are a subset of the validation windows when the strides agree and no
    # cap applies: one prediction pass then serves both.
    reuse_pred = (bench is not None and bench_settings(cfg)["stride_s"] == cfg["data"]["eval_stride_s"]
                  and not tc.get("eval_max_windows"))
    history = open(out / "history.jsonl", "a")
    model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    metric_name = tc["early_stopping"]["metric"]
    t_start, acc_loss, k = time.monotonic(), 0.0, 0
    t_last = t_start
    stopped_early = False

    def save(path):
        tmp = path.with_suffix(".tmp")
        torch.save(dict(model=model.state_dict(), optimizer=opt.state_dict(), scheduler=sched.state_dict(),
                        torch_rng=torch.get_rng_state(),
                        cuda_rng=torch.cuda.get_rng_state_all() if dev.type == "cuda" else None,
                        config_fingerprint=cfg_fp, step=step, best=best, best_step=best_step,
                        bad_evals=bad_evals), tmp)
        tmp.replace(path)

    for batch in loader:
        b = to_device(batch, dev)
        with autocast(cfg, dev):
            logits, _ = model(b)
        loss = masked_loss(logits, b["labels"], b["label_mask"], lc, pos_weight) / tc["grad_accumulation"]
        loss.backward()
        acc_loss += float(loss.detach())
        k += 1
        if k % tc["grad_accumulation"]:
            continue
        gnorm = torch.nn.utils.clip_grad_norm_(params, tc["gradient_clip"])
        opt.step()
        sched.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        now = time.monotonic()
        rec = dict(step=step, train_loss=acc_loss, grad_norm=float(gnorm), lr=sched.get_last_lr()[0],
                   seconds=now - t_start)
        rec["time/step_seconds"] = now - t_last
        t_last = now
        acc_loss = 0.0
        if step % tc["eval_every"] == 0 or step == tc["max_steps"]:
            t_eval = time.monotonic()
            pred = predict_windows(model, val_ds, cfg, dev, tc.get("eval_max_windows"), cfg["run"]["seed"])
            rec["time/predict_seconds"] = time.monotonic() - t_eval
            m = evaluate_predictions(pred, cfg["labels"]["classes"], cfg["predict"]["threshold"],
                                     cfg["data"]["eval_stride_s"] * pred.attrs["stride_factor"],
                                     window_weight=pred.attrs["stride_factor"])
            rec.update({f"val/{k2}": v for k2, v in m.items() if k2 != "per_class"})
            rec["val/per_class"] = m["per_class"]
            # Not a config key: a new key would change the config fingerprint of running runs.
            if os.environ.get("MLHEAD_SAVE_PREDICTIONS") == "1":
                # Window probabilities of every evaluation, for offline alert-rule analysis.
                (out / "predictions").mkdir(exist_ok=True)
                compact_predictions(pred).to_parquet(out / "predictions" / f"val_step{step:05d}.parquet", index=False)
            if bench is not None:
                t_b = time.monotonic()
                b = bench.run(model, dev, pred if reuse_pred else None)
                rec["time/bench_seconds"] = time.monotonic() - t_b
                rec.update({f"bench_{k2}": v for k2, v in b["scalars"].items()})
                log(json.dumps(dict(step=step, **{k2: round(v, 3) for k2, v in rec.items()
                                                  if k2.startswith("bench_all/composite") or k2.startswith("time/")})))
            rec["time/eval_seconds"] = time.monotonic() - t_eval
            cur = rec.get(metric_name, float("nan"))
            if not math.isnan(cur) and cur > best:
                best, best_step, bad_evals = cur, step, 0
                save(out / "best.pt")
            else:
                bad_evals += 1
            stopped_early = bad_evals >= tc["early_stopping"]["patience_evals"]
        if tb:
            log_scalars(tb, rec)
        history.write(json.dumps(rec, default=str) + "\n")
        history.flush()
        if step % tc["checkpoint_every"] == 0 or step >= stop or stopped_early:
            save(ckpt_path)
        if stopped_early:
            break
    history.close()
    if tb:
        tb.close()
    completed = stopped_early or step >= tc["max_steps"]
    summary = dict(step=step, completed=completed, stopped_early=stopped_early, best_metric=best,
                   best_step=best_step, metric=metric_name, **info)
    write_json(summary_path, summary)
    log(json.dumps({k: summary[k] for k in ("step", "completed", "best_metric", "best_step")}))
    return summary


def load_trained(cfg: dict, which: str = "best"):
    model, dev = build(cfg)
    path = run_dir(cfg) / f"{which}.pt"
    if not path.exists() and which == "best":
        print(f"warning: {path} missing (no evaluation improved); using checkpoint.pt")
        path = run_dir(cfg) / "checkpoint.pt"
    st = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(st["model"])
    return model, dev, st["step"]


def evaluate(cfg: dict, which: str = "best", log=print) -> dict:
    model, dev, step = load_trained(cfg, which)
    ds = WindowDataset(cfg, "val", cfg["data"]["eval_stride_s"])
    pred = predict_windows(model, ds, cfg, dev, cfg["predict"].get("max_windows"))
    out = run_dir(cfg)
    pred.to_parquet(out / f"predictions_val_{which}.parquet", index=False)
    k = pred.attrs["stride_factor"]
    m = evaluate_predictions(pred, cfg["labels"]["classes"], cfg["predict"]["threshold"],
                             cfg["data"]["eval_stride_s"] * k, window_weight=k)
    m["stride_factor"] = k
    m["checkpoint_step"] = step
    if bench_settings(cfg)["enabled"]:
        b = Benchmark(cfg).run(model, dev)
        m["benchmark"] = b["scalars"]
        for src, d in b["details"].items():
            write_json(out / f"benchmark_{src}_{which}.json", dict(result=d["result"], per_event=d["per_event"]))
            d["alerts"].to_csv(out / f"benchmark_alerts_{src}_{which}.csv", index=False)
        tb = tensorboard_writer(out, [])
        if tb:
            log_scalars(tb, dict(step=step, **{f"bench_final_{which}_{k2}": v for k2, v in b["scalars"].items()}))
            tb.close()
    write_json(out / f"metrics_val_{which}.json", m)
    log(json.dumps({k: v for k, v in m.items() if k != "per_class"}))
    return m


def export_alerts(cfg: dict, predictions: Path, dest: Path) -> pd.DataFrame:
    """Submission-format alerts from saved window predictions (rules in benchmark.alerts_from_predictions)."""
    res = alerts_from_predictions(cfg, pd.read_parquet(predictions))
    dest.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(dest, index=False)
    return res

"""Per-class alert thresholds for a frozen experiment-6 model, with leave-one-pump-out (LOPO) validation.

    .venv/bin/python per_class.py --model 6h [--windows 30 180] [--name per-class-6h-v1]

Search (for one running-average window): start with every class at --start (0.99), then coordinate ascent: for each
class in turn, try every value of LEVELS (OFF = the class never alerts) and keep the value with the best composite on
the selection pumps; repeat until no class changes (at most --passes passes). The window is chosen on the selection
pumps as well.

Results (organizer composite on the 7 validation pumps):
  global_fit     best common (threshold, window) of the global grid, chosen on all 7 pumps (optimistic)
  global_lopo    the same choice made on 6 pumps and applied to the 7th, for each pump; held-out alerts scored together
  per_class_fit  per-class thresholds chosen on all 7 pumps (optimistic; the setting to use for the test pumps)
  per_class_lopo per-class thresholds chosen on 6 pumps and applied to the 7th (honest estimate of the method)
The checkpoint and the global grid were also inspected on these pumps, so even the LOPO values are a little optimistic.
Outputs: results/<name>/ (per_class.json, report.md, alerts_fit.csv, per_type.csv), tensorboard/<name>/.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from alerts import CLASSES, Truth, alert_type_table, event_type_table, fast_alerts, load_predictions, smooth
from study import EXP, FIXED, MODELS

HERE = Path(__file__).resolve().parent
OFF = 1.01
LEVELS = [0.9, 0.95, 0.97, 0.98, 0.99, 0.993, 0.995, 0.997, 0.999, OFF]
GLOBAL_THRESHOLDS = [0.9, 0.95, 0.98, 0.99, 0.993, 0.995, 0.997]

_S: dict = {}          # per-process state (predictions, truth)


def _init(model: str, windows: list[int], pred_root: str):
    df, meta = load_predictions(Path(pred_root) / MODELS[model])
    _S["frames"] = {w: smooth(df, w) for w in windows}
    _S["truth"] = Truth(EXP)
    _S["meta"] = meta


def _score(alerts: pd.DataFrame, keys: list[str]) -> dict:
    t = _S["truth"]
    ev, assets, bn = t.subset(keys)
    from retrofit_sim import scoring
    return scoring.score(alerts[alerts.asset_id.isin(set(assets.asset_id))], ev, assets, bn)


def _alerts(w: int, thr: dict, keys: list[str] | None = None) -> pd.DataFrame:
    df = _S["frames"][w]
    if keys is not None:
        df = df[df.asset.isin(keys)]
    off = tuple(c for c, v in thr.items() if v >= 1.0)
    return fast_alerts(df, 0.99, 1, class_thresholds={c: v for c, v in thr.items() if v < 1.0},
                       disabled_classes=off, **FIXED)


def search(job: tuple) -> dict:
    """Coordinate ascent on the selection pumps `keys` for every window; returns the best (window, thresholds)."""
    keys, windows, start, passes = job
    best_all = None
    for w in windows:
        thr = {c: start for c in CLASSES}
        cur = _score(_alerts(w, thr, keys), keys)["composite_score"]
        evals, trace = 1, [cur]
        for _ in range(passes):
            changed = False
            for c in CLASSES:
                best_v, best_s = thr[c], cur
                for v in LEVELS:
                    if v == thr[c]:
                        continue
                    s = _score(_alerts(w, {**thr, c: v}, keys), keys)["composite_score"]
                    evals += 1
                    if s > best_s + 1e-9:
                        best_v, best_s = v, s
                if best_v != thr[c]:
                    thr[c], cur, changed = best_v, best_s, True
                    trace.append(cur)
            if not changed:
                break
        if best_all is None or cur > best_all["selection_composite"]:
            best_all = dict(window_s=w, thresholds=thr, selection_composite=cur, evals=evals, trace=trace)
    return dict(best_all, keys=keys)


def global_choice(job: tuple) -> dict:
    keys, windows = job
    best = None
    for w in windows:
        for t in GLOBAL_THRESHOLDS:
            s = _score(_alerts(w, {c: t for c in CLASSES}, keys), keys)["composite_score"]
            if best is None or s > best["selection_composite"] + 1e-9:
                best = dict(window_s=w, threshold=t, selection_composite=s)
    return dict(best, keys=keys)


def held_out(keys_all: list[str], choices: list[dict], per_class: bool) -> pd.DataFrame:
    parts = []
    for k, ch in zip(keys_all, choices):
        thr = ch["thresholds"] if per_class else {c: ch["threshold"] for c in CLASSES}
        parts.append(_alerts(ch["window_s"], thr, [k]))
    return pd.concat(parts, ignore_index=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODELS))
    ap.add_argument("--windows", nargs="+", type=int, default=[30, 60, 180])
    ap.add_argument("--global-windows", nargs="+", type=int, default=[30, 60, 120, 180, 300])
    ap.add_argument("--start", type=float, default=0.99)
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--name")
    ap.add_argument("--pred-root", default=str(HERE / "predictions"))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    name = a.name or f"per-class-{a.model}-v1"
    out = HERE / "results" / name
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    windows = sorted(set(a.windows) | set(a.global_windows))
    _init(a.model, windows, a.pred_root)
    keys = sorted(_S["truth"].specs)
    folds = [[k for k in keys if k != h] for h in keys]
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(a.model, windows, a.pred_root)) as ex:
        pc_jobs = [(ks, a.windows, a.start, a.passes) for ks in [keys] + folds]
        gl_jobs = [(ks, a.global_windows) for ks in [keys] + folds]
        pc = list(ex.map(search, pc_jobs))
        gl = list(ex.map(global_choice, gl_jobs))
    print(f"searches done in {time.time() - t0:.0f} s", flush=True)

    truth = _S["truth"]
    res = {}
    fit_pc = _alerts(pc[0]["window_s"], pc[0]["thresholds"])
    fit_gl = _alerts(gl[0]["window_s"], {c: gl[0]["threshold"] for c in CLASSES})
    sets = dict(global_fit=fit_gl, global_lopo=held_out(keys, gl[1:], False),
                per_class_fit=fit_pc, per_class_lopo=held_out(keys, pc[1:], True))
    for n, al in sets.items():
        res[n] = {g: {k: v for k, v in truth.score(al, g).items() if k != "per_event" and not isinstance(v, (list, dict))}
                  for g in ("all", "val-orig", "val-new")}
        res[n]["per_event"] = truth.score(al, "all")["per_event"]
        print(f"{n:15s} composite all={res[n]['all']['composite_score']:.2f} 08/09={res[n]['val-orig']['composite_score']:.2f} "
              f"new={res[n]['val-new']['composite_score']:.2f} alerts={len(al)}", flush=True)
    fit_pc.to_csv(out / "alerts_fit.csv", index=False)
    sets["per_class_lopo"].to_csv(out / "alerts_lopo.csv", index=False)
    windows_tab = truth.event_windows()
    ev = event_type_table(res["per_class_fit"]["per_event"])
    al = alert_type_table(fit_pc, windows_tab, res["per_class_fit"]["all"]["asset_days"])
    pt = ev.merge(al, on="fault_type", how="outer")
    pt.to_csv(out / "per_type.csv", index=False)

    doc = dict(model=a.model, meta=_S["meta"], fixed=FIXED, levels=LEVELS, start=a.start, windows=a.windows,
               global_windows=a.global_windows, global_thresholds=GLOBAL_THRESHOLDS,
               fit=dict(per_class=pc[0], global_=gl[0]),
               folds=[dict(held_out=h, per_class=p, global_=g) for h, p, g in zip(keys, pc[1:], gl[1:])],
               scores={n: {g: v for g, v in r.items() if g != "per_event"} for n, r in res.items()})
    (out / "per_class.json").write_text(json.dumps(doc, indent=1, default=str))

    # TensorBoard
    from tensorboardX import SummaryWriter
    with SummaryWriter(str(HERE / "tensorboard" / name)) as tb:
        for n, r in res.items():
            for k in ("composite_score", "event_f1", "alert_precision", "event_recall", "fault_type_recall",
                      "timeliness", "false_alerts_per_asset_day"):
                tb.add_scalar(f"{n}/{k}", r["all"][k], 0)
        for i, v in enumerate(pc[0]["trace"]):
            tb.add_scalar("fit/selection_composite_trace", v, i)
        for c, v in pc[0]["thresholds"].items():
            tb.add_scalar(f"fit_threshold/{c}", v, 0)

    # report
    def lv(v):
        return "off" if v >= 1.0 else f"{v:g}"
    L = [f"# Per-class thresholds, model {a.model} (`{name}`)", "",
         f"Model `{_S['meta']['run']}` `{_S['meta']['checkpoint']}`, predictions every {_S['meta']['stride_s']} s. "
         f"Rules: {json.dumps(FIXED)}, persistence one window. Levels per class: "
         f"{', '.join(lv(v) for v in LEVELS)}. Windows searched: {a.windows} s.", "",
         "## Scores (organizer composite)", "",
         "`fit` = chosen and scored on the same 7 pumps (optimistic). `lopo` = for each pump, chosen on the other 6 pumps "
         "and applied to it; the 7 held-out alert sets scored together.", "",
         "| Method | All 7 | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in ("global_fit", "global_lopo", "per_class_fit", "per_class_lopo"):
        r = res[n]
        L.append(f"| {n} | **{r['all']['composite_score']:.1f}** | {r['val-orig']['composite_score']:.1f} | "
                 f"{r['val-new']['composite_score']:.1f} | {r['all']['event_f1']:.2f} | {r['all']['alert_precision']:.2f} | "
                 f"{r['all']['event_recall']:.2f} | {r['all']['fault_type_recall']:.2f} | {r['all']['timeliness']:.2f} | "
                 f"{r['all']['false_alerts_per_asset_day']:.2f} | {r['all']['alerts_scored']} |")
    L += ["", f"Global fit: threshold {gl[0]['threshold']:g}, window {gl[0]['window_s']} s.", "",
          f"## Per-class thresholds chosen on all 7 pumps (window {pc[0]['window_s']} s)", "",
          "The fold columns show the value chosen without each pump: a stable class has the same value in most folds.", "",
          "| Fault type | Fit | " + " | ".join(k.split("/")[-1].replace("GEN-val6-45001-", "new-") for k in keys) +
          " | Events | Detected | Type correct | Alerts | Correct | Wrong | Outside |",
          "|---|---|" + "---|" * len(keys) + "---|---|---|---|---|---|---|"]
    pti = pt.set_index("fault_type")
    for c in CLASSES:
        r = pti.loc[c] if c in pti.index else None
        g = lambda k: ("–" if r is None or pd.isna(r.get(k)) else int(r[k]))
        L.append(f"| {c} | **{lv(pc[0]['thresholds'][c])}** | " +
                 " | ".join(lv(f['thresholds'][c]) for f in pc[1:]) +
                 f" | {g('events')} | {g('detected')} | {g('type_correct')} | {g('bursts')} | {g('correct_type')} | "
                 f"{g('wrong_type')} | {g('outside')} |")
    L += ["", "Fold windows: " + ", ".join(f"{k.split('/')[-1]}: {f['window_s']} s" for k, f in zip(keys, pc[1:])), "",
          f"Done in {time.time() - t0:.0f} s."]
    (out / "report.md").write_text("\n".join(L) + "\n")
    print(f"done in {time.time() - t0:.0f} s -> {out}", flush=True)


if __name__ == "__main__":
    main()

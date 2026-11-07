"""Optuna grid study: alert threshold x causal running average of the class probabilities, for the frozen
experiment-6 models (3h and 6h context). Objective: organizer composite score on the 7 validation pumps.

    .venv/bin/python study.py [--study thr-window-v1] [--persistence-min 0 15] [--models 3h 6h]

Search space (user request 7 Nov 2026): model {3h, 6h} x threshold {0.7, 0.8, 0.85, 0.9, 0.95, 0.99} x window {5, 15, 30, 60 s}
(reduced by the user on 7 Nov 2026 from 8 thresholds and 5 windows).
Fixed rules (experiment-6 defaults): cooldown 720 min per class, 5 min gap between alerts of one pump, persistence
--persistence-min (a grid dimension; 0 = one window: the running average is the only time filter).

Telemetry per trial (all in the Optuna storage as user attributes, plus files and TensorBoard):
  * every organizer metric for the groups all / val-orig (PUMP-08/09) / val-new (5 generated pumps)
  * per true fault type: events, detected, type-correct, recall, type recall, timeliness, median delay, repeats
  * per predicted fault type: bursts, correct-type / wrong-type / outside-window bursts, false bursts per asset-day
  * per (model, window): window-level AUPRC of the smoothed probability for each class
Outputs: results/<study>/ (trials.csv, per_type_events.csv, per_type_alerts.csv, window_auprc.csv,
alerts/<trial>.csv, per_event/<trial>.csv, report.md, figures), tensorboard/<study>/, study.db.
Selection uses the validation pumps only; the scores are optimistic (the same events select and score).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import optuna
import pandas as pd

from alerts import CLASSES, SCALARS, Truth, alert_type_table, average_precision, event_type_table, fast_alerts, \
    load_predictions, smooth

HERE = Path(__file__).resolve().parent
# The experiment-6 folder: the worktree in the experiment repository, else a sibling folder (submission package layout).
EXP = next((p for p in (HERE.parent / ".claude/worktrees/timestral-multiclass-prediction-c697e7/data_analysis_experiment_6_model",
                        HERE.parent / "data_analysis_experiment_6_model") if p.exists()),
           HERE.parent / "data_analysis_experiment_6_model")
MODELS = {"3h": "rp3-3h-r32-v1", "6h": "rp3-6h-r32-v1"}
THRESHOLDS = [0.7, 0.8, 0.85, 0.9, 0.95, 0.99]
WINDOWS_S = [5, 15, 30, 60]
FIXED = dict(cooldown_minutes=720, global_gap_minutes=5)
GROUPS = ["all", "val-orig", "val-new"]
# Reference: the rule of the current submission (threshold 0.9, persistence 15 min, no smoothing).
REFERENCE = dict(threshold=0.9, window_s=0, persistence_s=900)


class Data:
    """Predictions per model and smoothed copies per (model, window), built once."""

    def __init__(self, models, root: Path):
        self.raw, self.meta, self.cache = {}, {}, {}
        for m in models:
            self.raw[m], self.meta[m] = load_predictions(root / MODELS[m])

    def get(self, m: str, w: int) -> pd.DataFrame:
        if (m, w) not in self.cache:
            self.cache[(m, w)] = self.raw[m] if w <= 0 else smooth(self.raw[m], w)
        return self.cache[(m, w)]

    def persistence_windows(self, m: str, seconds: float) -> int:
        return max(1, int(round(seconds / self.meta[m]["stride_s"])))


def evaluate(data: Data, truth: Truth, windows: pd.DataFrame, m: str, thr: float, w: int, persistence_s: float):
    df = data.get(m, w)
    alerts = fast_alerts(df, thr, data.persistence_windows(m, persistence_s), **FIXED)
    res = {g: truth.score(alerts, g) for g in GROUPS}
    ev_t = event_type_table(res["all"]["per_event"])
    al_t = alert_type_table(alerts, windows, res["all"]["asset_days"])
    return alerts, res, ev_t, al_t


def scalars(res: dict) -> dict:
    out = {}
    for g, r in res.items():
        for k in SCALARS:
            v = r.get(k)
            if isinstance(v, (int, float, np.integer, np.floating)) and v is not None and not pd.isna(v):
                out[f"{g}/{k}"] = float(v)
    return out


def window_auprc(data: Data, m: str, w: int) -> dict:
    df = data.get(m, w)
    out = {}
    for c in CLASSES:
        y, p = df[f"y_{c}"].to_numpy(), df[f"p_{c}"].to_numpy()
        k = y >= 0
        out[c] = average_precision((y[k] == 1).astype(int), p[k]) if k.any() else float("nan")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", default="thr-window-v1")
    ap.add_argument("--models", nargs="+", default=list(MODELS))
    ap.add_argument("--persistence-min", nargs="+", type=float, default=[0])
    ap.add_argument("--thresholds", nargs="+", type=float, default=THRESHOLDS)
    ap.add_argument("--windows", nargs="+", type=int, default=WINDOWS_S)
    ap.add_argument("--pred-root", default=str(HERE / "predictions"))
    ap.add_argument("--storage", default=f"sqlite:///{HERE / 'study.db'}")
    a = ap.parse_args()
    THRESHOLDS[:] = a.thresholds
    WINDOWS_S[:] = a.windows

    from tensorboardX import SummaryWriter
    out = HERE / "results" / a.study
    for d in ("alerts", "per_event"):
        (out / d).mkdir(parents=True, exist_ok=True)
    tb_root = HERE / "tensorboard" / a.study

    t0 = time.time()
    data = Data(a.models, Path(a.pred_root))
    truth = Truth(EXP)
    windows = truth.event_windows()
    print(json.dumps({m: data.meta[m] for m in a.models}), flush=True)

    space = dict(model=a.models, threshold=THRESHOLDS, window_s=WINDOWS_S, persistence_min=a.persistence_min)
    study = optuna.create_study(study_name=a.study, storage=a.storage, direction="maximize", load_if_exists=True,
                                sampler=optuna.samplers.GridSampler(space, seed=0))
    study.set_user_attr("fixed_rules", dict(FIXED))
    study.set_user_attr("models", {m: data.meta[m] for m in a.models})
    study.set_user_attr("objective", "organizer composite_score, all 7 validation pumps")

    # Window-level AUPRC of the smoothed probabilities (independent of the threshold).
    auprc_rows = []
    for m in a.models:
        for w in WINDOWS_S:
            for c, v in window_auprc(data, m, w).items():
                auprc_rows.append(dict(model=m, window_s=w, fault_type=c, auprc=v))
    auprc = pd.DataFrame(auprc_rows)
    auprc.to_csv(out / "window_auprc.csv", index=False)
    with SummaryWriter(str(tb_root / "window_auprc")) as tb:
        for (m, c), g in auprc.groupby(["model", "fault_type"]):
            for _, r in g.iterrows():
                if not pd.isna(r.auprc):
                    tb.add_scalar(f"auprc_{m}/{c}", r.auprc, int(r.window_s))

    def objective(trial: optuna.Trial) -> float:
        m = trial.suggest_categorical("model", a.models)
        thr = trial.suggest_categorical("threshold", THRESHOLDS)
        w = trial.suggest_categorical("window_s", WINDOWS_S)
        pm = trial.suggest_categorical("persistence_min", a.persistence_min)
        ts = time.time()
        alerts, res, ev_t, al_t = evaluate(data, truth, windows, m, thr, w, pm * 60)
        sc = scalars(res)
        for k, v in sc.items():
            trial.set_user_attr(k, v)
        trial.set_user_attr("per_type_events", ev_t.to_dict("records"))
        trial.set_user_attr("per_type_alerts", al_t.to_dict("records"))
        trial.set_user_attr("seconds", round(time.time() - ts, 2))
        name = f"{trial.number:03d}_{m}_thr{thr:g}_w{w}_p{pm:g}"
        alerts.to_csv(out / "alerts" / f"{name}.csv", index=False)
        pd.DataFrame(res["all"]["per_event"]).to_csv(out / "per_event" / f"{name}.csv", index=False)
        with SummaryWriter(str(tb_root / "trials" / name)) as tb:
            hp = dict(model=m, threshold=thr, window_s=w, persistence_min=pm)
            metrics = {f"hparam/{k}": v for k, v in sc.items() if k.split("/")[1] in
                       ("composite_score", "event_f1", "alert_precision", "event_recall", "fault_type_recall",
                        "timeliness", "false_alerts_per_asset_day")}
            for _, r in ev_t.iterrows():
                metrics[f"hparam/type_recall/{r.fault_type}"] = float(r.type_recall)
            tb.add_hparams(hp, metrics, name=".")
        print(f"trial {trial.number:3d} {m} thr={thr:<5g} w={w:>3}s p={pm:g}min composite={sc['all/composite_score']:.2f} "
              f"(08/09 {sc['val-orig/composite_score']:.1f}, new {sc['val-new/composite_score']:.1f}) "
              f"alerts={len(alerts)} fa/day={sc['all/false_alerts_per_asset_day']:.2f}", flush=True)
        return sc["all/composite_score"]

    n_grid = len(a.models) * len(THRESHOLDS) * len(WINDOWS_S) * len(a.persistence_min)
    done = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])
    if done < n_grid:
        study.optimize(objective, n_trials=n_grid - done)

    # Reference rule (current submission) on the same fine-stride predictions, not part of the search.
    ref = {}
    for m in a.models:
        _, res, ev_t, al_t = evaluate(data, truth, windows, m, REFERENCE["threshold"], 0, REFERENCE["persistence_s"])
        ref[m] = dict(scalars=scalars(res), per_type_events=ev_t, per_type_alerts=al_t)
    report(study, out, tb_root, ref, auprc, a)
    print(f"done in {time.time() - t0:.0f} s -> {out}", flush=True)


def report(study, out: Path, tb_root: Path, ref: dict, auprc: pd.DataFrame, a) -> None:
    from tensorboardX import SummaryWriter
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    rows, ev_rows, al_rows = [], [], []
    for t in trials:
        base = dict(trial=t.number, **t.params)
        rows.append(dict(base, **{k: v for k, v in t.user_attrs.items() if not k.startswith("per_type")}))
        ev_rows += [dict(base, **r) for r in t.user_attrs.get("per_type_events", [])]
        al_rows += [dict(base, **r) for r in t.user_attrs.get("per_type_alerts", [])]
    tr = pd.DataFrame(rows).sort_values("all/composite_score", ascending=False)
    ev = pd.DataFrame(ev_rows)
    al = pd.DataFrame(al_rows)
    tr.to_csv(out / "trials.csv", index=False)
    ev.to_csv(out / "per_type_events.csv", index=False)
    al.to_csv(out / "per_type_alerts.csv", index=False)

    figs = {}
    # Composite heat maps: threshold x window, one per model and group.
    for g in ("all", "val-orig", "val-new"):
        fig, axes = plt.subplots(1, len(a.models), figsize=(5.5 * len(a.models), 4), squeeze=False)
        for ax, m in zip(axes[0], a.models):
            pv = tr[tr.model == m].pivot_table(index="threshold", columns="window_s", values=f"{g}/composite_score", aggfunc="max")
            im = ax.imshow(pv.values, cmap="viridis", aspect="auto", vmin=tr[f"{g}/composite_score"].min(),
                           vmax=tr[f"{g}/composite_score"].max())
            ax.set_xticks(range(len(pv.columns)), [f"{c}s" for c in pv.columns])
            ax.set_yticks(range(len(pv.index)), [f"{i:g}" for i in pv.index])
            for i in range(pv.shape[0]):
                for j in range(pv.shape[1]):
                    ax.text(j, i, f"{pv.values[i, j]:.1f}", ha="center", va="center", fontsize=8, color="w")
            ax.set_title(f"{m}: composite ({g}), max over persistence")
            ax.set_xlabel("running average window")
            ax.set_ylabel("threshold")
            fig.colorbar(im, ax=ax)
        fig.tight_layout()
        figs[f"composite_{g}"] = fig
    # Type recall per fault type at the best (threshold, window) of each model.
    for m in a.models:
        best = tr[tr.model == m].iloc[0]
        e = ev[ev.trial == best.trial].set_index("fault_type")
        fig, ax = plt.subplots(figsize=(8, 4))
        e[["recall", "type_recall"]].plot.barh(ax=ax)
        ax.set_title(f"{m} best (thr {best.threshold:g}, {best.window_s}s, p {best.persistence_min:g} min): recall per fault type")
        ax.set_xlim(0, 1)
        fig.tight_layout()
        figs[f"per_type_{m}"] = fig
    with SummaryWriter(str(tb_root / "summary")) as tb:
        for k, fig in figs.items():
            fig.savefig(out / f"{k}.png", dpi=110)
            tb.add_figure(k, fig)
        for m in a.models:
            sub = tr[tr.model == m]
            for (w, pmin), s in sub.groupby(["window_s", "persistence_min"]):
                s = s.sort_values("threshold")
                for _, r in s.iterrows():
                    step = int(round(r.threshold * 100))
                    for k in ("composite_score", "event_f1", "alert_precision", "event_recall", "fault_type_recall",
                              "timeliness", "false_alerts_per_asset_day"):
                        tb.add_scalar(f"{m}_w{w}s_p{pmin:g}/{k}", r[f"all/{k}"], step)
                    for _, e in ev[ev.trial == r.trial].iterrows():
                        tb.add_scalar(f"{m}_w{w}s_p{pmin:g}_type_recall/{e.fault_type}", e.type_recall, step)
        tb.add_text("report", (out / "report.md").read_text() if (out / "report.md").exists() else "", 0)
    plt.close("all")

    # ------------------------------------------------------------------ report.md
    def fmt(v, nd=2):
        return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))

    L = [f"# Threshold and running-average study `{a.study}`", "",
         f"Created {time.strftime('%Y-%m-%d %H:%M %Z')} by `optimize/study.py`. Objective: organizer composite score on "
         "all 7 validation pumps (PUMP-08/09 and 5 generated pumps, 24 observable events). Selection and score use the "
         "same validation events, so the best values are optimistic.", "",
         "Models (frozen last checkpoints of experiment 6, round 3):", ""]
    for m, meta in study.user_attrs["models"].items():
        L.append(f"- {m}: `{meta['run']}` `{meta['checkpoint']}` (step {meta['step']}), {meta['minutes']} min context, "
                 f"predictions every {meta['stride_s']} s")
    L += ["", f"Fixed rules: {json.dumps(study.user_attrs['fixed_rules'])}. Persistence 0 min means one window. "
          "A running-average window shorter than the prediction stride holds one sample (the raw probability).", "",
          "## Top 10 settings", "",
          "| # | Model | Threshold | Window | Persistence | Composite all | 08/09 | val-new | F1 | Precision | Recall | Type recall | Timeliness | False alerts/day | Alerts |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, (_, r) in enumerate(tr.head(10).iterrows(), 1):
        L.append(f"| {i} | {r.model} | {r.threshold:g} | {r.window_s} s | {r.persistence_min:g} min | **{r['all/composite_score']:.1f}** | "
                 f"{r['val-orig/composite_score']:.1f} | {r['val-new/composite_score']:.1f} | {r['all/event_f1']:.2f} | "
                 f"{r['all/alert_precision']:.2f} | {r['all/event_recall']:.2f} | {r['all/fault_type_recall']:.2f} | "
                 f"{r['all/timeliness']:.2f} | {r['all/false_alerts_per_asset_day']:.2f} | {int(r['all/alerts_scored'])} |")
    L += ["", "## Reference: current submission rule on the same predictions", "",
          "Threshold 0.9, persistence 15 min, no running average (the rule of `submission/predictions_test.csv`).", "",
          "| Model | Composite all | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |",
          "|---|---|---|---|---|---|---|---|"]
    for m, r in ref.items():
        s = r["scalars"]
        L.append(f"| {m} | {s['all/composite_score']:.1f} | {s['val-orig/composite_score']:.1f} | "
                 f"{s['val-new/composite_score']:.1f} | {s['all/alert_precision']:.2f} | {s['all/event_recall']:.2f} | "
                 f"{s['all/fault_type_recall']:.2f} | {s['all/false_alerts_per_asset_day']:.2f} |")
    for m in a.models:
        sub = tr[tr.model == m]
        best = sub.iloc[0]
        L += ["", f"## Model {m}: best setting threshold {best.threshold:g}, window {best.window_s} s, persistence {best.persistence_min:g} min "
              f"(composite {best['all/composite_score']:.1f})", "", "### Composite (all pumps) by threshold and window (best persistence)", "",
              "| Threshold | " + " | ".join(f"{w} s" for w in WINDOWS_S) + " |", "|---" * (len(WINDOWS_S) + 1) + "|"]
        pv = sub.pivot_table(index="threshold", columns="window_s", values="all/composite_score", aggfunc="max")
        for thr, row in pv.iterrows():
            L.append(f"| {thr:g} | " + " | ".join(f"{row[w]:.1f}" for w in WINDOWS_S) + " |")
        PS = sorted(sub.persistence_min.unique())
        pp = sub.pivot_table(index="threshold", columns="persistence_min", values="all/composite_score", aggfunc="max")
        L += ["", "### Composite (all pumps) by threshold and persistence (best window)", "",
              "| Threshold | " + " | ".join(f"{p:g} min" for p in PS) + " |", "|---" * (len(PS) + 1) + "|"]
        for thr, row in pp.iterrows():
            L.append(f"| {thr:g} | " + " | ".join(f"{row[p]:.1f}" for p in PS) + " |")
        e = ev[ev.trial == best.trial].set_index("fault_type")
        al_b = al[al.trial == best.trial].set_index("fault_type")
        L += ["", "### Per fault type at the best setting", "",
              "Events: true events of the type. Alerts: scored bursts that name the type (correct = inside an event window of "
              "that type; wrong = inside the window of another type; outside = false alert).", "",
              "| Fault type | Events | Detected | Type correct | Timeliness | Median delay h | Alerts | Correct | Wrong | Outside | Window AUPRC |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        ap_m = auprc[(auprc.model == m) & (auprc.window_s == best.window_s)].set_index("fault_type").auprc
        for c in CLASSES:
            er = e.loc[c] if c in e.index else None
            ar = al_b.loc[c] if c in al_b.index else None
            L.append(f"| {c} | {int(er.events) if er is not None else 0} | {int(er.detected) if er is not None else '–'} | "
                     f"{int(er.type_correct) if er is not None else '–'} | {fmt(er.timeliness) if er is not None else '–'} | "
                     f"{fmt(er.median_delay_h, 1) if er is not None else '–'} | {int(ar.bursts) if ar is not None else 0} | "
                     f"{int(ar.correct_type) if ar is not None else 0} | {int(ar.wrong_type) if ar is not None else 0} | "
                     f"{int(ar.outside) if ar is not None else 0} | {fmt(ap_m.get(c, float('nan')), 3)} |")
    # Best setting per fault type (hint for per-class thresholds): type F1 from type recall and type precision.
    L += ["", "## Best setting for each fault type", "",
          "Type score = harmonic mean of type recall (events of the type detected with the correct type) and type precision "
          "(alert bursts that name the type and fall inside an event window of that type). Ties go to the higher "
          "threshold. A hint for per-class thresholds; few events per type, so the values are noisy.", "",
          "| Fault type | Events | Model | Threshold | Window | Type recall | Type precision | Type score | Outside alerts |",
          "|---|---|---|---|---|---|---|---|---|"]
    if len(ev) and len(al):
        j = ev.merge(al[["trial", "fault_type", "bursts", "correct_type", "outside", "type_precision"]],
                     on=["trial", "fault_type"], how="left").fillna({"bursts": 0, "correct_type": 0, "outside": 0,
                                                                      "type_precision": 0})
        j["type_score"] = np.where(j.type_recall + j.type_precision > 0,
                                   2 * j.type_recall * j.type_precision / (j.type_recall + j.type_precision), 0)
        j.to_csv(out / "per_type_joined.csv", index=False)
        for c in CLASSES:
            s = j[j.fault_type == c].sort_values(["type_score", "threshold", "window_s", "persistence_min"], ascending=[False, False, False, False])
            if not len(s):
                L.append(f"| {c} | 0 | – | – | – | – | – | – | – |")
                continue
            r = s.iloc[0]
            L.append(f"| {c} | {int(r.events)} | {r.model} | {r.threshold:g} | {r.window_s} s, p {r.persistence_min:g} min | {r.type_recall:.2f} | "
                     f"{r.type_precision:.2f} | {r.type_score:.2f} | {int(r.outside)} |")
    L += ["", "## Files", "",
          "- `trials.csv`: every trial with all organizer metrics per group (`all/`, `val-orig/`, `val-new/`).",
          "- `per_type_events.csv`, `per_type_alerts.csv`, `per_type_joined.csv`: per fault type for every trial.",
          "- `window_auprc.csv`: window-level AUPRC per model, window and fault type (independent of the threshold).",
          "- `alerts/`, `per_event/`: alert file (organizer format) and per-event scorer result of every trial.",
          "- `composite_*.png`, `per_type_*.png`: figures. TensorBoard: `optimize/tensorboard/" + a.study + "/`.",
          "- Optuna storage: `optimize/study.db` (study `" + a.study + "`)."]
    (out / "report.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()

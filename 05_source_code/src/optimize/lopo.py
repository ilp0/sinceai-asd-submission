"""Leave-one-pump-out (LOPO) estimate of the setting selection of a finished study.

    .venv/bin/python lopo.py --study persistence-v1 [--model 3h]

For each validation pump h: select the trial with the best composite on the other 6 pumps, and take the alerts of that
trial on pump h. The 7 held-out alert sets are scored together with the organizer scorer. This estimates the score of
"choose the setting on validation, then apply it to new pumps", which the best trial of the study overestimates.
With --model, only the trials of that model can be selected; without it, the model is selected too.
Inputs: results/<study>/trials.csv and results/<study>/alerts/<trial>.csv. Output: results/<study>/lopo[_<model>].json
and lopo[_<model>].md.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from alerts import Truth
from study import EXP

HERE = Path(__file__).resolve().parent
_T: dict = {}


def _init():
    _T["truth"] = Truth(EXP)


def _score(alerts: pd.DataFrame, keys: list[str]) -> dict:
    from retrofit_sim import scoring
    ev, assets, bn = _T["truth"].subset(keys)
    return scoring.score(alerts[alerts.asset_id.isin(set(assets.asset_id))], ev, assets, bn)


def fold_scores(job):
    """Composite of one trial on each 6-pump selection set."""
    trial, path, folds = job
    al = pd.read_csv(path)
    return trial, [_score(al, ks)["composite_score"] for ks in folds]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True)
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    out = HERE / "results" / a.study
    tr = pd.read_csv(out / "trials.csv")
    if a.model:
        tr = tr[tr.model == a.model]
    files = {int(f.name.split("_", 1)[0]): f for f in (out / "alerts").glob("*.csv")}
    _init()
    truth = _T["truth"]
    keys = sorted(truth.specs)
    folds = [[k for k in keys if k != h] for h in keys]
    params = [c for c in ("model", "threshold", "window_s", "persistence_min") if c in tr.columns]
    with ProcessPoolExecutor(a.workers, initializer=_init) as ex:
        sc = dict(ex.map(fold_scores, [(int(t), str(files[int(t)]), folds) for t in tr.trial], chunksize=4))
    held, rows = [], []
    for i, h in enumerate(keys):
        best = max(sc, key=lambda t: (sc[t][i], -t))
        r = tr[tr.trial == best].iloc[0]
        al = pd.read_csv(files[best])
        held.append(al[al.asset_id == truth.specs[h].asset_id])
        rows.append(dict(held_out=h, trial=int(best), selection_composite=round(sc[best][i], 2),
                         **{p: (r[p].item() if hasattr(r[p], "item") else r[p]) for p in params}))
    held = pd.concat(held, ignore_index=True)
    res = {g: {k: v for k, v in truth.score(held, g).items() if not isinstance(v, (list, dict))}
           for g in ("all", "val-orig", "val-new")}
    best_fit = tr.sort_values("all/composite_score", ascending=False).iloc[0]
    tag = f"_{a.model}" if a.model else ""
    held.to_csv(out / f"lopo{tag}_alerts.csv", index=False)
    (out / f"lopo{tag}.json").write_text(json.dumps(dict(folds=rows, scores=res, trials=len(tr),
                                                         best_fit={p: str(best_fit[p]) for p in params} |
                                                         {"composite": float(best_fit["all/composite_score"])}),
                                                    indent=1, default=str))
    L = [f"# Leave-one-pump-out: study `{a.study}`{' model ' + a.model if a.model else ''}", "",
         f"{len(tr)} trials can be selected. For each pump, the setting comes from the other 6 pumps. The grid itself "
         "(threshold, window and persistence values, the models) was designed after earlier studies on all 7 pumps, so "
         "this estimate is still a little optimistic.", "",
         "| Estimate | All 7 | 08/09 | val-new | Precision | Recall | Type recall | False alerts/day |",
         "|---|---|---|---|---|---|---|---|",
         f"| Best trial on all 7 (optimistic) | {best_fit['all/composite_score']:.1f} | {best_fit['val-orig/composite_score']:.1f} | "
         f"{best_fit['val-new/composite_score']:.1f} | {best_fit['all/alert_precision']:.2f} | {best_fit['all/event_recall']:.2f} | "
         f"{best_fit['all/fault_type_recall']:.2f} | {best_fit['all/false_alerts_per_asset_day']:.2f} |",
         f"| LOPO (held out) | **{res['all']['composite_score']:.1f}** | {res['val-orig']['composite_score']:.1f} | "
         f"{res['val-new']['composite_score']:.1f} | {res['all']['alert_precision']:.2f} | {res['all']['event_recall']:.2f} | "
         f"{res['all']['fault_type_recall']:.2f} | {res['all']['false_alerts_per_asset_day']:.2f} |", "",
         "Best trial on all 7: " + ", ".join(f"{p}={best_fit[p]}" for p in params), "",
         "| Held-out pump | Selected setting | Composite on the other 6 |", "|---|---|---|"]
    for r in rows:
        L.append(f"| {r['held_out']} | " + ", ".join(f"{p}={r[p]}" for p in params) + f" | {r['selection_composite']} |")
    (out / f"lopo{tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()

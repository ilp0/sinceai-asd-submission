"""Check the validation occlusion evidence against the organizer label evidence_channels, per event.

    python occlusion_check.py      # reads results/submission-fine/occlusion_validation.csv

Each validation alert is matched to an event of the same pump and fault type whose scoring window contains it. An
event counts as a hit for a method when the method's row is a label channel for the majority of the event's alerts.
COMMUNICATION_LOSS is left out: its label channel is "GATEWAY", which no sensor row can match.
Writes results/submission-fine/occlusion_validation_by_event.csv and prints a summary.
"""
from __future__ import annotations

import json

import pandas as pd

from alerts import PKG, scoring
from predict_test_fine import OUT_DIR


def main():
    occ = pd.read_csv(OUT_DIR / "occlusion_validation.csv")
    al = pd.read_csv(OUT_DIR / "predictions_validation.csv")
    ev = pd.read_csv(PKG / "data/full/events_validation.csv")
    assets = pd.read_csv(PKG / "data/full/assets.csv")
    we = dict(zip(assets.asset_id, scoring._ts(assets.window_end_utc)))
    ws = dict(zip(assets.asset_id, scoring._ts(assets.window_start_utc)))
    for c in ("onset_utc", "detectable_utc", "end_utc"):
        ev[c] = scoring._ts(ev[c])

    def window(e):
        s = max(e.onset_utc, ws[e.asset_id])
        if pd.notna(e.detectable_utc):
            s = max(s, e.detectable_utc - scoring.PRE_TOL)
        if pd.isna(e.end_utc):
            return s, we[e.asset_id]
        soft = e.fault_type in scoring.SOFT_END or e.event_class == "SENSOR"
        return s, min(e.end_utc + (scoring.POST_TOL if soft else pd.Timedelta(0)), we[e.asset_id])

    ev[["w_start", "w_end"]] = [window(e) for _, e in ev.iterrows()]
    rows = []
    for i, a in al.iterrows():
        t = pd.Timestamp(a.alert_time_utc)
        m = ev[(ev.asset_id == a.asset_id) & (ev.fault_type == a.fault_type) & (ev.w_start <= t) & (t <= ev.w_end)]
        if m.empty or a.fault_type == "COMMUNICATION_LOSS":
            continue
        e = m.iloc[0]
        labels = set(str(e.evidence_channels).split(","))
        o = occ[occ.alert == i]
        attn = str(a.evidence).split("strongest row ", 1)[1].split(";", 1)[0]
        top = o.loc[o["drop"].idxmax(), "row"]
        dec = o[o.decisive].sort_values("p_without").row.tolist()
        rows.append(dict(event_id=e.event_id, fault_type=a.fault_type, alert=i, labels=",".join(sorted(labels)),
                         attention_row=attn, attention_hit=attn in labels, top_drop_row=top, top_drop_hit=top in labels,
                         first_decisive=dec[0] if dec else "", decisive_hit=(dec[0] in labels) if dec else None))
    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "occlusion_validation_by_event.csv", index=False)
    by = df.groupby(["event_id", "fault_type"]).agg(
        alerts=("alert", "size"), attention=("attention_hit", "mean"), top_drop=("top_drop_hit", "mean"),
        decisive_alerts=("decisive_hit", lambda s: int(s.notna().sum())),
        decisive=("decisive_hit", lambda s: s.dropna().astype(float).mean() if s.notna().any() else float("nan")))
    print(by.round(2).to_string())
    summary = dict(events=len(by), alerts=len(df),
                   events_attention_majority=int((by.attention > 0.5).sum()),
                   events_top_drop_majority=int((by.top_drop > 0.5).sum()),
                   events_with_decisive=int(by.decisive.notna().sum()),
                   events_decisive_majority=int((by.decisive > 0.5).sum()))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

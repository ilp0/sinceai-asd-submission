"""Run every LLM call of the demo once and save the results for the static site.

For each pump and fault type (the first alert of that pair), this script runs the advice flow of `pipeline.py`
(writer -> checker -> retry -> summary only) and saves all its events. It also runs one test with a wrong
reference (shown with `?test=1`), and answers three prepared questions per pump and fault type.

Output: `site/data/guides.json` and `site/data/manual-<pump>.json`. Run `build_data.py` first.
The replies are also cached in `cache/llm_cache.json`, so a second run only calls the LLM for new prompts.

Run:  .venv/bin/python bake.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import llm
import manuals
import pipeline

HERE = Path(__file__).resolve().parent
DATA = HERE / "site" / "data"
PUMPS = ["PUMP-08", "PUMP-09"]
TEST_KEY = "PUMP-08|BEARING_WEAR"

QUESTIONS = {
    "SUCTION_STRAINER_CLOGGING": ["Can I clean the strainer while the pump runs?", "When must I clean the strainer?",
                                  "What do I check after I clean the strainer?"],
    "BEARING_WEAR": ["Which grease do I use, and how much?", "When must I replace the bearings?",
                     "What do I check after a bearing replacement?"],
    "COMMUNICATION_LOSS": ["Does this alert mean that the pump has a fault?", "What do I check at the pump?",
                           "How do I restart the gateway?"],
    "MISALIGNMENT": ["What are the alignment limits?", "Which vibration direction shows misalignment?",
                     "What torque do the foundation bolts need?"],
    "IMBALANCE": ["What causes imbalance?", "To which grade do I balance the impeller?", "Must I stop the pump now?"],
    "SENSOR_STUCK": ["How do I check the sensor?", "Can I disable the trip of this sensor?",
                     "What do I do until the sensor is repaired?"],
    "DISCHARGE_RESTRICTION": ["Which valves do I check?", "What is the minimum flow?",
                              "When do I change over to the standby pump?"],
    "AIR_ENTRAINMENT": ["How do I vent the pump?", "What causes air in the water?",
                        "What do I do if the pump loses its prime?"],
}
DEFAULT_Q = ["What do I check first?", "When must I stop the pump?", "Whom do I call?"]


def run_flow(alert: dict, inject: bool) -> list[dict]:
    return list(pipeline.run(alert, inject_fault=inject, use_cache=True))


def guide_text(events: list[dict]) -> str | None:
    final = next((e for e in events if e["stage"] == "final"), None)
    if not final or final["status"] != "accepted":
        return None
    g = final["guide"]
    return (f"{g['summary']}\n" + "\n".join(f"{i}. {a['text']} [{'], ['.join(a['citations'])}]"
                                            for i, a in enumerate(g["actions"], 1))
            + f"\nEscalate if: {g['escalate_if']['text']} [{'], ['.join(g['escalate_if']['citations'])}]")


def main():
    t0 = time.time()
    if not llm.health()["available"]:
        raise SystemExit(f"Ollama does not have {llm.CONFIG['model']}. Start Ollama first.")
    for p in PUMPS:
        (DATA / f"manual-{p}.json").write_text(json.dumps(manuals.load(p).to_json()))
    alerts = json.loads((DATA / "alerts.json").read_text())
    first: dict[str, dict] = {}
    for a in alerts:
        first.setdefault(f"{a['asset_id']}|{a['fault_type']}", a)

    out = {"llm": llm.CONFIG["label"], "model": llm.CONFIG["model"], "guides": {}, "test": {}, "questions": {}}
    for key, a in first.items():
        t = time.time()
        events = run_flow(a, inject=False)
        final = events[-1]
        out["guides"][key] = {"alert_id": a["id"], "events": events}
        print(f"{key}: {final.get('status', final['stage'])} after {final.get('attempts', '?')} tries, "
              f"{time.time() - t:.0f} s", flush=True)
        gt = guide_text(events)
        qa = []
        for q in QUESTIONS.get(a["fault_type"], DEFAULT_Q):
            ans = "".join(pipeline.ask(a, q, [], gt, use_cache=True)).strip()
            qa.append({"q": q, "a": ans})
        out["questions"][key] = qa
        print(f"  {len(qa)} questions answered", flush=True)

    a = first[TEST_KEY]
    events = run_flow(a, inject=True)
    out["test"][TEST_KEY] = {"alert_id": a["id"], "events": events}
    print(f"test {TEST_KEY}: {events[-1].get('status')} after {events[-1].get('attempts')} tries", flush=True)

    out["made"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (DATA / "guides.json").write_text(json.dumps(out, indent=1))
    print(f"done in {time.time() - t0:.0f} s -> {DATA / 'guides.json'}")


if __name__ == "__main__":
    main()

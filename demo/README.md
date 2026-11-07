# RETROFIT AI live demo

Replay of two validation pumps (PUMP-08 and PUMP-09, 7 days each) with the submitted model and alert rule. A local LLM wrote advice from the pump manual, and a second call of the same LLM checked every manual reference. Only checked advice is shown.

The demo is a **static HTML/JS package** (`site/`). All model and LLM results were made one time and saved as JSON. The page makes no model or LLM calls, so any static web server can serve it.

## Run

```sh
./run.sh        # http://127.0.0.1:8797 (python3 -m http.server in site/)
```

Press `space` to play or pause. The replay stops at a new alert of the pump on screen and opens it in the alert list. An alert of the other pump goes into the list, and the replay continues. Click an alert to open or close it. **Acknowledge** closes the alert and continues the replay. Repeat alerts of the same pump and fault type (12 h cooldown) go to the alert list without a stop, with the advice of the first alert.

URL options for the recording:

| Option | Effect |
|---|---|
| `?test=1` | Shows the saved test run for PUMP-08 bearing wear: one reference of the first draft was changed to a wrong clause, the checker rejected it, and the writer wrote the advice again. The checker also rejected try 2 (escalation step), so the alert shows the summary only. |
| `?pause=0` | Does not stop at alerts. |

## Make the data again

1. `build_data.py` (no LLM): reads the 10 s window probabilities of the submitted model (`rp3-3h-r32-v1`, `checkpoint_last_step11500`) on PUMP-08/09, and makes the alerts with `fast_alerts` from `05_source_code/src/optimize/alerts.py` and the `RULE` of `05_source_code/src/optimize/predict_test_fine.py` (threshold 0.9 for 15 min, 12 h cooldown, 10 s steps). It stops if the alerts differ from `05_source_code/src/optimize/results/submission-fine/predictions_validation.csv` (25 alerts).
2. `bake.py` (needs Ollama with `hf.co/unsloth/Qwen3.5-4B-GGUF:Q8_0`): runs the advice flow once for the first alert of each pump and fault type, one test run with a wrong reference, and three prepared questions per pump and fault type. It writes `site/data/guides.json` and the manuals. Replies are cached in `cache/llm_cache.json`.

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python build_data.py
.venv/bin/python bake.py
```

## LLM flow (`pipeline.py`)

1. The fault type of the alert selects the manual sections (`manuals.FAULT_SECTIONS`).
2. Writer call: alert data and these sections in, advice out (JSON schema: summary, 3–5 actions with clause references, escalation).
3. Checker call (same model, same sections): one verdict per step (JSON schema). The code also rejects a clause number that is not in the given sections.
4. All steps supported: the advice is shown. Not supported: back to step 2 with the reasons. Two rejections: the LLM writes only a summary of the alert and the values, without advice.
5. Prepared questions: the same model with the full manual, the alert and the approved advice. References in the answer link to the manual clause.

## Files

| File | Purpose |
|---|---|
| `site/` | The static page (`index.html`, `app.js`, `style.css`, `data/`). No external libraries. |
| `build_data.py`, `bake.py` | Make `site/data/` (see above). |
| `manuals/PUMP-08.md`, `manuals/PUMP-09.md` | Demo manuals with numbered clauses. The team wrote them from the organizer asset table. They are not manufacturer documents. |
| `pipeline.py`, `llm.py`, `manuals.py` | LLM flow, Ollama client with reply cache, manual parser. Used only by `bake.py`. |

Data: "RETROFIT AI 2026 synthetic pump benchmark, Since AI Hackathon 2026" (CC BY 4.0). All data are synthetic.

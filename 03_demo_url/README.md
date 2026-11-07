# Demo URL

**https://sinceai-asd-submission.0m.fi** (form value: `demo_url.txt`)

The live demo replays two validation pumps (PUMP-08 and PUMP-09, 7 days each) with the submitted model and alert rule. It shows the alerts, the fault probabilities, the sensor signals and the advice from the pump manual that a second LLM call checked. All model and LLM results were made one time and saved, so the page makes no model or LLM calls.

## Use

- Press **▶ Play** or `space` to start or pause the replay.
- The replay stops at a new alert of the pump on screen and opens it. Click a manual reference (for example `§4.3`) to see the clause.
- **Acknowledge** closes the alert and continues the replay.
- URL options: `?test=1` shows the saved test run with a wrong manual reference that the checker rejected. `?pause=0` does not stop at alerts.

## Source and hosting

- Source: `demo/site/` in this package (static HTML/JS, no external libraries). See `demo/README.md`.
- Hosting: nginx container on a K3s server, HTTPS with Let's Encrypt. Online since 2026-11-07.

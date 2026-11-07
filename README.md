# RETROFIT AI — Make Existing Machines Intelligent

Our submission to the Business Turku challenge at the Since AI Hackathon 2026 (Turku, 6–8 November 2026).

## The challenge

Factories, vessels and smaller industrial sites operate machines that work well but cannot tell their condition or warn operators before a problem becomes a failure. Business Turku asks teams to add this intelligence to existing machines without a replacement of the equipment. The solution must find emerging faults early, show evidence that operators can trust, and turn complex sensor signals into clear recommendations. The data is 1 Hz telemetry from industrial pumps, and the organizer scorer rewards early, correct and causal alerts with the correct fault type and few false alerts.

## Our approach

We use Timestral-28M, a pretrained time-series foundation model, as the backbone. We removed its forecast head and trained a new multi-label fault head that gives one probability for each of the 13 fault types. The backbone reads a 3 h window of pump telemetry, and LoRA adapters (rank 32) fine-tune its attention layers. Class attention pooling lets each fault type look at the sensors that matter for it. For each alert, a sensor-removal test (occlusion) shows the operator which signals the model's alert depends on. A causal alert rule (probability ≥ 0.9 for 15 minutes, with a cooldown) changes the probabilities into alerts. On the validation pumps, this method scored 81.8 against 65.6 for the organizer baseline; the leave-one-pump-out estimate for new pumps is 77.6.

The trained weights of the submitted model (LoRA adapters, query token and fault head: 1 419 213 values, 5.7 MB) are in [`05_source_code/model/`](05_source_code/model/), with a script that makes the full checkpoint from them and the public Timestral-28M weights. The weights are under the Timestral-28M licence (Modified MIT License, Mistral AI).

## Test predictions (the file to submit)

[`predictions_test.csv`](predictions_test.csv) is the alert file for the test pumps, in the format of the organizer file `submission_template/predictions_template.csv`. It has 34 alerts: PUMP-10 (9), PUMP-11 (10) and PUMP-12 (15); 30 MACHINE and 4 SENSOR. It is identical to `05_source_code/predictions/predictions_test.csv`, where the method, the frozen alert rule and the validation scores are described.

Checked on 8 November 2026: the organizer loader reads it without errors; all fault types are in the taxonomy; the class agrees with the fault type; every alert is inside the pump window and after the first 24 h; no burst mixes fault types. The frozen rule, applied again to the saved test probabilities, gives the same 34 rows. SHA-256: `a1aee9f0862fb35badaa211d6c1ce61086edd29fde767d9738c57cbb1e7db1e3`.

## Package layout

One directory for each field of the submission form:

| Directory | Form field | Required |
|---|---|---|
| `01_project_text/` | Project name, tagline (≤ 140 characters), about text (≤ 5000 characters), built with | Yes |
| `02_repository/` | Repository link | Yes |
| `03_demo_url/` | Demo URL | No |
| `04_demo_video/` | Demo video (YouTube link or MP4/WebM, under 2 minutes) | Yes |
| `05_source_code/` | Source code `.zip` at the deadline, without dependencies and data | Yes |
| `06_pitch_deck/` | Pitch deck (PDF or PowerPoint) | Yes |

We do not submit the two optional fields "Supporting document" (pilot or continuation plan) and "Partner technologies".

`demo/` is the source of the live demo (see `03_demo_url/README.md` and `demo/README.md`).

Submission deadline: **Sunday 8 November 2026, 10:00 (Helsinki time)**.

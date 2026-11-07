#!/bin/bash
# On the pod: one JSON line per run with the last step, process state and the last evaluation.
cd /root/exp6/data_analysis_experiment_6_model
python - <<'PY'
import json, subprocess
from pathlib import Path
for d in sorted(Path("runs").glob("rp*-*")):
    h = [json.loads(l) for l in (d / "history.jsonl").read_text().splitlines()] if (d / "history.jsonl").exists() else []
    ev = [r for r in h if "bench_all/composite_max" in r]
    alive = subprocess.run(["pgrep", "-f", f"^python run.py train --config configs/{d.name.rsplit('-v', 1)[0]}.yaml"], capture_output=True).returncode == 0
    s = json.loads((d / "summary.json").read_text()) if (d / "summary.json").exists() else {}
    print(json.dumps(dict(run=d.name, step=h[-1]["step"] if h else 0, alive=alive, completed=s.get("completed", False),
                          step_s=round(sum(r.get("time/step_seconds", 0) for r in h[-50:]) / max(1, len(h[-50:])), 3),
                          last_eval=None if not ev else {k: round(v, 3) for k, v in ev[-1].items()
                                                         if k in ("step", "time/eval_seconds", "val/macro_auprc")
                                                         or k.startswith("bench_all/composite")})))
PY
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader

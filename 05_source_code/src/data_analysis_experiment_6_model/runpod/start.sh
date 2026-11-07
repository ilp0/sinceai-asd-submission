#!/bin/bash
# On the pod: start the training of one config in the background unless it runs or is complete.
#   bash runpod/start.sh configs/rp-3h-r32.yaml
# Prints one JSON line: {"run": ..., "state": "started|running|completed", "step": N}
set -euo pipefail
cd /root/exp6/data_analysis_experiment_6_model
cfg=$1
run=$(python -c "import sys; sys.path.insert(0,'.'); from mlhead.config import load_config; print(load_config('$cfg')['run']['name'])")
mkdir -p logs "runs/$run"
step=$( (tail -n 1 "runs/$run/history.jsonl" 2>/dev/null || true) | python -c "import json,sys; l=sys.stdin.read().strip(); print(json.loads(l)['step'] if l else 0)")
# One start check at a time per run (two lr items can call this script at the same moment).
exec 9>"runs/$run/.start.lock"
flock 9
if python -c "import json,sys; sys.exit(0 if json.load(open('runs/$run/summary.json')).get('completed') else 1)" 2>/dev/null; then
  state=completed
elif pgrep -f "^python run.py train --config $cfg" >/dev/null; then
  state=running
else
  export OMP_NUM_THREADS=4 PYTHONUNBUFFERED=1 MLHEAD_SAVE_PREDICTIONS=1
  ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)"
  setsid nohup python run.py train --config "$cfg" >> "logs/$run.log" 2>&1 < /dev/null 9>&- &
  state=started
  sleep 2
fi
echo "{\"run\": \"$run\", \"state\": \"$state\", \"step\": $step}"

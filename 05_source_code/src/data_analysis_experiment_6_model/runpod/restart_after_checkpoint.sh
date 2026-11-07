#!/bin/bash
# On the pod: stop each training run just after its next checkpoint (step % 250 in 1..20), so that the
# lr job restarts it on the current code and loses at most 20 steps. Runs in the background:
#   nohup bash runpod/restart_after_checkpoint.sh > logs/restart.log 2>&1 &
cd /root/exp6/data_analysis_experiment_6_model
declare -A done_
for i in $(seq 1 1800); do
  left=0
  for h in runs/rp-*/history.jsonl; do
    run=$(basename "$(dirname "$h")"); [[ -n "${done_[$run]:-}" ]] && continue
    [[ -f "runs/$run/summary.json" ]] && { done_[$run]=1; continue; }
    left=1
    step=$(tail -n 1 "$h" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['step'])")
    if (( step % 250 >= 1 && step % 250 <= 20 )); then
      pkill -f "^python run.py train --config configs/${run%-v1}.yaml" && echo "$(date +%T) stopped $run at step $step"
      done_[$run]=1
    fi
  done
  (( left )) || break
  sleep 2
done
echo "$(date +%T) finished"

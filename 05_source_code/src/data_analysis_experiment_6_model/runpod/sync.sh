#!/bin/bash
# Copy code, base model, scorer and experiment-6 data to one pod, in the repository-relative layout
# that the configuration paths expect. Run from anywhere on the Mac:  runpod/sync.sh 3h
# Never copied: PUMP-10..12 telemetry, gen-test data, caches, runs, the RunPod API key.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)          # experiment folder
REPO=$(cd "$HERE/.." && pwd)
POD=$1
REMOTE=/root/exp6
PKG=raw/BusinessTurku_SinceAI2026_FINAL_BUILDER_PUBLISH/RETROFIT_AI_PARTICIPANTS_2026
RSH="$HERE/runpod/ssh.sh $POD"
"$HERE/runpod/ssh.sh" "$POD" "mkdir -p $REMOTE/$PKG/data $REMOTE/data_analysis_experiment_2_lora $REMOTE/data_analysis_expriment_1/outputs $REMOTE/data_analysis_experiment_6_model"
rsync -a --delete -e "$RSH" --exclude cache --exclude 'cache-*' --exclude runs --exclude logs --exclude __pycache__ \
  --exclude .pytest_cache --exclude .runpod-apikey --exclude runpod/pods.json --exclude runpod/known_hosts --exclude '*.tmp' \
  "$HERE/" "pod:$REMOTE/data_analysis_experiment_6_model/"
rsync -a -e "$RSH" --exclude __pycache__ "$REPO/data_analysis_experiment_2_lora/base_model" "$REPO/data_analysis_experiment_2_lora/vendor" \
  "pod:$REMOTE/data_analysis_experiment_2_lora/"
rsync -a -e "$RSH" --exclude __pycache__ "$REPO/$PKG/src" "pod:$REMOTE/$PKG/"
rsync -a -e "$RSH" --exclude 'telemetry/asset_id=PUMP-1[0-2]' "$REPO/$PKG/data/full" "pod:$REMOTE/$PKG/data/"
rsync -a -e "$RSH" "$REPO/data_analysis_expriment_1/outputs/alerts_causal_B1.csv" "pod:$REMOTE/data_analysis_expriment_1/outputs/"
"$HERE/runpod/ssh.sh" "$POD" "du -sh $REMOTE | tail -1; ls $REMOTE/$PKG/data/full/telemetry | tr '\n' ' '"

#!/bin/bash
# On the pod: Python packages, GPU check, TensorBoard on loopback, cost guard. Idempotent.
#   bash runpod/setup.sh <guard_hours>
set -euo pipefail
cd /root/exp6/data_analysis_experiment_6_model
mkdir -p logs runs
python -c "import torch; assert torch.cuda.is_available(); print('torch', torch.__version__, torch.cuda.get_device_name(), 'cuda', torch.version.cuda)"
PKGS="pandas pyarrow pyyaml scipy safetensors tensorboard pytest huggingface_hub"
python -c "import pandas, pyarrow, yaml, scipy, safetensors, tensorboard, pytest, huggingface_hub" 2>/dev/null \
  || pip install -q $PKGS 2>&1 | tail -2 || pip install -q --break-system-packages $PKGS 2>&1 | tail -2
python -c "import pandas, pyarrow, yaml, scipy, safetensors, tensorboard, pytest, huggingface_hub; print('packages ok')"
# TensorBoard: loopback only; the Mac reaches it through an SSH forward.
if ! pgrep -f "tensorboard --logdir runs" >/dev/null; then
  nohup tensorboard --logdir runs --host 127.0.0.1 --port 6006 --reload_interval 30 > logs/tensorboard.log 2>&1 &
fi
# Cost guard: the pod stops itself after <guard_hours> from the first setup (if runpodctl and a pod key exist).
hours=${1:-3.5}
if [[ ! -f logs/guard.started ]]; then
  date -u +%FT%TZ > logs/guard.started
  if command -v runpodctl >/dev/null && [[ -n "${RUNPOD_POD_ID:-}" ]]; then
    nohup bash -c "sleep \$(python -c 'print(int($hours*3600))'); runpodctl stop pod $RUNPOD_POD_ID" > logs/guard.log 2>&1 &
    echo "guard: pod stops itself after $hours h"
  else
    echo "guard: runpodctl or RUNPOD_POD_ID missing; the Mac-side guard is necessary"
  fi
fi
nproc; free -g | head -2; df -h /root | tail -1
touch .ready

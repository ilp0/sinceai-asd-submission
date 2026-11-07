#!/bin/bash
# SSH to one experiment-6 pod (name from runpod/pods.json) with the pod-only key and pinned host keys.
#   runpod/ssh.sh 3h 'nvidia-smi'
#   SSH_OPTS='-N -L 127.0.0.1:16006:127.0.0.1:6006' runpod/ssh.sh 3h      (TensorBoard tunnel)
#   rsync -e "runpod/ssh.sh 3h" src/ pod:/root/exp6/...      (rsync adds the host "pod"; it is dropped)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
pod=$1; shift
[[ "${1:-}" == pod ]] && shift
ep=$(python3 -c "import json,sys; d=json.load(open('$HERE/pods.json'))['$pod']; print(d['host'], d['port'])")
read -r host port <<<"$ep"
exec /usr/bin/ssh -i "$HOME/.ssh/id_ed25519_runpod" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=20 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=4 -o UserKnownHostsFile="$HERE/known_hosts" \
  -o StrictHostKeyChecking=accept-new ${SSH_OPTS:-} -p "$port" "root@$host" "$@"

"""RunPod pod control for experiment 6 (Mac side, Python stdlib only).

    python3 runpod/pods.py create <name> [--gpu "NVIDIA A100-SXM4-80GB"]   # one secure-cloud pod, SSH only
    python3 runpod/pods.py list                                           # pods of this account + cost/h
    python3 runpod/pods.py refresh                                        # update SSH host/port in pods.json
    python3 runpod/pods.py stop <name>|--all                              # stop (no GPU charge, disk kept)
    python3 runpod/pods.py terminate <name>|--all                         # delete pod and its disk
    python3 runpod/pods.py balance
    python3 runpod/pods.py guard --hours 3.5                              # stop each pod <hours> after creation

The API key is read from ../.runpod-apikey (never printed). The pod-only SSH public key
~/.ssh/id_ed25519_runpod.pub goes to the pod in the PUBLIC_KEY environment variable, so the account
settings stay unchanged. runpod/pods.json (git-ignored) maps pod name -> id, SSH host and port.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
KEY_FILE = EXP / ".runpod-apikey"
PODS = HERE / "pods.json"
PUBKEY = Path.home() / ".ssh/id_ed25519_runpod.pub"
IMAGE = "runpod/pytorch:2.0.0-cu1281-torch2130-ubuntu2404"
GPU = "NVIDIA A100-SXM4-80GB"
PREFIX = "exp6-"                     # every pod of this experiment has this name prefix


def gql(query: str, variables: dict | None = None) -> dict:
    key = KEY_FILE.read_text().strip()
    req = urllib.request.Request(
        "https://api.runpod.io/graphql", data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "exp6-client"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    if d.get("errors"):
        raise RuntimeError(json.dumps(d["errors"])[:2000])
    return d["data"]


def load() -> dict:
    return json.loads(PODS.read_text()) if PODS.exists() else {}


def save(d: dict) -> None:
    tmp = PODS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1))
    tmp.replace(PODS)


POD_FIELDS = """id name desiredStatus costPerHr gpuCount vcpuCount memoryInGb machine { gpuDisplayName }
  runtime { uptimeInSeconds ports { ip isIpPublic privatePort publicPort type } }"""


def my_pods() -> list[dict]:
    return [p for p in gql(f"query {{ myself {{ pods {{ {POD_FIELDS} }} }} }}")["myself"]["pods"]
            if p["name"].startswith(PREFIX)]


def ssh_endpoint(p: dict):
    for port in ((p.get("runtime") or {}).get("ports") or []):
        if port["privatePort"] == 22 and port["isIpPublic"] and port["type"] == "tcp":
            return port["ip"], port["publicPort"]
    return None


def public_keys() -> str:
    """The Mac pod-only key plus the ilpo-dev pod-only key (runpod/ilpo-dev.pub), one per line."""
    keys = [PUBKEY.read_text().strip()]
    extra = HERE / "ilpo-dev.pub"
    if extra.exists():
        keys.append(extra.read_text().strip())
    return "\n".join(keys)


def create(name: str, gpu: str, disk_gb: int, min_vcpu: int) -> None:
    full = PREFIX + name
    if any(p["name"] == full for p in my_pods()):
        raise SystemExit(f"pod {full} exists already")
    inp = dict(cloudType="SECURE", gpuCount=1, gpuTypeId=gpu, name=full, imageName=IMAGE,
               containerDiskInGb=disk_gb, volumeInGb=0, minVcpuCount=min_vcpu, minMemoryInGb=60,
               ports="22/tcp", startSsh=True, supportPublicIp=True,
               allowedCudaVersions=["12.8", "12.9", "13.0", "13.1", "13.2"],
               env=[dict(key="PUBLIC_KEY", value=public_keys())])
    d = gql("mutation($i: PodFindAndDeployOnDemandInput) { podFindAndDeployOnDemand(input: $i) "
            "{ id name costPerHr machine { gpuDisplayName } } }", {"i": inp})["podFindAndDeployOnDemand"]
    pods = load()
    pods[name] = dict(id=d["id"], gpu=d["machine"]["gpuDisplayName"], cost_per_hr=d["costPerHr"],
                      created=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    save(pods)
    print(json.dumps(pods[name]))
    refresh(wait_s=600)


def refresh(wait_s: int = 0) -> None:
    t0 = time.time()
    while True:
        pods, live = load(), {p["id"]: p for p in my_pods()}
        missing = []
        for name, rec in pods.items():
            p = live.get(rec["id"])
            rec["status"] = p["desiredStatus"] if p else "GONE"
            ep = ssh_endpoint(p) if p else None
            if ep:
                rec["host"], rec["port"] = ep
            elif rec["status"] == "RUNNING":
                missing.append(name)
        save(pods)
        if not missing or time.time() - t0 > wait_s:
            break
        time.sleep(10)
    print(json.dumps({n: {k: r.get(k) for k in ("status", "host", "port", "gpu")} for n, r in pods.items()}))


def act(action: str, target: str) -> None:
    pods = load()
    names = list(pods) if target == "--all" else [target]
    for n in names:
        pid = pods[n]["id"]
        if action == "stop":
            gql("mutation($i: PodStopInput!) { podStop(input: $i) { id desiredStatus } }", {"i": {"podId": pid}})
        else:
            gql("mutation($i: PodTerminateInput!) { podTerminate(input: $i) }", {"i": {"podId": pid}})
        pods[n]["status"] = "EXITED" if action == "stop" else "TERMINATED"
        pods[n][action + "ped_at" if action == "stop" else "terminated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        print(f"{action} {n} ({pid})")
    save(pods)


def guard(hours: float) -> None:
    """Cost guard (runs in the background on the Mac): every 60 s, stop each pod that is older than
    `hours` since its creation. Exits when no pod of pods.json is RUNNING any more."""
    import datetime as dt
    while True:
        try:
            pods, live = load(), {p["id"]: p for p in my_pods()}
        except Exception as e:          # DNS / network / API error: try again next minute, do not exit
            print(f"guard: API error {type(e).__name__}: {str(e)[:200]}; retry in 60 s", flush=True)
            time.sleep(60)
            continue
        running = 0
        for name, rec in pods.items():
            p = live.get(rec["id"])
            if not p or p["desiredStatus"] != "RUNNING":
                continue
            running += 1
            age_h = (dt.datetime.now(dt.timezone.utc) - dt.datetime.strptime(rec["created"], "%Y-%m-%dT%H:%M:%S%z")).total_seconds() / 3600
            if age_h > hours:
                act("stop", name)
                print(f"guard: stopped {name} after {age_h:.2f} h", flush=True)
        if not running and pods:
            print("guard: no running pod; exit", flush=True)
            return
        time.sleep(60)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["create", "list", "refresh", "stop", "terminate", "balance", "guard"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--gpu", default=GPU)
    ap.add_argument("--disk", type=int, default=60)
    ap.add_argument("--min-vcpu", type=int, default=16)
    ap.add_argument("--hours", type=float, default=3.5)
    a = ap.parse_args()
    if a.action == "create":
        create(a.name, a.gpu, a.disk, a.min_vcpu)
    elif a.action == "list":
        for p in my_pods():
            print(json.dumps({k: p[k] for k in ("id", "name", "desiredStatus", "costPerHr", "vcpuCount", "memoryInGb")}
                             | {"gpu": (p.get("machine") or {}).get("gpuDisplayName"),
                                "uptime_h": round(((p.get("runtime") or {}).get("uptimeInSeconds") or 0) / 3600, 2)}))
    elif a.action == "refresh":
        refresh()
    elif a.action == "guard":
        guard(a.hours)
    elif a.action == "balance":
        print(json.dumps(gql("query { myself { clientBalance currentSpendPerHr } }")["myself"]))
    else:
        if not a.name:
            sys.exit("name or --all required")
        act(a.action, a.name)


if __name__ == "__main__":
    main()

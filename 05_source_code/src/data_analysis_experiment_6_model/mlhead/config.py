"""YAML configuration with `inherit:` chains and `--set a.b=value` overrides."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent


def _merge(base: dict, over: dict) -> dict:
    """Deep merge: dictionaries merge key by key, every other value (lists too) replaces."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load(path: Path, seen: tuple = ()) -> dict:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"inherit cycle at {path}")
    data = yaml.safe_load(path.read_text()) or {}
    parent = data.pop("inherit", None)
    if parent:
        data = _merge(_load(path.parent / parent, seen + (path,)), data)
    return data


def apply_override(cfg: dict, assignment: str) -> None:
    key, _, raw = assignment.partition("=")
    if not _:
        raise ValueError(f"override must be key=value, got {assignment!r}")
    node = cfg
    parts = key.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = yaml.safe_load(raw)


def load_config(path: str | Path, overrides: list[str] | None = None) -> dict:
    cfg = _load(Path(path))
    for o in overrides or []:
        apply_override(cfg, o)
    cfg["_config_path"] = str(Path(path).resolve())
    return cfg


def resolve(p: str | Path) -> Path:
    """Paths in the configuration are relative to the experiment directory."""
    p = Path(p).expanduser()
    return p if p.is_absolute() else (EXPERIMENT_DIR / p).resolve()


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def data_fingerprint(cfg: dict) -> str:
    """Everything that changes the cached arrays (not the model or training settings)."""
    keep = {k: cfg["input"][k] for k in ("sample_period_s", "channels", "derived", "normalization")}
    keep["labels"] = cfg["labels"]
    keep["sources"] = cfg["data"]["sources"]
    return fingerprint(keep)

"""Small Ollama client with a reply cache on disk."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Iterator

import httpx

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / "config.json").read_text())["llm"]
CACHE_FILE = HERE / "cache" / "llm_cache.json"
_lock = threading.Lock()


def _key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def _cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _cache_put(key: str, value: str) -> None:
    with _lock:
        c = _cache()
        c[key] = value
        CACHE_FILE.parent.mkdir(exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, indent=1))
        tmp.replace(CACHE_FILE)


def _body(messages: list[dict], schema: dict | None, stream: bool, think: bool, max_tokens: int, seed: int = 7) -> dict:
    body = {
        "model": CONFIG["model"], "messages": messages, "stream": stream, "think": think,
        "keep_alive": "60m",
        "options": {"temperature": CONFIG.get("temperature", 0), "num_ctx": CONFIG.get("num_ctx", 16384),
                    "num_predict": max_tokens, "seed": seed},
    }
    if schema:
        body["format"] = schema
    return body


def chat_json(messages: list[dict], schema: dict, use_cache: bool = True, think: bool = False,
              max_tokens: int = 900) -> tuple[dict, dict]:
    """One structured call. Returns (parsed JSON, meta with ms / cached / tokens)."""
    key = _key(_body(messages, schema, False, think, max_tokens))
    if use_cache and (hit := _cache().get(key)):
        return json.loads(hit), {"cached": True, "ms": 0}
    t = time.perf_counter()
    for seed in (7, 8):  # a second seed if the first reply is not valid JSON (for example a cut-off loop)
        body = _body(messages, schema, False, think, max_tokens, seed)
        r = httpx.post(f"{CONFIG['url']}/api/chat", json=body, timeout=httpx.Timeout(300, connect=5))
        r.raise_for_status()
        d = r.json()
        text = d["message"]["content"]
        try:
            parsed = json.loads(text)
            break
        except json.JSONDecodeError:
            continue
    else:
        raise ValueError("The model did not return valid JSON")
    _cache_put(key, text)
    return parsed, {"cached": False, "ms": round((time.perf_counter() - t) * 1000),
                    "tokens": d.get("eval_count")}


def chat_stream(messages: list[dict], use_cache: bool = True, max_tokens: int = 600) -> Iterator[str]:
    body = _body(messages, None, True, False, max_tokens)
    key = _key(body)
    if use_cache and (hit := _cache().get(key)):
        yield hit
        return
    parts: list[str] = []
    with httpx.stream("POST", f"{CONFIG['url']}/api/chat", json=body, timeout=httpx.Timeout(300, connect=5)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line and (chunk := json.loads(line).get("message", {}).get("content", "")):
                parts.append(chunk)
                yield chunk
    _cache_put(key, "".join(parts))


def health() -> dict:
    try:
        tags = httpx.get(f"{CONFIG['url']}/api/tags", timeout=3).json()
        ok = any(m["name"] == CONFIG["model"] for m in tags.get("models", []))
    except httpx.HTTPError:
        ok = False
    return {"model": CONFIG["model"], "available": ok}


def warm() -> None:
    try:
        httpx.post(f"{CONFIG['url']}/api/generate", json={"model": CONFIG["model"], "keep_alive": "60m"}, timeout=120)
    except httpx.HTTPError:
        pass

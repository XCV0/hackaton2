"""LLM gateway. Key, base URL, protocol and model are configured from the admin UI and stored
locally in the settings table (never exported, never logged). Default gateway: AgentRouter.

Supported protocols:
  openai     POST {base}/v1/chat/completions   (OpenAI-compatible: AgentRouter, OpenRouter, vLLM ...)
  anthropic  POST {base}/v1/messages           (Anthropic-compatible)
"""
from __future__ import annotations

import base64
import json
import re
import time

import httpx

from . import db

DEFAULTS = {
    "base_url": "https://agentrouter.org",
    "protocol": "openai",
    "api_key": "",
    "model_a": "",
    "model_b": "",
    "model_c": "",
    "model_vision": "",
    "temperature": 0.0,
    "max_tokens": 8000,
    "timeout_s": 240,
    "price_in_per_mtok": 0.0,
    "price_out_per_mtok": 0.0,
}


class LLMError(RuntimeError):
    pass


def config() -> dict:
    cfg = dict(DEFAULTS)
    cfg.update(db.get_setting("llm", {}) or {})
    return cfg


def public_config() -> dict:
    cfg = config()
    key = cfg.pop("api_key", "")
    cfg["api_key_set"] = bool(key)
    cfg["api_key_hint"] = (key[:4] + "…" + key[-4:]) if len(key) > 10 else ("set" if key else "")
    return cfg


def save_config(update: dict) -> dict:
    cfg = config()
    for k, v in update.items():
        if k not in DEFAULTS:
            continue
        if k == "api_key" and (v is None or v == ""):
            continue  # keep existing key unless explicitly replaced
        cfg[k] = v
    if update.get("clear_key"):
        cfg["api_key"] = ""
    db.set_setting("llm", cfg)
    return public_config()


def available() -> bool:
    c = config()
    return bool(c["api_key"] and c["model_a"])


def _base(cfg) -> str:
    b = cfg["base_url"].rstrip("/")
    return b[:-3] if b.endswith("/v1") else b


def _headers(cfg) -> dict:
    if cfg["protocol"] == "anthropic":
        return {"x-api-key": cfg["api_key"], "authorization": f"Bearer {cfg['api_key']}",
                "anthropic-version": "2023-06-01", "content-type": "application/json"}
    return {"authorization": f"Bearer {cfg['api_key']}", "content-type": "application/json"}


def list_models() -> list[str]:
    cfg = config()
    if not cfg["api_key"]:
        raise LLMError("API key is not set")
    r = httpx.get(_base(cfg) + "/v1/models", headers=_headers(cfg), timeout=30)
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    items = data.get("data", data if isinstance(data, list) else [])
    return sorted({m.get("id") for m in items if isinstance(m, dict) and m.get("id")})


def chat(model: str, system: str, user: str, *, images: list[bytes] | None = None, json_mode: bool = True,
         max_tokens: int | None = None) -> dict:
    """Single call. Returns {text, tokens_in, tokens_out, seconds, model, params}."""
    cfg = config()
    if not cfg["api_key"]:
        raise LLMError("API key is not set (Admin → LLM)")
    if not model:
        raise LLMError("model is not selected (Admin → LLM)")
    params = {"temperature": cfg["temperature"], "max_tokens": max_tokens or cfg["max_tokens"], "protocol": cfg["protocol"],
              "base_url": _base(cfg)}
    t0 = time.time()
    if cfg["protocol"] == "anthropic":
        content = []
        for img in images or []:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.b64encode(img).decode()}})
        content.append({"type": "text", "text": user})
        body = {"model": model, "system": system, "max_tokens": params["max_tokens"], "temperature": params["temperature"],
                "messages": [{"role": "user", "content": content}]}
        url = _base(cfg) + "/v1/messages"
    else:
        if images:
            content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(i).decode()}} for i in images]
        else:
            content = user
        body = {"model": model, "temperature": params["temperature"], "max_tokens": params["max_tokens"],
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        url = _base(cfg) + "/v1/chat/completions"
    last = None
    for attempt in range(3):
        try:
            r = httpx.post(url, headers=_headers(cfg), json=body, timeout=cfg["timeout_s"])
            if r.status_code == 400 and json_mode and "response_format" in body:
                body.pop("response_format")  # some gateways reject it; schema is still enforced by our parser
                continue
            if r.status_code in (429, 500, 502, 503, 504, 529):
                last = LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:500]}")
            data = r.json()
            break
        except httpx.HTTPError as exc:
            last = LLMError(f"network error: {exc}")
            time.sleep(3 * (attempt + 1))
    else:
        raise last or LLMError("LLM call failed")
    if cfg["protocol"] == "anthropic":
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    else:
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
        if isinstance(text, list):
            text = "".join(t.get("text", "") for t in text if isinstance(t, dict))
        usage = data.get("usage", {}) or {}
        tin, tout = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    secs = round(time.time() - t0, 2)
    cost = (tin * cfg["price_in_per_mtok"] + tout * cfg["price_out_per_mtok"]) / 1e6
    return {"text": text, "tokens_in": tin, "tokens_out": tout, "seconds": secs, "model": data.get("model", model),
            "params": params, "cost_usd": round(cost, 6)}


def parse_json(text: str) -> dict:
    """Parse a JSON object from a model reply (tolerates code fences). Raises on failure."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        i, k = t.find("{"), t.rfind("}")
        if i >= 0 and k > i:
            return json.loads(t[i:k + 1])
        raise


def test_connection() -> dict:
    cfg = config()
    out = {"base_url": _base(cfg), "protocol": cfg["protocol"]}
    try:
        out["models"] = list_models()[:200]
    except Exception as exc:
        out["models_error"] = str(exc)
    if cfg["model_a"]:
        try:
            r = chat(cfg["model_a"], "Reply with JSON only.", 'Return {"ok": true}', max_tokens=50)
            out["probe"] = {"model": r["model"], "reply": r["text"][:200], "seconds": r["seconds"]}
        except Exception as exc:
            out["probe_error"] = str(exc)
    return out

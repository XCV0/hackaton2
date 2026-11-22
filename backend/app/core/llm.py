"""LLM client. Provider presets; AgentRouter uses the OpenAI Responses API (/v1/responses) with its
client identification headers, other providers use OpenAI-compatible /chat/completions.

Settings (provider, base_url, key, per-node models) are entered in the admin UI and stored locally in
the `settings` table. The key is never exported or written to logs; an env var is used as a fallback.
Every call made by extraction nodes is logged by the caller in `node_runs`."""
from __future__ import annotations

import base64
import json
import os
import re
import time

import httpx

from . import db

PRESETS = {
    "agentrouter": {"base_url": "https://agentrouter.org/v1", "model": "gpt-6.1-sol", "json_mode": False, "api": "responses"},
    "claude-cli": {"base_url": "local: claude -p", "model": "haiku", "json_mode": False, "api": "claude-cli"},
    "klinch": {"base_url": "https://api.klinch.cloud/v1", "model": "", "json_mode": False, "api": "chat"},
    "klinch-ru": {"base_url": "https://ru.klinch.cloud/v1", "model": "", "json_mode": False, "api": "chat"},
    "deepseek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "json_mode": True, "api": "chat"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openrouter/free", "json_mode": False, "api": "chat"},
    "orcarouter": {"base_url": "https://api.orcarouter.ai/v1", "model": "deepseek/deepseek-v4-flash-free", "json_mode": False, "api": "chat"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash", "json_mode": False, "api": "chat"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b", "json_mode": True, "api": "chat"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen3.5:4b", "json_mode": True, "api": "chat"},
    "lmstudio": {"base_url": "http://127.0.0.1:1234/v1", "model": "local-model", "json_mode": False, "api": "chat"},
    "custom": {"base_url": "", "model": "", "json_mode": False, "api": "chat"},
}
API_KEY_ENV = {"klinch": "KLINCH_API_KEY", "klinch-ru": "KLINCH_API_KEY", "agentrouter": "AGENTROUTER_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "groq": "GROQ_API_KEY",
               "openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY"}
NO_KEY = {"ollama", "lmstudio", "claude-cli"}
DEFAULTS = {"provider": "agentrouter", "base_url": "", "api_key": "", "api_key_provider": "", "model_a": "", "model_b": "",
            "model_c": "", "model_vision": "", "reasoning_effort": "low", "page_workers": 6, "max_tokens": 8000, "timeout_s": 600, "workers": 1,
            "price_in_per_mtok": 0.0, "price_out_per_mtok": 0.0,
            # tried in order when the primary provider is out of quota / unavailable
            "fallback_chain": [{"provider": "klinch", "model": "claude-haiku-5-5"},
                               {"provider": "klinch", "model": "gpt-6-luna"},
                               {"provider": "claude-cli", "model": "haiku"}],
            "breaker_minutes": 30}
RETRIES = 3
RETRY_SLEEP = 3.0
GROQ_MAX_RETRY_AFTER = 30


class LLMError(RuntimeError):
    pass


# ------------------------------------------------------------------ settings
def _stored() -> dict:
    return db.get_setting("llm", {}) or {}


def _keys(raw: dict) -> dict:
    """Per-provider key pool {provider: [key1, key2, ...]}; key1 is the main key, the rest are backups.
    Migrates the legacy single key and single-string entries."""
    keys = {p: ([v] if isinstance(v, str) else list(v)) for p, v in (raw.get("keys") or {}).items() if v}
    if raw.get("api_key") and raw.get("api_key_provider") and raw["api_key_provider"] not in keys:
        keys[raw["api_key_provider"]] = [raw["api_key"]]
    return {p: [k for k in v if k] for p, v in keys.items() if any(v)}


def _hint(k: str) -> str:
    return (k[:4] + "…" + k[-4:]) if len(k) > 10 else "задан"


def config(provider: str | None = None, key_index: int = 0) -> dict:
    """Effective settings for `provider` (default: the primary one), including its key. Internal use only."""
    raw = _stored()
    s = {**DEFAULTS, **{k: v for k, v in raw.items() if k not in ("api_key", "api_key_provider", "keys")}}
    primary = s.get("provider") if s.get("provider") in PRESETS else DEFAULTS["provider"]
    prov = provider if provider in PRESETS else primary
    preset = PRESETS[prov]
    s["provider"] = prov
    s["primary_provider"] = primary
    if prov != primary or not s.get("base_url") or prov in ("ollama",):
        s["base_url"] = preset["base_url"]
    s["model_a"] = s.get("model_a") or preset["model"]
    pool = [] if prov in NO_KEY else _keys(raw).get(prov, [])
    key = pool[key_index] if key_index < len(pool) else ""
    s["key_count"] = len(pool)
    s["key_index"] = key_index
    env = API_KEY_ENV.get(prov)
    s["api_key"] = key or (os.environ.get(env, "").strip() if env else "")
    s["key_source"] = "settings" if key else ("env:" + env if s["api_key"] else "")
    s["json_mode"] = preset["json_mode"]
    s["api"] = preset["api"]
    return s


def public_config() -> dict:
    s = config()
    k = s.pop("api_key", "")
    s.pop("api_key_provider", None)
    s["api_key_set"] = bool(k)
    s["api_key_hint"] = (k[:4] + "…" + k[-4:]) if len(k) > 10 else ("задан" if k else "")
    s["presets"] = {p: {"base_url": v["base_url"], "model": v["model"], "api": v["api"]} for p, v in PRESETS.items()}
    keys = _keys(_stored())
    s["keys_set"] = sorted(p for p in PRESETS if keys.get(p) or (API_KEY_ENV.get(p) and os.environ.get(API_KEY_ENV[p])) or p in NO_KEY)
    s["key_pools"] = {p: [_hint(k) for k in v] for p, v in keys.items()}
    s["breaker"] = breaker_state()
    return s


def save_config(patch: dict) -> dict:
    patch = dict(patch or {})
    clear = patch.pop("clear_key", False) or patch.pop("clear_api_key", False)
    add_key = (patch.pop("add_key", "") or "").strip()
    remove_index = patch.pop("remove_key_index", None)
    raw = _stored()
    old = raw.get("provider") or DEFAULTS["provider"]
    prov = patch.get("provider") or old
    if prov not in PRESETS:
        raise LLMError("Неизвестный провайдер: %s (допустимы %s)" % (prov, ", ".join(PRESETS)))
    if prov != old and prov != "custom":
        if not patch.get("base_url"):
            patch["base_url"] = PRESETS[prov]["base_url"]
        if not patch.get("model_a"):
            patch["model_a"] = PRESETS[prov]["model"]
    new = dict(raw)
    for k, v in patch.items():
        if k not in DEFAULTS or v is None:
            continue
        if k == "api_key":
            if not v or prov in NO_KEY:
                continue
            keys = _keys(new)
            pool = keys.get(prov, [])
            keys[prov] = [v.strip()] + pool[1:]  # replaces the main key, backups are kept
            new["keys"] = keys
            new.pop("api_key", None)
            new.pop("api_key_provider", None)
            continue
        if k == "fallback_chain":
            if not isinstance(v, list) or not all(isinstance(x, dict) and x.get("provider") in PRESETS and x.get("model") for x in v):
                raise LLMError("fallback_chain: нужен список {provider, model} с известными провайдерами")
            new[k] = [{"provider": x["provider"], "model": str(x["model"]).strip()} for x in v]
            continue
        if k in ("max_tokens", "timeout_s", "workers", "page_workers"):
            try:
                v = max(1, int(v))
            except (TypeError, ValueError):
                raise LLMError(f"{k} должно быть целым числом")
        if k.startswith("price"):
            v = float(v or 0)
        new[k] = v.strip() if isinstance(v, str) else v
    if add_key and prov not in NO_KEY:
        keys = _keys(new)
        pool = keys.get(prov, [])
        if add_key not in pool:
            keys[prov] = pool + [add_key]
        new["keys"] = keys
        new.pop("api_key", None)
        new.pop("api_key_provider", None)
    if remove_index is not None:
        keys = _keys(new)
        pool = keys.get(prov, [])
        i = int(remove_index)
        if 0 <= i < len(pool):
            pool.pop(i)
        keys[prov] = pool
        new["keys"] = {p: v for p, v in keys.items() if v}
        new.pop("api_key", None)
        new.pop("api_key_provider", None)
    if clear:
        keys = _keys(new)
        keys.pop(prov, None)
        new["keys"] = keys
        new.pop("api_key", None)
        new.pop("api_key_provider", None)
    db.set_setting("llm", new)
    return public_config()


def _usable(prov: str) -> bool:
    c = config(prov)
    return bool(c["base_url"] and (c["api_key"] or prov in NO_KEY))


def available() -> bool:
    s = config()
    return bool(s["model_a"]) and (_usable(s["provider"]) or any(_usable(x["provider"]) for x in s.get("fallback_chain") or []))


# ------------------------------------------------------------------ fallback chain + circuit breaker
_breaker: dict[str, float] = {}
FALLBACK_MARKERS = ("quota", "insufficient", "402", "403", "401", "не ответила после", "не ответил после", "content-blocked",
                    "не залогинен", "не задан api-ключ", "недостаточно средств", "отклонил ключ", "http 429",
                    "не нашёл модель", "404", "сеть:", "не найден исполняемый файл", "model not available", "model_not_found")


def breaker_state() -> dict:
    now_ = time.time()
    return {p: round((t - now_) / 60, 1) for p, t in _breaker.items() if t > now_}


def _should_fallback(err: str) -> bool:
    e = err.lower()
    return any(m in e for m in FALLBACK_MARKERS)


def chat(model: str, system: str, user: str, *, images: list[bytes] | None = None, json_mode: bool | None = None,
         max_tokens: int | None = None) -> dict:
    """Primary provider first; on quota/auth/availability errors walk the fallback chain.
    A provider that ran out of quota is skipped for `breaker_minutes`. The provider and model that actually
    answered are returned in params (served_by) and logged by the caller."""
    s = config()
    chain = [(s["provider"], model or s["model_a"])]
    for x in s.get("fallback_chain") or []:
        step = (x["provider"], x["model"])
        if step not in chain:
            chain.append(step)
    attempts, last = [], None
    for prov, mdl in chain:
        if images and PRESETS[prov]["api"] == "claude-cli":
            attempts.append(f"{prov}/{mdl}: пропущен (не передаёт изображения)")
            continue
        if not _usable(prov):
            attempts.append(f"{prov}/{mdl}: нет ключа")
            continue
        n_keys = max(1, config(prov).get("key_count") or 1)
        for ki in range(n_keys):
            slot = f" (ключ {ki + 1})" if n_keys > 1 else ""
            bk = f"{prov}/{mdl}" + (f"#{ki + 1}" if n_keys > 1 else "")
            if _breaker.get(bk, 0) > time.time():
                attempts.append(f"{prov}/{mdl}{slot}: пропущен (квота исчерпана, повтор через {breaker_state().get(bk)} мин)")
                continue
            try:
                r = _chat_one(config(prov, ki), mdl, system, user, images=images, json_mode=json_mode, max_tokens=max_tokens)
                r["params"]["served_by"] = f"{prov}/{mdl}{slot}"
                r["params"]["requested"] = f"{s['provider']}/{model or s['model_a']}"
                if attempts:
                    r["params"]["fallback_attempts"] = attempts
                return r
            except LLMError as exc:
                last = exc
                attempts.append(f"{prov}/{mdl}{slot}: {str(exc)[:160]}")
                if not _should_fallback(str(exc)):
                    raise
                quota = any(m in str(exc).lower() for m in ("quota", "insufficient", "402", "недостаточно средств"))
                bad_key = any(m in str(exc).lower() for m in ("401", "403", "отклонил ключ"))
                if quota:
                    _breaker[bk] = time.time() + 60 * float(s.get("breaker_minutes") or 30)
                if quota or bad_key:
                    continue  # same model, next key of this provider
                break  # not a key problem (model/network/outage): next step of the chain
    raise LLMError("Все провайдеры цепочки недоступны: " + " | ".join(attempts)) from last





# ------------------------------------------------------------------ JSON parsing
def parse_json(text: str):
    """JSON from a model reply; a truncated reply is repaired by keeping complete top-level fields and
    complete elements of a truncated top-level array."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    cands = [m.start() for m in re.finditer(r'\{\s*"[^"\n]{1,60}"\s*:', text)]
    cands = [c for c in cands if text[:c].rstrip()[-1:] not in ("[", ",")] or cands
    if not cands:
        raise LLMError("Модель вернула не-JSON ответ")
    best, best_score = {}, -1
    for c in cands[:60]:
        out = _recover(text, c)
        score = sum(10 * len(v) if isinstance(v, list) else 1 for v in out.values())
        if score > best_score:
            best, best_score = out, score
    if not best:
        raise LLMError("Модель вернула не-JSON ответ")
    best["_truncated_recovered"] = True
    return best


def _recover(text, start):
    dec = json.JSONDecoder()
    out, i, n = {}, start + 1, len(text)
    while i < n:
        while i < n and text[i] in " \n\r\t,":
            i += 1
        if i >= n or text[i] != '"':
            break
        try:
            key, i = dec.raw_decode(text, i)
        except Exception:
            break
        while i < n and text[i] in " \n\r\t":
            i += 1
        if i >= n or text[i] != ":":
            break
        i += 1
        while i < n and text[i] in " \n\r\t":
            i += 1
        try:
            val, j = dec.raw_decode(text, i)
            out[key] = val
            i = j
            continue
        except Exception:
            pass
        if i < n and text[i] == "{":
            sub = _recover(text, i)
            if sub:
                out[key] = sub
            break
        if i < n and text[i] == "[":
            items, k = [], i + 1
            while True:
                while k < n and text[k] in " \n\r\t,":
                    k += 1
                if k >= n or text[k] not in '{["':
                    break
                try:
                    obj, k = dec.raw_decode(text, k)
                except Exception:
                    break
                items.append(obj)
            out[key] = items
        break
    return out


# ------------------------------------------------------------------ call
def _chat_one(s: dict, model: str, system: str, user: str, *, images: list[bytes] | None = None, json_mode: bool | None = None,
              max_tokens: int | None = None) -> dict:
    """One request to one provider with retries -> {text, tokens_in, tokens_out, seconds, model, params, cost_usd}."""
    base = (s["base_url"] or "").rstrip("/")
    if not base:
        raise LLMError("Не задан адрес API (base_url). Укажите его в разделе «LLM и ноды».")
    prov = s["provider"]
    model = model or s["model_a"]
    if not model:
        raise LLMError("Не выбрана модель (раздел «LLM и ноды»).")
    if prov not in NO_KEY and not s["api_key"]:
        raise LLMError(f"Не задан API-ключ провайдера {prov}. Укажите его в разделе «LLM и ноды»"
                       + (f" или в переменной {API_KEY_ENV[prov]}." if prov in API_KEY_ENV else "."))
    max_tokens = int(max_tokens or s["max_tokens"])
    if s["api"] == "claude-cli":
        return _claude_cli(model, system, user, images, s)
    headers = {"Content-Type": "application/json"}
    if s["api_key"]:
        headers["Authorization"] = "Bearer " + s["api_key"]
    use_responses = s["api"] == "responses"
    if prov == "agentrouter":
        headers.update({"User-Agent": "codex_cli_rs/0.149.1", "originator": "codex_cli_rs"})
    if use_responses:
        if images:
            ucontent = [{"type": "input_text", "text": user}] + [
                {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(im).decode()} for im in images]
        else:
            ucontent = user
        # reasoning tokens count against this limit: keep a practical floor
        body = {"model": model, "input": [{"role": "system", "content": system}, {"role": "user", "content": ucontent}],
                "max_output_tokens": max(40000, max_tokens)}
        if s.get("reasoning_effort") and s["reasoning_effort"] != "default":
            body["reasoning"] = {"effort": s["reasoning_effort"]}
    else:
        if images:
            ucontent = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(im).decode()}} for im in images]
        else:
            ucontent = user
        body = {"model": model, "temperature": 0, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": ucontent}]}
    options = {"timeout": s["timeout_s"]}
    if prov == "groq":
        body["max_completion_tokens"] = body.pop("max_tokens")
        if model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            body["reasoning_effort"] = "low"
        options["timeout"] = httpx.Timeout(90, connect=5)
    elif prov == "openrouter":
        body["reasoning"] = {"enabled": False}
        body["max_tokens"] = max(body.get("max_tokens", 0), 12000)
    elif prov == "ollama":
        body["reasoning_effort"] = "none"
        options.update(trust_env=False, timeout=httpx.Timeout(s["timeout_s"], connect=3))
    if (s["json_mode"] if json_mode is None else json_mode):
        if use_responses:
            body["text"] = {"format": {"type": "json_object"}}
        else:
            body["response_format"] = {"type": "json_object"}
    params = {"provider": prov, "base_url": base, "api": "responses" if use_responses else "chat.completions",
              "max_tokens": body.get("max_output_tokens") or body.get("max_tokens") or body.get("max_completion_tokens"),
              "temperature": body.get("temperature", "provider default"), "reasoning": body.get("reasoning"), "json_mode": "text" in body or "response_format" in body}
    t0, last = time.time(), None
    endpoint = "/responses" if use_responses else "/chat/completions"
    if use_responses:
        body["stream"] = True  # long non-streamed requests are dropped by the gateway (connection reset)
        params["stream"] = True
    for a in range(RETRIES + 1):
        delay = RETRY_SLEEP * (a + 1)
        if use_responses:
            try:
                res = _stream_responses(base + endpoint, headers, body, s)
            except _Retry as e:
                last = str(e)
                if a < RETRIES:
                    time.sleep(delay)
                continue
            text, payload = res
            usage = payload.get("usage") or {}
            if text.strip():
                return _done(text, t0, payload.get("model", model), params, usage.get("input_tokens", 0), usage.get("output_tokens", 0), s)
            inc = payload.get("incomplete_details") or {}
            if payload.get("status") == "incomplete" and inc.get("reason") == "max_output_tokens":
                rt = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
                raise LLMError("Модель исчерпала max_output_tokens (%s) до выдачи текста; reasoning_tokens=%s." % (body.get("max_output_tokens"), rt))
            last = "пустой ответ Responses API (status=%s, incomplete=%s)" % (payload.get("status"), inc)
            if a < RETRIES:
                time.sleep(delay)
            continue
        try:
            r = httpx.post(base + endpoint, headers=headers, json=body, **options)
        except httpx.HTTPError as e:
            last = "сеть: %s" % (str(e) or type(e).__name__)
        else:
            code = r.status_code
            if code in (401, 403):
                raise LLMError(("AgentRouter HTTP %d: %s" % (code, r.text[:600])) if prov == "agentrouter"
                               else "API отклонил ключ (HTTP %d). Проверьте API-ключ и права доступа." % code)
            if code == 402:
                raise LLMError("Недостаточно средств на аккаунте провайдера (HTTP 402).")
            if code == 404:
                raise LLMError("API не нашёл модель или адрес (HTTP 404): проверьте base_url и модель «%s»." % model)
            if code == 429 or code >= 500:
                last = "HTTP %d" % code
                if prov == "groq" and code == 429:
                    ra = r.headers.get("Retry-After", "")
                    if ra.isascii() and ra.isdecimal():
                        if int(ra) > GROQ_MAX_RETRY_AFTER:
                            raise LLMError(f"Лимит Groq (HTTP 429): API просит подождать {ra} с.")
                        delay = max(delay, int(ra))
            elif code == 400 and "reasoning" in body and "reasoning" in r.text.lower():
                body.pop("reasoning", None)
                last = "модель требует reasoning, повтор без отключения"
                continue
            elif code == 400 and ("text" in body or "response_format" in body) and ("format" in r.text.lower() or "response_format" in r.text.lower()):
                body.pop("text", None)
                body.pop("response_format", None)
                params["json_mode"] = False
                last = "JSON-режим не поддержан, повтор без него"
                continue
            elif code >= 400:
                raise LLMError("API вернул ошибку HTTP %d: %s" % (code, r.text[:800]))
            else:
                try:
                    payload = r.json()
                except Exception:
                    raise LLMError("API вернул не-JSON ответ: %s" % r.text[:400])
                usage = payload.get("usage") or {}
                if use_responses:
                    msg = payload.get("output_text") or ""
                    if not msg:
                        parts = []
                        for item in payload.get("output", []) or []:
                            if item.get("type") == "message":
                                for c in item.get("content", []) or []:
                                    if c.get("type") in ("output_text", "text") and c.get("text"):
                                        parts.append(c["text"])
                        msg = "\n".join(parts)
                    tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                    if not msg.strip():
                        if payload.get("error"):
                            raise LLMError("AgentRouter Responses API: %s" % json.dumps(payload["error"], ensure_ascii=False)[:800])
                        inc = payload.get("incomplete_details") or {}
                        if payload.get("status") == "incomplete" and inc.get("reason") == "max_output_tokens":
                            rt = (usage.get("output_tokens_details") or {}).get("reasoning_tokens")
                            raise LLMError("Модель исчерпала max_output_tokens (%s) до выдачи текста; reasoning_tokens=%s."
                                           % (body.get("max_output_tokens"), rt))
                        last = "пустой ответ Responses API (status=%s, incomplete=%s)" % (payload.get("status"), inc)
                    else:
                        return _done(msg, t0, payload.get("model", model), params, tin, tout, s)
                else:
                    try:
                        ch = payload["choices"][0]
                        m = ch["message"]
                        msg = m.get("content") or ""
                    except Exception:
                        raise LLMError("Неожиданный формат ответа API: %s" % r.text[:400])
                    if isinstance(msg, list):
                        msg = "".join(x.get("text", "") for x in msg if isinstance(x, dict))
                    tin, tout = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
                    if not msg.strip():
                        alt = m.get("reasoning") or m.get("reasoning_content") or ""
                        if isinstance(alt, str) and "{" in alt and "}" in alt:
                            return _done(alt, t0, payload.get("model", model), params, tin, tout, s)
                        last = "пустой ответ модели (finish_reason=%s)" % ch.get("finish_reason")
                    else:
                        return _done(msg, t0, payload.get("model", model), params, tin, tout, s)
        if a < RETRIES:
            time.sleep(delay)
    raise LLMError("Модель не ответила после %d попыток (%s)." % (RETRIES + 1, last))


def _cli_path():
    import shutil
    for c in [shutil.which("claude"), os.path.expanduser("~/.local/bin/claude"), "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]:
        if c and os.path.exists(c):
            return c
    raise LLMError("Не найден исполняемый файл claude (Claude Code CLI).")


def _cli_env():
    """Clean environment: the CLI must use the user's own login, not variables of whatever launched the server."""
    keep = {k: v for k, v in os.environ.items() if k in ("HOME", "PATH", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "SHELL")}
    keep.setdefault("PATH", "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin")
    return keep


def _claude_cli(model, system, user, images, s):
    """Local Claude Code CLI in headless mode (`claude -p`). Prompt goes via stdin; no tools are allowed."""
    import subprocess
    import tempfile
    if images:
        raise LLMError("Провайдер claude-cli не передаёт изображения: для Vision выберите API-провайдера.")
    t0 = time.time()
    cmd = [_cli_path(), "-p", "--output-format", "json", "--model", model or "haiku", "--system-prompt", system,
           "--max-turns", "1", "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch,Glob,Grep,Task,NotebookEdit"]
    last = None
    for a in range(RETRIES + 1):
        try:
            with tempfile.TemporaryDirectory(prefix="viniti_cli_") as cwd:  # empty cwd: no project context leaks in
                p = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=s["timeout_s"], env=_cli_env(), cwd=cwd)
        except subprocess.TimeoutExpired:
            last = "таймаут CLI"
            continue
        try:
            out = json.loads(p.stdout or "{}")
        except ValueError:
            raise LLMError("claude CLI вернул не-JSON: %s %s" % (p.stdout[:300], p.stderr[:300]))
        text = out.get("result") or ""
        if out.get("is_error"):
            if "login" in text.lower():
                raise LLMError("Claude Code CLI не залогинен: выполните в терминале `claude`, затем `/login`.")
            last = text[:300] or out.get("terminal_reason")
            if a < RETRIES:
                time.sleep(RETRY_SLEEP * (a + 1))
            continue
        u = out.get("usage") or {}
        tin = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
        params = {"provider": "claude-cli", "api": "claude -p (local Claude Code)", "model": model, "temperature": "CLI default",
                  "session_id": out.get("session_id"), "num_turns": out.get("num_turns")}
        r = _done(text, t0, model, params, tin, u.get("output_tokens") or 0, s)
        r["cost_usd"] = round(out.get("total_cost_usd") or 0, 6)
        return r
    raise LLMError("claude CLI не ответил после %d попыток (%s)" % (RETRIES + 1, last))


class _Retry(Exception):
    pass


def _stream_responses(url, headers, body, s):
    """SSE stream of the Responses API. Returns (text, final_response_payload)."""
    parts, final = [], {}
    try:
        with httpx.stream("POST", url, headers=headers, json=body, timeout=httpx.Timeout(s["timeout_s"], read=s["timeout_s"])) as r:
            code = r.status_code
            if code >= 400:
                txt = r.read().decode("utf-8", "replace")[:800]
                if code in (401, 403):
                    raise LLMError("AgentRouter HTTP %d: %s" % (code, txt))
                if code == 402:
                    raise LLMError("Недостаточно средств на аккаунте провайдера (HTTP 402).")
                if code == 404:
                    raise LLMError("API не нашёл модель или адрес (HTTP 404): %s" % txt)
                if code == 429 or code >= 500:
                    raise _Retry("HTTP %d" % code)
                if code == 400 and "text" in body and "format" in txt.lower():
                    body.pop("text", None)
                    raise _Retry("JSON-режим не поддержан, повтор без него")
                raise LLMError("API вернул ошибку HTTP %d: %s" % (code, txt))
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    ev = json.loads(data)
                except ValueError:
                    continue
                t = ev.get("type", "")
                if t == "response.output_text.delta":
                    parts.append(ev.get("delta", ""))
                elif t in ("response.completed", "response.incomplete", "response.failed"):
                    final = ev.get("response") or {}
                    if t == "response.failed":
                        raise _Retry("response.failed: %s" % json.dumps(final.get("error"), ensure_ascii=False)[:300])
                elif t == "error":
                    raise _Retry("stream error: %s" % json.dumps(ev, ensure_ascii=False)[:300])
    except httpx.HTTPError as e:
        raise _Retry("сеть: %s" % (str(e) or type(e).__name__))
    text = "".join(parts)
    if not text:
        text = final.get("output_text") or ""
    return text, final


def _done(text, t0, model, params, tin, tout, s):
    cost = (tin * float(s["price_in_per_mtok"] or 0) + tout * float(s["price_out_per_mtok"] or 0)) / 1e6
    return {"text": text, "tokens_in": tin or 0, "tokens_out": tout or 0, "seconds": round(time.time() - t0, 2),
            "model": model, "params": params, "cost_usd": round(cost, 6)}


def list_models() -> list[str]:
    s = config()
    if s["api"] == "claude-cli":
        return ["haiku", "sonnet", "opus", "claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
    headers = {"Authorization": "Bearer " + s["api_key"]} if s["api_key"] else {}
    if s["provider"] == "agentrouter":
        headers.update({"User-Agent": "codex_cli_rs/0.149.1", "originator": "codex_cli_rs"})
    r = httpx.get(s["base_url"].rstrip("/") + "/models", headers=headers, timeout=30)
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    items = data.get("data", data if isinstance(data, list) else [])
    return sorted({m.get("id") for m in items if isinstance(m, dict) and m.get("id")})


def test_connection() -> dict:
    s = config()
    out = {"provider": s["provider"], "base_url": s["base_url"], "model": s["model_a"], "key_source": s["key_source"]}
    try:
        out["models"] = list_models()[:300]
    except Exception as exc:
        out["models_error"] = str(exc)
    try:
        if s["provider"] == "agentrouter":
            r = chat(s["model_a"], "You are a helpful assistant.", "Reply with exactly: OK", max_tokens=16, json_mode=False)
        else:
            r = chat(s["model_a"], "Отвечай только JSON.", 'Верни JSON {"ok": true}', max_tokens=512 if s["provider"] in NO_KEY else 60)
        if not r["text"].strip():
            raise LLMError("пустой ответ")
        out.update(ok=True, message="Соединение работает", probe={"model": r["model"], "reply": r["text"][:100], "seconds": r["seconds"]})
    except LLMError as exc:
        out.update(ok=False, message=str(exc), probe_error=str(exc))
    return out

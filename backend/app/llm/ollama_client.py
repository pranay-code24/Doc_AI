import time
import contextvars
import json
from typing import Any
import requests

from app.config import (
    DEFAULT_LLM_PROVIDER,
    GROQ_API_KEY,
    GROQ_API_URL,
    GROQ_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)

# Per-request provider override ('groq' or 'ollama')
ACTIVE_PROVIDER: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ACTIVE_PROVIDER",
    default=DEFAULT_LLM_PROVIDER,
)


def get_effective_provider(requested: str | None = None) -> str:
    """Resolve active open-source provider safely (falls back to local ollama if no Groq key)."""
    choice = (requested or ACTIVE_PROVIDER.get() or DEFAULT_LLM_PROVIDER).lower()
    if choice == "groq" and GROQ_API_KEY:
        return "groq"
    return "ollama"


def _parse_json_safe(raw_content: str) -> dict[str, Any]:
    raw_content = raw_content.strip()
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw_content[start : end + 1])
        raise ValueError(f"LLM did not return valid JSON:\n{raw_content}")


def _call_groq_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    timeout: int = 45,
) -> dict[str, Any]:
    schema_instruction = (
        "\n\nOUTPUT FORMAT RULE: Return ONLY a single valid JSON object strictly conforming "
        f"to this JSON Schema (include every required field):\n{json.dumps(json_schema)}"
    )
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt + schema_instruction},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.0,
        "max_completion_tokens": 1024,
        "response_format": {"type": "json_object"},
    }
    if "gpt-oss" in GROQ_MODEL.lower():
        payload["reasoning_effort"] = "low"

    # 429 Free-Tier TPM rate limit par 2.5s wait karke retry karo (slow Ollama par mat giro)
    for attempt in range(3):
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 429 and attempt < 2:
            time.sleep(2.5)
            continue
        if not resp.ok:
            raise RuntimeError(f"{resp.status_code} {resp.text[:300]}")
        raw_content = resp.json()["choices"][0]["message"]["content"]
        return _parse_json_safe(raw_content)

    raise RuntimeError("Groq rate limit persisted after retries")


def _call_local_ollama_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    model: str = OLLAMA_MODEL,
    timeout: int = 120,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "format": json_schema,
        "options": {
            "temperature": 0.0,
            "repeat_penalty": 1.15,
            "num_ctx": 2048,
            "num_predict": 320,
        },
    }
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    raw_content = resp.json()["message"]["content"]
    return _parse_json_safe(raw_content)


def call_ollama_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    model: str = OLLAMA_MODEL,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Unified Open-Source Structured JSON caller:
    - Uses fast Groq Free Tier open-source model if configured & selected (~0.5s)
    - Automatically falls back to 100% offline local Ollama if offline or Groq fails.
    """
    provider = get_effective_provider()
    if provider == "groq":
        try:
            return _call_groq_json(system_prompt, user_prompt, json_schema)
        except Exception as e:
            print(f"[WARN] Groq API call failed ({e}), falling back to local Ollama...")
    return _call_local_ollama_json(system_prompt, user_prompt, json_schema, model=model, timeout=timeout)
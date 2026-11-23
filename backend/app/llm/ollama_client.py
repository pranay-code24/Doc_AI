import json
from typing import Any
import requests

from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL


def call_ollama_json(
    system_prompt: str,
    user_prompt: str,
    json_schema: dict[str, Any],
    model: str = OLLAMA_MODEL,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    Local Ollama /api/chat ko call karta hai with strict JSON schema,
    temperature=0.0, aur bounded token limit taaki kabhi hang/timeout na ho.
    """
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
            "num_ctx": 4096,
            "num_predict": 512,
        },
    }

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    raw_content = resp.json()["message"]["content"].strip()

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(raw_content[start : end + 1])
        raise ValueError(f"LLM did not return valid JSON:\n{raw_content}")
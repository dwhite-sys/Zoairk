"""Tiny Ollama chat helper (stdlib only)."""
from __future__ import annotations

import json
import os
import urllib.request

# Point the game at any Ollama: OLLAMA_HOST=http://host:11434, ZOAIRK_MODEL=<model tag>.
_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
URL = (_HOST if _HOST.startswith("http") else f"http://{_HOST}").rstrip("/") + "/api/chat"
MODEL = os.environ.get("ZOAIRK_MODEL", "deepseek-v4.1-flash:cloud")


def chat(messages: list[dict], tools: list[dict] | None = None, timeout: float = 30,
         temperature: float = 0.7) -> dict:
    """POST to Ollama /api/chat; return the assistant message dict, or {} on any error."""
    body = {"model": MODEL, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": temperature}}
    if tools:
        body["tools"] = tools
    try:
        req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r).get("message") or {}
    except Exception:
        return {}

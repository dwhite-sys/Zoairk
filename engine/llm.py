"""Tiny Ollama chat helper (stdlib only)."""
from __future__ import annotations

import json
import urllib.request

URL = "http://127.0.0.1:11434/api/chat"
MODEL = "deepseek-v4.1-flash:cloud"


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

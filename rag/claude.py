"""Minimal Claude Messages API client using only the standard library.

Used instead of the `anthropic` SDK because that package ships a compiled
library (jiter) that some Windows Application Control policies block.
"""
import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ClaudeError(RuntimeError):
    pass


def chat(model, messages, max_tokens=800, system=None, tools=None, timeout=60):
    """Call the Messages API and return the full response dict."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ClaudeError("ANTHROPIC_API_KEY is not set")
    body = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise ClaudeError(f"API error {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ClaudeError(f"Network error: {e.reason}") from None


MAX_STREAM_BLOCKS = 32


def chat_stream(model, messages, max_tokens=800, system=None, tools=None, timeout=60, on_text=None):
    """Like chat(), but reads the answer as it is written and calls on_text(piece) for every piece of text.

    Returns the same dict chat() would (stop_reason and content blocks, including tool calls), so the caller's
    loop does not change. If on_text raises (for example the customer closed the page), reading stops at once
    and the connection to the API is closed."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ClaudeError("ANTHROPIC_API_KEY is not set")
    body = {"model": model, "max_tokens": max_tokens, "messages": messages, "stream": True}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json",
                 "accept": "text/event-stream"},
        method="POST",
    )
    blocks, stop_reason = {}, None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:])
                except ValueError:
                    continue
                kind, idx = ev.get("type"), ev.get("index", 0)
                if kind == "content_block_start":
                    if len(blocks) >= MAX_STREAM_BLOCKS:
                        raise ClaudeError("too many content blocks")
                    blocks[idx] = dict(ev.get("content_block") or {})
                    blocks[idx]["_json"] = ""
                elif kind == "content_block_delta" and idx in blocks:
                    d = ev.get("delta") or {}
                    if d.get("type") == "text_delta":
                        piece = d.get("text", "")
                        blocks[idx]["text"] = blocks[idx].get("text", "") + piece
                        if on_text and piece:
                            on_text(piece)
                    elif d.get("type") == "input_json_delta":
                        blocks[idx]["_json"] += d.get("partial_json", "")
                elif kind == "message_delta":
                    stop_reason = (ev.get("delta") or {}).get("stop_reason", stop_reason)
                elif kind == "error":
                    raise ClaudeError(f"stream error: {(ev.get('error') or {}).get('type', 'unknown')}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise ClaudeError(f"API error {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ClaudeError(f"Network error: {e.reason}") from None
    content = []
    for idx in sorted(blocks):
        b = blocks[idx]
        raw_json = b.pop("_json", "")
        if b.get("type") == "tool_use":
            try:
                b["input"] = json.loads(raw_json) if raw_json else {}
            except ValueError:
                b["input"] = {}
        content.append(b)
    return {"stop_reason": stop_reason, "content": content}


def text_of(data):
    """Join the text blocks of a response."""
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def create(model, messages, max_tokens=800, system=None, timeout=60):
    """Call the Messages API and return the reply text."""
    return text_of(chat(model, messages, max_tokens, system, None, timeout))

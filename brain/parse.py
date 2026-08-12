# zero/brain/parse.py
#
# Turning model text into structured decisions. The fence/channel handling is
# hard-won knowledge about how this model family actually emits text
# (salvaged from the old eval's _extract_code): reasoning-tuned checkpoints
# wrap output in <|channel>thought ... <channel|> markers, and code/JSON often
# arrives inside markdown fences — sometimes with a draft copy inside the
# thought block, so we prefer the LAST fence, not the first.

import json
import re

FENCE_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
FENCE_ANY = re.compile(r"```[a-z]*\s*(.*?)\s*```", re.DOTALL)


def strip_thought(text: str) -> str:
    """Drop everything before the closing channel marker, if present."""
    if "<channel|>" in text:
        return text.split("<channel|>")[-1].strip()
    return text.strip()


def extract_code(text: str) -> str:
    """Best-effort extraction of a code payload from model output."""
    text = strip_thought(text)
    matches = FENCE_ANY.findall(text)
    if matches:
        return matches[-1].strip()
    return text.strip()


def extract_tool_call(text: str):
    """Parse a {"tool": name, "args": {...}} decision from model output.

    Returns (call_dict, None) on success or (None, reason) on failure —
    the caller decides whether failure means no_op or retry. Never raises.
    """
    candidates = []
    body = strip_thought(text)

    for m in FENCE_JSON.findall(body):
        candidates.append(m)
    # bare JSON object anywhere in the text (last one wins, same logic as fences)
    for m in re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", body):
        candidates.append(m)

    for raw in reversed(candidates):
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(doc, dict):
            continue
        if "tool" not in doc:
            continue
        tool = doc.get("tool")
        args = doc.get("args", {})
        if tool is not None and not isinstance(tool, str):
            continue
        if not isinstance(args, dict):
            continue
        return {"tool": tool, "args": args}, None

    return None, f"no parseable tool call in {len(text)} chars of output"


def extract_json_array(text: str):
    """(list | None, error | None) — same channel/fence tolerance as tool
    calls, for prompts whose contract is a bare JSON array."""
    candidate = extract_code(strip_thought(text)).strip()
    start, end = candidate.find("["), candidate.rfind("]")
    if start == -1 or end <= start:
        return None, "no JSON array found"
    try:
        value = json.loads(candidate[start:end + 1])
    except json.JSONDecodeError as e:
        return None, f"array parse failed: {e}"
    if not isinstance(value, list):
        return None, "top-level JSON is not an array"
    return value, None

# zero/brain/answer.py
#
# The answer channel: Zero says something back, in English, every single turn.
#
# The previous prototype died of not having this — its own logs contain the
# verdict verbatim: "I'm not reading allat tool call crap". Acting without
# speaking reads as broken even when the action succeeded, and a silent
# failure is indistinguishable from a hang.
#
# Rules:
#   1. Every turn produces exactly one answer. No exceptions, no silence.
#   2. Failures are answers too — said plainly, never as a stack trace.
#   3. If the model can't phrase it, a deterministic fallback still speaks.

MAX_ANSWER_CHARS = 600

PROMPT = (
    "You are Zero. You just handled a request for the user. Tell them what "
    "happened in ONE short, warm, plain sentence — like a helpful person, not "
    "a program. No JSON, no tool names, no file paths unless the user needs "
    "them, no apologising twice.\n"
    "If it failed, say what didn't work and what you'd try next. If nothing "
    "you did answers the question but something you already KNOW about the "
    "user does, answer from that instead of saying you did nothing.\n\n"
    "{memory_block}"
    "They asked: {goal}\n"
    "What you did: {action}\n"
    "Result: {result}\n\n"
    "Your one sentence:"
)


def _summarize_action(call):
    if not call:
        return "nothing — you couldn't work out a next step"
    tool = call.get("tool", "?")
    if tool == "no_op":
        return f"nothing on purpose ({call.get('args', {}).get('reason', 'no action needed')})"
    return f"used the {tool} tool with {call.get('args', {})}"


# Tool name -> how a person would say it. Verified against the real result
# shapes danger_core returns; "write_file" must never become "write fileed".
_PHRASING = {
    "list_dir": "looked in that folder",
    "read_file": "read that file",
    "search_code": "searched through the files",
    "write_file": "written that file",
    "edit_file": "made that edit",
    "run_command": "run that",
}

SHADOW_NOTE = ("I'm in shadow mode right now, so I only wrote down what I "
               "would have done instead of actually doing it")


def _outcome(result):
    """(short_text, ok, shadowed) — what actually happened, in plain terms.

    Result shapes come from danger_core: the executor wraps tool output as
    {"status": ..., "result": {...}} and shadowed calls arrive as
    {"status": "shadowed", "message": ...}.
    """
    if result is None:
        return "nothing needed doing", True, False
    if isinstance(result, dict):
        inner = result.get("result")
        if result.get("status") == "shadowed" or (
            isinstance(inner, dict) and inner.get("status") == "shadowed"
        ):
            return SHADOW_NOTE, True, True
        for layer in (inner, result):
            if isinstance(layer, dict) and layer.get("status") == "error":
                return layer.get("message", "something went wrong"), False, False
        if isinstance(inner, dict) and "content" in inner:
            return "here's what it says", True, False
        if isinstance(inner, (str, list)):
            return str(inner)[:300], True, False
        return "that's done", True, False
    return str(result)[:300], True, False


def fallback(goal, call, result):
    """Deterministic answer for when the model can't phrase one. Never empty,
    never grammatically embarrassing, never leaks a payload."""
    outcome, ok, shadowed = _outcome(result)
    if call is None:
        return ("I didn't quite follow that one — could you say it another way?")
    tool = call.get("tool", "?")
    if tool == "no_op":
        reason = call.get("args", {}).get("reason", "nothing needed doing")
        return f"I didn't need to do anything — {reason}."
    phrase = _PHRASING.get(tool, f"used {tool.replace('_', ' ')}")
    if shadowed:
        return f"I would have {phrase} — but {SHADOW_NOTE}."
    if not ok:
        return f"I tried, but {outcome}. Want me to try a different way?"
    return f"Done — I {phrase}. {outcome[0].upper() + outcome[1:]}."


def is_speakable(text):
    """Would a human read this as a sentence someone said to them?

    Reasoning checkpoints open a thought block and can spend the entire token
    budget inside it — an unclosed block means we caught it mid-think, and
    that raw text must never reach the user.
    """
    if not text or len(text.strip()) < 5:
        return False
    t = text.strip()
    if "channel" in t[:40] or "<|" in t or "Thinking Process" in t:
        return False
    if t.startswith(("{", "[")):
        return False
    return True


def compose(brain, goal, call, result, memory="", max_tokens=400):
    """Ask the model for one plain sentence; fall back to a deterministic one.

    Never raises, never returns empty, never leaks reasoning — the user always
    hears something a person would say. max_tokens has headroom because this
    model family thinks before it speaks.

    memory is what decide() already saw this turn — without it, a question a
    tool can't answer but memory CAN (e.g. "what did we decide?") gets a
    generic "nothing happened" reply even though Zero knew the answer.
    """
    outcome, _ok, _shadowed = _outcome(result)
    memory_block = f"What you already know:\n{memory}\n\n" if memory else ""
    try:
        raw = brain._generate(
            PROMPT.format(goal=goal, action=_summarize_action(call), result=outcome,
                          memory_block=memory_block),
            max_tokens,
        )
        from brain import parse
        text = parse.strip_thought(raw).strip().strip('"').lstrip("*").strip()
        # keep only the first sentence-ish chunk: the prompt asks for one
        if is_speakable(text):
            return text[:MAX_ANSWER_CHARS]
    except Exception:
        pass  # model trouble is never a reason for silence
    return fallback(goal, call, result)

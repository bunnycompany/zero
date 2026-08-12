# zero/brain/orchestrator.py

import json
import logging

from mlx_lm import load, generate, stream_generate

from brain import parse
from zero import memory, ns

DEFAULT_MODEL = "mlx-community/gemma-4-e2b-it-4bit"

# Sentinel a brain's _generate() may return to mean "the backend was
# unreachable" (used by the remote/gateway brain). decide() recognizes it and
# reports an honest, distinct failure rather than a confusing parse error, so
# the user hears "I can't reach the server right now" instead of nonsense.
GATEWAY_UNREACHABLE = "__gateway_unreachable__"


class BrainOrchestrator:
    def __init__(self, model_path=DEFAULT_MODEL):
        self.logger = logging.getLogger("BrainOrchestrator")
        self.logger.info(f"Loading model: {model_path}...")
        self.model, self.tokenizer = load(model_path)
        self.model_path = model_path
        self.logger.info("Model loaded successfully.")

    def _generate(self, prompt, max_tokens, think=False, on_token=None):
        """One completion. `think` toggles the model's reasoning block via the
        chat template's enable_thinking flag (verified: it injects <|think|>).

        Off by default on purpose — reasoning is worth its tokens for
        decisions, but for one-sentence language jobs it burns the whole
        budget thinking and then says nothing, which is exactly how the raw
        chain-of-thought leaked to the user in live testing.
        """
        messages = [{"role": "user", "content": prompt}]
        try:
            full_prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=think
            )
        except TypeError:  # template without the flag: take what we get
            full_prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        if on_token is None:
            return generate(
                self.model, self.tokenizer, prompt=full_prompt, verbose=False, max_tokens=max_tokens
            )
        # streaming path: the wait becomes visible instead of dead air
        chunks = []
        for step in stream_generate(
            self.model, self.tokenizer, prompt=full_prompt, max_tokens=max_tokens
        ):
            chunks.append(step.text)
            on_token(step.text)
        return "".join(chunks)


    THINKING_TAIL_CHARS = 240

    def _publish_thinking(self, chunk):
        """Live reasoning tail. Best-effort: never let telemetry break a turn."""
        raw = getattr(self, "_thinking_raw", "") + chunk
        self._thinking_raw = raw[-self.THINKING_TAIL_CHARS * 3:]
        # never show the protocol markers to a human
        self._thinking = (
            raw.replace("<|channel>thought", "").replace("<channel|>", "").strip()
        )[-self.THINKING_TAIL_CHARS:]
        try:
            ns.write_text("thinking", self._thinking, writer="brain")
        except Exception:
            pass

    def _clear_thinking(self):
        self._thinking = ""
        self._thinking_raw = ""
        try:
            ns.write_text("thinking", "", writer="brain")
        except Exception:
            pass

    def decide(self, context, goal, manifest, max_tokens=512, memory=""):
        """One structured decision: (tool_call | None, raw_text, error | None).

        Unparseable output is a decision failure to be journaled by the
        caller, never an exception. `memory` is the pre-rendered, budgeted
        block from zero.memory.render() — empty means no section.
        """
        tools_text = "\n".join(f"- {t['tool']}: {t['description']}" for t in manifest)
        # Memory is only useful if the prompt says what to DO with it. Both e2b
        # and a 12B via the gateway failed the "apply a remembered preference
        # to tool arguments" scenario identically — the block was present and
        # simply never instructed, which is a prompt bug, not a capacity one.
        memory_block = (
            "What you already know about this user — treat these as standing "
            "instructions and use them when filling in tool arguments (paths, "
            "commands, names), not just as background:\n"
            f"{memory}\n\n"
        ) if memory else ""
        prompt = (
            "You are Zero, an agent running locally on the user's Mac.\n\n"
            f"{memory_block}"
            f"Current context: {json.dumps(context)}\n"
            f"User request: {goal}\n\n"
            "Available tools:\n"
            f"{tools_text}\n\n"
            "Choose one tool. Fill its arguments with real, concrete values — "
            "an actual path or command, never a description or placeholder. "
            "Prefer what you know about the user over a generic default.\n"
            'Reply with ONLY a JSON object of the form {"tool": "<name>", "args": {...}}.\n'
            "No explanation, no markdown, no extra text.\n"
            'If nothing should be done, reply {"tool": "no_op", "args": {"reason": "<why>"}}.'
        )

        # the rendered prompt is training data: LoRA mining joins this line
        # with the proposal/result events that follow it
        ns.log("brain", "decision_prompt", prompt=prompt[:3000], goal=goal)

        # Decisions think — tool choice is the hard call and reasoning earns
        # its tokens there. Stream it so a thinking Zero looks alive instead of
        # frozen: the tail lands in namespace/thinking for the UIs to show.
        raw = self._generate(prompt, max_tokens, think=True, on_token=self._publish_thinking)
        self._clear_thinking()

        # A backend that was unreachable after retries is a distinct failure
        # from a model that answered with garbage — say so honestly.
        if raw == GATEWAY_UNREACHABLE:
            ns.write_doc("action", "brain", {"model": self.model_path, "unreachable": True})
            ns.log("brain", "gateway_unreachable", goal=goal)
            return None, raw, "gateway_unreachable"

        self.logger.info(f"Model decision: {raw[:200]}")

        call, err = parse.extract_tool_call(raw)
        payload = {"model": self.model_path}
        if call:
            payload.update(call)
        else:
            payload["text"] = parse.strip_thought(raw)[:1000]
            payload["parse_error"] = err
        ns.write_doc("action", "brain", payload)
        return call, raw, err

    def process_context(self, context_summary, goal=None, custom_prompt=None, max_tokens=1024):
        """Free-text generation (legacy path, still used by the eval)."""
        if custom_prompt:
            prompt = custom_prompt
        elif goal:
            prompt = (
                f"The user asked: {goal}\n"
                f"Current context: {context_summary}\n"
                f"Suggest a single concrete next action."
            )
        else:
            prompt = f"User is focused on: {context_summary}. Suggest a high-level action."

        response = self._generate(prompt, max_tokens)
        self.logger.info(f"Model decision: {response[:200]}")
        ns.write_doc("action", "brain", {"text": response, "model": self.model_path})
        return response

    def extract_observations(self, goal, call, result, max_tokens=256):
        """The hot memory write path: 0-3 notable facts from this turn, ADD-only.
        This single small structured task is the future LoRA target."""
        prompt = (
            "A user asked their assistant to do something. Extract 0-3 durable facts "
            "about the USER worth remembering for future requests (preferences, "
            "projects, recurring names/paths). Do NOT record the request itself.\n"
            f"Request: {goal}\n"
            f"Action taken: {json.dumps(call) if call else 'none'}\n"
            f"Outcome: {str(result)[:300]}\n\n"
            'Reply with ONLY a JSON array, e.g. '
            '[{"text": "...", "subject": "...", "importance": 1-10}]. '
            "Reply [] if nothing is worth remembering."
        )
        raw = self._generate(prompt, max_tokens, think=False)
        items, err = parse.extract_json_array(raw)
        if err:
            ns.log("brain", "observation_unparseable", error=err, raw=raw[:300])
            return 0
        n = 0
        for item in (items or [])[:3]:
            if isinstance(item, dict) and item.get("text"):
                memory.submit_observation(
                    str(item["text"]), str(item.get("subject", "")),
                    int(item.get("importance", 5) or 5),
                )
                n += 1
        if n:
            ns.log("brain", "observations_queued", count=n)
        return n

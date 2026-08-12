# zero/brain/remote.py
#
# A brain that thinks on the gateway instead of in local RAM.
#
# Why this exists: gemma-4-e2b is Google's *edge* variant, and it shows —
# literal path arguments, unparseable JSON, remembered facts it can read but
# not apply. The obvious fix is a bigger model, but this machine has 8 GB
# total and the cached 12B/31B variants are 8.3/9.7 GB of weights: they
# cannot load here at all. So the bigger brain has to live on the other end
# of a socket.
#
# Same interface as BrainOrchestrator — decide(), extract_observations(),
# _generate() — so main.py, the answer channel, and the eval harness neither
# know nor care which one they were handed.

import json
import logging
import os
import time
import urllib.error
import urllib.request

from brain.orchestrator import BrainOrchestrator, GATEWAY_UNREACHABLE

DEFAULT_GATEWAY = "https://api.danger.plus/v1"
DEFAULT_REMOTE_MODEL = "auto"  # the gateway routes; see its own auto endpoint

# The gateway 403s Python-urllib's default user agent (verified). Identify
# ourselves properly rather than looking like a scraper.
USER_AGENT = "zero-agent/0.1"

# GATEWAY_UNREACHABLE (the sentinel _generate returns when the gateway is
# down after retries) is defined in brain.orchestrator and imported above, so
# decide() there can recognize it. A larger option — falling back to a
# locally-loaded model — is deliberately NOT done here: it would load multi-GB
# weights on a "remote" install and change its RAM profile, an architecture
# decision for the founder, not a silent default. See docs/launch-blockers.md §4.


class RemoteBrain(BrainOrchestrator):
    """Gateway-backed brain. Inherits every decision/memory prompt from the
    local brain and swaps only where the tokens are produced."""

    def __init__(self, base_url=None, api_key=None, model=None, timeout=120):
        self.logger = logging.getLogger("RemoteBrain")
        self.base_url = (base_url or os.environ.get("ZERO_GATEWAY_URL") or DEFAULT_GATEWAY).rstrip("/")
        # never hardcoded, never journaled
        self.api_key = api_key or os.environ.get("ZERO_API_KEY", "")
        self.model_path = model or os.environ.get("ZERO_MODEL") or DEFAULT_REMOTE_MODEL
        self.timeout = timeout
        self.model = None      # nothing loaded locally
        self.tokenizer = None  # the gateway owns the chat template
        self.logger.info(f"Remote brain: {self.base_url} model={self.model_path}")

    def _post(self, payload):
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT,
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())

    def _post_with_retry(self, payload, attempts=3):
        """Bounded retry over transient gateway failures. danger.plus was
        observed returning 500/530 in bursts — a blip, not a verdict — so a
        few retries with backoff turn most of that into a successful turn.

        Safe to retry because generation is a pure read: no tool has run, no
        state has mutated. The 'never auto-retry a mutation' rule
        (danger_core/executor.py) is about the executor, not the brain. Only
        transient errors are retried; a 4xx (bad request, bad auth) will never
        improve, so it is raised immediately.
        """
        last = None
        for i in range(attempts):
            try:
                return self._post(payload)
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise  # client error — retrying cannot help
                last = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
            if i + 1 < attempts:
                time.sleep(0.5 * (2 ** i))  # 0.5s, 1s
        raise last

    def _generate(self, prompt, max_tokens, think=False, on_token=None):
        """Non-streaming for now: one request, one completion.

        `think` is advisory here — the gateway (and whichever model it routes
        to) owns its own reasoning behaviour. We still separate reasoning from
        the answer: gateways return it as `reasoning_content`, which must never
        be mistaken for the reply.
        """
        payload = {
            "model": self.model_path,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            data = self._post_with_retry(payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            # Still down after retries. A dead gateway reads as a failed turn,
            # never a crash. Return a sentinel the answer layer recognizes, so
            # the user hears "I can't reach the server right now" rather than a
            # generic "couldn't work out a next step" — an honest, actionable
            # failure instead of a confusing one.
            self.logger.warning(f"gateway unreachable after retries: {e}")
            return GATEWAY_UNREACHABLE
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            self.logger.warning(f"unexpected gateway response: {str(data)[:200]}")
            return ""
        text = msg.get("content") or ""
        if not text and msg.get("reasoning_content"):
            # spent the whole budget reasoning and never answered
            self.logger.info("gateway returned reasoning only")
        if on_token and text:
            on_token(text)
        return text

    def health(self):
        """(ok, detail) — used by `zero status` so a novice learns which brain
        they are talking to and whether it is reachable."""
        req = urllib.request.Request(
            f"{self.base_url}/models",
            headers={"User-Agent": USER_AGENT,
                     **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                models = [m["id"] for m in json.loads(resp.read()).get("data", [])]
            return True, f"{len(models)} models available"
        except urllib.error.HTTPError as e:
            hint = " (is ZERO_API_KEY set?)" if e.code in (401, 403, 500) else ""
            return False, f"HTTP {e.code}{hint}"
        except Exception as e:
            return False, str(e)


def build_brain():
    """Pick a brain from the environment.

    ZERO_BRAIN=remote (default when ZERO_API_KEY is set) -> gateway
    ZERO_BRAIN=local                                     -> in-RAM MLX
    """
    choice = os.environ.get("ZERO_BRAIN", "").lower()
    if not choice:
        choice = "remote" if os.environ.get("ZERO_API_KEY") else "local"
    if choice == "remote":
        return RemoteBrain()
    return BrainOrchestrator()

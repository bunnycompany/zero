// Token-bucket rate limiter, one Durable Object instance per (route, client
// IP) pair. That keying is deliberately different from ChallengeStore /
// LinkStore / HandleRegistry: those spin up a brand-new instance per
// request via crypto.randomUUID(), which is exactly the unbounded-DO-
// creation problem this file exists to stop. A rate limiter keyed by real
// client IPs has bounded cardinality — the same abusive IP reuses the same
// instance every time, so checking the bucket is cheap even under attack.
//
// Token bucket, not fixed window: refills continuously over time, so a
// legitimate user retrying a flaky passkey ceremony a few seconds later is
// never punished for a neighbor's burst, but a tight loop runs dry fast.

export class RateLimiter {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);
    if (pathname !== "/take" || request.method !== "POST") {
      return new Response("not found", { status: 404 });
    }

    const { capacity, refillPerSec } = await request.json();
    const now = Date.now();
    const stored = (await this.state.storage.get("bucket")) || { tokens: capacity, updated: now };

    const elapsedSec = Math.max(0, (now - stored.updated) / 1000);
    const tokens = Math.min(capacity, stored.tokens + elapsedSec * refillPerSec);

    if (tokens < 1) {
      // Don't spend a token, but do persist the refill progress made this
      // call — a client that backs off and waits shouldn't lose credit for
      // time that already elapsed before it asked.
      await this.state.storage.put("bucket", { tokens, updated: now });
      const deficit = 1 - tokens;
      const retryAfterMs = Math.max(1, Math.ceil((deficit / refillPerSec) * 1000));
      return Response.json({ allowed: false, retryAfterMs });
    }

    await this.state.storage.put("bucket", { tokens: tokens - 1, updated: now });
    return Response.json({ allowed: true, retryAfterMs: 0 });
  }
}

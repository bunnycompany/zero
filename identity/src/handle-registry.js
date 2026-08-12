// Atomic handle claiming. Found by the stress test in test/stress.js: a
// plain KV get-then-put has no compare-and-swap, so N concurrent
// registrations for the same handle can all pass the "is it taken?" check
// before any of them writes — reproduced live as 2 winners out of 50
// concurrent requests for one handle. Two people sharing a handle is a real
// identity-integrity failure, not a cosmetic race.
//
// Same fix as ChallengeStore and LinkStore: a Durable Object processes
// requests to one instance sequentially, so keying one instance per handle
// name turns "check then set" into a real mutex. KV still holds the actual
// credential data (this DO only holds a claim marker) — Workers KV remains
// the fast read path for everything that isn't a write race.

export class HandleRegistry {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);

    // The only atomic operation this needs: claim if and only if unclaimed.
    // Runs to completion before any concurrent request to the SAME DO
    // instance (same handle) can be interleaved — that ordering guarantee,
    // not any lock we write ourselves, is what makes this correct.
    if (pathname === "/claim" && request.method === "POST") {
      const already = await this.state.storage.get("claimed");
      if (already) return Response.json({ ok: false, reason: "already claimed" }, { status: 409 });
      await this.state.storage.put("claimed", true);
      return Response.json({ ok: true });
    }

    // Compensating action: if passkey verification fails AFTER the handle
    // was claimed, the claim must be released or that handle becomes
    // permanently unusable — squatted by a registration that never
    // completed. Without this, every failed/abandoned signup attempt would
    // burn a handle forever.
    if (pathname === "/release" && request.method === "POST") {
      await this.state.storage.delete("claimed");
      return Response.json({ ok: true });
    }

    return new Response("not found", { status: 404 });
  }
}

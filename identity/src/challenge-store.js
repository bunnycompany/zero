// A WebAuthn challenge must be used exactly once, or a captured response can
// be replayed. Workers KV is eventually consistent — a delete-after-read
// there is not atomic across the edge, so a fast attacker (or an honest
// double-submit from a flaky connection) could pass the read before the
// delete lands elsewhere. A Durable Object is a single, strongly-consistent
// instance per challenge id, so claim-once is a real guarantee, not a hope.

const TTL_MS = 5 * 60 * 1000; // a passkey ceremony takes seconds, not minutes

export class ChallengeStore {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);

    if (pathname === "/put" && request.method === "POST") {
      const { challenge, purpose } = await request.json();
      await this.state.storage.put("challenge", {
        challenge, purpose, expires: Date.now() + TTL_MS,
      });
      return new Response(null, { status: 204 });
    }

    if (pathname === "/claim" && request.method === "POST") {
      const { purpose } = await request.json();
      const record = await this.state.storage.get("challenge");
      // Claim is destructive and unconditional: whether it matches or not,
      // this challenge id can never be presented again.
      await this.state.storage.delete("challenge");
      if (!record) {
        return Response.json({ ok: false, reason: "unknown or already used" }, { status: 410 });
      }
      if (Date.now() > record.expires) {
        return Response.json({ ok: false, reason: "expired" }, { status: 410 });
      }
      if (record.purpose !== purpose) {
        return Response.json({ ok: false, reason: "wrong ceremony" }, { status: 400 });
      }
      return Response.json({ ok: true, challenge: record.challenge });
    }

    return new Response("not found", { status: 404 });
  }
}

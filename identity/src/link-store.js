// Device-linking flow (RFC 8628-shaped): how a headless anchor machine —
// a Mac mini with no browser, no biometric sensor to check — gets a
// legitimate session for a handle, without a raw passkey ceremony ever
// running somewhere it structurally cannot be trusted.
//
// `wrangler login`, `gh auth login`, and Tailscale's `tailscale up` all use
// this shape. Tailscale is the closest precedent to this exact use case:
// a machine that's sometimes offline, linked once from a device that has a
// real authenticator, reconnecting on its own after that.
//
// One DO instance per pending link, keyed by the code itself: the terminal
// displays it, the human types it into the browser, the terminal polls
// with the same code. The code is the shared secret for this exchange, so
// it needs real entropy despite being short — see CODE_ALPHABET in
// index.js (8 chars, 32-symbol unambiguous alphabet, ~40 bits — brute
// force is impractical inside the 10-minute window).

const PENDING_TTL_MS = 10 * 60 * 1000; // a human needs time to switch devices and look

export class LinkStore {
  constructor(state) {
    this.state = state;
  }

  async fetch(request) {
    const { pathname } = new URL(request.url);

    if (pathname === "/create" && request.method === "POST") {
      const { code } = await request.json();
      await this.state.storage.put("link", {
        code, status: "pending", handle: null, sessionToken: null,
        expires: Date.now() + PENDING_TTL_MS,
      });
      return new Response(null, { status: 204 });
    }

    if (pathname === "/approve" && request.method === "POST") {
      const { handle, sessionToken } = await request.json();
      const link = await this.state.storage.get("link");
      if (!link) return Response.json({ ok: false, reason: "expired or unknown" }, { status: 410 });
      if (Date.now() > link.expires) return Response.json({ ok: false, reason: "expired" }, { status: 410 });
      if (link.status !== "pending") return Response.json({ ok: false, reason: "already used" }, { status: 409 });
      link.status = "approved";
      link.handle = handle;
      link.sessionToken = sessionToken;
      await this.state.storage.put("link", link);
      return Response.json({ ok: true });
    }

    if (pathname === "/poll" && request.method === "POST") {
      const link = await this.state.storage.get("link");
      if (!link) return Response.json({ status: "unknown" }, { status: 404 });
      if (Date.now() > link.expires && link.status === "pending") {
        return Response.json({ status: "expired" });
      }
      // One-time collection: once the terminal has picked up the token,
      // the token is gone. A stolen poll response can't be replayed for a
      // second copy of the same session.
      if (link.status === "approved" && link.sessionToken) {
        const { sessionToken, handle } = link;
        link.sessionToken = null;
        await this.state.storage.put("link", link);
        return Response.json({ status: "approved", handle, sessionToken });
      }
      return Response.json({ status: link.status });
    }

    return new Response("not found", { status: 404 });
  }
}

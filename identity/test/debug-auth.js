import { server } from "@passwordless-id/webauthn";
import { syntheticRegister, syntheticAuthenticate } from "./synthetic-authenticator.js";

const rpId = "localhost", origin = "http://localhost:8787";
const challenge1 = "abc123challengeAAAAAAAAAAAAAAAAAAAAAAAAAAA";

const { registration, cred } = await syntheticRegister({ rpId, origin, challenge: challenge1 });
const reg = await server.verifyRegistration(registration, { challenge: challenge1, origin, domain: rpId, userVerified: false });
console.log("registration verified:", reg.credential);

const challenge2 = "def456challengeBBBBBBBBBBBBBBBBBBBBBBBBBBB";
const authentication = await syntheticAuthenticate({ rpId, origin, challenge: challenge2, cred });

try {
  const result = await server.verifyAuthentication(authentication, reg.credential, {
    challenge: challenge2, origin, userVerified: false,
  });
  console.log("AUTH OK:", result);
} catch (e) {
  console.error("AUTH FAILED:", e.message, "\n", e.stack);
}

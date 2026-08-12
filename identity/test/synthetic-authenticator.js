// A synthetic WebAuthn authenticator for load-testing the identity Worker
// against its REAL verification logic (server.verifyRegistration/
// verifyAuthentication), not just its HTTP routing. Same idea as Chrome
// DevTools Protocol's WebAuthn virtual-authenticator domain, minimal and
// dependency-free so it can fire hundreds of concurrent "signups" fast.
//
// This is test tooling. The security-critical code under test is the
// vetted @passwordless-id/webauthn library on the Worker side — this file's
// only job is to produce byte-correct WebAuthn responses; any mistake here
// surfaces immediately as a verification error, not a silent hole.

import { webcrypto as crypto } from "node:crypto";

// ---- minimal CBOR encoder: only the shapes WebAuthn actually needs -------

function cborUint(n) {
  if (n < 24) return Buffer.from([n]);
  if (n < 256) return Buffer.from([0x18, n]);
  if (n < 65536) return Buffer.from([0x19, n >> 8, n & 0xff]);
  return Buffer.from([0x1a, (n >> 24) & 0xff, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff]);
}
function cborNegInt(n) {
  // CBOR major type 1: n IS the argument already; the decoded value is
  // -(n+1). Caller passes n such that -(n+1) is the number they want
  // (e.g. cborNegInt(6) encodes -7). Do not re-derive n from the target
  // value in here — that was the bug: double-negating produced a
  // corrupted byte for every negative CBOR value in the COSE key.
  if (n < 24) return Buffer.from([0x20 | n]);
  return Buffer.from([0x38, n]);
}
function cborTextString(s) {
  const b = Buffer.from(s, "utf8");
  return Buffer.concat([majorLen(3, b.length), b]);
}
function cborByteString(b) {
  return Buffer.concat([majorLen(2, b.length), b]);
}
function majorLen(major, len) {
  const mt = major << 5;
  if (len < 24) return Buffer.from([mt | len]);
  if (len < 256) return Buffer.from([mt | 24, len]);
  if (len < 65536) return Buffer.from([mt | 25, len >> 8, len & 0xff]);
  return Buffer.from([mt | 26, (len >> 24) & 0xff, (len >> 16) & 0xff, (len >> 8) & 0xff, len & 0xff]);
}
function cborMapHeader(n) {
  return Buffer.from([0xa0 | n]); // n < 24, true for every map we build here
}

// COSE_Key for a P-256 public key, the exact 5-field map WebAuthn expects
// embedded in attestedCredentialData.
function coseKeyP256(x, y) {
  return Buffer.concat([
    cborMapHeader(5),
    cborUint(1), cborUint(2),           // kty: EC2
    cborUint(3), cborNegInt(6),         // alg: ES256 (-7)
    cborNegInt(0), cborUint(1),         // crv: P-256 (key -1, value 1)
    cborNegInt(1), cborByteString(x),   // x   (key -2)
    cborNegInt(2), cborByteString(y),   // y   (key -3)
  ]);
}

async function sha256(bytes) {
  return Buffer.from(await crypto.subtle.digest("SHA-256", bytes));
}

function b64url(buf) {
  return Buffer.from(buf).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecode(s) {
  return Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64");
}

export async function makeSyntheticCredential() {
  const keyPair = await crypto.subtle.generateKey(
    { name: "ECDSA", namedCurve: "P-256" }, true, ["sign", "verify"]
  );
  const raw = Buffer.from(await crypto.subtle.exportKey("raw", keyPair.publicKey)); // 0x04 || x(32) || y(32)
  const x = raw.subarray(1, 33), y = raw.subarray(33, 65);
  const credentialId = Buffer.from(crypto.getRandomValues(new Uint8Array(32)));
  // Two encodings of the SAME key, both needed:
  //  - COSE goes inside the attestation object's attestedCredentialData
  //  - SPKI (DER) is what a real browser reports as response.publicKey, and
  //    is what the library re-imports at verify time (importKey("spki",...)).
  const spkiPublicKey = Buffer.from(await crypto.subtle.exportKey("spki", keyPair.publicKey));
  return { keyPair, credentialId, cosePublicKey: coseKeyP256(x, y), spkiPublicKey };
}

async function buildAuthData(rpId, cred, { attested }) {
  const rpIdHash = await sha256(Buffer.from(rpId, "utf8"));
  const flags = attested ? 0b01000101 : 0b00000101; // UP(0) + UV(2) + AT(6) if attested
  const signCount = Buffer.alloc(4); // 0 — synthetic authenticator, no real counter needed
  const parts = [rpIdHash, Buffer.from([flags]), signCount];
  if (attested) {
    const aaguid = Buffer.alloc(16); // all-zero: synthetic, not a real device
    const credIdLen = Buffer.from([cred.credentialId.length >> 8, cred.credentialId.length & 0xff]);
    parts.push(aaguid, credIdLen, cred.credentialId, cred.cosePublicKey);
  }
  return Buffer.concat(parts);
}

export async function syntheticRegister({ rpId, origin, challenge }) {
  const cred = await makeSyntheticCredential();
  const authData = await buildAuthData(rpId, cred, { attested: true });
  const attestationObject = Buffer.concat([
    cborMapHeader(3),
    cborTextString("fmt"), cborTextString("none"),
    cborTextString("attStmt"), cborMapHeader(0),
    cborTextString("authData"), cborByteString(authData),
  ]);
  const clientDataJSON = Buffer.from(JSON.stringify({
    type: "webauthn.create", challenge, origin, crossOrigin: false,
  }));

  const registration = {
    type: "public-key",
    id: b64url(cred.credentialId),
    rawId: b64url(cred.credentialId),
    authenticatorAttachment: "platform",
    clientExtensionResults: {},
    response: {
      attestationObject: b64url(attestationObject),
      authenticatorData: b64url(authData),
      clientDataJSON: b64url(clientDataJSON),
      publicKey: b64url(cred.spkiPublicKey), // SPKI, as a real browser reports it
      publicKeyAlgorithm: -7,
      transports: ["internal"],
    },
  };
  return { registration, cred };
}

export async function syntheticAuthenticate({ rpId, origin, challenge, cred }) {
  const authData = await buildAuthData(rpId, cred, { attested: false });
  const clientDataJSON = Buffer.from(JSON.stringify({
    type: "webauthn.get", challenge, origin, crossOrigin: false,
  }));
  const clientDataHash = await sha256(clientDataJSON);
  const signedData = Buffer.concat([authData, clientDataHash]);

  const sigDer = Buffer.from(await crypto.subtle.sign(
    { name: "ECDSA", hash: "SHA-256" }, cred.keyPair.privateKey, signedData
  ));
  // Web Crypto returns raw r||s (64 bytes); WebAuthn wants DER — convert.
  const signature = rawToDer(sigDer);

  return {
    type: "public-key",
    id: b64url(cred.credentialId),
    rawId: b64url(cred.credentialId),
    clientExtensionResults: {},
    response: {
      authenticatorData: b64url(authData),
      clientDataJSON: b64url(clientDataJSON),
      signature: b64url(signature),
      userHandle: b64url(Buffer.from("synthetic")),
    },
  };
}

function rawToDer(raw) {
  // ECDSA raw signature is r(32) || s(32); DER wants two signed-integer TLVs.
  const r = trimLeadingZeros(raw.subarray(0, 32));
  const s = trimLeadingZeros(raw.subarray(32, 64));
  const rEnc = derInt(r), sEnc = derInt(s);
  return Buffer.concat([Buffer.from([0x30, rEnc.length + sEnc.length]), rEnc, sEnc]);
}
function trimLeadingZeros(buf) {
  let i = 0;
  while (i < buf.length - 1 && buf[i] === 0) i++;
  return buf.subarray(i);
}
function derInt(buf) {
  const needsPad = buf[0] & 0x80; // high bit set -> would read as negative, pad with 0x00
  const body = needsPad ? Buffer.concat([Buffer.from([0]), buf]) : buf;
  return Buffer.concat([Buffer.from([0x02, body.length]), body]);
}

export { b64url, b64urlDecode };

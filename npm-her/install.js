// postinstall: never fail the npm install (package.json runs this with
// `|| true`). Say whether the Mac is ready and what the one next step is.
// Nothing heavy happens here — `her setup` is the opt-in step, and it is the
// same setup Zero uses, because Her is not a second agent.

let report;
try {
  ({ report } = require("@0-computer/zero/bin/preflight"));
} catch {
  report = () => ({ ok: false });
}

console.log("");
console.log("  Her — the part of Zero that gets to know you.");
console.log("");
const { ok } = report();
console.log("");
if (ok) {
  console.log("  Your Mac is ready. Set her up (downloads Zero's brain, ~3.6GB, once):");
  console.log("");
  console.log("      her setup");
} else {
  console.log("  Fix the ✗ line(s) above, then run:  her setup");
}
console.log("");

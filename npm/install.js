// postinstall: never fail the npm install itself (package.json runs this with
// `|| true`). Just tell the person, in plain words, whether their Mac is ready
// and what the one next step is. The heavy lifting (venv, model download,
// daemon) happens on first `zero setup`, not here — a postinstall that quietly
// downloads 6.7GB is exactly the kind of surprise this product refuses.

const { report } = require("./bin/preflight");

console.log("");
console.log("  Zero — a quiet assistant that lives on your Mac.");
console.log("");

const { ok } = report();

console.log("");
if (ok) {
  console.log("  Your Mac is ready. Set Zero up (this downloads its brain, ~7GB, once):");
  console.log("");
  console.log("      zero setup");
} else {
  console.log("  Fix the ✗ line(s) above, then run:  zero setup");
}
console.log("");

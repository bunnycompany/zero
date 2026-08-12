#!/usr/bin/env node
// The `zero` command as installed from npm. It is a thin, honest dispatcher:
//   zero setup     -> preflight, then hand off to the repo's setup (venv +
//                     model + launchd daemon). The one heavy, opt-in step.
//   zero <words>   -> forward to the real bash CLI (scripts/zero) once set up.
//   zero doctor    -> just the preflight, re-run any time.
//
// This installer never becomes a second implementation of the agent. Every
// real behaviour lives in the Python/bash the repo already ships; this only
// gets it onto the machine and out of the way. (Failure-ledger #4: surfaces
// are thin; the agent has one brain, not one per front door.)

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const HOME = os.homedir();
const ZERO_ROOT = process.env.ZERO_ROOT || path.join(HOME, ".0-computer", "zero");

function preflight() {
  const { report } = require("./preflight");
  return report().ok;
}

function say(s) {
  process.stdout.write(s + "\n");
}

const [cmd, ...rest] = process.argv.slice(2);

if (cmd === "doctor") {
  process.exit(preflight() ? 0 : 1);
}

if (cmd === "setup") {
  say("");
  say("  Checking your Mac…");
  if (!preflight()) {
    say("\n  Fix the ✗ line(s) above first, then run  zero setup  again.");
    process.exit(1);
  }
  // Hand off to the repo's setup script (creates the venv, installs deps,
  // downloads the model, installs the launchd daemon). Shipped in the package.
  const setup = path.join(__dirname, "..", "setup.sh");
  if (!fs.existsSync(setup)) {
    say("\n  (v0.1.0 stub) setup.sh is not bundled yet — see docs/ship-review.md.");
    process.exit(1);
  }
  const r = spawnSync("bash", [setup], {
    stdio: "inherit",
    env: { ...process.env, ZERO_ROOT },
  });
  process.exit(r.status || 0);
}

if (!cmd || cmd === "help" || cmd === "--help") {
  say("");
  say("  Zero — talk to a quiet assistant that lives on your Mac.");
  say("");
  say("    zero setup            get it ready (once — downloads its brain)");
  say("    zero <anything>       ask it, in your own words");
  say("    zero                  read the last thing it told you");
  say("    zero doctor           check your Mac is ready");
  say("");
  process.exit(0);
}

// Forward everything else to the installed bash CLI.
const bashCli = path.join(ZERO_ROOT, "scripts", "zero");
if (!fs.existsSync(bashCli)) {
  say("  Zero isn't set up yet. Run:  zero setup");
  process.exit(1);
}
const r = spawnSync(bashCli, [cmd, ...rest], {
  stdio: "inherit",
  env: { ...process.env, ZERO_ROOT },
});
process.exit(r.status || 0);

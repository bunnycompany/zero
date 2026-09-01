#!/usr/bin/env node
// The `her` command as installed from npm. A thin, honest dispatcher:
//   her setup      -> Zero's own setup (venv + model + launchd), then hello.
//   her <words>    -> forward to scripts/her in the installed repo.
//   her doctor     -> just the preflight.
//
// Her never becomes a second implementation of anything. She is a layer in
// the same repo, over the same brain, reading the same files. This package
// exists so `npx @0-computer/her` is the whole first step for a friend.

const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const HOME = os.homedir();
const ZERO_ROOT = process.env.ZERO_ROOT || path.join(HOME, ".0-computer", "zero");

function say(s) { process.stdout.write(s + "\n"); }

function zeroPkg(rel) {
  try { return require.resolve("@0-computer/zero/" + rel); } catch { return null; }
}

function preflight() {
  const p = zeroPkg("bin/preflight.js");
  if (!p) { say("  @0-computer/zero is not installed alongside — run: npm i -g @0-computer/her"); return false; }
  return require(p).report().ok;
}

const [cmd, ...rest] = process.argv.slice(2);

if (cmd === "doctor") process.exit(preflight() ? 0 : 1);

if (cmd === "setup") {
  say("");
  say("  Checking your Mac…");
  if (!preflight()) {
    say("\n  Fix the ✗ line(s) above first, then run  her setup  again.");
    process.exit(1);
  }
  const setup = zeroPkg("setup.sh");
  if (!setup || !fs.existsSync(setup)) {
    say("\n  Zero's setup.sh is missing from the installed @0-computer/zero package.");
    process.exit(1);
  }
  const r = spawnSync("bash", [setup], { stdio: "inherit", env: { ...process.env, ZERO_ROOT } });
  if (r.status) process.exit(r.status);
  say("");
  say("  She's here. Say hello and read her first question:");
  say("");
  say("      her");
  say("");
  say("  Then, whenever you like:  her pair   (your phone)   her glasses   (Ray-Ban Display)");
  say("");
  process.exit(0);
}

if (cmd === "help" || cmd === "--help") {
  say("");
  say("  Her — the part of Zero that gets to know you.");
  say("");
  say("    her setup             get her ready (once — downloads Zero's brain)");
  say("    her                   what she'd say if you looked, and her question if any");
  say("    her <your answer>     answer her, or ask Zero through her");
  say("    her pair              add your phone     her glasses   add your Ray-Ban Display");
  say("    her profile           everything she knows, in your words");
  say("    her doctor            check your Mac is ready");
  say("");
  process.exit(0);
}

const bashCli = path.join(ZERO_ROOT, "scripts", "her");
if (!fs.existsSync(bashCli)) {
  say("  Her isn't set up yet. Run:  her setup");
  process.exit(1);
}
const r = spawnSync(bashCli, cmd === undefined ? [] : [cmd, ...rest], {
  stdio: "inherit",
  env: { ...process.env, ZERO_ROOT },
});
process.exit(r.status || 0);

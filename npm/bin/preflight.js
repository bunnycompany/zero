// Preflight: everything that must be true before Zero can run, checked with a
// plain sentence per line — the same honesty rule as the agent itself. A
// non-technical person should be able to read the output and know exactly what
// to do next. No stack traces, no jargon.

const { execSync } = require("child_process");

function have(cmd) {
  try {
    execSync(cmd, { stdio: "pipe" });
    return true;
  } catch {
    return false;
  }
}

function out(cmd) {
  try {
    return execSync(cmd, { stdio: "pipe" }).toString().trim();
  } catch {
    return "";
  }
}

// Each check: {ok, label, fix}. fix is what a person types or does, in words.
function checks() {
  const results = [];

  const isMac = process.platform === "darwin";
  results.push({
    ok: isMac,
    label: "This is a Mac",
    fix: "Zero runs on a Mac with Apple Silicon (M1 or newer). It can't run here.",
  });

  const isArm = process.arch === "arm64";
  results.push({
    ok: isArm,
    label: "Apple Silicon (M1 or newer)",
    fix: "Zero needs an Apple-Silicon Mac. Intel Macs can't run the local brain.",
  });

  // Python 3.12+ — the venv target. Accept 3.12 or 3.13.
  const pyVer = out("python3 --version");
  const okPy = /3\.(1[2-9]|[2-9]\d)/.test(pyVer);
  results.push({
    ok: okPy,
    label: `Python 3.12 or newer (found: ${pyVer || "none"})`,
    fix: "Install it from python.org, or run: brew install python@3.12",
  });

  // Xcode Command Line Tools — needed for the menubar app and some wheels.
  const okClt = have("xcode-select -p");
  results.push({
    ok: okClt,
    label: "Xcode Command Line Tools",
    fix: "Run: xcode-select --install  (a system dialog will walk you through it)",
  });

  // Disk: the model download is ~3.6GB; want headroom for the venv too.
  // Distinguish "couldn't read df" from "genuinely 0GB free" — a full disk
  // must fail, not pass on a parse miss.
  const raw = out("df -g / | tail -1 | awk '{print $4}'");
  const parsed = raw === "" ? null : Number(raw);
  const freeG = parsed === null || Number.isNaN(parsed) ? null : parsed;
  results.push({
    ok: freeG === null || freeG >= 8, // unknown -> don't block; known-low -> block
    label: `Room for the brain (~3.6GB) — ${freeG === null ? "unknown" : freeG + "GB"} free`,
    fix: "Free up about 8GB. The model download is ~3.6GB, plus room for Python.",
  });

  return results;
}

function report() {
  const rs = checks();
  const pad = Math.max(...rs.map((r) => r.label.length));
  for (const r of rs) {
    const mark = r.ok ? "✓" : "✗";
    console.log(`  ${mark}  ${r.label.padEnd(pad)}`);
    if (!r.ok) console.log(`      → ${r.fix}`);
  }
  const blocked = rs.filter((r) => !r.ok);
  return { ok: blocked.length === 0, blocked };
}

module.exports = { checks, report };

if (require.main === module) {
  const { ok } = report();
  process.exit(ok ? 0 : 1);
}

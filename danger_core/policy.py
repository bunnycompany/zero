# zero/danger_core/policy.py
#
# The safety seam: capability tiers, execution mode, path confinement.
# Deliberately small — if this file passes ~150 lines it has been overbuilt.
#
# Blast-radius engineering for the owner's own machine, not vulnerability
# theater: the threat is a small model at temperature running unattended,
# not an attacker.

from pathlib import Path

from zero import ns, nspath

# tiers
READ = "read"      # auto-runs in every mode. Be generous here — approval
                   # fatigue is what kills safety seams.
WRITE = "write"    # mutating but snapshotted/undoable
DANGER = "danger"  # subprocesses, deletes, anything irreversible

# modes (namespace/control/mode, human-written, read on EVERY call so
# `echo shadow > namespace/control/mode` works as a live panic button)
SHADOW = "shadow"    # nothing executes; every proposal is journaled
APPROVE = "approve"  # READ executes; WRITE/DANGER are journaled as pending
LIVE = "live"        # READ+WRITE execute; DANGER still refuses

DEFAULT_MODE = SHADOW
_VALID_MODES = {SHADOW, APPROVE, LIVE}


def current_mode() -> str:
    """Never cached. An unrecognized or missing value fails closed to shadow."""
    mode = ns.read_text("mode", default=DEFAULT_MODE).lower()
    return mode if mode in _VALID_MODES else DEFAULT_MODE


def may_execute(tier: str, mode: str) -> bool:
    if tier == READ:
        return True
    if tier == WRITE:
        return mode == LIVE
    return False  # DANGER never auto-executes; approval flow comes later


# Commands that arrived from outside the house are the largest blast radius in
# the product. A remote ask may read and report freely, but a mutation it
# triggers must never auto-fire — even when you are in LIVE mode at the keyboard.
# So remote is capped at APPROVE regardless of the real mode. This is the lock
# built before the door (see docs/reaching-zero.md).
_TRUSTED_SOURCES = {"human", "scheduler"}  # local origins


def effective_mode(mode: str, source: str) -> str:
    if source in _TRUSTED_SOURCES:
        return mode
    return APPROVE if mode == LIVE else mode  # remote can never exceed APPROVE


def allowed_root() -> Path:
    return nspath.root()


def resolve_confined(path_str: str) -> Path:
    """Resolve (symlinks and .. included) BEFORE checking confinement.

    Raises PermissionError for anything outside the Zero root, any write
    surface the agent must never touch (control/), and the safety layer
    itself (danger_core/ — self-modification always escalates).
    """
    p = Path(path_str).expanduser()
    root = allowed_root()
    if not p.is_absolute():
        p = root / p  # relative tool paths are root-relative, never cwd-relative
    p = p.resolve()
    if not p.is_relative_to(root):
        raise PermissionError(f"{p} is outside the allowed root {root}")
    for denied in _DENIED:
        target = root / denied
        if p == target or p.is_relative_to(target):
            raise PermissionError(f"{denied} is off-limits to the agent — human hands only")
    return p


# Everything that could let the agent change what it is allowed to do next, or
# rewrite the record of what it did. An audit found live mode could otherwise
# edit launch_zero.sh (ZERO_ROOT=$HOME escapes confinement entirely on the next
# launch), repoint nspath, or self-prompt via the command inbox.
_DENIED = (
    "namespace/control",        # the mode file: humans only, always
    "namespace/log",            # the audit trail must be tamper-evident
    "namespace/command/inbox",  # writing here is self-prompting
    "danger_core",              # the safety layer itself
    "zero",                     # ns/nspath/policy resolution
    "brain",                    # the decision layer
    "main.py",
    "launch_zero.sh",
)

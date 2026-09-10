# her/devices.py
#
# Which of your things Her lives on. A device becomes yours by pairing: the
# Mac shows a short code (`her pair`), you type it on the phone, and the phone
# receives a token it keeps and the Mac keeps only a hash of. Same shape as
# `gh auth login` / `tailscale up` — the identity README already argues why.
#
# What pairing does NOT do: raise trust. A paired phone is a `source` the
# executor does not trust (danger_core/policy.py::_TRUSTED_SOURCES), so a
# command from it can read and report but never auto-mutate — even when the
# Mac is in live mode. A stolen phone can ask; it cannot act. (US-052.)
#
# State:
#   her/pairing/current — the one live code, writer: her (the CLI)
#   her/devices/current — the registry, writer: bridge

import hashlib
import secrets
import socket
import time

from zero import ns

PAIR_TTL_S = 600
PAIR_MAX_ATTEMPTS = 5
PAIR_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L
KINDS = ("phone", "glasses", "mac", "other")
BRIDGE_PORT = 7770


class PairError(Exception):
    pass


# --- pairing code --------------------------------------------------------

def open_pairing(now=None):
    """Mint a fresh code (replacing any previous one). Returns the code."""
    now = time.time() if now is None else now
    code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(6))
    ns.write_doc("her/pairing", "her", {"code": code, "expires": now + PAIR_TTL_S, "attempts": 0})
    ns.log("her", "pairing_opened", expires=now + PAIR_TTL_S)
    return code


def pairing(now=None):
    """The live pairing record, or None when there is none or it expired."""
    now = time.time() if now is None else now
    doc = ns.read_doc("her/pairing")
    if not doc:
        return None
    p = doc.get("payload") or {}
    if p.get("expires", 0) <= now or p.get("attempts", 0) >= PAIR_MAX_ATTEMPTS:
        return None
    return p


def close_pairing(reason="done"):
    doc = ns.read_doc("her/pairing")
    if doc:
        # keep the doc but expire it: the bridge polls the file, and a
        # missing file vs an expired one read the same to it
        ns.write_doc("her/pairing", "her", {"code": "", "expires": 0, "attempts": 0})
        ns.log("her", "pairing_closed", reason=reason)


def _bump_attempts():
    doc = ns.read_doc("her/pairing")
    if not doc:
        return
    p = dict(doc.get("payload") or {})
    p["attempts"] = int(p.get("attempts", 0)) + 1
    ns.write_doc("her/pairing", "her", p)
    if p["attempts"] >= PAIR_MAX_ATTEMPTS:
        ns.log("her", "pairing_closed", reason="too many wrong codes")


# --- registry ------------------------------------------------------------

def registry():
    doc = ns.read_doc("her/devices")
    if not doc or not isinstance(doc.get("payload"), dict):
        return {"devices": {}}
    reg = doc["payload"]
    reg.setdefault("devices", {})
    return reg


def _save(reg):
    ns.write_doc("her/devices", "bridge", reg)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def pair(code, name, kind, now=None):
    """Exchange a valid code for a device token. The token is returned once
    and never stored; the registry keeps its hash. Raises PairError."""
    now = time.time() if now is None else now
    p = pairing(now)
    if p is None:
        raise PairError("no pairing code is open — run  her pair  on the Mac")
    if str(code).strip().upper() != p["code"]:
        _bump_attempts()
        raise PairError("that code is not right")
    kind = kind if kind in KINDS else "other"
    name = (str(name).strip() or kind)[:40]
    token = secrets.token_urlsafe(32)
    device_id = secrets.token_hex(4)
    reg = registry()
    reg["devices"][device_id] = {
        "name": name, "kind": kind, "token_sha256": _hash(token),
        "paired": now, "last_seen": now,
    }
    _save(reg)
    close_pairing("paired")
    ns.log("bridge", "device_paired", device=device_id, name=name, kind=kind)
    return device_id, token


def authenticate(token, now=None):
    """(device_id, device) for a valid token, else None. Constant-time
    compare on the hash; last_seen is refreshed at most once a minute so a
    polling phone does not rewrite the registry every second."""
    if not token:
        return None
    now = time.time() if now is None else now
    h = _hash(token)
    reg = registry()
    for did, d in reg["devices"].items():
        if secrets.compare_digest(d.get("token_sha256", ""), h):
            if now - d.get("last_seen", 0) > 60:
                d["last_seen"] = now
                _save(reg)
            return did, d
    return None


def forget(device_id):
    """Revoke one device. Its token is a dead key from this moment (US-057)."""
    reg = registry()
    d = reg["devices"].pop(device_id, None)
    if d is None:
        return False
    _save(reg)
    ns.log("bridge", "device_forgotten", device=device_id, name=d.get("name"))
    return True


def list_devices():
    return registry()["devices"]


def should_listen(now=None):
    """The bridge binds a port only when there is someone to listen for: a
    paired device, or a pairing code you just opened. Otherwise the Mac
    listens for nothing (US-054)."""
    return bool(list_devices()) or pairing(now) is not None


# --- where am I ----------------------------------------------------------

def lan_ip():
    """This Mac's address on the home network, for the pairing screen. No
    packets are sent: connecting a UDP socket only picks a route."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def phone_url(ip=None, port=BRIDGE_PORT):
    """Where any phone on the home wifi finds Her with nothing to install:
    the page the bridge serves at /her/ (her/phone/index.html)."""
    return f"http://{ip or lan_ip()}:{port}/her/"

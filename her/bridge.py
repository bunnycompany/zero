# her/bridge.py
#
# The LAN bridge: how a paired phone or a pair of glasses reaches Her.
#
#   phone ──(device token)──▶ bridge ──▶ command/inbox {source: "phone", device}
#                                            │
#                                    the ordinary loop
#                                            │
#   phone ◀──(same wifi)──── her/presence + answer/current
#
# It is a thin authenticated listener over the namespace, nothing more: no
# second brain, no second executor, no execution path of its own. Rules:
#
#   * Listens only when there is someone to listen for (a paired device, or
#     a pairing code you opened). Otherwise no port is bound (US-054).
#   * Private addresses only: your wifi, or your own Tailscale mesh. A request
#     from the open internet is refused before it is read — reaching Her
#     from a cafe without a mesh is the identity/relay project
#     (docs/reaching-zero.md), not this file.
#   * A device is a source the executor does not trust: read and report,
#     never auto-mutate. Enforced in danger_core/policy.py, not here.
#
#   ~/.venv/bin/python3 -m her.bridge        # run forever (launch_zero.sh does)

import ipaddress
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from her import devices, presence
from zero import ns

MAX_BODY = 16 * 1024
POLL_S = 2.0
HISTORY_DEFAULT = 20
HISTORY_MAX = 200
SNAPSHOT_HISTORY = 8
_PAGES = {
    "/glasses": Path(__file__).with_name("glasses") / "index.html",
    "/her": Path(__file__).with_name("phone") / "index.html",
}
# Tailscale gives every node an address in the CGNAT range 100.64.0.0/10, and
# docs/reaching-zero.md recommends a mesh (Tailscale) as the way to reach Her
# from outside the house. Python's ipaddress.is_private says no to that range,
# so without this the recommended path would be refused by the code.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _is_private(addr):
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    return ip.version == 4 and ip in _CGNAT


def _alive():
    from zero import nspath
    try:
        m = nspath.state("status").stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - m < 30


# --- the journal, as a phone reads it ---------------------------------------
#
# The journal is the scrollback: a phone that comes back after an hour picks
# up where you left off by reading it, not by resuming a process. One pass
# pairs every command_received with the answered event that follows it (the
# loop is single-threaded and FIFO, so the next answered belongs to the most
# recent open ask) and counts today's events for US-044. The pass is cached
# on the journal's size and mtime: a phone polls every 1.5 s and the journal
# can be 10 MB.

_SCHEDULED = ("scheduler",)
_EMPTY_TODAY = {"asks": 0, "answered": 0, "executed": 0, "shadowed": 0, "held": 0}
_view_cache = {"key": None, "turns": [], "today": dict(_EMPTY_TODAY)}
_view_lock = threading.Lock()


def _same_local_day(ts, now):
    return time.localtime(ts)[:3] == time.localtime(now)[:3]


def _journal_view(now=None):
    """(turns, today). turns: every organic and device ask in order, each
    {ts, text, source, device, answer, answer_ts}. today, in local time:
    asks, answered, executed, shadowed (mode shadow) and held (a proposal
    waiting for a yes at the Mac: mode approve)."""
    now = time.time() if now is None else now
    from zero import nspath
    try:
        st = nspath.journal().stat()
    except FileNotFoundError:
        return [], dict(_EMPTY_TODAY)
    key = (st.st_size, st.st_mtime_ns, time.localtime(now)[:3])
    with _view_lock:
        if _view_cache["key"] == key:
            return list(_view_cache["turns"]), dict(_view_cache["today"])
    turns, today, open_turn = [], dict(_EMPTY_TODAY), None
    for e in ns.read_journal():
        ev, ts = e.get("event"), e.get("ts", 0)
        fresh = _same_local_day(ts, now)
        if ev == "command_received":
            open_turn = {"ts": ts, "text": e.get("text", ""), "source": e.get("source", "human"),
                         "device": e.get("device") or "", "answer": None, "answer_ts": None}
            turns.append(open_turn)
            if fresh and open_turn["source"] not in _SCHEDULED:
                today["asks"] += 1
        elif ev == "answered":
            if open_turn is not None and open_turn["answer"] is None:
                open_turn["answer"], open_turn["answer_ts"] = e.get("text", ""), ts
            if fresh:
                today["answered"] += 1
        elif ev == "executed" and fresh:
            today["executed"] += 1
        elif ev == "shadowed" and fresh:
            today["held" if e.get("mode") == "approve" else "shadowed"] += 1
    turns = [t for t in turns if t["source"] not in _SCHEDULED]
    with _view_lock:
        _view_cache.update(key=key, turns=turns, today=today)
    return list(turns), dict(today)


def history(limit=HISTORY_DEFAULT, now=None):
    """The last `limit` organic and device turns, oldest first."""
    limit = max(1, min(int(limit), HISTORY_MAX))
    return _journal_view(now)[0][-limit:]


def today_counts(now=None):
    return _journal_view(now)[1]


def snapshot(device_id=None):
    """What a surface needs to render Her, in one read."""
    p = presence.current()
    answer = ns.read_doc("answer")
    turns, today = _journal_view()
    return {
        "alive": _alive(),
        "status": ns.read_text("status", default="idle"),
        "mode": ns.read_text("mode", default="shadow"),
        "presence": p,
        "answer": (answer or {}).get("payload"),
        "answer_ts": (answer or {}).get("ts"),
        "device": device_id,
        "name": her_name(),
        "history": turns[-SNAPSHOT_HISTORY:],
        "today": today,
    }


def her_name():
    from zero import memory
    for f in memory.load_facts():
        if f.get("origin") == "intake:her_name":
            return f["text"].replace("Calls their assistant", "").strip()
    return "Her"


class Handler(BaseHTTPRequestHandler):
    server_version = "her-bridge/0.1"

    def log_message(self, *a):  # the journal is the log, not stderr
        pass

    # --- plumbing -----------------------------------------------------------

    def _json(self, code, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _token(self):
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return (self._query().get("t") or [""])[0]

    def _device(self):
        return devices.authenticate(self._token())

    def _gate(self):
        """Private network only, always, before anything else."""
        if not _is_private(self.client_address[0]):
            ns.log("bridge", "refused", reason="not a private address")
            self._json(403, {"error": "Her only answers on your own network"})
            return False
        return True

    def _path(self):
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def _query(self):
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(self.path).query)

    def _page(self, path):
        """A surface's page (the glasses lens, the phone page). Loading it
        needs no token; everything it reads does."""
        try:
            page = _PAGES[path].read_bytes()
        except FileNotFoundError:
            return self._json(404, {"error": "that page is not in this copy"})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(page)

    # --- routes -------------------------------------------------------------

    def do_GET(self):
        if not self._gate():
            return
        path = self._path()
        if path == "/health":
            return self._json(200, {"her": True, "name": her_name(), "alive": _alive(),
                                    "pairing_open": devices.pairing() is not None})
        if path in _PAGES:
            return self._page(path)
        dev = self._device()
        if dev is None:
            return self._json(401, {"error": "this device isn't paired — run  her pair  on the Mac"})
        did, _ = dev
        if path == "/v1/presence":
            return self._json(200, snapshot(did))
        if path == "/v1/answer":
            doc = ns.read_doc("answer")
            return self._json(200, {"answer": (doc or {}).get("payload"), "ts": (doc or {}).get("ts")})
        if path == "/v1/history":
            try:
                limit = int((self._query().get("limit") or [HISTORY_DEFAULT])[0])
            except ValueError:
                limit = HISTORY_DEFAULT
            return self._json(200, history(limit))
        return self._json(404, {"error": "no such thing"})

    def do_POST(self):
        if not self._gate():
            return
        path = self._path()
        body = self._body()
        if body is None or not isinstance(body, dict):
            return self._json(400, {"error": "send a small JSON object"})
        if path == "/pair":
            try:
                did, token = devices.pair(body.get("code", ""), body.get("name", ""),
                                          body.get("kind", "other"))
            except devices.PairError as e:
                return self._json(403, {"error": str(e)})
            return self._json(200, {"device": did, "token": token, "name": her_name()})
        dev = self._device()
        if dev is None:
            return self._json(401, {"error": "this device isn't paired — run  her pair  on the Mac"})
        did, d = dev
        if path == "/v1/say":
            text = str(body.get("text", "")).strip()
            if not text:
                return self._json(400, {"error": "say something"})
            meta = {"device": did}
            reply_to = body.get("reply_to")
            if isinstance(reply_to, str) and reply_to:
                meta["reply_to"] = reply_to
            # the device's kind is the command's source: untrusted, capped at
            # approve by policy.effective_mode — the phone can ask, never act
            ns.submit_command(text[:4000], source=d.get("kind", "other"), **meta)
            ns.log("bridge", "relayed", device=did, kind=d.get("kind"), chars=len(text))
            return self._json(200, {"queued": True, "ts": time.time()})
        return self._json(404, {"error": "no such thing"})


class Bridge:
    """Bind/unbind follows devices.should_listen(); serve() polls it."""

    def __init__(self, host="0.0.0.0", port=devices.BRIDGE_PORT):
        self.host, self.port = host, port
        self.httpd = None
        self._thread = None

    @property
    def listening(self):
        return self.httpd is not None

    @property
    def bound_port(self):
        return self.httpd.server_address[1] if self.httpd else None

    def start(self):
        if self.httpd:
            return
        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.httpd.daemon_threads = True
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        ns.log("bridge", "listening", host=self.host, port=self.bound_port)

    def stop(self):
        if not self.httpd:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None
        ns.log("bridge", "stopped")

    def reconcile(self):
        want = devices.should_listen()
        if want and not self.listening:
            self.start()
        elif not want and self.listening:
            self.stop()
        return self.listening

    def serve(self, poll_s=POLL_S):
        try:
            while True:
                self.reconcile()
                time.sleep(poll_s)
        except KeyboardInterrupt:
            self.stop()


if __name__ == "__main__":
    print(f"Her bridge: binds :{devices.BRIDGE_PORT} only while a device is paired or a pairing code is open.")
    Bridge().serve()

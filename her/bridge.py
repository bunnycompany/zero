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
#   * Private addresses only. A request from outside the house is refused
#     before it is read — reaching Her from a cafe is the identity/relay
#     project (docs/reaching-zero.md), not this file.
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
_GLASSES_PAGE = Path(__file__).with_name("glasses") / "index.html"


def _is_private(addr):
    try:
        ip = ipaddress.ip_address(addr.split("%")[0])
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _alive():
    from zero import nspath
    try:
        m = nspath.state("status").stat().st_mtime
    except FileNotFoundError:
        return False
    return time.time() - m < 30


def snapshot(device_id=None):
    """What a surface needs to render Her, in one read."""
    p = presence.current()
    answer = ns.read_doc("answer")
    return {
        "alive": _alive(),
        "status": ns.read_text("status", default="idle"),
        "mode": ns.read_text("mode", default="shadow"),
        "presence": p,
        "answer": (answer or {}).get("payload"),
        "answer_ts": (answer or {}).get("ts"),
        "device": device_id,
        "name": her_name(),
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
        from urllib.parse import parse_qs, urlparse
        return (parse_qs(urlparse(self.path).query).get("t") or [""])[0]

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

    # --- routes -------------------------------------------------------------

    def do_GET(self):
        if not self._gate():
            return
        path = self._path()
        if path == "/health":
            return self._json(200, {"her": True, "name": her_name(), "alive": _alive(),
                                    "pairing_open": devices.pairing() is not None})
        if path == "/glasses":
            try:
                page = _GLASSES_PAGE.read_bytes()
            except FileNotFoundError:
                return self._json(404, {"error": "no glasses page in this copy"})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            return self.wfile.write(page)
        dev = self._device()
        if dev is None:
            return self._json(401, {"error": "this device isn't paired — run  her pair  on the Mac"})
        did, _ = dev
        if path == "/v1/presence":
            return self._json(200, snapshot(did))
        if path == "/v1/answer":
            doc = ns.read_doc("answer")
            return self._json(200, {"answer": (doc or {}).get("payload"), "ts": (doc or {}).get("ts")})
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

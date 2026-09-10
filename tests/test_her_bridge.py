# zero/tests/test_her_bridge.py
#
# Devices and the LAN bridge, end to end over a real socket on loopback:
# pair by code, token in / hash kept, a phone's ask lands in the inbox with
# an untrusted source, presence/answer are readable, a forgotten device is a
# dead key, and the port is bound only while there is someone to listen for.

import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request

from danger_core import policy
from her import bridge, devices, presence
from zero import ns


class DevicesTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        self._tmp.cleanup()

    def test_pair_keeps_only_a_hash_and_closes_the_code(self):
        code = devices.open_pairing(now=1000.0)
        self.assertEqual(len(code), 6)
        did, token = devices.pair(code, "Nothing Phone 3", "phone", now=1001.0)
        reg = devices.list_devices()
        self.assertIn(did, reg)
        self.assertNotIn(token, json.dumps(reg))
        self.assertEqual(reg[did]["kind"], "phone")
        self.assertIsNone(devices.pairing(now=1002.0))  # single use
        self.assertEqual(devices.authenticate(token)[0], did)
        self.assertIsNone(devices.authenticate("nope"))

    def test_wrong_codes_burn_the_pairing(self):
        devices.open_pairing(now=1000.0)
        for _ in range(devices.PAIR_MAX_ATTEMPTS):
            with self.assertRaises(devices.PairError):
                devices.pair("WRONG1", "x", "phone", now=1001.0)
        self.assertIsNone(devices.pairing(now=1001.0))
        with self.assertRaises(devices.PairError):
            devices.pair("WRONG1", "x", "phone", now=1001.0)

    def test_code_expires(self):
        code = devices.open_pairing(now=1000.0)
        with self.assertRaises(devices.PairError):
            devices.pair(code, "x", "phone", now=1000.0 + devices.PAIR_TTL_S + 1)

    def test_forget_makes_a_dead_key(self):
        code = devices.open_pairing()
        did, token = devices.pair(code, "phone", "phone")
        self.assertTrue(devices.forget(did))
        self.assertIsNone(devices.authenticate(token))
        self.assertFalse(devices.forget(did))

    def test_listen_only_when_someone_to_listen_for(self):
        self.assertFalse(devices.should_listen(now=1000.0))
        code = devices.open_pairing(now=1000.0)
        self.assertTrue(devices.should_listen(now=1000.0))
        self.assertFalse(devices.should_listen(now=1000.0 + devices.PAIR_TTL_S + 1))
        devices.pair(code, "p", "phone", now=1001.0)
        self.assertTrue(devices.should_listen(now=99999999.0))

    def test_a_phone_is_capped_at_approve(self):
        for kind in devices.KINDS:
            self.assertEqual(policy.effective_mode(policy.LIVE, kind), policy.APPROVE)


class BridgeTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name
        self.b = bridge.Bridge(host="127.0.0.1", port=0)
        self.b.start()
        self.base = f"http://127.0.0.1:{self.b.bound_port}"

    def tearDown(self):
        self.b.stop()
        if self._old is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old
        self._tmp.cleanup()

    def _req(self, path, body=None, token=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def _pair(self):
        code = devices.open_pairing()
        status, body = self._req("/pair", {"code": code, "name": "Nothing Phone 3", "kind": "phone"})
        self.assertEqual(status, 200)
        return body["device"], body["token"]

    def test_health_is_open_and_says_little(self):
        status, body = self._req("/health")
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"her", "name", "alive", "pairing_open"})

    def test_unpaired_is_refused(self):
        self.assertEqual(self._req("/v1/presence")[0], 401)
        self.assertEqual(self._req("/v1/say", {"text": "hi"})[0], 401)
        self.assertEqual(self._req("/pair", {"code": "ABC123", "name": "x", "kind": "phone"})[0], 403)

    def test_say_lands_in_inbox_with_untrusted_source(self):
        did, token = self._pair()
        status, body = self._req("/v1/say", {"text": "what is in my downloads", "reply_to": "name"}, token)
        self.assertEqual(status, 200)
        cmds = ns.take_commands_full()
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["text"], "what is in my downloads")
        self.assertEqual(cmds[0]["source"], "phone")
        self.assertEqual(cmds[0]["device"], did)
        self.assertEqual(cmds[0]["reply_to"], "name")
        # the source can never be spoofed from the body
        self._req("/v1/say", {"text": "x", "source": "human"}, token)
        self.assertEqual(ns.take_commands_full()[0]["source"], "phone")

    def test_presence_and_answer_are_readable(self):
        did, token = self._pair()
        ns.write_doc("answer", "main", {"text": "I looked in that folder.", "goal": "ls"})
        presence.refresh("test")
        status, body = self._req("/v1/presence", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(body["answer"]["text"], "I looked in that folder.")
        self.assertIn("line", body["presence"])
        self.assertEqual(body["device"], did)
        self.assertEqual(self._req("/v1/answer", token=token)[1]["answer"]["goal"], "ls")

    def test_token_in_query_works_for_the_glasses_page(self):
        did, token = self._pair()
        status, body = self._req(f"/v1/presence?t={token}")
        self.assertEqual(status, 200)
        with urllib.request.urlopen(self.base + "/glasses/", timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertIn(b"Her", r.read())

    def test_forgotten_device_is_a_dead_key(self):
        did, token = self._pair()
        devices.forget(did)
        self.assertEqual(self._req("/v1/presence", token=token)[0], 401)
        self.assertEqual(self._req("/v1/say", {"text": "hi"}, token)[0], 401)
        self.assertEqual(ns.take_commands(), [])

    def test_oversized_and_junk_bodies_are_refused(self):
        did, token = self._pair()
        req = urllib.request.Request(self.base + "/v1/say", data=b"{not json",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {token}"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(cm.exception.code, 400)

    def test_reconcile_binds_only_when_needed(self):
        b = bridge.Bridge(host="127.0.0.1", port=0)
        self.assertFalse(b.reconcile())
        devices.open_pairing()
        self.assertTrue(b.reconcile())
        devices.close_pairing()
        self.assertFalse(b.reconcile())

    # --- the phone page ---------------------------------------------------

    def test_phone_page_is_served_at_her_with_and_without_slash(self):
        for path in ("/her", "/her/"):
            with urllib.request.urlopen(self.base + path, timeout=5) as r:
                self.assertEqual(r.status, 200)
                self.assertTrue(r.headers["Content-Type"].startswith("text/html"))
                page = r.read()
            self.assertIn(b"Pair this phone", page)
            self.assertIn(b"/v1/presence", page)  # it reads the same snapshot every surface does

    # --- history and today's counts, over the journal ---------------------

    def _turn(self, text, answer, source="human", device=""):
        ns.log("main", "command_received", text=text, source=source, device=device)
        if answer is not None:
            ns.log("main", "answered", text=answer, source=source)

    def test_history_pairs_each_ask_with_the_answer_that_follows(self):
        did, token = self._pair()
        ns.log("main", "answered", text="Hello, I am Zero.")           # the greeting: no ask to pair with
        self._turn("what is in my downloads", "Three files.")
        self._turn("check the backup drive", "Still there.", source="scheduler")  # not yours: hidden
        self._turn("and my desktop", None, source="phone", device=did)  # still thinking
        status, body = self._req("/v1/history", token=token)
        self.assertEqual(status, 200)
        self.assertEqual([t["text"] for t in body], ["what is in my downloads", "and my desktop"])
        first, last = body
        self.assertEqual(first["answer"], "Three files.")
        self.assertGreaterEqual(first["answer_ts"], first["ts"])
        self.assertEqual(first["source"], "human")
        self.assertEqual(last["source"], "phone")
        self.assertEqual(last["device"], did)
        self.assertIsNone(last["answer"])
        self.assertIsNone(last["answer_ts"])
        self.assertEqual(set(first), {"ts", "text", "source", "device", "answer", "answer_ts"})

    def test_history_limit_and_auth(self):
        did, token = self._pair()
        for i in range(5):
            self._turn(f"ask {i}", f"answer {i}")
        self.assertEqual(self._req("/v1/history?limit=2")[0], 401)
        status, body = self._req("/v1/history?limit=2", token=token)
        self.assertEqual([t["text"] for t in body], ["ask 3", "ask 4"])
        status, body = self._req("/v1/history?limit=junk", token=token)
        self.assertEqual(len(body), 5)
        self.assertEqual(len(bridge.history(limit=0)), 1)               # clamped, never empty by accident
        self.assertLessEqual(len(bridge.history(limit=10 ** 6)), bridge.HISTORY_MAX)

    def test_snapshot_carries_the_last_eight_turns_and_todays_counts(self):
        did, token = self._pair()
        for i in range(10):
            self._turn(f"ask {i}", f"answer {i}")
        ns.log("executor", "executed", tool="write_file")
        ns.log("executor", "shadowed", tool="write_file", tier="write", mode="shadow")
        ns.log("executor", "shadowed", tool="write_file", tier="write", mode="approve")
        ns.log("executor", "shadowed", tool="write_file", tier="write", mode="approve")
        status, body = self._req("/v1/presence", token=token)
        self.assertEqual(status, 200)
        self.assertEqual([t["text"] for t in body["history"]], [f"ask {i}" for i in range(2, 10)])
        self.assertEqual(body["today"],
                         {"asks": 10, "answered": 10, "executed": 1, "shadowed": 1, "held": 2})

    def test_today_is_the_local_day_and_the_view_follows_the_journal(self):
        self._turn("morning ask", "done", source="human")
        self._turn("timer", "done", source="scheduler")   # scheduled: never one of your asks
        now = time.time()
        self.assertEqual(bridge.today_counts(now)["asks"], 1)
        self.assertEqual(bridge.today_counts(now)["answered"], 2)
        # the same journal seen from two days later: nothing happened "today"
        self.assertEqual(bridge.today_counts(now + 2 * 86400),
                         {"asks": 0, "answered": 0, "executed": 0, "shadowed": 0, "held": 0})
        self.assertEqual(len(bridge.history(now=now + 2 * 86400)), 1)  # but the scrollback keeps it
        # a new line invalidates the cached pass
        self._turn("second ask", "done")
        self.assertEqual(bridge.today_counts(now)["asks"], 2)
        self.assertEqual(bridge.history(now=now)[-1]["text"], "second ask")

    def test_empty_journal_gives_an_empty_history(self):
        self.assertEqual(bridge.history(), [])
        self.assertEqual(bridge.today_counts()["asks"], 0)


class PrivateAddressGateTestCase(unittest.TestCase):
    # Tailscale addresses are 100.64.0.0/10 (CGNAT); docs/reaching-zero.md
    # recommends that mesh, so the gate must let it in (docs/her-lineage.md).

    def test_home_and_tailscale_addresses_are_private(self):
        for addr in ("127.0.0.1", "192.168.1.7", "10.0.0.5", "172.16.3.4", "::1", "fe80::1%en0",
                     "100.64.0.1", "100.100.1.2", "100.127.255.254"):
            self.assertTrue(bridge._is_private(addr), addr)

    def test_the_internet_is_not(self):
        for addr in ("8.8.8.8", "1.1.1.1", "100.63.255.255", "100.128.0.0", "2606:4700::1111",
                     "not an address", ""):
            self.assertFalse(bridge._is_private(addr), addr)

    def test_gate_refuses_by_client_address(self):
        class FakeHandler(bridge.Handler):
            def __init__(self, addr):
                self.client_address = (addr, 5)
                self.replies = []

            def _json(self, code, body):
                self.replies.append((code, body))

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("ZERO_ROOT")
            os.environ["ZERO_ROOT"] = tmp
            try:
                self.assertTrue(FakeHandler("100.100.1.2")._gate())
                h = FakeHandler("8.8.8.8")
                self.assertFalse(h._gate())
                self.assertEqual(h.replies[0][0], 403)
                self.assertIn("refused", [e["event"] for e in ns.read_journal()])
            finally:
                if old is None:
                    os.environ.pop("ZERO_ROOT", None)
                else:
                    os.environ["ZERO_ROOT"] = old


if __name__ == "__main__":
    unittest.main()

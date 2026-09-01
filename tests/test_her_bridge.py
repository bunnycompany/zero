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


if __name__ == "__main__":
    unittest.main()

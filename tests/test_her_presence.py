# zero/tests/test_her_presence.py
#
# Presence and the speech ladder. The invariants that matter:
#   - a fresh install is quiet by construction (nothing to say, nothing said)
#   - quiet never delivers; digest delivers one a day; ambient raises the dot;
#     live needs a precision record or it degrades to ambient
#   - Her can never write her own level
#   - triggers are rules over files, not judgment, and are deduplicated

import os
import tempfile
import time
import unittest

from her import intake, presence
from zero import memory, ns, nspath, scheduler


def _set_level(lv):
    p = nspath.state("presence_level")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(lv + "\n")  # a human with echo


class PresenceTestCase(unittest.TestCase):
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

    def _fact(self, text, subject, origin=""):
        memory.append_fact({"id": f"f{abs(hash(text)) % 10**6}", "text": text, "subject": subject,
                            "importance": 8, "ts_observed": time.time(), "ts_invalidated": None,
                            "last_accessed": time.time(), "origin": origin, "speaker": "user"})

    def test_default_level_is_quiet_and_unknown_fails_closed(self):
        self.assertEqual(presence.level(), "quiet")
        _set_level("LOUD")
        self.assertEqual(presence.level(), "quiet")
        _set_level("ambient")
        self.assertEqual(presence.level(), "ambient")

    def test_her_can_never_write_her_own_level(self):
        for writer in ("her", "main", "bridge", "brain"):
            with self.assertRaises(ns.OwnerViolation):
                ns.write_text("presence_level", "live", writer=writer)

    def test_fresh_install_is_silent_by_construction(self):
        p = presence.refresh("test", now=time.time())
        self.assertEqual(presence.entries(), [])
        self.assertFalse(p["attention"])
        self.assertIn("Nothing needs you", p["line"])
        self.assertLessEqual(len(p["glance"]), presence.GLANCE_CHARS)
        # and the first question is opened as part of presence — level 0 asking
        self.assertEqual(p["question"]["id"], "name")

    def test_quiet_logs_but_never_delivers(self):
        eid = presence.would_say("You told me Theo's birthday is Saturday.", "date", "date:x")
        self.assertIsNotNone(eid)
        p = presence.refresh("test")
        self.assertNotIn("Theo", p["line"])
        self.assertFalse(p["attention"])
        self.assertEqual(presence._delivered_ids(), set())
        self.assertEqual(len(presence.unreviewed()), 1)

    def test_would_say_is_deduplicated_per_key_per_day(self):
        now = time.time()
        self.assertIsNotNone(presence.would_say("a", "t", "k", now=now))
        self.assertIsNone(presence.would_say("a again", "t", "k", now=now + 60))
        self.assertIsNotNone(presence.would_say("a", "t", "k", now=now + presence.DEDUP_WINDOW_S + 1))

    def test_digest_delivers_one_a_day(self):
        _set_level("digest")
        now = time.time()
        presence.would_say("first thing", "t", "k1", now=now)
        p = presence.refresh("t", now=now)
        self.assertIn("first thing", p["line"])
        self.assertFalse(p["attention"])           # digest never raises the dot
        presence.would_say("second thing", "t", "k2", now=now + 10)
        p = presence.refresh("t", now=now + 20)
        self.assertNotIn("second thing", p["line"])  # today's one is spent
        self.assertEqual(len(presence._delivered_ids()), 1)

    def test_ambient_raises_attention(self):
        _set_level("ambient")
        presence.would_say("something", "t", "k")
        p = presence.refresh("t")
        self.assertTrue(p["attention"])
        self.assertEqual(p["glance"], "something")

    def test_live_degrades_to_ambient_without_a_precision_record(self):
        _set_level("live")
        self.assertEqual(presence.delivery_level(), "ambient")
        for i in range(presence.LIVE_MIN_REVIEWED):
            eid = presence.would_say(f"t{i}", "t", f"k{i}")
            presence.review(eid, wanted=(i % 10 != 0))  # 90% wanted
        n, prec = presence.precision()
        self.assertEqual(n, presence.LIVE_MIN_REVIEWED)
        self.assertGreaterEqual(prec, presence.LIVE_MIN_PRECISION)
        self.assertEqual(presence.delivery_level(), "live")

    def test_live_with_bad_precision_stays_ambient(self):
        _set_level("live")
        for i in range(presence.LIVE_MIN_REVIEWED + 5):
            eid = presence.would_say(f"t{i}", "t", f"k{i}")
            presence.review(eid, wanted=(i % 2 == 0))  # 50%
        self.assertEqual(presence.delivery_level(), "ambient")

    def test_date_trigger_within_a_week_in_the_users_words(self):
        now = time.time()
        soon = time.localtime(now + 3 * 86400)
        mon = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"][soon.tm_mon - 1]
        self._fact(f"Dates that matter: Theo's birthday {soon.tm_mday} {mon}", "dates", "intake:dates")
        self._fact("Dates that matter: something on 1 jan 2099", "dates", "intake:dates")
        found = presence.date_triggers(now)
        self.assertEqual(len([t for t in found if "Theo" in t[0]]), 1)
        self.assertIn("in 3 days", found[0][0])
        p = presence.refresh("t", now=now)
        self.assertEqual(len(presence.entries()), 1)  # logged, once
        self.assertNotIn("Theo", p["line"])           # quiet: not delivered

    def test_repeat_ask_trigger(self):
        for _ in range(presence.REPEAT_ASK_MIN):
            ns.log("main", "command_received", text="what is in the scripts folder", source="human")
        ns.log("main", "command_received", text="what is in the scripts folder", source="scheduler")
        found = presence.repeat_triggers(time.time())
        self.assertEqual(len(found), 1)
        self.assertIn("3 times", found[0][0])  # scheduler asks don't count

    def test_schedule_trigger_within_the_hour(self):
        now = time.time()
        scheduler.add("water the plants", now + 600)
        scheduler.add("far away", now + 7200)
        found = presence.schedule_triggers(now)
        self.assertEqual(len(found), 1)
        self.assertIn("water the plants", found[0][0])

    def test_observer_death_is_confessed(self):
        now = time.time()
        ns.write_doc("context", "observer", {"app": "Mail"})
        self.assertFalse(presence.observer_down(now))
        self.assertTrue(presence.observer_down(now + presence.OBSERVER_STALE_S + 1))
        p = presence.refresh("t", now=now + presence.OBSERVER_STALE_S + 1)
        self.assertIn("watches the screen has stopped", p["line"])

    def test_refresh_only_writes_on_change(self):
        now = time.time()
        presence.refresh("a", now=now)
        m1 = nspath.state("her/presence").stat().st_mtime_ns
        time.sleep(0.01)
        presence.refresh("b", now=now + 1)
        self.assertEqual(nspath.state("her/presence").stat().st_mtime_ns, m1)

    def test_greeting_uses_the_name_you_gave(self):
        intake.next_question(now=time.time())
        intake.turn({"text": "Dal", "reply_to": "name"})
        memory.drain_observations()
        self.assertEqual(presence.user_name(), "Dal")
        self.assertIn("Dal", presence.refresh("t")["line"])


if __name__ == "__main__":
    unittest.main()

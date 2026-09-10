# zero/tests/test_timeparse.py
#
# US-021: "at six" and "tomorrow morning" just work. The parser is pure, so
# every case pins `now` and the timezone; the DST and year-boundary cases are
# the ones a naive "add 86400" would get wrong.

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from zero import nspath, scheduler, timeparse

REPO = Path(__file__).resolve().parents[1]


def _tz(name):
    old = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    return old


def _restore_tz(old):
    if old is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old
    time.tzset()


def mk(y, mo, d, h=0, mi=0):
    """Local wall-clock -> unix, under the TZ currently in force."""
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


def wall(at):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(at))


class TzCase(unittest.TestCase):
    TZ = "America/New_York"

    def setUp(self):
        self._old_tz = _tz(self.TZ)

    def tearDown(self):
        _restore_tz(self._old_tz)


class TimeparseTests(TzCase):
    # Thursday 10 September 2026, 09:00 local
    NOW = None

    def setUp(self):
        super().setUp()
        self.now = mk(2026, 9, 10, 9, 0)
        self.evening = mk(2026, 9, 10, 20, 0)

    def at(self, text, now=None):
        a, e, rem = timeparse.parse(text, self.now if now is None else now)
        return wall(a), e, rem

    # -- relative -----------------------------------------------------------

    def test_in_units(self):
        self.assertEqual(self.at("call mom in 2h"), ("2026-09-10 11:00", None, "call mom"))
        self.assertEqual(self.at("in 30 min"), ("2026-09-10 09:30", None, ""))
        self.assertEqual(self.at("in 3 days"), ("2026-09-13 09:00", None, ""))
        self.assertEqual(self.at("in an hour"), ("2026-09-10 10:00", None, ""))
        self.assertEqual(self.at("in half an hour"), ("2026-09-10 09:30", None, ""))
        self.assertEqual(self.at("in two weeks"), ("2026-09-24 09:00", None, ""))
        self.assertEqual(self.at("in 90 minutes"), ("2026-09-10 10:30", None, ""))

    def test_relative_is_exact_seconds_not_wall_clock(self):
        a, _, _ = timeparse.parse("in 24h", self.now)
        self.assertEqual(a - self.now, 86400)

    # -- clock, next occurrence ----------------------------------------------

    def test_bare_hour_picks_the_next_occurrence(self):
        self.assertEqual(self.at("call mom at 6"), ("2026-09-10 18:00", None, "call mom"))
        self.assertEqual(self.at("call mom at six"), ("2026-09-10 18:00", None, "call mom"))
        self.assertEqual(self.at("call mom at 6", self.evening), ("2026-09-11 06:00", None, "call mom"))
        self.assertEqual(self.at("at 10"), ("2026-09-10 10:00", None, ""))
        self.assertEqual(self.at("at 8"), ("2026-09-10 20:00", None, ""))
        self.assertEqual(self.at("at 8", self.evening), ("2026-09-11 08:00", None, ""))
        self.assertEqual(self.at("at 6:30"), ("2026-09-10 18:30", None, ""))
        self.assertEqual(self.at("at 6:30", self.evening), ("2026-09-11 06:30", None, ""))
        self.assertEqual(self.at("at 12"), ("2026-09-10 12:00", None, ""))
        self.assertEqual(self.at("at 12", self.evening), ("2026-09-11 00:00", None, ""))

    def test_explicit_clock(self):
        self.assertEqual(self.at("at 6pm"), ("2026-09-10 18:00", None, ""))
        self.assertEqual(self.at("at 6 pm"), ("2026-09-10 18:00", None, ""))
        self.assertEqual(self.at("at 6am"), ("2026-09-11 06:00", None, ""))   # already past
        self.assertEqual(self.at("at 6pm", self.evening), ("2026-09-11 18:00", None, ""))
        self.assertEqual(self.at("at 18:30"), ("2026-09-10 18:30", None, ""))
        self.assertEqual(self.at("at 07:15"), ("2026-09-11 07:15", None, ""))
        self.assertEqual(self.at("at 12pm"), ("2026-09-10 12:00", None, ""))
        self.assertEqual(self.at("at 12am"), ("2026-09-11 00:00", None, ""))
        self.assertEqual(self.at("at 6 in the evening"), ("2026-09-10 18:00", None, ""))
        self.assertEqual(self.at("at 6 in the morning"), ("2026-09-11 06:00", None, ""))
        self.assertEqual(self.at("at 9 at night"), ("2026-09-10 21:00", None, ""))
        self.assertEqual(self.at("at noon"), ("2026-09-10 12:00", None, ""))
        self.assertEqual(self.at("at noon", self.evening), ("2026-09-11 12:00", None, ""))
        self.assertEqual(self.at("at midnight"), ("2026-09-11 00:00", None, ""))
        self.assertEqual(self.at("at midnight", self.evening), ("2026-09-11 00:00", None, ""))

    def test_last_time_phrase_wins(self):
        self.assertEqual(self.at("look at 3 files at 6"), ("2026-09-10 18:00", None, "look at 3 files"))

    # -- day words ----------------------------------------------------------

    def test_day_words_with_defaults(self):
        self.assertEqual(self.at("tomorrow at 9"), ("2026-09-11 09:00", None, ""))
        self.assertEqual(self.at("tomorrow at 6"), ("2026-09-11 18:00", None, ""))
        self.assertEqual(self.at("tomorrow at 6am"), ("2026-09-11 06:00", None, ""))
        self.assertEqual(self.at("tomorrow 9am"), ("2026-09-11 09:00", None, ""))
        self.assertEqual(self.at("water the plants tomorrow morning"),
                         ("2026-09-11 09:00", None, "water the plants"))
        self.assertEqual(self.at("tomorrow afternoon"), ("2026-09-11 15:00", None, ""))
        self.assertEqual(self.at("tomorrow evening"), ("2026-09-11 18:00", None, ""))
        self.assertEqual(self.at("tomorrow night"), ("2026-09-11 20:00", None, ""))
        self.assertEqual(self.at("tomorrow"), ("2026-09-11 09:00", None, ""))
        self.assertEqual(self.at("tonight"), ("2026-09-10 20:00", None, ""))
        self.assertEqual(self.at("this evening"), ("2026-09-10 18:00", None, ""))
        self.assertEqual(self.at("this afternoon"), ("2026-09-10 15:00", None, ""))
        self.assertEqual(self.at("at 9 in the morning tomorrow"), ("2026-09-11 09:00", None, ""))

    def test_this_evening_said_late_is_soon_not_tomorrow(self):
        late = mk(2026, 9, 10, 23, 0)
        a, e, rem = timeparse.parse("tonight", late)
        self.assertTrue(late < a <= late + 120)

    def test_weekdays(self):
        # now is a Thursday
        self.assertEqual(self.at("on friday"), ("2026-09-11 09:00", None, ""))
        self.assertEqual(self.at("on wednesday"), ("2026-09-16 09:00", None, ""))
        self.assertEqual(self.at("on thursday"), ("2026-09-17 09:00", None, ""))
        self.assertEqual(self.at("on thursday at 3"), ("2026-09-10 15:00", None, ""))  # still ahead today
        self.assertEqual(self.at("next thursday"), ("2026-09-17 09:00", None, ""))
        self.assertEqual(self.at("next monday at 10"), ("2026-09-14 10:00", None, ""))
        self.assertEqual(self.at("next monday at 6"), ("2026-09-14 18:00", None, ""))
        self.assertEqual(self.at("stand up tuesday"), ("2026-09-15 09:00", None, "stand up"))
        self.assertEqual(self.at("on sat morning"), ("2026-09-12 09:00", None, ""))
        self.assertEqual(self.at("this thursday at 4"), ("2026-09-10 16:00", None, ""))

    def test_short_weekday_names_need_a_preposition(self):
        self.assertEqual(timeparse.parse("sit in the sun", self.now), (None, None, "sit in the sun"))
        self.assertEqual(timeparse.parse("where I sat", self.now), (None, None, "where I sat"))

    # -- recurring ----------------------------------------------------------

    def test_every(self):
        self.assertEqual(self.at("every day at 8"), ("2026-09-11 08:00", 86400, ""))
        self.assertEqual(self.at("every day at 6"), ("2026-09-10 18:00", 86400, ""))
        self.assertEqual(self.at("every morning"), ("2026-09-11 08:00", 86400, ""))
        self.assertEqual(self.at("every evening"), ("2026-09-10 18:00", 86400, ""))
        self.assertEqual(self.at("every night"), ("2026-09-10 20:00", 86400, ""))
        self.assertEqual(self.at("every day at noon"), ("2026-09-10 12:00", 86400, ""))
        self.assertEqual(self.at("daily at noon"), ("2026-09-10 12:00", 86400, ""))
        self.assertEqual(self.at("every thursday at 3pm"), ("2026-09-10 15:00", 604800, ""))
        self.assertEqual(self.at("every monday at 10"), ("2026-09-14 10:00", 604800, ""))
        self.assertEqual(self.at("every tuesday morning"), ("2026-09-15 08:00", 604800, ""))
        self.assertEqual(self.at("every 2 hours"), ("2026-09-10 11:00", 7200, ""))
        self.assertEqual(self.at("every hour"), ("2026-09-10 10:00", 3600, ""))
        self.assertEqual(self.at("every 1d review evals"), ("2026-09-11 09:00", 86400, "review evals"))
        self.assertEqual(self.at("every week"), ("2026-09-17 09:00", 604800, ""))

    def test_every_weekday_is_daily_with_a_note(self):
        p = timeparse.parse_full("every weekday at 9", self.now)
        self.assertEqual((wall(p.at), p.every), ("2026-09-11 09:00", 86400))
        self.assertTrue(p.note)
        self.assertIn(p.note, timeparse.describe(p.at, p.every, self.now, note=p.note))

    # -- nothing understood ---------------------------------------------------

    def test_no_time_leaves_the_text_alone(self):
        self.assertEqual(timeparse.parse("just some words", self.now), (None, None, "just some words"))
        self.assertEqual(timeparse.parse("", self.now), (None, None, ""))
        self.assertEqual(timeparse.parse("put it in a box", self.now), (None, None, "put it in a box"))

    # -- DST and year boundaries ---------------------------------------------

    def test_spring_forward_keeps_the_wall_clock(self):
        # US DST starts 2026-03-08 at 02:00 local
        now = mk(2026, 3, 7, 9, 0)
        a, _, _ = timeparse.parse("tomorrow at 9", now)
        self.assertEqual(wall(a), "2026-03-08 09:00")
        self.assertEqual(a - now, 23 * 3600)          # one hour shorter on the clock
        a, _, _ = timeparse.parse("in 24h", now)
        self.assertEqual(wall(a), "2026-03-08 10:00")  # exact seconds, so the wall moves
        a, e, _ = timeparse.parse("every day at 8", now)
        self.assertEqual((wall(a), e), ("2026-03-08 08:00", 86400))
        a, _, _ = timeparse.parse("at 2:30am", mk(2026, 3, 8, 1, 0))
        self.assertTrue(a > mk(2026, 3, 8, 1, 0))     # a time that does not exist still lands ahead

    def test_fall_back_keeps_the_wall_clock(self):
        # US DST ends 2026-11-01 at 02:00 local
        now = mk(2026, 10, 31, 9, 0)
        a, _, _ = timeparse.parse("tomorrow at 9", now)
        self.assertEqual(wall(a), "2026-11-01 09:00")
        self.assertEqual(a - now, 25 * 3600)
        a, _, _ = timeparse.parse("next monday at 10", now)
        self.assertEqual(wall(a), "2026-11-02 10:00")
        a, _, _ = timeparse.parse("at 6", mk(2026, 10, 31, 20, 0))
        self.assertEqual(wall(a), "2026-11-01 06:00")

    def test_year_boundary(self):
        now = mk(2025, 12, 31, 23, 30)   # a Wednesday
        self.assertEqual(self.at("in an hour", now)[0], "2026-01-01 00:30")
        self.assertEqual(self.at("tomorrow at 9", now)[0], "2026-01-01 09:00")
        self.assertEqual(self.at("at 6", now)[0], "2026-01-01 06:00")
        self.assertEqual(self.at("at midnight", now)[0], "2026-01-01 00:00")
        self.assertEqual(self.at("next monday at 10", now)[0], "2026-01-05 10:00")
        self.assertEqual(self.at("on thursday", now)[0], "2026-01-01 09:00")
        self.assertEqual(self.at("every morning", now), ("2026-01-01 08:00", 86400, ""))
        self.assertEqual(self.at("in 3 days", now)[0], "2026-01-03 23:30")

    def test_month_boundary_and_leap_day(self):
        self.assertEqual(self.at("in 3 days", mk(2026, 9, 30, 9))[0], "2026-10-03 09:00")
        self.assertEqual(self.at("tomorrow at 9", mk(2028, 2, 28, 9))[0], "2028-02-29 09:00")
        self.assertEqual(self.at("tomorrow at 9", mk(2027, 2, 28, 9))[0], "2027-03-01 09:00")

    def test_same_rules_in_other_timezones(self):
        for tz in ("Europe/Berlin", "Asia/Kolkata", "UTC", "Pacific/Auckland"):
            old = _tz(tz)
            try:
                now = mk(2026, 9, 10, 9, 0)
                self.assertEqual(self.at("at 6", now)[0], "2026-09-10 18:00", tz)
                self.assertEqual(self.at("at 6", mk(2026, 9, 10, 20))[0], "2026-09-11 06:00", tz)
                self.assertEqual(self.at("tomorrow morning", now)[0], "2026-09-11 09:00", tz)
                self.assertEqual(self.at("every day at 8", now), ("2026-09-11 08:00", 86400, ""), tz)
            finally:
                _restore_tz(old)

    # -- saying it back --------------------------------------------------------

    def test_describe(self):
        def say(text, now=None):
            now = self.now if now is None else now
            p = timeparse.parse_full(text, now)
            return timeparse.describe(p.at, p.every, now, relative=p.relative, note=p.note)
        self.assertEqual(say("at six"), "at 6 this evening")
        self.assertEqual(say("at six", self.evening), "at 6 tomorrow morning")
        self.assertEqual(say("at 18:30"), "at 6:30 this evening")
        self.assertEqual(say("tomorrow morning"), "at 9 tomorrow morning")
        self.assertEqual(say("tonight"), "at 8 tonight")
        self.assertEqual(say("at noon"), "at noon today")
        self.assertEqual(say("at midnight"), "at midnight tonight")
        self.assertEqual(say("next monday at 10"), "at 10 on Monday morning")
        self.assertEqual(say("on thursday"), "at 9 next Thursday morning")
        self.assertEqual(say("in 30 min"), "in 30 minutes")
        self.assertEqual(say("in 2h"), "in 2 hours")
        self.assertEqual(say("in an hour"), "in an hour")
        self.assertEqual(say("in 3 days"), "in 3 days")
        self.assertEqual(say("every day at 8"), "every day at 8 in the morning")
        self.assertEqual(say("every morning"), "every day at 8 in the morning")
        self.assertEqual(say("every weekday at 9"), "every day at 9 in the morning, weekends included for now")
        self.assertEqual(say("every thursday at 3pm"), "every Thursday at 3 in the afternoon")
        self.assertEqual(say("every hour"), "every hour")
        self.assertEqual(say("every 2 hours"), "every 2 hours")
        self.assertEqual(say("tonight", mk(2026, 9, 10, 23)), "in a minute")


class SandboxCase(TzCase):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_root = os.environ.get("ZERO_ROOT")
        os.environ["ZERO_ROOT"] = self._tmp.name

    def tearDown(self):
        if self._old_root is None:
            os.environ.pop("ZERO_ROOT", None)
        else:
            os.environ["ZERO_ROOT"] = self._old_root
        self._tmp.cleanup()
        super().tearDown()

    def tasks(self):
        p = nspath.schedule()
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class RemindTests(SandboxCase):
    """scheduler.remind is what `zero remind|at|every` and `her remind|every` call."""

    def setUp(self):
        super().setUp()
        self.now = mk(2026, 9, 10, 9, 0)

    def test_remind_call_mom_at_six(self):
        msg = scheduler.remind("remind", "call mom at six", self.now)
        self.assertEqual(msg, "  ok — I will bring up 'call mom' at 6 this evening.")
        t = self.tasks()
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]["text"], "call mom")
        self.assertEqual(wall(t[0]["at"]), "2026-09-10 18:00")
        self.assertIsNone(t[0]["every"])
        self.assertEqual(t[0]["source"], "scheduler")

    def test_remind_me_to_strips_the_filler(self):
        msg = scheduler.remind("remind", "me to water the plants tomorrow morning", self.now)
        self.assertEqual(msg, "  ok — I will bring up 'water the plants' at 9 tomorrow morning.")
        self.assertEqual(self.tasks()[0]["text"], "water the plants")
        self.assertEqual(wall(self.tasks()[0]["at"]), "2026-09-11 09:00")

    def test_at_and_every_verbs(self):
        scheduler.remind("at", "6pm call mom", self.now)
        scheduler.remind("every", "morning check the backups", self.now)
        scheduler.remind("every", "1d review evals", self.now)   # the old spelling still works
        t = self.tasks()
        self.assertEqual([x["text"] for x in t], ["call mom", "check the backups", "review evals"])
        self.assertEqual(wall(t[0]["at"]), "2026-09-10 18:00")
        self.assertEqual((wall(t[1]["at"]), t[1]["every"]), ("2026-09-11 08:00", 86400))
        self.assertEqual(t[2]["every"], 86400)

    def test_nothing_to_bring_up_schedules_nothing(self):
        msg = scheduler.remind("remind", "at six", self.now)
        self.assertIn("what should I remind you", msg)
        self.assertEqual(self.tasks(), [])

    def test_no_time_is_said_out_loud(self):
        msg = scheduler.remind("remind", "buy milk", self.now)
        self.assertIn("shortly", msg)
        self.assertIn("did not catch a time", msg)
        self.assertEqual(wall(self.tasks()[0]["at"]), "2026-09-10 09:00")


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class ZeroScriptTests(SandboxCase):
    """`zero remind call mom at six` end to end, through scripts/zero."""

    def run_zero(self, *args):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)   # the script must find the package on its own
        return subprocess.run(["bash", str(REPO / "scripts" / "zero"), *args],
                              capture_output=True, text=True, env=env, timeout=60)

    def test_remind_call_mom_at_six(self):
        r = self.run_zero("remind", "call", "mom", "at", "six")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("I will bring up 'call mom'", r.stdout)
        self.assertRegex(r.stdout, r"at 6 (this evening|tomorrow morning|this morning)")
        t = self.tasks()
        self.assertEqual(t[0]["text"], "call mom")
        now = time.time()
        self.assertTrue(now < t[0]["at"] <= now + 86400)
        lt = time.localtime(t[0]["at"])
        self.assertIn(lt.tm_hour, (6, 18))
        self.assertEqual(lt.tm_min, 0)

    def test_every_morning(self):
        r = self.run_zero("every", "morning", "check", "the", "backups")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("every day at 8 in the morning", r.stdout)
        self.assertEqual(self.tasks()[0]["every"], 86400)


if __name__ == "__main__":
    unittest.main()

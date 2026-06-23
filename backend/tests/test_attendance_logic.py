"""Unit test for late-arrival calculation without a DB (pure logic check)."""
from datetime import datetime, time, timedelta
import pytz


def compute_late_minutes(now_local, shift_start: time, grace_min: int, tz):
    scheduled = tz.localize(datetime.combine(now_local.date(), shift_start))
    grace = timedelta(minutes=grace_min)
    return max(0, int((now_local - (scheduled + grace)).total_seconds() / 60))


def test_on_time():
    tz = pytz.timezone("Asia/Dhaka")
    now = tz.localize(datetime(2025, 1, 6, 9, 5))   # 9:05, 10-min grace
    assert compute_late_minutes(now, time(9, 0), 10, tz) == 0


def test_late():
    tz = pytz.timezone("Asia/Dhaka")
    now = tz.localize(datetime(2025, 1, 6, 9, 25))  # 25 min after start
    assert compute_late_minutes(now, time(9, 0), 10, tz) == 15

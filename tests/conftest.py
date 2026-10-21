import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flight_tracker.config import parse_config  # noqa: E402
from flight_tracker.storage import Storage  # noqa: E402

TODAY = date(2026, 10, 21)


def base_raw(**trip_overrides):
    trip = {
        "name": "T1",
        "origin": ["YYZ"],
        "destination": ["LHR", "LGW"],
        "trip_type": "round_trip",
        "depart_window": {"start": "2026-11-10", "end": "2026-12-20"},
        "nights": {"min": 7, "max": 12},
        "strategy": {"budget": 40},
    }
    trip.update(trip_overrides)
    return {"currency": "USD", "workers": 4, "trips": [trip], "providers": ["mock"], "notifiers": ["console"]}


@pytest.fixture
def today():
    return TODAY


@pytest.fixture
def cfg():
    return parse_config(base_raw(), today=TODAY)


@pytest.fixture
def storage(tmp_path):
    s = Storage(tmp_path / "t.db")
    yield s
    s.close()

from datetime import date, time

import pytest

from flight_tracker.config import ConfigError, parse_config

from .conftest import TODAY, base_raw


def test_parses_basic(cfg):
    t = cfg.trips[0]
    assert t.origins == ["YYZ"] and t.destinations == ["LHR", "LGW"]
    assert t.is_round_trip and (t.nights_min, t.nights_max) == (7, 12)


def test_relative_dates_and_past_clamped():
    cfg = parse_config(base_raw(depart_window={"start": "2026-01-01", "end": "+30d"}), today=TODAY)
    w = cfg.trips[0].depart_window
    assert w.start == date(2026, 10, 22)  # never before tomorrow
    assert w.end == date(2026, 11, 20)


def test_window_entirely_in_past_fails():
    with pytest.raises(ConfigError, match="past"):
        parse_config(base_raw(depart_window={"start": "2026-01-01", "end": "2026-02-01"}), today=TODAY)


@pytest.mark.parametrize("bad", [
    {"origin": "TORONTO"},
    {"destination": ["YYZ"]},  # same as origin
    {"trip_type": "multi"},
    {"cabin": "luxury"},
    {"nights": {"min": 5, "max": 2}},
    {"typo_key": 1},
    {"filters": {"max_stopz": 1}},
    {"strategy": {"mode": "random"}},
])
def test_invalid(bad):
    with pytest.raises(ConfigError):
        parse_config(base_raw(**bad), today=TODAY)


def test_round_trip_requires_nights():
    raw = base_raw()
    del raw["trips"][0]["nights"]
    with pytest.raises(ConfigError, match="nights"):
        parse_config(raw, today=TODAY)


def test_times_including_yaml_sexagesimal():
    cfg = parse_config(base_raw(filters={"depart_after": 360, "depart_before": "22:30"}), today=TODAY)
    f = cfg.trips[0].filters
    assert f.depart_after == time(6, 0) and f.depart_before == time(22, 30)


def test_one_way_and_lowercase_codes():
    cfg = parse_config(base_raw(trip_type="one_way", origin="yyz"), today=TODAY)
    t = cfg.trips[0]
    assert not t.is_round_trip and t.origins == ["YYZ"]


def test_duplicate_trip_names():
    raw = base_raw()
    raw["trips"].append(dict(raw["trips"][0]))
    with pytest.raises(ConfigError, match="unique"):
        parse_config(raw, today=TODAY)


def test_example_config_is_valid():
    from pathlib import Path

    from flight_tracker.config import load_config
    load_config(Path(__file__).resolve().parents[1] / "config.example.yaml", today=TODAY)


def test_verify_block():
    raw = base_raw()
    raw["verify"] = {"provider": "serpapi", "top_k": 3}
    v = parse_config(raw, today=TODAY).verify
    assert v.provider == "serpapi" and v.top_k == 3
    raw["verify"] = {"provider": "serpapi", "enabled": False}
    assert parse_config(raw, today=TODAY).verify is None
    raw["verify"] = {"top_k": 3}
    with pytest.raises(ConfigError, match="provider"):
        parse_config(raw, today=TODAY)


def test_report_folder_name():
    cfg = parse_config(base_raw(code="T1", from_name="Vancouver", to_name="Kochi"), today=TODAY)
    assert cfg.trips[0].report_folder == "T1 Vancouver - Kochi (Round)"
    cfg = parse_config(base_raw(trip_type="one_way"), today=TODAY)
    assert cfg.trips[0].report_folder == "T1 YYZ - LHR+LGW (One-Way)"


def test_report_folder_defaults_and_validation():
    with pytest.raises(ConfigError, match="code"):
        parse_config(base_raw(code="T 1"), today=TODAY)
    with pytest.raises(ConfigError, match="from_name"):
        parse_config(base_raw(from_name="Vancouver: BC"), today=TODAY)

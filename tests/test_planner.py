from datetime import timedelta

from flight_tracker.config import parse_config
from flight_tracker.planner import PHASE1_SHARE, all_combinations, plan_exhaustive, plan_refine, plan_sample

from .conftest import TODAY, base_raw


def test_all_combinations_count(cfg):
    t = cfg.trips[0]
    days = (t.depart_window.end - t.depart_window.start).days + 1
    assert len(all_combinations(t, "USD")) == days * 6 * 2  # 6 stay lengths x 2 airport pairs


def test_sample_fits_budget_and_covers_window(cfg):
    t = cfg.trips[0]
    qs = plan_sample(t, "USD")
    assert 0 < len(qs) <= t.strategy.budget * PHASE1_SHARE
    deps = sorted({q.depart_date for q in qs})
    assert deps[0] == t.depart_window.start and deps[-1] == t.depart_window.end
    for q in qs:
        assert t.nights_min <= q.nights <= t.nights_max
    assert len({q.key() for q in qs}) == len(qs)


def test_sample_tiny_budget():
    cfg = parse_config(base_raw(strategy={"budget": 1}), today=TODAY)
    assert 1 <= len(plan_sample(cfg.trips[0], "USD")) <= 1


def test_refine_neighbours_of_cheapest(cfg):
    t = cfg.trips[0]
    phase1 = plan_sample(t, "USD")
    cheap = {q.key(): (q, 100.0 + i) for i, q in enumerate(phase1)}
    seed = phase1[0]
    refine = plan_refine(t, "USD", cheap, [q.key() for q in phase1], remaining=10)
    assert 0 < len(refine) <= 10
    keys = {q.key() for q in phase1}
    for q in refine:
        assert q.key() not in keys
        assert t.depart_window.start <= q.depart_date <= t.depart_window.end
        assert t.nights_min <= q.nights <= t.nights_max
    # the closest neighbours of the cheapest seed come first
    first = refine[0]
    assert abs((first.depart_date - seed.depart_date).days) + abs(first.nights - seed.nights) == 1


def test_refine_respects_zero_budget(cfg):
    t = cfg.trips[0]
    q = plan_sample(t, "USD")[0]
    assert plan_refine(t, "USD", {q.key(): (q, 1.0)}, [q.key()], remaining=0) == []


def test_exhaustive_capped_by_budget():
    cfg = parse_config(base_raw(strategy={"mode": "exhaustive", "budget": 25}), today=TODAY)
    assert len(plan_exhaustive(cfg.trips[0], "USD")) == 25


def test_one_way_and_weekdays():
    cfg = parse_config(base_raw(trip_type="one_way", filters={"allowed_weekdays": [1, 2]},
                                strategy={"budget": 200}), today=TODAY)
    qs = plan_sample(cfg.trips[0], "USD")
    assert all(q.return_date is None for q in qs)
    assert all(q.depart_date.weekday() in (1, 2) for q in qs)
    assert all(q.return_date is None or q.return_date - q.depart_date >= timedelta(0) for q in qs)

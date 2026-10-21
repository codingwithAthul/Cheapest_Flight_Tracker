"""Turn a Trip into concrete SearchQuery objects, within a search budget.

Flexible dates explode quickly: a 90-day window x 8 possible stay lengths x
2 origin airports is 1,440 searches, which is too many for any paid API to
run daily. So the planner works in two phases:

Phase 1 ("sample"): searches a coarse grid. That is every Nth departure date,
a few stay lengths spread across the allowed range, and every airport pair.
It uses up to PHASE1_SHARE of the budget, and widens the grid when it would
not fit.

Phase 2 ("zoom"): takes the K cheapest combinations from phase 1 and
searches their unsearched neighbours (+/- radius days on departure and on
stay length), closest first, until the budget runs out. Fares cluster by
date, so this finds the true minimum far more often than random sampling.

With `rotate_daily`, the phase-1 grid shifts by one step each day, so even a
tiny budget covers the whole window within a few days.

`exhaustive` mode skips the phases and searches every combination. When
there are more combinations than the budget allows, it searches an evenly
spaced subset instead.
"""

from __future__ import annotations

import itertools
import math
from datetime import date, timedelta
from typing import Iterable, Optional

from .config import Trip
from .models import SearchQuery

PHASE1_SHARE = 0.6


def _query(trip: Trip, origin: str, dest: str, depart: date, nights: Optional[int], currency: str) -> SearchQuery:
    return SearchQuery(
        trip_name=trip.name,
        origin=origin,
        destination=dest,
        depart_date=depart,
        return_date=(depart + timedelta(days=nights)) if nights is not None else None,
        adults=trip.adults,
        cabin=trip.cabin,
        currency=currency,
        max_stops=trip.filters.max_stops,
    )


def _nights_range(trip: Trip) -> list[Optional[int]]:
    if not trip.is_round_trip:
        return [None]
    return list(range(trip.nights_min, trip.nights_max + 1))


def _depart_days(trip: Trip) -> list[date]:
    days = trip.depart_window.days()
    if trip.filters.allowed_weekdays:
        days = [d for d in days if d.weekday() in trip.filters.allowed_weekdays]
    return days


def _pairs(trip: Trip) -> list[tuple[str, str]]:
    return list(itertools.product(trip.origins, trip.destinations))


def _spread(items: list, n: int) -> list:
    """Pick n items evenly spread across the list, always including both ends."""
    if n >= len(items):
        return list(items)
    if n <= 1:
        return [items[len(items) // 2]] if n == 1 else []
    step = (len(items) - 1) / (n - 1)
    idx = sorted({round(i * step) for i in range(n)})
    return [items[i] for i in idx]


def all_combinations(trip: Trip, currency: str) -> list[SearchQuery]:
    return [
        _query(trip, o, d, dep, n, currency)
        for (o, d) in _pairs(trip)
        for dep in _depart_days(trip)
        for n in _nights_range(trip)
    ]


def plan_exhaustive(trip: Trip, currency: str) -> list[SearchQuery]:
    combos = all_combinations(trip, currency)
    return _spread(combos, trip.strategy.budget)


def plan_sample(trip: Trip, currency: str, rotation: int = 0) -> list[SearchQuery]:
    """Phase 1 coarse grid that fits within PHASE1_SHARE of the budget.

    `rotation` (e.g. the run date's ordinal) shifts the grid each day, so a small daily budget
    still covers every departure date and stay length over a few days instead of re-checking the same ones.
    """
    s = trip.strategy
    pairs = _pairs(trip)
    days = _depart_days(trip)
    nights_all = _nights_range(trip)
    if not days:
        return []
    allowance = max(1, math.floor(s.budget * PHASE1_SHARE))

    n_nights = min(s.nights_samples, len(nights_all))
    every = s.sample_every_days
    while True:
        sampled_days = days[rotation % every::every] if rotation else days[::every]
        if not rotation and days[-1] not in sampled_days:
            sampled_days.append(days[-1])
        # With rotation, size the grid by its largest possible slice so the step is the same every day.
        n_days = math.ceil(len(days) / every) if rotation else len(sampled_days)
        size = len(pairs) * n_days * n_nights
        if size <= allowance:
            break
        # Shrink stay-length samples first (fares vary less by stay than by date), then widen date step.
        if n_nights > 1 and len(pairs) * n_days * (n_nights - 1) >= allowance * 0.5:
            n_nights -= 1
        elif every < len(days):
            every += 1
        elif n_nights > 1:
            n_nights -= 1
        else:
            # Even one date per pair does not fit: keep as many pairs as we can afford.
            pairs = pairs[:allowance]
            sampled_days = [days[len(days) // 2]]
            break
    nights = _spread(nights_all, n_nights)
    if rotation and n_nights < len(nights_all):
        windows = max(1, len(nights_all) - n_nights + 1)
        offset = (rotation // every) % windows
        nights = _spread(nights_all[offset:offset + max(n_nights, len(nights_all) - windows + 1)], n_nights)
    return [
        _query(trip, o, d, dep, n, currency)
        for (o, d) in pairs
        for dep in sampled_days
        for n in nights
    ]


def plan_refine(
    trip: Trip,
    currency: str,
    cheapest_by_query: dict[str, tuple[SearchQuery, float]],
    already: Iterable[str],
    remaining: int,
) -> list[SearchQuery]:
    """Phase 2: neighbours of the K cheapest phase-1 results, nearest first."""
    if remaining <= 0 or not cheapest_by_query:
        return []
    s = trip.strategy
    searched = set(already)
    valid_days = set(_depart_days(trip))
    seeds = sorted(cheapest_by_query.values(), key=lambda qp: qp[1])[: s.refine_top_k]

    candidates: list[tuple[int, float, SearchQuery]] = []
    r = s.refine_radius_days
    for seed, price in seeds:
        night_offsets = range(-r, r + 1) if seed.is_round_trip else [0]
        for dd in range(-r, r + 1):
            for dn in night_offsets:
                if dd == 0 and dn == 0:
                    continue
                dep = seed.depart_date + timedelta(days=dd)
                if dep not in valid_days:
                    continue
                nights = None
                if seed.is_round_trip:
                    nights = seed.nights + dn
                    if not trip.nights_min <= nights <= trip.nights_max:
                        continue
                q = _query(trip, seed.origin, seed.destination, dep, nights, currency)
                if q.key() in searched:
                    continue
                searched.add(q.key())
                candidates.append((abs(dd) + abs(dn), price, q))
    # Closest to a cheap seed first; break ties by the seed's price.
    candidates.sort(key=lambda c: (c[0], c[1]))
    return [c[2] for c in candidates[:remaining]]

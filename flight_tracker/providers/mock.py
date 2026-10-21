"""Deterministic fake provider so the whole pipeline runs without API keys.

Prices follow realistic patterns: weekend and holiday premiums, a lead-time
curve, cheaper mid-week departures, and a small day-to-day drift so that
history and price-drop alerts have something to show. The same
(query, day) always gives the same result, which keeps tests stable.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, time, timedelta

from ..models import FlightOffer, Leg, SearchQuery, Segment
from .base import Provider, TransientProviderError

AIRLINES = [
    ("AC", "Air Canada"), ("EK", "Emirates"), ("QR", "Qatar Airways"), ("LH", "Lufthansa"),
    ("BA", "British Airways"), ("AI", "Air India"), ("TK", "Turkish Airlines"), ("EY", "Etihad"),
    ("KL", "KLM"), ("UA", "United"),
]
HUBS = ["DXB", "DOH", "FRA", "LHR", "IST", "AUH", "AMS", "ORD"]
CABIN_MULT = {"economy": 1.0, "premium_economy": 1.7, "business": 3.6, "first": 6.0}


def _rng(*parts: object) -> random.Random:
    seed = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return random.Random(int(seed[:16], 16))


def _route_base(origin: str, dest: str) -> float:
    r = _rng("base", *sorted([origin, dest]))
    return r.uniform(250, 1100)


def _date_factor(d: date, today: date) -> float:
    f = 1.0
    if d.weekday() in (4, 6):  # Fri, Sun
        f *= 1.18
    elif d.weekday() in (1, 2):  # Tue, Wed
        f *= 0.9
    if (d.month == 12 and d.day >= 15) or (d.month == 1 and d.day <= 5):
        f *= 1.35
    if d.month in (7, 8):
        f *= 1.15
    lead = (d - today).days
    if lead < 14:
        f *= 1.45
    elif lead < 30:
        f *= 1.15
    elif lead > 150:
        f *= 1.08
    # Smooth pseudo-random wave so neighbouring dates are correlated.
    wave = _rng("wave", d.isocalendar()[1], d.year).uniform(0.85, 1.15)
    return f * wave


class MockProvider(Provider):
    name = "mock"
    max_concurrency = 16

    def __init__(self, **options):
        super().__init__(**options)
        self.today = options.get("today") or date.today()
        self.fail_rate = float(options.get("fail_rate", 0.0))

    def search(self, query: SearchQuery) -> list[FlightOffer]:
        r = _rng(query.key(), self.today.isoformat())
        if self.fail_rate and r.random() < self.fail_rate:
            raise TransientProviderError("mock: simulated timeout")

        base = _route_base(query.origin, query.destination) * CABIN_MULT.get(query.cabin, 1.0)
        price_core = base * _date_factor(query.depart_date, self.today)
        if query.return_date:
            price_core += base * 0.75 * _date_factor(query.return_date, self.today)
        drift = _rng("drift", query.key(), self.today.isoformat()).uniform(0.94, 1.06)

        offers = []
        for i in range(r.randint(3, 7)):
            code, name = r.choice(AIRLINES)
            stops = r.choices([0, 1, 2], weights=[2, 5, 2])[0]
            if query.max_stops is not None:
                stops = min(stops, query.max_stops)
            stop_factor = {0: 1.25, 1: 1.0, 2: 0.88}[stops]
            price = round(price_core * drift * stop_factor * r.uniform(0.92, 1.2) * query.adults, 2)
            out = self._leg(r, query.origin, query.destination, query.depart_date, stops, code, name)
            inb = None
            if query.return_date:
                inb = self._leg(r, query.destination, query.origin, query.return_date, stops, code, name)
            offers.append(FlightOffer(
                provider=self.name,
                query=query,
                price=price,
                currency=query.currency,
                outbound=out,
                inbound=inb,
                booking_url=f"https://example.com/book?o={query.origin}&d={query.destination}&dep={query.depart_date}",
            ))
        return offers

    @staticmethod
    def _leg(r: random.Random, origin: str, dest: str, day: date, stops: int, code: str, name: str) -> Leg:
        hubs = r.sample([h for h in HUBS if h not in (origin, dest)], stops)
        points = [origin, *hubs, dest]
        t = datetime.combine(day, time(r.randint(5, 22), r.choice([0, 15, 30, 45])))
        segments = []
        for a, b in zip(points, points[1:]):
            dur = timedelta(minutes=r.randint(90, 600))
            segments.append(Segment(
                origin=a, destination=b, depart_at=t, arrive_at=t + dur,
                carrier=code, carrier_name=name, flight_number=str(r.randint(10, 999)),
            ))
            t = t + dur + timedelta(minutes=r.randint(60, 300))
        return Leg(segments=segments)

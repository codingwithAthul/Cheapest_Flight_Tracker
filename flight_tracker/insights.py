"""Build the per-trip daily summary from the database (no rendering here)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .config import Config, Trip
from .models import Leg
from .storage import Storage, row_legs

SPARK = "▁▂▃▄▅▆▇█"


@dataclass
class Option:
    rank: int
    price: float
    currency: str
    origin: str
    destination: str
    depart_date: date
    return_date: Optional[date]
    airlines: str
    stops: int
    duration_minutes: int
    outbound: Leg
    inbound: Optional[Leg]
    booking_url: str
    providers: list[str]
    change_vs_prev: Optional[float] = None  # same dates/airports, previous run's cheapest

    @property
    def nights(self) -> Optional[int]:
        return (self.return_date - self.depart_date).days if self.return_date else None


@dataclass
class TripSummary:
    trip: Trip
    run_date: date
    options: list[Option] = field(default_factory=list)
    best_value: Optional[Option] = None
    today_min: Optional[float] = None
    prev_min: Optional[float] = None
    prev_date: Optional[str] = None
    all_time_low_before: Optional[float] = None
    history: list[tuple[str, float]] = field(default_factory=list)
    cheapest_dates: list[tuple[date, Optional[date], float]] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)

    @property
    def change_pct(self) -> Optional[float]:
        if self.today_min is None or not self.prev_min:
            return None
        return (self.today_min - self.prev_min) / self.prev_min * 100

    @property
    def sparkline(self) -> str:
        prices = [p for _, p in self.history]
        if len(prices) < 2:
            return ""
        lo, hi = min(prices), max(prices)
        span = (hi - lo) or 1
        return "".join(SPARK[min(int((p - lo) / span * (len(SPARK) - 1)), len(SPARK) - 1)] for p in prices)


def _d(s: Optional[str]) -> Optional[date]:
    return date.fromisoformat(s) if s else None


def build_summary(storage: Storage, trip: Trip, run_date: date, config: Config) -> TripSummary:
    s = TripSummary(trip=trip, run_date=run_date)
    rows = storage.offers_for(trip.name, run_date)
    if not rows:
        s.prev_date = storage.previous_run_date(trip.name, run_date)
        return s

    # De-duplicate the same itinerary seen on several providers (keep cheapest).
    by_fp: dict[str, dict] = {}
    for r in rows:  # rows are ordered by price
        fp = r["fingerprint"]
        if fp not in by_fp:
            by_fp[fp] = {"row": r, "providers": [r["provider"]]}
        elif r["provider"] not in by_fp[fp]["providers"]:
            by_fp[fp]["providers"].append(r["provider"])
    unique = list(by_fp.values())

    s.prev_date = storage.previous_run_date(trip.name, run_date)

    def to_option(rank: int, item: dict) -> Option:
        r = item["row"]
        out, inb = row_legs(r)
        opt = Option(
            rank=rank, price=r["price"], currency=r["currency"], origin=r["origin"], destination=r["destination"],
            depart_date=_d(r["depart_date"]), return_date=_d(r["return_date"]), airlines=r["airlines"] or "",
            stops=r["stops"], duration_minutes=r["duration_minutes"] or 0, outbound=out, inbound=inb,
            booking_url=r["booking_url"] or "", providers=item["providers"],
        )
        if s.prev_date:
            prev = storage.combo_price(trip.name, r["origin"], r["destination"], r["depart_date"],
                                       r["return_date"], s.prev_date)
            if prev is not None:
                opt.change_vs_prev = round(r["price"] - prev, 2)
        return opt

    top_n = config.report.top_n
    s.options = [to_option(i + 1, item) for i, item in enumerate(unique[:top_n])]
    s.today_min = s.options[0].price

    if config.report.value_of_hour > 0:
        voh = config.report.value_of_hour
        best = min(unique, key=lambda it: it["row"]["price"] + voh * (it["row"]["duration_minutes"] or 0) / 60)
        if best is not unique[0]:
            s.best_value = to_option(0, best)

    if s.prev_date:
        prev_rows = storage.offers_for(trip.name, date.fromisoformat(s.prev_date))
        s.prev_min = prev_rows[0]["price"] if prev_rows else None
    atl = storage.all_time_low(trip.name, before=run_date)
    s.all_time_low_before = atl["price"] if atl else None
    s.history = storage.daily_minimums(trip.name, limit_days=30)

    # Cheapest per departure date, then the best few dates overall.
    per_date: dict[tuple, float] = {}
    for item in unique:
        r = item["row"]
        key = (r["depart_date"], r["return_date"])
        per_date[key] = min(per_date.get(key, float("inf")), r["price"])
    best_dates = sorted(per_date.items(), key=lambda kv: kv[1])[:7]
    s.cheapest_dates = [(_d(k[0]), _d(k[1]), p) for k, p in best_dates]

    # Alerts
    cur = s.options[0].currency
    if s.all_time_low_before is not None and s.today_min < s.all_time_low_before:
        s.alerts.append(f"New all-time low: {cur} {s.today_min:,.0f} (was {cur} {s.all_time_low_before:,.0f})")
    pct = s.change_pct
    if pct is not None and pct <= -abs(config.report.drop_alert_percent):
        s.alerts.append(f"Cheapest fare dropped {abs(pct):.1f}% since {s.prev_date}")
    if trip.target_price is not None and s.today_min <= trip.target_price:
        s.alerts.append(f"Target price hit: {cur} {s.today_min:,.0f} <= {cur} {trip.target_price:,.0f}")
    return s


def build_all(storage: Storage, config: Config, run_date: date) -> list[TripSummary]:
    return [build_summary(storage, t, run_date, config) for t in config.trips if t.enabled]

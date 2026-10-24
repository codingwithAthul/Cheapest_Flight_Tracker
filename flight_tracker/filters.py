"""Apply a trip's hard constraints to offers, and de-duplicate across providers."""

from __future__ import annotations

from typing import Iterable

from .config import Filters
from .models import FlightOffer


def _matches_airline(offer_names: Iterable[str], wanted: list[str]) -> bool:
    wanted_l = {w.lower() for w in wanted}
    return any(n.lower() in wanted_l for n in offer_names)


def rejection_reason(offer: FlightOffer, f: Filters) -> str | None:
    """Return why an offer fails the filters, or None if it passes."""
    if f.max_price is not None and offer.price > f.max_price:
        return "price"
    if f.max_stops is not None and offer.max_stops > f.max_stops:
        return "stops"
    if f.max_duration_hours is not None:
        limit = f.max_duration_hours * 60
        for leg in (offer.outbound, offer.inbound):
            if leg is not None and (leg.duration_minutes or 0) > limit:
                return "duration"
    for leg in (offer.outbound, offer.inbound):
        if leg is None:
            continue
        for _, minutes in leg.layovers:
            if f.max_layover_hours is not None and minutes > f.max_layover_hours * 60:
                return "layover_long"
            if f.min_layover_minutes is not None and minutes < f.min_layover_minutes:
                return "layover_short"
    names = set(offer.airline_codes) | set(offer.airlines)
    if f.exclude_airlines and _matches_airline(names, f.exclude_airlines):
        return "airline_excluded"
    if f.include_airlines:
        # Every segment's carrier must be on the allow-list (by code or name).
        allowed = {a.lower() for a in f.include_airlines}
        for leg in (offer.outbound, offer.inbound):
            if leg is None:
                continue
            for s in leg.segments:
                if s.carrier.lower() not in allowed and s.carrier_name.lower() not in allowed:
                    return "airline_not_included"
    dep = offer.outbound.depart_at.time()
    if f.depart_after and dep < f.depart_after:
        return "depart_time"
    if f.depart_before and dep > f.depart_before:
        return "depart_time"
    if offer.inbound is not None:
        rdep = offer.inbound.depart_at.time()
        if f.return_depart_after and rdep < f.return_depart_after:
            return "return_time"
        if f.return_depart_before and rdep > f.return_depart_before:
            return "return_time"
    return None


def apply_filters(offers: list[FlightOffer], f: Filters) -> tuple[list[FlightOffer], dict[str, int]]:
    kept, rejected = [], {}
    for o in offers:
        reason = rejection_reason(o, f)
        if reason is None:
            kept.append(o)
        else:
            rejected[reason] = rejected.get(reason, 0) + 1
    return kept, rejected


def dedupe(offers: list[FlightOffer]) -> list[FlightOffer]:
    """Keep the cheapest copy of each itinerary; remember who else sold it."""
    best: dict[str, FlightOffer] = {}
    for o in sorted(offers, key=lambda x: x.price):
        fp = o.fingerprint()
        if fp not in best:
            best[fp] = o
        elif o.provider != best[fp].provider and o.provider not in best[fp].also_seen_on:
            best[fp].also_seen_on.append(o.provider)
    return sorted(best.values(), key=lambda x: x.price)

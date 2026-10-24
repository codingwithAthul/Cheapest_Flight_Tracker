"""Duffel provider (https://duffel.com/docs/api/v2/offer-requests).

Credentials: set DUFFEL_ACCESS_TOKEN (or the env var named in `token_env`).
A test token (duffel_test_...) returns Duffel Airways sandbox data; a live
token returns real airline offers.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import requests

from ..models import FlightOffer, Leg, SearchQuery, Segment
from .base import Provider, ProviderError, TransientProviderError

log = logging.getLogger(__name__)

ENDPOINT = "https://api.duffel.com/air/offer_requests"
ISO_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?")


def parse_iso_duration(value: str | None) -> int | None:
    if not value:
        return None
    m = ISO_DURATION.fullmatch(value)
    if not m:
        return None
    d, h, mins = (int(x or 0) for x in m.groups())
    return d * 1440 + h * 60 + mins


class DuffelProvider(Provider):
    name = "duffel"
    max_concurrency = 3
    min_interval = 0.5

    def __init__(self, **options):
        super().__init__(**options)
        self.token = os.environ.get(options.get("token_env", "DUFFEL_ACCESS_TOKEN"), "")
        self.timeout = float(options.get("timeout", 90))
        self.session = requests.Session()
        # Test tokens only return synthetic sandbox offers ("Duffel Airways"), never real fares.
        # Tag them so reports can say so instead of passing fake prices off as real.
        self.sandbox = self.token.startswith("duffel_test_")
        self.label = "duffel-test" if self.sandbox else self.name

    def check_ready(self) -> None:
        if not self.token:
            raise ProviderError("duffel: DUFFEL_ACCESS_TOKEN is not set")
        if self.sandbox:
            log.warning("duffel: test token in use; results are sandbox data, not real prices")

    def build_body(self, q: SearchQuery) -> dict:
        slices = [{"origin": q.origin, "destination": q.destination, "departure_date": q.depart_date.isoformat()}]
        if q.return_date:
            slices.append({"origin": q.destination, "destination": q.origin, "departure_date": q.return_date.isoformat()})
        body = {
            "slices": slices,
            "passengers": [{"type": "adult"} for _ in range(q.adults)],
            "cabin_class": q.cabin,
        }
        if q.max_stops is not None:
            body["max_connections"] = q.max_stops
        return {"data": body}

    def search(self, query: SearchQuery) -> list[FlightOffer]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        try:
            resp = self.session.post(
                ENDPOINT, params={"return_offers": "true"}, json=self.build_body(query),
                headers=headers, timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise TransientProviderError(f"duffel: network error: {e}") from e
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientProviderError(f"duffel: HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise ProviderError(f"duffel: HTTP {resp.status_code}: {resp.text[:300]}")
        return self.parse(query, resp.json())

    def parse(self, query: SearchQuery, payload: dict) -> list[FlightOffer]:
        offers = []
        for o in (payload.get("data") or {}).get("offers") or []:
            legs = []
            for sl in o.get("slices") or []:
                segs = []
                for s in sl.get("segments") or []:
                    mk = s.get("marketing_carrier") or {}
                    segs.append(Segment(
                        origin=s["origin"]["iata_code"],
                        destination=s["destination"]["iata_code"],
                        depart_at=datetime.fromisoformat(s["departing_at"]),
                        arrive_at=datetime.fromisoformat(s["arriving_at"]),
                        carrier=mk.get("iata_code", ""),
                        carrier_name=mk.get("name", ""),
                        flight_number=str(s.get("marketing_carrier_flight_number", "")),
                    ))
                if segs:
                    legs.append(Leg(segments=segs, duration_minutes=parse_iso_duration(sl.get("duration"))))
            if not legs:
                continue
            offers.append(FlightOffer(
                provider=self.label,
                query=query,
                price=float(o["total_amount"]),
                currency=o.get("total_currency", query.currency),
                outbound=legs[0],
                inbound=legs[1] if len(legs) > 1 else None,
                booking_url="",
            ))
        return offers

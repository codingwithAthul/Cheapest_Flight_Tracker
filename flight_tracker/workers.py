"""Parallel search engine.

Each (query, provider) pair is a job. Jobs run on a thread pool (searches
are I/O bound). Each provider also enforces its own concurrency cap and rate
limit (see Provider.throttled_search), so one slow API can't starve the
others or get us banned. Transient failures are retried with exponential
backoff and jitter.

Only the main thread writes to SQLite: results are recorded as futures
complete, which keeps the database single-writer and safe.
"""

from __future__ import annotations

import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .config import Config, Trip
from .filters import apply_filters
from .models import FlightOffer, SearchQuery
from .planner import plan_exhaustive, plan_refine, plan_sample
from .providers import Provider, ProviderError, TransientProviderError
from .storage import Storage

log = logging.getLogger(__name__)


@dataclass
class JobResult:
    query: SearchQuery
    provider: str
    offers: list[FlightOffer] = field(default_factory=list)
    error: Optional[str] = None
    attempts: int = 0


@dataclass
class TripStats:
    planned: int = 0
    ok: int = 0
    failed: int = 0
    skipped_cached: int = 0
    offers_found: int = 0
    offers_kept: int = 0
    rejected: dict[str, int] = field(default_factory=dict)


def run_with_retries(provider: Provider, query: SearchQuery, retries: int = 3, base_delay: float = 1.0,
                     sleep: Callable[[float], None] = time.sleep) -> JobResult:
    res = JobResult(query=query, provider=provider.name)
    for attempt in range(1, retries + 2):
        res.attempts = attempt
        try:
            res.offers = provider.throttled_search(query)
            res.error = None
            return res
        except TransientProviderError as e:
            res.error = str(e)
            if attempt > retries:
                break
            delay = base_delay * (2 ** (attempt - 1)) * random.uniform(0.8, 1.2)
            log.warning("%s %s: %s (retry %d in %.1fs)", provider.name, query.key(), e, attempt, delay)
            sleep(delay)
        except ProviderError as e:
            res.error = str(e)
            break
        except Exception as e:  # provider bug: never crash the whole run
            res.error = f"unexpected {type(e).__name__}: {e}"
            log.exception("provider %s crashed on %s", provider.name, query.key())
            break
    return res


def _cache_key(q: SearchQuery) -> str:
    return f"{q.origin}|{q.destination}|{q.depart_date.isoformat()}|{q.return_date.isoformat() if q.return_date else '-'}"


class SearchEngine:
    def __init__(self, config: Config, providers: list[Provider], storage: Storage, run_id: str, run_date: date,
                 retries: int = 3, base_delay: float = 1.0):
        self.config = config
        self.providers = providers
        self.storage = storage
        self.run_id = run_id
        self.run_date = run_date
        self.retries = retries
        self.base_delay = base_delay

    def _execute(self, trip: Trip, queries: list[SearchQuery], phase: str, stats: TripStats,
                 pool: ThreadPoolExecutor) -> dict[str, tuple[SearchQuery, float]]:
        """Run queries on all providers; return cheapest filtered price per query key."""
        cheapest: dict[str, tuple[SearchQuery, float]] = {}
        futures = {}
        for provider in self.providers:
            done_today = self.storage.searched_keys_today(trip.name, provider.name, self.run_date)
            for q in queries:
                stats.planned += 1
                if _cache_key(q) in done_today:
                    stats.skipped_cached += 1
                    continue
                fut = pool.submit(run_with_retries, provider, q, self.retries, self.base_delay)
                futures[fut] = provider.name
        for fut in as_completed(futures):
            res: JobResult = fut.result()
            if res.error and not res.offers:
                stats.failed += 1
                self.storage.record_search(self.run_id, self.run_date, res.provider, res.query, phase, 0, [],
                                           error=res.error)
                continue
            stats.ok += 1
            kept, rejected = apply_filters(res.offers, trip.filters)
            stats.offers_found += len(res.offers)
            stats.offers_kept += len(kept)
            for k, v in rejected.items():
                stats.rejected[k] = stats.rejected.get(k, 0) + v
            self.storage.record_search(self.run_id, self.run_date, res.provider, res.query, phase,
                                       len(res.offers), kept, keep_offers=trip.strategy.keep_offers_per_search)
            if kept:
                p = min(o.price for o in kept)
                k = res.query.key()
                if k not in cheapest or p < cheapest[k][1]:
                    cheapest[k] = (res.query, p)
        # Cached combos still count as seeds for refinement.
        for q in queries:
            if q.key() in cheapest:
                continue
            price = self.storage.combo_price(trip.name, q.origin, q.destination, q.depart_date.isoformat(),
                                             q.return_date.isoformat() if q.return_date else None,
                                             self.run_date.isoformat())
            if price is not None:
                cheapest[q.key()] = (q, price)
        return cheapest

    def run_trip(self, trip: Trip, pool: ThreadPoolExecutor) -> TripStats:
        stats = TripStats()
        cur = self.config.currency
        if trip.strategy.mode == "exhaustive":
            self._execute(trip, plan_exhaustive(trip, cur), "exhaustive", stats, pool)
            return stats
        phase1 = plan_sample(trip, cur)
        cheapest = self._execute(trip, phase1, "sample", stats, pool)
        remaining = trip.strategy.budget - len(phase1)
        phase2 = plan_refine(trip, cur, cheapest, [q.key() for q in phase1], remaining)
        if phase2:
            self._execute(trip, phase2, "refine", stats, pool)
        log.info("trip %s: %d sample + %d refine searches", trip.name, len(phase1), len(phase2))
        return stats

    def run(self, trips: list[Trip]) -> dict[str, TripStats]:
        out: dict[str, TripStats] = {}
        with ThreadPoolExecutor(max_workers=self.config.workers, thread_name_prefix="search") as pool:
            for trip in trips:
                out[trip.name] = self.run_trip(trip, pool)
        return out

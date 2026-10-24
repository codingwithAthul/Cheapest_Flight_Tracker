"""Provider interface. Add a new data source by subclassing Provider."""

from __future__ import annotations

import abc
import threading
import time
from typing import Any

from ..models import FlightOffer, SearchQuery


class ProviderError(Exception):
    """A search failed and should not be retried (bad request, auth, quota)."""


class TransientProviderError(ProviderError):
    """A search failed but may succeed on retry (timeouts, 429, 5xx)."""


class Provider(abc.ABC):
    """Base class for flight data sources.

    Subclasses implement `search()` and may set:
      - name:            registry key used in config.yaml
      - max_concurrency: max simultaneous requests to this provider
      - min_interval:    minimum seconds between request starts (rate limit)
    """

    name: str = "base"
    max_concurrency: int = 4
    min_interval: float = 0.0

    def __init__(self, **options: Any) -> None:
        self.options = options
        self.max_concurrency = int(options.get("max_concurrency", self.max_concurrency))
        self.min_interval = float(options.get("min_interval", self.min_interval))
        self._sem = threading.BoundedSemaphore(self.max_concurrency)
        self._rate_lock = threading.Lock()
        self._next_slot = 0.0

    @abc.abstractmethod
    def search(self, query: SearchQuery) -> list[FlightOffer]:
        """Return offers for exactly this query (any order)."""

    def check_ready(self) -> None:
        """Raise ProviderError when required credentials are missing."""

    # Called by the worker pool; subclasses should not override.
    def throttled_search(self, query: SearchQuery) -> list[FlightOffer]:
        with self._sem:
            if self.min_interval > 0:
                with self._rate_lock:
                    now = time.monotonic()
                    wait = self._next_slot - now
                    self._next_slot = max(now, self._next_slot) + self.min_interval
                if wait > 0:
                    time.sleep(wait)
            return self.search(query)

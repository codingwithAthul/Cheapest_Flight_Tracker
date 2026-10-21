"""Provider registry. To add a data source, implement Provider and register it here."""

from __future__ import annotations

from typing import Any

from .base import Provider, ProviderError, TransientProviderError
from .duffel import DuffelProvider
from .mock import MockProvider
from .serpapi import SerpApiProvider

REGISTRY: dict[str, type[Provider]] = {
    MockProvider.name: MockProvider,
    SerpApiProvider.name: SerpApiProvider,
    DuffelProvider.name: DuffelProvider,
}


def create_provider(name: str, **options: Any) -> Provider:
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ProviderError(f"unknown provider {name!r}; available: {sorted(REGISTRY)}") from None
    return cls(**options)


__all__ = ["Provider", "ProviderError", "TransientProviderError", "create_provider", "REGISTRY"]

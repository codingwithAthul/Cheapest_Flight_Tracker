# Flight data providers

The bot is provider-agnostic. Enable one or more in `config.yaml`. When
several are enabled, the same itinerary is de-duplicated and the report shows
the cheapest copy along with every provider that sold it.

| Provider | `name` | Secret | Coverage | Cost (check current pricing) | Notes |
|---|---|---|---|---|---|
| Mock | `mock` | none | Fake but realistic | Free | For tests and dry runs. Deterministic per day. |
| SerpApi Google Flights | `serpapi` | `SERPAPI_API_KEY` | Everything on Google Flights, including most low-cost carriers | Small free tier, then paid monthly plans by searches/month | **Recommended.** Round trips return the total price and outbound details only; return details are on the linked Google Flights page. |
| Duffel | `duffel` | `DUFFEL_ACCESS_TOKEN` | Airlines connected to Duffel (NDC/GDS); weaker on some low-cost carriers | Searching is free with an account; Duffel charges on bookings | A test token gives sandbox data only. A live token may need business verification. |

## Recommended setup: Duffel search + SerpApi final check

```yaml
providers: [{name: duffel}]
verify: {provider: serpapi, top_k: 5}
```

Duffel searches the whole date window for free. SerpApi then re-prices only
the 5 cheapest combos on Google Flights, which costs 5 credits per trip per
day. That way the broad search is free and the paid source is only used
where it matters.

**Duffel test tokens (`duffel_test_…`) return sandbox data**, such as
"Duffel Airways", not real fares. The bot detects this and tags those offers
as `duffel-test`. The report then:
- shows a warning;
- leaves sandbox fares out of the ranking whenever real (verified) fares
  exist;
- still lets the sandbox results pick which dates get verified. With a test
  token that choice is essentially random, so get a **live** Duffel token
  for the search stage to mean anything.

### Not supported, and why

- **Amadeus Self-Service APIs** were shut down in July 2026.
- **Kiwi Tequila** no longer accepts new public sign-ups.
- **Scraping airline or OTA websites** is fragile and usually breaks their
  terms of service.

## Budgeting API calls

```
daily calls ≈ Σ(trip.strategy.budget) × number of providers
```

Run `python -m flight_tracker plan` to see the exact numbers. For example,
one trip with `budget: 60` on SerpApi uses 60 searches/day ≈ 1,800/month.
Lower `budget` or narrow the window to fit a plan. The smart planner gives
good results from about 30 searches per trip.

Re-running on the same day skips combos already searched successfully, so a
retried workflow doesn't double-bill you.

## Provider options

Any provider accepts `max_concurrency` (simultaneous requests) and
`min_interval` (seconds between request starts):

```yaml
providers:
  - name: serpapi
    max_concurrency: 4
    min_interval: 0.25
    gl: ca            # SerpApi: Google country (affects point of sale)
    hl: en
  - name: duffel
    max_concurrency: 3
```

## Adding a provider

1. Create `flight_tracker/providers/<name>.py`:

```python
from .base import Provider, ProviderError, TransientProviderError

class MyProvider(Provider):
    name = "myprovider"
    max_concurrency = 2

    def check_ready(self):
        ...  # raise ProviderError if the key is missing

    def search(self, query):
        ...  # call the API; raise TransientProviderError on 429/5xx/timeouts,
             # ProviderError on anything that won't fix itself
        return [FlightOffer(...)]  # normalised offers
```

2. Register it in `providers/__init__.py` (`REGISTRY`).
3. Add a parser test with a saved sample response (see
   `tests/test_filters_providers.py`). Tests must not hit the network.

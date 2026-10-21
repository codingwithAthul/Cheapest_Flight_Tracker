# PROGRESS — where the build is right now

> Update this file at the end of every work session. When resuming, read it
> first, then [PROJECT.md](PROJECT.md).

_Last updated: 2026-10-21_

## Status: v0.1 built, waiting on the owner's choices before going live

The full pipeline works end to end with the **mock** provider: plan →
parallel search → filter → SQLite → insights → report → notify. That
includes the GitHub Actions daily workflow with matrix shards. Real prices
need an API key. See "Waiting on owner" below.

## Done

- [x] Config schema and validation (`flight_tracker/config.py`, `config.example.yaml`)
- [x] Date planner: smart sample→zoom under a budget, plus exhaustive mode (`planner.py`)
- [x] Providers: `mock`, `serpapi` (Google Flights), `duffel` (`providers/`)
- [x] Parallel worker pool with per-provider concurrency, rate limit, retries and backoff (`workers.py`)
- [x] Filters (stops, price, duration, layovers, airlines, times, weekdays) and cross-provider de-dup (`filters.py`)
- [x] SQLite storage with migrations, shard merge, prune and a same-day cache (`storage.py`)
- [x] Insights: day-over-day change, all-time low, target price, 30-day sparkline, cheapest dates, best value (`insights.py`)
- [x] Reports: Markdown, HTML email and Telegram (`report.py`); files written to `reports/`
- [x] Notifiers: console, GitHub job summary, Telegram, email/SMTP (`notify/`)
- [x] CLI: plan / search / merge / report / run / history / prune (`cli.py`)
- [x] Workflows: `daily.yml` (plan → matrix search → merge+report → save to `data` branch) and `ci.yml`
- [x] Tests (pytest, no network): config, planner, filters, provider parsers, pipeline, CLI shards/merge
- [x] Docs: README, docs/ARCHITECTURE.md, CONFIGURATION.md, PROVIDERS.md, OPERATIONS.md

## Waiting on owner (decisions only they can make)

1. **Real route.** `config.yaml` has an EXAMPLE route (YYZ → LHR/LGW). Replace it with the real origin, destination, window, nights and filters.
2. **Data source.** The recommendation is SerpApi (Google Flights). Add the `SERPAPI_API_KEY` repo secret and switch `providers` in `config.yaml`.
3. **Report channel.** The recommendation is Telegram. Add the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets and enable the `telegram` notifier.

## Next up (in order)

1. Apply the owner's route, provider and channel choices to `config.yaml`, then run the workflow manually once.
2. Tune `strategy.budget` against the provider's plan quota (`python -m flight_tracker plan` shows calls per day and per month).
3. Roadmap items in PROJECT.md (return-leg details for SerpApi, price prediction, dashboard).

## How to resume quickly

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # everything should pass
python -m flight_tracker plan                         # see the search plan
python -m flight_tracker --db /tmp/t.db run --provider mock --no-notify
```

## Log

- 2026-10-21: Built v0.1 from an empty repo (README + LICENSE only). Amadeus Self-Service was shut down in July 2026 and Kiwi Tequila is closed to new sign-ups, so they are not supported.

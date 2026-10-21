# PROGRESS — where the build is right now

> Update this file at the end of every work session. When resuming, read it
> first, then [PROJECT.md](PROJECT.md).

_Last updated: 2026-10-21_

## Status: v0.2 (Duffel search + SerpApi final check), waiting on secrets and route

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
- [x] Verify stage: Duffel searches, SerpApi re-prices the top-K combos (`config.verify`)
- [x] Duffel test-token detection (`duffel-test`); sandbox fares never outrank real ones
- [x] `probe` command and `live-keys` CI job to check API keys

## Waiting on owner (decisions only they can make)

1. **Add the API keys as GitHub secrets.** Athul shared a Duffel key and a
   SerpApi key in chat on 2026-10-21. They must go into *Settings → Secrets and
   variables → Actions* as `DUFFEL_ACCESS_TOKEN` and `SERPAPI_API_KEY`. The
   build environment can't set repo secrets or reach either API, so the keys
   are untested. Never commit keys to the repo.
2. **Live Duffel token.** The shared key is `duffel_test_…`, which returns
   sandbox fares only. The SerpApi final check is the only real pricing until
   a live token is added.
3. **Real route.** `config.yaml` still has the EXAMPLE route (YYZ → LHR/LGW).
4. **Report channel.** Telegram is recommended, but nothing has been chosen yet.

## Next up (in order)

1. Once the secrets exist, check the `live-keys` CI job output (it runs `probe`).
2. Apply the route and channel to `config.yaml`, then run *Daily flight search* manually.
3. Tune `strategy.budget` and `verify.top_k` to the SerpApi plan quota (`plan` shows calls per month).
4. Roadmap items in PROJECT.md.

## How to resume quickly

```bash
pip install -r requirements-dev.txt
python -m pytest -q                                   # everything should pass
python -m flight_tracker plan                         # see the search plan
python -m flight_tracker --db /tmp/t.db run --provider mock --no-notify
```

## Log

- 2026-10-21: Built v0.1 from an empty repo (README + LICENSE only). Amadeus Self-Service was shut down in July 2026 and Kiwi Tequila is closed to new sign-ups, so they are not supported.
- 2026-10-21: Athul chose Duffel for search with SerpApi as the final check, and set a rule: one commit per small chunk of code. Added the verify stage, sandbox handling, probe and the live-keys CI job.

# PROGRESS — where the build is right now

> Update this file at the end of every work session. When resuming, read it
> first, then [PROJECT.md](PROJECT.md).

_Last updated: 2026-10-21_

## Status: v0.3 — T1 Vancouver ⇄ Kochi live on SerpApi (SERPAPI_API_KEY secret set by Athul)

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

1. **Stay length and window.** T1 assumes a 14–35 night stay and departures 2 weeks to 6 months out. Athul hasn't confirmed this yet.
2. **Report channel.** Reports are committed to `Report/` and shown in the Actions summary. Telegram or email isn't chosen yet.
3. **Duffel.** Parked: Athul is unsure about the charges. Only the test key exists, and it isn't in secrets.
4. **SerpApi quota.** The key is confirmed working (Free Plan, 250/month, first live fare CAD 1,803 on Air India). The budget is 7/day, about 217/month.

## Next up (in order)

1. Merge PR #1, then run *Actions → Daily flight search → Run workflow* once.
2. Upgrade the SerpApi plan if 7 searches/day turns out too sparse.
3. Roadmap items in PROJECT.md.

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
- 2026-10-21: Athul set the SERPAPI_API_KEY secret, parked Duffel, and gave the route Vancouver ⇄ Kochi (T1). Reports now go to `Report/<code> <from> - <to> (Round|One-Way)/` on main. Added rotate_daily and the 7-day best fares section.

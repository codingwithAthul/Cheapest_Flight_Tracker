# Architecture

## Data flow

```
                     ┌──────────────┐
 config.yaml ──────► │   planner    │  Trip → SearchQuery[] (within budget)
                     └──────┬───────┘
                            │ phase 1: sample grid
                            ▼
                     ┌──────────────┐     ┌───────────┐
                     │ SearchEngine │────►│ providers │  mock / serpapi / duffel
                     │ thread pool  │◄────│ (rate-    │  (each: own concurrency cap,
                     └──────┬───────┘     │  limited) │   min interval, retries)
                            │             └───────────┘
            filters ◄───────┤ kept offers
                            ▼
                     ┌──────────────┐
                     │   SQLite     │  runs / searches / offers / notifications
                     └──────┬───────┘
                            │ cheapest per combo → phase 2: zoom around the K cheapest
                            ▼
                     ┌──────────────┐     ┌──────────┐     ┌───────────┐
                     │   insights   │────►│  report  │────►│ notifiers │
                     └──────────────┘     └──────────┘     └───────────┘
```

## Modules (`flight_tracker/`)

| Module | Responsibility |
|---|---|
| `config.py` | Parse and validate YAML into `Config` / `Trip` / `Filters` / `Strategy`. Unknown keys are errors. Relative dates (`+30d`). Past dates are clamped to tomorrow. |
| `models.py` | Provider-neutral `SearchQuery`, `Segment`, `Leg`, `FlightOffer` (stops, layovers, fingerprint, value score). |
| `planner.py` | Expands a trip into queries: `plan_sample` (phase 1), `plan_refine` (phase 2), `plan_exhaustive`. |
| `providers/` | `Provider` base class (throttling), the registry, and the adapters. Errors are split into `TransientProviderError` (retried) and `ProviderError` (not retried). |
| `workers.py` | `SearchEngine`: fans jobs out to a `ThreadPoolExecutor`, retries with exponential backoff and jitter, filters and records results on the main thread (single SQLite writer), and skips combos already searched today. |
| `filters.py` | Hard constraints, with a rejection reason per offer (counts are logged in `runs.notes`), plus cross-provider de-dup. |
| `storage.py` | SQLite schema and migrations (`PRAGMA user_version`), writes, history queries, `merge_from` (shard merge) and `prune`. |
| `insights.py` | Builds a `TripSummary` per trip: top N sorted by price, day-over-day change, all-time low, target alert, sparkline, cheapest dates, best value. |
| `report.py` | Renders Markdown (files and GitHub summary), HTML (email) and Telegram messages (one per trip, under 4096 characters). |
| `notify/` | `console`, `github_summary`, `telegram`, `email`. Secrets come from environment variables, and `only_on_alert` is supported. |
| `cli.py` | `plan`, `search`, `merge`, `report`, `run`, `history`, `prune`. |

## The two-phase date search

A flexible-date trip has `airport pairs × departure days × stay lengths`
combinations. That is often more than 1,000, while paid APIs charge per
search. So:

1. **Sample** (≤60% of `budget`). Every `sample_every_days`-th departure day
   (always including the first and last), `nights_samples` stay lengths
   spread across `[min, max]`, and every airport pair. If that is still too
   big, the planner drops stay samples first, then widens the date step.
2. **Zoom** (the rest of the budget). Take the `refine_top_k` cheapest
   combos and search their neighbours within ±`refine_radius_days` on both
   departure day and stay length, nearest first.

Fares are strongly correlated between neighbouring dates, so this finds the
true minimum with a fraction of the calls. Use `mode: exhaustive` if you'd
rather pay for full coverage of a small window.

## Parallelism ("parallel bots")

- **In-process.** A thread pool of `workers` threads. Each provider also caps
  its own concurrency (`max_concurrency`) and request spacing
  (`min_interval`), so a fast mock and a strict paid API can share the pool.
- **Across machines.** The daily workflow runs a matrix of up to
  `MAX_SHARDS` jobs. Shard *i* of *n* takes the trips at index
  `i-1, i-1+n, …`. Each shard writes its own SQLite file. The report job
  merges them into the history DB. UUID primary keys make the merge
  collision-free, and re-merging the same shard is a no-op.

## Database schema

| Table | Key columns |
|---|---|
| `runs` | `id`, `run_date`, `shard`, `status` (ok/partial/failed), `searches_planned/ok/failed`, `notes` (filter rejection counts) |
| `searches` | `id`, `run_id`, `provider`, `trip_name`, `origin`, `destination`, `depart_date`, `return_date`, `phase`, `status`, `error`, `offers_found`, `offers_kept`, `min_price` |
| `offers` | `id`, `search_id`, `run_date`, `trip_name`, `provider`, route and dates, `price`, `currency`, `stops`, `duration_minutes`, `airlines`, `outbound_json`, `inbound_json`, `booking_url`, `fingerprint` |
| `notifications` | `run_date`, `channel`, `status`, `error` |

Only the `keep_offers_per_search` cheapest offers per search are stored, to
keep the DB small. `prune` deletes offers older than N days but keeps each
trip's cheapest offer per day forever, so long-term trends survive.

Useful queries:

```sql
-- daily cheapest per trip
SELECT trip_name, run_date, MIN(price) FROM offers GROUP BY 1, 2 ORDER BY 1, 2;
-- cheapest departure weekday so far
SELECT strftime('%w', depart_date) AS dow, MIN(price), AVG(price) FROM offers GROUP BY dow;
-- provider reliability
SELECT provider, status, COUNT(*) FROM searches GROUP BY 1, 2;
```

## Adding things

- **Provider:** see [PROVIDERS.md](PROVIDERS.md#adding-a-provider).
- **Notifier:** subclass `Notifier` in `notify/__init__.py`, implement
  `send(report)`, and add it to `REGISTRY`.
- **Schema change:** append a new SQL string to `storage.MIGRATIONS`. Never
  edit old ones.

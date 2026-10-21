# Cheapest Flight Tracker

You fix the first and last location, plus any other conditions you like. The
bot then finds the best and cheapest flights.

Every day it searches a **window of dates** between your **fixed origin and
destination**, using parallel workers. It applies your filters (stops,
budget, airlines, duration, times), stores everything in SQLite, and sends
you a **report sorted by price**, with price-drop and all-time-low alerts.

```
config.yaml ──► planner ──► parallel workers ──► filters ──► SQLite ──► insights ──► report ──► Telegram / email / summary
                (sample→zoom     (per-provider        (your hard        (history)    (trends,
                 within budget)   rate limits)         constraints)                   alerts)
```

## What you get each day

- **Top N options sorted by price.** Each shows dates and nights, airports,
  airlines, stops and layover cities, total time, departure and arrival
  times, the change since yesterday, and a booking link.
- **Alerts** for a new all-time low, a drop of X% since the last run, or
  your target price being hit.
- **Cheapest dates** across the window, plus a **30-day price trend** line.
- A **best value** pick that weighs price against travel time (optional).

## Quick start (local, no API keys)

```bash
pip install -r requirements-dev.txt
cp config.example.yaml config.yaml          # then edit the trip
python -m flight_tracker plan               # what will be searched and the API cost
python -m flight_tracker run --provider mock --no-notify
python -m pytest -q
```

## Going live (GitHub Actions, free)

1. **Edit `config.yaml`.** Set your route, date window, nights and filters. See
   [docs/CONFIGURATION.md](docs/CONFIGURATION.md).
2. **Pick a data source** and add its key as a repo secret (*Settings →
   Secrets and variables → Actions*). See [docs/PROVIDERS.md](docs/PROVIDERS.md).
   - Default setup: `duffel` searches the window (`DUFFEL_ACCESS_TOKEN`) and
     `serpapi` re-prices the cheapest dates on Google Flights
     (`SERPAPI_API_KEY`).
   - A `duffel_test_` token gives sandbox fares only. Use a live token for
     real prices.
3. **Pick where the report goes** and add its secrets:
   - Telegram needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`
   - Email needs `SMTP_USERNAME`, `SMTP_PASSWORD` (a Gmail App Password) and
     optionally `REPORT_EMAIL_TO`
   - The GitHub job summary is always on and needs no setup.
4. **Run it once by hand.** Go to *Actions → Daily flight search → Run
   workflow*. After that it runs daily at 11:30 UTC.

Daily reports land in **`Report/`** on `main`, one folder per trip, e.g.
`Report/T1 Vancouver - Kochi (Round)/2026-10-22.md` (plus `latest.md`).
The history database (`tracker.db`) lives on the **`data`** branch.

## Commands

| Command | What it does |
|---|---|
| `plan` | Shows the search plan and the API calls per day and per month |
| `run` | Search + report (single machine) |
| `search --shard i/n` | Searches one shard of the trips (used by parallel jobs) |
| `merge A.db B.db` | Merges shard databases into the main database |
| `report [--no-notify]` | Builds and sends the report for `--date` (default today) |
| `probe` | One live search per provider, to check the API keys |
| `history [--trip NAME]` | Daily cheapest fare per trip |
| `prune --keep-days N` | Deletes old offers but keeps each day's cheapest forever |

Global flags: `--config`, `--db`, `--date YYYY-MM-DD`, `-v`.

## Documentation

- [PROJECT.md](PROJECT.md): goals, design decisions, roadmap
- [PROGRESS.md](PROGRESS.md): current status and next steps (read this first when resuming)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): modules, data flow, database schema, parallelism
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): every config key
- [docs/PROVIDERS.md](docs/PROVIDERS.md): data sources, costs, and adding a new one
- [docs/OPERATIONS.md](docs/OPERATIONS.md): secrets, the daily workflow, the data branch, troubleshooting

## License

MIT

# Operations

## The daily workflow (`.github/workflows/daily.yml`)

| Job | What it does |
|---|---|
| `plan` | Validates `config.yaml`, picks the shard count (one per enabled trip, capped at `MAX_SHARDS`), and prints the API cost |
| `search` (matrix) | Each shard searches its trips into `shards/shard-i.db` and uploads it as an artifact |
| `report` | Checks out the `data` branch, merges the shards into `tracker.db`, builds and sends the report, commits `Report/<trip folder>/` to `main`, prunes offers older than 120 days, and commits the DB to `data` |

- **Schedule:** `30 11 * * *` (UTC). Edit the cron line to change it.
- **Manual run:** *Actions → Daily flight search → Run workflow*. You can
  type `mock` in the provider box for a free test.
- **Failures:** a failed shard doesn't block the report (`fail-fast: false`,
  `if: always()`). Failed searches are listed at the bottom of the report.
  The job goes red if every search failed or a notifier failed.

## Checking your API keys

- Locally: `python -m flight_tracker probe` runs one real search per
  configured provider (and the verify provider) and prints OK/FAILED, the
  offer count and the cheapest fare. It also flags Duffel test keys.
- In GitHub: the `live-keys` job in `ci.yml` runs the same probe on every
  push and PR once the secrets exist (1 SerpApi credit each time). Its output
  appears in the job summary.

## Secrets

*Settings → Secrets and variables → Actions → New repository secret.* You
only need the secrets for what is enabled in `config.yaml`.

| Secret | Used by |
|---|---|
| `SERPAPI_API_KEY` | serpapi provider |
| `DUFFEL_ACCESS_TOKEN` | duffel provider |
| `TELEGRAM_BOT_TOKEN` | telegram notifier: create a bot with @BotFather |
| `TELEGRAM_CHAT_ID` | telegram notifier: message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | email notifier: for Gmail, turn on 2FA, then create an App Password |
| `REPORT_EMAIL_TO` | email notifier recipient (defaults to `SMTP_USERNAME`) |

## The `data` branch

The first run creates it automatically. It contains:

- `tracker.db`: the full history (open it with any SQLite viewer, or with
  `sqlite3 tracker.db`)

To inspect it locally:

```bash
git fetch origin data && git worktree add ../flight-data origin/data
python -m flight_tracker --db ../flight-data/tracker.db history
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `config error: ...` | The message names the key. Fix `config.yaml` and run `plan` locally. |
| `no provider is ready (missing API keys?)` | Add the provider's secret, or run with `--provider mock` |
| Report says "No fares matched your filters" | Filters are too strict. Check `runs.notes` for the rejection counts, e.g. `rejected={'price': 40}`. |
| `serpapi: ... run out of searches` | Plan quota exhausted. Lower `strategy.budget` or upgrade. |
| Telegram `HTTP 400 chat not found` | Send any message to your bot first, then re-check `TELEGRAM_CHAT_ID`. |
| Gmail `535 Username and Password not accepted` | Use an App Password, not your normal password. |
| Push to `data` rejected | Two runs overlapped. The workflow's `concurrency` group prevents this; re-run the job. |

## Local development

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m flight_tracker --db /tmp/dev.db --date 2026-11-01 run --provider mock --no-notify
python -m flight_tracker --db /tmp/dev.db history
```

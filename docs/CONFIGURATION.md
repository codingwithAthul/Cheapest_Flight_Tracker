# Configuration reference (`config.yaml`)

Start from [`config.example.yaml`](../config.example.yaml). Unknown keys are
rejected, so typos fail loudly. Check your config at any time with
`python -m flight_tracker plan`.

## Top level

| Key | Default | Meaning |
|---|---|---|
| `currency` | `USD` | Currency requested from providers |
| `workers` | `8` | Threads in the search pool |
| `database` | `data/tracker.db` | SQLite path (the workflow overrides it with `--db`) |
| `providers` | `[mock]` | List of `{name, ...options}`. See [PROVIDERS.md](PROVIDERS.md) |
| `notifiers` | `[console]` | List of `{type, ...options}`. See below |
| `verify` | off | Final check on a second provider. See below |
| `report` | | See below |
| `trips` | **required** | One or more trips |

## `trips[]`

| Key | Required | Meaning |
|---|---|---|
| `name` | | Unique label (defaults to `ORIGIN-DEST`) |
| `code` | | Short unique ID, letters and digits only (defaults to `T1`, `T2`, … by position) |
| `from_name` / `to_name` | | Place names for the report folder (default: the airport codes) |
| `origin` | ✔ | IATA code or list, e.g. `[YYZ, YTZ]`. **Fixed.** |
| `destination` | ✔ | IATA code or list. **Fixed.** |
| `trip_type` | | `round_trip` (default) or `one_way` |
| `depart_window.start` / `.end` | ✔ | `YYYY-MM-DD` or relative `+Nd`. Past dates are clamped to tomorrow. |
| `nights` | round trips | `{min, max}` or a single number. Optional when `return_window` is set. |
| `return_window.start` / `.end` | | Round trips: only search returns inside these dates (e.g. leave Nov 23–Dec 14, return Jan 1–14) |
| `adults` | | 1–9 (default 1). Prices are for all adults. |
| `cabin` | | `economy`, `premium_economy`, `business`, `first` |
| `target_price` | | Alert when the cheapest fare is ≤ this |
| `enabled` | | `false` pauses the trip |
| `filters` | | Hard constraints, below |
| `strategy` | | Search plan and budget, below |

### `filters` (all optional)

| Key | Meaning |
|---|---|
| `max_stops` | 0 = nonstop only. Also sent to providers that filter server-side. |
| `max_price` | Drop offers above this total price |
| `max_duration_hours` | Per direction, including layovers |
| `max_layover_hours` / `min_layover_minutes` | Bounds on each connection |
| `include_airlines` | If set, **every** flight must be on one of these (IATA code or name) |
| `exclude_airlines` | Drop offers using any of these |
| `depart_after` / `depart_before` | Outbound local departure time, `"HH:MM"` |
| `return_depart_after` / `return_depart_before` | Same, for the return flight (when the provider gives return details) |
| `allowed_weekdays` | Outbound departure weekdays, 0 = Monday … 6 = Sunday |

### `strategy`

| Key | Default | Meaning |
|---|---|---|
| `mode` | `smart` | `smart` = sample then zoom; `exhaustive` = every combination (evenly thinned to fit the budget) |
| `budget` | `60` | Max searches **per provider** for this trip per day, or `auto`: spread the provider's remaining monthly quota (read from SerpApi's free account endpoint) evenly over the days left in the month, shared across auto trips. Falls back to 7 if the quota can't be read. |
| `auto_reserve` | `10` | With `budget: auto`, searches held back each month for manual runs and key checks |
| `sample_every_days` | `3` | Phase-1 departure-date step (auto-widened to fit) |
| `nights_samples` | `3` | Phase-1 stay lengths spread across `[min, max]` |
| `refine_top_k` | `5` | Phase-2 seeds (the cheapest phase-1 combos) |
| `refine_radius_days` | `2` | Phase-2 neighbourhood (± days on departure and stay length) |
| `keep_offers_per_search` | `5` | Offers stored per search (DB size control) |
| `rotate_daily` | `false` | Shift the phase-1 grid each day so a small budget covers every date and stay length over several days. The report's "Best fares seen in the last 7 days" keeps earlier finds visible. |

**Cost:** daily API calls ≈ Σ `budget` × number of providers. Monthly ≈ ×30.
`plan` prints both.

## `verify` (optional final check)

After the search providers finish a trip, the `top_k` cheapest airport/date
combos are re-priced on this provider. The report shows a "Final check"
table comparing each search price with the verified price.

| Key | Default | Meaning |
|---|---|---|
| `provider` | **required** | e.g. `serpapi` |
| `top_k` | `5` | Combos re-checked per trip per day (= extra API calls) |
| `enabled` | `true` | `false` turns it off without deleting the block |
| `options` | | Provider options, same as under `providers` |

It is skipped when you pass `--provider` (e.g. free `mock` test runs) or `--no-verify`.

## `report`

| Key | Default | Meaning |
|---|---|---|
| `top_n` | `15` | Options listed per trip |
| `output_dir` | `Report` | One folder per trip, named `<code> <from_name> - <to_name> (Round|One-Way)`, holding `YYYY-MM-DD.md/.html` and `latest.md` |
| `value_of_hour` | `0` | If > 0, also show a "best value" pick that minimises `price + value_of_hour × hours` |
| `drop_alert_percent` | `5` | Alert when the cheapest fare falls by at least this % since the last run |

## `notifiers[]`

| type | Options | Secrets (env) |
|---|---|---|
| `console` | | |
| `github_summary` | | Uses `GITHUB_STEP_SUMMARY` automatically |
| `telegram` | `bot_token_env`, `chat_id_env` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| `email` | `smtp_host` (default `smtp.gmail.com`), `smtp_port` (465 SSL / 587 STARTTLS), `to`, `from`, `username_env`, `password_env`, `to_env` | `SMTP_USERNAME`, `SMTP_PASSWORD`, `REPORT_EMAIL_TO` |

Every notifier accepts `only_on_alert: true`, which sends only on days with a
price drop, a new low or a target hit.

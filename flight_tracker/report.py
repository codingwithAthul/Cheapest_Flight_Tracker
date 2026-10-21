"""Render TripSummary objects as Markdown, HTML (email) and Telegram text."""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path
from typing import Optional

from .insights import Option, TripSummary
from .models import Leg


def fmt_minutes(m: Optional[int]) -> str:
    if not m:
        return "?"
    return f"{m // 60}h{m % 60:02d}"


def fmt_money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.0f}"


def fmt_date(d: date) -> str:
    return d.strftime("%a %d %b %Y")


def fmt_change(delta: Optional[float], currency: str) -> str:
    if delta is None:
        return "new"
    if abs(delta) < 1:
        return "same"
    arrow = "▼" if delta < 0 else "▲"
    return f"{arrow} {abs(delta):,.0f}"


def leg_line(leg: Leg) -> str:
    """e.g. 'YYZ 21:45 → COK 03:25 (+2d) · 1 stop via DXB (3h10)'"""
    dep, arr = leg.depart_at, leg.arrive_at
    day_shift = (arr.date() - dep.date()).days
    shift = f" (+{day_shift}d)" if day_shift > 0 else ""
    route = f"{leg.segments[0].origin} {dep:%H:%M} → {leg.segments[-1].destination} {arr:%H:%M}{shift}"
    if leg.stops == 0:
        stops = "nonstop"
    else:
        via = ", ".join(f"{a} ({fmt_minutes(m)})" for a, m in leg.layovers)
        stops = f"{leg.stops} stop{'s' if leg.stops > 1 else ''} via {via}"
    flights = " ".join(f"{s.carrier}{s.flight_number}" for s in leg.segments if s.flight_number)
    parts = [route, stops, fmt_minutes(leg.duration_minutes)]
    if flights:
        parts.append(flights)
    return " · ".join(parts)


def option_dates(o: Option) -> str:
    if o.return_date:
        return f"{fmt_date(o.depart_date)} → {fmt_date(o.return_date)} ({o.nights} nights)"
    return f"{fmt_date(o.depart_date)} (one-way)"


def _trip_header(s: TripSummary) -> str:
    t = s.trip
    kind = f"return, {t.nights_min}-{t.nights_max} nights" if t.is_round_trip else "one-way"
    return (f"{'/'.join(t.origins)} → {'/'.join(t.destinations)} · {kind} · "
            f"departing {t.depart_window.start:%d %b} – {t.depart_window.end:%d %b %Y} · "
            f"{t.adults} adult{'s' if t.adults > 1 else ''}, {t.cabin.replace('_', ' ')}")


def _headline(s: TripSummary) -> str:
    if s.today_min is None:
        return "No fares matched your filters today."
    cur = s.options[0].currency
    parts = [f"Cheapest today: **{fmt_money(s.today_min, cur)}**"]
    if s.prev_min is not None:
        pct = s.change_pct or 0
        parts.append(f"{'▼' if pct < 0 else '▲' if pct > 0 else '='} {abs(pct):.1f}% vs {s.prev_date}")
    if s.all_time_low_before is not None:
        parts.append(f"all-time low before today {fmt_money(s.all_time_low_before, cur)}")
    if s.sparkline:
        parts.append(f"30-day trend `{s.sparkline}`")
    return " · ".join(parts)


# ---------------------------------------------------------------- Markdown


def render_markdown(summaries: list[TripSummary], run_date: date, stats: Optional[dict] = None,
                    errors: Optional[list[str]] = None) -> str:
    lines = [f"# ✈️ Daily flight report — {fmt_date(run_date)}", ""]
    for s in summaries:
        lines += [f"## {s.trip.name}", "", f"_{_trip_header(s)}_", "", _headline(s), ""]
        for a in s.alerts:
            lines.append(f"> 🔔 **{a}**")
        if s.alerts:
            lines.append("")
        if not s.options:
            continue
        lines += ["| # | Price | Δ vs prev | Dates | Route | Airlines | Stops | Total time | Via | Book |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for o in s.options:
            via = ", ".join(a for leg in (o.outbound, o.inbound) if leg for a, _ in leg.layovers) or "—"
            link = f"[link]({o.booking_url})" if o.booking_url else "—"
            lines.append(
                f"| {o.rank} | **{fmt_money(o.price, o.currency)}** | {fmt_change(o.change_vs_prev, o.currency)} | "
                f"{option_dates(o)} | {o.origin}→{o.destination} | {o.airlines} | {o.stops} | "
                f"{fmt_minutes(o.duration_minutes)} | {via} | {link} |"
            )
        lines.append("")
        lines.append("<details><summary>Flight details for the top 5</summary>")
        lines.append("")
        for o in s.options[:5]:
            lines.append(f"**#{o.rank} {fmt_money(o.price, o.currency)}** — {option_dates(o)} "
                         f"(via {', '.join(o.providers)})")
            lines.append(f"- Out: {leg_line(o.outbound)}")
            if o.inbound:
                lines.append(f"- Back: {leg_line(o.inbound)}")
            elif o.return_date:
                lines.append("- Back: details on the booking page")
            lines.append("")
        lines.append("</details>")
        lines.append("")
        if s.best_value:
            b = s.best_value
            lines += [f"**Best value (price + time):** {fmt_money(b.price, b.currency)} · {option_dates(b)} · "
                      f"{b.airlines} · {b.stops} stop(s) · {fmt_minutes(b.duration_minutes)}", ""]
        if s.cheapest_dates:
            lines.append("**Cheapest dates today:** " + " · ".join(
                f"{d:%d %b}{('→' + r.strftime('%d %b')) if r else ''} {fmt_money(p, s.options[0].currency)}"
                for d, r, p in s.cheapest_dates))
            lines.append("")
    if stats:
        lines.append(f"---\n_Searches: {stats.get('ok', 0)} ok, {stats.get('failed', 0)} failed "
                     f"(across {stats.get('runs', 0)} worker run(s))._")
    if errors:
        lines.append("")
        lines.append("_Errors: " + "; ".join(errors) + "_")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- HTML (email)


def render_html(summaries: list[TripSummary], run_date: date, stats: Optional[dict] = None) -> str:
    e = html.escape
    out = [
        "<html><body style=\"font-family:-apple-system,Segoe UI,Arial,sans-serif;color:#1a1a1a;max-width:900px\">",
        f"<h2>✈️ Daily flight report — {e(fmt_date(run_date))}</h2>",
    ]
    for s in summaries:
        out.append(f"<h3 style=\"margin-bottom:2px\">{e(s.trip.name)}</h3>")
        out.append(f"<div style=\"color:#666;font-size:13px\">{e(_trip_header(s))}</div>")
        out.append(f"<p>{e(_headline(s)).replace('**', '')}</p>")
        for a in s.alerts:
            out.append(f"<p style=\"background:#fff4d6;padding:6px 10px;border-radius:6px\">🔔 <b>{e(a)}</b></p>")
        if not s.options:
            continue
        out.append("<table cellpadding=\"6\" style=\"border-collapse:collapse;font-size:13px\">")
        out.append("<tr style=\"background:#f2f4f7;text-align:left\"><th>#</th><th>Price</th><th>Δ</th><th>Dates</th>"
                   "<th>Airlines</th><th>Outbound</th><th>Return</th><th></th></tr>")
        for o in s.options:
            back = leg_line(o.inbound) if o.inbound else ("see booking page" if o.return_date else "—")
            link = f"<a href=\"{e(o.booking_url)}\">Book</a>" if o.booking_url else ""
            out.append(
                f"<tr style=\"border-top:1px solid #e5e7eb\"><td>{o.rank}</td><td><b>{e(fmt_money(o.price, o.currency))}</b></td>"
                f"<td>{e(fmt_change(o.change_vs_prev, o.currency))}</td><td>{e(option_dates(o))}</td>"
                f"<td>{e(o.airlines)}</td><td>{e(leg_line(o.outbound))}</td><td>{e(back)}</td><td>{link}</td></tr>"
            )
        out.append("</table>")
        if s.best_value:
            b = s.best_value
            out.append(f"<p><b>Best value:</b> {e(fmt_money(b.price, b.currency))} · {e(option_dates(b))} · "
                       f"{e(b.airlines)} · {fmt_minutes(b.duration_minutes)}</p>")
    if stats:
        out.append(f"<p style=\"color:#888;font-size:12px\">Searches: {stats.get('ok', 0)} ok, "
                   f"{stats.get('failed', 0)} failed.</p>")
    out.append("</body></html>")
    return "\n".join(out)


# ---------------------------------------------------------------- Telegram


def render_telegram(summaries: list[TripSummary], run_date: date, top: int = 5) -> list[str]:
    """One message per trip (Telegram caps messages at 4096 chars). Uses parse_mode=HTML."""
    e = html.escape
    msgs = []
    for s in summaries:
        lines = [f"✈️ <b>{e(s.trip.name)}</b> — {run_date:%d %b}", f"<i>{e(_trip_header(s))}</i>"]
        lines.append(e(_headline(s).replace("**", "").replace("`", "")))
        for a in s.alerts:
            lines.append(f"🔔 <b>{e(a)}</b>")
        lines.append("")
        for o in s.options[:top]:
            price = f"<b>{e(fmt_money(o.price, o.currency))}</b>"
            if o.booking_url:
                price = f"<a href=\"{e(o.booking_url)}\">{price}</a>"
            lines.append(f"{o.rank}. {price} ({e(fmt_change(o.change_vs_prev, o.currency))}) · {e(option_dates(o))}")
            lines.append(f"    {e(o.airlines)} · {o.stops} stop(s) · {fmt_minutes(o.duration_minutes)} · "
                         f"{e(o.origin)}→{e(o.destination)}")
        if s.best_value:
            b = s.best_value
            lines.append(f"\n⭐ Best value: {e(fmt_money(b.price, b.currency))} · {e(option_dates(b))} · "
                         f"{fmt_minutes(b.duration_minutes)}")
        msg = "\n".join(lines)
        msgs.append(msg[:4000])
    return msgs


def write_report_files(output_dir: str | Path, run_date: date, markdown: str, html_body: str) -> list[Path]:
    d = Path(output_dir)
    d.mkdir(parents=True, exist_ok=True)
    paths = [d / f"{run_date.isoformat()}.md", d / f"{run_date.isoformat()}.html", d / "latest.md"]
    paths[0].write_text(markdown)
    paths[1].write_text(html_body)
    paths[2].write_text(markdown)
    return paths

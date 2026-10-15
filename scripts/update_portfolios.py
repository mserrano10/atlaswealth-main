#!/usr/bin/env python3
"""Recompute portfolio returns from adjusted closes.

Reads holdings, start dates, and start weights in data/portfolios.json.
Writes total return, CAGR, each holding's return, and as_of.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "portfolios.json"
NY = ZoneInfo("America/New_York")


def round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def equal_weights(count: int) -> list[float]:
    if count < 1:
        raise SystemExit("A portfolio needs at least one holding.")
    rounded = [round(1.0 / count, 8) for _ in range(count)]
    rounded[-1] = round(rounded[-1] + (1.0 - sum(rounded)), 8)
    return rounded


def naive_dates(series: pd.Series) -> pd.Series:
    cleaned = series.dropna()
    idx = pd.to_datetime(cleaned.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(NY).tz_localize(None)
    cleaned = cleaned.copy()
    cleaned.index = idx.normalize()
    return cleaned.sort_index()


def close_frame(frame: pd.DataFrame) -> pd.Series:
    if isinstance(frame, pd.Series):
        return frame
    for column in ("Close", "Adj Close"):
        if column in frame.columns:
            return frame[column]
    raise SystemExit("Adjusted close column was not found.")


def download_closes(tickers: list[str], start: date, end: date) -> dict[str, pd.Series]:
    downloaded = yf.download(
        tickers=tickers,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if downloaded is None or downloaded.empty:
        raise SystemExit("No prices were returned.")

    closes: dict[str, pd.Series] = {}
    if len(tickers) == 1:
        closes[tickers[0]] = naive_dates(close_frame(downloaded))
        return closes

    for ticker in tickers:
        if ticker not in downloaded.columns.get_level_values(0):
            raise SystemExit(f"No prices for {ticker}.")
        closes[ticker] = naive_dates(close_frame(downloaded[ticker]))
        if closes[ticker].empty:
            raise SystemExit(f"No prices for {ticker}.")
    return closes


def price_on_or_after(series: pd.Series, day: date, ticker: str) -> tuple[date, float]:
    window = series[series.index >= pd.Timestamp(day)]
    if window.empty:
        raise SystemExit(f"No close for {ticker} on or after {day.isoformat()}.")
    stamp = window.index[0]
    return stamp.date(), float(window.iloc[0])


def price_on_or_before(series: pd.Series, day: date, ticker: str) -> tuple[date, float]:
    window = series[series.index <= pd.Timestamp(day)]
    if window.empty:
        raise SystemExit(f"No close for {ticker} on or before {day.isoformat()}.")
    stamp = window.index[-1]
    return stamp.date(), float(window.iloc[-1])


def parse_start(value: str) -> date:
    parts = value.split("-")
    if len(parts) == 3:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1)
    raise SystemExit(f"Unrecognised start date: {value}")


def refresh(payload: dict) -> dict:
    portfolios = payload.get("portfolios") or []
    if not portfolios:
        raise SystemExit("No portfolios in data/portfolios.json.")

    tickers = sorted({holding["ticker"] for portfolio in portfolios for holding in portfolio["holdings"]})
    starts = [parse_start(portfolio["start"]) for portfolio in portfolios]
    today = datetime.now(NY).date()
    closes = download_closes(tickers, min(starts), today)
    shared_days = None
    for series in closes.values():
        days = {stamp.date() for stamp in series.index if stamp.date() <= today}
        shared_days = days if shared_days is None else shared_days & days
    if not shared_days:
        raise SystemExit("No shared close across holdings.")
    as_of_day = max(shared_days)

    for portfolio in portfolios:
        holdings = portfolio["holdings"]
        if any("start_weight" not in holding for holding in holdings):
            for holding, weight in zip(holdings, equal_weights(len(holdings))):
                holding.setdefault("start_weight", weight)

        start_day = parse_start(portfolio["start"])
        weighted = 0.0
        weight_sum = 0.0
        book_start = None
        for holding in holdings:
            ticker = holding["ticker"]
            series = closes[ticker]
            first_day, first_px = price_on_or_after(series, start_day, ticker)
            _last_day, last_px = price_on_or_before(series, as_of_day, ticker)
            if first_px <= 0 or last_px <= 0:
                raise SystemExit(f"Invalid close for {ticker}.")
            holding["return_pct"] = round1((last_px / first_px - 1.0) * 100.0)
            weight = float(holding["start_weight"])
            weighted += weight * (holding["return_pct"] / 100.0)
            weight_sum += weight
            book_start = first_day if book_start is None else max(book_start, first_day)

        if not weight_sum or book_start is None or as_of_day <= book_start:
            raise SystemExit(f"Could not price {portfolio.get('id', portfolio.get('name'))}.")
        total = weighted / weight_sum
        years = (as_of_day - book_start).days / 365.25
        cagr = (1.0 + total) ** (1.0 / years) - 1.0
        portfolio["total_return_pct"] = round1(total * 100.0)
        portfolio["cagr_pct"] = round1(cagr * 100.0)
        portfolio["end"] = as_of_day.isoformat()

    payload["as_of"] = as_of_day.isoformat()
    return payload


def main() -> None:
    payload = json.loads(DATA_PATH.read_text())
    updated = refresh(payload)
    DATA_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n")
    print(f"Updated {DATA_PATH} as of {updated['as_of']}")
    for portfolio in updated["portfolios"]:
        print(f"{portfolio['id']}: {portfolio['total_return_pct']}% total, {portfolio['cagr_pct']}% CAGR")


if __name__ == "__main__":
    main()

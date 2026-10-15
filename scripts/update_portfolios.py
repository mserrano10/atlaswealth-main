#!/usr/bin/env python3
"""Recompute portfolio returns from adjusted closes.

Reads holdings, start dates, and start weights in data/portfolios.json.
A book with data/lots/<id>.json is valued from those trades instead.
Writes year-to-date return, total return, CAGR, each holding's return, and as_of.
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
LOTS_DIR = ROOT / "data" / "lots"
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


def lot_path(portfolio: dict) -> Path | None:
    path = LOTS_DIR / f"{portfolio['id'].replace('-', '_')}.json"
    return path if path.exists() else None


def load_lots(path: Path) -> list[tuple[str, date, float]]:
    payload = json.loads(path.read_text())
    lots = payload.get("lots") or []
    if not lots:
        raise SystemExit(f"No lots in {path}.")
    parsed: list[tuple[str, date, float]] = []
    for lot in lots:
        if len(lot) != 3:
            raise SystemExit(f"Lot in {path} must be ticker, date, and percent.")
        ticker, day, pct = lot
        parsed.append((str(ticker), parse_start(str(day)), float(pct)))
    return parsed


def unit_fractions(values: list[tuple[str, float]]) -> dict[str, float]:
    total = sum(value for _, value in values)
    if total <= 0:
        raise SystemExit("Holding weights need a positive market value.")
    rounded = [(name, round(value / total, 8)) for name, value in values]
    drift = round(1.0 - sum(weight for _, weight in rounded), 8)
    largest = max(range(len(rounded)), key=lambda index: rounded[index][1])
    name, weight = rounded[largest]
    rounded[largest] = (name, round(weight + drift, 8))
    return dict(rounded)


def sessions_through(series: pd.Series, start: date, end: date) -> list[date]:
    return [stamp.date() for stamp in series.index if start <= stamp.date() <= end]


def price_map(series: pd.Series) -> dict[date, float]:
    return {stamp.date(): float(value) for stamp, value in series.items()}


def refresh_lots(portfolio: dict, path: Path, closes: dict[str, pd.Series], as_of_day: date) -> None:
    """Time-weighted return from lot sizes.

    units = pct / adjusted close. Holdings are cumulative units.
    V_t = sum(H * P). flow_t = sum((H_t - H_{t-1}) * P_t).
    r_t = (V_t - flow_t) / V_{t-1} - 1, chained from the first session.
    """
    lots = load_lots(path)
    tickers = sorted({ticker for ticker, _, _ in lots})
    for ticker in tickers:
        if ticker not in closes or closes[ticker].empty:
            raise SystemExit(f"No prices for {ticker}.")

    first_trade = min(day for _, day, _ in lots)
    sessions = None
    prices: dict[str, dict[date, float]] = {}
    for ticker in tickers:
        prices[ticker] = price_map(closes[ticker])
        days = set(sessions_through(closes[ticker], first_trade, as_of_day))
        sessions = days if sessions is None else sessions & days
    if not sessions:
        raise SystemExit(f"No shared close for {portfolio.get('id')}.")
    calendar = sorted(sessions)

    def on_session(day: date) -> date:
        for session in calendar:
            if session >= day:
                return session
        raise SystemExit(f"No session on or after {day.isoformat()} for {portfolio.get('id')}.")

    flows: dict[tuple[date, str], float] = {}
    for ticker, day, pct in lots:
        if day > as_of_day:
            continue
        session = on_session(day)
        flows[(session, ticker)] = flows.get((session, ticker), 0.0) + pct

    holdings = {ticker: 0.0 for ticker in tickers}
    first_price: dict[str, float] = {}
    chained = 1.0
    ytd_chain = 1.0
    prev_value = None
    book_start = None
    year_end = date(as_of_day.year - 1, 12, 31)
    base_day = max((day for day in calendar if day <= year_end), default=None)
    last_value = 0.0
    last_prices: dict[str, float] = {}

    for day in calendar:
        day_prices = {ticker: prices[ticker][day] for ticker in tickers}
        if any(px <= 0 for px in day_prices.values()):
            raise SystemExit(f"Invalid close while pricing {portfolio.get('id')}.")
        flow = 0.0
        for ticker in tickers:
            pct = flows.get((day, ticker))
            if pct is None:
                continue
            units = pct / day_prices[ticker]
            holdings[ticker] += units
            flow += units * day_prices[ticker]
            if ticker not in first_price and abs(holdings[ticker]) > 1e-12:
                first_price[ticker] = day_prices[ticker]
        for ticker, units in holdings.items():
            if units < -1e-6:
                raise SystemExit(f"Negative units for {ticker} on {day.isoformat()}.")

        value = sum(holdings[ticker] * day_prices[ticker] for ticker in tickers)
        if value <= 0:
            raise SystemExit(f"Could not price {portfolio.get('id')}.")
        if prev_value is None:
            book_start = day
            prev_value = value
            last_value = value
            last_prices = day_prices
            continue
        growth = (value - flow) / prev_value
        chained *= growth
        if base_day is not None and day > base_day:
            ytd_chain *= growth
        prev_value = value
        last_value = value
        last_prices = day_prices

    if book_start is None or as_of_day <= book_start or last_value <= 0:
        raise SystemExit(f"Could not price {portfolio.get('id')}.")
    total = chained - 1.0
    ytd = total if base_day is None else ytd_chain - 1.0
    years = (as_of_day - book_start).days / 365.25
    cagr = (1.0 + total) ** (1.0 / years) - 1.0

    active = [
        ticker
        for ticker in tickers
        if holdings[ticker] * last_prices[ticker] > 1e-8
    ]
    current = unit_fractions([(ticker, holdings[ticker] * last_prices[ticker]) for ticker in active])
    net_capital: dict[str, float] = {}
    for ticker, day, pct in lots:
        if day > as_of_day:
            continue
        net_capital[ticker] = net_capital.get(ticker, 0.0) + pct
    started = unit_fractions([(ticker, net_capital.get(ticker, 0.0)) for ticker in active])
    rows = []
    for ticker in active:
        entry = first_price[ticker]
        last_px = last_prices[ticker]
        rows.append(
            {
                "ticker": ticker,
                "start_weight": started.get(ticker, 0.0),
                "current_weight": current[ticker],
                "return_pct": round1((last_px / entry - 1.0) * 100.0),
            }
        )
    portfolio["holdings"] = rows
    portfolio["ytd_pct"] = round1(ytd * 100.0)
    portfolio["total_return_pct"] = round1(total * 100.0)
    portfolio["cagr_pct"] = round1(cagr * 100.0)
    portfolio["end"] = as_of_day.isoformat()


def portfolio_tickers(portfolio: dict) -> set[str]:
    names = {holding["ticker"] for holding in portfolio.get("holdings") or []}
    path = lot_path(portfolio)
    if path is not None:
        names.update(ticker for ticker, _, _ in load_lots(path))
    return names


def refresh(payload: dict) -> dict:
    portfolios = payload.get("portfolios") or []
    if not portfolios:
        raise SystemExit("No portfolios in data/portfolios.json.")

    tickers = sorted({ticker for portfolio in portfolios for ticker in portfolio_tickers(portfolio)})
    starts = [parse_start(portfolio["start"]) for portfolio in portfolios]
    now = datetime.now(NY)
    today = now.date()
    closes = download_closes(tickers, min(starts), today)
    shared_days = None
    for series in closes.values():
        days = {stamp.date() for stamp in series.index if stamp.date() <= today}
        shared_days = days if shared_days is None else shared_days & days
    if not shared_days:
        raise SystemExit("No shared close across holdings.")
    as_of_day = max(shared_days)
    # The cash close is 16:00 New York. Ignore a same-day bar before then so a
    # midday run does not publish an unfinished session. The weekday workflow
    # runs after the close, so that session is still included.
    if as_of_day == today and (now.hour, now.minute) < (16, 0):
        finished = {day for day in shared_days if day < today}
        if finished:
            as_of_day = max(finished)

    for portfolio in portfolios:
        lots = lot_path(portfolio)
        if lots is not None:
            refresh_lots(portfolio, lots, closes, as_of_day)
            continue

        holdings = portfolio["holdings"]
        if any("start_weight" not in holding for holding in holdings):
            for holding, weight in zip(holdings, equal_weights(len(holdings))):
                holding.setdefault("start_weight", weight)

        start_day = parse_start(portfolio["start"])
        year_end = date(as_of_day.year - 1, 12, 31)
        weighted = 0.0
        weight_sum = 0.0
        book_start = None
        base_values: list[float] = []
        ytd_returns: list[float] = []
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
            if first_day > year_end:
                base_px = first_px
                base_value = weight
            else:
                _base_day, base_px = price_on_or_before(series, year_end, ticker)
                if base_px <= 0:
                    raise SystemExit(f"Invalid close for {ticker}.")
                base_value = weight * (base_px / first_px)
            base_values.append(base_value)
            ytd_returns.append(last_px / base_px - 1.0)

        if not weight_sum or book_start is None or as_of_day <= book_start:
            raise SystemExit(f"Could not price {portfolio.get('id', portfolio.get('name'))}.")
        base_sum = sum(base_values)
        if not base_sum:
            raise SystemExit(f"Could not price {portfolio.get('id', portfolio.get('name'))}.")
        total = weighted / weight_sum
        ytd = sum((value / base_sum) * ret for value, ret in zip(base_values, ytd_returns))
        years = (as_of_day - book_start).days / 365.25
        cagr = (1.0 + total) ** (1.0 / years) - 1.0
        portfolio["ytd_pct"] = round1(ytd * 100.0)
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
        print(
            f"{portfolio['id']}: {portfolio['ytd_pct']}% YTD, "
            f"{portfolio['total_return_pct']}% since inception, "
            f"{portfolio['cagr_pct']}% annualized"
        )


if __name__ == "__main__":
    main()

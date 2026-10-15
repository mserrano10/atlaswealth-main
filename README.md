# atlaswealth-main
Main website atlas wealth repository

## Portfolios

The landing page reads [`data/portfolios.json`](data/portfolios.json) and lists each portfolio, in order, as a card. A card links to `portfolio.html?id=<id>`.

Names are the Roman numeral for the start year, a middle dot, and a letter: `MMXXIV·A`, `MMXXIV·B`, then `MMXXV·A`. The next year uses the next numeral, and letters start again at A when more than one portfolio shares a year. The id is the lowercase numeral, a hyphen, and the lowercase letter, so `MMXXVI·A` is `mmxxvi-a`.

To add a portfolio, append an object to the `portfolios` array:

```json
{
  "id": "mmxxvi-a",
  "name": "MMXXVI·A",
  "screen": "ROIC > 40%",
  "criteria": "Equal weight at the start of Jan 2026, companies with ROIC > 40%",
  "start": "2026-01-02",
  "holdings": [
    { "ticker": "AAPL", "start_weight": 0.5 },
    { "ticker": "MSFT", "start_weight": 0.5 }
  ]
}
```

`screen` and `criteria` stay in the file for reference and are not shown on the site. `start` is the first close (`YYYY-MM-DD`). `start_weight` is the weight at that close; omit it to treat the book as equal weight.

The public cards show year-to-date return, cumulative return since inception, annualized return, and the inception month. `scripts/update_portfolios.py` writes `ytd_pct` from the prior year-end close, using each holding's drifted weight at that close. If a portfolio starts after that close, year-to-date runs from its start date. The script also refreshes each holding's return, total return, CAGR, and `as_of`. Install the dependency with `pip install -r requirements.txt`, then run:

```bash
python scripts/update_portfolios.py
```

A GitHub Actions workflow runs that script every weekday at 21:30 UTC and commits `data/portfolios.json` when the figures change.

MMXXV·C stores a start weight on each holding and uses the 16 April 2025 close. An equal-weight approximation is acceptable for that book, and it is what the refresh script applies.

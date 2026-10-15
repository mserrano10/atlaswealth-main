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

`screen` stores the original screen. `criteria` is the sentence shown on the detail page. `start` is the first close (`YYYY-MM-DD`). `start_weight` is the weight at that close; omit it to treat the book as equal weight.

`scripts/update_portfolios.py` recomputes each holding's return, plus total return and CAGR, from adjusted closes and updates `as_of`. Install the dependency with `pip install -r requirements.txt`, then run:

```bash
python scripts/update_portfolios.py
```

A GitHub Actions workflow runs that script every weekday at 21:30 UTC and commits `data/portfolios.json` when the figures change.

MMXXV·C stores a start weight on each holding and uses the 16 April 2025 close. An equal-weight approximation is acceptable for that book, and it is what the refresh script applies.

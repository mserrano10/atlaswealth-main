# atlaswealth-main
Main website atlas wealth repository

## Adding a portfolio cohort

The Portfolio Performance page reads [`data/portfolios.json`](data/portfolios.json).

To add a yearly cohort, append an object to the `cohorts` array:

```json
{
  "year": 2026,
  "portfolios": []
}
```

Each portfolio needs `name`, `criteria`, `start` (`YYYY-MM`), `end`, `total_return_pct`, `cagr_pct`, and `holdings`. A holding is `{ "ticker": "AAPL" }` and may include `return_pct` when that holding's return is shown. Update `as_of` (`YYYY-MM-DD`) when the figures change.

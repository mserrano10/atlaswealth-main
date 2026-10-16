# atlaswealth-main
Main website atlas wealth repository

## Portfolios

The landing page reads [`data/portfolios.json`](data/portfolios.json) and lists each portfolio, in order, as a card. A card links to `portfolio.html?id=<id>`.

Names are a Roman numeral, a middle dot, and a letter: `MMXXIV·A`, `MMXXIV·B`, `MMXXV·A`. The id is the lowercase numeral, a hyphen, and the lowercase letter, so `MMXXVI·A` is `mmxxvi-a`.

The public file holds only what the site shows: since-inception return, annualized return, year-to-date, the data date, and each holding's ticker, current weight, and return. The cards lead with since-inception return, then annualized and YTD. The close line formats `as_of` as “As of Mon D, YYYY close”.

## Refresh

`scripts/update_portfolios.py` recomputes the figures from adjusted closes. Its inputs are private and are never committed: the script reads them from the JSON file named by `PORTFOLIOS_PRIVATE_PATH`, which must sit outside the repository. In GitHub Actions that file is written from the `PORTFOLIOS_PRIVATE_JSON` repository secret and deleted after the run.

```bash
pip install -r requirements.txt
PORTFOLIOS_PRIVATE_PATH=/path/outside/repo/inputs.json python scripts/update_portfolios.py
```

A workflow runs the script every weekday at 21:30 UTC and commits `data/portfolios.json` when the figures change.

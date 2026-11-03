# market-ml

Production ML on market data, built in public: open tools, honest benchmarks and MLOps projects.

| Package | Status | What it does |
|---|---|---|
| [`india-costs`](packages/india-costs) | v0.1 | Charges on Indian equity trades (STT, stamp duty, exchange, SEBI, IPFT, GST, brokerage, DP) from dated rate tables, so a backtest pays the rates in force on each trade date (₹1 lakh delivery round trip today: ₹237.82, 0.24%) |

Next: an NSE bhavcopy parser with schema checks (code and synthetic fixtures only), an instrument-master schema, then an SEC 8-K event classifier served on Kubernetes.

## Ground rules

- **No market data or model weights in this repo.** CI fails on data, archive and weight files, notebooks saved with outputs, and files over 500 KB; synthetic fixtures live only under paths listed in [`.raw-data-allow`](.raw-data-allow).
- **Licence gate.** Anything published from here (datasets, weights, metrics, reference tables) declares its inputs in a `provenance.toml`, checked against [`licences/sources.toml`](licences/sources.toml). See [DATA_POLICY.md](DATA_POLICY.md).
- **Tools, not calls.** Nothing here recommends buying or selling anything, and nothing reports trading returns.

## Development

Needs [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```bash
make setup   # install the workspace and git hooks
make ci      # lint, typecheck, test, data guards (what GitHub Actions runs)
```

## Disclaimer

Educational engineering content. Not investment advice. Not SEBI-registered. Use of this code for trading in Indian markets is subject to SEBI's retail algorithmic-trading framework ([circular of 4 Feb 2025](https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html)) and your broker's rules. Consult your broker and the primary source.

Code is licensed under [Apache-2.0](LICENSE).

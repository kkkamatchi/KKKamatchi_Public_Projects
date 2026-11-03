# india-costs

Charges on Indian equity trades, computed from **dated** rate tables: a backtest pays the segment rates that were in force on each trade date, so a 2021 trade isn't charged 2026 STT.

Covers NSE equity delivery, intraday, futures and options (on premium) for trade dates from 1 Jul 2020: STT, stamp duty, exchange transaction charges, SEBI turnover fees, NSE IPFT charges and GST, plus brokerage and DP charges from a broker schedule you choose. It has no runtime dependencies; amounts are `Decimal`, rounded to the paisa.

## Use

```python
from datetime import date
from india_costs import ZERODHA, Segment, round_trip

trip = round_trip(
    100_000, 100_000, segment=Segment.EQUITY_DELIVERY, buy_on=date(2026, 11, 3), broker=ZERODHA
)
trip.total  # Decimal('237.82'): rupees, both legs
trip.combined.as_dict()  # per charge
```

From the shell:

```bash
india-costs 100000 --segment equity_delivery --broker zerodha --date 2026-11-03
```

`order_charges(value, segment=..., side=..., on=...)` prices a single order. Pass your own `BrokerSchedule` if your broker isn't listed; `STATUTORY_ONLY` leaves brokerage and DP charges out. For intraday round trips, sell-side STT is levied on the day's VWAP, as the STT Rules require, not on the sell price.

## Rate tables

Rates are bundled in `india_costs/data/nse.toml`. Each entry gives the dates it applied to and the primary source (Finance Act circulars, SEBI and NSE circulars) it was checked against. On load the table is validated: every charge, segment and side must resolve to exactly one rate on every covered date, with no gaps and no overlaps. Trade dates before the coverage start raise `RatesUnavailableError`. Dates after the table's `as_of` date trigger a `StaleRatesWarning`, because rates may have changed since.

## Limits

- **NSE equity only.** No currency, commodity or BSE segments yet.
- **Trades only, not expiry.** Exercise and assignment of options, in-the-money expiry, and physical delivery of stock F&O are not priced. Each carries its own STT (0.15% of intrinsic value on exercised options from 1 Apr 2026; delivery-rate STT on physically settled stock F&O), stamp duty and broker charges. A contract held to expiry is not a sell order.
- **Per-contract waivers.** Exchange charges use NSE's segment rate. NSE's launch waivers for particular index derivatives are not modelled, so costs are overstated for those contracts: FINNIFTY F&O (11 Jan 2021 to 31 Dec 2022), MIDCPNIFTY F&O (from 24 Jan 2022), BANKNIFTY quarterly options (late 2020 to 2021), NIFTYNXT50 F&O (24 Apr to 31 Oct 2024) and NIFTYFPI F&O (12 Aug 2026 to 28 Feb 2027).
- **Rounding.** STT and stamp duty are rounded to the rupee per client, per day, per segment by the clearing corporation, so per-order figures can differ from a contract note by a rupee or so.
- **Client circumstances.** Stamp duty assumes the client is not domiciled in Sikkim, where collection stopped from 20 Aug 2020. Broker schedules ignore discounts and surcharges (for example Zerodha's DP discount for women and extra brokerage on debit balances). Before 3 Jun 2021 Zerodha charged no DP on BTST sells; pass `include_dp=False` for those.
- **Snapshots.** Broker schedules are dated snapshots. Check your broker's current price list.

## Disclaimer

Educational engineering content. Not investment, tax or legal advice. Not SEBI-registered. Verify rates against the primary sources cited in the table before relying on them.

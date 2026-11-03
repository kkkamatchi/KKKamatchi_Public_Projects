"""Command line: print the charges on a round trip.

india-costs 100000 --segment equity_delivery --broker zerodha --date 2026-11-03
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from india_costs._amounts import to_decimal
from india_costs.brokers import STATUTORY_ONLY, ZERODHA
from india_costs.charges import round_trip
from india_costs.rates import RatesError, Segment

BROKERS = {"none": STATUTORY_ONLY, "zerodha": ZERODHA}


def _rupees(text: str) -> Decimal:
    try:
        return to_decimal(text, "value")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="india-costs", description="Charges on a round trip.")
    parser.add_argument(
        "value", type=_rupees, help="buy value in rupees (premium x qty for options)"
    )
    parser.add_argument("--sell-value", type=_rupees, help="sell value (default: same as buy)")
    parser.add_argument(
        "--segment", choices=[s.value for s in Segment], default=Segment.EQUITY_DELIVERY.value
    )
    parser.add_argument("--broker", choices=sorted(BROKERS), default="none")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD")
    args = parser.parse_args(argv)

    try:
        trip = round_trip(
            args.value,
            args.sell_value if args.sell_value is not None else args.value,
            segment=Segment(args.segment),
            buy_on=args.date,
            broker=BROKERS[args.broker],
        )
    except RatesError as exc:
        parser.error(str(exc))
    buy, sell, combined = trip.buy.as_dict(), trip.sell.as_dict(), trip.combined.as_dict()
    print(f"{'charge':<14}{'buy':>12}{'sell':>12}{'total':>12}")
    for name in combined:
        print(f"{name:<14}{buy[name]:>12}{sell[name]:>12}{combined[name]:>12}")
    print(f"{'total':<14}{trip.buy.total:>12}{trip.sell.total:>12}{trip.total:>12}")
    share = f"{trip.total / args.value * 100:.4f}%" if args.value else "n/a"
    print(f"{share} of the buy value ({args.segment}, {args.date}, broker: {args.broker})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

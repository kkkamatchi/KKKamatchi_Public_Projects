"""Broker schedules: brokerage per order and depository (DP) charges.

Statutory and exchange charges come from the dated rate table. What a broker
adds on top varies by broker and plan, so it is passed in as a schedule. Build
your own with `BrokerSchedule` if yours is not listed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from india_costs._amounts import Amount, to_decimal
from india_costs.rates import Segment

ZERO = Decimal(0)


@dataclass(frozen=True)
class Brokerage:
    """Brokerage on one executed order: a flat fee, or a rate with an optional cap."""

    rate: Decimal = ZERO
    cap: Decimal | None = None
    flat: Decimal = ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", to_decimal(self.rate, "brokerage rate"))
        object.__setattr__(self, "flat", to_decimal(self.flat, "flat brokerage"))
        if self.cap is not None:
            object.__setattr__(self, "cap", to_decimal(self.cap, "brokerage cap"))
        if self.rate >= 1:
            raise ValueError(f"brokerage rate is a fraction of value, got {self.rate}")
        if self.flat and self.rate:
            raise ValueError("set either a flat fee or a rate, not both")

    def amount(self, value: Decimal) -> Decimal:
        if value == 0:
            return ZERO
        if self.flat:
            return self.flat
        fee = value * self.rate
        return fee if self.cap is None else min(fee, self.cap)


@dataclass(frozen=True)
class BrokerSchedule:
    """Brokerage by segment, plus DP charges as (first trade date, amount) steps."""

    name: str
    delivery: Brokerage = Brokerage()
    intraday: Brokerage = Brokerage()
    futures: Brokerage = Brokerage()
    options: Brokerage = Brokerage()
    dp_charges: tuple[tuple[date, Amount], ...] = ()  # per scrip per day, before GST
    as_of: date | None = None
    source: str = ""

    def __post_init__(self) -> None:
        steps = tuple((start, to_decimal(amount, "DP charge")) for start, amount in self.dp_charges)
        starts = [start for start, _ in steps]
        if starts != sorted(set(starts)):
            raise ValueError("dp_charges must be in strictly increasing date order")
        object.__setattr__(self, "dp_charges", steps)

    def brokerage(self, segment: Segment, value: Decimal) -> Decimal:
        rule = {
            Segment.EQUITY_DELIVERY: self.delivery,
            Segment.EQUITY_INTRADAY: self.intraday,
            Segment.EQUITY_FUTURES: self.futures,
            Segment.EQUITY_OPTIONS: self.options,
        }[segment]
        return rule.amount(value)

    def dp_charge(self, on: date) -> Decimal:
        """DP charge per scrip per day on delivery sells, before GST."""
        current = ZERO
        for start, amount in self.dp_charges:
            if start > on:
                break
            current = to_decimal(amount)
        return current


# zerodha.com/charges, checked against archived copies from Jun 2020 to Nov 2026. Not
# modelled: the Rs 0.25 DP discount for female first holders (from Jun 2024); no DP on
# BTST sells before the 3 Jun 2021 settlement change (pass include_dp=False); the extra
# brokerage on debit-balance or collateral-shortfall accounts; and charges on exercised,
# assigned or physically settled F&O.
ZERODHA = BrokerSchedule(
    name="Zerodha (equity)",
    intraday=Brokerage(rate=Decimal("0.0003"), cap=Decimal(20)),
    futures=Brokerage(rate=Decimal("0.0003"), cap=Decimal(20)),
    options=Brokerage(flat=Decimal(20)),
    dp_charges=(
        (date(2020, 7, 1), Decimal("13.5")),  # CDSL 5.5 + Zerodha 8
        (date(2024, 6, 1), Decimal(13)),  # CDSL cut its fee by 50 paise
    ),
    as_of=date(2026, 11, 3),
    source="https://zerodha.com/charges",
)

STATUTORY_ONLY = BrokerSchedule(name="statutory and exchange charges only")

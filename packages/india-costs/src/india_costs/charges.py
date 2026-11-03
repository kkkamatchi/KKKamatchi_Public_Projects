"""Charges on one order and on a buy-then-sell round trip."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from india_costs._amounts import Amount, to_decimal
from india_costs.brokers import STATUTORY_ONLY, BrokerSchedule
from india_costs.rates import (
    Component,
    Exchange,
    RateTable,
    Segment,
    Side,
    StaleRatesWarning,
    default_table,
)

PAISA = Decimal("0.01")
ZERO = Decimal(0)


@dataclass(frozen=True)
class Charges:
    """Charges in rupees, each rounded to the paisa."""

    brokerage: Decimal = ZERO
    stt: Decimal = ZERO
    exchange_txn: Decimal = ZERO
    sebi_fee: Decimal = ZERO
    ipft: Decimal = ZERO
    stamp_duty: Decimal = ZERO
    dp_charge: Decimal = ZERO
    gst: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return sum(self.as_dict().values(), ZERO)

    def as_dict(self) -> dict[str, Decimal]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def __add__(self, other: Charges) -> Charges:
        mine, theirs = self.as_dict(), other.as_dict()
        return Charges(**{name: mine[name] + theirs[name] for name in mine})


@dataclass(frozen=True)
class RoundTrip:
    buy: Charges
    sell: Charges

    @property
    def combined(self) -> Charges:
        return self.buy + self.sell

    @property
    def total(self) -> Decimal:
        return self.combined.total


def _trade_date(on: date) -> date:
    if isinstance(on, datetime):  # includes pandas.Timestamp
        raise TypeError(
            f"on must be a datetime.date, not {type(on).__name__}: pass ts.date() "
            "(convert a tz-aware timestamp to Asia/Kolkata first)"
        )
    return on


def _paise(x: Decimal) -> Decimal:
    return x.quantize(PAISA, rounding=ROUND_HALF_UP)


def order_charges(
    value: Amount,
    *,
    segment: Segment,
    side: Side,
    on: date,
    exchange: Exchange = Exchange.NSE,
    broker: BrokerSchedule = STATUTORY_ONLY,
    include_dp: bool = True,
    stt_value: Amount | None = None,
    table: RateTable | None = None,
) -> Charges:
    """Charges on one executed order.

    `value` is price x quantity; for options it is premium x quantity. STT on an
    intraday sell is levied on the client's VWAP in the scrip that day times the
    quantity sold: pass that as `stt_value` (`round_trip` does this for you). DP
    charges apply to delivery sells once per scrip per day: pass `include_dp=False`
    for a second sell of the same scrip on the same day.
    """
    segment, side, exchange = Segment(segment), Side(side), Exchange(exchange)
    on = _trade_date(on)
    amount = to_decimal(value, "trade value")
    stt_basis = amount if stt_value is None else to_decimal(stt_value, "stt_value")
    table = table or default_table()
    if on > table.as_of:
        warnings.warn(
            f"rates checked up to {table.as_of}; assuming none changed by {on}",
            StaleRatesWarning,
            stacklevel=2,
        )

    def rate(component: Component) -> Decimal:
        return table.lookup(component, exchange, segment, side, on).rate

    brokerage = broker.brokerage(segment, amount)
    exchange_txn = amount * rate(Component.EXCHANGE_TXN)
    sebi_fee = amount * rate(Component.SEBI_FEE)
    ipft = amount * rate(Component.IPFT)
    is_delivery_sell = segment is Segment.EQUITY_DELIVERY and side is Side.SELL
    dp_charge = broker.dp_charge(on) if is_delivery_sell and include_dp and amount else ZERO
    gst = (brokerage + exchange_txn + ipft + dp_charge) * rate(Component.GST)
    gst += sebi_fee * rate(Component.GST_ON_SEBI_FEE)
    return Charges(
        brokerage=_paise(brokerage),
        stt=_paise(stt_basis * rate(Component.STT)),
        exchange_txn=_paise(exchange_txn),
        sebi_fee=_paise(sebi_fee),
        ipft=_paise(ipft),
        stamp_duty=_paise(amount * rate(Component.STAMP_DUTY)),
        dp_charge=_paise(dp_charge),
        gst=_paise(gst),
    )


def round_trip(
    buy_value: Amount,
    sell_value: Amount,
    *,
    segment: Segment,
    buy_on: date,
    sell_on: date | None = None,
    exchange: Exchange = Exchange.NSE,
    broker: BrokerSchedule = STATUTORY_ONLY,
    include_dp: bool = True,
    table: RateTable | None = None,
) -> RoundTrip:
    """Charges on buying a quantity and later selling the same quantity.

    `sell_on` defaults to `buy_on`. For intraday trades the sell-side STT is levied
    on the day's VWAP, which for equal quantities is the mean of the two values.
    `include_dp` applies to the sell leg. A contract held to expiry is not a sell:
    exercise, assignment and physical settlement are not priced here.
    """
    segment, exchange = Segment(segment), Exchange(exchange)
    sell_on = sell_on or buy_on
    stt_value = None
    if segment is Segment.EQUITY_INTRADAY:
        buy, sell = to_decimal(buy_value, "buy value"), to_decimal(sell_value, "sell value")
        stt_value = (buy + sell) / 2

    def leg(
        value: Amount, side: Side, on: date, stt: Amount | None = None, dp: bool = True
    ) -> Charges:
        return order_charges(
            value,
            segment=segment,
            side=side,
            on=on,
            exchange=exchange,
            broker=broker,
            include_dp=dp,
            stt_value=stt,
            table=table,
        )

    return RoundTrip(
        buy=leg(buy_value, Side.BUY, buy_on),
        sell=leg(sell_value, Side.SELL, sell_on, stt_value, include_dp),
    )

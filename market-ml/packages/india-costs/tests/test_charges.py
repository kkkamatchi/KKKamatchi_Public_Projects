"""Expected figures are worked by hand from the cited circulars, not from the code."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from india_costs import (
    STATUTORY_ONLY,
    ZERODHA,
    Brokerage,
    BrokerSchedule,
    RatesUnavailableError,
    Segment,
    Side,
    StaleRatesWarning,
    default_table,
    order_charges,
    round_trip,
)

DELIVERY, INTRADAY = Segment.EQUITY_DELIVERY, Segment.EQUITY_INTRADAY
FUTURES, OPTIONS = Segment.EQUITY_FUTURES, Segment.EQUITY_OPTIONS


def test_bundled_table_is_valid_and_sourced() -> None:
    table = default_table()
    assert table.coverage_start == date(2020, 7, 1)
    assert all(r.source.startswith("https://") for r in table.rates)


def test_one_lakh_delivery_round_trip_today() -> None:
    """The roadmap's ~0.24% check: Rs 1 lakh in and out, Zerodha, 3 Nov 2026."""
    trip = round_trip(100_000, 100_000, segment=DELIVERY, buy_on=date(2026, 11, 3), broker=ZERODHA)
    assert trip.buy.as_dict() == {
        "brokerage": Decimal("0.00"),
        "stt": Decimal("100.00"),
        "exchange_txn": Decimal("3.07"),  # Rs 306.99/crore
        "sebi_fee": Decimal("0.10"),
        "ipft": Decimal("0.00"),  # Rs 0.01/crore
        "stamp_duty": Decimal("15.00"),
        "dp_charge": Decimal("0.00"),
        "gst": Decimal("0.57"),  # 18% of (3.0699 + 0.0001 + 0.10)
    }
    assert trip.sell.as_dict() == {
        "brokerage": Decimal("0.00"),
        "stt": Decimal("100.00"),
        "exchange_txn": Decimal("3.07"),
        "sebi_fee": Decimal("0.10"),
        "ipft": Decimal("0.00"),
        "stamp_duty": Decimal("0.00"),
        "dp_charge": Decimal("13.00"),
        "gst": Decimal("2.91"),  # 18% of (3.0699 + 0.0001 + 13 + 0.10)
    }
    assert trip.total == Decimal("237.82")
    assert Decimal("0.0023") < trip.total / 100_000 < Decimal("0.0025")


def test_one_lakh_delivery_round_trip_in_2021() -> None:
    """Older rates: Rs 345/crore exchange, DP Rs 13.5, no GST on the SEBI fee."""
    trip = round_trip(100_000, 100_000, segment=DELIVERY, buy_on=date(2021, 6, 15), broker=ZERODHA)
    assert trip.buy.total == Decimal("119.17")
    assert trip.sell.dp_charge == Decimal("13.50")
    assert trip.sell.gst == Decimal("3.05")
    assert trip.total == Decimal("239.27")


@pytest.mark.parametrize(
    ("on", "futures_stt", "options_stt"),
    [
        (date(2022, 6, 1), "100.00", "50.00"),
        (date(2023, 6, 1), "125.00", "62.50"),
        (date(2025, 6, 1), "200.00", "100.00"),
        (date(2026, 3, 31), "200.00", "100.00"),
        (date(2026, 4, 1), "500.00", "150.00"),
    ],
)
def test_fo_stt_follows_the_finance_acts(on: date, futures_stt: str, options_stt: str) -> None:
    futures = order_charges(1_000_000, segment=FUTURES, side=Side.SELL, on=on)
    options = order_charges(100_000, segment=OPTIONS, side=Side.SELL, on=on)
    assert futures.stt == Decimal(futures_stt)
    assert options.stt == Decimal(options_stt)


@pytest.mark.parametrize("segment", [FUTURES, OPTIONS, INTRADAY])
def test_no_stt_on_derivative_or_intraday_buys(segment: Segment) -> None:
    assert order_charges(100_000, segment=segment, side=Side.BUY, on=date(2026, 6, 1)).stt == 0


def test_stamp_duty_only_on_buys() -> None:
    on = date(2025, 1, 10)
    buy = order_charges(100_000, segment=DELIVERY, side=Side.BUY, on=on)
    sell = order_charges(100_000, segment=DELIVERY, side=Side.SELL, on=on)
    assert (buy.stamp_duty, sell.stamp_duty) == (Decimal("15.00"), Decimal("0.00"))


def test_gst_on_sebi_fee_starts_2022_07_18() -> None:
    def gst(on: date) -> Decimal:
        return order_charges(1_000_000, segment=DELIVERY, side=Side.BUY, on=on).gst

    assert gst(date(2022, 7, 15)) == Decimal("6.21")  # 18% of 34.50 exchange + 0.001 IPFT
    assert gst(date(2022, 7, 18)) == Decimal("6.39")  # plus 18% of the Rs 1.00 SEBI fee


def test_halved_sebi_fee_in_2020() -> None:
    charges = order_charges(10_000_000, segment=DELIVERY, side=Side.BUY, on=date(2020, 12, 1))
    assert charges.sebi_fee == Decimal("5.00")


def test_ipft_by_period_on_options_premium() -> None:
    def ipft(on: date) -> Decimal:
        return order_charges(1_000_000, segment=OPTIONS, side=Side.SELL, on=on).ipft

    assert ipft(date(2022, 1, 3)) == Decimal("0.00")
    assert ipft(date(2025, 6, 2)) == Decimal("5.00")  # Rs 50/crore of premium
    assert ipft(date(2026, 6, 1)) == Decimal("0.00")


def test_intraday_stt_uses_the_days_vwap() -> None:
    """Buy 500 at 100, sell 500 at 105: STT on the 102.50 average, Rs 12.81."""
    trip = round_trip(50_000, 52_500, segment=INTRADAY, buy_on=date(2026, 11, 3), broker=ZERODHA)
    assert trip.sell.stt == Decimal("12.81")
    assert (trip.buy.brokerage, trip.sell.brokerage) == (Decimal("15.00"), Decimal("15.75"))


def test_intraday_brokerage_is_capped() -> None:
    charges = order_charges(
        200_000, segment=INTRADAY, side=Side.BUY, on=date(2026, 11, 3), broker=ZERODHA
    )
    assert charges.brokerage == Decimal("20.00")


def test_option_buy_with_flat_brokerage() -> None:
    charges = order_charges(
        5_000, segment=OPTIONS, side=Side.BUY, on=date(2026, 11, 3), broker=ZERODHA
    )
    assert charges.brokerage == Decimal("20.00")
    assert charges.exchange_txn == Decimal("1.78")  # Rs 3,552.99/crore of premium
    assert charges.stamp_duty == Decimal("0.15")
    assert charges.gst == Decimal("3.92")
    assert charges.total == Decimal("25.86")


def test_dp_charge_history_and_opt_out() -> None:
    def dp(on: date, include_dp: bool = True) -> Decimal:
        sell = order_charges(
            50_000, segment=DELIVERY, side=Side.SELL, on=on, broker=ZERODHA, include_dp=include_dp
        )
        return sell.dp_charge

    assert dp(date(2024, 5, 31)) == Decimal("13.50")
    assert dp(date(2024, 6, 1)) == Decimal("13.00")
    assert dp(date(2024, 6, 1), include_dp=False) == 0


def test_dp_steps_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="increasing"):
        BrokerSchedule(
            name="x", dp_charges=((date(2024, 1, 2), Decimal(1)), (date(2024, 1, 1), Decimal(2)))
        )


def test_dates_outside_the_table() -> None:
    with pytest.raises(RatesUnavailableError):
        order_charges(1000, segment=DELIVERY, side=Side.BUY, on=date(2020, 6, 30))
    with pytest.warns(StaleRatesWarning, match="checked up to 2026-11-03"):
        order_charges(1000, segment=DELIVERY, side=Side.BUY, on=date(2026, 11, 4))


def test_value_types() -> None:
    on = date(2026, 1, 5)
    exact = order_charges("100000", segment=DELIVERY, side=Side.BUY, on=on)
    assert order_charges(100000.0, segment=DELIVERY, side=Side.BUY, on=on) == exact
    assert order_charges(0, segment=OPTIONS, side=Side.BUY, on=on, broker=ZERODHA).total == 0
    with pytest.raises(ValueError, match="non-negative"):
        order_charges(-1, segment=DELIVERY, side=Side.BUY, on=on)
    with pytest.raises(ValueError, match="not a number"):
        order_charges("lots", segment=DELIVERY, side=Side.BUY, on=on)
    with pytest.raises(TypeError):
        order_charges(True, segment=DELIVERY, side=Side.BUY, on=on)


def test_statutory_only_has_no_broker_charges() -> None:
    trip = round_trip(100_000, 100_000, segment=DELIVERY, buy_on=date(2026, 11, 3))
    assert trip.combined.brokerage == trip.combined.dp_charge == 0
    assert trip.total == Decimal("237.82") - Decimal("13.00") - Decimal("2.34")
    assert STATUTORY_ONLY.dp_charge(date(2026, 1, 1)) == 0


def test_plain_strings_behave_like_enums() -> None:
    on = date(2026, 11, 3)
    as_enum = round_trip(100_000, 100_000, segment=DELIVERY, buy_on=on, broker=ZERODHA)
    as_str = round_trip(100_000, 100_000, segment="equity_delivery", buy_on=on, broker=ZERODHA)  # type: ignore[arg-type]
    assert as_str == as_enum
    sell = order_charges(52_500, segment="equity_intraday", side="sell", on=on, stt_value=51_250)  # type: ignore[arg-type]
    assert sell.stt == Decimal("12.81")
    with pytest.raises(ValueError, match="crypto"):
        order_charges(1, segment="crypto", side="buy", on=on)  # type: ignore[arg-type]


class Float64(float):
    """Stands in for numpy.float64: a float subclass with a decorated repr."""

    def __repr__(self) -> str:
        return f"np.float64({float(self)!r})"


class Int64:
    """Stands in for numpy.int64: not an int, but supports __index__."""

    def __init__(self, n: int) -> None:
        self.n = n

    def __index__(self) -> int:
        return self.n


def test_numpy_style_scalars_and_negative_zero() -> None:
    on = date(2026, 1, 5)
    exact = order_charges(100_000, segment=DELIVERY, side=Side.BUY, on=on)
    assert order_charges(Float64(100000.0), segment=DELIVERY, side=Side.BUY, on=on) == exact
    assert order_charges(Int64(100000), segment=DELIVERY, side=Side.BUY, on=on) == exact
    zero = order_charges(-0.0, segment=DELIVERY, side=Side.BUY, on=on)
    assert not any(v.is_signed() for v in zero.as_dict().values())
    with pytest.raises(ValueError, match="finite"):
        order_charges("NaN", segment=DELIVERY, side=Side.BUY, on=on)


def test_datetime_trade_dates_rejected() -> None:
    with pytest.raises(TypeError, match=r"ts\.date\(\)"):
        order_charges(1, segment=DELIVERY, side=Side.BUY, on=datetime(2026, 1, 5, 9, 15))


def test_round_trip_can_skip_dp_for_btst_sells() -> None:
    trip = round_trip(
        100_000,
        100_000,
        segment=DELIVERY,
        buy_on=date(2021, 3, 1),
        sell_on=date(2021, 3, 2),
        broker=ZERODHA,
        include_dp=False,
    )
    assert trip.sell.dp_charge == 0


def test_broker_numbers_are_validated_and_coerced() -> None:
    mine = BrokerSchedule(
        name="mine",
        intraday=Brokerage(rate=Decimal("0.0003"), cap=20),  # type: ignore[arg-type]
        dp_charges=((date(2020, 7, 1), 13),),
    )
    on = date(2026, 11, 3)
    big = order_charges(1_000_000, segment=INTRADAY, side=Side.BUY, on=on, broker=mine)
    assert big.brokerage == Decimal("20.00")
    assert mine.dp_charge(on) == Decimal(13)
    with pytest.raises(ValueError, match="non-negative"):
        Brokerage(flat=Decimal(-50))
    with pytest.raises(ValueError, match="not both"):
        Brokerage(rate=Decimal("0.001"), flat=Decimal(20))

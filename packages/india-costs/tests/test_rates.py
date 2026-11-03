from datetime import date
from decimal import Decimal

import pytest

from india_costs import (
    Component,
    Exchange,
    RatesUnavailableError,
    RateTableError,
    Segment,
    Side,
    load_table,
)

HEADER = """
schema_version = 1
as_of = 2026-01-31
coverage_start = 2026-01-01
"""


def entry(component: str, *, rate: str = '"0"', start: str = "2026-01-01", **extra: str) -> str:
    """One [[rate]] entry; keyword values are raw TOML."""
    fields = {"segment": '"*"', "side": '"both"', "source": '"https://example.org/c"', **extra}
    lines = [f'component = "{component}"', f"rate = {rate}", f"start = {start}"]
    lines += [f"{k} = {v}" for k, v in fields.items()]
    return "\n[[rate]]\n" + "\n".join(lines) + "\n"


def table(*stt_entries: str) -> str:
    """A valid all-zero table, with STT replaced by the given entries."""
    others = "".join(entry(c) for c in Component if c is not Component.STT)
    return HEADER + others + "".join(stt_entries or (entry("stt"),))


def test_minimal_table_loads() -> None:
    t = load_table(table())
    rate = t.lookup(
        Component.STT, Exchange.NSE, Segment.EQUITY_OPTIONS, Side.SELL, date(2026, 1, 9)
    )
    assert rate.rate == 0


def test_lookup_picks_the_period_in_force() -> None:
    t = load_table(
        table(
            entry("stt", rate='"0.001"', end="2026-01-14"),
            entry("stt", rate='"0.002"', start="2026-01-15"),
        )
    )

    def stt(day: int) -> Decimal:
        on = date(2026, 1, day)
        return t.lookup(Component.STT, Exchange.NSE, Segment.EQUITY_DELIVERY, Side.BUY, on).rate

    assert stt(14) == Decimal("0.001")
    assert stt(15) == Decimal("0.002")


def test_dates_before_coverage_raise() -> None:
    t = load_table(table())
    with pytest.raises(RatesUnavailableError, match="no rates before 2026-01-01"):
        t.lookup(Component.STT, Exchange.NSE, Segment.EQUITY_DELIVERY, Side.BUY, date(2025, 12, 31))


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ((entry("stt", end="2026-01-10"), entry("stt", start="2026-01-12")), "gap between"),
        ((entry("stt"), entry("stt", side='"sell"', segment='"equity_futures"')), "overlap"),
        ((entry("stt", start="2026-01-05"),), "nothing from 2026-01-01"),
        ((entry("stt", end="2026-01-20"),), "nothing after 2026-01-20"),
        ((entry("stt", rate='"1.5"'),), "not a fraction"),
        ((entry("stt", end="2025-12-01"),), "ends before it starts"),
        ((entry("stt", segment='"crypto"'),), "unknown segment"),
        ((entry("stt", source='"http://insecure.example"'),), "https"),
    ],
)
def test_validation_rejects_bad_tables(entries: tuple[str, ...], message: str) -> None:
    with pytest.raises(RateTableError, match=message):
        load_table(table(*entries))


def test_float_rates_rejected() -> None:
    with pytest.raises(RateTableError, match="string"):
        load_table(table(entry("stt", rate="0.001")))


def test_unknown_fields_rejected() -> None:
    with pytest.raises(RateTableError, match="unknown fields"):
        load_table(table(entry("stt", segmnet='"x"')))


def test_schema_version_required() -> None:
    with pytest.raises(RateTableError, match="schema_version"):
        load_table(table().replace("schema_version = 1", "schema_version = 2"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (table().replace("as_of = 2026-01-31", "as_of = 2026-01-31T00:00:00"), "not datetimes"),
        (table(entry("stt", start="2026-01-01T09:15:00")), "not datetimes"),
        (table().replace("as_of = 2026-01-31", "as_of = 2025-12-01"), "before coverage_start"),
        (table(entry("stt", rate='"NaN"')), "finite"),
        (table(entry("stt", segment='["equity_delivery"]')), "must be strings"),
        (table(entry("stt", source="5")), "must be strings"),
        (HEADER + "rate = 5\n", r"\[\[rate\]\]"),
    ],
)
def test_malformed_tables_raise_rate_table_error(text: str, message: str) -> None:
    with pytest.raises(RateTableError, match=message):
        load_table(text)

"""Dated rate tables: load, validate and look up statutory and exchange charges.

A table lists each rate with the trade dates it applied to, so a backtest of a
2021 trade is charged 2021 rates. Validation guarantees that every component,
segment and side resolves to exactly one rate on every date the table covers.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import cache, cached_property
from importlib import resources
from itertools import pairwise, product
from typing import TypeGuard


class Exchange(StrEnum):
    NSE = "NSE"


class Segment(StrEnum):
    EQUITY_DELIVERY = "equity_delivery"
    EQUITY_INTRADAY = "equity_intraday"
    EQUITY_FUTURES = "equity_futures"
    EQUITY_OPTIONS = "equity_options"  # charged on premium


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Component(StrEnum):
    STT = "stt"
    STAMP_DUTY = "stamp_duty"
    EXCHANGE_TXN = "exchange_txn"
    SEBI_FEE = "sebi_fee"
    IPFT = "ipft"
    GST = "gst"  # on brokerage, exchange, IPFT and DP charges, not on trade value
    GST_ON_SEBI_FEE = "gst_on_sebi_fee"  # SEBI fees joined the GST base on 2022-07-18


ANY = "*"
BOTH = "both"
SCHEMA_VERSION = 1
_FIELDS = frozenset(
    {"component", "exchange", "segment", "side", "rate", "start", "end", "source", "note"}
)


class RatesError(Exception):
    """Base class for rate-table errors."""


class RatesUnavailableError(RatesError, LookupError):
    """No rate is known for the requested date."""


class RateTableError(RatesError, ValueError):
    """The rate table itself is malformed."""


class StaleRatesWarning(UserWarning):
    """A trade date falls after the date the table was last checked."""


@dataclass(frozen=True)
class Rate:
    component: Component
    exchange: str
    segment: str
    side: str
    rate: Decimal
    start: date
    end: date | None  # inclusive; None while still in force
    source: str
    note: str = ""

    def matches(self, component: str, exchange: str, segment: str, side: str) -> bool:
        return (
            self.component == component
            and self.exchange in (exchange, ANY)
            and self.segment in (segment, ANY)
            and self.side in (side, BOTH)
        )

    def covers(self, day: date) -> bool:
        return self.start <= day and (self.end is None or day <= self.end)


@dataclass(frozen=True)
class RateTable:
    as_of: date
    coverage_start: date
    rates: tuple[Rate, ...]

    @cached_property
    def _by_component(self) -> Mapping[str, tuple[Rate, ...]]:
        return {c: tuple(r for r in self.rates if r.component == c) for c in Component}

    def periods(
        self, component: Component, exchange: Exchange, segment: Segment, side: Side
    ) -> list[Rate]:
        """Every rate that applies to this key, oldest first."""
        hits = (
            r
            for r in self._by_component[component]
            if r.matches(component, exchange, segment, side)
        )
        return sorted(hits, key=lambda r: r.start)

    def lookup(
        self, component: Component, exchange: Exchange, segment: Segment, side: Side, on: date
    ) -> Rate:
        if on < self.coverage_start:
            raise RatesUnavailableError(f"no rates before {self.coverage_start} (asked for {on})")
        hits = [r for r in self.periods(component, exchange, segment, side) if r.covers(on)]
        key = f"{component} {exchange} {segment} {side}"
        if not hits:
            raise RatesUnavailableError(f"no {key} rate on {on}")
        if len(hits) > 1:
            raise RateTableError(f"overlapping {key} rates on {on}")
        return hits[0]

    def validate(self) -> None:
        problems = list(self._entry_problems())
        if self.as_of < self.coverage_start:
            problems.append(f"as_of {self.as_of} is before coverage_start {self.coverage_start}")
        for key in product(Component, Exchange, Segment, Side):
            problems.extend(self._coverage_problems(*key))
        if problems:
            raise RateTableError("invalid rate table:\n  " + "\n  ".join(problems))

    def _entry_problems(self) -> Iterator[str]:
        segments = {*Segment, ANY}
        for r in self.rates:
            where = f"{r.component} {r.segment} {r.side} from {r.start}"
            if not Decimal(0) <= r.rate < Decimal(1):
                yield f"{where}: rate {r.rate} is not a fraction in [0, 1)"
            if r.end is not None and r.end < r.start:
                yield f"{where}: ends before it starts"
            if r.exchange not in {*Exchange, ANY}:
                yield f"{where}: unknown exchange {r.exchange!r}"
            if r.segment not in segments:
                yield f"{where}: unknown segment {r.segment!r}"
            if r.side not in {*Side, BOTH}:
                yield f"{where}: unknown side {r.side!r}"
            if not r.source.startswith("https://"):
                yield f"{where}: source must be an https URL"

    def _coverage_problems(
        self, component: Component, exchange: Exchange, segment: Segment, side: Side
    ) -> Iterator[str]:
        label = f"{component} {exchange} {segment} {side}"
        periods = self.periods(component, exchange, segment, side)
        if not periods:
            yield f"{label}: no rates"
            return
        if periods[0].start > self.coverage_start:
            yield f"{label}: nothing from {self.coverage_start} to {periods[0].start}"
        for prev, nxt in pairwise(periods):
            if prev.end is None or prev.end >= nxt.start:
                yield f"{label}: periods starting {prev.start} and {nxt.start} overlap"
            elif prev.end + timedelta(days=1) < nxt.start:
                yield f"{label}: gap between {prev.end} and {nxt.start}"
        last = periods[-1].end
        if last is not None and last < self.as_of:
            yield f"{label}: nothing after {last}"


def _is_date(value: object) -> TypeGuard[date]:
    return isinstance(value, date) and not isinstance(value, datetime)


def _parse_rate(index: int, raw: object) -> Rate:
    where = f"rate #{index + 1}"
    if not isinstance(raw, dict):
        raise RateTableError(f"{where}: must be a [[rate]] table")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise RateTableError(f"{where}: unknown fields {sorted(unknown)}")
    missing = {"component", "segment", "side", "rate", "start", "source"} - set(raw)
    if missing:
        raise RateTableError(f"{where}: missing fields {sorted(missing)}")
    raw.setdefault("exchange", ANY)
    raw.setdefault("note", "")
    texts = ("component", "exchange", "segment", "side", "rate", "source", "note")
    if not all(isinstance(raw[k], str) for k in texts):
        raise RateTableError(f"{where}: {', '.join(texts)} must be strings (rate keeps it exact)")
    start, end = raw["start"], raw.get("end")
    if not _is_date(start) or not (end is None or _is_date(end)):
        raise RateTableError(f"{where}: start and end must be TOML dates, not datetimes")
    try:
        component, rate = Component(raw["component"]), Decimal(raw["rate"])
    except (ValueError, InvalidOperation) as exc:
        raise RateTableError(f"{where}: {exc!r}") from exc
    if not rate.is_finite():
        raise RateTableError(f"{where}: rate must be finite")
    return Rate(
        component=component,
        exchange=raw["exchange"],
        segment=raw["segment"],
        side=raw["side"],
        rate=rate,
        start=start,
        end=end,
        source=raw["source"],
        note=raw["note"],
    )


def load_table(text: str) -> RateTable:
    """Parse and validate a rate table written in TOML."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RateTableError(str(exc)) from exc
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise RateTableError(f"schema_version must be {SCHEMA_VERSION}")
    as_of, start = doc.get("as_of"), doc.get("coverage_start")
    if not _is_date(as_of) or not _is_date(start):
        raise RateTableError("as_of and coverage_start must be TOML dates, not datetimes")
    entries = doc.get("rate", [])
    if not isinstance(entries, list):
        raise RateTableError("rates must be written as [[rate]] tables")
    rates = tuple(_parse_rate(i, raw) for i, raw in enumerate(entries))
    table = RateTable(as_of=as_of, coverage_start=start, rates=rates)
    table.validate()
    return table


@cache
def default_table() -> RateTable:
    """The bundled NSE table."""
    text = resources.files("india_costs.data").joinpath("nse.toml").read_text(encoding="utf-8")
    return load_table(text)

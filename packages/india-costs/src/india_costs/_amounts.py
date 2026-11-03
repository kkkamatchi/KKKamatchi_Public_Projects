"""Turn user-supplied amounts into exact, non-negative Decimals."""

from __future__ import annotations

import operator
from decimal import Decimal, InvalidOperation
from typing import SupportsIndex

Amount = Decimal | int | float | str | SupportsIndex


def to_decimal(value: Amount, what: str = "amount") -> Decimal:
    """Accept Decimal, int, str, float (via its shortest repr) and numpy-style scalars."""
    if isinstance(value, bool):
        raise TypeError(f"{what} must be a number, not bool")
    try:
        if isinstance(value, Decimal | int | str):
            amount = Decimal(value)
        elif isinstance(value, float):
            amount = Decimal(repr(float(value)))  # float() drops subclass reprs (np.float64)
        elif hasattr(type(value), "__index__"):
            amount = Decimal(operator.index(value))  # np.int64 and friends
        else:
            amount = Decimal(str(value))  # np.float32 prints its shortest decimal
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{what} is not a number: {value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{what} must be finite and non-negative, got {value!r}")
    return amount.copy_abs()  # turns -0 into 0

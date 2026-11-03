import pytest

from india_costs.__main__ import main


def test_prints_breakdown_and_share(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["100000", "--broker", "zerodha", "--date", "2026-11-03"])
    out = capsys.readouterr().out
    assert code == 0
    for charge in ("stt", "stamp_duty", "exchange_txn", "sebi_fee", "dp_charge", "gst"):
        assert charge in out
    assert "% of the buy value (equity_delivery, 2026-11-03, broker: zerodha)" in out


def test_rejects_unknown_segment() -> None:
    with pytest.raises(SystemExit):
        main(["100000", "--segment", "crypto"])


@pytest.mark.parametrize("args", [["abc"], ["-100"], ["nan"], ["100000", "--date", "2019-01-01"]])
def test_bad_input_exits_cleanly(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(args)
    assert exit_info.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


def test_zero_buy_value_has_no_share(capsys: pytest.CaptureFixture[str]) -> None:
    main(["0", "--sell-value", "100000", "--date", "2026-11-03"])
    assert "n/a of the buy value" in capsys.readouterr().out

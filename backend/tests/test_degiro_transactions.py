"""
Degiro transaction export parsing and position reconstruction.

Fixtures mirror the structure of a real Czech-locale export (442 rows,
2022-2026) with invented instruments and amounts. The owner's real export is
never committed.

The partial-fill cases are the important ones. A first cut of this parser
deduplicated on `ID objednávky` and would have deleted 600 real shares from a
single position, because one sell order routinely executes as several fills
that share an id and are indistinguishable at minute resolution.
"""

from datetime import datetime

import pytest

from app.services.degiro_transactions import (
    DegiroImportError,
    parse_czech_datetime,
    parse_czech_number,
    parse_transactions,
    deduplicate,
    derive_positions,
    summarize,
)

HEADER = (
    "Datum,Čas,Produkt,ISIN,Reference exchange,Venue,Počet,Cena,,"
    "Hodnota v domácí měně,,Hodnota EUR,Směnný kurz,AutoFX Fee,"
    "Transaction and/or third party fees EUR,Celkem EUR,ID objednávky"
)


def csv_of(*lines: str) -> str:
    return "\n".join([HEADER, *lines])


# Written out literally so the Czech number format is exercised end to end.
BUY_300 = (
    '21-08-2026,15:30,DATA CORP,US2376901029,NDQ,XNAS,300,"2,9600",USD,'
    '"-888,00",USD,"-760,02","1,1684","-1,90","-2,00","-763,92",ord-buy-1'
)
SELL_50 = (
    '17-08-2026,15:47,DATA CORP,US2376901029,NDQ,MSRP,-50,"7,7150",USD,'
    '"385,75",USD,"332,86","1,1589","-0,83","-2,00","330,03",ord-sell-1'
)


# ==============================================================================
# Number and date parsing — Czech locale
# ==============================================================================

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2,9600", 2.96),
        ("-888,00", -888.0),
        ("1.234,56", 1234.56),
        ("-1.234,56", -1234.56),
        ("0,1400", 0.14),
    ],
)
def test_czech_numbers(raw, expected):
    assert parse_czech_number(raw) == pytest.approx(expected)


def test_unparseable_number_is_none_not_zero():
    """A fee that failed to parse must not silently become 'no fee'."""
    assert parse_czech_number("n/a") is None
    assert parse_czech_number("") is None
    assert parse_czech_number(None) is None


def test_czech_date_with_and_without_time():
    assert parse_czech_datetime("21-08-2026", "15:30") == datetime(2026, 8, 21, 15, 30)
    assert parse_czech_datetime("21-08-2026", "") == datetime(2026, 8, 21)
    assert parse_czech_datetime("", "15:30") is None


# ==============================================================================
# Direction — the sign convention
# ==============================================================================

def test_positive_quantity_is_a_buy():
    tx = parse_transactions(csv_of(BUY_300))[0]
    assert tx.is_buy and tx.side == "BUY"
    assert tx.quantity == 300 and tx.price == pytest.approx(2.96)
    assert tx.currency == "USD"
    assert tx.local_value == pytest.approx(-888.0)   # money out


def test_negative_quantity_is_a_sell():
    tx = parse_transactions(csv_of(SELL_50))[0]
    assert not tx.is_buy and tx.side == "SELL"
    assert tx.quantity == -50
    assert tx.price == pytest.approx(7.715)          # price stays positive
    assert tx.local_value == pytest.approx(385.75)   # money in


def test_fees_are_normalised_to_a_positive_magnitude():
    tx = parse_transactions(csv_of(BUY_300))[0]
    assert tx.fees_eur == pytest.approx(3.90)        # 1.90 autoFX + 2.00 transaction


# ==============================================================================
# Partial fills — the bug that would have deleted real shares
# ==============================================================================

IDENTICAL_FILL = (
    '07-02-2023,16:09,MICRO SOFT,US8321542073,NDQ,XNAS,-100,"3,1400",USD,'
    '"314,00",USD,"290,00","1,0800","-0,50","-2,00","287,50",ord-split-1'
)


def test_seven_identical_fills_are_seven_real_trades():
    """
    A 700-share sell executed as seven 100-share fills at one price inside one
    minute. Byte-identical rows, one order id — and every one of them real.
    """
    parsed = parse_transactions(csv_of(*[IDENTICAL_FILL] * 7))
    assert len(parsed) == 7
    assert sum(t.quantity for t in parsed) == -700
    assert [t.fill_seq for t in parsed] == [1, 2, 3, 4, 5, 6, 7]


def test_deduplicate_keeps_every_fill_within_one_export():
    parsed = parse_transactions(csv_of(*[IDENTICAL_FILL] * 7))
    assert len(deduplicate(parsed)) == 7


def test_reimporting_the_same_export_is_idempotent():
    parsed = parse_transactions(csv_of(*[IDENTICAL_FILL] * 7, BUY_300))
    assert len(deduplicate(parsed + parsed)) == len(parsed)


def test_two_fills_of_one_order_at_different_prices_both_survive():
    a = ('05-08-2026,16:27,ADCORE,CA00650V1004,TSX,XTSE,-2000,"0,1400",CAD,'
         '"280,00",CAD,"254,00","1,1000","-0,50","-2,00","251,50",ord-x')
    b = ('05-08-2026,16:26,ADCORE,CA00650V1004,TSX,XTSE,-500,"0,1500",CAD,'
         '"75,00",CAD,"68,00","1,1000","-0,50","-2,00","65,50",ord-x')
    parsed = deduplicate(parse_transactions(csv_of(a, b)))
    assert len(parsed) == 2
    assert sum(t.quantity for t in parsed) == -2500


# ==============================================================================
# Position reconstruction
# ==============================================================================

def test_weighted_average_cost_is_derived_from_real_buys():
    b1 = ('01-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,100,"10,0000",USD,'
          '"-1.000,00",USD,"-900,00","1,1000","-0,50","-2,00","-902,50",o1')
    b2 = ('02-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,100,"20,0000",USD,'
          '"-2.000,00",USD,"-1.800,00","1,1000","-0,50","-2,00","-1.802,50",o2')
    pos = derive_positions(parse_transactions(csv_of(b1, b2)))["US1111111111"]
    assert pos.shares == 200
    assert pos.avg_cost == pytest.approx(15.0)


def test_realized_pl_is_computed_on_sells():
    b = ('01-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,100,"10,0000",USD,'
         '"-1.000,00",USD,"-900,00","1,1000","-0,50","-2,00","-902,50",o1')
    s = ('05-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,-40,"15,0000",USD,'
         '"600,00",USD,"545,00","1,1000","-0,50","-2,00","542,50",o2')
    pos = derive_positions(parse_transactions(csv_of(b, s)))["US1111111111"]
    assert pos.shares == 60
    assert pos.realized_pl == pytest.approx(200.0)   # (15 - 10) * 40
    assert pos.avg_cost == pytest.approx(10.0)       # selling does not move it


def test_fully_exited_position_reports_zero_shares_and_no_average():
    b = ('01-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,100,"10,0000",USD,'
         '"-1.000,00",USD,"-900,00","1,1000","-0,50","-2,00","-902,50",o1')
    s = ('05-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,-100,"12,0000",USD,'
         '"1.200,00",USD,"1.090,00","1,1000","-0,50","-2,00","1.087,50",o2')
    pos = derive_positions(parse_transactions(csv_of(b, s)))["US1111111111"]
    assert pos.shares == 0
    assert pos.is_open is False
    assert pos.avg_cost is None       # the average of zero shares is not 0.0


def test_selling_more_than_the_history_knows_is_flagged_not_absorbed():
    """
    A corporate action the export does not contain — a reverse split, a ticker
    change. The number must be flagged for the owner, never quietly fixed up.
    """
    s = ('09-08-2024,10:00,ZENT,CA0089111088,TSX,XTSE,-23,"5,0000",CAD,'
         '"115,00",CAD,"78,00","1,4700","-0,50","-2,00","75,50",o1')
    pos = derive_positions(parse_transactions(csv_of(s)))["CA0089111088"]
    assert pos.inconsistent is True
    assert pos.notes and "split" in pos.notes[0]


def test_summary_counts_open_closed_and_flagged():
    b = ('01-03-2024,10:00,ACME,US1111111111,NDQ,XNAS,100,"10,0000",USD,'
         '"-1.000,00",USD,"-900,00","1,1000","-0,50","-2,00","-902,50",o1')
    out = summarize(derive_positions(parse_transactions(csv_of(b))))
    assert out["instruments"] == 1 and out["open_positions"] == 1
    assert out["total_fees_eur"] == pytest.approx(2.50)


# ==============================================================================
# Rejecting the wrong file
# ==============================================================================

def test_positions_export_is_rejected_with_a_useful_message():
    """The owner has both exports on disk; the wrong one must say so."""
    with pytest.raises(DegiroImportError, match="export transakcí"):
        parse_transactions("Produkt,Symbol,Počet,Cena\nACME,ACM,10,5")


def test_empty_file_is_rejected():
    with pytest.raises(DegiroImportError):
        parse_transactions("")


def test_non_trade_rows_are_skipped_not_guessed():
    """Cash movements and dividends ride along in some export variants."""
    cash = ('01-03-2024,10:00,DIVIDEND,US1111111111,,,,"",USD,'
            '"12,00",USD,"11,00","1,1000","0,00","0,00","11,00",o9')
    with pytest.raises(DegiroImportError):
        parse_transactions(csv_of(cash))

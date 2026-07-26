"""
Broker CSV import honesty tests.

Degiro portfolio exports carry NO purchase price — only the closing price.
These tests lock the rule that the parser must never fabricate cost basis
from a quote: avg_cost comes back None (user fills it in), the closing price
lands in current_price, and validation keeps such rows instead of dropping
them. T212/XTB exports carry genuine costs and must keep working unchanged.
"""

from __future__ import annotations

from app.services.importer import BrokerCSVParser, validate_position_data
from app.models.portfolio import BrokerType

DEGIRO_CSV = """Produkt,Symbol/ISIN,Množství,Uzavírací,Hodnota,Hodnota v EUR
AEHR TEST SYSTEMS,AEHR | US00760J1088,12,"76,32",USD 915.84,843.21
IRIDEX CORP,IRIX | US4463651012,350,"0,89",USD 311.85,287.02
"""

T212_CSV = """Ticker,No. of shares,Average price,Currency (Average price)
AEHR,12,27.75,USD
SMSI,122.2,3.00,USD
"""


class TestDegiroParser:
    def test_degiro_avg_cost_is_none_never_closing_price(self):
        positions = BrokerCSVParser.parse_broker_csv(DEGIRO_CSV, BrokerType.DEGIRO)
        assert len(positions) == 2
        for pos in positions:
            assert pos["avg_cost"] is None, (
                "Degiro export has no purchase price — avg_cost must be None, "
                "never the closing price"
            )

    def test_degiro_closing_price_becomes_current_price(self):
        positions = BrokerCSVParser.parse_broker_csv(DEGIRO_CSV, BrokerType.DEGIRO)
        by_ticker = {p["ticker"]: p for p in positions}
        assert by_ticker["AEHR"]["current_price"] == 76.32
        assert by_ticker["IRIX"]["current_price"] == 0.89
        assert by_ticker["AEHR"]["shares_count"] == 12

    def test_validation_keeps_positions_without_cost(self):
        positions = BrokerCSVParser.parse_broker_csv(DEGIRO_CSV, BrokerType.DEGIRO)
        validated = validate_position_data(positions)
        assert len(validated) == 2
        assert all(v["avg_cost"] is None for v in validated)
        assert all(v["current_price"] is not None for v in validated)

    def test_first_position_not_eaten_as_metadata(self):
        """
        Regression: the old metadata heuristic required a cell to literally
        start with "ISIN", so a Degiro file WITHOUT a metadata line lost its
        first position. Rows carry real ISINs — both shapes must parse fully.
        """
        no_metadata = BrokerCSVParser.parse_broker_csv(DEGIRO_CSV, BrokerType.DEGIRO)
        assert [p["ticker"] for p in no_metadata] == ["AEHR", "IRIX"]

        with_metadata = (
            "Produkt,Symbol/ISIN,Množství,Uzavírací,Hodnota,Hodnota v EUR\n"
            "Portfolio,,,,,\n"  # metadata line some exports include
            + DEGIRO_CSV.split("\n", 1)[1]
        )
        parsed = BrokerCSVParser.parse_broker_csv(with_metadata, BrokerType.DEGIRO)
        assert [p["ticker"] for p in parsed] == ["AEHR", "IRIX"]


class TestT212Parser:
    def test_t212_keeps_genuine_average_price(self):
        positions = BrokerCSVParser.parse_broker_csv(T212_CSV, BrokerType.T212)
        by_ticker = {p["ticker"]: p for p in positions}
        assert by_ticker["AEHR"]["avg_cost"] == 27.75
        assert by_ticker["SMSI"]["avg_cost"] == 3.00

    def test_t212_survives_validation_with_cost(self):
        validated = validate_position_data(
            BrokerCSVParser.parse_broker_csv(T212_CSV, BrokerType.T212)
        )
        assert len(validated) == 2
        assert all(v["avg_cost"] is not None for v in validated)


class TestValidation:
    def test_nonpositive_present_cost_is_dropped(self):
        """A present-but-zero cost is corrupt data, not 'unknown'."""
        validated = validate_position_data(
            [{"ticker": "X", "shares_count": 10, "avg_cost": 0.0}]
        )
        assert validated == []

    def test_missing_cost_is_kept(self):
        validated = validate_position_data(
            [{"ticker": "X", "shares_count": 10, "avg_cost": None,
              "current_price": 5.0}]
        )
        assert len(validated) == 1
        assert validated[0]["avg_cost"] is None

    def test_nonpositive_shares_dropped(self):
        validated = validate_position_data(
            [{"ticker": "X", "shares_count": 0, "avg_cost": None}]
        )
        assert validated == []

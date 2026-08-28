"""
Every column of `stocks` must survive `StockResponse`.

Why this test exists
--------------------
On 2026-08-23 the whole app went blind. The sidebar said "Sledované 0", all
twelve positions showed "bez konvikčního skóre", and every stock detail said
"Chybí data akcie" — while the database held twelve scored rows the entire
time.

The cause was one annotation. `Stock.catalyst_date` is a DATE column;
`StockResponse.catalyst_date` was typed `str | None`. That mismatch is
invisible for as long as every row is NULL, so it sat there for months. The
first row to get a real date made `StockResponse.model_validate` raise, the
route turned the exception into a 500, the frontend caught the failure and
left its stock list empty — and an empty list reads, in every widget
downstream, as "there is no analysis".

That is the app's recurring defect wearing a new coat: an absence manufactured
out of nothing, then stated as fact. A test for `catalyst_date` alone would
only close this one instance, so the test below walks EVERY column and feeds
each one a value of its own declared type. The next `Date`, `Float` or
`Boolean` column added to the model cannot repeat this quietly.
"""

from datetime import date, datetime

import pytest
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String, Text

import app.models  # noqa: F401  — SQLAlchemy needs every mapper
import app.models.trading  # noqa: F401
from app.models.stock import Stock
from app.schemas.responses import StockResponse

#: One representative value per SQLAlchemy type. Deliberately NOT None — the
#: bug this file guards against only appears once a column stops being NULL.
SAMPLE_BY_TYPE = [
    (Boolean, True),
    (Date, date(2026, 6, 30)),
    (DateTime, datetime(2026, 6, 30, 12, 0)),
    (Integer, 1),
    (Numeric, 1.5),
    (Float, 1.5),
    (String, "x"),
    (Text, "x"),
]


def _sample_for(column) -> object:
    # Order matters: Boolean and Date subclass more general types in SQLAlchemy,
    # so the most specific match has to be tried first.
    for type_, value in SAMPLE_BY_TYPE:
        if isinstance(column.type, type_):
            return value
    pytest.fail(
        f"Sloupec {column.name} má typ {type(column.type).__name__}, "
        "pro který tenhle test nezná vzorovou hodnotu. Doplň ho do "
        "SAMPLE_BY_TYPE, jinak by prošel bez kontroly."
    )


def _minimal_stock(**overrides) -> Stock:
    """A row with only the columns StockResponse insists on, plus overrides."""
    return Stock(id=1, created_at=datetime(2026, 8, 23, 10, 0), **overrides)


def _fully_populated_stock() -> Stock:
    stock = Stock()
    for column in Stock.__table__.columns:
        setattr(stock, column.name, _sample_for(column))
    return stock


def test_every_column_survives_the_response_schema():
    """
    A row with every column filled must serialize.

    This is the whole guard. If it fails, some column's Python type disagrees
    with its annotation in StockResponse, and GET /api/stocks will answer 500
    the moment a real row carries that value.
    """
    StockResponse.model_validate(_fully_populated_stock())


def test_catalyst_date_stays_a_date():
    """
    The specific regression: a DATE column typed as `str` in the schema.

    Kept alongside the sweep above because it names the failure that actually
    happened, and because the JSON shape matters to the frontend, which types
    the field as a string.
    """
    stock = _minimal_stock(ticker="KUYA.V", catalyst_date=date(2026, 6, 30))

    response = StockResponse.model_validate(stock)

    assert response.catalyst_date == date(2026, 6, 30)
    # The wire format the frontend reads is unchanged by the fix.
    assert response.model_dump(mode="json")["catalyst_date"] == "2026-06-30"


def test_a_null_catalyst_date_is_still_null():
    """An empty date must not become today, or an empty string."""
    response = StockResponse.model_validate(_minimal_stock(ticker="AEHR"))
    assert response.catalyst_date is None

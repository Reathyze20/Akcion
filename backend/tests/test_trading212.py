"""
Trading 212 client — the parts that hold without a network.

The live API needs a key, so the shape-dependent reads are exercised against
the real service once one exists. What is pinned here is everything that must
be true regardless: symbol normalisation, the refusal to construct without a
key, and the absence of any order-placing capability.
"""

import ast
import inspect

import pytest

from app.services import trading212
from app.services.trading212 import (
    T212Instrument,
    T212Position,
    Trading212AuthError,
    Trading212Client,
)


# ==============================================================================
# The guarantee the owner asked for
# ==============================================================================

def test_module_cannot_issue_a_write_request():
    """
    Trading 212 exposes POST equity/orders, which spends real money. The owner
    was explicit: the app advises, he executes. Rather than trusting prose,
    this asserts the module contains no write verb at all — checked on the
    parsed syntax tree, so a mention inside a docstring does not count.
    """
    tree = ast.parse(inspect.getsource(trading212))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called & {"post", "put", "patch", "delete"}, sorted(called)


def test_no_public_method_is_named_like_a_trade():
    public = [n for n in dir(Trading212Client) if not n.startswith("_")]
    forbidden = {"place_order", "buy", "sell", "create_order", "submit_order"}
    assert forbidden.isdisjoint(public)


def test_every_public_method_is_a_read():
    public = [n for n in dir(Trading212Client) if not n.startswith("_")]
    assert all(n.startswith(("get_", "build_")) for n in public), public


# ==============================================================================
# Construction
# ==============================================================================

@pytest.mark.parametrize("bad", ["", "   ", None])
def test_missing_key_fails_loudly_at_construction(bad):
    """Failing at construction beats failing on the first read at 6am."""
    with pytest.raises(Trading212AuthError, match="T212_API_KEY"):
        Trading212Client(bad)  # type: ignore[arg-type]


def test_key_is_trimmed():
    client = Trading212Client("  abc123  ")
    assert client._key == "abc123"


# ==============================================================================
# Symbol normalisation
# ==============================================================================

@pytest.mark.parametrize(
    "t212_symbol,expected",
    [
        ("ECOR_US_EQ", "ECOR"),
        ("INMB_US_EQ", "INMB"),
        ("ALAR_US_EQ", "ALAR"),
        ("VTSI_US_EQ", "VTSI"),
        ("AAPL", "AAPL"),
    ],
)
def test_t212_symbols_reduce_to_the_bare_ticker(t212_symbol, expected):
    """
    T212 suffixes symbols with market and instrument type. The Gomes tracker
    and the Breakout watchlist both use the bare symbol, so positions cannot
    be matched across sources without this.
    """
    pos = T212Position(
        ticker=t212_symbol, quantity=1.0, average_price=1.0,
        current_price=None, ppl=None,
    )
    assert pos.plain_ticker == expected


def test_instruments_normalise_the_same_way():
    inst = T212Instrument(
        ticker="ECOR_US_EQ", isin="US28531P2020", name="electroCore",
        currency="USD", type_="STOCK",
    )
    assert inst.plain_ticker == "ECOR"


# ==============================================================================
# Fractional shares
# ==============================================================================

def test_fractional_quantities_survive_unrounded():
    """
    A real T212 holding is 114.96302143 shares. Rounding it anywhere turns a
    correct position into a wrong one.
    """
    pos = T212Position(
        ticker="ECOR_US_EQ", quantity=114.96302143, average_price=11.77,
        current_price=10.52, ppl=None,
    )
    assert pos.quantity == 114.96302143

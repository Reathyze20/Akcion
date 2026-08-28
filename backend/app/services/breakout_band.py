"""
Breakout Investors as a second valuation, and the limits of what they publish.

The decision this implements
----------------------------
Breakout sits at the same level as Gomes — **equal in the right to prevent, not
in the right to allow**. Either of them saying no stops a purchase; neither of
them alone can authorise one, because a purchase needs a real valuation band and
a Buy Guard that passes on it.

`evaluate_dual_source_buy` has implemented that since it was written and has
never received a single Breakout row: on 2026-08-24 not one company in `stocks`
carries `source_key = BREAKOUT_INVESTORS`. The veto the owner asked for has been
dead code. This module is the missing feed.

Two things they publish, and only one of them is an opinion
-----------------------------------------------------------
Their API returns six fields — symbol, company name, endorsement count, an
`upside` ratio, a read price and a timestamp. No author, no verdict, no text.

That makes the watchlist a **valuation input and never a stance**. Writing all
28 names down as bullish would silently double the permitted size of 28
positions on the strength of a list nobody read and nobody signed. A stance
exists only where a named analyst from `analyst_roster` actually wrote
something — a person putting their name to a view is a different object from a
row in a feed.

Where their band comes from, and when there isn't one
-----------------------------------------------------
* **Their red line** is the target. A target an analyst wrote in their own words
  beats one derived from `upside`, and when both exist and differ that is a
  disagreement *inside* one source, shown as such — otherwise Breakout votes
  twice.
* **Their green line** is the price an analyst named as a buy, or failing that
  the price when we watched them *add* the name. The second only exists for
  names first seen after the poller started on 2026-08-23; for the 28 already on
  the list when it began there is no green line and there never will be.

With both, a real logarithmic R/R score on their band by the same formula as
Gomes. With only a target, **no band at all** — just the upside and a comparison
against Gomes' red line. The gap is not filled in: inventing a green line to
complete a band would manufacture the one number the whole method rests on.
"""

from __future__ import annotations

from app.core.czech import n as cz

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Final

from app.core.sources import verdict_stance

#: Below this many endorsements the name is one person's idea rather than the
#: community's. It still shows; it just says so.
THIN_ENDORSEMENT_COUNT: Final[int] = 3

#: A written target this far from the derived one is worth naming rather than
#: quietly preferring one. A ratio, not a percentage: 0.25 = a quarter apart.
TARGET_DISAGREEMENT_RATIO: Final[float] = 0.25


@dataclass(frozen=True)
class WatchlistRow:
    """What their feed publishes, unchanged."""

    symbol: str
    company_name: str | None = None
    endorsements: int = 0
    upside_ratio: float | None = None
    price_at_read: float | None = None
    implied_target: float | None = None
    #: When their list first showed this name to us — not when they added it.
    first_seen_at: datetime | None = None
    #: Their own date, which predates our polling and cannot anchor a price.
    added_at: datetime | None = None
    #: True once we have watched this name appear, so `price_at_read` is the
    #: price at the moment of the addition rather than at an arbitrary poll.
    seen_added: bool = False


@dataclass(frozen=True)
class AnalystWord:
    """Something a named analyst actually wrote."""

    analyst: str
    said_on: date
    #: A price they named as a target, in their own words.
    target: float | None = None
    #: A price they named as a buy level.
    buy_at: float | None = None
    #: BUY / SELL / TRIM / … as recorded on the claim, or None for a note that
    #: carried facts and no instruction — which is the common case.
    verdict: str | None = None


@dataclass
class BreakoutView:
    """Their side of one company, with everything they cannot say left empty."""

    ticker: str
    green_line: float | None = None
    red_line: float | None = None
    #: BUY / SELL / … only ever from a named analyst, never from a feed row.
    action_verdict: str | None = None
    #: Who and when, for anything that came from a person.
    attributed_to: str | None = None
    said_on: date | None = None
    endorsements: int = 0
    upside_ratio: float | None = None
    notes_cs: list[str] = field(default_factory=list)

    @property
    def has_band(self) -> bool:
        return (
            self.green_line is not None
            and self.red_line is not None
            and self.red_line > self.green_line
        )

    @property
    def target_only(self) -> bool:
        """A ceiling with no floor. Real, and not a band."""
        return self.red_line is not None and not self.has_band

    @property
    def verdict_is_bearish(self) -> bool:
        """
        A named analyst saying no. This is the half of the equality the owner
        asked for that actually bites: either source may prevent a purchase.
        """
        return verdict_stance(self.action_verdict) == "BEARISH"

    @property
    def verdict_is_bullish(self) -> bool:
        """
        A named analyst saying yes — which raises the cap and never authorises
        anything on its own. A purchase still needs a Gomes band and a Buy Guard
        that passes on it.
        """
        return verdict_stance(self.action_verdict) == "BULLISH"


def build_view(
    row: WatchlistRow | None,
    words: list[AnalystWord] | None = None,
) -> BreakoutView | None:
    """
    Assemble Breakout's position on one company, or None when they have none.

    The order of precedence is the whole point: a person's written number beats
    a number derived from a ratio, and a person's verdict is the only thing that
    becomes a verdict at all.
    """
    words = sorted(words or [], key=lambda w: w.said_on, reverse=True)
    if row is None and not words:
        return None
    if row is None:
        return None  # an analyst note about a name they do not track: no view

    notes: list[str] = []
    view = BreakoutView(
        ticker=row.symbol,
        endorsements=row.endorsements,
        upside_ratio=row.upside_ratio,
    )

    written_target = next((w.target for w in words if w.target is not None), None)
    derived_target = row.implied_target

    # --- the red line -------------------------------------------------------
    if written_target is not None:
        author = next(w for w in words if w.target is not None)
        view.red_line = written_target
        view.attributed_to = author.analyst
        view.said_on = author.said_on

        if derived_target and derived_target > 0:
            apart = abs(written_target - derived_target) / derived_target
            if apart >= TARGET_DISAGREEMENT_RATIO:
                notes.append(
                    f"Breakout si sám odporuje: {author.analyst} napsal cíl "
                    f"{cz(written_target, 2)}, ze staženého seznamu vychází "
                    f"{cz(derived_target, 2)}. Platí napsaný — je pod ním podpis."
                )
    elif derived_target is not None:
        view.red_line = derived_target

    # --- the green line -----------------------------------------------------
    buy_at = next((w.buy_at for w in words if w.buy_at is not None), None)
    if buy_at is not None:
        view.green_line = buy_at
        if view.attributed_to is None:
            author = next(w for w in words if w.buy_at is not None)
            view.attributed_to = author.analyst
            view.said_on = author.said_on
    elif row.seen_added and row.price_at_read:
        view.green_line = row.price_at_read

    # --- the verdict, which only a person can give --------------------------
    spoken = next((w for w in words if w.verdict), None)
    if spoken is not None:
        view.action_verdict = spoken.verdict.strip().upper()
        view.attributed_to = view.attributed_to or spoken.analyst
        view.said_on = view.said_on or spoken.said_on

    # --- what has to be said out loud ---------------------------------------
    if view.target_only:
        notes.append(
            f"Breakout má u {row.symbol} jen cíl {cz(view.red_line, 2)}, ne spodní "
            f"hranici — pásmo z toho nedělám. Chybí cena, za kterou by nákup "
            f"doporučili."
        )
    if 0 < row.endorsements < THIN_ENDORSEMENT_COUNT:
        who = "člen" if row.endorsements == 1 else "členové"
        notes.append(
            f"Za {row.symbol} se u Breakoutu postavili jen {row.endorsements} "
            f"{who} — je to nápad, ne stanovisko skupiny."
        )
    if view.action_verdict is None:
        notes.append(
            f"Z Breakoutu u {row.symbol} nemám žádný výrok — stažený seznam "
            f"nikdo nepodepsal, takže z něj nákup ani zákaz nedělám."
        )

    view.notes_cs = notes
    return view


#: The currency every Breakout target is quoted in. Their list carries the US
#: symbol, so the number is dollars — which is not the currency four of the
#: twelve holdings trade in.
TARGET_CURRENCY: Final[str] = "USD"


def headroom_to_target(
    view: BreakoutView | None,
    price: float | None,
    price_currency: str | None,
    convert: Callable[[float, str, str], float | None],
) -> tuple[float | None, str | None]:
    """
    How far today's price sits below their target, as a percentage.

    Returns `(headroom_pct, warning_cs)`. Both may be None; a warning without a
    number is the honest answer when the two cannot be compared.

    The conversion is not optional bookkeeping
    ------------------------------------------
    Their targets quote the US listing in dollars. `DBO.TO` and `GSI.V` trade
    in Canadian dollars and `IMP.V` and `KUYA.V` are held in euros — four of the
    twelve holdings, and the four largest among the unvalued ones. Comparing
    those prices to a dollar target directly is wrong by the whole exchange
    rate, which is precisely the defect that produced a wrong TRIM on GSI.V at
    an R/R of 2.97 when the real figure was 4.23.

    With no rate available the answer is no number and a named gap, never a
    number in the wrong money.
    """
    if view is None or view.red_line is None or not price or price <= 0:
        return None, None

    here = price
    if price_currency and price_currency.upper() != TARGET_CURRENCY:
        here = convert(price, price_currency, TARGET_CURRENCY)
        if here is None:
            return None, (
                f"{view.ticker}: cíl Breakoutu je v {TARGET_CURRENCY}, cena v "
                f"{price_currency.upper()} a kurz nemám — nesrovnávám je, "
                f"protože rozdíl by byl o celý kurz."
            )

    return (view.red_line / here - 1.0) * 100.0, None


def compare_to_gomes(
    view: BreakoutView | None,
    gomes_red: float | None,
) -> str | None:
    """
    Name the disagreement between the two targets. Never average them.

    The average of two targets nobody holds is a number neither source would
    defend, and it is the shape of answer that makes a wrong position feel
    researched.
    """
    if view is None or view.red_line is None or not gomes_red:
        return None

    if view.red_line < gomes_red:
        return (
            f"Breakout čeká míň než Gomes — jejich cíl {cz(view.red_line, 2)} leží "
            f"POD jeho červenou čárou {cz(gomes_red, 2)}."
        )
    if view.red_line > gomes_red:
        return (
            f"Breakout čeká víc než Gomes — jejich cíl {cz(view.red_line, 2)} leží "
            f"NAD jeho červenou čárou {cz(gomes_red, 2)}. Nákup dál hradí Gomesovo "
            f"pásmo."
        )
    return None

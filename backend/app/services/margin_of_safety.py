"""
How far the price can fall before something real stops it.

The question the app could not answer
--------------------------------------
Everything else here measures upside: the R/R score counts the distance to the
Red Line, Breakout publishes an `upside` ratio, the band says how cheap a stock
is for its quality. Not one of them says **how much can be lost**.

The Five Keys framework (J. Dennis Jean-Jacques, summarised in the note Gomes
recommended) makes that the fifth and last question before buying, and puts it
deliberately the other way round from a discount-to-fair-value:

    "FKV's margin of safety is heavily conscious of what can go wrong, and not
     what the discount it is to fair value — the safety is thus purely based on
     the value of the assets."

Its worked example is the shape this module produces: at 15 USD the support
level was 12,50 — 9,50 in asset value and 2,50 in cash — so 100 % of upside
against 17 % of downside.

Tangible only, and why that is not pessimism
--------------------------------------------
Goodwill and intangibles are the first entries written down when a thesis
breaks, so a floor that counts them is not a floor. The book says as much and
then says the opposite too: only counting tangibles *understates* the business,
because culture, customers and reputation are real and unbookable.

Both are true, and the resolution is that this is not a valuation. It is the
answer to "why shouldn't it fall from here", and that answer has to be made of
things a liquidator could sell.

What it must never become
-------------------------
**A sixth gate.** A purchase already passes the Gomes band, the cylinder count,
the Buy Guard, the tier cap, the source matrix, pacing and concentration. This
is a different method's question, and wiring a different method's veto into the
buy path is exactly how the app ended up with six answers to one question. It
informs and it warns; it never authorises and never blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from app.core.czech import n as cz

#: Which floor was computable, in descending order of how much it is worth.
LAYER_TANGIBLE: Final[str] = "TANGIBLE_BOOK"
LAYER_NET_CASH: Final[str] = "NET_CASH"
LAYER_NONE: Final[str] = "NONE"

#: Below this much support under the price, there is effectively nothing
#: holding the stock up — whatever the story is. Not a sell signal: a company
#: can be worth many times its liquidation value. It is a statement about what
#: happens if the story stops working.
THIN_SUPPORT_PCT: Final[float] = 15.0

#: "Having too much debt is a red flag." Debt above this multiple of cash means
#: the floor is somebody else's before it is the shareholder's.
DEBT_TO_CASH_RED_FLAG: Final[float] = 2.0

#: Upside worth this many times the downside is the asymmetry the framework is
#: looking for — its own example ran at roughly six.
GOOD_ASYMMETRY: Final[float] = 3.0

#: Past this, the ratio has stopped describing a trade and started describing a
#: doubtful input. IMP.V reads at 17: a Red Line of 10,00 USD against a price
#: near 0,75 is a thirteen-bagger, and a thirteen-bagger is an extraordinary
#: claim about the ceiling rather than an extraordinary opportunity. Said out
#: loud instead of celebrated, because the number is real and its meaning is not.
IMPLAUSIBLE_ASYMMETRY: Final[float] = 8.0


@dataclass(frozen=True)
class Balance:
    """The balance-sheet lines this needs, as filed."""

    cash: float | None = None
    total_debt: float | None = None
    equity: float | None = None
    goodwill: float | None = None
    intangibles: float | None = None
    shares: float | None = None
    #: Currency the filing reports in, which need not be the trading currency.
    currency: str | None = None


@dataclass
class Support:
    """What is under the price, and how much of it there is."""

    floor_per_share: float | None = None
    net_cash_per_share: float | None = None
    tangible_book_per_share: float | None = None
    layer: str = LAYER_NONE
    #: Named gaps. An absent floor is not a floor of zero.
    unknowns: list[str] = None  # type: ignore[assignment]
    debt_heavy: bool = False

    def __post_init__(self) -> None:
        if self.unknowns is None:
            self.unknowns = []

    @property
    def known(self) -> bool:
        return self.floor_per_share is not None and self.floor_per_share > 0


def support_level(balance: Balance) -> Support:
    """
    The per-share floor, built from what a liquidator could actually sell.

    Two layers, and the weaker one is used only when the stronger cannot be
    computed — with the layer named either way, because "supported at 1,14" and
    "supported at 1,14, and that is cash alone" are different claims.
    """
    support = Support()

    if not balance.shares or balance.shares <= 0:
        support.unknowns.append("počet akcií neznám, takže na akcii nic nepřepočítám")
        return support

    cash = balance.cash
    debt = balance.total_debt or 0.0

    if cash is not None:
        support.net_cash_per_share = (cash - debt) / balance.shares
        if cash > 0 and debt > cash * DEBT_TO_CASH_RED_FLAG:
            support.debt_heavy = True
    else:
        support.unknowns.append("hotovost z výkazu neznám")

    if balance.equity is not None:
        tangible = (
            balance.equity - (balance.goodwill or 0.0) - (balance.intangibles or 0.0)
        )
        support.tangible_book_per_share = tangible / balance.shares
    else:
        support.unknowns.append("vlastní kapitál z výkazu neznám")

    # Tangible book already contains the cash, so the two are not added — the
    # book's own example splits them for explanation, not for arithmetic.
    if support.tangible_book_per_share is not None:
        support.floor_per_share = support.tangible_book_per_share
        support.layer = LAYER_TANGIBLE
    elif support.net_cash_per_share is not None:
        support.floor_per_share = support.net_cash_per_share
        support.layer = LAYER_NET_CASH
        support.unknowns.append(
            "podlahu počítám jen z čisté hotovosti — hmotná aktiva z výkazu nemám"
        )

    return support


@dataclass
class Reading:
    """The asymmetry: what there is to gain against what there is to lose."""

    ticker: str
    price: float | None = None
    support: Support | None = None
    #: Percent the price would have to fall to reach the floor. None when there
    #: is no floor — which is not the same as no downside.
    downside_pct: float | None = None
    #: Percent to the valuation ceiling, when one exists.
    upside_pct: float | None = None

    @property
    def asymmetry(self) -> float | None:
        """Upside divided by downside. None when either half is missing."""
        if not self.upside_pct or not self.downside_pct:
            return None
        if self.downside_pct <= 0:
            return None
        return self.upside_pct / self.downside_pct

    @property
    def below_its_floor(self) -> bool:
        """Trading under what a liquidator could realise. Rare and loud."""
        return self.downside_pct is not None and self.downside_pct < 0

    def notes_cs(self) -> list[str]:
        """Everything worth saying, most important first."""
        out: list[str] = []
        support = self.support

        if support is None or not support.known:
            gaps = "; ".join(support.unknowns) if support and support.unknowns else "chybí rozvaha"
            out.append(
                f"Ochrannou rezervu nespočítám ({gaps}) — neznamená to, že tam "
                f"žádná není, ale spolehnout se na ni nemůžeš"
            )
            return out

        floor = support.floor_per_share or 0.0
        layer_cs = (
            "z hmotných aktiv" if support.layer == LAYER_TANGIBLE
            else "jen z čisté hotovosti"
        )

        if self.below_its_floor:
            out.append(
                f"Obchoduje se POD svou podlahou {cz(floor, 2)} {layer_cs} — trh "
                f"počítá s tím, že se ta aktiva rozpustí. Buď je to příležitost, "
                f"nebo o firmě něco ví; z rozvahy to nepoznám"
            )
        elif self.downside_pct is not None and self.downside_pct < THIN_SUPPORT_PCT:
            out.append(
                f"Podlaha {cz(floor, 2)} {layer_cs} je jen {cz(self.downside_pct, 0)} % "
                f"pod cenou — dolů je blízko"
            )
        elif self.downside_pct is not None:
            out.append(
                f"Pod cenou je {cz(self.downside_pct, 0)} % k podlaze "
                f"{cz(floor, 2)} {layer_cs}"
            )

        ratio = self.asymmetry
        if ratio is not None:
            if ratio >= IMPLAUSIBLE_ASYMMETRY:
                verdict = (
                    "takový poměr obvykle neznamená výjimečnou příležitost, ale "
                    "nespolehlivý strop — ověř tu cílovou cenu, než se na ni "
                    "spolehneš"
                )
            elif ratio >= GOOD_ASYMMETRY:
                verdict = "nahoru je toho víc než dolů"
            else:
                verdict = "nahoru toho není o moc víc než dolů"
            out.append(
                f"Nahoru {cz(self.upside_pct or 0, 0)} %, dolů "
                f"{cz(self.downside_pct or 0, 0)} % — poměr {cz(ratio, 1)}, {verdict}"
            )

        if support.debt_heavy:
            out.append(
                "Dluh je násobkem hotovosti — na tu podlahu má někdo nárok dřív "
                "než ty"
            )

        for gap in support.unknowns:
            out.append(f"Co do podlahy nevidím: {gap}")

        return out


def read(
    ticker: str,
    price: float | None,
    balance: Balance,
    *,
    ceiling: float | None = None,
) -> Reading:
    """
    Assemble the downside picture for one company.

    `ceiling` is the valuation top — Gomes' Red Line — used only to state the
    asymmetry. It is never recomputed here: this module answers the downside
    question and takes the upside as given, so the two cannot drift apart.
    """
    support = support_level(balance)
    reading = Reading(ticker=ticker, price=price, support=support)

    if not price or price <= 0 or not support.known:
        return reading

    floor = support.floor_per_share or 0.0
    reading.downside_pct = (price - floor) / price * 100.0

    if ceiling and ceiling > price:
        reading.upside_pct = (ceiling - price) / price * 100.0

    return reading

"""
Nákupní brána česky.

`GomesGatekeeper.check_buy_guard` vrací kód a k němu větu — jenže ta věta je
u většiny bran anglická a vypisuje syrové hodnoty z databáze: *„Market Alert is
YELLOW (BUY requires GREEN)"*, *„Cylinders unknown or zero"*, *„Score 4.2 <=
Deserved 5.0"*. Česky jsou dnes jen dvě věty o přechodném útlumu.

Podle briefu na front-end (a podle zdravého rozumu) `GREEN`/`YELLOW`/`ORANGE`/
`RED` nesmí nikdy stát ve větě, kterou čte člověk. Tenhle modul je proto jediné
místo, kde se z kódu brány dělá česká věta — jedno místo pravdy vedle enumu,
ne kopie v TypeScriptu, kde by se rozešla.

Využitelné i mimo Nálezy: `refused_buys.failed_gate` ukládá tytéž kódy a dodnes
je nemá jak vypsat.
"""

from __future__ import annotations

from typing import Final

from app.core.czech import n as cz_num
from app.services.market_gauge import alert_cs
from app.trading.gomes_logic import GomesGatekeeper

BuyGate = GomesGatekeeper.BuyGate

#: Věta pro každý kód, když se nedá nic upřesnit. Klíčem je hodnota enumu,
#: aby nový kód brány padl na `KeyError` v testu, ne tiše na obrazovce.
_PLAIN: Final[dict[str, str]] = {
    BuyGate.PASSED.value: "Všechny podmínky metodiky pro nákup jsou splněné.",
    BuyGate.ALERT_UNKNOWN.value: (
        "Stupeň semaforu není zadaný, takže se nedá říct, jestli se vůbec smí "
        "nakupovat. Nákup se nepouští, dokud to někdo neurčí."
    ),
    BuyGate.MARKET_NOT_GREEN.value: (
        "Semafor není na zelené, a metodika nakupuje jen v zelené."
    ),
    BuyGate.CYLINDERS_UNKNOWN.value: (
        "Válce (0–10) nikdo nepotvrdil, takže kvalita firmy je neověřená. "
        "Bez nich se nedá spočítat, jak levná by musela být, aby stála za nákup."
    ),
    BuyGate.WAIT_TIME.value: (
        "Firma je ve fázi čekání — cena se dlouho nikam nehne a kapitál by "
        "ležel ladem."
    ),
    BuyGate.ROUGH_PATCH_STALE_QUALITY.value: (
        "Firma prochází přechodným útlumem, který je novější než posudek jejích "
        "válců. Kvalitu je potřeba posoudit znovu, než se přikoupí."
    ),
    BuyGate.SCORE_MISSING.value: (
        "Chybí R/R skóre nebo zasloužené skóre, takže není co s čím porovnat."
    ),
    BuyGate.NOT_CHEAP_ENOUGH.value: (
        "Papír není dost levný vzhledem ke kvalitě firmy."
    ),
    BuyGate.EARNINGS_SOON.value: (
        "Výsledky jsou na spadnutí. Metodika do nich nevstupuje a drží se "
        "stranou čtrnáct dní předem."
    ),
    BuyGate.SOURCE_CONFLICT.value: (
        "Zdroje si o téhle firmě odporují. Rozpor se neřeší průměrem — dokud "
        "trvá, nákup se nepouští."
    ),
}


def gate_cs(
    gate: "BuyGate | str | None",
    *,
    market_alert: str | None = None,
    rr_score: float | None = None,
    deserved: float | None = None,
    days_to_earnings: int | None = None,
) -> str:
    """
    Česká věta k jednomu výsledku nákupní brány.

    Kontext se doplní jen tam, kde upřesňuje: který stupeň semaforu svítí,
    o kolik je papír drahý, za kolik dní jsou výsledky. Bez kontextu se vrací
    obecná věta — nikdy ne prázdný řetězec a nikdy ne syrový kód.
    """
    if gate is None:
        return (
            "Nákupní bránu se nepodařilo vyhodnotit. To není souhlas ani "
            "zamítnutí — je to chybějící odpověď."
        )

    code = getattr(gate, "value", gate)
    base = _PLAIN.get(code)
    if base is None:
        # Nový kód brány, který sem nikdo nedopsal. Radši to přiznat než
        # vypsat konstantu z databáze a tvářit se, že je to věta.
        return (
            f"Nákupní brána nepustila nákup s kódem {code}, ke kterému zatím "
            f"nemáme vysvětlení."
        )

    if code == BuyGate.MARKET_NOT_GREEN.value and market_alert:
        return (
            f"Semafor je {alert_cs(market_alert)}, a metodika nakupuje jen "
            f"v zelené."
        )

    if (
        code == BuyGate.NOT_CHEAP_ENOUGH.value
        and rr_score is not None
        and deserved is not None
    ):
        return (
            f"Papír není dost levný vzhledem ke kvalitě firmy: R/R skóre "
            f"{cz_num(rr_score, 2)} proti zaslouženému {cz_num(deserved, 1)}."
        )

    if code == BuyGate.EARNINGS_SOON.value and days_to_earnings is not None:
        return (
            f"Výsledky jsou za {days_to_earnings} dní. Metodika do nich "
            f"nevstupuje a drží se stranou čtrnáct dní předem."
        )

    return base

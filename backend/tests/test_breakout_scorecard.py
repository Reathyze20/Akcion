"""
Vysvědčení cílů Breakout Investors — a hlavně to, kdy se ještě nevydává.

Celá tahle rubrika existuje kvůli jedné otázce: zaslouží si jejich hlas váhu?
Dnes žádnou nemá, protože anonymní počet podpisů není stanovisko. Jejich cíl je
ale padatelná předpověď s datem, takže za rok se to dá rozhodnout podloženě.

Riziko je, že se to rozhodne dřív. Podíl spočítaný po týdnu měří náladu trhu a
čte se jako výsledek — a jakmile jednou padne číslo „úspěšnost 40 %", nikdo se
už nezeptá, z jak dlouhé doby. Většina testů níž hlídá právě tenhle práh.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.services import breakout_scorecard as bs

TODAY = date(2026, 8, 25)


def reading(
    symbol="ABCD",
    *,
    days_ago: int | None = 10,
    price_then: float | None = 4.0,
    target_then: float | None = 6.0,
    price_now: float | None = 5.0,
) -> bs.Reading:
    first_seen = None
    if days_ago is not None:
        first_seen = datetime(2026, 8, 25, tzinfo=timezone.utc) - timedelta(days=days_ago)
    return bs.Reading(
        symbol=symbol,
        first_seen_at=first_seen,
        price_at_first_seen=price_then,
        target_at_first_seen=target_then,
        price_now=price_now,
    )


# ==============================================================================
# Práh: pod ním se úspěšnost nevydá vůbec
# ==============================================================================

class TestItRefusesToGradeTooEarly:
    def test_a_fresh_list_returns_no_hit_rate_at_all(self):
        card = bs.build([reading(days_ago=2)], today=TODAY)
        assert card.too_early is True
        assert card.reached_total is None

    def test_it_says_how_long_it_has_been_watching_and_how_long_is_left(self):
        card = bs.build([reading(days_ago=2)], today=TODAY)
        assert "2 dny" in card.verdict_cs
        assert str(bs.MIN_HORIZON_DAYS) in card.verdict_cs
        assert "jen průběh, ne známka" in card.verdict_cs

    def test_it_still_shows_the_individual_rows(self):
        """Průběh je užitečný. Známka je to, co se nesmí vydat brzy."""
        card = bs.build([reading(days_ago=2)], today=TODAY)
        assert len(card.names) == 1
        assert card.names[0].progress_pct == 50.0

    def test_past_the_horizon_it_finally_grades(self):
        card = bs.build(
            [
                reading("A", days_ago=400, price_now=6.5),   # cíl 6,0 → dosažen
                reading("B", days_ago=400, price_now=4.5),   # nedosažen
            ],
            today=TODAY,
        )
        assert card.too_early is False
        assert card.measurable == 2
        assert card.reached_total == 1
        assert "50 %" in card.verdict_cs

    def test_the_horizon_is_measured_on_the_median_not_the_oldest(self):
        """Jedno staré jméno nesmí odemknout známku pro dvacet čerstvých."""
        card = bs.build(
            [reading("STARY", days_ago=900)] + [
                reading(f"NOVY{i}", days_ago=5) for i in range(5)
            ],
            today=TODAY,
        )
        assert card.too_early is True


# ==============================================================================
# Chybějící vstup není nesplněný cíl
# ==============================================================================

class TestMissingInputsAreNotFailures:
    def test_a_name_without_a_starting_price_is_left_out_entirely(self):
        card = bs.build([reading(price_then=None)], today=TODAY)
        assert card.names == ()
        assert "není co měřit" in card.verdict_cs

    def test_a_name_without_a_first_seen_date_is_left_out(self):
        assert bs.build([reading(days_ago=None)], today=TODAY).names == ()

    def test_a_name_without_todays_price_is_kept_but_not_counted(self):
        """
        Nevědět, kde akcie dnes stojí, není nesplněný cíl — a kdyby se počítalo
        do jmenovatele, každý nedostupný kurz by jim srazil úspěšnost.
        """
        card = bs.build(
            [
                reading("MA", days_ago=400, price_now=6.5),
                reading("NEMA", days_ago=400, price_now=None),
            ],
            today=TODAY,
        )
        assert len(card.names) == 2
        assert card.measurable == 1
        assert card.reached_total == 1

    def test_an_empty_input_says_so_instead_of_reporting_zero_percent(self):
        card = bs.build([], today=TODAY)
        assert card.reached_total is None
        assert card.median_days is None


# ==============================================================================
# Aritmetika jednoho jména
# ==============================================================================

class TestOneName:
    def test_progress_is_the_share_of_the_road_travelled(self):
        n = bs.build([reading(price_then=4.0, target_then=6.0, price_now=5.0)],
                     today=TODAY).names[0]
        assert n.progress_pct == 50.0
        assert n.move_pct == 25.0
        assert n.upside_then_pct == 50.0

    def test_going_the_other_way_is_negative_progress_not_zero(self):
        n = bs.build([reading(price_then=4.0, target_then=6.0, price_now=3.0)],
                     today=TODAY).names[0]
        assert n.progress_pct == -50.0
        assert n.reached is False

    def test_a_target_below_the_price_has_no_measurable_road(self):
        """Dělit nulou nebo záporem by vyrobilo číslo bez významu."""
        n = bs.build([reading(price_then=6.0, target_then=4.0, price_now=5.0)],
                     today=TODAY).names[0]
        assert n.progress_pct is None
        assert n.reached is None

    def test_reaching_the_target_exactly_counts_as_reached(self):
        n = bs.build([reading(price_then=4.0, target_then=6.0, price_now=6.0)],
                     today=TODAY).names[0]
        assert n.reached is True

    def test_no_average_move_is_published(self):
        """
        Osmadvacet jmen s cíli od 6 % do 186 % nemá smysluplný průměr. Vrací se
        řádky a medián dnů — nic, co by šlo přečíst jako „jejich průměrný cíl".
        """
        card = bs.build([reading("A"), reading("B", target_then=20.0)], today=TODAY)
        assert not hasattr(card, "average_move_pct")
        assert "průměr" not in card.verdict_cs.lower()


class TestSerialisation:
    def test_the_payload_always_carries_the_horizon_next_to_the_verdict(self):
        payload = bs.build([reading(days_ago=3)], today=TODAY).to_dict()
        assert payload["min_horizon_days"] == bs.MIN_HORIZON_DAYS
        assert payload["too_early"] is True
        assert payload["reached_total"] is None
        assert payload["names"][0]["symbol"] == "ABCD"

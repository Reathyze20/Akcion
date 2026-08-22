# Backlog

Živý seznam. Pořadí = **riziko pro kapitál × úspora tvého času**, ne závažnost a ne atraktivita featury.
Zdroje: [audit 22. 8.](AUDIT_2026-08-22_AKCNI_PLAN.md) (56 ověřených nálezů) a gap-mapa
[kánonu](GOMES_METHODOLOGY_CANON.md#9-gap-map--článek-vs-současný-kód) (co metoda vyžaduje a appka nemá).

**Stav ověřen proti kódu 22. 8. 2026** (commit `31184dc`), ne převzat z auditu — auditní kotvy míří na
`8e32c1d` a od té doby padlo šest položek. Každý řádek níž jsem si sám ověřil v aktuálním kódu.

| | |
|---|---|
| `[ ]` | otevřené, ověřené v aktuálním kódu |
| `[x]` | hotové, s commitem |
| `[?]` | vyžaduje tvoje rozhodnutí, nemůžu ho udělat za tebe |

---

## P0 — appka buď nefunguje, nebo tvrdí čísla, která nejsou pravda

### `[x]` B1. Analýza je mrtvá od 1. června

`gomes_deep_dd.py:73` volá `gemini-2.0-flash`, který byl vyřazen **1. 6. 2026**. Tlačítko „Analyzovat"
nefunguje ~12 týdnů. Stejný mrtvý model i v `constants.py:143`, `core/analysis.py`,
`knowledge_synthesis.py`, `routes/analysis.py`.

V `.env` je platný `ANTHROPIC_API_KEY` (108 znaků) i `GEMINI_API_KEY`. Extrakce claimů už na Claude jede
(`claim_extraction.py:374`), takže cesta existuje.

**Hotovo když:** „Analyzovat" doběhne na živém modelu a vrátí skóre. Kdo model volá, ať ho volá z jednoho
místa, ne z pěti.

### `[x]` B2. Neúspěšné stažení ceny se razítkuje jako čerstvé

`yahoo_cache.py:498` — `_increment_error_count` nastaví `last_updated = NOW()`. Selhání tím **vyřadí
jedinou pojistku proti starým datům**: čím víc fetch selhává, tím čerstvěji cena vypadá. Přesně opačně,
než má.

Přímý zásah do „musí přežít, když se týden nedívám": po týdnu výpadku appka tvrdí týden starou cenu jako
dnešní.

**Hotovo když:** neúspěch nesahá na `last_updated`. Stáří ceny na UI je stáří posledního *úspěšného*
stažení.

### `[x]` B3. Včerejší close se vydává za aktuální cenu

`market_data.py:168-170` — když Finnhub nemá kotaci, potichu vrátí `pc` (previous close) a ta jde dál
jako „current price". Massive/Polygon vrací včerejší close pořád.

Cena je vstup do R/R skóre, takže se ta chyba propíše do každého verdiktu.

**Hotovo když:** cena si nese, ke kdy platí. Když je to close, řekne se to — nedosazuje se za živou kotaci.

### `[x]` B4. Kurzy měn jsou z ledna 2025

`currency.py:43` — `FALLBACK_RATES` má razítko `2025-01-11`, dnes je o 9–15 % vedle, a použijí se tiše,
kdykoliv ČNB neodpoví. Neznámá měna dostane potichu kurz USD.

Celé portfolio v CZK stojí na těchhle číslech. Čtyři pozice drží CAD/EUR.

**Hotovo když:** starý kurz se buď nepoužije, nebo je vidět, že je starý. Neznámá měna není USD.

### `[x]` B5. Analýza zapíše skóre do DB a až pak spadne

`gomes_deep_dd.py` — `score_history` se přidá do session, drift alert taky, a `AttributeError` přijde až
potom. Uvidíš „analýza selhala", ale conviction skóre v DB už je jiné.

**Hotovo když:** zápis a pád nemůžou nastat v tomhle pořadí. Buď projde celá analýza, nebo se nezmění nic.

---

## P1 — bez tebe se nic nestane

### `[x]` B6. Notifikace nemůžou odejít

Dva paralelní stacky: ten nakonfigurovaný nemá automatiku, ten s automatikou (`notifications.py:291`)
neumí na tomhle stroji postavit ani jeden kanál. A i kdyby: `EmailChannel._format_html` má
`{alert.entry_price:.2f if alert.entry_price else '—'}` — **neplatný format spec**, spadne při každém
volání.

**Hotovo když:** jeden kanál skutečně odešle zprávu na tvůj účet, ověřeno odesláním.

### `[ ]` B7. Away mode neexistuje

Ani v jedné podobě. Scheduler žije uvnitř ručně spuštěného localhost procesu — zavřeš appku, skončí
všechno. Přitom je to ta funkce, kterou při relapsu potřebuješ nejvíc: utaženější stopy, default na
raise cash, **jeden** nejnaléhavější push místo šumu, a stará data viditelně označená.

Závisí na B6 (kanál) a B2 (poctivé stáří dat).

**Hotovo když:** týden nespuštěná appka ti pošle nejvýš pár zpráv a žádná z nich není postavená na
starých datech vydávaných za čerstvá.

### `[x]` B8. Health endpoint lže

Hlásí model, který neexistuje, a inzeruje `google_search`, který je vypnutý. Health, kterému se nedá
věřit, je horší než žádný — je to první místo, kam se podíváš, když něco nesedí.

**Hotovo když:** hlásí to, co appka opravdu volá.

---

## P2 — věrnost metodě (kánon říká, kód nemá)

### `[?]` B9. Weinstein pilíř odporuje kánonu — tvoje rozhodnutí

Master Signal má „Weinstein Guard" (30 WMA, 15 % váhy) = technická analýza. Gomes explicitně píše, že
metoda *„has almost NOTHING to do with technical analysis"* (kánon gap #3).

Tři možnosti: označit jako **vlastní rozšíření mimo Gomese**, snížit váhu, nebo odstranit.
Neudělám to za tebe — je to tvoje metodické rozhodnutí, ne bug.

### `[ ]` B10. Yellow neflagne držené WAIT_TIME pozice

Kánon §2: v Yellow se prodávají **všechny spekulativní i „Wait Time"** akcie. `get_blocked_tiers`
blokuje jen TERTIARY tier, ne držené WAIT_TIME pozice (gap #9). Půlka pravidla chybí.

Data jsou: `inflection_status` se od commitu `31184dc` konečně čte z reálného záznamu.

### `[ ]` B11. Emoční brzdy — cooldown po ztrátě, detekce revenge-tradingu

Audit je označil za neexistující, protože nebyla kniha obchodů. **Ta teď existuje**
(`services/trade_ledger.py`, zapisuje i `emotion_tag`) — takže brzdy jdou konečně postavit.

Je to důvod, proč appka vznikla, a v běžícím kódu pro to zatím není nic.

### `[ ]` B12. Market alert gauge

Semafor je ručně nastavené pole. Kánon ho odvozuje z pozice S&P na 40letém valuačním grafu (gap #2).
Aspoň asistovaný výpočet, aby GREEN nestál na tom, že si někdo vzpomněl přepnout přepínač.

Souvisí s už opraveným `STALE_ALERT_AFTER = 14 dní`.

### `[ ]` B13. BOXX / RWM jako reálné instrumenty

Cash je dnes abstraktní `cash_pct`, hedge taky. Kánon §2 je má jako konkrétní tickery, do kterých se
opravdu jde (gap #6). Nejmenší dopad z P2 — dokud nejsi v Yellow/Orange, nespustí se.

---

## Hotovo

- `[x]` Tlačítka Buy/Sell v obchodním modálu byla `console.log` no-opy → napojeno na `apiClient`
- `[x]` Semafor v modálu byl vždy GREEN → čte se přes `marketAlertOverride ?? fetchedAlert`
- `[x]` Vymyšlené cenové linie (`cena × 0.80 / 1.50 / 0.65`) → smazáno z promptu i z `gomes_deep_dd`
- `[x]` Buy Guard byl mrtvý kód → volá se z `daily_actions`, `gomes_logic`, `master_signal`
- `[x]` Kniha obchodů neexistovala → `services/trade_ledger.py`, píše i `emotion_tag`
- `[x]` 3-bodové cenové triggery → `gomes_logic.py:641` `three_point_up` / `three_point_down`
- `[x]` Logaritmické R/R skóre + válce → `gomes_logic.py:545`, pokryto testy
- `[x]` Klasifikátor vyráběl 10-válcové BUY ze substringu — commit `1902969`
- `[x]` Sedm měsíců starý GREEN semafor autorizoval dnešní nákupy — commit `3630a38`
- `[x]` Chybějící data na pozici se zodpovídala SELL příkazem — commit `eed1265`
- `[x]` Verbatim guard mazal pravdivé claimy přes časové značky — commit `6440f64`
- `[x]` Portfolio tabulka odpovídala na „bez analýzy" verdiktem — commit `31184dc`
- `[x]` B1 Analýza volala model vyřazený 1. 6. 2026 — commit `f179e58`
- `[x]` B8 Health endpoint hlásil neexistující model a web přístup, který appka nemá — commit `f179e58`
- `[x]` B2 Neúspěšné stažení dávalo staré ceně razítko „teď“ a tím vypínalo jedinou pojistku
- `[x]` B3 Finnhub dosazoval včerejší close za chybějící kotaci; Massive se jmenoval, jako by vracel živou cenu
- `[x]` B4 Kurzy z ledna 2025 se používaly tiše; neznámá měna dostávala kurz dolaru
- `[x]` B5 Analýza commitla nové skóre a teprve pak spadla na chybějícím poli
- `[x]` B6 Automatizovaný stack četl názvy proměnných, které v `.env` nejsou; e-mail padal na neplatném format specu

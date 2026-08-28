# Rozhodovací jádro: Pásmo × Kvalita × Načasování — Prohloubený plán

## Verdikt k původnímu plánu

Původní plán je chirurgicky přesná diagnóza a solidní architektura. Níže jsou věci, které jsem při myšlení do hloubky identifikoval jako **slepá místa, strukturální rizika a chybějící mechanismy**, seřazené podle toho, jak moc by bolely v produkci.

---

## 🔴 Kritické mezery, které plán neadresuje

### 1. Chybí tvrdá technická brána mezi Fází 0 a zbytkem

Plán říká „teď, nebo nikdy" pro deník — ale technicky nic nebrání tomu, aby engine vydal první signál **před** tím, než migrace proběhne. Jeden `alembic upgrade` se může zaseknout, někdo spustí `daily_actions` ručně, a první skutečný pokyn se zapíše bez `rr_score`, `band`, `green_line`.

**Řešení:** Startup guard v `daily_actions.py`:
```python
REQUIRED_JOURNAL_COLUMNS = ['rr_score', 'band', 'green_line', 'red_line', 'cylinders']
def _verify_schema():
    """Raises RuntimeError if journal schema is not ready. 
    This gate MUST NOT be bypassable."""
    missing = [c for c in REQUIRED_JOURNAL_COLUMNS 
               if c not in inspect(conviction_score_history).columns]
    if missing:
        raise RuntimeError(f"Journal schema incomplete: {missing}. Run migration first.")
```
Volat na začátku `generate_daily_actions()`. Ne check, ne warning — `RuntimeError`. Engine nesmí běžet s děravým deníkem.

### 2. Cylinder rubrika nemá definovanou agregaci

Plán uvádí ±1/±2 váhy pro ~10 rubrikových bodů, ale nikde neříká:
- Jaký je **rozsah výsledku**? Může být záporný?
- Je to **součet pozitivních**, nebo **netto**?
- Jak se mapuje na Gomesův koncept „válce = 0–10"?

Tohle je zásadní, protože `deserved = 10 − cylinders` a celé pásmo z toho vychází.

**Návrh agregace:**
```
raw_score = Σ(všechny body)                    # může být záporné
cylinders = clamp(raw_score, 0, 10)            # Gomes škála 0–10
unknowns_count = počet bodů, které nelze zjistit
```

> [!IMPORTANT]
> Pokud `unknowns_count > 3`, rubrika by neměla vydat návrh vůbec — příliš málo dat na smysluplné číslo. Tohle plán zmiňuje obecně („pojmenuje mezeru"), ale chybí mu tvrdý práh.

**Minimální práh pro vydání návrhu:** rubrika potřebuje alespoň 5 ze ~10 bodů vyhodnocených. Pod tím se nejedná o „nízké válce", ale o „nevíme".

### 3. Race condition: Tracker sync vs. potvrzení válců

Scénář:
1. Potvrdíš válce pro CXDO při zelené 3,25 a červené 15,50
2. O hodinu později tracker sync posune zelenou na 4,00
3. Tvoje potvrzení je nyní proti **starým liniím** — R/R skóre se změnilo, ale pásmo bylo spočítané z jiného rozpětí

**Řešení:** Potvrzení válců musí nést `confirmed_against_green` a `confirmed_against_red`. Když se linie posunou o víc než X %, potvrzení se automaticky označí jako `stale` (ne smazané — prodejní strana ho stále čte, viz pravidlo „vypršení nesmí umlčet").

### 4. Fronta nových pozic nemá řazení

Pravidlo „max 1 nová pozice za týden" (2b-2) je správné, ale plán neříká: **kterou vybrat**, když jich je víc?

Scénáře:
- 5 tickerů vstoupí do BUY zóny ve stejný den
- Koupíš první (podle čeho?)
- Příští týden je #2 už mimo zónu

**Návrh řazení fronty:**
1. Nejnižší `rr_score` (= největší discount vůči červené linii) — „co je nejlevnější"
2. Při shodě: vyšší `cylinders` — „co je kvalitnější"
3. Při shodě: menší `unknowns_count` — „o čem víme víc"
4. **Nikdy** podle velikosti pozice nebo absolutní ceny

A fronta se **přepočítá každý den** — položka, jejíž podmínky se změnily (opustila pásmo, vypršely válce), z fronty vypadne. Tohle je de facto „priority queue s denním garbage collection".

### 5. Chybí paper-trade fáze

Plán jde z „testy prošly" rovnou na „engine vydává pokyny". To je skok přes propast.

**Vložit Fázi 2.5: Stínový režim (2–4 týdny)**
- Engine běží denně, zapisuje do `shadow_actions` tabulky
- Žádné notifikace, žádné push
- Ty mezitím děláš rozhodnutí ručně
- Po 2–4 týdnech porovnáš: co řekl engine vs. co jsi udělal
- Pokud engine nikdy nevydal BUY (= stále nefunguje), víš to dřív, než na něj spoléháš

> [!WARNING]
> Bez stínového režimu je „konec nasucho" v plánu jen unit test. Unit test ověří, že kód vrátí správné číslo pro fixture. Stínový režim ověří, že celý řetězec (sync → rubrika → potvrzení → ladder → guard → pokyn) proběhne i v produkčním prostředí s reálnými daty.

### 6. Degradovaný stav mezi fázemi není specifikovaný

Po každé fázi existuje přechodné období, kdy engine umí „půlku". Plán neříká, co se děje v těchto mezerách:

| Stav | Co engine umí | Co by měl dělat |
|------|---------------|-----------------|
| Po Fázi 1, před Fázi 1c | Má linie, nemá válce | Jen R/R skóre bez pásma. `band = NEZNÁMÉ` pro vše. Nákup zablokován (správně). |
| Po Fázi 1c, před Fázi 2a | Má linie + válce, nemá ladder | Starý `get_action_zone` s deserved místo 5. Lepší než dnes, ale ještě ne cílový stav. |
| Po Fázi 2a, před Fázi 4 | Má pásmo, nemá načasování | Pásmo platí, ale pokyn nemá `valid_until` ani blackout. Uživatel musí vědět, že platnost pokynu ještě není hlídaná. |

**Každý přechodný stav potřebuje viditelný štítek v UI**: „Engine v1.1 — pásmo bez načasování" nebo podobně. Jinak si zvykneš na pokyn, který vypadá hotově, ale nemá všechny záruky.

---

## 🟡 Důležité vylepšení

### 7. Gradualita uvnitř pásma

Plán má binární pásma (NÁKUP / DRŽET / PŘEPLACENO). Ale akcie na skóre 8.0 (hluboko v nákupu) a akcie na skóre 6.6 (sotva v nákupu) by neměly dostat stejný pokyn.

**Návrh: intenzita uvnitř pásma**
```
SILNÝ NÁKUP:  skóre > deserved + 2.0    (hluboko pod zelenou)
NÁKUP:        skóre > deserved + 0.5    (v nákupním pásmu)
DRŽET:        |skóre − deserved| ≤ 0.5
PŘEPLACENO:   skóre < deserved − 0.5
SILNĚ PŘEPLACENO: skóre < deserved − 2.0
```

Tohle neovlivňuje logiku Buy Guardu (ten je binární: projde/neprojde), ale ovlivňuje:
- **Velikost dávky**: SILNÝ NÁKUP = mezera/2, NÁKUP = mezera/3
- **Prioritu ve frontě**: SILNÝ NÁKUP sortuje výš
- **Zobrazení**: jiná barva na škále

### 8. Audit tracker vs. realita PŘED prvním synchroundem

Plán identifikuje rozpor (CXDO 4,50/19,00 vs. 3,25/15,50), ale nepokládá klíčovou otázku: **proč jsou jiné?**

Možnosti:
- Tracker byl aktualizován, `price_lines_data.py` ne → tracker je pravda
- Byl split a jedno z čísel ho nezachytilo → jedno je špatně
- Gomes přecenil firmu → obě jsou „správné" k různému datu

**Před prvním synchroundem:** jednorázový audit, který porovná tracker linie vs. poslední známou cenu a ověří, že `green_line < current_price < red_line` je alespoň fyzicky možné. Pokud zelená > červená, nebo obě > current_price × 10, data jsou poškozená.

### 9. Earnings date spolehlivost pro micro/small caps

`yfinance.Ticker().get_earnings_dates()` je notoricky nespolehlivý pro micro-capy (SMSI, ECOR, IRIX, RDCM...). Často vrací `None` nebo staré datum.

**Praktický dopad:** Pokud je datum odhad s chybou ±2 týdny a blackout je 14 dní, musíš buď:
- Rozšířit blackout pro odhadované datum na 21 dní (14 + 7 margin)
- Nebo blackout odstupňovat: tvrdý (žádný nákup) 7 dní před potvrzeným datem, měkký (varování) 14–21 dní před odhadem

**Návrh:**
```python
class EarningsDate:
    date: datetime
    source: Literal['confirmed', 'yfinance', 'estimated_from_cadence']
    confidence: Literal['high', 'medium', 'low']
    
    @property
    def blackout_start(self) -> datetime:
        margin = {
            'high': timedelta(days=14),
            'medium': timedelta(days=21),
            'low': timedelta(days=28)
        }
        return self.date - margin[self.confidence]
```

### 10. Semafor: co když se rozbije?

Auto-tightening („smí přitvrdit, nikdy povolit") je geniální bezpečnostní inženýrství. Ale: co když gauge vrátí YELLOW kvůli datové chybě? Ručně to opravit nemůžeš (engine to zakázal).

**Řešení:**
- Ruční override s povinným `reason` a `expires_at` (max 48h)
- Override se loguje do deníku odmítnutých akcí
- Po vypršení se vrací automatický stupeň
- Override nikdy nesmí nastavit GREEN — jen vrátit z chybného YELLOW na předchozí stav

### 11. Měsíční vklad ignoruje korelaci

„Největší mezera" jako heuristika pro alokaci vkladu neřeší situaci, kdy dvě největší mezery jsou ve stejném sektoru nebo typu aktiva. Pokud SMSI (biotech) a ECOR (biotech) mají oba největší mezeru, nasypat vklad do obou zvyšuje koncentraci.

**Vylepšení:** Po výběru podle mezery, zkontrolovat `stocks.asset_class` a `stocks.sector`. Pokud by vklad zvýšil sektorovou váhu nad 25 %, přeskočit na další mezeru. Toto korelační pravidlo je jednodušší než plný Markowitz a respektuje realitu, že u micro-capů nemáš kovarianční matici.

### 12. Portfolio-level concentration — rozšířit nad rámec SEC nálezů

Plán navrhuje sčítat podíl portfolia ve firmách s CRITICAL/HIGH nálezem. To je správné, ale neúplné. Existují další agregace, které per-akciový engine nevidí:

| Metrika | Práh | Akce |
|---------|------|------|
| Podíl s going concern / IC weakness | >25% | žádná nová spekulativní pozice |
| Podíl v jednom sektoru | >30% | varování, žádný nový nákup v tom sektoru |
| Podíl bez SEC pokrytí | >50% | informativní (dnes ~54%) |
| Podíl s vypršenými válci | >40% | „portfoli v tmě" varování |
| Počet pozic celkem | >15 | „rozředěný názor" — Gomes říká 8–12 |
| Podíl v pozicích bez linie | >30% | „většina portfolia mimo metodiku" |

### 13. Dva různé 3-body: pojmenovat TEĎKA, ne „někdy"

Plán správně identifikuje kolizi (konvikční drift 3 body ≠ R/R pohyb 3 body) a říká „pojmenovat odděleně". Ale tenhle rename patří do **Fáze 0**, ne „průběžně" — protože Fáze 0 zapisuje do deníku, a pokud se v deníku bude jmenovat `three_point_change` bez rozlišení, za rok nebudeš vědět, o kterých 3 bodech řádek mluví.

**Konkrétní pojmenování:**
- `conviction_drift` — pohyb konvikčního skóre od posledního hodnocení (thesis_monitor)
- `rr_shift` — pohyb R/R skóre od vstupu do pozice (kánon §5)

Obě se zapisují do deníku od prvního dne, jinak je kalibrace neměřitelná.

---

## 🟢 Strukturální vylepšení architektury

### 14. Typová ochrana principu „nikdy nevymyslí verdikt"

Dnes je to konvence. Mělo by to být v typovém systému:

```python
@dataclass
class BandResult:
    band: Literal['POD_ZELENOU', 'NAKUP', 'DRZET', 'PREPLACENO', 'NAD_CERVENOU']
    price_boundaries: dict[str, Decimal]
    
@dataclass  
class InsufficientData:
    missing: list[str]   # ["cylinders", "green_line"]
    reason: str

BandOrGap = BandResult | InsufficientData
```

Každá funkce, která počítá pásmo, vrací `BandOrGap`. Volající **musí** pattern-matchovat. `InsufficientData` se nikdy nesmí tiše proměnit v `DRZET` nebo `WATCH` — to je přesně ta chyba, kterou diagnóza identifikovala u `int(data_dict.get("conviction_score", 5))`.

### 15. Idempotence tracker syncu

`tracker_sync.sync_tracker()` by měl být idempotentní — spuštění dvakrát za sebou nesmí vytvořit duplicitní `TrackerChange` záznamy nebo dva push notifikace. Plán zmiňuje `MIN_POLL_INTERVAL = 12h`, ale to je throttling, ne idempotence. Pokud poll proběhne a pak se restartuje server a proběhne znovu (pod 12h limitem kvůli restartu), výsledek musí být stejný.

**Řešení:** `TrackerChange` nese hash `(ticker, green, red, timestamp_rounded_to_day)`. Duplicitní hash = skip.

### 16. Kdy se pásmo přepočítá?

Plán nespecifikuje trigger pro přepočet. Možnosti:

| Trigger | Pro | Proti |
|---------|-----|-------|
| Každý API request | Vždy aktuální | Pomalé, zbytečné |
| Denně (daily_actions) | Jednoduchý, stačí | 23h stará data |
| Při změně vstupu (cena, linie, válce) | Optimální | Složitější implementace |

**Doporučení:** Denně v `daily_actions` + on-demand přes API endpoint. Nikdy při každém GET requestu — to je past na výkon. Denní přepočet je konzistentní s tím, jak se appka reálně používá (otevřeš ji jednou denně, chceš vidět aktuální stav).

---

## Aktualizované pořadí implementace

Původní pořadí je správné v hlavních obrysech. Přidávám sub-kroky a jednu novou fázi:

| # | Co | Změna oproti originálu |
|---|----|-----------------------|
| **0** | Fáze 0 — deník + rename 3-bodů + schema guard | + rename `conviction_drift` / `rr_shift` **teď**, + startup guard |
| **1** | 1a + 1b — přívod linií + smazání rozporných dat | + jednorázový audit tracker vs. realita |
| **2** | 1c — rubrika válců + agregační pravidlo + práh unknowns | + definice clamp(0,10) + min 5 bodů pro návrh |
| **3** | 2a — ZoneLadder + cenové hranice | beze změny |
| **3.5** | **NOVÉ: Stínový režim 2–4 týdny** | engine běží, nic neposílá, porovnáváš |
| **4** | 2b — dokup + fronta s řazením + dávková disciplína | + řazení fronty (skóre → válce → unknowns) |
| **5** | Fáze 4 — načasování + platnost pokynu | + EarningsDate.confidence + odstupňovaný blackout |
| **6** | 2b — odstranění soupeřů | beze změny (až nový engine prokazatelně funguje) |
| **7** | Fáze 3 — mimo metodiku | beze změny |
| **8** | Portfolio-level concentration (rozšířená) | + sektorová váha, + podíl bez SEC, + počet pozic |
| **9** | Fáze 5 — obrazovka + degradovaný stav labels | + štítky přechodných stavů |
| **10** | Opravy | beze změny (průběžně) |

---

## Rozšířená verifikační tabulka

K původním testům přidat:

| Co | Očekávané |
|----|-----------|
| `green_line > red_line` (datová chyba) | `InsufficientData("green > red, data corrupted")`, nikdy pásmo |
| cena přesně na `green_line` | `POD_ZELENOU` (inclusive boundary) |
| penny stock se spreadem 20 % šířky pásma | varování „spread příliš široký pro limitní příkaz" |
| rubrika s 3 z 10 bodů vyhodnocenými | žádný návrh, `InsufficientData(["unknowns: 7/10"])` |
| rubrika se záporným raw_score | `cylinders = 0`, ne záporné číslo |
| tracker sync spuštěný 2× za sebou | identický výsledek, žádný duplicitní change/push |
| schema guard — chybí sloupec `rr_score` | `RuntimeError`, engine se nespustí |
| fronta 5 nákupů, #2 příští týden mimo zónu | #2 vypadne z fronty, #3 se posune |
| měsíční vklad, 2 největší mezery stejný sektor | přeskočí na 3. mezeru |
| semafor override na GREEN | odmítnuto, override nikdy nepovolí GREEN |
| potvrzení válců, linie se pak změní o >5 % | potvrzení flagged `stale`, prodejní strana funguje, nákupní ne |
| `conviction_drift` 3 body + `rr_shift` 1 bod | žádný trigger §5 — jen drift, ne shift |

---

## Open Questions

> [!IMPORTANT]
> **Agregace válců: součet vs. vážený průměr?**
> Rubrika má body ±1 a ±2. Je runway < 6 měsíců (−2) opravdu dvakrát horší než klesající tržby (−1)? Nebo by měly být všechny body ±1 a runway/going concern je prostě **veto** (= válce automaticky 0 bez ohledu na zbytek)? Veto model je jednodušší a bezpečnější — firma s going concern nemá co být „na 3 válcích".

> [!IMPORTANT]  
> **Stínový režim: jak dlouho?**
> 2 týdny = minimum pro alespoň 10 denních běhů. 4 týdny = pokryje jeden earnings cyklus. 8 týdnů = statisticky smysluplnější, ale zdržuje. Jaká je tvoje tolerance pro čekání?

> [!WARNING]
> **Rubrika pro firmy mimo SEC:** U kanadských a ISIN pozic (KUYA.V, IMP.V, GSI.V, DBO.TO) nemáš 6 z 10 rubrikových bodů (tržby, marže, cash flow, runway, ředění, red flags). Rubrika pro ně **nikdy** nevydá návrh, pokud je práh 5 bodů. Buď: (a) snížit práh pro non-SEC na 3 body, (b) akceptovat trvalé `NEZNÁMÉ`, (c) najít alternativní datový zdroj (SEDAR+ pro Kanadu). Které z toho preferuješ?

> [!WARNING]
> **Breakout watchlist a pásmo:** Plán říká, že breakout je „jen evidence, nikdy násobitel." Ale co když breakout target < červená linie? Pak breakout signál říká „cíl je nižší než plná valuace" — to je samo o sobě informace, kterou by engine měl zobrazit (ne jednat podle ní, ale zobrazit). Souhlasíš?

---

## Co plán vědomě neslibuje — rozšíření

Původní plán správně říká, že negarantuje dobré načasování. Přidávám:

- **Nenahrazuje due diligence.** Rubrika počítá z dostupných dat; „co Gomes skutečně řekl" závisí na kvalitě `claim_extraction`, která může citaci vytáhnout z kontextu.
- **Neřeší likviditu.** U micro-capů s objemem <$50k/den je limitní příkaz „kupuj do 4,12 $" reálně nevykonatelný bez market impactu. Engine by měl u pozic pod prahem likvidity zobrazit varování, ne pokyn.
- **Nevidí makro události.** Celní válka, Fed, geopolitika — nic z toho rubrika nezachytí. Semafor je nejbližší proxy a je vědomě pomalý.
- **Kalibrace je opravdu až srpen 2027.** Do té doby je celý systém „informovaný odhad s auditní stopou", ne „ověřená metoda". Plán to říká; stojí za to to připomínat na obrazovce.

---

# 📐 Datová základna pro ohodnocení jedné akcie

> Doplněno 23. 8. 2026. **Každé číslo v této části je změřené** proti živému
> `riskrewardcharts.com/api/tickers`, živému `breakoutinvestors.com/api/stocks`
> a produkční databázi — ne odhadnuté a ne převzaté z dřívějšího snapshotu.
> Kde měření chybí, je to napsané.

Zbytek plánu řeší **jak** se z dat udělá rozhodnutí. Tahle část řeší otázku,
která je před ním a dosud nikde nestála celá: **jaká data to vlastně jsou,
odkud se každé z nich bere, a kolik jich dnes reálně máme.** Odpověď je
nepříjemná a je to nejlevnější zjištění v celém dokumentu: engine je hotový a
otestovaný, ale u jedenácti z dvanácti pozic nemá z čeho počítat.

---

## 17. Úplný seznam vstupů, které brána vyžaduje

`GomesGatekeeper.evaluate_buy_guard` (`gomes_logic.py:922`) je jediná pravda o
tom, co je k verdiktu potřeba. Brány se vyhodnocují v tomhle pořadí a **první
neúspěch končí** — což je zároveň pořadí, v jakém má smysl data shánět:

| # | Brána | Vstup | Odkud | Automaticky? |
|---|-------|-------|-------|--------------|
| 1 | Semafor je GREEN | `market_alert` | 40letý graf S&P, `market_gauge.py` | 🟡 asistovaně |
| 2 | Válce známé a ≠ 0 | `cylinders` 0–10 | **nikde na webu** — stream, skupina, úsudek | ❌ nikdy |
| 3 | Není Wait Time | `lifecycle_phase` | stream / analýza textu | 🟡 z přepisu |
| 4 | R/R i zasloužené existují | `green_line`, `red_line`, `price` | **riskrewardcharts.com** | ✅ plně |
| 5 | R/R > zasloužené | `10×log(High/price)/log(High/Low)` vs `10 − cylinders` | výpočet | ✅ |

K tomu vstupy, které nejsou v bráně, ale rozhodují o **velikosti** a o tom, co
se ukáže:

| Vstup | K čemu | Odkud | Automaticky? |
|-------|--------|-------|--------------|
| `pick_type` OFFICIAL / NOT OFFICIAL | portfolio vs. watchlist, tier | riskrewardcharts.com | ✅ |
| `tier` Primary / Secondary / Tertiary | strop pozice 10 / 5–8 / 1–2 % | odvozeno z fáze + pick_type | 🟡 |
| `endorsements` | konvikce druhého zdroje | breakoutinvestors.com | ✅ |
| `upside` → cílová cena | odhad druhého zdroje | breakoutinvestors.com | ✅ |
| `avg_cost` | P/L, pravidlo zdvojnásobení | výpis od brokera | ❌ jen ručně |
| `currency` | hodnota v CZK | výpis od brokera | ❌ jen ručně |
| SEC fundamenty (runway, burn, ředění) | rubrika válců | EDGAR XBRL | ✅ jen pro US |

> [!IMPORTANT]
> **Brána č. 2 je ta, o kterou to celé stojí.** Válce nejsou na žádné stránce.
> Ani u Gomese, ani u BI. Jsou to jeho slova ze streamu o provozním zdraví
> firmy. Dokud pro ně neexistuje cesta dovnitř, je jedno, kolik dalších
> zdrojů se napojí — brána skončí na druhém kroku u všech dvanácti pozic.

---

## 18. Co která stránka skutečně publikuje

### 18a. riskrewardcharts.com — `GET /api/tickers`

Odpovídá bez autentizace, JSON, `{"items": [...], "cached": true}`. Šest polí
na pick, nic víc:

```
ticker · low (Green Line) · high (Red Line) · pickType · price · chartUrl
```

**Živý stav 23. 8. 2026 — 16 picků, 7 OFFICIAL + 9 NOT OFFICIAL:**

| pickType | Tickery |
|----------|---------|
| OFFICIAL (Money Mark Portfolio) | CXDO, GEO.TO, GKPRF, ITMSF, IZEA, TPCS, VTSI |
| NOT OFFICIAL (watchlist) | AEHR, AMPL, CELH, CURI, DRSHF, EVLV, IDN, KRKNF, TSSI |

`pickType` je to jediné pole, které nemá náhradu odjinud — říká, jestli za
pickem stojí skutečné peníze. Mapuje se 1:1 na appčin split portfolio/watchlist.

**Co tam NENÍ:** válce, fáze životního cyklu, tier, teze, katalyzátor, datum
výsledků, DCF předpoklady. Nic z toho se z těch šesti polí neodvodí.

### 18b. breakoutinvestors.com — tři endpointy

| Endpoint | Vrací |
|----------|-------|
| `GET /api/stocks` | 28 jmen: `symbol · companyName · endorsements · upside · created_at` |
| `GET /api/stocks/{symbol}` | kvóta OHLCV (open/high/low/price/volume/latestTradingDay) |
| `GET /api/stocks/batch?symbols=…` | tytéž kvóty dávkově |

`upside` je jejich cílová cena řečená jinak — `cena × (1 + upside)` ji
rekonstruuje na kulaté číslo, což je podpis uloženého analytického cíle, ne
aritmetické náhody (WATT $29,40, DAIO $6,50, ADCOF $0,30).

**Co tam NENÍ:** psané analýzy, teze, valuační pásmo, válce. Prosa je za
přihlášením a do aplikace vede ručním vložením přes importér přepisů
(`claim_extraction`), ne API.

> [!WARNING]
> **Obě stránky odpovídají bez autentizace na produkt, který je placený.**
> Kód to řeší třemi pravidly, která musí zůstat: jeden dotaz denně
> (`MIN_POLL_INTERVAL` — 20 h u BI, 12 h u trackeru), poctivá hlavička
> `User-Agent`, a **nic v aplikaci na těch datech nesmí tvrdě viset**. Když
> zdroj zmizí, vrátí se chyba a Gomesova strana běží dál. Přívod dat, který se
> pozná podle zátěže, je přívod dat, který se zavře.

---

## 19. Matice pokrytí portfolia (změřeno 23. 8. 2026)

Klíčováno kanonickým tickerem (`app/core/tickers.py`), protože čtyři pozice se
drží na kanadské burze, zatímco oba zdroje jmenují americký OTC listing.

| Kanonicky | Náš ticker | riskrewardcharts | zelená | červená | válce | fáze | skóre | BI |
|-----------|-----------|------------------|-------|--------|------|------|------|-----|
| GKPRF | GSI.V | **OFFICIAL** | 0,30 | 3,75 | 10 | UNKNOWN | — | ano |
| ITMSF | IMP.V | **OFFICIAL** | 0,30 | 10,00 | — | — | — | ano |
| IZEA | IZEA | **OFFICIAL** | 2,50 | 11,00 | — | — | — | — |
| VTSI | VTSI | **OFFICIAL** | 5,00 | 22,50 | — | — | — | — |
| DAIO | DAIO | — | — | — | — | — | — | ano |
| DBOXF | DBO.TO | — | — | — | — | — | — | ano |
| INFU | INFU | — | — | — | — | — | — | ano |
| IRIX | IRIX | — | — | — | — | — | — | ano |
| KUYAF | KUYA.V | — | — | — | — | — | 10 ⚠️ | ano |
| RDCM | RDCM | — | — | — | — | — | — | ano |
| **ECOR** | ECOR | — | — | — | — | — | — | **—** |
| **SMSI** | SMSI | — | — | — | — | — | — | **—** |

**Tři čísla, která z toho plynou:**

1. **4 z 12** držených pozic jsou Gomesovy OFFICIAL picky. Zbylých osm nemá od
   něj žádné pokrytí — ani pásmo, ani zmínku.
2. **3 jeho OFFICIAL picky nedržíme vůbec:** CXDO, GEO.TO, TPCS. To není bug,
   ale je to informace: portfolio se s Money Mark Portfolio překrývá ze 4/7.
3. **ECOR a SMSI nepokrývá ani jeden zdroj.** Jsou to zároveň dvě nejhorší
   pozice v portfoliu (−35,66 % a −93,40 %). O nich aplikace neřekne nikdy
   nic, dokud pro ně nevznikne analýza mimo oba weby.

---

## 20. 🔴 Nejzávažnější nález: skóre a pásma jsou disjunktní množiny

Tohle není mezera v plánu, tohle je vada v datech, která je dnes v produkci.

Konvikční skóre má podle kánonu vycházet z pásma: `R/R = 10×log(High/price)/log(High/Low)`
a `zasloužené = 10 − válce`. V databázi je ale rozdělení takové, že **kromě
CXDO nemá ani jeden řádek se skóre pásmo, a ani jeden řádek s pásmem nemá skóre:**

| Skupina | Tickery | Má pásmo? | Má skóre? |
|---------|---------|-----------|-----------|
| Z trackeru | AEHR, AMPL, CELH, CURI, DRSHF, EVLV, GEO.TO, GKPRF, IDN, ITMSF, IZEA, KRKNF, TPCS, TSSI, VTSI | ✅ | ❌ |
| Se skóre | DOW 5, KRKN 2, **KUYAF 10**, MU 1, MVIS 1, **OPTX 9**, STX 1, TWLO 5 | ❌ | ✅ |
| Obojí | **CXDO** (3,25 / 15,50 / skóre 7) | ✅ | ✅ |

> [!CAUTION]
> **KUYAF má skóre 10 a verdikt `BUY_NOW` bez zelené linie, bez červené linie
> a bez válců.** OPTX má 9 a `BUY_NOW` za stejných podmínek. To jsou dvě
> nejsilnější doporučení v celé databázi a ani jedno nemá pod sebou vstup, ze
> kterého se podle metodiky počítá. Je to táž vada, jaká 23. 8. položila
> `/api/stocks` — sebejisté číslo bez vstupů — jen na jiném místě.

**Co s tím:** skóre bez pásma není „nízká kvalita dat", je to **jiná veličina**
než ta, kterou brána počítá. Buď se dohledá, odkud pochází (přepis? ruční
zápis?) a označí se zdrojem, nebo se smaže. Třetí možnost — nechat ho a
doufat, že se jednou doplní pásmo — znamená, že do té doby aplikace radí podle
čísla, které si nikdo neumí odvodit.

Sem patří i **KUYA.V (zdroj OTHER) se zelenou 1,20 a červenou 2,00** — na
trackeru KUYAF není, takže to pásmo někdo zadal ručně nebo ho aplikace
dopočítala z ceny. Provenience neznámá, a dokud je neznámá, je to pásmo
nepoužitelné.

---

## 20b. 🔴 Druhá sada pásem, systematicky býčí, a živý endpoint, který ji umí zapsat

`app/trading/price_lines_data.py` drží dvacet natvrdo zapsaných pásem. Vlastní
docstring toho souboru o nich říká:

> *„TODO: These values should be verified against actual screenshots.
> The values below are **placeholder estimates** that need manual review."*

`POST /api/gomes/price-lines/import-images` je zapsat do databáze umí —
`load_price_lines_from_images()` je projde, uloží jako `price_lines` se
`source="image"` a zaloguje do `image_analysis_log`, jako by byly odečtené
z grafů. Odečtené nejsou. Jsou to odhady.

**Porovnání se skutečným trackerem (23. 8. 2026), včetně dopadu na R/R skóre:**

| Ticker | placeholder | skutečné | cena | R/R z placeholderu | R/R skutečné | rozdíl |
|--------|-------------|----------|------|-------------------|--------------|--------|
| CELH | 23,50 / 137,50 | 18,00 / 110,00 | 33,36 | 8,02 | 6,59 | **+1,43** |
| CXDO | 4,50 / 19,00 | 3,25 / 15,50 | 6,39 | 7,57 | 5,67 | **+1,89** |
| EVLV | 3,00 / 11,75 | 2,50 / 9,00 | 5,34 | 5,78 | 4,08 | **+1,70** |
| GEODF | 2,10 / 7,50 | 1,75 / 5,25 | 2,86 | 7,57 | 5,53 | **+2,04** |
| GKPRF | 0,45 / 3,25 | 0,30 / 3,75 | 1,29 | 4,67 | 4,22 | +0,45 |
| IDN | 2,65 / 25,00 | 2,00 / 25,00 | 2,95 | 9,52 | 8,46 | **+1,06** |
| ITMSF | 0,55 / 11,00 | 0,30 / 10,00 | 0,75 | 8,96 | 7,39 | **+1,58** |
| IZEA | 3,35 / 11,50 | 2,50 / 11,00 | 2,99 | 10,00 | 8,79 | **+1,21** |
| KRKNF | 0,65 / 5,50 | 0,45 / 2,50 | 4,32 | 1,13 | 0,00 | **+1,13** |
| TPCS | 4,25 / 19,00 | 3,25 / 14,00 | 5,69 | 8,05 | 6,17 | **+1,89** |
| TSSI | 5,25 / 26,50 | 4,00 / 21,00 | 8,75 | 6,84 | 5,28 | **+1,57** |
| AEHR, CURI, VTSI | — | — | — | shodné (cena mimo pásmo) | | +0,00 |

> [!CAUTION]
> **Odchylka není náhodná — je jednosměrná.** Ani jeden placeholder nevychází
> pesimističtěji než skutečnost. Průměr je **+1,2 bodu na desetibodové škále**,
> maximum +2,04. A protože pravidlo zní `BUY když R/R > zasloužené`, posun o
> jeden až dva body nahoru **překlápí odmítnuté nákupy na povolené**.
>
> Konkrétní případ při válcích 5 (zasloužené 5,00):
> **EVLV skutečně 4,08 → ODMÍTNUTO. Z placeholderu 5,78 → POVOLENO.**
> Táž akcie, tentýž den, opačný verdikt — rozdíl je jen v tom, které pásmo
> se načetlo jako první.

Šest položek v tom souboru navíc **nejsou Gomesovy picky vůbec**: CTLP, IT,
IWM, NVDA, PESI, QQQ. Indexová ETF a large capy s vymyšleným valuačním pásmem
v tabulce, ze které engine čte valuaci.

**Je to třetí výskyt téhož vzoru v jednom dni** — po `_generate_mock_analysis`
(vymyšlené finanční údaje zapsané do skutečného portfolia) a po testovacích
řádcích MSTY/NVDY/TSLY/XMMO.V. Rozdíl je v tom, že tenhle míří přesně na
**jediný vstup, který engine skutečně používá**.

**Co s tím, v tomhle pořadí:**

1. **Zavřít endpoint** `POST /api/gomes/price-lines/import-images`, dokud se
   soubor nevyčistí. Ne warning — routa pryč nebo 501, stejně jako u AI
   analytika.
2. **Smazat šest ne-picků** (CTLP, IT, IWM, NVDA, PESI, QQQ). Nemají v tabulce
   valuací co dělat.
3. **Zbylých 14 nahradit trackerem**, který je publikuje přesně (§18a). Po
   zapojení `tracker_sync` (krok D2) je celý soubor zbytečný.
4. **Ověřeno 23. 8. 2026: `price_lines` i `image_analysis_log` jsou prázdné.**
   Placeholdery se nikdy nezapsaly, takže není co uklízet — jen zavřít dveře,
   než tudy někdo projde. To je jediná dobrá zpráva v téhle sekci a platí jen
   do příštího zavolání té routy.

---

## 21. Válce — jediný vstup, který na žádném webu není

**Stav dnes: v celé databázi je jeden jediný lifecycle řádek** (GKPRF, válce
10, fáze `UNKNOWN`). Jedenáct z dvanácti pozic nemá válce ani fázi.

Válce jsou přitom brána č. 2 — spadne na nich všechno ostatní. Ukázka, co
aplikace **umí spočítat už teď** u čtyř oficiálních picků a na čem to končí:

| Ticker | Nás | Low | High | Cena | R/R skóre | Brána |
|--------|-----|-----|------|------|-----------|-------|
| GKPRF | GSI.V | 0,30 | 3,75 | 1,29 | **4,22** | ❌ válce neznámé |
| ITMSF | IMP.V | 0,30 | 10,00 | 0,75 | **7,39** | ❌ válce neznámé |
| IZEA | IZEA | 2,50 | 11,00 | 2,99 | **8,79** | ❌ válce neznámé |
| VTSI | VTSI | 5,00 | 22,50 | 3,13 | **10,00** (pod zelenou) | ❌ válce neznámé |

Kdyby válce byly 5 (zasloužené 5), brána by u ITMSF, IZEA a VTSI **povolila
nákup**, u GKPRF odmítla (4,22 ≤ 5,00 — není dost levné vzhledem ke kvalitě).
Jinými slovy: **chybí jedno číslo mezi 0 a 10, a stojí na něm celý engine.**

**Tři cesty, jak se válce mohou dostat dovnitř, seřazené podle poctivosti:**

1. **Rubrika z tvrdých dat** (plán §2 / bod 1c). SEC XBRL dá runway, burn,
   ředění, trend tržeb a marží — to je 6 z ~10 bodů, automaticky, pro US
   tickery. Pro ITMSF, GKPRF, DBOXF, KUYAF (kanadské) to nefunguje, viz Open
   Question o SEDAR+.
2. **Z přepisu streamu.** `claim_extraction` už umí vytáhnout tvrzení
   z textu — „delays", „lawsuit", „CFO odešel", „firing on all cylinders" jsou
   přesně ty výrazy, které kánon jmenuje. Návrh válců z přepisu, potvrzený
   ručně, ne zapsaný automaticky.
3. **Ručně, jedno číslo na ticker.** Dvanáct čísel. Hodina práce. Dokud
   neexistuje 1 ani 2, tohle je jediná cesta, jak engine vůbec rozjet — a je
   lepší než čekat na automatiku, protože engine bez válců neřekne nic.

> [!IMPORTANT]
> Ať se zvolí kterákoli cesta, **válce musí nést datum a zdroj**. Válce
> z ledna nejsou fakt o firmě v srpnu a rubrika je bude muset umět prohlásit
> za vypršelé (viz §3 tohoto plánu o `stale` potvrzení).

---

## 22. Grafy jsou PNG — zbytek DCF je uvnitř obrázku

Každý pick nese `chartUrl`, například:

```
https://riskreward.z13.web.core.windows.net/charts/GKPRF.PNG   (~450 kB, image)
```

Tam je Gomesův skutečný R/R graf: linie **New DCF** a **Prior DCF**, očekávaný
**rev CAGR** a **net margin**, tedy předpoklady, ze kterých zelená a červená
linie vůbec vznikly. V JSON API nic z toho není.

To má dva důsledky:

- **Zelená a červená linie jsou výstup, ne vstup.** Aplikace je bere jako daná
  čísla a neví, na jakém růstu a marži stojí. Když se předpoklad změní, linie
  se pohne a aplikace se dozví jen to, že se pohnula — ne proč. Alert na posun
  linie (už napsaný v `gomes_tracker.diff_tracker`) je proto správná věc a
  zároveň maximum, co se z JSON dá.
- **Vision cesta zatím NEEXISTUJE, i když to tak vypadá.** V aplikaci je
  `ImageAnalysisLogModel`, routa `price-lines/import-images` a služba
  `load_price_lines_from_images()` — jenže žádná z nich obrázek nečte. Čtou
  natvrdo zapsaný slovník odhadů (§20b). Jméno slibuje odečet z grafu, kód
  dělá import placeholderů.
- **Postavit ji jde a stojí to za to.** Stáhnout PNG a nechat vision model
  přečíst DCF předpoklady je proveditelné. **Ale:** je to čtení čísel
  z obrázku modelem, což je přesně ten druh vstupu, který se nesmí zapsat jako
  fakt — patří to do návrhu k potvrzení, s odkazem na graf, ze kterého to je.
  A rozhodně to nesmí sdílet jméno ani tabulku s tím, co tam je dnes.

---

## 23. Přívod linií je napsaný a nezapojený

`app/services/gomes_tracker.py` + `app/services/tracker_sync.py` jsou hotové a
otestované: čtou `/api/tickers`, porovnávají dva odečty, hlásí posun zelené či
červené linie i přehození OFFICIAL ↔ NOT OFFICIAL. **Nevolá je nic.** Žádná
routa, žádný scheduler, žádný skript.

Přesně v tomhle stavu byl do 23. 8. i `breakout_watchlist.py`, než se
zapojil — model, migrace, routa, denní úloha v Plánovači, karta v UI.
Tracker potřebuje totéž a je hodnotnější: dodává **bránu č. 4** pro sedm
oficiálních picků, zatímco BI dodává druhý názor.

**Konkrétně chybí:** tabulka na stav odečtu, routa `GET/POST /api/tracker/*`,
denní úloha (obálka `.cmd` jako u `evaluate_scores` a `breakout_poll`),
upozornění na posun linie a zobrazení v UI. Odhad: stejný rozsah jako přívod
BI, tedy jeden zásah.

---

## 24. 🔴 Testovací řádky v produkční databázi

V `stocks` leží čtyři řádky s vymyšlenými pásmy:

| Ticker | Název | Zelená | Červená |
|--------|-------|-------|--------|
| MSTY | MSTY Test Company | 45,00 | 55,00 |
| NVDY | NVDY Test Company | 25,00 | 35,00 |
| TSLY | TSLY Test Company | 40,00 | 50,00 |
| XMMO.V | XMMO.V Test Company | 0,60 | 1,00 |

Nejsou to pozice a dnes nic neovlivňují, ale jsou to **kulatá vymyšlená pásma
v tabulce, ze které engine čte valuaci**. Jakmile se doplní válce plošně,
začnou z nich vycházet R/R skóre jako z čehokoli jiného. Smazat před Fází 1,
ne po ní.

---

## 24b. 🔴 `price_lines` je přes ORM nečitelná (týž typ vady jako `catalyst_date`)

Model `PriceLinesModel` má sloupce `conviction_score_at_green` a
`conviction_score_at_red`. Databáze má `gomes_score_at_green` a
`gomes_score_at_red`. Jakýkoli dotaz přes ORM proto skončí:

```
psycopg2.errors.UndefinedColumn: column price_lines.conviction_score_at_green does not exist
```

**Není to jedna hodnota jako u `catalyst_date` — je to celá tabulka.** Nevšimlo
si toho nic jen proto, že je prázdná a v běžném toku ji nikdo nečte. První
zápis linek přes `PriceLinesModel` spadne, a spadne stejným způsobem: výjimka
se v routě přeloží na 500, front-end dostane chybu místo dat a nějaká
obrazovka nahlásí, že žádné linie neexistují.

Do stejné kategorie patří migrace, které se nespouštějí samy:
`initialize_database` volá `create_all(checkfirst=True)`, což **vytvoří chybějící
tabulky, ale nikdy nedoplní chybějící sloupec**. Každý `ALTER TABLE` je ruční
krok a nic nehlídá, že proběhl.

**Co s tím:**

1. Rozhodnout, které jméno je správné (`gomes_score_*` v DB je starší), a
   srovnat model s databází — ne naopak, dokud v tabulce nic není.
2. **Zobecnit `tests/test_stock_schema_types.py` na všechny modely.** Ten test
   dnes hlídá jen `Stock`. Táž smyčka přes `Base.registry.mappers` by odhalila
   `price_lines` i všechno další, co se rozejde příště. Je to pár řádků a
   pokrývá celou třídu vad, která už dnes stála jeden výpadek aplikace.
3. Přidat startup kontrolu „model versus `information_schema`" ke schema guardu
   z §1 — ten dnes hlídá jen deník skóre.

---

## 25. Pořadí implementace pro datovou základnu

Vloženo **před** Fázi 1 původního pořadí — bez těchhle kroků nemá 1a odkud brát.

| # | Krok | Proč právě teď | Rozsah |
|---|------|----------------|--------|
| **D0** | Smazat 4 testovací řádky a vyřešit provenienci KUYA.V 1,20/2,00 | vymyšlená pásma nesmí přežít do okamžiku, kdy je engine začne číst | minuty |
| **D0b** | Zavřít `price-lines/import-images` a smazat 6 ne-picků (§20b) | živý endpoint umí zapsat odhady systematicky o +1,2 bodu býčí; tabulky jsou zatím prázdné | minuty |
| **D0c** | Srovnat `PriceLinesModel` s DB a rozšířit schema test na všechny modely (§24b) | celá tabulka je přes ORM nečitelná; táž vada položila 23. 8. `/api/stocks` | hodina |
| **D1** | Rozhodnout o 8 skóre bez pásma (KUYAF 10, OPTX 9, DOW, KRKN, MU, MVIS, STX, TWLO): dohledat zdroj, nebo smazat | dnes to jsou nejsilnější doporučení v aplikaci bez odvoditelného základu | hodina |
| **D2** | Zapojit `tracker_sync` — tabulka, routa, denní úloha, alert na posun linie, UI | dodá bránu č. 4 pro 7 picků; kód je hotový, chybí dráty | jeden zásah |
| **D3** | Válce: 12 čísel ručně, s datem a zdrojem | odemkne bránu č. 2, bez které engine nevydá nic | hodina |
| **D4** | Rubrika válců ze SEC XBRL pro US tickery (návrh, ne zápis) | nahradí D3 u části portfolia a udrží válce živé | plán §2 |
| **D5** | Fáze životního cyklu z přepisů (návrh k potvrzení) | brána č. 3; dnes je v DB jediný řádek a ten je `UNKNOWN` | plán §2 |
| **D6** | Vision čtení DCF předpokladů z `chartUrl` PNG | vysvětlí, PROČ se linie pohnula; nikdy se nezapisuje bez potvrzení | volitelné |
| **D7** | ECOR a SMSI: rozhodnout, čím je nahradit, nebo přiznat trvalé „nevíme" | dvě nejhorší pozice, které nepokrývá žádný zdroj | rozhodnutí |

> [!IMPORTANT]
> **D3 před D4.** Je svůdné počkat na rubriku a nezadávat nic ručně. Jenže
> rubrika je práce na dny, dvanáct čísel je práce na hodinu, a do té doby
> aplikace u každé pozice mlčí. Ruční válce s datem a zdrojem jsou poctivý
> vstup — ne provizorium, které by se muselo omlouvat.

---

## 26. Rozšíření verifikační tabulky

| Co | Očekávané |
|----|-----------|
| tracker vrátí pick s `low > high` | `InsufficientData`, řádek se nezapíše |
| tracker vrátí `price = 0` | cena se ignoruje, pásmo se zapíše |
| pick zmizí z trackeru | pásmo zůstane + označí se datem posledního odečtu, nezmizí tiše |
| pick přehodí OFFICIAL → NOT OFFICIAL | upozornění s nejvyšší prioritou (analytik vystoupil z pozice) |
| skóre bez `green_line` | engine nevydá R/R ani zasloužené, brána skončí na č. 4 |
| válce zadané ručně bez data | odmítnuto — válce bez data nejsou fakt o firmě |
| válce starší než N měsíců | `stale`, nákupní strana neprojde, prodejní ano |
| DCF přečtené z PNG | uloží se jako **návrh** s odkazem na graf, nikdy jako pásmo |
| ticker jen v BI, ne u Gomese (DAIO, IRIX, INFU, RDCM…) | zobrazí se cíl BI, verdikt se nevydá |
| ticker v žádném zdroji (ECOR, SMSI) | „žádná analýza", nikdy neutrální skóre 5 |
| pásmo ze `source="image"` vs. z trackeru pro týž ticker | vyhrává tracker; odhad se nikdy nezapíše přes měřený zdroj |
| import placeholderových pásem | routa neexistuje / 501, ne „úspěšně importováno 20 řádků" |

---

## 27. Open Questions

> [!WARNING]
> **KUYAF 10 a OPTX 9 — smazat, nebo dohledat?**
> Obojí je `BUY_NOW` bez pásma a bez válců. Smazání je bezpečné a ztratí
> informaci, která možná pochází z reálného streamu. Dohledání znamená projít
> přepisy. Co s nimi?

> [!WARNING]
> **Kanadské pozice a SEC.** ITMSF, GKPRF, DBOXF, KUYAF nejsou v EDGAR. Rubrika
> válců pro ně nikdy nevydá návrh, pokud je práh 5 z 10 bodů. SEDAR+ má
> kanadský ekvivalent, ale je to další integrace. Stojí za to, nebo u těch
> čtyř zůstanou válce trvale ruční?

> [!WARNING]
> **ECOR a SMSI.** Ani Gomes, ani BI. SMSI je −93,40 %. Má pro ně vzniknout
> vlastní analýza, nebo je to případ pro rozhodnutí „prodat, protože o tom
> nemám co vědět" — což je samo o sobě legitimní závěr metodiky?

> [!WARNING]
> **Placeholderová pásma: smazat celý soubor, nebo nechat jako fallback?**
> Po zapojení trackeru (D2) je `price_lines_data.py` zbytečný pro 14 z 20
> tickerů a škodlivý pro zbylých 6. Fallback „když tracker nejede, použij
> tohle" zní rozumně, ale znamená, že při výpadku zdroje začne engine počítat
> z odhadů o +1,2 bodu býčích, aniž by to bylo na obrazovce vidět. Smazat celý?

> [!IMPORTANT]
> **Překryv 4/7 s Money Mark Portfolio.** Tři jeho oficiální picky (CXDO,
> GEO.TO, TPCS) v portfoliu nejsou. Má být „není v portfoliu, ale je OFFICIAL"
> vlastní stav na obrazovce, nebo to patří do fronty nových pozic z §4?

---

## 28. Co ani tahle část neslibuje

- **Nezíská válce z webu.** Neexistují tam. Každá cesta k nim je návrh
  k potvrzení, ne měření.
- **Nevysvětlí Gomesovy linie.** DCF předpoklady jsou v PNG a i po přečtení
  vision modelem to zůstane přečtený obrázek, ne datová řada.
- **Nezaručí, že zdroje zůstanou dostupné.** Obě API dnes odpovídají bez
  autentizace na placený produkt. Může to skončit ze dne na den a aplikace
  musí přežít, že skončí — proto na nich nesmí tvrdě viset ani jeden verdikt.
- **Neručí za to, co už v databázi leží.** Tahle část našla tři sady
  vymyšlených čísel (mock analytik, testovací řádky, placeholderová pásma).
  Že nenašla čtvrtou, neznamená, že tam není.
- **Nepokryje ECOR a SMSI.** Osm z dvanácti pozic nemá Gomesovu analýzu a dvě
  nemají žádnou. Ať se napojí cokoli, tenhle zbytek je práce, ne integrace.

---

## 29. Ověřeno živě 24. 8. 2026 — stav D0/D0b/D0c a tři nové drobnosti

Uživatel se ptal, proč portfolio ukazuje N/A skoro všude. Nezávislá kontrola
(mimo tenhle dokument, přímými dotazy na živou DB) potvrdila, že **D0 a D0b
už proběhly**, a doplnila tři menší nálezy, které v dokumentu dosud nebyly:

**D0 hotovo:** `stocks` už neobsahuje MSTY/NVDY/TSLY/XMMO.V. KUYA.V (OTHER,
id 164) má `green_line`/`red_line` = NULL — fabrikovaná 1,20/2,00 zmizela,
pravděpodobně skrze `backend/scripts/clean_fake_stock_lines.py`. Na řádku
zůstává `action_verdict='ACCUMULATE'`, `conviction_score=7` — to je vědomě
ponechaný pozůstatek atrapy (`akcion-ai-analyst-was-a-stub`, rozhodnutí
z 23. 8.), ne nová vada; `pickAnalysis` (viz níže) ho stejně nikdy nevybere,
protože řádek 172 (GOMES, se skóre) má přednost.

**D0b hotovo:** `price_lines_data.py` smazaný (`git status`: `D`), žádná
routa na `import-images` už neexistuje.

**D0c částečně:** `price_lines` má dnes OBĚ sady sloupců
(`gomes_score_at_*` i `conviction_score_at_*`) — ORM tedy dnes nespadne.
Tabulka je stále prázdná (0 řádků), takže nic nehrozí, ale je to obezlička,
ne rozhodnutí; §24b pořád čeká na skutečné sjednocení.

**Nové, mimo dokument:**

1. **`pickAnalysis` (`frontend/src/lib/tickers.ts`) a klíčování `bandByTicker`
   (`InvestmentTerminal.tsx:2887-2890`) už řeší přesně ty dva scénáře, které
   tenhle dokument i nezávislá kontrola samostatně označily za chybějící**
   (GKPRF dostane zelenou/červenou z Gomesova řádku i když skóre vede jinam;
   Pásmo se dohledá přes 4 klíče včetně kanonického tickeru). Soubory jsou
   needocommitované (`??`), poslední úprava 24. 8. 17:18 — pravděpodobně
   rozdělaná práce z týhle větve. Nekontrolovat znovu, jen ověřit při commitu.
2. **Cost basis (`Position.cost_basis`) se počítá a vrací z API, ale
   nevykresluje se nikde na živé obrazovce** — `StockDetail.tsx:668-686` má
   4 MetricCards (počet akcií/průměrná cena/aktuální cena/hodnota pozice),
   páté („Vloženo celkem") chybí. Jednořádková úprava, žádná backend změna.
3. **`unconvertible_positions` (backend/app/routes/portfolio.py:203) se nikdy
   nedostane na frontend** — netypováno, nečteno, nevykresleno. Dnes prázdné
   pro všech 12 pozic (USD/CAD/EUR mají živý kurz), takže se to neprojevuje —
   ale je to přesně to hlášení, které mělo zabránit opakování ILS-za-kurz-USD
   incidentu z `currency.py`, a dnes by šlo do prázdna.
4. **`POST /api/intelligence/analyze-ticker` byl v uplynulých 24h volán
   143× na KUYA.V** (~jednou za 10 minut), pokaždé s LLM odpovědí „no new
   intelligence, keeping existing thesis". Tohle NENÍ atrapa — jde o skutečnou
   LLM-backed cestu z `routes/intelligence_gomes.py`, kterou `akcion-ai-analyst-was-a-stub`
   označuje za legitimní náhradu. Ale desetiminutový interval je řádově
   agresivnější než 12–20h throttling, který si tenhle dokument (§18b)
   vynucuje u riskrewardcharts/BI kvůli stabilitě zdroje. Stojí za rychlou
   kontrolu, jestli je to záměrný scheduler, nebo něco běží v smyčce navíc.

## 30. 🔴 OPRAVA §21 — válce NEJSOU otevřený bod, jsou hotové od 23. 8.

§21 tvrdí „v celé databázi je jeden jediný lifecycle řádek... jedenáct
z dvanácti pozic nemá válce ani fázi." **To bylo pravda ráno 23. 8., ne po
zbytek toho dne.** Ověřeno živě 24. 8.: `stock_lifecycle` má pro všech 12
držených tickerů řádek s `cylinders_confirmed_by='Tomas'`,
`cylinders_confirmed_at` 23. 8. 2026 (dvě vlny, 16:24 a 19:05 UTC), platnost
do 26. 11. 2026 — přes `cylinder_intake.confirm()`, ne ručním odhadem, ale ani
prostým `--confirm` na `propose_cylinders.py` (ten writovat vůbec neumí, jen
tiskne návrh — zápis jde přes samostatný, dosud nedohledaný krok). **D3
z §25 je hotové, škrtnout.**

**Fáze cyklu (`phase`) je odděleně potvrzená pro 7 z 12** (přes
`propose_lifecycle.py --confirm`, běh 24. 8. 08:51 UTC): DBOXF→GOLD_MINE,
IRIX/ITMSF/IZEA/SMSI/VTSI→WAIT_TIME, RDCM→GOLD_MINE. **Zbylých 5 je záměrně
nepotvrzeno** — rubrika sama řekla „posuď sám" a napsala proč (ověřeno živě
24. 8., `propose_lifecycle.py --ticker <X>`, nic nezapsáno):

| Ticker | Proč rubrika nerozhodla |
|--------|--------------------------|
| DAIO | čísla sedí stejně na GOLD_MINE i WAIT_TIME |
| ECOR | cenou vypadá na WAIT_TIME, ale tržby +28 % — definice čekání neplatí |
| GKPRF | čísla sedí stejně na GOLD_MINE i WAIT_TIME |
| INFU | vydělává, ale tržby jen +2,6 % — chybí druhá půlka definice GOLD_MINE (zisk + momentum) |
| KUYAF | sedí stejně na GOLD_MINE i GREAT_FIND, meziroční růst tržeb navíc neznámý |

> [!CAUTION]
> **GKPRF: potvrzené válce (5/10, z Yahoo TTM záporné marže) jdou proti
> Gomesovu vlastnímu videu.** `stock_lifecycle` má i nepotvrzený řádek
> (id 1, `source='gomes_video_2026-08-21'`): doslovná citace *„gatekeeper is
> operating on ten cylinders right now I don't think anybody can deny they
> are operating on all ten cylinders."* Do Buy Guardu ale jde potvrzené číslo
> 5, ne Gomesova 10 — nikdo ten rozpor nikdy nesrovnal, jen tiše vyhrálo to,
> co se potvrdilo jako druhé v pořadí. Buď je Yahoo TTM marže špatný proxy
> pro tohle konkrétní tvrzení (mluví o provozním zdraví, ne o účetní marži
> za poslední rok), nebo Gomes mluví o něčem jiném než rubrika měří — v obou
> případech je to na tobě, ne na automatice.

---

## 31. Rozhodnuto a zapsáno 24. 8. 2026 — žebřík poprvé vydává konkrétní ceny

Tomáš rozhodl pět otevřených fází a spor o GKPRF. Zapsáno přes sankcionované
cesty (`lifecycle_intake.confirm`, `cylinder_intake.confirm`), append-only —
předchozí řádky dostaly `valid_until`, nic se nepřepsalo ani nesmazalo.

| Ticker | Fáze | Proč tak |
|--------|------|----------|
| DAIO | zlatý důl | čísla sedla stejně na obě, vlastník zvolil |
| ECOR | objev | tržby +28 % r/r → čekání neplatí, ale ještě nevydělává |
| INFU | zlatý důl | kladné cash flow; 2,6 % r/r uznáno jako dostatečné momentum |
| KUYAF | objev | pre-produkční Bethania — začíná slibně, nevydělává |
| GKPRF | zlatý důl | + válce **5 → 10** |

**GKPRF: Gomesova desítka vrácena zpět.** Zapsáno se zdrojem
`gomes_video_2026-08-21` (ne `rubric` — `confirm()` má zdroj natvrdo, takže se
opravuje na řádku před commitem, jinak by za rok nikdo nepoznal, odkud číslo
je, a příští rubrikový běh by ho směl tiše přepsat zpátky na 5, přesně jako
23. 8.). `phase_signals.owner_override` nese původní hodnotu, důvod i datum.

**Stav žebříku po zápisu** (ověřeno `portfolio_ladder`, 24. 8. 2026):

| Ticker | Pásmo | R/R | zasloužené | kup ≤ | prodej ≥ |
|--------|-------|-----|-----------|-------|----------|
| VTSI | pod zelenou | 10,00 | 7,00 | 7,28 | 8,46 |
| GSI.V | **NÁKUP** | 4,17 | **0,00** | 3,31 | 3,75 |
| IMP.V | **NÁKUP** | 7,69 | 6,00 | 1,02 | 1,45 |
| IZEA | **NÁKUP** | 8,79 | 7,00 | 3,62 | 4,20 |
| ostatních 8 | mimo metodiku | — | — | — | — |

> [!CAUTION]
> **Deset válců znamená zasloužené = 0, a to je u GKPRF téměř vždy NÁKUP.**
> `zasloužené = 10 − válce`, takže po přepisu je laťka nula a jakékoli kladné
> R/R ji přeskočí — dnes 4,17 > 0. Před přepisem platilo 4,17 ≤ 5,00, tedy
> ODMÍTNUTO. Je to logický důsledek kánonu (dokonalá kvalita snese jakoukoli
> cenu až k červené lince), ne chyba, ale znamená to, že GKPRF bude hlásit
> nákup až do ~3,31 USD při dnešní ceně 1,29. Pokud to není záměr, je oprava
> triviální: potvrdit válce znovu nižším číslem, předchozí řádek zůstává čitelný.

**Osm pozic zůstává „mimo metodiku" a je to správná odpověď** — Gomes pro ně
nevydal zelenou ani červenou linku, takže žádné pásmo neexistuje. To není
N/A z rozbité aplikace, ale pojmenovaná nepřítomnost. Zbývá je odlišit v UI
(§29 bod 2-3) a rozhodnout §27 o ECOR/SMSI.

---

## 32. 🔴 Backend vůbec nestartoval — `routes/intake.py` (nalezeno 24. 8. 2026)

`app/main.py:46` importoval `routes/intake.py`, který dělá
`from ..models.trading import StockLifecycle`. Takový model tam není — je to
`StockLifecycleModel` v `models/gomes.py`, jak ho správně importuje každá
ostatní služba. Protože to viselo na `main.py`, **neimportovala se celá
aplikace**: `python -c "import app.main"` skončil `ImportError` a API
nemohlo nastartovat. Zároveň to shodilo sběr testů (`pytest` hlásil 2 chyby
při collection), takže projektová brána z CLAUDE.md nešla vůbec spustit.

**Vypnuto, ne opraveno — schválně.** Ten soubor nemá jen špatný název modelu.
Zapisuje `lifecycle_phase` přímo z Gemini Flash extrakce, s natvrdo zapsanou
`confidence_score=0.8`, a do sloupců, které na modelu neexistují
(`current_stage`, `stage_entered_date`, `stage_rationale`). Byl psaný proti
schématu, které nikdy neexistovalo. Kdyby se „opravil" jen import, rozjel by
se automat, který obchází `lifecycle_intake.confirm()` — ráčnu i lidské
potvrzení — a sám si autorizuje vstup do brány č. 3, která pouští nákupy.
Táž vada jako `_generate_mock_analysis` (§20b, [[akcion-ai-analyst-was-a-stub]]),
jen na jiném místě. Oprava importu by ji spustila, ne odstranila.

Zapnout až fáze poteče přes návrh k potvrzení, ne přes přímý zápis — tedy
stejnou cestou jako `propose_lifecycle.py`.

**Zbytek testů po vypnutí: 1309 prošlo, 54 přeskočeno, 1 spadl.** Ten jeden
(`test_unvalued_breakout_note.py::test_a_euro_holding_is_converted_before_the_percentage`)
je vada návrhu testu, ne regrese: očekává natvrdo „252 %", ale `_breakout_note`
si bere **živý** kurz přes `CurrencyService.get_rate_to_czk`, takže výsledek
se hýbe s eurem (dnes 253 %). Test bude padat každou chvíli, dokud si kurz
nezafixuje.

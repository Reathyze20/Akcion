# Gomes Methodology — Canonical Reference

**Zdroj:** Mark Gomes ("Money Mark"), článek *"Get Rich On Stocks"* (jeho vlastní psaná metodika).
**Účel tohoto dokumentu:** Jediný zdroj pravdy pro to, co Gomesova metoda SKUTEČNĚ říká — proti kterému
měříme, co appka dělá. Když se kód a tento dokument rozejdou, **vyhrává tento dokument** (je to primární
zdroj přímo od autora, ne přepis z videa z druhé ruky).

> ⚠️ **Kontext dvou zdrojů.** Uživatel sleduje DVA nezávislé zdroje:
> 1. **Mark Gomes** — strukturovaná metodika jednoho analytika (tento dokument = její kánon).
> 2. **Breakout Investors** — Discord komunita traderů (crowd-sourced, více hlasů, žádný psaný kánon).
>
> Tento dokument je kánon POUZE pro Gomese. Breakout Investors nemá pevná pravidla — jeho "signál" je
> konsensus/nesouhlas komunity. Appka je dnes míchá do jednoho `speaker` pole a přepisuje starší verze
> (viz `reath-main-design-*` trust-triage doc). To je samostatná mezera, nesouvisí s věrností Gomesovi.

> ➕ **Doplněk z videa.** `GOMES_VIDEO_ADDENDUM.md` rozebírá Gomesovo video `9PhWx9rzIaU`
> (jeho vlastní kanál, také primární zdroj) a pokrývá témata, o kterých tenhle článek mlčí:
> Gold Mine jako absorpční stav vs. „rough patch“, velikost pozice jako funkce R/R skóre,
> stupně semaforu jako valuace × znalost příčiny, výjimka „getting paid to wait“ ve žluté,
> chase guard a odjištění hedge u dna. Kde se překrývají, vyhrává tenhle dokument.

---

## 1. Jádro doktríny (co Gomes je a co není)

- **"WE INVEST. WE'RE NOT HERE TO TRADE."** — Žádné denní sledování. Pár "oficiálních" tahů za rok.
- **Víc tahů když je trh levný, míň když je drahý.** → Víc peněz v býčím trhu, míň ztrát v medvědím.
- **Není to technická analýza ani day trading.** Gomes to říká explicitně: *"it has almost NOTHING to do
  with technical analysis or day trading!"* Hodnota je ve **fundamentálním ocenění firmy** — STOCK je kus
  COMPANY a každá company má odhadnutelnou VALUE.
- **Gomes je EQUITY ANALYST**, ne broker/poradce. Jeho hrana = 30 let tréninku v oceňování firem.
- **Vše je zdarma, navždy, bez háčků.** Primární účel blogu (dle jeho disclaimeru): získávat kontakty
  s oborovou expertízou pro potvrzení/vyvrácení jeho investičních tezí.

---

## 2. Market Alert System (Semafor) — timing trhu

Alert se **odvozuje z dlouhodobého grafu** (40letý S&P 500), z pozice trhu vůči třem liniím:

| Pozice na 40y grafu | Význam |
|---------------------|--------|
| U horní linie | Výborný čas brát zisky, jít jinam (dlouhé vládní dluhopisy / money market) |
| Pod šedou linií | Bezpečná nákupní zóna (výjimka: Red Alert) |
| U spodní bílé linie | Generační příležitost (jednou za život) |

| Alert | Chování | Hedge / Cash |
|-------|---------|--------------|
| 🟢 **GREEN** | "Own stocks without fear." Velikost pozic řídí Risk/Reward charts. | 0% hedge |
| 🟡 **YELLOW** | Prodej VŠECHNY spekulativní + "Wait Time" akcie. **Zapomeň na 10-point rule.** RAISE CASH (neredeployuj zisky z prodejů u R/R highs). | 20-30% v RWM "je víc než dost" |
| 🟠 **ORANGE** | Mezi Yellow a Red. | *"I have ALL of my cash in RWM."* |
| 🔴 **RED** | Prodej skoro všechno, sázej PROTI trhu. Extrémně vzácné — **jen 2× v životě** (konec 1999, půlka 2007). | Většina peněz v RWM |

**Instrumenty:**
- **BOXX** — money market ETF, kam se parkuje cash (rychle likvidní).
- **RWM** — inverzní Russell 2000 ETF (roste když trh padá; padá když trh roste → nekupovat moc). Toto je "hedge".
- **Mimo USA:** RWM nemusí být dostupné → buď extra vybíravý, drž víc cashe místo hedge.

> Klíč: Cash se **buduje v drahém trhu** (přes prodeje u R/R highs, které se prostě neredeployují), aby
> bylo za co kupovat, až přijde nevyhnutelná korekce. *"You can't buy cheap stocks if you have no cash!!"*

---

## 3. Tři stádia akcie (Lifecycle)

Gomes vybírá **neznámé / neoblíbené / nenáviděné** akcie (jako raný Buffett). Každá projde třemi cykly:

| Stádium | Popis | Akce |
|---------|-------|------|
| **1. Great Find** | Nikdo o ní neslyšel, ale začíná dělat skvělé věci. Být early je profitabilní. | Riskantní, povolené v Green |
| **2. Wait Time** | Hype umřel, story ještě nechytla trakci. Retracuje velkou část Great Find pohybu, trvá dýl než čekáš. | ⚠️ **NEBÝT INVESTOVANÝ** |
| **3. Gold Mine** | Momentum nastartoval, firma profituje / má silné objednávky. | Bezpečné držet dlouhodobě |

---

## 4. Risk/Reward Charts + pravidlo 10 válců (Level 3 — nejdůležitější mechanika)

Gomesovy "Risk/Reward charts" jsou **fundamentální, ne technické** (i když vypadají podobně).
Grafy jsou postavené na DCF ("New DCF" / "Prior DCF" linie), rev CAGR a net margin očekáváních.

- **Green Line** (= "Low") = podhodnoceno → nákupní zóna → **R/R skóre 10**.
- **Red Line** (= "High") = plná valuace → prodejní zóna → **R/R skóre 0**.

### 4a. Přesná matematika R/R skóre — LOGARITMICKÁ, ne lineární

> ⚠️ Ověřeno z live trackeru **riskrewardcharts.com** (2026-07-25, fan-built replika Gomesovy metody;
> tickery sedí na jeho reálné picky — TPCS, GKPRF/GSLV). Appka dnes používá LINEÁRNÍ 30/70 pásma
> (`gomes_logic.py:562-573`), což je **matematicky špatně**. Správně:

```
R/R skóre = 10 × log(High / price) / log(High / Low)      # varianta [10,0]: skóre 10→0
R/R skóre = 1 + 9 × log(High / price) / log(High / Low)   # varianta [10,1]: skóre 10→1
```

- `price ≤ Low` → skóre capnuté na 10 (pod green line, max buy).
- `price ≥ High` → skóre capnuté na 0 (nad red line, full value / sell).
- Potential % Gain = `(High − price) / price`.

**Ověření na live datech (varianta [10,0]):**
| Ticker | Low | High | Cena | R/R skóre | Kontrola |
|--------|-----|------|------|-----------|----------|
| CXDO | 3.25 | 15.50 | 6.62 | 5.45 | 10×log(15.5/6.62)/log(15.5/3.25) = 5.45 ✓ |
| GKPRF | 0.30 | 3.75 | 1.17 | 4.61 | 10×log(3.75/1.17)/log(3.75/0.30) = 4.61 ✓ |

### 4b. Pravidlo 10 válců = zasloužené skóre

Válce = provozní zdraví firmy (0-10; delays/lawsuits/CFO odchod snižují; "firing on all cylinders" = 10).
Článek: *"5 cylinders → stock should only be halfway between green and red; 1 cylinder → near green line."*

Halfway mezi green a red = skóre 5. Tzn. **zasloužené R/R skóre ≈ (10 − cylinders):**

| Válce | Zaslouží dojet k... | Zasloužené R/R skóre |
|-------|---------------------|----------------------|
| 10 | Red Line (plná valuace) | 0 |
| 5 | Půlka | 5 |
| 1 | U Green Line | ~9 |

**Rozhodovací pravidlo (kompletní, obě vrstvy):**
```
current_R/R_score = 10 × log(High / price) / log(High / Low)
deserved_score    = 10 - cylinders

BUY   když current_R/R_score > deserved_score   (levné vzhledem ke kvalitě)
SELL  když current_R/R_score < deserved_score   (drahé vzhledem ke kvalitě)
```
(Pokud čekáme růst válců brzy → impetus koupit v předstihu zasloužené hodnoty.)

---

## 5. Prodejní / take-profit pravidla

- **Take profits u R/R highs** — hlavní zdroj cashe do Yellow/Orange/Red.
- **Doubling / House Money rule** — *"If you doubled your money, sell half."*
- **3-point rule (VYŘEŠENO z trackeru):** pohyb o 3 body na 10-bodové R/R log škále. Přesná cenová matematika:
  ```
  3pt up (take-profit trigger)  = price × (High / Low)^(3 / (10 − topScore))
  3pt down (add trigger)        = price ÷ (High / Low)^(3 / (10 − topScore))
  ```
  Appčino "score klesne o 3 → take profit" je tedy směrově správně; teď máme přesný cenový spouštěč.
- **"10-point rule"** — v Yellow "zapomeň na ni". Nejspíš jen odkaz na celou 10-bodovou R/R škálu (tj. v
  Yellow neřeš R/R skóre jednotlivých akcií, prostě raise cash). Ověřit na streamu, ale záhada z gap-mapy
  #12 je vyřešená: 3-point ≠ jiné pravidlo, je to 3 body na té samé 10-bodové škále.

---

## 6. Position Sizing (velikost pozice podle tieru)

| Tier | Typ | Max % portfolia |
|------|-----|-----------------|
| **Primary (Core)** | Proven Gold Mine | 10% |
| **Secondary** | Great Find, "dating" fáze | menší |
| **Tertiary** | Spekulativní / FOMO | 1-2% |

> **Yellow constraint:** V Yellow Alertu žádné spekulativní (Tertiary) pozice.

---

## 7. Explicitní zákazy (co Gomes říká NEDĚLAT)

1. **Opce — NE.** *"DON'T !!"* Jen pro plně vzdělané. Opakuje 3×.
2. **Nezačínej nákupem VŠECH aktivních picků naráz.** Většina lidí začne, když je trh "hot" → nebezpečné.
3. **Kupuj jen když:** (a) trh je Green Alert A (b) akcie je na atraktivní úrovni dle R/R chartu.
   Jinak se zeptej na streamu nebo počkej na jeho DALŠÍ pick (kup, když kupuje on).
4. **Nedeployuj cash na sílu.** Přebytečná cash → BOXX/money market, ne do trhu.

---

## 8. Zdroje dat (kde metodika žije)

| Zdroj | Detail |
|-------|--------|
| Money Mark Portfolio (spreadsheet) | Oficiální tahy, časově razítkované |
| Stock Talk LIVE (YouTube) | Pátek 14:00 ET — lekce, picky, R/R charts, Q&A |
| R/R charts | Link v popisku streamu; NENÍ real-time (mění se zřídka) |
| WhatsApp komunita | Peer potvrzení |
| StockTwits | `@MasterCap` |
| pipelinedatallc.com | Track record (24 triples / 5 let na Seeking Alpha) |
| **riskrewardcharts.com** | Fan-built live tracker jeho R/R chartů + přesná matematika skóre (viz §4a). Nezveřejňuje API, ale odhaluje low/high/skóre pro každý pick. Disclaimer říká "not affiliated / fictional" (legal cover). |

### 8a. Aktuální picky z trackeru (snapshot 2026-07-25)

Sloupce: Ticker · Low (green) · High (red) · aktuální cena · R/R skóre 10→0. **OFFICIAL** = Money Mark
Portfolio (= appčino portfolio); **NOT OFFICIAL** = watchlist (= appčin watchlist). Mapuje se 1:1 na
appčin split portfolio/watchlist a na `source_type` OFFICIAL vs. ne.

| Ticker | Pick | Low | High | Cena | R/R |
|--------|------|-----|------|------|-----|
| CXDO | OFFICIAL | 3.25 | 15.50 | 6.62 | 5.45 |
| GEO.TO | OFFICIAL | 1.75 | 5.25 | 2.51 | 6.72 |
| GKPRF (GSLV) | OFFICIAL | 0.30 | 3.75 | 1.17 | 4.61 |
| ITMSF | OFFICIAL | 0.30 | 10.00 | 0.69 | 7.62 |
| IZEA | OFFICIAL | 2.50 | 11.00 | 3.40 | 7.92 |
| TPCS | OFFICIAL | 3.25 | 14.00 | 4.56 | 7.68 |
| VTSI | OFFICIAL | 5.00 | 22.50 | 3.18 | 10.00 (pod green) |
| AEHR | NOT OFFICIAL | 8.00 | 60.00 | 76.32 | 0.00 (nad red) |
| AMPL | NOT OFFICIAL | 8.50 | 17.50 | 8.10 | 10.00 |
| CELH | NOT OFFICIAL | 18.00 | 110.00 | 27.12 | 7.74 |
| CURI | NOT OFFICIAL | 3.50 | 12.00 | 2.35 | 10.00 |
| DRSHF | NOT OFFICIAL | 0.15 | 2.00 | 1.49 | 1.14 |
| EVLV | NOT OFFICIAL | 2.50 | 9.00 | 5.24 | 4.22 |
| IDN | NOT OFFICIAL | 2.00 | 25.00 | 3.63 | 7.64 |
| KRKNF | NOT OFFICIAL | 0.45 | 2.50 | 4.32 | 0.00 (nad red) |
| TSSI | NOT OFFICIAL | 4.00 | 21.00 | 9.70 | 4.66 |

> Interval toggle `[10,0]` vs `[10,1]` = jestli top skóre je 0 nebo 1 (viz vzorce §4a). Appka by měla
> nabídnout stejný toggle nebo si vybrat jednu variantu (default `[10,0]`).

---

## 9. GAP MAP — článek vs. současný kód

Legenda: ✅ FAITHFUL (věrné) · 🟡 DRIFT (odchylka/interpretace) · ❌ MISSING (chybí) · ⚠️ CONTRADICTS (v rozporu)

| # | Pravidlo z článku | Stav v kódu | Verdikt |
|---|-------------------|-------------|---------|
| 0 | R/R skóre je LOGARITMICKÉ `10×log(High/price)/log(High/Low)` | `determine_action_zone` používá LINEÁRNÍ pásma 30/70 (`gomes_logic.py:562-573`) | ❌ **MISSING/WRONG** (matematika ověřena z trackeru, viz §4a) |
| 1 | 10-válců škáluje zaslouženou cenu: `deserved_score = 10 − cylinders` | `cylinders_count` se ukládá (`models/gomes.py:119`), ale skóre ho **ignoruje** | ❌ **MISSING** (viz §4b — teď plně specifikováno) |
| 2 | Market timing z 40y S&P valuačního grafu | Alert je **ručně nastavené pole** (`set_market_alert`), žádný výpočet z dlouhodobého indexu | ❌ MISSING (gauge) |
| 3 | Metoda NENÍ technická analýza | Master Signal má "Weinstein Guard" (30 WMA, 15% váhy) = technická analýza | ⚠️ **CONTRADICTS** — Weinstein pilíř není z Gomesova psaného kánonu |
| 4 | Green/Yellow/Orange/Red alokace | `gomes_logic.py:237-242`: Y(75/15/10) O(25/35/40) R(5/45/50). Článek dává jen "Yellow 20-30% RWM"; zbytek je interpretace | 🟡 DRIFT (rozumná, ale ne doslovná) |
| 5 | RWM jako hedge | `hedge_ticker="RWM"` (`gomes_logic.py:274`) | ✅ FAITHFUL |
| 6 | BOXX jako cash parking | Cash je jen abstraktní `cash_pct`, BOXX nikde nemodelováno | ❌ MISSING (minor) |
| 7 | Tři stádia (Great Find/Wait Time/Gold Mine) | `LifecyclePhase` enum + detekce klíčových slov (`gomes_logic.py:312+`) | ✅ FAITHFUL |
| 8 | Yellow = pryč se spekulativními | `get_blocked_tiers` YELLOW blokuje TERTIARY (`gomes_logic.py:298`) | ✅ FAITHFUL |
| 9 | Yellow = pryč i s "Wait Time" akciemi | Yellow blokuje jen tiery, ne držené WAIT_TIME lifecycle pozice | 🟡 DRIFT (částečné) |
| 10 | Opce — NE | Appka opce neřeší | ✅ FAITHFUL (omissí) |
| 11 | Position tiers 10/5-8/1-2% | `PositionSizingEngine` (`gomes_logic.py:582+`) | ✅ FAITHFUL |
| 12 | "3-point rule" = 3 body na 10-bodové R/R škále | Appka má "3-point rule" (score -3 → take profit) — směrově OK, chybí přesná cenová matematika (§5) | ✅ VYŘEŠENO (viz §5) |
| 13 | Doubling / House Money (double → sell half) | Přítomné v docs; ověřit implementaci ve výpočtu signálu | 🟡 VERIFY |
| 14 | Nekupuj všechny picky naráz / jen v Green + atraktivní | Žádný onboarding guard proti nákupu picku u Red Line / mimo Green | ❌ MISSING (feature) |

---

## 10. Prioritizovaný backlog (odvozený z gap-mapy)

Seřazeno dle věrnosti metodice × dopad na rozhodnutí:

1. **[Gap #0+#1] Přepsat R/R skóre na logaritmické + zapojit válce.** Nahradit lineární 30/70 pásma
   (`gomes_logic.py:562-573`) vzorcem `score = 10×log(High/price)/log(High/Low)` a rozhodovat
   `BUY když score > (10 − cylinders)`. Data (green_line, red_line, cylinders_count) už existují.
   → Nejvěrnější Level-3 mechanika, dnes matematicky špatná. Přidat i `3pt up/down` cenové triggery (§5).
2. **[Gap #3] Rozhodnout o Weinstein pilíři.** Buď ho označit jako "vlastní rozšíření (ne Gomes)", snížit
   jeho váhu, nebo odstranit — protože přímo odporuje článku ("not technical analysis").
3. **[Gap #2] Market-alert gauge.** Aspoň asistovaný výpočet alertu z pozice S&P na dlouhodobém
   valuačním grafu, místo čistě ručního pole.
4. **[Gap #14] Onboarding / buy guard.** Varovat při nákupu picku, když (a) alert ≠ Green nebo
   (b) cena je nad deserved position. Přímo z pravidla "jen v Green + atraktivní".
5. **[Gap #9] Yellow force-review Wait Time pozic.** Při Yellow flagnout i držené WAIT_TIME akcie, ne jen
   Tertiary tier.
6. **[Gap #12] Vyjasnit 3-point vs 10-point rule.** Dohledat z "Three Stages" článku / streamu a sjednotit.
7. **[Gap #6] Modelovat BOXX/RWM jako reálné cash/hedge instrumenty**, ne jen procenta.

---

*Vytvořeno z Gomesova psaného článku "Get Rich On Stocks". Když se objeví novější/přesnější zdroj
(např. "Three Stages" článek pro 10-point rule), aktualizuj tento dokument jako první.*

# Efficient Investing Playbook — User Paths & Test Cases

**Kontext / design north star.** Uživatel spravuje reálné rodinné peníze, má **omezenou časovou a
energetickou kapacitu** (proměnlivá energie, období nižší dostupnosti) a **nemá čas**. Cíl ~20 % ročně je
vysoký. Aplikace to **negarantuje** (nikdo nemůže) — její úkol je:

1. **Nulové chyby z appky.** Žádný fake údaj, žádný nezapsaný obchod, žádná špatná matematika. Když se
   něco betuje na reálné peníze, korektnost JE ta funkce.
2. **Vynutit pravidla.** Gomes: *"selective signal following destroys the statistics."* Appka dělá myšlení,
   uživatel jen potvrzuje. Disciplína chrání kapitál víc než výběr picku.
3. **2 minuty na rozhodnutí.** Proměnlivá energie a kognitivní zátěž znamenají, že appka musí rozhodovat
   za uživatele, ne s ním diskutovat. Každá cesta má **časový rozpočet**. Když je co dělat, appka řekne
   přesně co a kolik. Když není, řekne "Nic. Drž." (to je feature).
4. **Přežít nepřítomnost.** V obdobích nižší dostupnosti (nemoc, vytížení, cestování) musí portfolio být
   chráněné i bez denní kontroly.

> Vše navazuje na `GOMES_METHODOLOGY_CANON.md` (pravidla + přesná R/R matematika). Testovací fixtures níže
> používají reálná čísla z trackeru (snapshot 2026-07-25), takže testy = zároveň regrese proti metodice.

---

## ČÁST 1 — User Paths (cesty, seřazené dle četnosti)

Legenda časového rozpočtu: ⏱ = kolik času/interakcí cesta smí maximálně zabrat.

### Path 1 — "Co mám dnes udělat?" (Denní check) ⏱ ≤ 2 min, ≤ 3 akce

Srdce appky. Jedna obrazovka, žádné hledání, žádné počítání.

1. Nahoře **Market Alert semafor** (🟢🟡🟠🔴). Když NENÍ Green → odpověď je skoro vždy "drž cash / nic".
2. **Ranked Action List** — max 1-3 položky. Každá: `TICKER · AKCE · přesná částka · jednořádkové proč`.
   - Př.: `GKPRF · BUY · 12 000 Kč · R/R skóre 8.1 > zasloužené 5 (levné vzhledem ke kvalitě)`
   - Př.: `CXDO · TRIM půl · +154 % (Doubling rule — House Money)`
3. Když není co dělat → velké **"Nic. Drž."** To je správná odpověď většinu dní.

**Acceptance:** obrazovka čitelná na jeden pohled, žádné rozklikávání nutné k rozhodnutí. Akce už obsahuje
částku (uživatel nepočítá). Když chybí data pro rozhodnutí → položka se nezobrazí jako akce, ale jako
"⚠️ chybí data" (nikdy fake číslo).

### Path 2 — "Přišel nový Gomes pick / video" (Zpracovat pick) ⏱ ≤ 5 min

1. Vlož YouTube URL / transkript / paste. AI extrahuje ticker, low/high, cylinders, katalyzátor.
2. Appka rovnou vyhodnotí: **Market Green?** + **R/R skóre > (10 − cylinders)?**
   → `BUY teď` / `WAIT (moc drahé / market není Green)` / `Watchlist`.
3. Uživatel nemusí číst celé video — dostane verdikt + jednu větu proč.

**Acceptance:** verdikt nikdy neřekne BUY, když market ≠ Green nebo cena je nad zasloužené skóre.

### Path 3 — "Provést obchod" (Zapsat co appka řekla) ⏱ ≤ 1 min

Potvrdit BUY/ADD/TRIM/SELL → appka zapíše transakci → pozice + P&L se přepočítá.
> ⚠️ Toto byla rozbitá cesta (trim tlačítko dělalo `console.log`). Musí být neprůstřelné — viz Group E.

### Path 4 — "Alert přepnul na Yellow/Orange/Red" (De-risk) ⏱ ≤ 3 min

Appka vygeneruje **seznam k prodeji** (spekulativní + Wait Time pozice) a cílovou cash/hedge alokaci
(BOXX/RWM). Jedno potvrzení provede celý seznam. Vysvětlí "proč" jednou větou.

**Acceptance:** v Yellow zmizí všechny spekulativní BUY signály; v Red appka blokuje nákupy úplně.

### Path 5 — "Měsíční vklad" (Nasadit novou hotovost) ⏱ ≤ 3 min

Nová hotovost → appka řekne kam (dle gap analýzy a R/R skóre), NEBO "drž v BOXX, nic není atraktivní".
Respektuje pravidlo *"nedeployuj cash na sílu"*.

### Path 6 — "Zdraví portfolia" (Týdenní/měsíční audit) ⏱ ≤ 5 min

Thesis drift alerty? Pozice nad capem (15 %)? Cash runway < 6 měsíců u nějaké firmy? Family audit napříč
portfolii. Jen výjimky, ne zeď dat.

### Path 7 — "Away mode" (Delší nepřítomnost) ⏱ nastavit jednou

**Pojistka pro období nedostupnosti.** Když uživatel nemůže kontrolovat (nemoc, špatné období, cesta):
- Zapne se přísnější režim: tighter stops, "when in doubt raise cash".
- Push (Telegram/email) pošle **jen jeden nejnaléhavější alert**, ne šum.
- Default při nejistotě = chránit kapitál, ne honit zisk.

**Acceptance:** po X týdnech bez přihlášení appka nespadne, data nejsou fake, a poslední známý bezpečný
stav je jasně označen jako "neaktuální od {datum}".

---

## ČÁST 2 — Test Cases (Given / When / Then)

Fixtures = reálné picky z trackeru. Interval `[10,0]` pokud neuvedeno jinak.

### Group A — R/R skóre matematika (musí být PŘESNÉ)

| ID | Given (Low, High, Cena) | When | Then (skóre) |
|----|--------------------------|------|--------------|
| A1 | CXDO 3.25 / 15.50 / 6.62 | vypočti R/R | **5.45** (10×log(15.5/6.62)/log(15.5/3.25)) |
| A2 | GKPRF 0.30 / 3.75 / 1.17 | vypočti R/R | **4.61** |
| A3 | VTSI 5.00 / 22.50 / 3.18 (cena pod Low) | vypočti R/R | **10.00** (cap, ne >10) |
| A4 | AEHR 8.00 / 60.00 / 76.32 (cena nad High) | vypočti R/R | **0.00** (cap, ne <0) |
| A5 | jakýkoli, interval `[10,1]` | vypočti R/R u High | **1.00**, ne 0 |
| A6 | CXDO 3.25 / 15.50 / 6.62 | Potential % Gain | **+134.14 %** ((15.5−6.62)/6.62) |
| A7 | AEHR, cena nad High | Potential % Gain | **záporné** (−21.38 %), zobrazit jako "nad cílem" |
| A8 | Low == High (chybná data) | vypočti R/R | nepadne; vrátí "N/A", ne dělení nulou |

### Group B — Buy/Hold/Sell rozhodnutí (skóre vs zasloužené = 10 − cylinders)

| ID | Given (R/R skóre, cylinders) | Then (verdikt) |
|----|-------------------------------|----------------|
| B1 | skóre 8, cylinders 3 (deserved 7) | 8 > 7 → **BUY** (levné vzhledem ke kvalitě) |
| B2 | skóre 4, cylinders 8 (deserved 2) | 4 > 2 → **BUY/HOLD** (i drahé, ale kvalita to unese) |
| B3 | skóre 3, cylinders 3 (deserved 7) | 3 < 7 → **SELL/TRIM** (drahé na svou kvalitu) |
| B4 | skóre == deserved | **HOLD** |
| B5 | cylinders = null (neznámé) | konzervativně: **neukáže BUY**, označí "chybí kvalita firmy" |

### Group C — Market Alert gating (#1 ochrana kapitálu)

| ID | Given | When | Then |
|----|-------|------|------|
| C1 | Market = RED | pokus o BUY | **zablokováno** (Gatekeeper AVOID/BLOCKED) |
| C2 | Market = YELLOW | pick je spekulativní (Tertiary) | BUY signál **potlačen** |
| C3 | Market = YELLOW | držená WAIT_TIME pozice | flag **"prodat"** (Path 4 seznam) |
| C4 | Market = GREEN, cena nad Red Line | pokus o BUY | **varování** "nad cílem, nekupovat" (onboarding guard) |
| C5 | Market = ORANGE | cílová alokace | většina cash/hedge do RWM (dle §2 canon) |

### Group D — Position sizing / capy

| ID | Given | Then |
|----|-------|------|
| D1 | skóre/conviction 9-10 | target weight 15 % (CORE) |
| D2 | conviction 4 a níž | target 0 % (EXIT) |
| D3 | pokus dokoupit nad 15 % v jedné akcii | **zablokováno** (MAX_POSITION_WEIGHT) |
| D4 | doporučený nákup < MIN_INVESTMENT_CZK (1000) | přeskočit (poplatky) |
| D5 | gap analýza: current 6 %, target 12 % | akce "dokup X Kč do targetu" s přesnou částkou |

### Group E — Trim/Sell persistence (BYLA ROZBITÁ — kritické)

| ID | Given | When | Then |
|----|-------|------|------|
| E1 | pozice 100 ks | trim 40 ks, potvrdit | DB `shares_count` = **60** (reálně zapsáno) |
| E2 | po E1 | refresh / znovu otevřít | pozice ukazuje 60, ne 100 (žádný optimistický fake) |
| E3 | pozice 100 ks | pokus trim 150 ks | **zamítnuto** (nelze prodat víc než držíš) |
| E4 | po trim | P&L a market_value | **přepočítané**, ne stará hodnota |
| E5 | API/DB selže během ukládání | uživatel | vidí **chybu**, ne "úspěch"; pozice nezměněná |

### Group F — Take-profit / 3-point triggery

| ID | Given | Then |
|----|-------|------|
| F1 | pozice, R/R skóre kleslo o 3 body od nákupu | alert **"take profit"** |
| F2 | 3pt up cena | `price × (High/Low)^(3/(10−topScore))` — přesná hodnota |
| F3 | pozice +100 % (zdvojnásobení) | **Doubling rule**: navrhni prodat půl (House Money) |
| F4 | pozice +150 %+ | **Free Ride** signál |

### Group G — Fail-safe / důvěra (nikdy fake číslo)

| ID | Given | Then |
|----|-------|------|
| G1 | cena se načítá ("loading…") | ukázat "—" / "N/A", **nikdy** 0 nebo odhad jako fakt |
| G2 | market cap neznámý | Large Cap warning se **neukáže** (ne fake `isLargeCap`) |
| G3 | Neon DB uspaná / nedostupná | jasná chyba + "poslední známý stav z {datum}", ne prázdno tvářící se jako $0 |
| G4 | API klíč mrtvý (Gemini/Finnhub) | degradovat gracefully, oznámit, neblokovat celou appku |
| G5 | dev SQL endpoint | dostupný **jen** když DEBUG=True |

### Group H — Efektivita / dostupnost (jádro "nemám čas a energii")

| ID | Given | Then |
|----|-------|------|
| H1 | denní check (Path 1) | ≤ 3 akce, čitelné na jednu obrazovku bez scrollu k rozhodnutí |
| H2 | nic k akci | velké "Nic. Drž.", ne prázdná/matoucí obrazovka |
| H3 | akční položka | obsahuje **přesnou částku** (uživatel nepočítá) |
| H4 | ovládání | velké tap targety, klávesové zkratky, vysoký kontrast (dark theme) |
| H5 | X týdnů bez přihlášení (Away mode) | appka funkční, data označená jako neaktuální, žádný fake |
| H6 | naléhavá událost během nepřítomnosti | **jeden** push (Telegram/email), ne šum |

---

## ČÁST 3 — Priorita (co testovat/stavět první, dle rizika × dopadu)

1. **Group E + G** — důvěra. Bez toho se na appku nedá vsadit reálná koruna. (Group E už z části opraveno.)
2. **Group A + B + C** — správná matematika a gating. Toto přímo chrání kapitál a je dnes částečně špatně
   (lineární místo log skóre — viz canon §4a, Gap #0).
3. **Path 1 (denní check) + Group H** — efektivita. Toto řeší "nemám čas a energii".
4. **Path 7 (Away mode)** — pojistka pro období nedostupnosti. Dnes chybí.
5. **Group D + F** — sizing a take-profit. Optimalizace, až základ drží.

> **Realistické očekávání k 20 %.** Appka nezaručí návratnost. Zaručí, že (a) nepřijdeš o peníze kvůli
> chybě appky, (b) neudělas nákup, který pravidla zakazují, a (c) každé rozhodnutí zabere minuty ne hodiny.
> To je nejlepší, co technologie pro tvůj cíl může udělat — zbytek je disciplína a trpělivost.

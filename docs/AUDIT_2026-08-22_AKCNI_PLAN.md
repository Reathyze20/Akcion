# Audit 22. 8. 2026 — co s tím

Krátká verze. Plné znění všech 106 nálezů: [AUDIT_2026-08-22.md](AUDIT_2026-08-22.md).

**Ověřeno:** 56 potvrzených nálezů (každý prošel agentem, jehož úkolem bylo ho vyvrátit — nevyvrátil).
Z toho **8× P0** (ohrožuje peníze) a **17× P1** (blokuje misi). Kotvy platí ke commitu `8e32c1d`.

---

## Nejdůležitější věta celého auditu

> **Nosná čísla Gomesovy metody — green / red / grey line — se vymýšlejí z aktuální ceny.**

[prompts_enterprise_v2.py:130](../backend/app/core/prompts_enterprise_v2.py#L130) instruuje model:
`green_line = current_price * 0.80`, `red_line = current_price * 1.50`, `grey_line = current_price * 0.65`,
a k tomu **„NIKDY nenechávej null — vždy poskytni odhad"**. Totéž pak podruhé v kódu na
[gomes_deep_dd.py:306](../backend/app/services/gomes_deep_dd.py#L306).

Proč je to nejhorší nález: z těch tří čísel se počítá **úplně všechno ostatní** — logaritmické R/R skóre,
zasloužené skóre podle válců, 3-bodové pravidlo, buy guard. Když jsou vymyšlená z ceny, celá metodika
počítá nad fikcí a výsledek vypadá stejně důvěryhodně jako pravda. Je to přesný opak pravidla
*„nikdy nefakeuj číslo, když data chybí"*.

---

## Pořadí oprav

Řazeno podle (riziko pro kapitál × jak rychle to jde spravit), ne podle závažnosti.

### 1. Tlačítka, která nic nedělají — znovu

- **Buy a Sell v obchodním modálu jsou `console.log` no-opy** — [StockDetail.tsx:183](../frontend/src/components/StockDetail.tsx#L183)
- **Semafor trhu v tom samém modálu je vždycky GREEN** — [StockDetail.tsx:83](../frontend/src/components/StockDetail.tsx#L83)
  má `marketAlert = 'GREEN'` jako výchozí hodnotu propu a **ani jedno ze dvou míst, která modál vykreslují,
  ji nepřepisuje** ([InvestmentTerminal.tsx:4615](../frontend/src/components/InvestmentTerminal.tsx#L4615),
  [PortfolioView.tsx:405](../frontend/src/components/PortfolioView.tsx#L405)). Blok nákupu na RED marketu
  v [TradingDeck.tsx:56](../frontend/src/components/stock-detail/TradingDeck.tsx#L56) tím pádem
  **nemůže nikdy zafungovat** — ta větev je nedosažitelná.

Modál je **živý** — vykresluje se ze dvou míst (viz odkazy výše), není to mrtvý kód.
Je to stejná třída chyby, kterou jsme opravovali v červenci (commit `c21462b`, trim tlačítko);
vrátila se na jiném místě. **Oprava na hodinu, bere největší riziko.**

*(Obojí ověřeno ručně 22. 8., nejen agentem.)*

### 2. Vymyšlené cenové linie

Smazat `*0.80 / *1.50 / *0.65` defaulty z promptu i z kódu, nechat `null`, a v UI vykreslit
`⚠️ chybí — doplň z R/R chartu`. Viz nález výše.

### 3. Analýza je mrtvá od června

- **`gemini-2.0-flash` byl vyřazen 1. 6. 2026** — [constants.py:143](../backend/app/core/constants.py#L143).
  Funkce „Analyzovat" nefunguje **~12 týdnů**.
- **Analýza spadne na `AttributeError` až POTOM, co zapíše nové conviction skóre do DB** —
  [gomes_deep_dd.py:508](../backend/app/services/gomes_deep_dd.py#L508). Uvidíš „analýza selhala",
  ale databáze už je změněná.
- Health endpoint hlásí ještě jiný, taky neexistující model, a inzeruje `google_search`, který je vypnutý.

### 4. Ceny lžou o svém stáří

- **Neúspěšné stažení z Yahoo se zapíše jako ÚSPĚCH** a stará cena dostane razítko „teď" —
  [yahoo_cache.py:132](../backend/app/services/yahoo_cache.py#L132) + [market_data.py:560](../backend/app/services/market_data.py#L560).
  Tím se **trvale vyřadí jediná pojistka proti starým datům**. Když budeš týden mimo, appka bude
  týden starou cenu tvrdit jako aktuální.
- **Massive/Polygon vrací včerejší close** a Finnhub potichu dosadí předchozí close místo chybějící kotace —
  obojí se předá dál jako „současná cena" — [market_data.py:120](../backend/app/services/market_data.py#L120)
- **Kurzy měn se vymýšlejí** a jsou dnes o 9–15 % vedle; neznámá měna dostane potichu kurz USD —
  [currency.py:43](../backend/app/services/currency.py#L43)

### 5. Emoční brzdy fakticky neexistují

Tohle je ta funkce, kvůli které appka vzniká — a v běžícím kódu není.

- **Jediná dosažitelná cesta k nákupu nemá žádnou brzdu.** Při přidání pozice neproběhne ani řádek
  Gomesovy logiky — [InvestmentTerminal.tsx:2270](../frontend/src/components/InvestmentTerminal.tsx#L2270)
- **Buy Guard v cestě 2 selže vždycky:** `generate_verdict()` nikdy nepředá `cylinders_count`,
  takže BUY verdikt nemůže vzniknout — [gomes_intelligence.py:465](../backend/app/services/gomes_intelligence.py#L465)
- Oba „jističe" jsou mrtvý kód — žádný klient je nikdy nezavolal.
- **Neexistuje kniha obchodů**, takže cooldown po ztrátě ani detekce revenge-tradingu nejdou postavit.
- Sloupec `emotion_tag` v DB existuje a **nikdo do něj nikdy nezapsal** — [portfolio.py:346](../backend/app/models/portfolio.py#L346)

### 6. Bez tebe neběží nic

- **Scheduler běží každých 30 minut a nemůže nic odeslat** — na tomhle stroji nejde zkonstruovat
  ani jeden notifikační kanál — [notifications.py:291](../backend/app/services/notifications.py#L291)
- **`EmailChannel._format_html` spadne při každém volání** (neplatný format spec ve f-stringu) —
  [notifications.py:185](../backend/app/services/notifications.py#L185). Takže i po opravě přihlašovacích
  údajů by e-mail nefungoval.
- Dva paralelní notifikační stacky: ten správně nakonfigurovaný nemá automatiku, ten s automatikou nemá konfiguraci.
- **Away mode neexistuje v žádné podobě.** Scheduler žije uvnitř ručně spuštěného localhost procesu —
  zavřeš appku, skončí všechno.

---

## Co audit *nenašel* jako rozbité

Aby to nevyznělo hůř, než to je:

- Logaritmické R/R skóre a válce jsou **správně** implementované a otestované (canon §4a).
- 3-bodové pravidlo je implementované, otestované — jen ho nikdo nevolá.
- Daily Action engine včetně „Nic. Drž." funguje a je pokrytý testy.
- Poctivý import z brokera (Degiro `avg_cost = NULL` místo vymyšlené ceny) drží.
- Dvouzdrojová atribuce Gomes / Breakout Investors funguje.

Problém není metodika ani jádro. Problém je, že **velká část toho jádra není zapojená do ničeho,
co uživatel vidí** — a to, co vidí, na několika místech ukazuje vymyšlená čísla.

---

## Poznámka k ceně tohohle auditu

104 agentů, 18 MB transkriptů, ~22 minut. Neúměrně mnoho — fan-out neměl strop a agenti opakovaně
načítali `InvestmentTerminal.tsx` (261 KB). Klíčový nález (appka nechodí na internet a health endpoint
o tom lže) se našel třemi grepy mimo workflow. **Příště: jeden agent na oblast, strop na počet verifikací.**

Ze 106 surových nálezů bylo 19 z 75 ověřených vyvráceno — **25 % falešných poplachů.**
Proto se sekce *Neověřeno* v plném dokumentu nedá brát jako fakta.

# Kanadské firmy: čísla, na která SEC nedosáhne

Čtyři pozice podávají v Kanadě, takže **54 % portfolia je mimo SEC EDGAR**
([BACKLOG.md B16](BACKLOG.md)). Rubrika válců pro ně neměla ani jeden tvrdý
údaj z podání a spadala na roční souhrny z Yahoo, uzamčené do 3-7 se střední
jistotou ([`cylinders.py`](../backend/app/services/cylinders.py)) — a
`IMPLEMENTATION_PLAN.md` §295 se ptá, jestli kvůli tomu snížit práh, smířit se
s trvalým `NEZNÁMÉ`, nebo najít zdroj. Tohle je ten zdroj.

**Odkud:** vlastní čtvrtletní tisková zpráva firmy, stažená přes Firecrawl
([`services/firecrawl.py`](../backend/app/services/firecrawl.py),
[`scripts/firecrawl_fetch.py`](../backend/scripts/firecrawl_fetch.py)).
Stránky leží v `backend/data/firecrawl/pages/` (mimo git), účetní kniha
kreditů v `backend/data/firecrawl/ledger.json`.

**Cena zjištění:** 10 kreditů z 1000 — čtyři mapy domén po jednom kreditu,
pět stránek po jednom. Jedna tisková zpráva nese kvartál i meziroční
srovnání, takže na jednu firmu stačí jedna stránka.

---

## Čeho se u těchhle čísel držet

1. **Je to firemní tvrzení, ne auditovaný výkaz.** Tiskovka je výběr, který
   firma udělala sama. Patří jí vlastní vrstva se svým stropem jistoty — nikdy
   `SEC_XBRL`.
2. **Měna není u tří ze čtyř v textu vůbec uvedená.** Explicitně ji píše jen
   Gatekeeper („Canadian dollars"). U D-BOXu, Intermapu a Kuya Silveru je `$`
   bez určení. Než jakékoli číslo vstoupí do DB, měna se musí potvrdit z výkazu
   — tohle je přesně ta past, která už jednou proběhla u ILS/USD.
3. **Provozní cash flow a počet akcií v tiskovkách nejsou.** U žádné ze čtyř.
   Takže **runway a ředění zůstávají neznámé** a nesmí se dopočítat z toho, co
   tu je. Rubrika je má nechat prázdné.
4. **Čtvrtletí a fiskální rok se nekryjí.** D-BOX FY končí v březnu, Gatekeeper
   v srpnu (FQ3 skončilo 31. 5. 2026). „Q3 2026" u D-BOXu znamená kvartál do
   31. 12. 2025 — o osm měsíců starší než Gatekeeperovo „FQ3 2026".

---

## DBOXF — D-BOX Technologies

**Q3 FY2026, kvartál končící 31. 12. 2025** · zveřejněno 10. 2. 2026 ·
[zdroj](https://www.d-box.com/en/news/d-box-news-d-box-technologies-reports-third-quarter-2026-results)

| Údaj | Hodnota | Meziročně |
|---|---|---|
| Tržby celkem | 13,8 M | **+4 %** |
| Royalty | 3,1 M | −3 % (z 3,2 M) |
| Prodej systémů do kin | 5,8 M | +21 % |
| Hrubá marže (9 měsíců) | 54 % | +2 p.b. (z 52 %) |
| Upravená EBITDA | 3,4 M (marže 24 %) | +31 % |
| Hotovost | 16,2 M | +3 M |
| **Aktivní sály** | **1 135** | **+12,8 %** |

- Čistý zisk 9,1 M je **zavádějící**: 6,4 M z toho je odložená daňová pohledávka
  (uznané dřívější ztráty), ne provozní výsledek. Zisk před daní byl 2,7 M.
- 86 hrubých instalací za kvartál = rekord, ale čistý přírůstek 51, protože
  35 sálů mimo Severní Ameriku firma deaktivovala jako tři roky nečinné.
- Pokles royalt firma vysvětluje severoamerickým box office −6,9 % a menším
  podílem blockbusterů.

> **Vazba na WhatsApp výtažek 18.–19. 8.** Brad odhaduje počet sálů proxy
> metodou („penetration averages by movie type") a sám říká, že to má ověřené
> jen na jednom kvartálu. **Firma to číslo zveřejňuje sama** — 1 135 aktivních
> sálů, +12,8 % meziročně. Viz [whatsapp/2026-08-18_19.md](whatsapp/2026-08-18_19.md).

## GKPRF — Gatekeeper Systems

**FQ3 2026, kvartál končící 31. 5. 2026** · měna: **CAD (uvedeno v textu)** ·
[zdroj](https://www.gatekeeper-systems.com/gatekeeper-reports-record-fq3-2026-results-with-12-5m-revenue-68-growth-and-2-4m-adjusted-ebitdagatekeeper-announces-c19-million-septa-transit-video-services-contract-over-5-years-2)

| Údaj | Hodnota | Meziročně |
|---|---|---|
| Tržby (kvartál) | 12,5 M | **+68 %** (rekord) |
| Hrubá marže (kvartál) | 53 % | +4 p.b. (ze 49 %) |
| Hrubá marže (9 měsíců) | 48 % | +4 p.b. (ze 44 %) |
| Upravená EBITDA | 2,4 M | z 0,2 M |
| Hotovost | 7,2 M | — |
| Pracovní kapitál | 37,5 M | — |
| Zásoby | 17,4 M | **z 5,2 M** |
| Dluh | žádný | — |

- Nové zakázky za fiskální rok ~73 M, z toho 14 M už zaúčtováno jako tržby.
- **Zásoby vyskočily z 5,2 M na 17,4 M.** Firma to podává jako přípravu na
  zakázky. Je to zároveň hotovost vázaná ve skladu, u firmy se 7,2 M v hotovosti.
  Bez cash flow výkazu se nedá říct, která interpretace platí.

## ITMSF — Intermap Technologies

**Q1 2026, kvartál končící 31. 3. 2026** · zveřejněno 13. 5. 2026 ·
[zdroj](https://www.intermap.com/pressreleases/2026/05/intermap-reports-first-quarter-2026-results)

| Údaj | Hodnota |
|---|---|
| Tržby celkem | **1,4 M** |
| Z toho opakované (subscription + data) | > 80 % |
| Hotovost | ~18,8 M |
| Pracovní kapitál | ~16,3 M |
| Potvrzený výhled na rok | **30–35 M tržeb, 28% EBITDA marže** |

> **Tohle je největší nález z celé dávky.** Firma potvrzuje roční výhled
> 30–35 M a za první kvartál vykázala **1,4 M — tedy 4 % z něj**. Aby výhled
> platil, musí zbylá tři čtvrtletí přinést zhruba 29–34 M. Firma to vysvětluje
> časováním velkých vládních zakázek (Indonésie, americký federál), ne poptávkou.
> Ať už je vysvětlení pravdivé, nebo ne, **je to teze stojící a padající na
> konverzi jedné zakázkové roury** — a appka o tom dosud nevěděla nic.

- „Near break-even" platí až po vyloučení odkupu ředících cenných papírů,
  kurzových vlivů a časového rozlišení tržeb. Nevyloučeno to není break-even.

## KUYAF — Kuya Silver

**H1 2026, šest měsíců končících 30. 6. 2026** · zveřejněno 17. 8. 2026 ·
[zdroj](https://kuyasilver.com/news/news/2026-news/kuya-silver-reports-q2-2026-financial-results---advances-be2026-08-17-040502)

| Údaj | Hodnota | Meziročně |
|---|---|---|
| Tržby (6 měsíců) | 2,7 M | **z 1,3 M** |
| Tržby (Q2 samotný) | 1,25 M | — |
| Čistá ztráta (6 měsíců) | **2,8 M** | z 1,35 M |
| Hotovost | 25,5 M | — |
| Průzkum a vyhodnocení | 1,0 M | — |

- Tržby se víc než zdvojnásobily (vyšší produkce v Bethanii + vyšší cena
  stříbra), ale **ztráta se zdvojnásobila taky**. Je to důlní firma ve fázi
  rozjezdu — hotovost 25,5 M proti půlroční ztrátě 2,8 M je zatím pohodlná,
  ale rampa na 350 t/den se z tiskovky nedá ocenit.
- Kuya vykazuje **pololetně, ne čtvrtletně.** Meziroční srovnání jednoho
  kvartálu z toho nejde.

---

## Co z toho zatím NESMÍ do enginu

- Žádné z čísel, dokud není potvrzená **měna** (bod 2 nahoře).
- **Runway ani ředění** u žádné ze čtyř — vstupy pro ně v tiskovkách nejsou.
- Intermapův výhled 30–35 M jako fundament. Je to **tvrzení firmy o budoucnosti**,
  ne výsledek. Do appky patří nanejvýš jako teze s datem a citací.
- D-BOXův čistý zisk 9,1 M. Vstupem je 2,7 M před daní; 6,4 M je účetní.

## Jak to zopakovat příští kvartál

```
cd backend
python scripts/firecrawl_fetch.py ledger                 # zdarma
python scripts/firecrawl_fetch.py map --ticker GKPRF ... # 1 kredit, pak z cache
python scripts/firecrawl_fetch.py fetch <url>            # 1 kredit za novou stránku
```

Mapa domény se kešuje, takže hledání v už zmapovaném webu je zdarma. Čtyři
firmy jednou za kvartál = **4 kredity**. Při 990 zbývajících to vystačí na
roky, pokud se nikdy nepustí plošný crawl.

---

## Co z toho vyšlo v rubrice (25. 8. 2026)

Tiskovky jsou zapojené jako vlastní vrstva `RELEASE` v
[`cylinders.py`](../backend/app/services/cylinders.py) — nad Yahoo, pod
podáním u SEC. Pásmo 2–8 a jistota vždy nejvýš **střední**: tiskovka neuvádí
provozní cash flow ani počet akcií, tedy dvě věci, které mikrokapku zabíjejí,
takže se z ní firma nesmí označit za výbornou. Dolní hranice je naopak nižší
než u Yahoo — kdo je uvěřitelný v dobré zprávě, musí umět doručit i špatnou.

| Ticker | Válce potvrzené | Návrh z tiskovky | Zasloužené (10−válce) | R/R | Brána | Strop pozice |
|---|---|---|---|---|---|---|
| **GKPRF** | 10 | **8** | 2,0 | 4,04 | NÁKUP | 7 % |
| **ITMSF** | 4 | 4 (Yahoo) | 6,0 | 7,43 | NÁKUP | 7 % |
| **DBOXF** | 7 | **6** | 4,0 | chybí pásmo | mimo metodiku | — |
| **KUYAF** | 4 | **6** | 4,0 | chybí pásmo | mimo metodiku | — |

**Strop 7 %, ne 15 %, u obou nakupovatelných.** Dvojí zdroj vyžaduje napsaný
názor pojmenovaného analytika z rosteru, a `breakout_lookup` čte jen řádky
`WHERE speaker IS NOT NULL`. Všech 14 nedávných záznamů v `ticker_mentions`
pro tyhle čtyři tickery má `speaker` i `source_key` prázdné, takže se
zahazují. Dokud u nich nebude jméno, 15 % je nedosažitelných.

### Nejcennější jediná změna: GKPRF

Potvrzené válce 10 dávají zasloužené skóre **0,00**, což znamená „NÁKUP vždy" —
laťka, kterou nelze podlézt. Tiskovka na to má vlastní důkazy (tržby +68 %,
marže +4 p.b., kladná EBITDA) a vydá **8**, tedy laťku **2,0**. Nákup projde
i tak (4,04 > 2,0), ale poprvé projde *proti něčemu*.

### Nejvážnější rozpor: ITMSF

Rubrika i pásmo říkají NÁKUP: R/R 7,43 proti zaslouženému 6,0, cena 0,74 proti
červené lince 10,00. Tiskovka ale říká, že za Q1 přišlo **1,4 M z potvrzeného
ročního výhledu 30–35 M**. Rubrika to nemá jak vyjádřit — výhled není jejím
vstupem a být jím nemá, je to tvrzení o budoucnosti. **Takže tohle je jediné
místo, kde nová data mluví proti tomu, co appka ukazuje**, a nese to člověk,
ne engine: buď to patří do hlídání teze, nebo válce potvrdit ručně níž než 4.

---

## RDCM přidán 25. 8. 2026 — a je to nejhorší nález z celé série

RADCOM není kanadský, ale trpí tím samým: je to `FOREIGN_PRIVATE_ISSUER`, takže
EDGAR o něm má **osm podání, která jsou krycí listy**. Čísla sedí v příloze
`EX-99.1`, kterou appka nestahuje. Přitom je to **10,2 % portfolia** a nemá
pásmo, takže o něm metodika neuměla říct nic.

**Q2 2026 (kvartál do 30. 6. 2026, zveřejněno 12. 8. 2026)** ·
měna neuvedena ·
[zdroj](https://radcom.com/latest-news/radcom-reports-second-quarter-2026-results)

| Údaj | Q2 2026 | Q2 2025 |
|---|---|---|
| Tržby | **11,8 M** | 17,7 M (**−33,4 %**) |
| Provozní marže (GAAP) | **−31,9 %** | +9,9 % (**−41,8 p.b.**) |
| Čistý výsledek (GAAP) | ztráta 3,1 M (−0,18 /akcii) | zisk 2,4 M (+0,15) |
| Hotovost a krátkodobé vklady | **109,7 M**, žádný dluh | — |

Za půl roku je to mírnější: tržby 30,3 M proti 34,2 M, tedy −11,4 %. **Propad
je soustředěný do jednoho kvartálu.**

**Rubrika navrhuje 2/10 válců** (potvrzeno je dnes 6). Tržby −2, marže −1,
ztráta −1, rozvaha +1, insideři −1 (2× prodej na trhu za půl roku, ani jeden
nákup). Zasloužené skóre by bylo 8,0.

> **Co rubrika nevidí a člověk musí.** Firma to podává jako *zpoždění*, ne
> ztrátu poptávky: „higher component costs and supply constraints slowed the
> buildout". Po konci kvartálu podepsala **tři kontrakty** — CETIN Networks na
> Slovensku, nový Tier-1 v Asii vyhraný na úkor zavedeného dodavatele,
> a prodloužení v Evropě. Výhled na rok nezměnila a mluví o návratu
> k dvoucifernému růstu v 2027. K tomu 109,7 M hotovosti, žádný dluh a vedení
> zakládá **zpětný odkup za 20–25 M**.
>
> Číslo říká „špatný kvartál". Kontext říká „možná načasování". Tenhle rozpor
> rubrika rozhodnout neumí a nemá — rozhoduje ho Tomáš.

Tiskovka píše „Cash flow in the second quarter of 2026 was $1.3 million" —
kladné, ale **bez upřesnění, jestli provozní**. Proto se to nezapsalo jako
provozní cash flow a runway se z toho nepočítá.

### Dvě čtení přidaná kvůli RDCM

- **Provozní marže** jako náhrada, když firma nezveřejní hrubou. Vždy jen jedna
  marže — hrubá má přednost, jinak by se stejný pohyb počítal dvakrát.
- **Rozvaha** (hotovost proti dluhu) jako porovnání, ne částka, takže přežije
  neuvedenou měnu. Špatný kvartál u firmy bez dluhu se stovkou milionů
  v hotovosti je jiná věc než ten samý kvartál u firmy financované věřitelem.

### Stav po této dávce

| Ticker | Váha | Vrstva | Válce navrhované | Válce potvrzené |
|---|---|---|---|---|
| DBO.TO | 19,6 % | RELEASE | 6 | 7 |
| GSI.V | 16,1 % | RELEASE | **8** | 10 |
| RDCM | 10,2 % | RELEASE | **2** | 6 |
| KUYA.V | 9,7 % | RELEASE | **6** | 4 |
| IMP.V | 7,5 % | YAHOO_TTM | 4 | 4 |

Zbylých sedm pozic (INFU, DAIO, IRIX, IZEA, VTSI, SMSI, ECOR) jsou plnohodnotní
plátci u SEC se čtyřmi podáními každý — tam Firecrawl nemá co přidat a kredity
by se utratily za data, která jsou zdarma v EDGARu.

**Datum výsledků chybí už jen u dvou:** GKPRF a KUYAF. U ostatních deseti ho
Yahoo zná. Gatekeeper podle zmapovaného webu žádné avízo „to report on…"
nevydává, takže se to nedá koupit stránkou — buď odhad z kadence (FQ3 do 31. 5.
hlásil 21. 7., tedy zhruba sedm týdnů po konci kvartálu), nebo zůstane prázdné.

---

## Datum výsledků z vlastních stránek firem (25. 8. 2026)

Gatekeeper a Kuya byly poslední dvě pozice, u kterých appka hlásila „datum
výsledků nezná ani poskytovatel, ani kadence podání". Obě to na svém webu mají,
každá jinak:

- **Gatekeeper** má na [IR stránce](https://www.gatekeeper-systems.com/investors/financial-reports)
  celý archiv výkazů a MD&A jako PDF. Cesta k souboru nese měsíc nahrání, takže
  z osmi let jde vyčíst kadence: **Q1 leden, Q2 duben, Q3 červenec, Q4/roční
  prosinec** — a to platí každý rok od 2019. Den firma neuvádí.
- **Kuya** nese datum zveřejnění přímo v adrese tiskové zprávy, tedy **na den**:
  Q2 2025 → 2. 9. 2025, Q3 2025 → 21. 11. 2025, Q1 2026 → 27. 5. 2026,
  Q2 2026 → 17. 8. 2026.

Vznikla z toho třetí úroveň odhadu, `RELEASE_CADENCE`
([`earnings_calendar.py`](../backend/app/services/earnings_calendar.py)), pod
oznámeným datem od poskytovatele a pod kadencí podání u SEC. Dvě věci na ní
stojí:

**Není to průměr mezer.** Gatekeeperovi trvá čtvrtý kvartál pět měsíců
a ostatní tři měsíce. Median by roční zprávu položil do října a blackout by
začal o dva měsíce dřív, než má. Vzorec, který skutečně drží, je **měsíc v roce**.

**Přesnost se nevymýšlí.** U Gatekeepera je odpověď celý měsíc (1.–31. 12.),
protože zdroj den nezná. U Kuyi je to den ± čtrnáct dní. A odhad nikdy nesmí
projít jako oznámené datum — `confirmed=False` a v poznámce stojí „Není to
oznámené datum."

**Ochrana proti vlastní pasti:** odhad musí ležet aspoň 60 dní po posledním
skutečném zveřejnění. Bez toho by Kuya po zprávě ze 17. 8. 2026 dostala
„výsledky za dva týdny", protože loňské Q2 vyšlo 2. 9. — tedy výročí zprávy,
která už je venku.

### Výsledek: všech 12 pozic má poprvé datum

| Ticker | Datum | Okno do | Dní | Zdroj |
|---|---|---|---|---|
| DAIO | 29. 9. 2026 | — | 35 | kadence podání |
| INFU | 3. 11. 2026 | — | 70 | poskytovatel |
| ECOR, SMSI | 4. 11. 2026 | — | 71 | poskytovatel |
| VTSI | 9. 11. 2026 | — | 76 | poskytovatel |
| RDCM, DBOXF, IZEA | 11. 11. 2026 | — | 78 | poskytovatel |
| ITMSF | 12. 11. 2026 | — | 79 | poskytovatel |
| IRIX | 17. 11. 2026 | — | 84 | poskytovatel |
| **KUYAF** | **21. 11. 2026** | 5. 12. | 88 | **vlastní historie** |
| **GKPRF** | **1. 12. 2026** | 31. 12. | 98 | **vlastní historie** |

Praktický důsledek: **žádná pozice není v čtrnáctidenním blackoutu** a nejbližší
print je DAIO za 35 dní. U GKPRF to bylo potřeba vědět nejvíc — je to jedna ze
dvou pozic, které dnes projdou branou, a do teď se u ní blackout neměl o co
opřít.

---

## Sloupec „Výsledky" v portfoliu i ve sledovaných (25. 8. 2026)

Odpočet do nejbližších výsledků je teď sloupec v obou tabulkách. Text píše
backend ([`earnings_lookup.py`](../backend/app/services/earnings_lookup.py)),
kreslí ho jedna sdílená komponenta `EarningsCell` — ta samá otázka se ve dvou
tabulkách nesmí čtvrtletně rozejít.

**Odhad to řekne v buňce, ne až v tooltipu.** „za 78 dní" je oznámené datum,
**„asi za 98 dní"** je vzorec odvozený z vlastní historie zveřejňování firmy.
Sloupec holých čísel se čte jako sloupec faktů, a dvě z dvanácti pozic mají
datum, které nikdo neoznámil.

**Blackout počítá backend, ne prohlížeč.** Je to týchž čtrnáct dnů, ve kterých
`GomesGatekeeper` odmítá nákupy. Kdyby si je počítal frontend, mohla by tabulka
tvrdit něco jiného než brána.

**Chybějící datum je pomlčka, ne nula.** Nula by se četla jako „vykazuje dnes".

### Dvě vady, které se při tom našly

- **Kalendář kladl tabulku pozic.** Chybějící tabulka `earnings_dates` shodila
  celý přehled portfolia přes `OperationalError`. Odpočet je ozdoba, peníze
  jsou obsah — `badges()` teď selhání zaloguje a vrátí prázdno, stejné pravidlo
  jako `unvalued_findings`.
- **Poskytovatel vracel data v minulosti.** U čtyř sledovaných (AISP, CELH,
  MVIS, DFSC) vracel Yahoo minulý kvartál týdny po termínu. Modul má vlastní
  pravidlo „datum tři měsíce staré je horší než žádné, protože vypadá jako
  odpověď", ale platilo jen pro odhad z kadence. `_first_future` ho teď
  uplatňuje na všechny tři úrovně; okno, které ještě běží, se počítá jako
  budoucnost.

### Pokrytí

**Portfolio 12/12**, sledované **48/55**. Kalendář se dosud plnil jen pro
držené pozice — po obnově pro celý seznam má datum 31 z 38 firem, žádné
v minulosti. Nejbližší print v portfoliu je DAIO za 35 dní, žádná pozice není
v blackoutu; ve sledovaných jsou v blackoutu KRKNF a 0777.HK.

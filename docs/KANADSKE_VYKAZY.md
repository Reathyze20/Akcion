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

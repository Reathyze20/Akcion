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

### `[x]` B7. Away mode neexistuje

Ani v jedné podobě. Scheduler žil uvnitř ručně spuštěného localhost procesu — zavřel jsi appku,
skončilo všechno. Přitom je to ta funkce, kterou při relapsu potřebuješ nejvíc: utaženější stopy,
default na raise cash, **jeden** nejnaléhavější push místo šumu, a stará data viditelně označená.

**Hotovo (23. 8.):**

- `app/services/away_mode.py` — čistá pravidla, bez DB a HTTP:
  - **Cestuje jen to, co chrání kapitál.** BUY se v away mode neposílá nikdy. Promeškaný nákup
    stojí příležitost, promeškaný prodej peníze, které už máš.
  - **Nic akční se nestaví na datech starších dvou dnů.** Běžná cesta toleruje tři dny a varuje;
    away mode ne. Naléhavá akce na starých datech pošle „otevři aplikaci" — bez ceny, bez kusů.
  - **Jedna zpráva, ne proud.** Nejnaléhavější věc plus počet ostatních. Druhá jde jen když je
    o 10 bodů naléhavější. Test simuluje týden po půlhodinách: odejde 7–8 zpráv.
- `app/services/away_runner.py` + `app/routes/away.py` + `away_mode_state` (jeden řádek, `last_push_*`
  přežije restart — scheduler, který zapomene, co poslal, to pošle znovu).
- `backend/scripts/away_check.py` — **nepotřebuje běžící appku.** Pověsíš na Windows Task Scheduler
  a away mode funguje se zavřenou aplikací. Pořád to chce zapnutý stroj a funkční SMTP.

**Utažená stopka je semafor o stupeň dřív, ne vymyšlená cena.** První verze tohohle modulu si
vymyslela stopku 5 % nad červenou linkou. Měla linky obráceně: zelená je kde se nakupuje, červená
je **cílová cena k prodeji** — cena pod červenou linkou je normální stav pozice, která nedošla na
cíl. Na živém portfoliu ta verze nařídila prodat IZEA, VTSI a KUYA.V, jednu z nich 86 % pod cílem.
Nahradilo to escalation semaforu: GREEN se pro odlehčování bere jako YELLOW, YELLOW jako ORANGE.
ORANGE se **nezvyšuje** na RED — „prodej skoro všechno" není rozhodnutí, které se dělá za někoho,
kdo nemůže odpovědět. Je to rozšíření aplikace, ne kánon, a každá zpráva to říká.

**UI:** `AwayModeCard` na dashboardu — přepínač, pravidla, poslední rozhodnutí a tlačítko
„Co by se poslalo teď" (spustí skutečný cyklus, nic neodešle).

**Známý limit, ověřeno na živém portfoliu:** away mode teď reálně nemá na čem zabrat. Všech 15 pozic
nemá fázi ani konvikční skóre, takže se motor odmítá k nim vyjádřit (což je záměrná pojistka) a away
mode mlčí. Aby se mlčení nedalo splést s „všechno je v pořádku", ukládá se k rozhodnutí i důvod —
`⚠️ NEZNÁMÁ KVALITA u 15 pozic` je první v pořadí. Doplnit fáze pozicím je tvoje práce, ne kódu.

### `[x]` B8. Health endpoint lže

Hlásí model, který neexistuje, a inzeruje `google_search`, který je vypnutý. Health, kterému se nedá
věřit, je horší než žádný — je to první místo, kam se podíváš, když něco nesedí.

**Hotovo když:** hlásí to, co appka opravdu volá.

---

## P2 — věrnost metodě (kánon říká, kód nemá)

### `[x]` B9. Weinstein pilíř odporuje kánonu — tvoje rozhodnutí

Master Signal má „Weinstein Guard" (30 WMA, 15 % váhy) = technická analýza. Gomes explicitně píše, že
metoda *„has almost NOTHING to do with technical analysis"* (kánon gap #3).

Tři možnosti: označit jako **vlastní rozšíření mimo Gomese**, snížit váhu, nebo odstranit.
Neudělám to za tebe — je to tvoje metodické rozhodnutí, ne bug.

### `[x]` B10. Yellow neflagne držené WAIT_TIME pozice

Kánon §2: v Yellow se prodávají **všechny spekulativní i „Wait Time"** akcie. `get_blocked_tiers`
blokuje jen TERTIARY tier, ne držené WAIT_TIME pozice (gap #9). Půlka pravidla chybí.

Data jsou: `inflection_status` se od commitu `31184dc` konečně čte z reálného záznamu.

### `[x]` B11. Emoční brzdy — cooldown po ztrátě, detekce revenge-tradingu

Audit je označil za neexistující, protože nebyla kniha obchodů. **Ta teď existuje**
(`services/trade_ledger.py`, zapisuje i `emotion_tag`) — takže brzdy jdou konečně postavit.

Je to důvod, proč appka vznikla, a v běžícím kódu pro to zatím není nic.

### `[x]` B12. Market alert gauge

Semafor byl ručně nastavené pole. Kánon ho odvozuje z pozice S&P na 40letém valuačním grafu (gap #2).

**Hotovo (23. 8.):** `app/services/market_gauge.py` + `GET /api/market-gauge`. Měsíční closy ^GSPC
za celé dostupné okno (1985→dnes, **41,7 roku** — přesně ten 40letý graf), log-lineární trend skrz ně,
a dnešní cena vyjádřená v sigmách od trendu. Tři linky kánonu = z +2,5 / 0 / −2,0.

**Ověřeno proti oběma RED alertům, které Gomes za život vyhlásil:**

| kánon | co ukazatel našel |
|---|---|
| konec 1999 | **našel přesvědčivě** — prosinec 1999 `z=+2,74` a březen 2000 `z=+2,75` jsou dvě nejvyšší hodnoty za celých 41 let |
| půlka 2007 | **nenašel vůbec** — červen 2007 `z=+0,58`, 78. percentil, úplně obyčejný měsíc |
| (bonus) únor 2009 | nejlevnější měsíc řady, `z=−2,85` — generační příležitost |

Vrchol 2007 stál na úvěrech a ziscích, které se chystaly zmizet. Cena proti vlastnímu trendu to
strukturálně vidět nemůže. **Ukazatel proto tuhle svoji slepou skvrnu píše do každé odpovědi**
(`blind_spot_cs`) a obě čísla jsou zapíchnutá v testech proti fixtuře reálné řady — kdyby je někdo
rozbil, tvrzení v textu přestane být pravda a testy spadnou.

Semafor **nepřepisuje**. `suggested_alert` je návrh; `AT_UPPER_LINE` navrhuje ORANGE a ne RED,
protože RED je dvakrát za život a jednou z těch dvou tenhle ukazatel nevidí.

**UI:** `MarketGaugeCard` — z-skóre, značka mezi třemi linkami, shoda se semaforem, a slepá
skvrna přímo na kartě. **Žádné tlačítko, které semafor přepíše.**

Dnes: `z=+1,46`, 91. percentil, `EXPENSIVE` → návrh **YELLOW**, což **sedí** s tím, co máš ručně
nastavené.

### `[x]` B13. BOXX / RWM jako reálné instrumenty

Cash byl abstraktní `cash_pct`, hedge taky. Kánon §2 je má jako konkrétní tickery (gap #6).

**Hotovo (23. 8.):** `app/services/cash_hedge.py` + `GET /api/cash-hedge`. Semafor se převádí na
kusy: cíl v Kč, živá cena, počet akcií.

**Ale to podstatné vypadlo až při modelování.** Ověřeno proti živým datům 23. 8.:

| ticker | co to je | domicil | burza |
|---|---|---|---|
| BOXX | Alpha Architect 1-3 Month Box ETF | **US** | Cboe US |
| RWM | ProShares Short Russell2000 | **US** | NYSE Arca |

Oba jsou americké fondy bez KID podle PRIIPs. **Evropský retailový broker (Degiro, Trading 212) je
retailovému klientovi zpravidla neprodá.** Plán, který ti při ORANGE říká „dej 93 317 Kč do RWM",
je plán na tlačítko, které tam není.

Kánon na to má vlastní větu — *„Mimo USA: RWM nemusí být dostupné → buď extra vybíravý, drž víc
cashe místo hedge"* — a to je přesně to, co teď appka vrátí místo nesplnitelného cíle.

Formulace je **„pravděpodobně neprodá, ověř si to"**, ne „nedostupné". Kód nikdy neviděl tvůj účet;
tvrdit fakt o produktové nabídce, kterou nečetl, by byla přesně ta vymyšlená jistota, kterou odsud
pořád odstraňujeme.

`XSPS.L` (Xtrackers S&P 500 Inverse Daily Swap UCITS) se vrací jako **důkaz, že evropská inverzní
ETF existují — ne jako náhrada**: shortuje S&P 500, ne Russell 2000, a resetuje se denně, takže
v rozkolísaném bočním trhu ztrácí, i když index skončí tam, kde začal.

**UI:** `CashHedgeCard` — vede blokací a náhradou, ne cílovou částkou.

**Čí je které číslo:** kánon dává procento jen pro GREEN (0 % hedge) a YELLOW (20–30 % v RWM).
ORANGE má větu („I have ALL of my cash in RWM"), RED popis. Odpověď proto nese `interpreted: true`
tam, kde jsou čísla 25/35/40 a 5/45/50 čtení aplikace, ne Gomesova slova.

---

## Nové (zadané 22. 8.)

### `[x]` B14. SEC EDGAR — 10-K, 10-Q a Form 4 pro držené pozice

Automaticky stahovat výroční (10-K) a čtvrtletní (10-Q) zprávy a Form 4 (insider nákupy/prodeje)
pro pozice v portfoliu, analyzovat je a zapojit do rozhodování.

**Dvě pasti, ověřené naživo 22. 8.:**

1. **Pět ze čtrnácti pozic u SEC vůbec nepodává** — GSI.V, KUYA.V, IMP.V, QIPT, UMD jsou TSX Venture
   a jiné burzy. „Žádná podání" se u nich nesmí zobrazit stejně jako u firmy, která podává a mlčí.
   První je fakt o burze, druhé fakt o firmě.
2. **Form 4 „prodej" většinou není prodej.** První stažený Form 4 (TPCS, 19. 8.) má kód `G` — dar,
   cena $0, označený jako *Disposed*. Naivní parser z toho udělá medvědí signál. Totéž `F` (akcie
   zadržené na daň) a `M` (uplatnění opce). Skutečný signál nesou jen `P` (nákup na trhu)
   a `S` (prodej na trhu).

---

### `[?]` B15. Dvě pozice mají měnu, která nesedí s burzou — ověř

`IMP.V` a `KUYA.V` jsou uložené jako **EUR**, zatímco `GSI.V` a `DBO.TO` ze stejných burz
(TSX Venture / Toronto) jsou **CAD**. Pokud jde skutečně o TSX Venture listingy, je jejich
hodnota v CZK nadhodnocená o poměr EUR/CAD, tedy **o 61 %** — dohromady zhruba 17 000 Kč,
což je **7 % celého portfolia**.

Nemůžu to rozhodnout za tebe: Degiro je může držet přes evropský listing (Intermap se
obchoduje i ve Frankfurtu), a pak je EUR správně. Podívej se do Degira, jakou měnu ti u nich
skutečně účtuje.

Appka na to od teď upozorní sama (`currency_mismatch`, varování v denním přehledu).

### `[ ]` B16. SEC pokrývá jen 46 % portfolia

Podle hodnoty k 22. 8. je **54,1 % portfolia mimo dosah SEC EDGAR** — TSX Venture, Toronto
a tři pozice uložené jako ISIN. Čtyři z pěti největších pozic tam spadají.

To znamená, že „SEC nic nenašel" je u poloviny portfolia prázdná informace, ne dobrá zpráva.
Pro kanadské firmy by ekvivalentem byl **SEDAR+**; stojí za zvážení jako další zdroj.

---

### `[x]` B17. U zahraničních emitentů čteme obálku, ne obsah

RDCM je jediná pozice se statusem `FOREIGN_PRIVATE_ISSUER`. Její nejnovější 6-K má
**1 777 znaků** — je to krycí list. Skutečný obsah (tisková zpráva s výsledky) sedí
v příloze `EX-99.1`, kterou jsme nestahovali.

Důsledek: průzkum u RDCM nenašel **nic**, a to při 9,9 % podílu v portfoliu. „Nula nálezů"
tam ale neznamenala čistý štít, znamenala, že jsme četli obálku.

**Hotovo (23. 8.):** `SecEdgarClient.fetch_documents` čte manifest podání z
`-index-headers.html`, takže typ dokumentu určuje SEC, ne odhad z názvu souboru.
`read_filing` přidává přílohy `EX-99` u wrapper formulářů (6-K, 8-K) a u každého podání,
jehož hlavní dokument přijde nečekaně tenký. Podání, které opravdu je jen krycí list
(RDCM 27. 5. 2026), to teď v souhrnu **řekne**.

Ověřeno na živých datech: RDCM 6-K z 12. 8. 2026 vzrostl z 1 777 na 22 443 znaků a
z nuly nálezů na **šest** — tržby −33,4 % r/r, obrat z provozního zisku 1,7 mil. USD
do GAAP provozní ztráty 3,8 mil. USD, odkup akcií zatím jen rozhodnutý, ne schválený.

---

### `[x]` B18. Hromadné přeanalyzování má jít z předplatného, ne z API

Předplatné přihlašuje **tebe v klientovi**; backend je proces na serveru a nemá se čím
přihlásit, takže si nové podání kupuje přes Anthropic API. To je v pořádku — je to jedno
volání na ticker za čtvrtletí a jinak by se appka sama nikdy neaktualizovala.

Backfill je ale jiný tvar: po každé změně promptu je to desítka dlouhých dokumentů naráz.
Ten nemá důvod jít přes API, když je stejně otevřená session.

**Hotovo (23. 8.):** `backend/scripts/sec_backfill.py`
- `export [TICKER ...] [--newest-only]` — stáhne text nepřečtených podání do
  `.sec_backfill/` (včetně příloh, viz B17). Žádný model, jen EDGAR.
- `import` — načte ručně napsané souhrny zpět do DB.
- `status` — co je analyzované, co čeká, co je vyexportované.

Prázdná šablona se **neuloží** — `analysis` zůstane NULL. Kdyby se uložila, „nikdo to
nečetl" by se v UI změnilo na „přečteno, nic zvláštního".

**Co běží přes API a co ne:** přes API jde jen textová vrstva (varovné signály a výhled
z podání, deep DD, knowledge synthesis, claim extraction). Všechno číselné — XBRL
fundamenty, hotovost, burn, runway, trend tržeb, klasifikace Form 4, coverage status,
kurzy, R/R skóre, semafor — je čistý kód a běží i bez klíče.

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
- `[x]` B9 „Weinstein Stage 4“ nebyl Weinstein a blokoval nákup pod green line — tvoje volba: označit jako vlastní rozšíření

---

## Vyžaduje tvůj zásah (ne kód)

- **Gmail app password vypršelo.** Ověřeno 22. 8. živým odesláním: server odpověděl
  `535 BadCredentials`. Kanál se postaví a dojde až ke Gmailu, ale nepřihlásí se.
  Vygeneruj nové app password na myaccount.google.com → Security → App passwords
  a přepiš `SMTP_PASSWORD` v `backend/.env`. Do té doby ti appka nemůže nic poslat.
- `[x]` B14 SEC EDGAR — výsledky z XBRL, výhledy z textu, Form 4 jako doplněk

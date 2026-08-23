# Přestavba front-endu — seznam úkolů pro autonomní běh

Stav k 23. 8. 2026. Pořadí je závazné: každý blok stojí na předchozím.
Cílem není hezčí obrazovka, ale **aplikace, ve které se dá za pár minut
rozhodnout, co koupit a co prodat** — protože to je jediná cesta k 15 %
a víc ročně.

## Rozsah

- **Jen desktop.** Mobilní podoba se v tomhle běhu neřeší. Nesmí se ale
  aktivně rozbít víc, než je dnes: žádné nové pevné šířky v px na kořenových
  prvcích.
- Vizuální směr: studená černá + korálový akcent (reference RedSun), levá
  lišta, plná šířka, vysoká hustota. Písma zůstávají — Archivo, IBM Plex Sans,
  IBM Plex Mono.
- Čeština všude, odborně. Zkratky mají vysvětlivku.

## Měřitelný cíl

Změřeno na dnešní verzi při okně 1600 × 1000:

| Co | Dnes | Hotovo, když |
|---|---|---|
| Výška záložky Portfolio | 3 025 px | ≤ 1 100 px |
| Kde začíná tabulka pozic | 1 969 px | ≤ 220 px |
| Šířka obsahu | 1 280 px | = šířka okna |
| Výška řádku pozice | 69 px | ≤ 32 px |
| Sloupce v tabulce | 10, z toho 4 prázdné | ≤ 6, žádný trvale prázdný |
| Varování pod verdiktem | 9 řádků textu | 3 úkoly s akcí |
| Kolikrát je na stránce celková hodnota | 2× | 1× |

## Ověřovací příkazy

Úkol je hotový, teprve když příslušný příkaz skončí návratovým kódem 0.
Tvrzení „funguje to" není důkaz.

- Sestavení a typová kontrola: `npm run build` z `frontend/`
- Lint: `npm run lint` z `frontend/`
- Testy front-endu: `npm test` z `frontend/`
- Testy backendu: `python -m pytest` z `backend/` (systémový Python)

U vizuálních úkolů navíc platí: pořídit snímek přes `browse` a připojit
naměřená čísla z tabulky výše. Snímek bez čísla neprokazuje nic.

## Zábradlí

### Cizí práce se nemaže

Na aplikaci pracoval víc než jeden člověk. Autor **Majkysa
<miska.svo@seznam.cz>** přidala evidenci dluhů a plateb (záložka Platby:
Společné splácení, Společné platby, Platby Míša, Šetření Míša, Platby Tom)
v commitech `c1839a6` a `03f8a21`, plus opravy backendu v `b86a848`.

Tahle funkce **se neruší, neslučuje ani „neuklízí" jako mrtvý kód.** Smí se
překreslit do nového vzhledu, ale musí zůstat dosažitelná z navigace a musí
dál číst a zapisovat stejné klíče `localStorage`:
`akcion_debts`, `akcion_shared_payments`, `akcion_misa_payments`,
`akcion_savings`, `akcion_tom_payments`.

Data leží v prohlížeči, ne na serveru. Přejmenování klíče = ztráta cizích dat
bez možnosti obnovy z gitu.

**Před smazáním čehokoli spusť `git log --format='%an' -- <soubor>` a podívej
se, kdo to psal.** Jednou už se stalo, že se záložka Platby smazala jako
„prázdná" — nebyla prázdná, jen ji nikdo nenaplnil v testovacím prostředí.


- Commit na `feature/gomes-fidelity`. **Nepushovat, nezakládat PR.**
- `backend/.env` se nečte do výstupu, nekopíruje, necommituje.
- Žádné skutečné notifikace ani příkazy k obchodu kvůli ověření.
- Po každé etapě musí aplikace jet. Žádná etapa nesmí skončit stavem
  „rozpracováno, zatím nefunguje".
- Když se ukáže, že úkol je špatně zadaný, zapsat to sem a pokračovat
  dalším — ne tiše přeskočit.

---

## Hotovo (kontext, nedělat znovu)

- [x] Barvy jako CSS proměnné, dvě témata, přepínač se třemi stavy
- [x] Čeština v celé aplikaci; sémantické barvy místo napevno zadaných
- [x] Glosář 40 pojmů + komponenta `Term` s vysvětlivkami
- [x] Záložka Cíl: kalkulačka, projekce s pásem rozpětí, žebřík mezníků
- [x] `src/lib/compound.ts` + 31 testů; `src/lib/format.ts`

---

## A. Paleta

### A1. Nová paleta v `tokens.css`
Studená černá (`#0A0C11`), panel `#10131A`, linky `#202634`, korál `#FF5A36`.
Semafor zůstává samostatný přístroj: zelená / žlutá / oranžová / červená,
vždy s popiskem.

*Akcent se nikdy nepoužije na stav.* Kdyby korál označoval zároveň tlačítka
i stupeň semaforu, přestal by stupeň něco znamenat.

**Hotovo, když:** obě témata projdou vizuální kontrolou na Portfoliu,
Sledovaných i Cíli; `npm run build` prochází.

### A2. Kontrast
Poměr kontrastu textu ke své ploše ≥ 4,5 : 1 pro běžný text a ≥ 3 : 1 pro
popisky pod 12 px, v obou tématech.

**Hotovo, když:** existuje `frontend/src/design/contrast.test.ts`, který
poměry počítá z tokenů a padá při podkročení. `npm test` prochází.

### A3. Úklid
Poslední 2 napevno zadané barvy v živých souborech; smazat mrtvý
`src/App-old.tsx` (132 barev, nikdo ho neimportuje).

**Hotovo, když:** `grep -rE "(bg|text|border)-(slate|gray|blue|green|red|amber|orange|white|black)" frontend/src --include=*.tsx` nevrací nic.

---

## B. Skelet

### B1. Levá lišta
Nová komponenta `components/shell/SideRail.tsx`: značka, navigace
(Portfolio / Sledované / Cíl / Analýzy / Nepřítomnost), dole semafor.
Šířka 190 px, sbalitelná na ikony.

### B2. Plná šířka
Zrušit `max-w-7xl mx-auto` a `bg-slate-950` z `App.tsx` i
`InvestmentTerminal.tsx`. Obsah zabírá celé okno.

**Hotovo, když:** `document.querySelector('main').getBoundingClientRect().width`
= `window.innerWidth` na 1600 px.

### B3. Semafor jako trvalý přístroj
Stupeň vidět na každé stránce, ne jen na Portfoliu. Čte se z ukazatele trhu,
**nepřepíná se automaticky** — je to podklad, ne verdikt.

### B4. Směrování
Zavést `react-router-dom`. Adresy: `/portfolio`, `/sledovane`, `/cil`,
`/pozice/:ticker`. Tlačítko zpět musí fungovat, odkaz na pozici musí jít
poslat.

**Hotovo, když:** načtení `/pozice/KUYA.V` napřímo zobrazí tu pozici;
tlačítko zpět z detailu vrátí na seznam.

### B5. Horní pruh
Jedno místo pro celkovou hodnotu, P/L, hotovost a počet blokujících mezer.
Zrušit čtyři souhrnné karty v hlavičce i druhou čtveřici uprostřed stránky —
dnes je celková hodnota na stránce dvakrát, pokaždé jinak zaokrouhlená.

---

## C. Deska Portfolia

### C1. Verdiktní sloupec
Úzký levý sloupec: dnešní datum, verdikt jednou větou, důvod. Dnes je to
pruh přes celou šířku, 300 px vysoký, s vycentrovaným štítem.

### C2. Mezery jako úkoly
Devět varování složit do tří skupin **podle problému**, ne podle tickeru:
bez hodnocení / měna k ověření / chybí nákupní cena. Každá skupina má větu
o tom, co kvůli ní aplikace nemůže, a tlačítko vedoucí k opravě.

**Hotovo, když:** test ověří, že se varování stejného druhu slučují a že
skupina nese počet dotčených pozic.

### C3. Hustá tabulka pozic
Řádek ≤ 32 px. Sloupce: symbol, váha, cena, P/L, stav. Chybějící údaj se
nevykreslí, místo aby držel prázdný sloupec. Zrušit `animate-pulse`
u zhoršených řádků — trvale blikající řádek je rušivý, ne informativní.
U P/L pruh velikosti, aby −93 % nevypadalo jako −17 %.

### C4. Spodní pás
Trh na dlouhém grafu / hotovost a hedge / nepřítomnost — tři kompaktní
buňky místo tří karet na celou šířku.

### C5. Řazení a filtr
Řadit podle váhy, P/L, skóre a **podle toho, co vyžaduje pozornost**.
Filtr na „jen pozice s mezerou".

---

## D. Cesta k hodnocení

Nejdůležitější blok celé přestavby a nejmíň vizuální. Dnes aplikace nemůže
doporučit nic, protože žádná z 15 pozic nemá platné konvikční skóre — a v UI
není vidět, jak to napravit. Bez tohohle bloku zůstane appka hezká a němá.

### D1. Obrazovka „co chybí"
Seznam pozic seřazený podle váhy s tím, co u každé chybí (fáze, skóre,
nákupní cena, měna). Zelený řádek = připraveno.

### D2. Hromadné doplnění nákupních cen
Tři pozice bez ceny (`US40053W1018`, `CA00654B1040`, `US90138A1034`) jde
vyplnit na jedné obrazovce, ne proklikem tří dialogů.

### D3. Oprava měny
`IMP.V` a `KUYA.V` jsou vedené v EUR, burza obchoduje v CAD. Rozdíl je
~17 000 Kč, tedy 7 % portfolia. Obrazovka ukáže obě varianty přepočtu
a nechá rozhodnout — **aplikace to sama nepřepíše.**

### D4. Spuštění analýzy z UI
Tlačítko, které pošle pozici k analýze, ukazuje průběh a doplní výsledek.
Bez toho je „Spustit analýzu" na desce slib, který nikam nevede.

**Hotovo, když:** po projití D1–D4 na testovacích datech má alespoň jedna
pozice fázi i skóre a denní seznam k ní vydá pokyn.

---

## E. Detail pozice jako stránka

### E1. Stránka místo dialogu
Route `/pozice/:ticker`. Rozpustit `AssetDetailModal.tsx` (1 236 řádků)
a `StockDetailModal` uvnitř `InvestmentTerminal.tsx`.

### E2. Poctivý prázdný stav
Klik na `RDCM` — 9,9 % portfolia a jediná pozice se šesti zjištěními z SEC —
dnes otevře box 200 px široký s textem „Chybí data akcie" a tlačítkem Zavřít.
Musí místo toho ukázat, co chybí a co s tím.

### E3. Obsah stránky
Teze, zjištění z SEC, historie skóre, obchodní formulář, pásmo mezi zelenou
a červenou linkou. Vysvětlivky u všech zkratek.

### E4. Propojení se sledovanými
`KUYAF` ve sledovaných a `KUYA.V` v portfoliu je tatáž firma. Stránka to
musí říct, jinak aplikace doporučí nákup něčeho, co už držím.

---

## F. Sledované

### F1. Stejná hustá tabulka jako u pozic
Zrušit sloupec `PRICE ZONE`, který je u všech devíti řádků `N/A`, a tlačítko
„View Details" v každém řádku — celý řádek je klikací.

---

## G. Cíl

### G1. Uložit nastavení kalkulačky
Dnes se po znovunačtení vrátí na výchozí hodnoty. Ukládat do `localStorage`
přes `try/catch` (přístup umí vyhodit výjimku, ne jen vrátit prázdno).

### G2. Ověřit výchozí předpoklady
Věk 35, cíl 30 mil., výnos 15 %, vklad 20 000 Kč jsou převzaté ze staré
záložky Freedom. Doplnit je do nastavení, ať nejsou zadrátované v kódu.

---

## H. Napříč aplikací

### H1. Jednotné stavy načítání, prázdna a chyby
Prázdný stav není zelená fajfka. „Nic jsi nezadal" se nesmí tvářit jako
„všechno je vyřízené" — pět takových fajfek měla stará záložka Platby.

### H2. Ovládání klávesnicí
Viditelné zaostření, rozumné pořadí tabulátoru, `/` skočí do hledání,
`Esc` zavírá. Aplikaci používá člověk s roztroušenou sklerózou; přesné míření
myší nesmí být podmínkou.

### H3. Omezený pohyb
`prefers-reduced-motion` skutečně vypíná animace, ne jen zkracuje.

### H4. Vysvětlivky všude
Glosář má 40 pojmů, používají se tři. Projít aplikaci a obalit zkratky
(`P/L`, `ISIN`, `ADR`, `SEC`, `σ`, `percentil`, `konvikční skóre`, `pásmo`,
fáze životního cyklu, zelená a červená linka).

**Hotovo, když:** test projde `.tsx` soubory a ohlásí zkratku ze slovníku,
která není obalená v `Term`.

### H0. Lint musí projít
`npm run lint` dnes hlásí **24 chyb a 5 varování** ve 12 souborech —
`no-explicit-any`, nepoužité proměnné, chybějící závislosti hooků. Podle
CLAUDE.md je úkol hotový až když příkaz skončí nulou, takže tenhle dluh
blokuje uzavření všech ostatních. Je předchozí, ne způsobený přestavbou.

**Hotovo, když:** `npm run lint` skončí návratovým kódem 0.

### H5. Formátování čísel jen přes `format.ts`
Zrušit místní `formatCurrency` a `formatPercent` v `InvestmentTerminal.tsx`.
Jedno číslo se nesmí na dvou místech zaokrouhlit jinak.

---

## I. Známé vady mimo přestavbu

### I1. Automatické alerty nikdy neběžely
`check_and_send_alerts` v `backend/app/services/notifications.py:423` volá
`get_top_opportunities_v2(db=, min_confidence=, limit=10)`. Ta funkce
(`backend/app/trading/master_signal.py:674`) parametr `limit` nezná a povinný
`tickers` nedostane. Plánovač to zkouší každých 30 minut a pokaždé spadne.

**Hotovo, když:** existuje test, který volání ověří, a `python -m pytest`
prochází.

### I2. Rozhodnutí o měně (B15)
Čeká na uživatele. Aplikace varuje, sama nepřepisuje. Viz D3.

### I3. SEC pokrývá 46 % portfolia (B16)
Kanadská jména potřebují jiný zdroj (SEDAR+). Mimo rozsah tohohle běhu;
zapsáno, aby se na to nezapomnělo.

---

## Pořadí

```
A1 → A2 → A3          paleta a úklid
B1 → B2 → B3 → B4 → B5   skelet
C1 → C2 → C3 → C4 → C5   deska Portfolia          ← tady se přestane scrollovat
D1 → D2 → D3 → D4        cesta k hodnocení        ← tady appka začne radit
E1 → E2 → E3 → E4        detail pozice
F1 · G1 · G2             sledované a cíl
H0 … H5                  napříč aplikací (H0 blokuje uzavření všeho)
I1                       oprava alertů
```

Blok **C** je ten, po kterém uvidíš rozdíl. Blok **D** je ten, po kterém
bude aplikace k něčemu.

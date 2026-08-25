# Zadání pro designovou AI — desktopová verze Akcionu

Zkopíruj všechno pod čarou do nové konverzace s designovou AI (Claude, v2, Figma Make,
Lovable — cokoliv, co umí vrátit HTML). Text je psaný tak, aby modelu, který o Akcionu
nikdy neslyšel, stačil sám o sobě.

Volitelný blok „Nativní desktopová aplikace" na konci nech, jen pokud chceš aplikaci
zabalit do okna (Tauri/Electron). Pokud jde jen o rozvržení pro velké obrazovky, smaž ho.

---

Jsi produktový designér, který navrhuje rozhraní pro nástroje, podle kterých lidé
rozhodují o penězích — ne marketingové stránky. Navrhni **desktopovou verzi aplikace
Akcion**.

## 1. Co Akcion je

Osobní investiční terminál pro správu rodinného portfolia podle jedné konkrétní
investiční metodiky. Není to fintech pro masy — má jednoho uživatele a spravuje
skutečné rodinné peníze. Backend (Python/FastAPI) počítá verdikty z pravidel a z dat
o trhu a regulátora; frontend je jednostránková aplikace v Reactu 19, Vite, Tailwind 3,
grafy v Rechartsu, ikony Lucide.

Aplikace neradí obecně. Vyhodnotí pravidla a řekne, co dnes udělat — nebo že se dnes
nedělá nic.

## 2. Pro koho to je

Jeden člověk. Spravuje skutečné rodinné peníze. Má roztroušenou sklerózu, takže má
omezenou energii a přicházejí týdny, kdy se k aplikaci vůbec nedostane.

Z toho plyne celé zadání:

- Každé rozhodnutí se musí vejít do **dvou minut, tří akcí a jedné obrazovky**.
- **Aplikace rozhoduje, člověk potvrzuje.** Ne naopak.
- Velké plochy k proklikání, vysoký kontrast, ovládání z klávesnice.
- **„Nic. Drž."** je plnohodnotný stav rozhraní, ne prázdná obrazovka. Zpráva, že se
  dnes nic dělat nemá, je nejčastější a nejcennější výstup aplikace. Navrhni ji jako
  hlavní stav, ne jako výpadek.
- Aplikace musí přežít nepřítomnost: režim „Nepřítomnost" (přísnější stopy, přednost
  hotovosti), jedno nejnaléhavější upozornění místo šumu, a **stará data zřetelně
  označená jako stará**.

## 3. Etika rozhraní — tohle je důležitější než estetika

1. **Chybějící údaj se nikdy nesmí tvářit jako verdikt.** Když chybí vstup, rozhraní
   napíše „chybí údaje" nebo „cena z 3. 8.", nikdy dopočítanou nulu ani sebejisté
   „Koupit". Navrhni pro tohle vizuální jazyk — je to nejčastější stav v aplikaci a
   nejčastější zdroj škody.
2. **Barva něco znamená.** Jediná barevná plocha v aplikaci je semafor. Dekorativní
   barvu aplikace nemá.
3. **Aplikace nikdy neslibuje výnos.** Projekce jsou projekce a musí tak vypadat.

## 4. Schválený vizuální směr: „signální skříň"

Předchozí návrh byl zamítnut jako „velmi generický a nudný". Tenhle směr je schválený a
platí — nevymýšlej jiný, dotáhni tenhle.

**Jedna strukturální myšlenka: dvě plochy, každá něco znamená.**

- **panel** — tmavý v *obou* tématech. Odsud aplikace mluví: verdikt, semafor,
  navigace. Úsudek má mít váhu, proto je pod ním nejtmavší plocha.
- **list** — linkovaný účetní arch. Tady žijí záznamy: pozice, čísla, zjištění
  regulátora. Ve světlém tématu bílý, v tmavém teple tmavý.

Téma nemění ten vztah, mění osvětlení.

**Semafor je poznávací prvek.** Čtyřstupňová světelná lišta (zelená / žlutá / oranžová
/ červená). Rozsvícený stupeň zároveň **ztlumí ty úrovně pozic, které dané pravidlo
blokuje** — na červené se ztlumí nákupní patra. Není to dekorace, kóduje reálné
pravidlo z backendu. Na desktopu má být trvale viditelný.

Tvar: **hranatý**. Rádius karet 3 px, vstupů 2 px. Žádné bubliny, žádné pilulky.

## 5. Barevné tokeny — použij přesně tyhle hodnoty

Nevymýšlej paletu. Barvy jsou CSS proměnné (trojice RGB), Tailwind je skládá přes
`rgb(var(--x) / <alpha-value>)`.

**Světlé téma**

```
--page   #F2F0E9   podklad, teplá lomená bílá
--sheet  #FFFDF8   arch          --sheet-alt #F6F3EA   --rule #DFD9C9
--ink    #23261F   text na archu --ink-2 #63665B       --ink-3 #8A8D82
--frame  #1C201B   panel         --frame-2 #262B24     --frame-3 #333930
--on-frame #E9E7DF               --on-frame-2 #9DA096
semafor: zelená #3F7A4B  žlutá #8A6A10  oranžová #A85F22  červená #9C3A32
--accent #2F567A   ocelová modř (jediná interakční barva)
```

**Tmavé téma**

```
--page   #0F1110   zelenočerná, ne modročerná
--sheet  #1A1E19                 --sheet-alt #20251F   --rule #373D34
--ink    #E8E7DF                 --ink-2 #8E9189       --ink-3 #62655D
--frame  #171A17                 --frame-2 #1E221E     --frame-3 #272C26
semafor: zelená #5C9B62  žlutá #D3A017  oranžová #C9772F  červená #B2453D
--accent #6D98BE
```

Stíny jsou téměř neviditelné: `0 1px 2px rgb(0 0 0 / .16)`.

Tři stavy tématu: světlé / tmavé / systémové, systémové je výchozí.

## 6. Typografie

- **Archivo Variable** — displej, používá osu šířky. Střídmě: verdikt, značka, nadpisy.
- **IBM Plex Sans** — české věty. Má poctivé latin-ext, takže háčky a čárky sedí.
- **IBM Plex Mono** — **každé číslo v aplikaci**, tabulkové číslice, aby sloupce lícovaly.

## 7. Co má desktopová verze vyřešit

Současný stav: jeden dlouhý sloupec widgetů pod sebou, nad ním záložky
**Portfolio / Sledované / Cíl**, vlevo postranní panel pro vstup analýzy. Na 1920 px se
plýtvá šířkou a to nejdůležitější je pod ohybem. Mobil je vědomě odložený — neřeš ho.

Návrh má dodat:

1. **Trvalé rozvržení pro velké obrazovky** postavené na těch dvou plochách:
   navigace a úsudek na panelu, záznamy na archu. Ne tři náhodné sloupce — rozvržení,
   ze kterého je poznat, kde aplikace mluví a kde se vedou záznamy.
2. **Mřížku a body zlomu**: 1280, 1440, 1920, 2560. Řekni, co se na každé šířce
   přidá — a co se nepřidá, protože prázdné místo je lepší než výplň.
3. **Hustotu**: vyjmenuj, co je vidět bez posouvání na 1440 × 900.
4. **Klávesovou vrstvu**: zkratky pro hlavní úkony, viditelné stavy zaměření, průchod
   celou aplikací bez myši.
5. **Mapu stavů** pro každou plochu: načítání, prázdno, stará data, chybějící údaj,
   chyba spojení, „nic k řešení".
6. **Obě témata** u každého artboardu.

## 8. Obrazovky, které se navrhují

1. **Dnešek** — první, co se otevře. Buď „Nic. Drž.", nebo nejvýše tři seřazené akce
   s přesnými částkami v korunách. Vedle: stupeň semaforu, hodnota portfolia,
   hotovost a zajištění, rizikoměr, karta režimu Nepřítomnost.
2. **Portfolio** — tabulka pozic na archu. Sloupce: ticker, název, váha v portfoliu,
   strop alokace, mezera v Kč (+ dokoupit / − prodat), skóre přesvědčení 0–10,
   akční signál (Koupit / Držet / Prodat / Odstřelovač), trend, další katalyzátor.
   Nad ní souhrn portfolií (více účtů u různých brokerů). Pod ní **mezerový výkaz** —
   rozdíl mezi tím, jak portfolio vypadá, a jak podle pravidel vypadat má.
3. **Sledované** — žebříček kandidátů, kteří ještě nejsou v portfoliu.
4. **Cíl** — kalkulačka a graf projekce, žebřík milníků. Projekce se ukazuje jako
   rozpětí, ne jako jedna křivka.
5. **Detail titulu** — dnes je to modální okno, na desktopu má být plná stránka:
   hlavička s verdiktem, investiční teze, zjištění regulátora (SEC), obchodní paluba,
   formulář obchodu, časová osa titulu.
6. **Vstup analýzy** — text / YouTube / Google Docs plus jméno mluvčího. Na desktopu
   to nemusí zabírat trvalý postranní panel; navrhni, kam patří.
7. **Drobnosti**: zvonek oznámení, přepínač tématu, hledání, potvrzovací dialogy.

## 9. Tvrdá pravidla textů a prvků

Porušení kteréhokoliv bodu znamená, že návrh je nepoužitelný:

- **Čeština všude, v profesionálním rejstříku.** Žádná žargonová čeština („setupy"),
  žádný telegrafní styl („NIC. DRŽ." velkými písmeny jako povel).
- **GREEN / YELLOW / ORANGE / RED jsou hodnoty z databáze a nikdy se neobjeví ve větě.**
  V textu se píše „zelená", „žlutá", „oranžová", „červená".
- **Žádné emoji jako prvek rozhraní.** Místo něj barevný bod. Emoji se vykresluje
  písmem systému, na každém stroji vypadá jinak a nejde přebarvit s tématem.
- **Česká desetinná čárka a české datum.** Skutečný zůstatek se tiskne do koruny;
  patnáctiletá projekce jako „15,6 mil. Kč", protože nezná své haléře.
- **Každá zkratka má vysvětlivku** dostupnou na místě (P/L, ATH, 10-K, going concern…).
- **Žádná napevno zadaná paleta Tailwindu** (`slate-800`, `text-green-400`) ani hex
  v komponentě — jen tokeny výše.
- **Žádné přechody na pozadí, sklo, fialová, záře, 3D karty, plovoucí bubliny.**

## 10. Co odevzdat

1. **Jeden soběstačný HTML soubor** — inline CSS, žádné CDN, žádné externí obrázky.
   Artboardy pod sebou, každý popsaný: název obrazovky, šířka, téma. Použij skutečně
   vypadající česká data (tickery, koruny, procenta), ne „Lorem ipsum" a ne kulatá čísla.
2. **Mřížku a spacing škálu** jako tabulku.
3. **Inventář komponent** — co je nová komponenta a co je jen nové uspořádání
   existujících.
4. **Mapu stavů** podle bodu 7.5.
5. **Seznam klávesových zkratek.**
6. **Odůvodnění, nejvýše deset vět**: co se změnilo oproti jednomu sloupci a proč je
   nová podoba rychlejší pro člověka, který má na rozhodnutí dvě minuty.

## 11. Jak návrh posoudím

- Na 1440 × 900 v tmavém tématu vidím bez posouvání: dnešní verdikt, stupeň semaforu,
  hodnotu portfolia a nejvýše tři akce.
- Otázku „co mám dnes udělat" zvládnu za dvě minuty a tři kliknutí.
- Chybějící údaj je na první pohled poznat jako chybějící, ne jako nula.
- Barva se nikde nepoužívá dekorativně; semafor je jediná chroma.
- Návrh nevypadá jako šablona pro startupový dashboard.
- Obě témata drží kontrast; panel je tmavý v obou.

Než začneš kreslit, napiš nejvýše pět otázek, které by změnily rozvržení. Pak navrhuj.

---

### Volitelně: nativní desktopová aplikace

Pokud má vzniknout i okenní aplikace (Tauri nebo Electron kolem stejného frontendu),
navrhni navíc: chování vlastní lišty okna, minimální rozměr okna, chování při plné
obrazovce a při dvou monitorech, ikonu v oznamovací oblasti a jedno tiché denní
upozornění, offline stav s výrazným razítkem stáří dat, a globální zkratku, která
vyvolá obrazovku „Dnešek" odkudkoliv ze systému.

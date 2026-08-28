# Gomes — Video Addendum (co článek neříká, a kód proto nemá)

**Zdroj:** Mark Gomes, *"How I Make Money On Stocks (READ THE DESCRIPTION FIRST!)"*,
YouTube `9PhWx9rzIaU`, natočeno začátkem 2025 (v přepisu: *"This is the beginning of 2025"*,
tehdy Yellow Alert).

**Vztah ke kánonu:** `GOMES_METHODOLOGY_CANON.md` má pravidlo *"když se kód a dokument rozejdou,
vyhrává dokument, protože je to psaný zdroj od autora, ne přepis z videa z druhé ruky."*
To pravidlo mířilo na přepisy **od třetích stran**. Tohle je Gomes sám na svém kanálu, tedy taky
primární zdroj. **Amendment:** pro témata, o kterých článek MLČÍ, je tohle video kánon. Kde se
překrývají, vyhrává dál článek.

> Pozn. k referencím: komentáře v kódu citují minutáž (`Ref: Minute 42:00`) z videa, které není
> tohle — část značek nesedí (House Money je tu v 29:35, ne v 42:00). Minutáž neidentifikovaného
> videa je neověřitelná reference. Nové věci níže odkazuj na sekce tohoto dokumentu.

---

## TIER 1 — kód aktivně odporuje metodice

### V1. Gold Mine je ABSORPČNÍ stav. Kód ho umí degradovat zpět na Wait Time. ✅ HOTOVO 2026-08-24

Gomes to říká jako jedinou věc ve videu, kterou explicitně nakazuje si zapsat (36:27–37:05):

> *"The fact that you go through a rough patch — less orders, the business slows down — that does
> NOT mean you have shifted out of Gold Mine. You're still in Gold Mine phase. You've already proven
> your product sells in the marketplace, so you're not going to go back to Wait Time. (…) Gold Mine
> is a long-term measure that denotes a company that has graduated from being promising to being
> proven. **Very important for you to write down and understand the difference between being Gold
> Mine and being in a rough patch.**"*

Životní cyklus je tedy **ráčna**, ne klasifikace: `GREAT_FIND → WAIT_TIME → GOLD_MINE`, a Gold Mine
je pohlcující stav. "Rough patch" je **ortogonální dočasný příznak**, ne fáze.

**Stav v kódu — dvě nezávislá místa, obě bezpaměťová:**
- `StockLifecycleClassifier.classify` (`app/trading/gomes_logic.py:377`) — hlasování klíčových slov,
  `WAIT_TIME` vyhrává při ≥2 shodách. A `WAIT_TIME_SIGNALS` (`:331`) obsahuje přesně slovník rough
  patche: `"missed guidance"`, `"lawsuit"`, `"delays"`, `"cfo left"`, `"execution problems"`.
- `propose_phase` (`app/services/lifecycle_rubric.py:203`) — čisté `argmax` přes skóre signálů,
  bez jakékoli znalosti dřív dosažené fáze. Klesající tržby + hluboký retrace ⇒ `WAIT_TIME`.
- `grep -rn "rough_patch"` napříč repem = **0 výskytů**. Ten pojem v aplikaci neexistuje.

**Dopad je konkrétní a drahý.** `check_buy_guard` (`gomes_logic.py:948`) má tvrdou branku
`Gate.WAIT_TIME`. Prověřený Gold Mine s jedním špatným kvartálem se přeznačí na Wait Time → Buy
Guard zakáže nákup **přesně v momentě, kdy je akcie nejlevnější**. To je ta situace, na které Gomes
vydělal celou kariéru (CTLP za $3 → $11, VTSI, AirTest). Aplikace ji systematicky zablokuje.

**Spec:**
- Persistovat `lifecycle_phase_max` (nejvyšší kdy dosažená fáze) per ticker. Návrh nové fáze se
  aplikuje jen když je ≥ `lifecycle_phase_max`.
- Přidat `rough_patch: bool`, `rough_patch_source: str`, `rough_patch_until: date | None`.
- Wait-time signály detekované na tickeru s `lifecycle_phase_max == GOLD_MINE` **nesmí** snížit fázi
  — nastaví `rough_patch = True`.
- Degradace z Gold Mine je možná jen ručním rozhodnutím člověka s poznámkou, nikdy z klíčových slov.

### V2. Velikost pozice je funkce R/R skóre. Kód sází ploché procento per tier. ✅ HOTOVO 2026-08-24

49:34–50:14, doslova a s čísly:

> *"Why would you put the same amount of money in a stock that's here [nezajímavá] as a stock that
> is way up here? (…) When a stock is up here, I'm liable to own **zero or 1%** of it in my
> portfolio. When it's here, **a 10 on the scale**, I'm more liable to own **10%** of that stock."*

Tier tedy **není cíl, je STROP**. Řídící páka je skóre. Rovnoměrné vážení Gomes odmítá výslovně
(*"a lot of people say, well, I'm just going to put 10,000 in this stock, 10,000 in that stock —
that defeats the purpose"*).

**Stav v kódu:** `PositionSizingEngine.TIER_LIMITS` (`gomes_logic.py:772`) dává fixní
`recommended_pct`: PRIMARY 8 %, SECONDARY 3 %, TERTIARY 1 % — nezávisle na skóre. PRIMARY se skóre 5
dostane stejných 8 % jako PRIMARY se skóre 10.

**Spec:**

```
target_pct = tier_cap × score / 10          # Gomesova vlastní čísla: 10→10 %, 1→1 %
target_pct = min(target_pct, tier_cap)
```

Volitelně přesnější varianta, která zapojí i válce (kánon §4b) — velikost podle toho, o kolik je
akcie levnější, než si zaslouží: `tier_cap × (score − deserved) / (10 − deserved)`, floor 0.

**A jedna zvláštní klauzule navíc (50:00):** v Yellow Alertu jde plně oceněná pozice na **NULU**, ne
na 1 %. *"Especially in a yellow alert — zero. Why should I own a stock that's fully valued in a
market that's likely to go down? There's no upside in that. High risk, low reward."*

### V3. Stupeň semaforu není jen valuace. Je to valuace × ZNALOST PŘÍČINY. ✅ HOTOVO 2026-08-24

Tohle je nejhlubší věc ve videu a řeší otevřenou mezeru #2 kánonu způsobem, který článek nikde
neuvádí. Gomes definuje stupně podle toho, **co ví**, ne podle toho, jak je draho (13:54–15:18):

| Stupeň | Definice z videa | Osa |
|--------|------------------|-----|
| 🟡 YELLOW | *"I don't know what's going to cause the market to drop, but something's going to, because the market's too expensive right now. **Most of my alerts are going to be yellow.**"* | jen valuace, žádný katalyzátor |
| 🟠 ORANGE | COVID: *"I knew it was bad. I just didn't know **how** bad, because frankly I'm not a biologist."* | katalyzátor znám, **rozsah neznámý** |
| 🔴 RED | *"That is when I know **exactly** what's happening, why it's happening, and how severe it is. And it's bad."* 2× za 30+ let (konec 1999, půlka 2007) | katalyzátor i rozsah znám |

**Důsledek, který mění architekturu:** valuační měřidlo **nikdy nemůže legitimně vyrobit ORANGE ani
RED**. Z-skóre neví, co se ve světě děje. U horní linie bez pojmenovaného katalyzátoru je to podle
Gomese **YELLOW**, ne oranžová.

**Stav v kódu:** `POSITION_ALERT[AT_UPPER_LINE] = "ORANGE"` (`app/services/market_gauge.py:94`).
Měřidlo eskaluje na oranžovou z pouhé valuace. `market_watch.py` smí semafor jen přitvrdit — takže
tahle chyba **projde automaticky** a rozjede oranžovou alokaci (25/35/40) bez jediného katalyzátoru.

**Spec:**
- `POSITION_ALERT[AT_UPPER_LINE] → "YELLOW"`. Měřidlo má obor hodnot `{GREEN, YELLOW}`. Tečka.
- Nová entita `MarketCatalyst`: `{description, identified_at, severity_known: bool, expected_end}`.
  `severity_known == False → ORANGE`; `True ∧ severe → RED`.
- ORANGE/RED **bez** živého katalyzátoru je nevalidní stav → aplikace hlásí "semafor tvrdí oranžovou,
  ale není zapsané proč" a navrhne návrat na valuační stupeň. Tohle je zároveň jediná
  **de-eskalační** logika, která dnes v aplikaci úplně chybí.
- Základní sazba je YELLOW (*"most of my alerts are going to be yellow"*) — ne GREEN. Dobrá
  kalibrace pro varování "semafor je GREEN a nikdo se na něj 4 měsíce nepodíval".

---

## TIER 2 — chybějící mechaniky s přesnou specifikací

### V4. Výjimka "getting paid to wait" v Yellow — a protipříklad VTSI, který ji ohraničuje

Kánon i kód berou non-GREEN jako tvrdý zákaz nákupu. Gomes má výjimku (37:05):

> *"No speculative and no wait-time stocks during a yellow alert, **unless Money Mark tells you this
> is an exception**. There will be companies that I will say: this stock is now so cheap that it
> doesn't matter if we go into a recession, it doesn't matter if they're going through a rough patch
> — the stock is just so cheap that it's going to **pay us to wait**. That's a phrase my mentor
> taught me. The stock has to have **exceptional value** for us to do that."*

A hned protipříklad, který tu výjimku ohraničuje — VTSI (40:15–41:38):

> *"Once we hit yellow alert, it didn't matter to me anymore how low the stock would get. **This is a
> 10. I still didn't buy it at a 10.** Why? Even though it's a 10 on the chart, it's a yellow alert,
> and this company is in a **rough patch**. I happen to know this rough patch will probably persist
> for the next six months because of their dealings with the government. The company itself has told
> us to expect maybe six months of a rough patch. So we just stay out of the way. Can the stock go
> up? Yes. But we're not here to guess. We're here to take the highest-probability bets."*

Není to detail: **VTSI je v kánonu §8a živý OFFICIAL pick se skóre 10.00 pod green line.** Přesně ten
případ.

**Stav v kódu:** `check_buy_guard` vrací `Gate.MARKET_NOT_GREEN` pro cokoli ≠ GREEN, bez výjimky.
V dlouhém žlutém trhu (což je Gomesův základní stav) aplikace nevygeneruje ani jeden nákup celý rok
— a tím propásne přesně ty CTLP-za-$3 situace, kvůli kterým Level-3 mechanika existuje. Přísnější
než Gomes není bezpečnější; je to jiná chyba.

**Spec — úzce zavřená branka `EXCEPTIONAL_VALUE`, jen v YELLOW (nikdy ORANGE/RED):**
1. band == `POD_ZELENOU` (cena pod green line), tj. skóre na stropu 10, a
2. válce známé a ≥ podlaha (kvalita ověřená), a
3. `lifecycle_phase != WAIT_TIME`, a
4. **`rough_patch == False` NEBO `rough_patch_until == None`** — otevřený rough patch se známým
   koncem nákup zakáže bez ohledu na skóre (pravidlo VTSI), a
5. zapsané ruční potvrzení člověka s odůvodněním (výjimka nesmí být automatická — Gomes ji vyhlašuje
   jmenovitě: *"unless Money Mark tells you"*).

### V5. Chase guard — vstupní cena picku a jeho stáří ❌ MISSING

23:25–25:07, řečeno dvakrát a s čísly:

> *"Mark owns this one, that one, that other one, I'm gonna buy them all today. **That's dumb.**
> I might be getting ready to sell that pick and you're just buying it. **It might already be up
> 186%.**"* … *"Buy when I buy, sell when I sell, **as close to the price as I initiate at**. Don't
> go chasing a stock up 10 or 20%. If you pay 20% more than I did, and then when I sell it you sell
> 20% lower than that…"*

**Stav v kódu:** nikde se neporovnává dnešní cena s cenou, **za kterou analytik pick vydal**.
`breakout_watchlist.py:288` řeší drift očekávaného zisku, což je jiná věc. Chybí `pick_price`
a `pick_date` jako first-class údaje signálu.

**Spec:** `chase_pct = (price − pick_price) / pick_price`. Varování > 10 %, blok > 20 % (jeho vlastní
čísla). Na obrazovce věta typu *"tenhle pick je od vydání +186 % — nekupuješ jeho vstup."* Tohle je
druhá polovina mezery #14 kánonu a pro uživatele, který kopíruje analytika, je to přímo
důvěryhodnostní funkce.

### V6. Detektor mrtvých peněz — Wait Time jako POZOROVANÝ FAKT, ne klíčové slovo ❌ MISSING

52:16–53:01:

> *"What's worse is not just that you're losing money — **even if the stock stays flat you're not
> making money. That money isn't working for you. Your money is on vacation.** That's not how to
> become a millionaire, keeping your head just above water. That's one step away from drowning."*

Aplikace dnes pozná Wait Time **jen z textu**, který o té firmě někdo napsal. Gomes ho tady definuje
jako měřitelnou vlastnost portfolia. Pro uživatele, který se k appce vrátí po 3,5 měsíci
(viz `akcion-trust-triage`), je tohle nejpravděpodobnější reálný únik kapitálu, protože nevyžaduje,
aby někdo něco řekl — stačí, že se nic nestalo.

**Spec:** označ pozici jako `WAIT_TIME_BY_EVIDENCE`, když `držená ≥ 9 měsíců ∧ |celkový výnos| < 10 %`
(třetí noha `∧ skóre se nezlepšilo` je použitelná až jak poroste deník skóre — ten běží od
23. 8. 2026, viz `akcion-score-journal-opened`; první dvě nohy fungují dnes). Nesmí to sahat na fázi
cyklu (V1) — je to samostatný příznak "kapitál na dovolené" s návrhem na realokaci.

### V7. Odjištění hedge u dna — RWM je ZDROJ nákupní síly, ne trvalá alokace ❌ MISSING

42:33–44:28:

> *"After the market dropped enough — I didn't call the bottom — I said: time to start buying stocks.
> (…) You would have a huge profit on RWM, which you could then sell because, let's face it, the
> market's low. **Why do we want to hedge? To buy the cheap.**"*

A protipříklad: *"You got $100,000, an orange alert hits, you keep all your stocks, your money drops
from a hundred thousand to fifty thousand. You're like: man, I wish I had money to buy those cheap
stocks."*

**Stav v kódu:** `cash_hedge.py` počítá cílové nohy BOXX/RWM pro daný stupeň, ale **nic neříká, kdy
hedge zavřít a co s výtěžkem**. Chybí celá druhá půlka manévru.

**Spec:** při de-eskalaci (ORANGE→YELLOW→GREEN) nebo když měřidlo hlásí `AT_LOWER_LINE` (ten stav už
existuje, dnes je to jen popisek) vygeneruj explicitní akci: *prodej RWM → nasaď do jmen na/pod green
line*, se seznamem konkrétních tickerů z ladderu.

### V8. Skóre má přesahovat pásmo. Kód ho ořezává. 🟡 DRIFT

12:00–12:38:

> *"These are **not technical lines**, as you can see, because the stock actually became overvalued
> at one point in time, eventually dropped and became undervalued, and even **broke up above or
> below my lines**. This just means it's become **more** overvalued, and [below] just means it's
> become **more** undervalued."*

**Stav v kódu:** `calculate_rr_score` (`gomes_logic.py:542`) ořezává na `[top_score, 10]`. Dvě pozice
se skóre 10.00 vypadají identicky, ale v kánonu §8a je VTSI na 3.18 proti green line 5.00 (**−36 %
pod čarou**), zatímco AMPL je na 8.10 proti 8.50 (−4,7 %). Pod score-proporcionálním sizingem (V2) by
dostaly stejnou váhu, což je špatně.

**Spec:** nech `rr_score` ořezané (parita s trackerem, matematiku neměnit) a **přidej** `rr_extension`
— stejný logaritmický vzorec bez clampu. `> 10` = o kolik bodů škály je cena pod green, `< 0` = nad
red. Použij na řazení, rozřazení při shodě skóre v sizingu a na příznak "generační". **Nikdy** na
band enum.

---

## TIER 3 — invarianty a brzdy

### V9. Oranžový hedge je POMĚR, ne procento

42:12: *"If you have $10,000 that you keep in your stocks, make sure you have **at least $10,000 in
RWM** to protect those positions."* → invariant `hedge_value ≥ equity_value` v ORANGE.
`ALLOCATIONS[ORANGE] = (25, 35, 40)` (`gomes_logic.py:244`) ho splňuje náhodou (40 ≥ 25); kdokoli
zvýší stocks_pct na 45 ho tiše rozbije. Udělej z toho odvozenou hodnotu / assert, ne dvě nezávislé
konstanty.

### V10. TLT není hedge — kontrola MECHANISMU u náhradního nástroje

46:25–48:32, odpověď na živý dotaz, s daty: *"TLT goes up because **interest rates** are going down,
not because the market is going down. (…) In an environment like we are in right now [inflace brání
snižování sazeb] I specifically told people **do not**."* Čísla od konce listopadu: RWM +39 % (tehdy
+22 %), TLT −4 %.

Pozitivní pravidlo: hedge index musí **sedět na velikost firem v portfoliu** — *"I make my money on
small-cap stocks, so I want my insurance to also be small caps."* A důvod, proč to funguje
asymetricky: *"I only own good companies; I'm betting against 2,000 companies good, bad and ugly, so
generally I will outperform that index."*

`cash_hedge.py` už řeší dostupnost RWM v EU — tohle je přesně ta chybějící část: pravidlo pro výběr
náhrady. Přidej seznam **odmítnutých nástrojů s důvodem** (TLT: řízený sazbami, ne akciemi; selže
právě když inflace brání snižování) a kontrolu shody velikosti firem.

### V11. Rozpočet tahů: ~20 za rok

40:15: *"This is over the course of **years**. This is not day trading. (…) **I make maybe 20 moves
at most per year.**"* Plus *"you shouldn't be trading unless you've proven yourself to be a great
trader. I'm not. When I make trades, I generally lose, so I avoid them."*

`emotional_brakes.py` má `check_burst` (frekvence v krátkém okně), ale roční rozpočet ne. Pro
investora bez času je počítadlo "X z 20 tahů letos" lépe kalibrovaná brzda než burst okno — a je to
číslo, které Gomes řekl natvrdo.

### V12. Žebřík výběru zisku + opakované okružní jízdy

Dvě věci, které dnešní binární `Trigger` enum (`gomes_logic.py:1504`) nepokrývá:

- **Žebřík:** AirTest — *"from two to five you doubled your money, to ten quadrupled, taking profits
  along the way. At around fifteen I said: let's take a lot off the table because we've made five
  times our money."* Postupné částečné výběry, ne jedno rozhodnutí. Nabídni **N dalších spouštěcích
  cen** s navrženým podílem, ne jednu `take_profit_above`.
- **Okružní jízda:** VTSI — *"we rode this thing multiple times"*, roky nákup/prodej mezi čarami.
  Plný výstup nesmí pick vyřadit; má se vrátit na watchlist s re-entry cenou = `buy_below`. A
  `emotional_brakes.check_reentry` (`:142`) musí rozlišit **návrat po ukázněném výstupu na/pod green
  line** (to je metoda) od **revenge-buy** (to je relaps). Dnes brzdí obojí stejně.

### V13. Spekulativní tier má dva detekovatelné znaky

30:23: *"A biotech company developing a drug that might cure cancer — there's no guarantee they're
going to be successful"* a *"a company that is rumored to get bought out — we don't know if that's
actually going to happen. It's just a rumor, just a hope."* → **binární regulatorní/klinický výsledek**
a **M&A fáma** jsou dva konkrétní markery pro automatické zařazení do TERTIARY (≤ 2 %).

### V14. Yellow spouští okamžitou likvidaci, ne postupnou

30:23: *"**The second the yellow alert triggers, I'm out.** No more speculative stocks."* Plus
sekvence, odkud se berou peníze na hedge (39:34): *"You sold your speculative stocks. You sold your
wait-time stocks. You now have a bunch of cash. You can put some of that cash into RWM to protect
the stocks that you actually keep."* → přechod na YELLOW má vygenerovat **seznam k okamžitému
prodeji** v tomhle pořadí, ne jen změnit cílová procenta.

---

## POTVRZENO — nesahat, ať to nikdo "neopraví" zpátky

**P1. Weinstein na 0 % váhy je správně — a video dává přesné pořadí faktorů.** 54:09 Gomes vyjmenuje,
podle čeho rozhoduje: (1) profil firmy — core vs. spekulace, (2) stádium cyklu, (3) valuace → R/R
graf, (4) fundamentální momentum = válce, a *"then **lastly and least importantly**, how much momentum
does the stock have, what does the chart look like."* Následuje varování, které patří přímo do textu
badge: *"the reason a company like CTLP stopped going down is not because of the chart — it's because
a multi-millionaire and his friends said this stock is too cheap. (…) **We may have been the ones
selling the stock to you right before it starts going down.**"* Dnešní řešení (informativní
`technical_overlay_warning`, nula do skóre, nikdy neblokuje) tomu odpovídá přesně. Ale má být
**poslední na seznamu**, ne schované — Gomes ten faktor nezakazuje, jen ho řadí nakonec.

**P2. Doubling rule je nezávislé na grafu.** 29:14: *"It doesn't matter the three-point rule, the
ten-point rule, any of that stuff. It doesn't matter where it is on the chart. What matters is I've
just doubled my money."* `apply_doubling_rule` (`gomes_logic.py:690`) počítá čistě z entry price ✓.
Dva nezávislé spouštěče výběru zisku spojené OR: 3 body na škále **nebo** 2× na vstupu.

**P3. OFFICIAL / NOT OFFICIAL ↔ portfolio / watchlist.** Potvrzeno pasáží s prstýnkem (50:42):
*"unofficial picks — I own the stock but it's not an official pick, I'm going to put less money in
those. Like the girl that you're dating, but you're not quite ready to put that ring on her finger."*
Potvrzuje i to, že SECONDARY má mít menší velikost než PRIMARY.

**P4. BOXX/RWM jako reálné nástroje** (`cash_hedge.py`) — mezera #6 kánonu je zavřená. 16:40:
*"Over half of my money is in cash, actually in **money market funds, earning 4%**, risk-free."*

---

## Co z videa je poznatek, ne funkce

- **Cíl ~40 % ročně** (18:09), zdvojnásobení každé 2 roky, $10k → $1M za 14 let. Uživatelův cíl je
  20 % (`akcion-user-context-and-goal`) — číslo se nepřenáší, ale přenáší se **asymetrie ztráty**
  (45:29): dvakrát −40 % udělá z $1M **$360k**; dvakrát +40 % udělá **~$2M**. Šestinásobek z rozdílu
  dvou let. To je celý důvod, proč semafor existuje, a je to jediná věta, která obhájí sezení
  v hotovosti před netrpělivým uživatelem.
- **PE je k ničemu** (06:44): hodnota se počítá z **prognózy budoucích zisků** přes dopředný provozní
  model + investigativní žurnalistiku, ne z násobku. To je původ green/red linií — nejsou to
  technické čáry, jsou to výstupy DCF modelu.
- **Dva hlavně brokovnice** (23:00): výnos má dva zdroje — (1) diskont, za který kupuješ, (2) růst,
  který firma dodá. Rozklad potenciálního zisku na "uzavření diskontu k red line" vs. "posun linií
  růstem" je dobrý UI prvek.
- **Vlastní expertíza vs. cizí** (10:45): *"I'm not an expert on many industries that I invest in.
  I have to find the experts. I'm an expert on evaluating how much stocks are worth."* AirTest →
  investigativně dohledáno, že zákazník je Tesla. Podpírá návrh `thesis_monitor` /
  `claim_extraction`: u každé teze evidovat **otevřenou otázku** a **koho by se šlo zeptat**.
- **Žebříček kompetence** (23:25): úroveň 1 = "kupuj, když kupuju, prodávej, když prodávám, za moje
  ceny". Vlastní sizing se odemyká až potom. Pro uživatele s MS a bez času je "zrcadlový režim"
  správný výchozí stav, ne omezení.
- **Tři kritéria důvěryhodnosti zdroje** (02:51): pravé jméno, ověřitelné kvalifikace, **veřejný**
  track record. Použitelné jako rubrika na `source_key` — Gomes všechna tři splňuje, Discord
  Breakout Investors ani jedno. To je nezávislé odůvodnění dnešní asymetrie
  (`breakout_band.py`: Breakout smí nákup zastavit, nikdy povolit).

---

## Co je hotové (2026-08-24)

| Věc | Kde to teď žije |
|-----|-----------------|
| **V1** ráčna + `rough_patch` | `lifecycle_rubric.apply_ratchet()`, sloupce `stock_lifecycle.phase_reached` / `rough_patch*` (migrace `add_lifecycle_ratchet.sql`), vynucené v `lifecycle_intake.confirm()` i v `StockLifecycleClassifier.classify(reached=…)`. Protiváha: nová branka `ROUGH_PATCH_STALE_QUALITY` — útlum, který začal po potvrzení válců, ruší platnost toho potvrzení pro nákup. Testy `test_lifecycle_ratchet.py`. |
| **V2** sizing podle skóre | `PositionSizingEngine.target_pct(ceiling, score, market_alert=…)`; obě místa v `daily_actions` (nákup i dokup) míří na cíl, ne na strop. Žlutá klauzule: plně oceněná pozice mimo zelenou jde na nulu. Testy `test_score_proportional_sizing.py`. |
| **V3** semafor = valuace × příčina | `market_gauge.GAUGE_MAX_ALERT = "YELLOW"` (měřidlo už nesmí navrhnout oranžovou), nový `market_catalyst.py`, sloupce `market_status.catalyst_*` (migrace `add_market_catalyst.sql`), PUT `/market-status` odmítne ORANGE/RED bez zapsané příčiny a GET vrací, jestli stupeň na něčem stojí a jak je to staré. Testy `test_market_catalyst.py`. |

**Migrace se musí pustit:** `python apply_migration.py add_lifecycle_ratchet` a
`python apply_migration.py add_market_catalyst` z `backend/`. Do té doby modely mají sloupce,
které databáze nezná.

---

## Pořadí prací

| # | Věc | Proč první | Kde |
|---|-----|-----------|-----|
| ~~1~~ | ✅ V1 Gold Mine ráčna + rough patch | Blokuje nákupy přesně v nejlepších momentech | `gomes_logic.py:331,377`, `lifecycle_rubric.py:203` |
| ~~2~~ | ✅ V3 Semafor: měřidlo jen GREEN/YELLOW + katalyzátor | Automatická falešná eskalace na oranžovou alokaci | `market_gauge.py:94` |
| ~~3~~ | ✅ V2 Sizing podle skóre | Každá pozice je dnes špatně velká | `gomes_logic.py:772` |
| 4 | V5 Chase guard | Levné, přímo chrání peníze při kopírování picku | nový sloupec + Buy Guard |
| 5 | V4 Výjimka výjimečné hodnoty (+ pravidlo VTSI) | Odemkne nákupy ve žlutém trhu, závisí na V1 | `gomes_logic.py:948` |
| 6 | V6 Detektor mrtvých peněz | Nejpravděpodobnější reálný únik u nečinného uživatele | nová služba |
| 7 | V8 `rr_extension` | Předpoklad, aby V2 správně řadila | `gomes_logic.py:542` |
| 8 | V7 Odjištění hedge | Chybí druhá půlka manévru | `cash_hedge.py` |
| 9 | V9–V14 | Invarianty a brzdy | dle sekcí |

---

*Vytvořeno 2026-08-24 z Gomesova videa `9PhWx9rzIaU`. Doplňuje `GOMES_METHODOLOGY_CANON.md`,
nenahrazuje ho.*

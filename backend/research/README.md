# backend/research

Offline laboratoř nad Markovým listem „Priority Ideas". **Není součástí služby.**

Cíl: z 231 datovaných vstupů za 12 let spočítat, jak vypadá jeho typický vstup, a
umět proti tomu porovnat vlastní nález. Plus pár věcí, které z těch dat vypadnou po
cestě (proč ve skutečnosti prodává, ověření semaforu, historie každého jména).

## Jediné pravidlo, které se nesmí porušit

**`backend/app/` nikdy neimportuje `backend/research/`.** Opačný směr je v pořádku a
je záměrný — sdílený výpočet vlastností žije v `app/services/entry_features.py` a
výzkum si ho importuje, aby kandidáta i referenci počítal jeden a týž kód. Hlídá to
`backend/tests/test_research_layout.py`.

Aplikace čte jen **commitnuté ploché soubory** v `backend/app/data/`, které sem
publikuje `research/publish.py`. Nikdy nespouští nic z `research/`.

## Co se commituje a co ne

| | |
|---|---|
| `data/` | **commitnuto** — přepis listu a lidský úsudek nad ním |
| `out/` | **v .gitignore** — každý odvozený artefakt, včetně cache barů |

`out/` je gitignorovaný, protože všechno v něm je funkcí (commitnuté vstupy +
yfinance k danému dni), a yfinance přepisuje očištěnou historii **zpětně** při každém
splitu a dividendě. `app/services/score_outcomes.py` odmítá cachovat očištěné ceny
přesně z tohohle důvodu. Výjimka je `data/reconciliation_decisions.csv` — lidská
rozhodnutí musí přežít `rm -rf out/`.

## Spuštění

Interpret je **systémový Python 3.12**, ne kořenový `.venv/` (ten je zastaralý —
nemá yfinance ani SQLAlchemy):

```
C:\Users\reath\AppData\Local\Programs\Python\Python312\python.exe
```

```bash
cd backend
python -m research.batches      # navrhne hromadné uzávěrky, nic nezapisuje
python -m research.reconcile    # smíří ceny s yfinance, píše out/
python -m research.analyse      # hypotézy
```

Testy: `python -m pytest tests/test_research_*.py` z `backend/`, systémovým Pythonem.

## Závislosti

**Žádné nové.** Jen stdlib + `pandas` + `yfinance`, obojí už v
`backend/requirements.txt`. Scipy/sklearn/statsmodels jsou v runtime interpretu
nainstalované, ale záměrně se nepoužívají: `app/services/market_gauge.py` fituje OLS
přes `sum()` a `statistics.pstdev`, a to je domácí styl. Percentily, medián i
bootstrap jsou pár desítek řádků nad `statistics` a `random`.

## Zdroj dat a jeho meze

`data/priority_ideas.csv` je doslovný přepis PDF „Priority Ideas" z 24. 8. 2026.
V hlavičce toho listu stojí *„For the exclusive use of Mark Gomes"* — je to jeho
sledovací tabulka, ne veřejná data. Repo je soukromé a nic z toho se neserví přes
HTTP (`app/main.py` nemá žádný `StaticFiles` mount). **Nepublikovat ven.**

Čtyři věci, které o tom listu musí vědět každý, kdo z něj počítá:

1. **„Pause Interest" často není prodejní rozhodnutí, ale úklid.** 2016-04-25 zavírá
   18 jmen naráz, 2015-06-10 čtrnáct, 2025-01-03 dvanáct. Sloupec `exit_kind`
   v `data/priority_ideas_labels.csv` to odděluje.
2. **Ceny nejsou očištěné o splity.** Jen dva řádky (NVDA, SMCI) nesou „Split Adj'd".
   Sloupec `peak_return_live_pct_unusable` je tím prokazatelně zkažený (MRIN 22394 %,
   GSAT 12850 %) a **nepoužívá se** — nahradí ho přepočet z barů.
3. **Přežití.** Zhruba 40 % tickerů z let 2014-2019 už neobchoduje. yfinance na ně
   vrátí prázdno.
4. **`LATEST NOTES` je poslední poznámka, ne poznámka při výstupu.** Několik řádků
   nese komentář datovaný roky po uzavření (QIPT zavřený 3. 1. 2025 má poznámku
   z 15. 12. 2025 „Acquired !"). Proto se `exit_reason` kóduje jen tam, kde ta
   poznámka výstup věrohodně popisuje, jinak `UNKNOWN`.

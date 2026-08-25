# WhatsApp výtažky — archiv

Ručně vložené výtažky ze skupiny Breakout Investors, pročištěné do čitelné
podoby. Slouží jako paměť mezi sezeními: co kdo o kterém tickeru řekl, jaké
číslo kde vzniklo a co se z toho smí (a nesmí) zapsat do Akcionu.

## Rejstřík

| Soubor | Období | Témata |
|---|---|---|
| [2026-08-18_19.md](2026-08-18_19.md) | 18.–19. 8. 2026 | DBOX (model FY27, Q4 slate, Cinemark), IDN (wealth management PR), Elite Call notes |
| [2026-08-25.md](2026-08-25.md) | 25. 8. 2026 | GKPRF/Gatekeeper (Genetec/MTA integrace, tři buckety byznysu ~300M, MDC ARR škálování, Doug Diamond o možné akvizici) — video ověřeno plným přepisem |

## Pravidla groomování

Platí pro každý další výtažek, ať ho zpracovává kdokoli.

1. **Žádná telefonní čísla.** Ani v dokumentu, ani v commitu. Export má tvar
   `[15:11, 18. 8. 2026] +XX (XXX) XXX-XXXX: text` — autor *je* číslo a to se
   maže dřív, než se čehokoli dotkne (`whatsapp_intake.strip_phone_numbers`).
2. **Číselník je mimo git.** Mapování telefonní číslo -> jméno žije
   v `whatsapp_contacts.local.json` v kořeni repa, který je v `.gitignore`.
   Odtud se slotům dávají jména bez ptaní. Do archivu i do DB jde jméno,
   číslo zůstává tam.
3. **Autoři jsou sloty, ne jména.** Každý odlišný autor dostane písmeno podle
   pořadí prvního výskytu (A, B, C…), stejně jako
   `whatsapp_intake.parse_export_format`. Jména do slotů doplňuje **člověk**,
   ne odhad z textu — proč, stojí v docstringu té funkce („This is great
   @~Robert Mock !!" jmenuje někoho, kdo tu zprávu psát nemusel).
4. **Odhad identity se smí zapsat, ale musí být označený.** V tabulce slotů
   sloupec „Důkaz" a „Stav" (`potvrzeno` / `odhad`). Odhad se nesmí použít jako
   `source_key` pro zápis tvrzení do DB, dokud ho Tomáš nepotvrdí.
5. **Cizí citace patří citovanému, ne pisateli.** WhatsApp odpověď zkopíruje
   text původní zprávy nad novou. V groomované verzi se duplikát zahazuje a
   zůstane jen `↩ reakce na …`.
6. **Číslo si nese původ.** U každého čísla se píše, jestli je to firemní údaj,
   model analytika, nebo dojem. Model analytika není fundament.
7. **Chybějící údaj zůstane chybějící.** PR bez dolarové částky se nesmí
   proměnit v signál. Viz opakovaná vada popsaná v paměti
   „Missing Data Becomes Verdicts".
8. **Vtipy, rapy a reakce se vynechávají** — jen se u nich poznamená, že tam
   byly, ať je vidět, že výtažek není osekaný o obsah.

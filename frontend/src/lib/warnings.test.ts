/**
 * Testy skládání varování.
 *
 * Nejdůležitější test je ten poslední: neznámé varování se nesmí ztratit.
 * Celá aplikace stojí na tom, že chybějící údaj se pojmenuje místo aby se
 * nahradil výchozí hodnotou — filtr, který tiše zahodí větu, které
 * nerozumí, by ten princip obrátil naruby.
 */

import { describe, expect, it } from 'vitest';
import { extractTickers, groupWarnings } from './warnings';

/* Skutečná varování z běžící aplikace, 23. 8. 2026. */
const SKUTECNA = [
  'CHYBÍ NÁKUPNÍ CENA: US40053W1018 — doplň ji v detailu pozice; P/L a pravidlo zdvojnásobení do té doby nehlídám',
  'CHYBÍ NÁKUPNÍ CENA: CA00654B1040 — doplň ji v detailu pozice; P/L a pravidlo zdvojnásobení do té doby nehlídám',
  'CHYBÍ NÁKUPNÍ CENA: US90138A1034 — doplň ji v detailu pozice; P/L a pravidlo zdvojnásobení do té doby nehlídám',
  'NEZNÁMÁ KVALITA u 15 pozic (US40053W1018, DBO.TO, ECOR, GSI.V, INFU, IMP.V, IRIX, IZEA, KUYA.V, RDCM, SMSI, VTSI, DAIO, CA00654B1040, US90138A1034) — chybí fáze i konvikční skóre, při stupni žlutá je neposoudím; rozhodni sám',
  'MĚNA NESEDÍ S BURZOU: IMP.V (EUR→CAD?) — hodnota v CZK je o tenhle poměr vedle; oprav měnu v detailu pozice',
  'MĚNA NESEDÍ S BURZOU: KUYA.V (EUR→CAD?) — hodnota v CZK je o tenhle poměr vedle; oprav měnu v detailu pozice',
  'STARÁ CENA: US40053W1018 naposledy aktualizována 2026-07-26 — ověř před obchodem',
  'STARÁ CENA: CA00654B1040 naposledy aktualizována 2026-07-26 — ověř před obchodem',
  'STARÁ CENA: US90138A1034 naposledy aktualizována 2026-07-26 — ověř před obchodem',
];

describe('extractTickers', () => {
  it('vezme ticker za dvojtečkou', () => {
    expect(extractTickers('STARÁ CENA: DBO.TO naposledy aktualizována'))
      .toEqual(['DBO.TO']);
  });

  it('zvládne ISIN, který je dlouhý a má číslice', () => {
    expect(extractTickers('CHYBÍ NÁKUPNÍ CENA: US40053W1018 — doplň ji'))
      .toEqual(['US40053W1018']);
  });

  it('nesplete si závorku s poznámkou o měně za ticker', () => {
    // „(EUR→CAD?)" není seznam tickerů, jen vysvětlení.
    expect(extractTickers('MĚNA NESEDÍ S BURZOU: IMP.V (EUR→CAD?) — hodnota'))
      .toEqual(['IMP.V']);
  });

  it('rozebere seznam v závorce u souhrnného varování', () => {
    const t = extractTickers('NEZNÁMÁ KVALITA u 3 pozic (DBO.TO, ECOR, GSI.V) — chybí fáze');
    expect(t).toEqual(['DBO.TO', 'ECOR', 'GSI.V']);
  });

  it('vrátí prázdno, když tam ticker není', () => {
    expect(extractTickers('Něco se pokazilo')).toEqual([]);
  });
});

describe('groupWarnings', () => {
  it('z devíti vět udělá čtyři skupiny', () => {
    const g = groupWarnings(SKUTECNA);
    expect(g).toHaveLength(4);
    expect(g.map((x) => x.kind)).toEqual([
      'BEZ_HODNOCENI',
      'MENA',
      'BEZ_NAKUPNI_CENY',
      'STARA_CENA',
    ]);
  });

  it('řadí podle toho, co nejvíc blokuje', () => {
    // Chybějící hodnocení umlčí celý denní seznam, takže patří nahoru
    // bez ohledu na to, v jakém pořadí varování přišla.
    const g = groupWarnings([...SKUTECNA].reverse());
    expect(g[0].kind).toBe('BEZ_HODNOCENI');
    expect(g[g.length - 1].kind).toBe('STARA_CENA');
  });

  it('sloučí tři chybějící nákupní ceny do jedné položky se třemi tickery', () => {
    const g = groupWarnings(SKUTECNA);
    const ceny = g.find((x) => x.kind === 'BEZ_NAKUPNI_CENY')!;
    expect(ceny.count).toBe(3);
    expect(ceny.tickers).toEqual(['US40053W1018', 'CA00654B1040', 'US90138A1034']);
    expect(ceny.raw).toHaveLength(3);
  });

  it('u souhrnného varování vezme počet z textu, ne počet vět', () => {
    const g = groupWarnings(SKUTECNA);
    const kvalita = g.find((x) => x.kind === 'BEZ_HODNOCENI')!;
    // Jedna věta, ale mluví o patnácti pozicích.
    expect(kvalita.raw).toHaveLength(1);
    expect(kvalita.count).toBe(15);
    expect(kvalita.tickers).toHaveLength(15);
  });

  it('ke každé skupině řekne, co kvůli ní aplikace nemůže', () => {
    for (const g of groupWarnings(SKUTECNA)) {
      expect(g.consequence.length).toBeGreaterThan(20);
    }
  });

  it('nezdvojí ticker, když přijde ve dvou větách', () => {
    const g = groupWarnings([
      'STARÁ CENA: DBO.TO naposledy aktualizována 2026-07-26 — ověř',
      'STARÁ CENA: DBO.TO naposledy aktualizována 2026-07-27 — ověř',
    ]);
    expect(g[0].tickers).toEqual(['DBO.TO']);
  });

  it('NEZAHODÍ varování, kterému nerozumí', () => {
    // Tohle je ten test, kvůli kterému soubor existuje. Kdyby se neznámé
    // varování tiše zahodilo, aplikace by mlčela přesně o tom, o čem má
    // mluvit nejvíc — o něčem novém, s čím se nepočítalo.
    const g = groupWarnings([
      ...SKUTECNA,
      'ÚPLNĚ NOVÝ DRUH POTÍŽE: něco, co nikdo nečekal',
    ]);
    const jine = g.filter((x) => x.kind === 'JINE');
    expect(jine).toHaveLength(1);
    expect(jine[0].label).toContain('ÚPLNĚ NOVÝ DRUH POTÍŽE');
  });

  it('neznámá varování jsou až za známými', () => {
    const g = groupWarnings(['NĚCO NOVÉHO: xyz', ...SKUTECNA]);
    expect(g[g.length - 1].kind).toBe('JINE');
  });

  it('prázdný vstup dá prázdný výstup', () => {
    expect(groupWarnings([])).toEqual([]);
  });
});

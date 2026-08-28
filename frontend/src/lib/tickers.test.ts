/**
 * Párování jedné firmy napříč burzami.
 *
 * Případy pocházejí z reálného portfolia k 23. 8. 2026: KUYA.V/KUYAF má dva
 * řádky s různým skóre, GSI.V/GKPRF má skóre jen pod kanadským tickerem,
 * IMP.V/ITMSF nemá skóre ani pod jedním.
 */

import { describe, expect, it } from 'vitest';
import { canonicalOf, canonicalSet, pickAnalysis } from './tickers';

const row = (
  ticker: string,
  canonical: string,
  source: 'GOMES' | 'OTHER' | null,
  score: number | null
) => ({
  ticker,
  canonical_ticker: canonical,
  source_key: source,
  conviction_score: score,
});

describe('canonicalOf', () => {
  it('bere kanonický ticker z API', () => {
    expect(canonicalOf({ ticker: 'KUYA.V', canonical_ticker: 'KUYAF' })).toBe('KUYAF');
  });

  it('bez něj použije samotný ticker', () => {
    // Většina papírů má jediný listing a je sama sobě kanonická. Chybějící
    // pole není chyba.
    expect(canonicalOf({ ticker: 'aehr' })).toBe('AEHR');
  });

  it('z ničeho nedělá klíč', () => {
    expect(canonicalOf(null)).toBe('');
    expect(canonicalOf(undefined)).toBe('');
  });
});

describe('canonicalSet', () => {
  it('dvě burzy jedné firmy jsou jedna položka', () => {
    const set = canonicalSet([
      { ticker: 'KUYA.V', canonical_ticker: 'KUYAF' },
      { ticker: 'KUYAF', canonical_ticker: 'KUYAF' },
    ]);
    expect(set.size).toBe(1);
    expect(set.has('KUYAF')).toBe(true);
  });

  it('prázdný ticker se do sady nedostane', () => {
    expect(canonicalSet([{ ticker: '' }]).size).toBe(0);
  });
});

describe('pickAnalysis', () => {
  const kuyaOther = row('KUYA.V', 'KUYAF', 'OTHER', 7);
  const kuyaGomes = row('KUYAF', 'KUYAF', 'GOMES', 10);
  const gsiOther = row('GSI.V', 'GKPRF', 'OTHER', 5);
  const gsiGomes = row('GKPRF', 'GKPRF', 'GOMES', null);
  const impOther = row('IMP.V', 'ITMSF', 'OTHER', null);
  const impGomes = row('ITMSF', 'ITMSF', 'GOMES', null);

  it('pozice najde analýzu vedenou pod druhou burzou', () => {
    const found = pickAnalysis([kuyaGomes], { ticker: 'KUYA.V', canonical_ticker: 'KUYAF' });
    expect(found).toBe(kuyaGomes);
  });

  it('ze dvou hodnocených řádků vyhraje Gomes', () => {
    const found = pickAnalysis([kuyaOther, kuyaGomes], {
      ticker: 'KUYA.V',
      canonical_ticker: 'KUYAF',
    });
    expect(found?.conviction_score).toBe(10);
  });

  it('nepřijde o skóre, když Gomesův řádek žádné nemá', () => {
    // Přesně případ GSI.V. Slepá přednost zdroje by pětku zahodila a
    // aplikace by tvrdila, že hodnocení chybí.
    const found = pickAnalysis([gsiGomes, gsiOther], {
      ticker: 'GSI.V',
      canonical_ticker: 'GKPRF',
    });
    expect(found?.conviction_score).toBe(5);
  });

  it('když skóre nemá nikdo, ukáže se Gomesův řádek', () => {
    const found = pickAnalysis([impOther, impGomes], {
      ticker: 'IMP.V',
      canonical_ticker: 'ITMSF',
    });
    expect(found).toBe(impGomes);
  });

  it('žádná analýza znamená undefined, ne prázdný řádek', () => {
    expect(
      pickAnalysis([kuyaGomes], { ticker: 'DBO.TO', canonical_ticker: 'DBOXF' })
    ).toBeUndefined();
  });

  it('nepáruje dvě různé firmy', () => {
    expect(
      pickAnalysis([kuyaGomes], { ticker: 'AEHR', canonical_ticker: 'AEHR' })
    ).toBeUndefined();
  });

  it('bez tickeru nevrací nic', () => {
    expect(pickAnalysis([kuyaGomes], null)).toBeUndefined();
  });
});

/**
 * Nálezy — co se nesmí splést na cestě z backendu na obrazovku.
 *
 * Nejdůležitější je `citedFacts`: čip odkazující na fakt, který ve spisu není,
 * by vypadal jako doklad. Backend takový bod neuloží, ale posudek se čte i
 * roky starý a spis se mezitím mohl změnit.
 *
 * Hned za tím je `priceChangePct`. Chybějící cena musí dát `null`, ne nulu —
 * nula tvrdí „nestalo se nic", což je něco úplně jiného než „nevíme".
 */

import { describe, expect, it } from 'vitest';

import type {
  Find,
  FindAssessment,
  FindAttention,
  FindDossier,
  FindFact,
  FindPillar,
  FindPoint,
} from '../api/client';
import {
  attentionLabel,
  attentionRatio,
  attentionTone,
  citations,
  citedFacts,
  conditionalCylinderSentence,
  directionTone,
  evolution,
  factsByLayer,
  layerLabel,
  orderedPillars,
  pillarWidths,
  priceChangePct,
  sortByAttention,
  splitGaps,
  splitSides,
} from './finds';

function fact(id: string, layer = 'GOMES', direction = 'NEUTRAL'): FindFact {
  return { id, layer, text_cs: `věta ${id}`, source: 'zdroj', direction };
}

function dossier(facts: FindFact[]): FindDossier {
  return {
    ticker: 'ABCD',
    symbol: 'ABCD',
    as_of: '2026-08-24T12:00:00Z',
    price_is_stale: false,
    facts,
    gaps: [],
    method: {
      band: 'NEZNAME',
      band_reason_cs: 'Válce neznáme',
      phase_is_proposal: true,
      market_alert_stale: true,
      gate_reason_cs: 'Semafor je žlutá, a metodika nakupuje jen v zelené.',
    },
  } as FindDossier;
}

function point(overrides: Partial<FindPoint> = {}): FindPoint {
  return {
    side: 'PRO',
    headline_cs: 'Tržby rostou',
    body_cs: 'Meziročně o 28 %.',
    fact_ids: ['GOMES-1'],
    canon_ref: '§3',
    canon_text_cs: 'Tři fáze…',
    check_yourself_cs: 'Ve výkazu 10-Q na řádku Revenues.',
    weight: 'PODSTATNY',
    ...overrides,
  };
}

describe('citedFacts', () => {
  it('zahodí id, které ve spisu není — čip nesmí odkazovat do prázdna', () => {
    const d = dossier([fact('GOMES-1')]);
    const found = citedFacts(point({ fact_ids: ['GOMES-1', 'VYMYSLENO-9'] }), d);
    expect(found.map((f) => f.id)).toEqual(['GOMES-1']);
  });

  it('u chybějícího spisu vrátí prázdno, ne výjimku', () => {
    expect(citedFacts(point(), null)).toEqual([]);
  });

  it('zachová pořadí, v jakém bod fakta cituje', () => {
    const d = dossier([fact('GOMES-1'), fact('FUND-1', 'FUNDAMENTY')]);
    const found = citedFacts(point({ fact_ids: ['FUND-1', 'GOMES-1'] }), d);
    expect(found.map((f) => f.id)).toEqual(['FUND-1', 'GOMES-1']);
  });
});

describe('priceChangePct', () => {
  it('spočítá změnu, když jsou obě ceny v téže měně', () => {
    const a = { price_at_assessment: 4, price_currency: 'USD' } as FindAssessment;
    expect(priceChangePct(a, 5, 'USD')).toBeCloseTo(25);
  });

  it('bez dnešní ceny vrátí null, ne nulu', () => {
    const a = { price_at_assessment: 4, price_currency: 'USD' } as FindAssessment;
    expect(priceChangePct(a, null, 'USD')).toBeNull();
  });

  it('bez ceny při posudku vrátí null', () => {
    const a = { price_at_assessment: null, price_currency: 'USD' } as FindAssessment;
    expect(priceChangePct(a, 5, 'USD')).toBeNull();
  });

  it('napříč měnami odmítne počítat — bylo by to o celý kurz vedle', () => {
    const a = { price_at_assessment: 4, price_currency: 'CAD' } as FindAssessment;
    expect(priceChangePct(a, 5, 'USD')).toBeNull();
  });

  it('nulová nebo záporná cena není cena', () => {
    const a = { price_at_assessment: 0, price_currency: 'USD' } as FindAssessment;
    expect(priceChangePct(a, 5, 'USD')).toBeNull();
  });
});

describe('splitSides', () => {
  it('rozdělí body a řadí nejtěžší nahoru', () => {
    const { pro, proti } = splitSides([
      point({ headline_cs: 'a', weight: 'DROBNY' }),
      point({ headline_cs: 'b', weight: 'ROZHODUJICI' }),
      point({ headline_cs: 'c', side: 'PROTI', weight: 'PODSTATNY' }),
    ]);
    expect(pro.map((p) => p.headline_cs)).toEqual(['b', 'a']);
    expect(proti.map((p) => p.headline_cs)).toEqual(['c']);
  });

  it('při stejné váze zachová pořadí', () => {
    const { pro } = splitSides([
      point({ headline_cs: 'prvni' }),
      point({ headline_cs: 'druhy' }),
    ]);
    expect(pro.map((p) => p.headline_cs)).toEqual(['prvni', 'druhy']);
  });

  it('prázdný seznam dá dvě prázdné strany', () => {
    expect(splitSides(null)).toEqual({ pro: [], proti: [] });
  });
});

describe('layerLabel', () => {
  it('nikdy nevrátí syrovou hodnotu z databáze', () => {
    for (const layer of ['GOMES', 'BREAKOUT', 'FUNDAMENTY', 'METODIKA', 'VLASTNI', 'TRH', 'NECO']) {
      expect(layerLabel(layer)).not.toMatch(/^[A-Z_]+$/);
    }
  });

  it('neznámou vrstvu pojmenuje, místo aby ji vypsala', () => {
    expect(layerLabel('XYZ')).toBe('Ostatní');
    expect(layerLabel(null)).toBe('Ostatní');
  });
});

describe('directionTone', () => {
  it('vrací jen třídy z tokenů, nikdy hex ani paletu Tailwindu', () => {
    for (const direction of ['PRO', 'PROTI', 'NEUTRAL', '', null]) {
      const tone = directionTone(direction);
      expect(tone).not.toContain('#');
      expect(tone).toMatch(/^text-(positive|negative|text-muted)$/);
    }
  });

  it('chybějící směr je šedý, ne zelený ani červený', () => {
    expect(directionTone(undefined)).toBe('text-text-muted');
  });
});

describe('factsByLayer', () => {
  it('prázdné vrstvy vynechá — sloupec pomlček není informace', () => {
    const groups = factsByLayer(dossier([fact('GOMES-1'), fact('TRH-1', 'TRH')]));
    expect(groups.map((g) => g.layer)).toEqual(['GOMES', 'TRH']);
  });

  it('drží stálé pořadí: nejdřív člověk, pak zdroje, pak stroj', () => {
    const groups = factsByLayer(
      dossier([fact('METOD-1', 'METODIKA'), fact('VLAST-1', 'VLASTNI'), fact('GOMES-1')]),
    );
    expect(groups.map((g) => g.layer)).toEqual(['VLASTNI', 'GOMES', 'METODIKA']);
  });
});

describe('conditionalCylinderSentence', () => {
  it('bez věty od backendu nic neskládá', () => {
    expect(conditionalCylinderSentence(dossier([]))).toBeNull();
  });

  it('prázdný řetězec je taky nic', () => {
    const d = dossier([]);
    d.method.if_cylinders_cs = '   ';
    expect(conditionalCylinderSentence(d)).toBeNull();
  });

  it('hotovou větu předá beze změny', () => {
    const d = dossier([]);
    d.method.if_cylinders_cs = 'Kdyby válce byly 6 (návrh rubriky, nepotvrzeno)…';
    expect(conditionalCylinderSentence(d)).toContain('nepotvrzeno');
  });
});

describe('evolution', () => {
  const a = (band: string, gate: string) =>
    ({ band, gate_code: gate }) as FindAssessment;

  it('bez posudku to řekne rovnou', () => {
    expect(evolution([]).summary_cs).toBe('Zatím bez posudku.');
  });

  it('jeden posudek není vývoj', () => {
    expect(evolution([a('NAKUP', 'PASSED')]).changed).toBe(false);
  });

  it('když se nic nezměnilo, řekne to místo vymýšlení vývoje', () => {
    const result = evolution([a('NAKUP', 'PASSED'), a('NAKUP', 'PASSED')]);
    expect(result.changed).toBe(false);
    expect(result.summary_cs).toContain('nezměnily');
  });

  it('změnu pásma i brány pojmenuje', () => {
    const result = evolution([a('DRZET', 'NOT_CHEAP_ENOUGH'), a('NAKUP', 'PASSED')]);
    expect(result.changed).toBe(true);
    expect(result.summary_cs).toContain('pásmo');
    expect(result.summary_cs).toContain('nákupní brána');
  });
});

// ==============================================================================
// Skóre pozornosti
// ==============================================================================

function pillar(overrides: Partial<FindPillar> = {}): FindPillar {
  return {
    key: 'OCENENI',
    label_cs: 'Ocenění',
    points: 0,
    ceiling: 0,
    max_points: 30,
    reason_cs: 'Bez čar to nejde.',
    ...overrides,
  };
}

function find(overrides: Partial<Find> = {}): Find {
  return {
    id: 1,
    ticker: 'ABCD',
    symbol: 'ABCD',
    note: 'proč',
    found_at: '2026-08-20',
    status: 'OTEVRENY',
    assessment_count: 1,
    ...overrides,
  } as Find;
}

describe('citations', () => {
  it('vrátí nedohledaná id zvlášť místo aby je zahodila', () => {
    // Přesně ten případ z 24. 8.: vysvětlení psané k jednomu spisu,
    // obrazovka ukazující jiný. Tiché zahození to schovalo.
    const result = citations(
      point({ fact_ids: ['GOMES-1', 'FUND-5'] }),
      dossier([fact('GOMES-1')]),
    );
    expect(result.found.map((f) => f.id)).toEqual(['GOMES-1']);
    expect(result.missing).toEqual(['FUND-5']);
  });

  it('citedFacts zůstává zkratkou na dohledaná fakta', () => {
    const d = dossier([fact('GOMES-1')]);
    const p = point({ fact_ids: ['GOMES-1', 'NEEXISTUJE-9'] });
    expect(citedFacts(p, d)).toEqual(citations(p, d).found);
  });
});

describe('splitGaps', () => {
  it('oddělí to, co jde doplnit, od toho, co prostě je', () => {
    const d = {
      ...dossier([]),
      gaps: [
        { id: 'MEZ-1', layer: 'FUNDAMENTY', text_cs: 'SEC nedosáhne', fixable_cs: 'Doplnit data' },
        { id: 'MEZ-2', layer: 'GOMES', text_cs: 'Gomes o ní nemluví' },
      ],
    } as FindDossier;
    const { fixable, permanent } = splitGaps(d);
    expect(fixable.map((g) => g.id)).toEqual(['MEZ-1']);
    expect(permanent.map((g) => g.id)).toEqual(['MEZ-2']);
  });
});

describe('attentionRatio', () => {
  it('je null při nulovém stropu, nikdy nula', () => {
    // Nula tvrdí „nic nezískal". Prázdný strop znamená „nedá se říct".
    expect(attentionRatio(0, 0)).toBeNull();
    expect(attentionRatio(null, 100)).toBeNull();
  });

  it('měří podíl ze stropu, ne ze sta', () => {
    expect(attentionRatio(30, 60)).toBe(0.5);
  });
});

describe('attentionLabel', () => {
  it('nikdy nevrátí samotné body bez stropu', () => {
    expect(attentionLabel(38, 62)).toBe('38 / 62');
  });

  it('u nulového stropu řekne, že skóre není', () => {
    expect(attentionLabel(0, 0)).toBe('bez skóre');
  });

  it('bez čísel nevrací nic k vykreslení', () => {
    expect(attentionLabel(null, null)).toBeNull();
  });
});

describe('attentionTone', () => {
  it('barví podle podílu, takže neprozkoumaná firma nevypadá jako slabá', () => {
    // 20 ze 30 dosažitelných je zelená, i když je to jen 20 ze sta možných.
    expect(attentionTone(attentionRatio(20, 30))).toBe('text-positive');
    expect(attentionTone(attentionRatio(20, 100))).not.toBe('text-positive');
  });

  it('bez podílu je šedá', () => {
    expect(attentionTone(null)).toBe('text-text-muted');
  });
});

describe('sortByAttention', () => {
  it('řadí podle podílu ze stropu, ne podle absolutních bodů', () => {
    const rows = [
      find({ id: 1, symbol: 'NIZKY', attention_points: 40, attention_ceiling: 100 }),
      find({ id: 2, symbol: 'VYSOKY', attention_points: 20, attention_ceiling: 25 }),
    ];
    expect(sortByAttention(rows).map((r) => r.symbol)).toEqual(['VYSOKY', 'NIZKY']);
  });

  it('nálezy bez skóre padají na konec, ne na začátek', () => {
    const rows = [
      find({ id: 1, symbol: 'BEZ' }),
      find({ id: 2, symbol: 'SE', attention_points: 5, attention_ceiling: 100 }),
    ];
    expect(sortByAttention(rows).map((r) => r.symbol)).toEqual(['SE', 'BEZ']);
  });

  it('při shodném podílu jde napřed ten, o kterém víme víc', () => {
    const rows = [
      find({ id: 1, symbol: 'MENE', attention_points: 5, attention_ceiling: 10 }),
      find({ id: 2, symbol: 'VICE', attention_points: 50, attention_ceiling: 100 }),
    ];
    expect(sortByAttention(rows).map((r) => r.symbol)).toEqual(['VICE', 'MENE']);
  });

  it('nemění pole, které dostane', () => {
    const rows = [find({ id: 1 }), find({ id: 2, attention_points: 9, attention_ceiling: 10 })];
    const before = rows.map((r) => r.id);
    sortByAttention(rows);
    expect(rows.map((r) => r.id)).toEqual(before);
  });
});

describe('orderedPillars', () => {
  it('drží pevné pořadí bez ohledu na to, jak přijdou', () => {
    const attention = {
      pillars: [pillar({ key: 'TEZE' }), pillar({ key: 'OCENENI' }), pillar({ key: 'PROVOZ' })],
    } as FindAttention;
    expect(orderedPillars(attention).map((p) => p.key)).toEqual([
      'OCENENI',
      'PROVOZ',
      'TEZE',
    ]);
  });
});

describe('pillarWidths', () => {
  it('kreslí i nedosažitelnou část, ne jen prázdno', () => {
    // Bez téhle části vypadá chybějící vstup jako propadlá známka.
    const w = pillarWidths(pillar({ points: 0, ceiling: 0, max_points: 30 }), 100);
    expect(w.earned).toBe(0);
    expect(w.open).toBe(0);
    expect(w.unreachable).toBe(30);
  });

  it('rozdělí plný pilíř na získané a zbývající', () => {
    const w = pillarWidths(pillar({ points: 10, ceiling: 25, max_points: 25 }), 100);
    expect(w.earned).toBe(10);
    expect(w.open).toBe(15);
    expect(w.unreachable).toBe(0);
  });

  it('nikdy nevrátí zápornou šířku', () => {
    const w = pillarWidths(pillar({ points: -5, ceiling: 0, max_points: 0 }), 100);
    expect(w.earned).toBeGreaterThanOrEqual(0);
    expect(w.open).toBeGreaterThanOrEqual(0);
    expect(w.unreachable).toBeGreaterThanOrEqual(0);
  });
});

describe('layerLabel — vrstva FIT', () => {
  it('pojmenuje shodu s Markovými vstupy místo obecného „Ostatní“', () => {
    expect(layerLabel('FIT')).not.toBe('Ostatní');
  });
});

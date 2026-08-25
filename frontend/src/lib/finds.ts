/**
 * Nálezy — čistá logika, kterou komponenty jen zobrazují.
 *
 * Všechno tady je funkce bez stavu a bez sítě, aby to šlo otestovat. Komponenty
 * v tomhle projektu se netestují (`@testing-library/react` v repu není), takže
 * cokoli, co se dá splést, musí být tady.
 *
 * Dvě pravidla, která tenhle soubor vynucuje:
 *
 *  - **Chybějící údaj se nikdy nestane nulou.** Změna kurzu bez ceny je `null`,
 *    ne 0 %. Nula by se četla jako „nic se nestalo", což je tvrzení, ne mezera.
 *  - **Bod nesmí odkázat na fakt, který ve spisu není.** Backend to hlídá při
 *    ukládání, ale spis se dá načíst i ze starého posudku, takže se to kontroluje
 *    i tady — čip odkazující do prázdna by vypadal jako doklad.
 */

import type { FindAssessment, FindDossier, FindFact, FindPoint } from '../api/client';

/** Vrstvy spisu v pořadí, v jakém se čtou: nejdřív člověk, pak zdroje, pak stroj. */
export const LAYER_ORDER = [
  'VLASTNI',
  'GOMES',
  'BREAKOUT',
  'FUNDAMENTY',
  'METODIKA',
  'TRH',
] as const;

const LAYER_LABELS: Record<string, string> = {
  VLASTNI: 'Tvoje úvaha',
  GOMES: 'Mark Gomes',
  BREAKOUT: 'Breakout Investors',
  FUNDAMENTY: 'Fundamenty',
  METODIKA: 'Metodika',
  TRH: 'Trh',
};

/** Nikdy nevrací syrovou hodnotu z databáze — na obrazovce nemá co dělat. */
export function layerLabel(layer: string | null | undefined): string {
  if (!layer) return 'Ostatní';
  return LAYER_LABELS[layer.toUpperCase()] ?? 'Ostatní';
}

const WEIGHT_LABELS: Record<string, string> = {
  ROZHODUJICI: 'rozhodující',
  PODSTATNY: 'podstatné',
  DROBNY: 'drobnost',
};

export function weightLabel(weight: string | null | undefined): string {
  if (!weight) return '';
  return WEIGHT_LABELS[weight.toUpperCase()] ?? '';
}

/**
 * Barva faktu podle směru.
 *
 * Vrací jen třídy z tokenů — nikdy hex ani paletu Tailwindu, protože ta by
 * v druhém motivu tiše zmizela. Neutrální fakt zůstává šedý: kontext není
 * dobrá ani špatná zpráva.
 */
export function directionTone(direction: string | null | undefined): string {
  switch ((direction ?? '').toUpperCase()) {
    case 'PRO':
      return 'text-positive';
    case 'PROTI':
      return 'text-negative';
    default:
      return 'text-text-muted';
  }
}

/** Fakta ze spisu podle id, pro rychlé dohledání citace. */
export function factsById(dossier: FindDossier | null | undefined): Map<string, FindFact> {
  const map = new Map<string, FindFact>();
  for (const fact of dossier?.facts ?? []) map.set(fact.id, fact);
  return map;
}

/**
 * Fakta, o která se bod skutečně opírá.
 *
 * Id, které ve spisu není, se zahodí. Backend takový bod neuloží, ale posudek
 * může být starý a spis se mezitím mohl změnit — a čip odkazující do prázdna
 * by vypadal jako doklad, který si nikdo neověří.
 */
export function citedFacts(point: FindPoint, dossier: FindDossier | null | undefined): FindFact[] {
  const known = factsById(dossier);
  return (point.fact_ids ?? [])
    .map((id) => known.get(id))
    .filter((fact): fact is FindFact => fact !== undefined);
}

/** Fakta seskupená po vrstvách, ve stálém pořadí. Prázdné vrstvy vypadnou. */
export function factsByLayer(
  dossier: FindDossier | null | undefined,
): Array<{ layer: string; label: string; facts: FindFact[] }> {
  return LAYER_ORDER.map((layer) => ({
    layer,
    label: layerLabel(layer),
    facts: (dossier?.facts ?? []).filter((f) => f.layer === layer),
  })).filter((group) => group.facts.length > 0);
}

const WEIGHT_ORDER = ['ROZHODUJICI', 'PODSTATNY', 'DROBNY'];

/**
 * Body rozdělené na dva sloupce, nejtěžší nahoře.
 *
 * Řazení je stabilní: dva body stejné váhy zůstanou v pořadí, v jakém přišly.
 */
export function splitSides(points: FindPoint[] | null | undefined): {
  pro: FindPoint[];
  proti: FindPoint[];
} {
  const rank = (p: FindPoint) => {
    const index = WEIGHT_ORDER.indexOf((p.weight ?? '').toUpperCase());
    return index === -1 ? WEIGHT_ORDER.length : index;
  };
  const sort = (list: FindPoint[]) =>
    list
      .map((point, index) => ({ point, index }))
      .sort((a, b) => rank(a.point) - rank(b.point) || a.index - b.index)
      .map((entry) => entry.point);

  const all = points ?? [];
  return {
    pro: sort(all.filter((p) => (p.side ?? '').toUpperCase() === 'PRO')),
    proti: sort(all.filter((p) => (p.side ?? '').toUpperCase() === 'PROTI')),
  };
}

/**
 * O kolik se kurz hnul od posudku.
 *
 * `null` znamená, že se to spočítat nedá — chybí jedna z cen, nebo je posudek
 * v jiné měně než dnešní kurz. Nula by tvrdila, že se nestalo nic.
 */
export function priceChangePct(
  assessment: Pick<FindAssessment, 'price_at_assessment' | 'price_currency'> | null | undefined,
  currentPrice: number | null | undefined,
  currentCurrency: string | null | undefined,
): number | null {
  const then = assessment?.price_at_assessment;
  if (then === null || then === undefined || then <= 0) return null;
  if (currentPrice === null || currentPrice === undefined || currentPrice <= 0) return null;

  const thenCcy = assessment?.price_currency?.toUpperCase();
  const nowCcy = currentCurrency?.toUpperCase();
  // Dvě různé měny bez kurzu nejsou porovnatelné. Porovnat je bez přepočtu by
  // vyrobilo číslo, které vypadá jako výnos a je to chyba o celý kurz.
  if (thenCcy && nowCcy && thenCcy !== nowCcy) return null;

  return ((currentPrice - then) / then) * 100;
}

/**
 * Věta „kdyby válce byly N".
 *
 * Sestaví se jen z hotové věty od backendu. Skládat ji tady z čísel by
 * znamenalo mít druhé místo, kde se rozhoduje, kdy má smysl — a to je přesně
 * ten druh dvojkolejnosti, kterou tahle aplikace už jednou zaplatila u pásem.
 */
export function conditionalCylinderSentence(
  dossier: FindDossier | null | undefined,
): string | null {
  const sentence = dossier?.method?.if_cylinders_cs;
  return sentence && sentence.trim() ? sentence : null;
}

/**
 * Kolik posudků a jestli se mezi posledními dvěma vůbec něco změnilo.
 *
 * Když se nezměnilo, řekne se to. Vyrábět „vývoj" tam, kde žádný není, je
 * jen jiná forma vymyšleného čísla.
 */
export function evolution(assessments: FindAssessment[] | null | undefined): {
  count: number;
  changed: boolean;
  summary_cs: string;
} {
  const list = assessments ?? [];
  if (list.length === 0) {
    return { count: 0, changed: false, summary_cs: 'Zatím bez posudku.' };
  }
  if (list.length === 1) {
    return { count: 1, changed: false, summary_cs: 'Jeden posudek, není s čím srovnávat.' };
  }

  const [newest, previous] = list;
  const bandMoved = newest.band !== previous.band;
  const gateMoved = newest.gate_code !== previous.gate_code;

  if (!bandMoved && !gateMoved) {
    return {
      count: list.length,
      changed: false,
      summary_cs: `${list.length} posudky a od minula se pásmo ani brána nezměnily.`,
    };
  }

  const parts: string[] = [];
  if (bandMoved) parts.push('pásmo');
  if (gateMoved) parts.push('nákupní brána');
  return {
    count: list.length,
    changed: true,
    summary_cs: `Od minulého posudku se změnila ${parts.join(' i ')}.`,
  };
}

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

import type {
  Find,
  FindAssessment,
  FindAttention,
  FindDossier,
  FindFact,
  FindGap,
  FindPillar,
  FindPoint,
} from '../api/client';

/** Vrstvy spisu v pořadí, v jakém se čtou: nejdřív člověk, pak zdroje, pak stroj. */
export const LAYER_ORDER = [
  'VLASTNI',
  'GOMES',
  'FIT',
  'BREAKOUT',
  'FUNDAMENTY',
  'METODIKA',
  'TRH',
] as const;

const LAYER_LABELS: Record<string, string> = {
  VLASTNI: 'Tvoje úvaha',
  GOMES: 'Mark Gomes',
  FIT: 'Shoda s Markovými vstupy',
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
  return citations(point, dossier).found;
}

/**
 * Citace bodu rozdělené na dohledané a nedohledané.
 *
 * Dřív se nedohledané mlčky zahazovaly a to bylo horší než chyba, kterou to
 * mělo krýt: 24. 8. ukazoval stůl u AZTR spis složený znovu (sedm faktů),
 * kdežto vysvětlení citovalo spis uložený (třináct). Čtyři z osmi citací
 * zmizely a čtyři ukázaly na JINÝ fakt — a obrazovka o tom nedala vědět.
 * Backend teď posílá zapsaný snímek, takže se to stát nemá; a když se to
 * stane, musí to být vidět, ne zmizet.
 */
export function citations(
  point: FindPoint,
  dossier: FindDossier | null | undefined,
): { found: FindFact[]; missing: string[] } {
  const known = factsById(dossier);
  const found: FindFact[] = [];
  const missing: string[] = [];
  for (const id of point.fact_ids ?? []) {
    const fact = known.get(id);
    if (fact) found.push(fact);
    else missing.push(id);
  }
  return { found, missing };
}

/**
 * Mezery rozdělené na ty, které jde doplnit, a ty, které prostě jsou.
 *
 * Jeden seznam se čte jako třináct selhání. U AZTR je z nich fixovatelná
 * jedna; zbytek je „Gomes o té firmě nemluví" — což není chyba aplikace ani
 * firmy, a nemá se tak číst.
 */
export function splitGaps(dossier: FindDossier | null | undefined): {
  fixable: FindGap[];
  permanent: FindGap[];
} {
  const gaps = dossier?.gaps ?? [];
  return {
    fixable: gaps.filter((g) => Boolean(g.fixable_cs)),
    permanent: gaps.filter((g) => !g.fixable_cs),
  };
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


// ==============================================================================
// Skóre pozornosti
// ==============================================================================

/**
 * Podíl získaných bodů ze stropu.
 *
 * `null` při nulovém stropu, nikdy 0. Nula by tvrdila „nic nezískal", kdežto
 * prázdný strop znamená „nedá se říct" — a to je jiná věta.
 */
export function attentionRatio(
  points: number | null | undefined,
  ceiling: number | null | undefined,
): number | null {
  if (points === null || points === undefined) return null;
  if (ceiling === null || ceiling === undefined || ceiling <= 0) return null;
  return points / ceiling;
}

/**
 * Dvojice na obrazovku, vždy i se stropem.
 *
 * Samotné body by se četly jako známka ze sta a rubrika by se tím změnila ve
 * verdikt — přesně to, čím být nemá. Proto tahle funkce nikdy nevrací jen
 * jedno číslo.
 */
export function attentionLabel(
  points: number | null | undefined,
  ceiling: number | null | undefined,
): string | null {
  if (points === null || points === undefined) return null;
  if (ceiling === null || ceiling === undefined) return null;
  if (ceiling <= 0) return 'bez skóre';
  return `${Math.round(points)} / ${Math.round(ceiling)}`;
}

/**
 * Barva podle podílu ze stropu, ne podle absolutních bodů.
 *
 * Absolutní body by obarvily neprozkoumanou firmu stejně jako slabou — což je
 * ta záměna, kvůli které strop vůbec existuje.
 */
export function attentionTone(ratio: number | null): string {
  if (ratio === null) return 'text-text-muted';
  if (ratio >= 0.6) return 'text-positive';
  if (ratio >= 0.3) return 'text-warning';
  return 'text-text-secondary';
}

/**
 * Nálezy seřazené podle toho, kolik si zaslouží pozornosti.
 *
 * Neseřazený seznam byl vlastní důvod, proč skóre vzniklo: pásmo je u všech
 * vlastních nálezů `MIMO_METODIKU` a věta brány je u všech stejná, dokud je
 * semafor jinak než zelený. Nálezy bez skóre padají na konec — nejsou horší,
 * jen se nedají zařadit, a to se pozná podle chybějícího čísla, ne podle
 * vymyšlené nuly.
 */
export function sortByAttention(finds: Find[] | null | undefined): Find[] {
  return [...(finds ?? [])].sort((a, b) => {
    const ra = attentionRatio(a.attention_points, a.attention_ceiling);
    const rb = attentionRatio(b.attention_points, b.attention_ceiling);
    if (ra === null && rb === null) {
      return (b.found_at ?? '').localeCompare(a.found_at ?? '');
    }
    if (ra === null) return 1;
    if (rb === null) return -1;
    if (rb !== ra) return rb - ra;
    // Při shodném podílu rozhoduje vyšší strop: víc známého je víc jistoty.
    return (b.attention_ceiling ?? 0) - (a.attention_ceiling ?? 0);
  });
}

/** Pilíře v pevném pořadí, jak se čtou shora dolů. */
export const PILLAR_ORDER = ['OCENENI', 'PROVOZ', 'KRYTI', 'NALEHAVOST', 'TEZE'] as const;

export function orderedPillars(attention: FindAttention | null | undefined): FindPillar[] {
  const list = attention?.pillars ?? [];
  const rank = (p: FindPillar) => {
    const i = PILLAR_ORDER.indexOf(p.key as (typeof PILLAR_ORDER)[number]);
    return i === -1 ? PILLAR_ORDER.length : i;
  };
  return [...list].sort((a, b) => rank(a) - rank(b));
}

/**
 * Tři šířky jednoho pilíře v procentech celku, pro pruh na obrazovce.
 *
 * `unreachable` je ta část, která se získat NEDÁ. Kreslí se, protože jinak by
 * pruh vypadal jako propadlá známka místo jako neprozkoumané místo.
 */
export function pillarWidths(pillar: FindPillar, total: number): {
  earned: number;
  open: number;
  unreachable: number;
} {
  const scale = total > 0 ? 100 / total : 0;
  const earned = Math.max(0, pillar.points) * scale;
  const open = Math.max(0, pillar.ceiling - pillar.points) * scale;
  const unreachable = Math.max(0, pillar.max_points - pillar.ceiling) * scale;
  return { earned, open, unreachable };
}

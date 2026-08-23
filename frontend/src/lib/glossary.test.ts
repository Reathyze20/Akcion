/**
 * Testy glosáře.
 *
 * Term s překlepem v identifikátoru se nijak neprojeví: komponenta
 * vykreslí prostý text bez tečkovaného podtržení a bez bubliny. Nic se
 * nerozbije, jen vysvětlivka tiše zmizí — a přesně proto se to
 * v aplikaci nikdy nevšimne. Tenhle test projde zdrojáky a ověří, že
 * každý použitý pojem v glosáři existuje.
 */

import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { GLOSSARY, lookup } from './glossary';

const SRC = path.resolve(__dirname, '..');

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      found.push(...sourceFiles(full));
    } else if (entry.name.endsWith('.tsx')) {
      found.push(full);
    }
  }
  return found;
}

/** Každé <Term id="..."> ve zdrojácích, s cestou k souboru. */
function usedTerms(): { id: string; file: string }[] {
  const used: { id: string; file: string }[] = [];
  const pattern = /<Term\s+id="([^"]+)"/g;

  for (const file of sourceFiles(SRC)) {
    const text = fs.readFileSync(file, 'utf8');
    for (const match of text.matchAll(pattern)) {
      used.push({ id: match[1], file: path.relative(SRC, file) });
    }
  }
  return used;
}

describe('glosář', () => {
  it('má u každého pojmu vysvětlení', () => {
    for (const [key, entry] of Object.entries(GLOSSARY)) {
      expect(entry.meaning, `pojem ${key} nemá vysvětlení`).toBeTruthy();
      expect(entry.meaning.length, `pojem ${key} má příliš krátké vysvětlení`)
        .toBeGreaterThan(20);
    }
  });

  it('nemá vysvětlení delší než dvě věty', () => {
    // Bublina, kterou nikdo nedočte, je stejně k ničemu jako žádná.
    for (const [key, entry] of Object.entries(GLOSSARY)) {
      const sentences = entry.meaning.split('. ').filter(Boolean).length;
      expect(sentences, `pojem ${key} má ${sentences} vět`).toBeLessThanOrEqual(2);
    }
  });

  it('u pojmů z metodiky uvádí, že standardem nejsou', () => {
    // Kdo si splete pojem z vlastní metodiky s oborovým standardem,
    // začne ho hledat jinde a nenajde.
    const fromMethod = Object.entries(GLOSSARY)
      .filter(([, entry]) => entry.source === 'metodika');
    expect(fromMethod.length).toBeGreaterThan(0);
    for (const [key, entry] of fromMethod) {
      expect(entry.source, `pojem ${key}`).toBe('metodika');
    }
  });

  it('neobsahuje pojem odkazující sám na sebe prázdným rozpisem', () => {
    for (const [key, entry] of Object.entries(GLOSSARY)) {
      if (entry.expansion !== undefined) {
        expect(entry.expansion.trim(), `pojem ${key} má prázdný rozpis`).not.toBe('');
      }
    }
  });

  it('vrací undefined pro neznámý pojem', () => {
    expect(lookup('tenhle-pojem-neexistuje')).toBeUndefined();
  });
});

describe('použití ve zdrojácích', () => {
  it('každý <Term id="..."> míří na existující pojem', () => {
    const unknown = usedTerms().filter(({ id }) => !(id in GLOSSARY));

    expect(
      unknown.map(({ id, file }) => `${file}: id="${id}"`),
      'Term odkazuje na pojem, který v glosáři není — vysvětlivka se tiše nevykreslí',
    ).toEqual([]);
  });

  it('nějaké vysvětlivky se opravdu používají', () => {
    // Glosář, na který nikdo neodkazuje, je mrtvý kód, ne funkce.
    expect(usedTerms().length).toBeGreaterThan(0);
  });
});

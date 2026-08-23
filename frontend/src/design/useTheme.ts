/**
 * Hook nad theme.ts.
 *
 * Oddělený soubor kvůli Fast Refresh: modul, který vyváží hook i prostý
 * modulový stav, se při úpravě přenačte celý a volba tématu se ztratí.
 */

import { useCallback, useSyncExternalStore } from 'react';
import {
  getChoice,
  getSnapshot,
  setChoice,
  subscribe,
  type ResolvedTheme,
  type ThemeChoice,
} from './theme';

interface ThemeState {
  /** Co je zvolené — včetně „podle systému". */
  choice: ThemeChoice;
  /** Co se doopravdy vykresluje. */
  resolved: ResolvedTheme;
  setTheme: (choice: ThemeChoice) => void;
  /** Projde světlé → tmavé → podle systému → světlé. */
  cycle: () => void;
}

const ORDER: ThemeChoice[] = ['light', 'dark', 'system'];

export function useTheme(): ThemeState {
  const snapshot = useSyncExternalStore(
    subscribe,
    getSnapshot,
    // Bez okna se nedá zjistit nic o systému; světlé je bezpečný výchozí.
    () => 'system|light',
  );

  const [choice, resolved] = snapshot.split('|') as [ThemeChoice, ResolvedTheme];

  const cycle = useCallback(() => {
    const index = ORDER.indexOf(getChoice());
    setChoice(ORDER[(index + 1) % ORDER.length]);
  }, []);

  return {
    choice,
    resolved,
    setTheme: setChoice,
    cycle,
  };
}

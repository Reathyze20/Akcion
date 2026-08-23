/**
 * Přepínání světlého a tmavého tématu.
 *
 * Tři stavy, ne dva. „Podle systému" je výchozí a je to skutečný stav:
 * nesmí se tvářit jako natvrdo zvolené světlo jen proto, že zrovna
 * je den. Výslovná volba se ukládá a přebíjí systém v obou směrech.
 *
 * Téma se zapisuje na <html> jako data-theme. Ve stavu „podle systému"
 * se atribut odstraní a rozhoduje prefers-color-scheme — tak, jak to
 * očekávají tokeny v tokens.css.
 */

export type ThemeChoice = 'light' | 'dark' | 'system';

/** Co se doopravdy vykreslí. „system" se sem nikdy nedostane. */
export type ResolvedTheme = 'light' | 'dark';

const STORAGE_KEY = 'akcion.theme';

const isChoice = (value: unknown): value is ThemeChoice =>
  value === 'light' || value === 'dark' || value === 'system';

/**
 * Přečte uloženou volbu.
 *
 * localStorage umí vyhodit výjimku (soukromé okno, zakázaná data webu),
 * ne jen vrátit prázdno. Neošetřený přístup shodí celý render, takže
 * čtení i zápis jsou obalené.
 */
export function readChoice(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isChoice(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

function writeChoice(choice: ThemeChoice): void {
  try {
    if (choice === 'system') {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, choice);
    }
  } catch {
    /* Volba nepřežije zavření okna. Aplikace kvůli tomu spadnout nesmí. */
  }
}

function systemPrefersDark(): boolean {
  return typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function resolve(choice: ThemeChoice): ResolvedTheme {
  if (choice === 'system') return systemPrefersDark() ? 'dark' : 'light';
  return choice;
}

/** Zapíše volbu na <html>. Sdílí ji inline skript v index.html, který
 *  běží před Reactem, aby stránka neproblikla opačným tématem. */
export function apply(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', choice);
  }
}

/* ---------------------------------------------------------------------------
   Sdílený stav bez knihovny
   Komponent, které téma zajímá, může být víc (přepínač v hlavičce, graf,
   který si volí barvy). Modulový store je drží v souladu.
   --------------------------------------------------------------------------- */

type Listener = () => void;

const listeners = new Set<Listener>();
let current: ThemeChoice = 'system';
let initialised = false;

/**
 * Otisk stavu: volba i to, co z ní vyšlo.
 *
 * useSyncExternalStore porovnává snímky. Kdyby snímkem byla jen volba,
 * přepnutí systému do noci by nic nezměnilo (pořád „system") a komponenty,
 * které si podle tématu vybírají barvy v JavaScriptu — třeba graf — by
 * zůstaly na světlé paletě uvnitř tmavé aplikace. Řetězec se drží
 * v proměnné, aby měl stabilní identitu mezi vykresleními.
 */
let snapshot = 'system|light';

function refreshSnapshot(): boolean {
  const next = `${current}|${resolve(current)}`;
  if (next === snapshot) return false;
  snapshot = next;
  return true;
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

function init(): void {
  if (initialised) return;
  initialised = true;
  current = readChoice();
  apply(current);
  refreshSnapshot();

  // Když uživatel nechá „podle systému", musí se aplikace přebarvit
  // ve chvíli, kdy si systém přepne na noční režim.
  if (typeof window.matchMedia === 'function') {
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (refreshSnapshot()) notify();
    };
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', onChange);
    }
  }
}

export function getChoice(): ThemeChoice {
  init();
  return current;
}

/** Snímek pro useSyncExternalStore ve tvaru `volba|vykreslené`. */
export function getSnapshot(): string {
  init();
  return snapshot;
}

export function setChoice(choice: ThemeChoice): void {
  init();
  current = choice;
  writeChoice(choice);
  apply(choice);
  refreshSnapshot();
  notify();
}

export function subscribe(listener: Listener): () => void {
  init();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

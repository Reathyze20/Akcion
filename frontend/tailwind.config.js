/** @type {import('tailwindcss').Config} */

/*
 * Barvy sem nepatří jako hodnoty — jsou v src/design/tokens.css jako
 * CSS proměnné, aby se daly přepnout za běhu (světlé / tmavé téma).
 * Tady je jen most: rgb(var(--x) / <alpha-value>) zachovává zápisy
 * s průhledností, které stávající komponenty používají (bg-positive/20,
 * border-accent/30 a podobně).
 */
const withAlpha = (variable) => `rgb(var(${variable}) / <alpha-value>)`;

export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // Třídy skládané za běhu Tailwind ve zdrojácích nenajde.
  safelist: [
    'text-positive', 'bg-positive', 'border-positive', 'bg-positive-bg', 'border-positive-border', 'hover:bg-positive-muted',
    'text-negative', 'bg-negative', 'border-negative', 'bg-negative-bg', 'border-negative-border', 'hover:bg-negative-muted',
    'text-warning', 'bg-warning', 'border-warning', 'bg-warning-bg', 'border-warning-border',
    'text-accent', 'bg-accent', 'border-accent', 'bg-accent-bg', 'border-accent-border', 'hover:bg-accent-hover',
    'bg-surface-base', 'bg-surface-raised', 'bg-surface-overlay', 'bg-surface-hover', 'bg-surface-active',
    'hover:bg-surface-hover', 'hover:bg-surface-active',
    'text-text-primary', 'text-text-secondary', 'text-text-muted',
    'border-border', 'border-border-subtle', 'border-border-strong',
    // Semafor — stupeň se vybírá za běhu podle stavu trhu.
    'text-signal-green', 'text-signal-amber', 'text-signal-orange', 'text-signal-red',
    'bg-signal-green', 'bg-signal-amber', 'bg-signal-orange', 'bg-signal-red',
    'border-signal-green', 'border-signal-amber', 'border-signal-orange', 'border-signal-red',
  ],
  theme: {
    extend: {
      colors: {
        /* ---- tři plochy, každá s významem ---------------------------- */

        // Podklad, na kterém všechno leží.
        page: withAlpha('--page'),

        // Panel — odkud aplikace mluví. V obou tématech tmavý.
        frame: {
          DEFAULT: withAlpha('--frame'),
          raised: withAlpha('--frame-2'),
          line: withAlpha('--frame-3'),
          text: withAlpha('--on-frame'),
          muted: withAlpha('--on-frame-2'),
        },

        // List — kde se vedou záznamy. Linkovaný arch.
        sheet: {
          DEFAULT: withAlpha('--sheet'),
          alt: withAlpha('--sheet-alt'),
          rule: withAlpha('--rule'),
          text: withAlpha('--ink'),
          muted: withAlpha('--ink-2'),
          faint: withAlpha('--ink-3'),
        },

        // Semafor — jediná chroma v aplikaci. Barva tu něco znamená.
        signal: {
          green: withAlpha('--signal-green'),
          amber: withAlpha('--signal-amber'),
          orange: withAlpha('--signal-orange'),
          red: withAlpha('--signal-red'),
        },

        /* ---- názvy, na kterých stojí stávající komponenty ------------- *
         * Zůstávají, jen jsou nově navázané na proměnné, takže se
         * přebarvují s tématem bez zásahu do 44 souborů.                 */

        surface: {
          base: withAlpha('--surface-base'),
          raised: withAlpha('--surface-raised'),
          overlay: withAlpha('--surface-overlay'),
          hover: withAlpha('--surface-hover'),
          active: withAlpha('--surface-active'),
        },
        border: {
          subtle: withAlpha('--border-subtle'),
          DEFAULT: withAlpha('--border-default'),
          strong: withAlpha('--border-strong'),
        },
        text: {
          primary: withAlpha('--text-primary'),
          secondary: withAlpha('--text-secondary'),
          muted: withAlpha('--text-muted'),
          inverse: withAlpha('--text-inverse'),
        },
        positive: {
          DEFAULT: withAlpha('--positive'),
          muted: withAlpha('--positive-muted'),
          bg: 'rgb(var(--positive) / var(--tint-bg))',
          border: 'rgb(var(--positive) / var(--tint-border))',
        },
        negative: {
          DEFAULT: withAlpha('--negative'),
          muted: withAlpha('--negative-muted'),
          bg: 'rgb(var(--negative) / var(--tint-bg))',
          border: 'rgb(var(--negative) / var(--tint-border))',
        },
        warning: {
          DEFAULT: withAlpha('--warning'),
          muted: withAlpha('--warning-muted'),
          bg: 'rgb(var(--warning) / var(--tint-bg))',
          border: 'rgb(var(--warning) / var(--tint-border))',
        },
        accent: {
          DEFAULT: withAlpha('--accent'),
          hover: withAlpha('--accent-strong'),
          muted: withAlpha('--accent-strong'),
          bg: 'rgb(var(--accent) / var(--tint-bg))',
          border: 'rgb(var(--accent) / var(--tint-border))',
        },
      },
      fontFamily: {
        // Displej — nese osobnost. Používá se střídmě: verdikt, značka, nadpisy listů.
        display: ['"Archivo Variable"', 'Archivo', '"Arial Narrow"', 'Helvetica', 'sans-serif'],
        // Text — české věty. Plex má poctivé latin-ext, takže háčky a čárky sedí.
        sans: ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        // Data — každé číslo v aplikaci. Tabulkové číslice, aby sloupce lícovaly.
        mono: ['"IBM Plex Mono"', 'Consolas', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        // Panel je hranatý, list má nepatrný rádius jako papír. Žádné bubliny.
        card: '3px',
        button: '3px',
        input: '2px',
      },
      boxShadow: {
        card: '0 1px 2px rgb(0 0 0 / 0.16)',
        'card-hover': '0 3px 10px rgb(0 0 0 / 0.20)',
      },
      animation: {
        'fade-in': 'fade-in 0.18s ease-out',
        'light-up': 'light-up 900ms ease-out 200ms both',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(3px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'light-up': {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--signal-amber) / 0.55)' },
          '60%': { boxShadow: '0 0 0 9px rgb(var(--signal-amber) / 0.05)' },
          '100%': { boxShadow: '0 0 0 4px rgb(var(--signal-amber) / 0.16)' },
        },
      },
    },
  },
  plugins: [],
}

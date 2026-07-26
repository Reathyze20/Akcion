/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // Safelist ensures these dynamic classes are always generated
  safelist: [
    // Semantic colors (ONLY for indicators)
    'text-positive', 'bg-positive', 'border-positive', 'bg-positive-bg', 'border-positive-border', 'hover:bg-positive-muted',
    'text-negative', 'bg-negative', 'border-negative', 'bg-negative-bg', 'border-negative-border', 'hover:bg-negative-muted',
    'text-warning', 'bg-warning', 'border-warning', 'bg-warning-bg', 'border-warning-border',
    // Accent (for buttons/interactive)
    'text-accent', 'bg-accent', 'border-accent', 'bg-accent-bg', 'border-accent-border', 'hover:bg-accent-hover',
    // Surfaces
    'bg-surface-base', 'bg-surface-raised', 'bg-surface-overlay', 'bg-surface-hover', 'bg-surface-active',
    'hover:bg-surface-hover', 'hover:bg-surface-active',
    // Text
    'text-text-primary', 'text-text-secondary', 'text-text-muted',
    // Borders
    'border-border', 'border-border-subtle', 'border-border-strong',
  ],
  theme: {
    extend: {
      colors: {
        // ================================================================
        // AKCION PRO - Professional Investment Terminal Palette
        // Inspired by Bloomberg Terminal, Linear, and Raycast
        // Low saturation, high contrast, easy on the eyes
        // ================================================================
        
        // Base surfaces (cool-toned grays with subtle blue undertone)
        surface: {
          base: '#0a0c10',      // Deepest background (near black)
          raised: '#12151a',    // Cards, elevated surfaces
          overlay: '#181c24',   // Modals, dropdowns
          hover: '#1e232d',     // Hover states
          active: '#252b38',    // Active/selected states
        },
        
        // Borders (subtle, low contrast)
        border: {
          subtle: '#1e2430',    // Barely visible dividers
          DEFAULT: '#2a3140',   // Standard borders
          strong: '#3a4355',    // Emphasized borders
        },
        
        // Text hierarchy
        text: {
          primary: '#e8ecf4',   // Primary content (soft white)
          secondary: '#9ca3b0', // Secondary content
          muted: '#6b7280',     // Tertiary/disabled
          inverse: '#0a0c10',   // Text on light backgrounds
        },
        
        // Semantic colors - ONLY for indicators (buy/sell/warning)
        // Desaturated on purpose: color carries meaning, never decoration.
        positive: {
          DEFAULT: '#4da37a',   // Calm financial green (was neon #22c55e)
          muted: '#3d8664',
          bg: 'rgba(77, 163, 122, 0.08)',
          border: 'rgba(77, 163, 122, 0.16)',
        },
        negative: {
          DEFAULT: '#c95c5c',   // Brick red (was alarm #ef4444)
          muted: '#a94b4b',
          bg: 'rgba(201, 92, 92, 0.08)',
          border: 'rgba(201, 92, 92, 0.16)',
        },
        warning: {
          DEFAULT: '#c0913f',   // Muted gold (was highlighter #f59e0b)
          muted: '#a17832',
          bg: 'rgba(192, 145, 63, 0.08)',
          border: 'rgba(192, 145, 63, 0.16)',
        },

        // UI accent - for interactive elements (buttons, links, focus)
        accent: {
          DEFAULT: '#4f81b3',   // Steel blue (was electric #3b82f6)
          hover: '#446f9b',
          muted: '#3a5f85',
          bg: 'rgba(79, 129, 179, 0.08)',
          border: 'rgba(79, 129, 179, 0.16)',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      borderRadius: {
        'card': '8px',       // Slightly smaller for professional look
        'button': '6px',
        'input': '4px',
      },
      boxShadow: {
        // Neutral elevation only — no colored glows (professional, not disco)
        'card': '0 1px 3px rgba(0, 0, 0, 0.3)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.4)',
      },
      animation: {
        'shimmer': 'shimmer 2s infinite',
        'fade-in': 'fade-in 0.2s ease-out',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' },
        },
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}

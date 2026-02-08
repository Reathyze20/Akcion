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
        positive: {
          DEFAULT: '#22c55e',   // Green for gains/buy
          muted: '#16a34a',
          bg: 'rgba(34, 197, 94, 0.1)',
          border: 'rgba(34, 197, 94, 0.25)',
        },
        negative: {
          DEFAULT: '#ef4444',   // Red for losses/sell
          muted: '#dc2626',
          bg: 'rgba(239, 68, 68, 0.1)',
          border: 'rgba(239, 68, 68, 0.25)',
        },
        warning: {
          DEFAULT: '#f59e0b',   // Amber for warnings
          muted: '#d97706',
          bg: 'rgba(245, 158, 11, 0.1)',
          border: 'rgba(245, 158, 11, 0.25)',
        },
        
        // UI accent - for interactive elements (buttons, links, focus)
        accent: {
          DEFAULT: '#3b82f6',   // Blue-500 - subtle, professional
          hover: '#2563eb',     // Blue-600
          muted: '#1d4ed8',     // Blue-700
          bg: 'rgba(59, 130, 246, 0.1)',
          border: 'rgba(59, 130, 246, 0.25)',
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
        'card': '0 1px 3px rgba(0, 0, 0, 0.3)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.4)',
        'card-hover': '0 4px 16px rgba(88, 166, 255, 0.15)',
        'glow-blue': '0 0 24px rgba(88, 166, 255, 0.3)',
        'glow-green': '0 0 24px rgba(63, 185, 80, 0.3)',
        'glow-red': '0 0 24px rgba(248, 81, 73, 0.3)',
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

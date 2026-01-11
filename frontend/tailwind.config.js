/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Premium Dark Modular (Linear/Raycast Style)
        terminal: {
          bg: '#0E1117',       // Deep midnight blue base
          surface: '#161B22',   // Elevated layer
          card: '#1C2128',      // Card background
          hover: '#22272E',     // Hover state
          border: '#30363D',    // Subtle borders
          'border-light': '#3D444D', // Lighter borders
        },
        text: {
          primary: '#E6EDF3',   // Soft white, not harsh
          secondary: '#8B949E', // Cool grey
          muted: '#6E7681',     // Dimmed grey
          inverse: '#0E1117',   // For light backgrounds
        },
        semantic: {
          bullish: '#3FB950',   // Muted neon green
          'bullish-bg': 'rgba(63, 185, 80, 0.15)',
          bearish: '#F85149',   // Muted neon red
          'bearish-bg': 'rgba(248, 81, 73, 0.15)',
          neutral: '#D29922',   // Amber
          'neutral-bg': 'rgba(210, 153, 34, 0.15)',
        },
        accent: {
          blue: '#58A6FF',      // Bright blue accent
          'blue-hover': '#388BFD',
          purple: '#BC8CFF',    // Soft purple
          cyan: '#39C5CF',      // Bright cyan
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Consolas', 'monospace'],
      },
      borderRadius: {
        'card': '12px',      // Standard card radius
        'button': '8px',     // Button radius
        'input': '6px',      // Input radius
      },
      boxShadow: {
        'card': '0 2px 8px rgba(0, 0, 0, 0.4)',
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

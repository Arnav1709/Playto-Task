/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        paper: 'var(--paper)',
        ink: {
          50: 'var(--ink-50)',
          100: 'var(--ink-100)',
          200: 'var(--ink-200)',
          300: 'var(--ink-300)',
          500: 'var(--ink-500)',
          600: 'var(--ink-600)',
          700: 'var(--ink-700)',
          800: 'var(--ink-800)',
          950: 'var(--ink-950)',
        },
        mint: {
          50: 'var(--mint-50)',
          100: 'var(--mint-100)',
          200: 'var(--mint-200)',
          700: 'var(--mint-700)',
          800: 'var(--mint-800)',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        ledger: '0 18px 60px rgba(24, 33, 49, 0.12)',
      },
    },
  },
  plugins: [],
};

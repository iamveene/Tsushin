import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class', // Enable dark mode with class strategy
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      // Tsushin Brand Colors - Extended for premium UI
      colors: {
        tsushin: {
          // Base colors
          ink: '#0B0F14',           // Primary dark background
          deep: '#0D1117',          // Darker variant for depth
          surface: '#161B22',       // Card/surface backgrounds
          elevated: '#1C2128',      // Elevated surfaces (modals, dropdowns)

          // Primary brand
          indigo: '#3C5AFE',        // Action/CTA
          'indigo-glow': '#6B7FFF', // Hover state with glow
          'indigo-muted': '#2D4494', // Disabled/muted state

          // Accent colors
          accent: '#00D9FF',        // Cyan accent for highlights
          'accent-glow': '#33E4FF', // Accent hover

          // Status colors
          vermilion: '#EE3E2D',     // Error/Danger
          success: '#3FB950',       // Success states
          'success-glow': '#56D364', // Success hover
          warning: '#D29922',       // Warning states
          'warning-glow': '#E3B341', // Warning hover

          // Neutral
          fog: '#F6F7F9',           // Light background
          slate: '#8B929E',         // Text secondary
          muted: '#484F58',         // Muted text/borders
          border: '#30363D',        // Subtle borders
        },
      },
      // Tsushin Typography - Distinctive fonts (using CSS variables for Next.js font optimization)
      fontFamily: {
        sans: ['var(--font-dm-sans)', 'system-ui', 'sans-serif'],
        display: ['var(--font-jakarta)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'JetBrains Mono', 'Menlo', 'monospace'],
      },
      // Font sizes with better hierarchy
      fontSize: {
        '2xs': ['0.625rem', { lineHeight: '0.875rem' }],
        'display-lg': ['2.5rem', { lineHeight: '1.2', fontWeight: '700' }],
        'display-md': ['2rem', { lineHeight: '1.25', fontWeight: '600' }],
      },
      // Background images for gradients and effects
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-conic': 'conic-gradient(from 180deg at 50% 50%, var(--tw-gradient-stops))',
        'gradient-primary': 'linear-gradient(135deg, #3C5AFE 0%, #6B7FFF 50%, #00D9FF 100%)',
        'gradient-primary-hover': 'linear-gradient(135deg, #4D6AFF 0%, #7C8FFF 50%, #33E4FF 100%)',
        'gradient-danger': 'linear-gradient(135deg, #EE3E2D 0%, #FF6B5B 100%)',
        'gradient-success': 'linear-gradient(135deg, #3FB950 0%, #56D364 100%)',
        'gradient-surface': 'linear-gradient(180deg, rgba(22, 27, 34, 0.9) 0%, rgba(11, 15, 20, 0.95) 100%)',
        'glow-indigo': 'radial-gradient(circle at center, rgba(60, 90, 254, 0.15) 0%, transparent 70%)',
        'glow-accent': 'radial-gradient(circle at center, rgba(0, 217, 255, 0.1) 0%, transparent 70%)',
        'noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E\")",
      },
      // Box shadows for depth
      boxShadow: {
        'glow-sm': '0 0 10px rgba(60, 90, 254, 0.3)',
        'glow-md': '0 0 20px rgba(60, 90, 254, 0.4)',
        'glow-lg': '0 0 30px rgba(60, 90, 254, 0.5)',
        'glow-accent': '0 0 20px rgba(0, 217, 255, 0.3)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -2px rgba(0, 0, 0, 0.2)',
        'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.3)',
        'elevated': '0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.3)',
        'inner-glow': 'inset 0 1px 0 0 rgba(255, 255, 255, 0.05)',
      },
      // Border radius
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.5rem',
      },
      // Animation keyframes
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in-down': {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'slide-in-left': {
          '0%': { opacity: '0', transform: 'translateX(-20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'pulse-glow': {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 10px rgba(60, 90, 254, 0.3)' },
          '50%': { opacity: '0.8', boxShadow: '0 0 20px rgba(60, 90, 254, 0.5)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'spin-slow': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
        'bounce-soft': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-5px)' },
        },
        'gradient-shift': {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        'count-up': {
          '0%': { transform: 'translateY(100%)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'wave': {
          '0%': { transform: 'rotate(0deg)' },
          '10%': { transform: 'rotate(14deg)' },
          '20%': { transform: 'rotate(-8deg)' },
          '30%': { transform: 'rotate(14deg)' },
          '40%': { transform: 'rotate(-4deg)' },
          '50%': { transform: 'rotate(10deg)' },
          '60%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(0deg)' },
        },
      },
      // Animation utilities
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'fade-in-up': 'fade-in-up 0.4s ease-out',
        'fade-in-down': 'fade-in-down 0.4s ease-out',
        'slide-in-right': 'slide-in-right 0.3s ease-out',
        'slide-in-left': 'slide-in-left 0.3s ease-out',
        'scale-in': 'scale-in 0.2s ease-out',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'pulse-soft': 'pulse-soft 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'spin-slow': 'spin-slow 3s linear infinite',
        'bounce-soft': 'bounce-soft 2s ease-in-out infinite',
        'gradient-shift': 'gradient-shift 3s ease infinite',
        'count-up': 'count-up 0.5s ease-out',
        'float': 'float 3s ease-in-out infinite',
        'wave': 'wave 2.5s ease-in-out infinite',
      },
      // Smooth transitions
      transitionProperty: {
        'height': 'height',
        'spacing': 'margin, padding',
        'colors': 'color, background-color, border-color, fill, stroke',
      },
      transitionDuration: {
        '400': '400ms',
      },
      transitionTimingFunction: {
        'bounce-in': 'cubic-bezier(0.68, -0.55, 0.265, 1.55)',
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      // Backdrop blur
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
export default config

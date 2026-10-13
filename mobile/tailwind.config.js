/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  // Light theme only for now (app.json userInterfaceStyle). 'class' also avoids a
  // NativeWind 4 web runtime error raised under the default 'media' strategy.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#EEF6FF',
          100: '#D9EAFF',
          500: '#1F6FEB',
          600: '#1759C2',
          700: '#114596',
        },
        ink: {
          DEFAULT: '#111827',
          muted: '#6B7280',
          subtle: '#9CA3AF',
        },
        surface: {
          DEFAULT: '#FFFFFF',
          muted: '#F3F4F6',
          border: '#E5E7EB',
        },
        success: '#15803D',
        warning: '#B45309',
        danger: '#B91C1C',
      },
    },
  },
  plugins: [],
};

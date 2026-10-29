/** @type {import('tailwindcss').Config} */

// Every color scale used by the Studio is backed by a CSS variable defined in
// src/theme.css, so the Dark / Light toggle can swap the whole palette at once
// (see scripts/generate-theme.cjs).
const SCALES = ['slate', 'indigo', 'violet', 'emerald', 'amber', 'cyan', 'rose', 'fuchsia'];
const SHADES = ['50', '100', '200', '300', '400', '500', '600', '700', '800', '900', '950'];

const themedColors = Object.fromEntries(
  SCALES.map((scale) => [
    scale,
    Object.fromEntries(
      SHADES.map((shade) => [shade, `rgb(var(--c-${scale}-${shade}) / <alpha-value>)`])
    ),
  ])
);

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ...themedColors,
        white: 'rgb(var(--c-white) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};

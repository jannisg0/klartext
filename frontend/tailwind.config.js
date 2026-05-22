/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Editorial palette from docs/design/Klartext.html
        paper: '#F4F1EA',
        paper2: '#EBE7DB',
        paper3: '#E2DDCD',
        ink: '#16140F',
        ink2: '#3C3830',
        ink3: '#6C6657',
        rule: '#D7D0BD',
        rule2: '#C8C0AB',

        graphite: '#131210',
        graphite2: '#1B1A16',
        graphite3: '#23211C',
        bone: '#ECE6D3',
        bone2: '#A39C88',
        bone3: '#6E6957',
        edge: '#2A2823',
        edge2: '#37342D',

        ochre: '#B88636',
        ochreDark: '#D9A658',
        ochreSoft: '#E8D7AE',

        rust: '#9E5742',
        rustDark: '#C97A5C',

        ver: '#7A8463',
        verDark: '#A6B189',

        // Party brand swatches kept for future badge use.
        party: {
          afd: '#009ee0',
          cdu: '#000000',
          gruene: '#46962b',
          linke: '#be3075',
          fdp: '#ffed00',
          spd: '#e3000f',
        },
      },
      fontFamily: {
        display: ['"Newsreader"', 'Georgia', 'serif'],
        sans: ['"Geist"', 'ui-sans-serif', 'system-ui'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        tightish: '-0.012em',
        tightest: '-0.025em',
      },
      boxShadow: {
        ring: '0 0 0 1px rgba(22,20,15,.08)',
        ringD: '0 0 0 1px rgba(236,230,211,.08)',
      },
    },
  },
  plugins: [],
}

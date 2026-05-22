/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        party: {
          afd: '#009ee0',
          cdu: '#000000',
          gruene: '#46962b',
          linke: '#be3075',
          fdp: '#ffed00',
          spd: '#e3000f',
        },
      },
    },
  },
  plugins: [],
}

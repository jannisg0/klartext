// Party slugs match the `party` metadata field on retrieved chunks
// (= the lowercased PDF stem). `tailwindKey` is the ASCII-safe key
// registered under `colors.party.*` in tailwind.config.js.

export const PARTIES = [
  { slug: 'spd', label: 'SPD', color: '#e3000f', tailwindKey: 'spd' },
  { slug: 'cdu', label: 'CDU', color: '#000000', tailwindKey: 'cdu' },
  { slug: 'diegrünen', label: 'Grüne', color: '#46962b', tailwindKey: 'gruene' },
  { slug: 'fdp', label: 'FDP', color: '#ffed00', tailwindKey: 'fdp' },
  { slug: 'afd', label: 'AfD', color: '#009ee0', tailwindKey: 'afd' },
  { slug: 'dielinke', label: 'Linke', color: '#be3075', tailwindKey: 'linke' },
]

export function partyBySlug(slug) {
  return PARTIES.find((p) => p.slug === slug)
}

export function partyLabel(slug) {
  return partyBySlug(slug)?.label ?? slug.toUpperCase()
}

// Party slugs match the `party` metadata field on retrieved chunks
// (= the lowercased PDF stem). `tailwindKey` is the ASCII-safe key
// registered under `colors.party.*` in tailwind.config.js.

export const PARTIES = [
  { slug: 'cdu', label: 'CDU / CSU', color: '#000000', tailwindKey: 'cdu' },
  { slug: 'spd', label: 'SPD', color: '#e3000f', tailwindKey: 'spd' },
  { slug: 'diegrünen', label: 'Bündnis 90 / Grüne', color: '#46962b', tailwindKey: 'gruene' },
  { slug: 'fdp', label: 'FDP', color: '#ffed00', tailwindKey: 'fdp' },
  { slug: 'dielinke', label: 'Die Linke', color: '#be3075', tailwindKey: 'linke' },
  { slug: 'afd', label: 'AfD', color: '#009ee0', tailwindKey: 'afd' },
]

export function partyBySlug(slug) {
  return PARTIES.find((p) => p.slug === slug)
}

export function partyLabel(slug) {
  return partyBySlug(slug)?.label ?? slug.toUpperCase()
}

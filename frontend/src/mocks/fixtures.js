// Mock payloads shaped exactly like backend/models.py.
// Used by mockStream until Session F2 wires the real /chat SSE.

export const SOURCES_DEMO = [
  {
    chunk_id: 'spd_p17_c1',
    party: 'spd',
    page: 17,
    section_path: 'Wirtschaft > Wohnungspolitik',
    score: 0.81,
    text_preview:
      'Wir gründen eine landeseigene Wohnbaugesellschaft BWohnen, die strategisch Grundstücke erwirbt...',
  },
  {
    chunk_id: 'spd_p17_c0',
    party: 'spd',
    page: 17,
    section_path: 'Wirtschaft > Wohnungspolitik',
    score: 0.74,
    text_preview:
      'Die Mietpreisbremse soll ausgeweitet werden; niemand soll mehr als 30 Prozent...',
  },
  {
    chunk_id: 'cdu_p9_c2',
    party: 'cdu',
    page: 9,
    section_path: 'Wirtschaft > Wohnen',
    score: 0.62,
    text_preview: 'Wir setzen auf Eigentumsbildung und vereinfachen das Baurecht...',
  },
  {
    chunk_id: 'diegrünen_p22_c1',
    party: 'diegrünen',
    page: 22,
    section_path: 'Klimaneutraler Wohnungsbau',
    score: 0.55,
    text_preview: 'Klimaneutrale Sanierung und sozialer Wohnungsbau gehören für uns zusammen...',
  },
  {
    chunk_id: 'dielinke_p7_c3',
    party: 'dielinke',
    page: 7,
    section_path: 'Wohnen ist Menschenrecht',
    score: 0.41,
    text_preview: 'Mieten deckeln, leerstehende Wohnungen vergesellschaften, Spekulation bremsen...',
  },
]

// A small German answer that lands a verified [SPD – Seite 17] citation
// plus one fabricated [SPD – Seite 99] that the verifier will catch.
export const TOKENS_DEMO = [
  'Die ',
  'SPD ',
  'gründet ',
  'eine ',
  'landeseigene ',
  'Wohnbaugesellschaft ',
  'BWohnen ',
  '[SPD – Seite 17]',
  '. ',
  'Sie ',
  'will ',
  'außerdem ',
  'die ',
  'Mietpreisbremse ',
  'ausweiten ',
  '[SPD – Seite 17]',
  '. ',
  'Zur ',
  'Hochschulpolitik ',
  'siehe ',
  'auch ',
  '[SPD – Seite 99]',
  '.',
]

export const CITATIONS_DEMO = {
  verified: [
    { party: 'spd', page: 17, raw: '[SPD – Seite 17]' },
  ],
  unverified: [
    { party: 'spd', page: 99, raw: '[SPD – Seite 99]' },
  ],
}

export const EMPTY_CITATIONS = { verified: [], unverified: [] }

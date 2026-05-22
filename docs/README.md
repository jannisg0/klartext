# docs/

Projektdokumentation außerhalb von `CLAUDE.md` und `README.md`.

## `docs/design/`

Visueller Entwurfs-Ort für die Frontend-Integration. Die Datei
`Klartext.html` ist die Übergabe aus **Claude Design** – ein
einzelnes statisches HTML-Dokument mit Tailwind-Klassen, das alle
UI-Zustände abbildet (Empty, Streaming, Citations, FilterBar +
PersonaSelector, Below-Threshold, Error).

In **Session F** wird dieses Markup pro Region in JSX-Komponenten
unter `frontend/src/components/` übersetzt. Tailwind-Klassen bleiben
im ersten Durchgang unverändert; Restrukturierung passiert erst nach
Sign-off pro Zustand.

`Klartext.html` wird vom Nutzer in diesen Ordner abgelegt und ist
**Referenz, nicht Build-Artefakt** – keine Auslieferung an den
Browser, kein Pipeline-Step.

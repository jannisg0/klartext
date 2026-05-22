# Evaluation (Session G)

Stand heute: **Skeleton in `scripts/eval.py`**, keine ragas-Integration
ausgerollt. Dieser Doc legt fest wie die Qualitätsmessung aussehen
wird, damit der Ingest-Output und das Frontend-Design schon
kompatibel sind.

---

## Ziel

Reproduzierbar messen, ob die Pipeline (Retrieval + Generation) für
typische Wahlprogramm-Fragen die richtigen Quellen findet und
verifizierbar zitiert — **nicht** subjektiv ob die Antwort "gut"
klingt.

---

## Goldset

`data/eval/goldset.json` — manuell kuratierte Q&A-Paare.
Format siehe `data/eval/_example.json`:

```json
{
  "version": "1.0",
  "questions": [
    {
      "id": "q001",
      "question": "Was sagt die SPD zur Vermögensteuer?",
      "party_filter": ["spd"],
      "politician": null,
      "expected_chunks": ["spd_p12_c3", "spd_p13_c1"],
      "expected_answer_contains": ["Vermögensteuer", "Wiedereinführung"],
      "notes": "Erwartet wird Bezug auf Vermögensteuer-Position im SPD-Programm"
    }
  ]
}
```

**Pro Frage erfasst:**
- `expected_chunks` — chunk_ids die im Top-K erscheinen sollen (Recall).
- `expected_answer_contains` — Substrings die in der Antwort
  vorkommen sollen (lockerer als exakter Wortlaut).
- `party_filter` / `politician` — wie der Endnutzer sie setzen würde.

Ziel-Größe: 30–50 Fragen, gemischt aus allen 6 Parteien + thematischer
Cross-Cut (Klima, Steuern, Wohnen, Bildung, Außenpolitik).

---

## Metriken (geplant via ragas)

[ragas](https://docs.ragas.io/) misst RAG-Qualität ohne ein
Vergleichsmodell — Bewertung kommt durch das LLM selbst plus
heuristische Checks:

| Metrik | Bedeutung |
|--------|-----------|
| `context_precision` | Wie viele der gelieferten Chunks sind relevant für die Frage? |
| `context_recall` | Wie viele der relevanten Chunks im Goldset wurden gefunden? |
| `faithfulness` | Stützt sich die Antwort durchweg auf den gelieferten Kontext? |
| `answer_relevancy` | Beantwortet die Antwort tatsächlich die gestellte Frage? |

`context_precision` + `context_recall` sind **die wichtigen** für uns
— misst direkt die Retrieval-Qualität, unabhängig vom LLM-Output.

Klartext-spezifische Zusatz-Metrik (nicht ragas):

| Metrik | Bedeutung |
|--------|-----------|
| `citation_faithfulness` | Anteil der `[PARTEI – Seite X]`-Citations, die vom Citation-Verifier als verified zurückgegeben werden |

`citation_faithfulness` wird direkt aus dem `citations`-Event berechnet:
`len(verified) / (len(verified) + len(unverified))`. Goal: ≥0.95.

---

## CLI (geplant)

```bash
uv run python -m scripts.eval \
  --goldset data/eval/goldset.json \
  --runs 3 \
  --output logs/eval_$(date +%Y%m%d_%H%M%S)
```

Schritte pro Frage:
1. Sende `query` + `party_filter` + `politician` an `/chat`.
2. Sammle `sources`-Liste, vollständige Antwort, `citations`-Resultat.
3. Berechne ragas-Metriken (LLM-as-Judge gegen retrieved Chunks).
4. Berechne `citation_faithfulness` aus dem `citations`-Event.
5. Vergleiche `sources.chunk_ids` mit `expected_chunks` → Recall@K.

**Output:** JSON-Report + Markdown-Summary unter `logs/`.

```
logs/
  eval_20260615_1430/
    raw.jsonl                # ein Eintrag pro Frage
    metrics.json             # aggregierte ragas + custom Metriken
    summary.md               # Markdown-Übersicht für Reviewer
```

---

## A/B-Vergleiche

Der `LLM_BACKEND=mlx|ollama`-Switch (siehe
[`DESIGN-DECISIONS.md`](DESIGN-DECISIONS.md)) ermöglicht
gegenüberstellende Eval-Läufe:

```bash
LLM_BACKEND=ollama OLLAMA_MODEL_MAIN=qwen3.5:2b-mlx uv run ... # MLX-Pfad
LLM_BACKEND=ollama OLLAMA_MODEL_MAIN=qwen3:14b      uv run ... # Legacy-Baseline
```

Sweeps über `RERANK_TOP_K`, `RERANK_SCORE_THRESHOLD`,
`CONTEXTUAL_ENRICHMENT_ENABLED` kommen in derselben Form.

---

## Wann läuft Eval

- **Lokal vor jedem PR**, der `backend/retriever.py`,
  `backend/reranker.py`, `backend/prompt_builder.py`,
  `backend/llm.py`, oder Modell-Config anfasst.
- **Nach jedem Modell-Tausch** im `.env`.
- **Nach jedem Ingest** über alle Parteien — Sanity-Check dass die
  Retrieval-Performance über neue Daten gehalten wird.

CI-Integration: out of scope für dieses Hochschulprojekt; lokal
ausreichend.

---

## Stand

- `data/eval/_example.json` ✓
- `scripts/eval.py` ist Stub: `"""Goldset evaluation with ragas
  metrics. Implementation in Session G."""` — wartet auf Goldset-
  Kuration.

Nächste Schritte (Session G):
1. 30+ Goldset-Fragen kuratieren über die 6 bereits ingesteten Parteien.
2. `scripts/eval.py` Implementation: ragas + custom citation-metric.
3. Baseline-Lauf gegen `qwen3.5:2b-mlx` einfangen.
4. Iteration: Threshold / TopK / Few-Shot tunen, bis
   `context_recall ≥ 0.7` und `citation_faithfulness ≥ 0.95`.

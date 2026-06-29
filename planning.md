# Provenance Guard Planning

## 1. Project Overview

Provenance Guard is a Flask backend that evaluates submitted text and returns a transparent authorship attribution: `likely_ai`, `likely_human`, or `uncertain`. The system combines an LLM-based signal with local stylometric heuristics, returns a confidence score, generates a reader-facing transparency label, supports creator appeals, applies rate limits, and writes structured audit log entries.

The project is intentionally cautious. It does not claim proof of authorship. It provides context, exposes the signals used, and allows creators to appeal.

## 2. Detection Signals

The backend uses two distinct detection signals:

1. Groq LLM signal using `llama-3.3-70b-versatile`
2. Pure Python stylometric heuristic signal

The LLM signal is weighted at 60%. The stylometric signal is weighted at 40%.

## 3. What Each Signal Measures

### LLM Signal

The LLM signal asks Groq's `llama-3.3-70b-versatile` model to assess the text and return a JSON-style AI-likelihood score from 0.0 to 1.0 with a short reason. The code tries to parse strict JSON first, then extracts JSON-like content or a score from imperfect model output.

If `GROQ_API_KEY` is missing or the API call fails, the app uses a safe fallback heuristic score so local demos and grading do not crash.

### Stylometric Signal

The stylometric signal measures:

- Sentence length variance
- Type-token ratio
- Punctuation density
- Average sentence length
- Repeated three-word phrase ratio

These metrics are combined into an AI-likelihood score from 0.0 to 1.0.

## 4. What Each Signal Misses

The LLM signal misses:

- It is not definitive proof of authorship.
- It can overfit to polished or formulaic human writing.
- It depends on model behavior and prompt compliance.
- It can fail or return malformed output.

The stylometric signal misses:

- Poetry or highly repetitive creative writing may be falsely scored as AI.
- Formal academic writing by humans may receive higher AI-likelihood scores.
- Non-native English writing may be misclassified because some heuristics assume certain fluency patterns.
- Short submissions provide too little evidence for stable metrics.

## 5. Confidence Scoring Thresholds

Combined score:

```text
combined_score = (0.60 * llm_score) + (0.40 * stylometric_score)
```

Attribution thresholds:

- `score >= 0.75`: `likely_ai`
- `score <= 0.35`: `likely_human`
- Otherwise: `uncertain`

Confidence represents distance away from uncertainty rather than the raw AI score:

- High likely AI scores produce confidence around 0.85 to 0.95.
- High likely human scores produce confidence around 0.85 to 0.95.
- Borderline scores produce confidence around 0.50 to 0.70.

## 6. Transparency Label Variants

High-confidence AI:

> This content shows strong signals of AI generation. We are displaying this label to give readers context, not as a final judgment of authorship.

High-confidence human:

> This content shows strong signals of human authorship. No AI-generation label is currently applied.

Uncertain:

> Our system could not confidently determine whether this content was AI-generated or human-written. Readers should treat the attribution as uncertain, and the creator may appeal this result.

## 7. Appeals Workflow

Creators can appeal a classification by calling `POST /appeal` with a `content_id` and `creator_reasoning`.

Appeal behavior:

- Validate required JSON fields.
- Find a prior audit entry with the submitted `content_id`.
- Write a new structured audit entry with `status` set to `under_review`.
- Preserve the original classification fields for auditability.
- Include the creator's appeal reasoning.
- Return a confirmation response.

## 8. Edge Cases

Handled edge cases:

- Missing or invalid JSON body
- Missing `text`
- Empty `text`
- Missing `creator_id`
- Missing `content_id` on appeal
- Missing `creator_reasoning` on appeal
- Unknown `content_id` on appeal
- Missing `GROQ_API_KEY`
- Groq request failure
- Groq output that is not valid JSON
- Empty audit log
- Invalid log lines are skipped when reading
- Submission rate limit exceeded

## 9. Architecture Section

The backend is organized into three primary modules:

- `app.py`: Flask application, route validation, rate limiting, response formatting
- `detection.py`: LLM signal, stylometric signal, scoring, attribution, labels
- `audit_log.py`: Structured JSONL audit log writing and reading

JSONL was chosen for the audit log because it is simple, reliable for an educational backend, easy to inspect, and append-friendly.

## 10. ASCII Architecture Diagram

```text
Architecture

Submission flow:

Client
|
v
POST /submit
|
v
Validate JSON input
|
v
LLM Signal + Stylometric Signal
|
v
Confidence Scoring
|
v
Transparency Label Generator
|
v
Structured Audit Log
|
v
JSON Response

Appeal flow:

Client
|
v
POST /appeal
|
v
Find content_id
|
v
Update status to under_review
|
v
Write appeal to audit log
|
v
JSON confirmation
```

## 11. AI Tool Plan for M3, M4, M5

### M3: Backend Implementation

Use AI assistance to draft Flask route structure, validation logic, modular helper functions, and robust error responses. Manually review generated code to ensure field names match the project requirements exactly.

### M4: Detection and Scoring

Use AI assistance to brainstorm stylometric metrics and confidence mapping. Manually tune thresholds so confidence communicates certainty instead of simply echoing the raw AI-likelihood score.

### M5: Documentation and Demo Readiness

Use AI assistance to turn the implementation into a clear README with setup steps, curl commands, limitations, sample outputs, and portfolio talking points. Manually verify commands locally and confirm that missing `GROQ_API_KEY` does not break the app.

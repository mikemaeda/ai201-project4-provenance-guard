# Provenance Guard

Provenance Guard is a Flask backend for cautious content provenance labeling. It accepts submitted text, evaluates it with multiple detection signals, returns `likely_ai`, `likely_human`, or `uncertain`, generates a transparency label, supports appeals, rate limits submissions, and stores a structured JSON audit log.

This project does not claim proof of authorship. It is designed to provide context and preserve an appeal path.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local `.env` file if you want Groq-powered LLM scoring:

```bash
GROQ_API_KEY=your_groq_api_key_here
```

`.env` is ignored by git. If `GROQ_API_KEY` is missing, the app still runs and uses a local fallback heuristic for the LLM signal.

## Run

```bash
python app.py
```

The API runs at:

```text
http://localhost:5000
```

If port 5000 is busy, choose another port:

```bash
PORT=5001 python app.py
```

## API Endpoints

### `POST /submit`

Request:

```json
{
  "text": "content to analyze",
  "creator_id": "creator-id"
}
```

Response:

```json
{
  "content_id": "generated-id",
  "creator_id": "creator-id",
  "attribution": "likely_ai",
  "confidence": 0.86,
  "label": "This content shows strong signals of AI generation. We are displaying this label to give readers context, not as a final judgment of authorship.",
  "signals": {
    "llm_score": 0.88,
    "llm_reason": "Model or fallback reason.",
    "stylometric_score": 0.74,
    "stylometric_metrics": {
      "word_count": 98,
      "sentence_count": 5,
      "average_sentence_length": 19.6,
      "sentence_length_variance": 9.04,
      "type_token_ratio": 0.57,
      "punctuation_density": 0.032,
      "repeated_phrase_ratio": 0.01
    }
  },
  "status": "classified"
}
```

### `POST /appeal`

Request:

```json
{
  "content_id": "generated-id",
  "creator_reasoning": "I wrote this draft myself and can provide notes."
}
```

Response:

```json
{
  "content_id": "generated-id",
  "status": "under_review",
  "message": "Appeal received and content marked for review."
}
```

### `GET /log`

Returns recent audit log entries:

```json
{
  "entries": []
}
```

Use `?limit=10` to request a smaller or larger recent window. The app caps the maximum at 200.

## Example Test Commands

Submit polished text:

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"creator_id":"writer-001","text":"In today\u0027s rapidly evolving digital landscape, organizations must adopt a thoughtful and scalable approach to governance. By combining transparent policies, consistent review workflows, and measurable accountability, teams can build trust while reducing operational risk."}'
```

Submit more informal human text:

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"creator_id":"writer-002","text":"I started this paragraph three times and kept changing my mind. The first version was too stiff, the second sounded like a bad speech, and this one is at least closer to how I actually talk when I am trying to explain something."}'
```

Appeal a result:

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id":"PASTE_CONTENT_ID_HERE","creator_reasoning":"I wrote this myself and can provide outlines, drafts, and revision history."}'
```

Read the audit log:

```bash
curl -s http://localhost:5000/log
```

## Architecture Overview

```text
Client -> POST /submit -> Flask validation
       -> Groq LLM signal + stylometric signal
       -> weighted scoring and attribution
       -> transparency label
       -> JSONL audit log
       -> JSON response

Client -> POST /appeal -> lookup content_id
       -> append under_review audit entry
       -> JSON confirmation
```

Files:

- `app.py`: Flask routes, request validation, rate limiting, JSON responses
- `detection.py`: Groq signal, fallback signal, stylometric metrics, scoring, labels
- `audit_log.py`: JSONL audit log append and read helpers
- `planning.md`: project plan and architecture details

## Detection Signals

### Signal 1: Groq LLM Classification

The LLM signal uses Groq's `llama-3.3-70b-versatile` model. The prompt asks for a JSON-style assessment with:

- `score`: AI-likelihood from 0.0 to 1.0
- `reason`: short explanation

The parser handles strict JSON, JSON embedded in extra text, or a score embedded in imperfect output. If the Groq key is missing or an API call fails, the app uses a fallback score based on the stylometric heuristic so the backend remains runnable.

### Signal 2: Stylometric Heuristics

The local heuristic measures sentence length variance, type-token ratio, punctuation density, average sentence length, and repeated phrase ratio.

This captures surface-level writing patterns that can appear in generated text: uniform sentence rhythm, lower lexical variety, polished punctuation, and repeated phrases. It misses context, author history, drafting process, and legitimate style differences.

## Confidence Scoring

Scores are combined like this:

```text
combined_score = (0.60 * llm_score) + (0.40 * stylometric_score)
```

Attribution thresholds:

- `score >= 0.75`: `likely_ai`
- `score <= 0.35`: `likely_human`
- Otherwise: `uncertain`

Confidence is distance away from uncertainty, not the raw AI score. A very high AI-likelihood score and a very low AI-likelihood score can both have high confidence. Borderline scores stay closer to 0.50 to 0.70.

## Example Submissions

Example 1, polished policy-style prose:

```json
{
  "attribution": "uncertain",
  "confidence": 0.67,
  "signals": {
    "llm_score": 0.71,
    "stylometric_score": 0.58
  }
}
```

Example 2, informal revision-focused prose:

```json
{
  "attribution": "likely_human",
  "confidence": 0.82,
  "signals": {
    "llm_score": 0.22,
    "stylometric_score": 0.31
  }
}
```

Actual scores may vary when `GROQ_API_KEY` is set because the LLM signal is live model output.

## Transparency Label Table

| Variant | Exact Label Text |
| --- | --- |
| High-confidence AI | This content shows strong signals of AI generation. We are displaying this label to give readers context, not as a final judgment of authorship. |
| High-confidence human | This content shows strong signals of human authorship. No AI-generation label is currently applied. |
| Uncertain | Our system could not confidently determine whether this content was AI-generated or human-written. Readers should treat the attribution as uncertain, and the creator may appeal this result. |

## Rate Limiting

`/submit` is limited with Flask-Limiter:

```python
@limiter.limit("10 per minute;100 per day")
```

These limits are realistic for a writer submitting work manually, while slowing scripts or abuse. Ten submissions per minute allows normal testing and occasional retries. One hundred per day is enough for a creator or reviewer demo, but low enough to discourage bulk automated classification attempts.

## Audit Log

The app writes `audit_log.jsonl`, with one JSON object per line. Each attribution decision logs:

- Timestamp
- Content ID
- Creator ID
- Text preview, not full text
- Attribution
- Confidence
- LLM score
- Stylometric score
- Stylometric metrics
- Label
- Status
- Appeal reasoning if appealed

Sample log entries:

```json
{"timestamp":"2026-06-28T22:50:00+00:00","event_type":"classification","content_id":"b77a2b4d","creator_id":"writer-001","text_preview":"In today's rapidly evolving digital landscape...","attribution":"likely_ai","confidence":0.88,"llm_score":0.91,"stylometric_score":0.77,"stylometric_metrics":{"word_count":93,"sentence_count":4,"average_sentence_length":23.25,"sentence_length_variance":6.18,"type_token_ratio":0.62,"punctuation_density":0.031,"repeated_phrase_ratio":0.0},"label":"This content shows strong signals of AI generation. We are displaying this label to give readers context, not as a final judgment of authorship.","status":"classified","appeal_reasoning":null}
{"timestamp":"2026-06-28T22:52:00+00:00","event_type":"classification","content_id":"31f83b10","creator_id":"writer-002","text_preview":"I started this paragraph three times and kept changing my mind...","attribution":"likely_human","confidence":0.84,"llm_score":0.2,"stylometric_score":0.3,"stylometric_metrics":{"word_count":48,"sentence_count":2,"average_sentence_length":24.0,"sentence_length_variance":4.0,"type_token_ratio":0.88,"punctuation_density":0.018,"repeated_phrase_ratio":0.0},"label":"This content shows strong signals of human authorship. No AI-generation label is currently applied.","status":"classified","appeal_reasoning":null}
{"timestamp":"2026-06-28T22:55:00+00:00","event_type":"appeal","content_id":"b77a2b4d","creator_id":"writer-001","text_preview":"In today's rapidly evolving digital landscape...","attribution":"likely_ai","confidence":0.88,"llm_score":0.91,"stylometric_score":0.77,"stylometric_metrics":{"word_count":93,"sentence_count":4,"average_sentence_length":23.25,"sentence_length_variance":6.18,"type_token_ratio":0.62,"punctuation_density":0.031,"repeated_phrase_ratio":0.0},"label":"This content shows strong signals of AI generation. We are displaying this label to give readers context, not as a final judgment of authorship.","status":"under_review","appeal_reasoning":"I wrote this myself and can provide revision history."}
```

## Known Limitations

- Poetry or highly repetitive creative writing may be falsely scored as AI by stylometric heuristics.
- Formal academic writing by humans may receive higher AI-likelihood scores.
- Non-native English writing may be misclassified because some heuristics assume certain fluency patterns.
- LLM-based detection is not definitive and should not be treated as proof.
- Very short text can produce unstable scores because there is not enough evidence.
- A determined user may intentionally rewrite text to avoid surface-level detection signals.

## Spec Reflection

The strongest design choice is separating classification from judgment. The API exposes signals, confidence, and labels, but the label text avoids declaring authorship as fact. The appeal workflow also matters because provenance systems affect real creators. Even simple audit logging improves accountability by preserving what the system decided and why.

The hardest tradeoff is making confidence meaningful. A raw AI-likelihood score is not the same as confidence. This implementation maps confidence based on distance from the uncertain region so both strong human and strong AI results can be high confidence.

## AI Usage

AI assistance was useful in two specific ways:

- Drafting and refining the Flask API structure, including validation behavior and JSON response shapes.
- Brainstorming stylometric features and documentation language for limitations, confidence scoring, and portfolio explanation.

All generated logic should be manually reviewed before submission, especially the scoring thresholds and README examples.

## Portfolio Walkthrough Talking Points

- "This backend uses two independent signals: an LLM review and local stylometric analysis."
- "The system is cautious: it returns `uncertain` for borderline cases and avoids claiming proof."
- "Confidence is based on distance from uncertainty, not the raw AI-likelihood score."
- "Every classification and appeal writes a structured audit log for accountability."
- "The app still runs without a Groq key, which makes local grading and demos reliable."
- "Rate limiting protects the endpoint from scripted abuse while allowing normal writer workflows."

# Sample Requests

## Health Check

```bash
curl -s http://localhost:5000/health
```

## Submit Text

```bash
curl -s -X POST http://localhost:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"creator_id":"writer-001","text":"This is the content I want Provenance Guard to analyze."}'
```

## Appeal Classification

```bash
curl -s -X POST http://localhost:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id":"PASTE_CONTENT_ID_HERE","creator_reasoning":"I wrote this myself and can provide drafts."}'
```

## Read Audit Log

```bash
curl -s http://localhost:5000/log
```

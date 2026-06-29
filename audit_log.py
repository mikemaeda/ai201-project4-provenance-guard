import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

LOG_PATH = Path("audit_log.jsonl")


def append_audit_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_entry(entry)
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    return normalized


def get_recent_entries(limit: int = 50) -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []

    with LOG_PATH.open("r", encoding="utf-8") as log_file:
        lines = log_file.readlines()

    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return entries


def mark_under_review(content_id: str, creator_reasoning: str) -> bool:
    entries = get_all_entries()
    original_entry = next(
        (entry for entry in reversed(entries) if entry.get("content_id") == content_id),
        None,
    )

    if not original_entry:
        return False

    updated_entries = []
    for entry in entries:
        if entry.get("content_id") == content_id:
            updated_entries.append(
                {
                    **entry,
                    "status": "under_review",
                    "appeal_reasoning": creator_reasoning,
                }
            )
        else:
            updated_entries.append(entry)

    write_all_entries(updated_entries)

    appeal_entry = {
        **original_entry,
        "status": "under_review",
        "appeal_reasoning": creator_reasoning,
        "event_type": "appeal",
    }
    append_audit_entry(appeal_entry)
    return True


def get_all_entries() -> List[Dict[str, Any]]:
    if not LOG_PATH.exists():
        return []

    entries = []
    with LOG_PATH.open("r", encoding="utf-8") as log_file:
        for line in log_file:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return entries


def write_all_entries(entries: List[Dict[str, Any]]) -> None:
    with LOG_PATH.open("w", encoding="utf-8") as log_file:
        for entry in entries:
            log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    signals = entry.get("signals", {})
    stylometric_metrics = signals.get("stylometric_metrics", entry.get("stylometric_metrics", {}))

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": entry.get("event_type", "classification"),
        "content_id": entry.get("content_id"),
        "creator_id": entry.get("creator_id"),
        "text_preview": entry.get("text_preview"),
        "attribution": entry.get("attribution"),
        "confidence": entry.get("confidence"),
        "llm_score": signals.get("llm_score", entry.get("llm_score")),
        "stylometric_score": signals.get(
            "stylometric_score", entry.get("stylometric_score")
        ),
        "stylometric_metrics": stylometric_metrics,
        "label": entry.get("label"),
        "status": entry.get("status", "classified"),
        "appeal_reasoning": entry.get("appeal_reasoning"),
    }

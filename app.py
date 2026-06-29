import os
import uuid
from typing import Any, Dict, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from audit_log import append_audit_entry, get_recent_entries, mark_under_review
from detection import classify_text

load_dotenv()

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


def error_response(message: str, status_code: int) -> Tuple[Any, int]:
    return jsonify({"error": message}), status_code


def get_json_body() -> Tuple[Dict[str, Any], Tuple[Any, int] | None]:
    if not request.is_json:
        return {}, error_response("Request body must be JSON.", 400)

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return {}, error_response("Request body must be a valid JSON object.", 400)

    return body, None


@app.errorhandler(429)
def rate_limit_handler(error: Any) -> Tuple[Any, int]:
    return (
        jsonify(
            {
                "error": "Rate limit exceeded.",
                "detail": str(error.description),
            }
        ),
        429,
    )


@app.route("/health", methods=["GET"])
def health() -> Any:
    return jsonify({"status": "ok"})


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit() -> Tuple[Any, int]:
    body, error = get_json_body()
    if error:
        return error

    text = body.get("text")
    creator_id = body.get("creator_id")

    if not isinstance(text, str) or not text.strip():
        return error_response("Missing or empty required field: text.", 400)

    if not isinstance(creator_id, str) or not creator_id.strip():
        return error_response("Missing or empty required field: creator_id.", 400)

    content_id = str(uuid.uuid4())
    classification = classify_text(text)

    response_body = {
        "content_id": content_id,
        "creator_id": creator_id.strip(),
        "attribution": classification["attribution"],
        "confidence": classification["confidence"],
        "label": classification["label"],
        "signals": {
            "llm_score": classification["llm_score"],
            "llm_reason": classification["llm_reason"],
            "stylometric_score": classification["stylometric_score"],
            "stylometric_metrics": classification["stylometric_metrics"],
        },
        "status": "classified",
    }

    append_audit_entry(
        {
            **response_body,
            "text_preview": text.strip()[:180],
            "appeal_reasoning": None,
        }
    )

    return jsonify(response_body), 200


@app.route("/appeal", methods=["POST"])
def appeal() -> Tuple[Any, int]:
    body, error = get_json_body()
    if error:
        return error

    content_id = body.get("content_id")
    creator_reasoning = body.get("creator_reasoning")

    if not isinstance(content_id, str) or not content_id.strip():
        return error_response("Missing or empty required field: content_id.", 400)

    if not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return error_response("Missing or empty required field: creator_reasoning.", 400)

    updated = mark_under_review(content_id.strip(), creator_reasoning.strip())
    if not updated:
        return error_response("No audit log entry found for that content_id.", 404)

    return (
        jsonify(
            {
                "content_id": content_id.strip(),
                "status": "under_review",
                "message": "Appeal received and content marked for review.",
            }
        ),
        200,
    )


@app.route("/log", methods=["GET"])
def log() -> Any:
    limit = request.args.get("limit", default=50, type=int)
    safe_limit = min(max(limit, 1), 200)
    return jsonify({"entries": get_recent_entries(limit=safe_limit)})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)

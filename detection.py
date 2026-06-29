import json
import os
import re
import statistics
from typing import Any, Dict, List

from groq import Groq

HIGH_CONFIDENCE_AI_LABEL = (
    "This content shows strong signals of AI generation. We are displaying this "
    "label to give readers context, not as a final judgment of authorship."
)
HIGH_CONFIDENCE_HUMAN_LABEL = (
    "This content shows strong signals of human authorship. No AI-generation "
    "label is currently applied."
)
UNCERTAIN_LABEL = (
    "Our system could not confidently determine whether this content was "
    "AI-generated or human-written. Readers should treat the attribution as "
    "uncertain, and the creator may appeal this result."
)


def classify_text(text: str) -> Dict[str, Any]:
    llm_signal = get_llm_signal(text)
    stylometric_signal = get_stylometric_signal(text)

    llm_score = llm_signal["score"]
    stylometric_score = stylometric_signal["score"]
    combined_score = (0.6 * llm_score) + (0.4 * stylometric_score)

    attribution = map_attribution(combined_score)
    confidence = calculate_confidence(combined_score)
    label = generate_label(attribution)

    return {
        "attribution": attribution,
        "confidence": confidence,
        "label": label,
        "llm_score": round(llm_score, 3),
        "llm_reason": llm_signal["reason"],
        "stylometric_score": round(stylometric_score, 3),
        "stylometric_metrics": stylometric_signal["metrics"],
        "combined_score": round(combined_score, 3),
    }


def get_llm_signal(text: str) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        fallback = fallback_llm_score(text)
        return {
            "score": fallback,
            "reason": "GROQ_API_KEY is missing; used local fallback heuristic.",
        }

    prompt = (
        "Assess whether the following text is AI-generated. Return only JSON with "
        'keys "score" and "reason". score must be a number from 0.0 to 1.0 where '
        "1.0 means very likely AI-generated and 0.0 means very likely human-written.\n\n"
        f"TEXT:\n{text[:6000]}"
    )

    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a cautious content provenance reviewer.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=220,
        )
        raw_output = completion.choices[0].message.content or ""
        parsed = parse_llm_json(raw_output)
        return {
            "score": clamp(float(parsed.get("score", 0.5))),
            "reason": str(parsed.get("reason", "Model returned no reason."))[:300],
        }
    except Exception as exc:
        fallback = fallback_llm_score(text)
        return {
            "score": fallback,
            "reason": f"Groq call failed; used fallback heuristic. Error: {exc}",
        }


def parse_llm_json(raw_output: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    score_match = re.search(r"(?:score|ai-likelihood|likelihood)\D+([01](?:\.\d+)?)", raw_output, re.I)
    if score_match:
        return {"score": float(score_match.group(1)), "reason": raw_output[:300]}

    return {"score": 0.5, "reason": "Could not parse model output reliably."}


def get_stylometric_signal(text: str) -> Dict[str, Any]:
    sentences = split_sentences(text)
    words = re.findall(r"\b[\w'-]+\b", text.lower())
    word_count = len(words)
    unique_words = len(set(words))
    sentence_lengths = [len(re.findall(r"\b[\w'-]+\b", sentence)) for sentence in sentences]
    sentence_lengths = [length for length in sentence_lengths if length > 0]

    avg_sentence_length = statistics.mean(sentence_lengths) if sentence_lengths else 0.0
    sentence_length_variance = (
        statistics.pvariance(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
    )
    type_token_ratio = unique_words / word_count if word_count else 0.0
    punctuation_count = len(re.findall(r"[.,;:!?]", text))
    punctuation_density = punctuation_count / max(len(text), 1)
    repeated_phrase_ratio = calculate_repeated_phrase_ratio(words)

    # The score captures patterns often seen in generated prose: moderate sentence
    # uniformity, lower lexical variety, polished punctuation, and phrase repetition.
    uniformity_score = 1.0 - clamp(sentence_length_variance / 80.0)
    lexical_repetition_score = 1.0 - clamp(type_token_ratio / 0.75)
    sentence_length_score = clamp((avg_sentence_length - 10.0) / 18.0)
    punctuation_score = clamp(punctuation_density / 0.045)
    phrase_score = clamp(repeated_phrase_ratio * 4.0)

    score = (
        0.25 * uniformity_score
        + 0.25 * lexical_repetition_score
        + 0.2 * sentence_length_score
        + 0.15 * punctuation_score
        + 0.15 * phrase_score
    )

    metrics = {
        "word_count": word_count,
        "sentence_count": len(sentence_lengths),
        "average_sentence_length": round(avg_sentence_length, 3),
        "sentence_length_variance": round(sentence_length_variance, 3),
        "type_token_ratio": round(type_token_ratio, 3),
        "punctuation_density": round(punctuation_density, 4),
        "repeated_phrase_ratio": round(repeated_phrase_ratio, 3),
    }

    return {"score": clamp(score), "metrics": metrics}


def fallback_llm_score(text: str) -> float:
    stylometric = get_stylometric_signal(text)
    metrics = stylometric["metrics"]
    score = stylometric["score"]

    if metrics["word_count"] < 30:
        score = (score + 0.5) / 2

    return clamp(score)


def split_sentences(text: str) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def calculate_repeated_phrase_ratio(words: List[str], phrase_size: int = 3) -> float:
    if len(words) < phrase_size:
        return 0.0

    phrases = [
        tuple(words[index : index + phrase_size])
        for index in range(0, len(words) - phrase_size + 1)
    ]
    repeated_phrases = len(phrases) - len(set(phrases))
    return repeated_phrases / max(len(phrases), 1)


def map_attribution(score: float) -> str:
    if score >= 0.75:
        return "likely_ai"
    if score <= 0.35:
        return "likely_human"
    return "uncertain"


def calculate_confidence(score: float) -> float:
    if score >= 0.75:
        return round(0.75 + (min(score, 1.0) - 0.75) * 0.8, 3)
    if score <= 0.35:
        return round(0.75 + (0.35 - max(score, 0.0)) * (0.2 / 0.35), 3)

    midpoint = 0.55
    distance = abs(score - midpoint)
    return round(0.5 + min(distance / 0.2, 1.0) * 0.2, 3)


def generate_label(attribution: str) -> str:
    if attribution == "likely_ai":
        return HIGH_CONFIDENCE_AI_LABEL
    if attribution == "likely_human":
        return HIGH_CONFIDENCE_HUMAN_LABEL
    return UNCERTAIN_LABEL


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))

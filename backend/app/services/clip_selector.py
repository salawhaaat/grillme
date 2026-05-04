"""Clip selector — matches LLM responses to pre-rendered scenario clips."""
import re

SIMILARITY_THRESHOLD = 0.25  # lowered from 0.7 — LLM responses rarely match exactly
FALLBACK_THRESHOLD = 0.0     # always use best available clip for the phase if no good match


def normalize_text(text: str) -> set[str]:
    # Remove stop words that inflate similarity scores
    STOP_WORDS = {"i", "a", "the", "is", "it", "to", "and", "of", "in", "you", "me", "my", "we", "do", "on", "at", "be", "or", "an"}
    words = re.sub(r"[^\w\s]", "", text.lower()).split()
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_match(response_text: str, current_phase: str, manifest_clips: list[dict]) -> dict | None:
    response_words = normalize_text(response_text)
    if not response_words:
        return None

    phase_clips = [c for c in manifest_clips if c.get("phase") == current_phase]
    if not phase_clips:
        return None

    best_match = None
    best_score = 0.0
    for clip in phase_clips:
        clip_words = normalize_text(clip.get("text", ""))
        score = jaccard_similarity(response_words, clip_words)
        if score > best_score:
            best_score = score
            best_match = {**clip, "score": score}

    # Return best match if above threshold, otherwise return best available for phase
    # This ensures pre-rendered clips are always used when available
    if best_match and best_score >= SIMILARITY_THRESHOLD:
        return best_match

    # Fallback: use best available clip for this phase (avoids live render)
    if best_match:
        return best_match

    return None

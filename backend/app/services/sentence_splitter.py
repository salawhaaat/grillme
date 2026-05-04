"""
Async sentence splitter for streaming LLM token output.

Accumulates tokens and yields complete sentences as detected by pySBD.
Handles edge cases like "Dr.", "3.14", abbreviations, etc.
"""

from typing import AsyncIterator

import pysbd


async def split_sentences(
    token_stream: AsyncIterator[str],
    min_length: int = 15,
) -> AsyncIterator[str]:
    """
    Consume an async stream of LLM text tokens and yield complete sentences.

    Uses pySBD for robust sentence boundary detection (handles abbreviations,
    decimals, URLs, etc.).  Merges fragments shorter than *min_length* into
    the next sentence to avoid sending trivially short TTS requests.
    """
    segmenter = pysbd.Segmenter(language="en", clean=False)
    buf = ""

    async for token in token_stream:
        buf += token

        # pySBD works on the full buffer and returns a list of sentences.
        # All but the last element are guaranteed to be complete.
        segments = segmenter.segment(buf)

        if len(segments) <= 1:
            # No complete sentence boundary found yet — keep accumulating.
            continue

        # Yield all complete sentences (everything except the last fragment).
        for sent in segments[:-1]:
            sent = sent.strip()
            if not sent:
                continue
            # Merge tiny fragments (e.g. "Yes.") with the next sentence
            if len(sent) < min_length:
                buf = sent + " " + segments[-1]
                segments[-1] = buf
                continue
            yield sent

        # Keep the trailing incomplete fragment for the next iteration.
        buf = segments[-1]

    # Flush any remaining text after the token stream ends.
    if buf.strip():
        yield buf.strip()

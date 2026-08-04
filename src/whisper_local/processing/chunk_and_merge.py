"""Memory-bounded, multi-pass meeting-document generation for local Ollama."""

from __future__ import annotations

import os
import re
from typing import Iterable


# Keep the source chunk small enough that the prompt, source, and response fit in
# a modest local model context.  The old 3,500-token chunks were routinely larger
# than llama3.2:3b's default context *before* its very large instruction prompt.
CHUNK_SIZE_TOKENS = int(os.environ.get("WHISPER_SUMMARY_CHUNK_TOKENS", "1400"))
REDUCE_SIZE_TOKENS = int(os.environ.get("WHISPER_SUMMARY_REDUCE_TOKENS", "2200"))
OLLAMA_CONTEXT_TOKENS = int(os.environ.get("WHISPER_OLLAMA_CONTEXT_TOKENS", "4096"))
DEFAULT_MODEL = os.environ.get("WHISPER_LLM_MODEL", "llama3.2:3b")


def count_tokens(text: str) -> int:
    """Conservative, dependency-free token estimate for chunk sizing."""
    return max(1, (len(text) + 3) // 4)


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE_TOKENS) -> list[str]:
    """Split at paragraph/sentence boundaries, with a safe hard-split fallback."""
    if not text or not text.strip():
        return []
    if chunk_size < 64:
        raise ValueError("chunk_size must be at least 64 tokens")

    # Whisper text is often one long paragraph, and '. ' misses ?! and newlines.
    units = [u.strip() for u in re.split(r"(?<=[.!?])\s+|\n+", text) if u.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    max_chars = chunk_size * 4

    for unit in units:
        # A malformed/noisy run can be longer than the target; retain all of it
        # rather than dropping it, in pieces that will fit an LLM context.
        pieces = [unit[i:i + max_chars] for i in range(0, len(unit), max_chars)] or [unit]
        for piece in pieces:
            piece_size = count_tokens(piece)
            if current and current_size + piece_size > chunk_size:
                chunks.append(" ".join(current))
                current, current_size = [], 0
            current.append(piece)
            current_size += piece_size
    if current:
        chunks.append(" ".join(current))
    return chunks


def _generate(prompt: str, model: str, *, num_predict: int) -> str:
    import requests

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": OLLAMA_CONTEXT_TOKENS, "num_predict": num_predict, "temperature": 0.1},
        },
        timeout=600,
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()


def process_chunk(chunk_text: str, chunk_num: int, total_chunks: int, model: str = DEFAULT_MODEL) -> str:
    """Extract faithful chronological notes from one source chunk (map phase)."""
    prompt = f"""You are extracting evidence for a company meeting record. The speech may mix English, Tagalog, and Bikol.

Return concise but detailed chronological notes from ONLY this transcript portion. Translate to clear English. Preserve names, numbers, decisions, assignments, questions, demonstrations, disagreements, anecdotes, and uncertainty. Do not invent facts, speakers, or outcomes. Do not write an executive summary, title, or closing commentary.

Use this Markdown shape:
### Segment {chunk_num}
- **Topic:** ...
- Discussion, decision, question, or action with concrete details.

This is segment {chunk_num} of {total_chunks}; do not refer to unavailable segments.

TRANSCRIPT:
{chunk_text}
"""
    try:
        return _generate(prompt, model, num_predict=900)
    except Exception as exc:
        return f"### Segment {chunk_num}\n- *Could not analyze this segment: {exc}*"


def _batches(items: Iterable[str], token_limit: int) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    size = 0
    for item in items:
        item_size = count_tokens(item)
        if current and size + item_size > token_limit:
            batches.append(current)
            current, size = [], 0
        current.append(item)
        size += item_size
    if current:
        batches.append(current)
    return batches


def _reduce_notes(notes: list[str], model: str) -> list[str]:
    """Compress notes hierarchically, preserving their original order."""
    from whisper_local.core.progress import is_cancelled, log_message, update_chunk

    round_number = 1
    while len(notes) > 1 or count_tokens(notes[0]) > REDUCE_SIZE_TOKENS:
        batches = _batches(notes, REDUCE_SIZE_TOKENS)
        if len(batches) == len(notes) and all(len(batch) == 1 for batch in batches):
            # A model response itself exceeded the budget. Trim each item enough
            # to combine adjacent items on the next pass. This is a last-resort
            # guard against an infinite loop if Ollama ignores num_predict.
            target_chars = max(1, REDUCE_SIZE_TOKENS * 2)
            notes = [note[:target_chars] for note in notes]
            if len(notes) == 1:
                break
            round_number += 1
            continue
        log_message(f"LLM consolidation pass {round_number}: {len(batches)} batch(es)")
        reduced: list[str] = []
        for index, batch in enumerate(batches, 1):
            if is_cancelled():
                return []
            prompt = f"""Consolidate the ordered meeting notes below into detailed chronological evidence for a later writer.
Keep all concrete names, figures, decisions, owners, deadlines, questions, examples, and unresolved items. Remove only duplication and filler. Do not invent facts and do not produce a title or executive summary.

NOTES:\n{'\n\n'.join(batch)}
"""
            try:
                reduced.append(_generate(prompt, model, num_predict=1000))
            except Exception as exc:
                reduced.append("\n\n".join(batch) + f"\n\n*Consolidation unavailable: {exc}*")
            update_chunk()
        notes = reduced
        round_number += 1
    return notes


def _write_document(evidence: str, model: str) -> str:
    """Produce one document from bounded evidence, rather than joining mini-docs."""
    prompt = f"""You are a professional meeting documentarian. Write a faithful complete meeting record from the ordered evidence below. The source may have been English, Tagalog, and Bikol; write clear professional English.

Never invent details or claim a decision/action owner/date that the evidence does not support. Preserve the chronological sequence, specific names, numbers, questions, demonstrations, anecdotes, disagreements, and uncertainty.

Output Markdown only, exactly in this broad structure:
# A fitting session title
## Executive Summary
4-8 factual sentences.
---
## Full Meeting Record
### 1. A chronological section title
Detailed paragraphs and bullets where useful.

Use as many numbered sections as the evidence warrants. Do not mention chunks, prompts, or the extraction process.

ORDERED EVIDENCE:
{evidence}
"""
    return _generate(prompt, model, num_predict=1800)


def process_full_transcript(transcript: str, model: str = DEFAULT_MODEL) -> str:
    """Map source chunks, reduce their evidence, then write one coherent document."""
    from whisper_local.core.progress import is_cancelled, log_message, update_chunk

    chunks = split_into_chunks(transcript)
    if not chunks:
        return ""
    if len(chunks) == 1 and len(re.findall(r"[.!?]", transcript)) < 5:
        return "**Status:** Short audio test or greeting detected. No substantive meeting content to document."

    log_message(f"LLM analysis: extracting evidence from {len(chunks)} chunk(s)")
    evidence: list[str] = []
    for number, chunk in enumerate(chunks, 1):
        if is_cancelled():
            return ""
        log_message(f"LLM extracting chunk {number}/{len(chunks)}...")
        evidence.append(process_chunk(chunk, number, len(chunks), model))
        update_chunk()

    evidence = _reduce_notes(evidence, model)
    if not evidence or is_cancelled():
        return ""
    log_message("LLM writing the final meeting record...")
    try:
        return _write_document("\n\n".join(evidence), model)
    except Exception as exc:
        return "\n\n".join(evidence) + f"\n\n*Final document generation unavailable: {exc}*"

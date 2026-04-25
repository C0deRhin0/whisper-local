import requests
import json

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"

def _check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def summarize(transcript: str, model: str = DEFAULT_MODEL) -> str:
    """Summarize a transcript (single-pass, for short audio)."""
    if not _check_ollama():
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )
    
    url = f"{OLLAMA_URL}/api/generate"
    prompt = _build_extraction_prompt(transcript)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=300)
    response.raise_for_status()
    
    data = response.json()
    return data.get("response", "")


def summarize_with_context(new_transcript: str, prior_summary: str = "", model: str = DEFAULT_MODEL) -> str:
    """
    Summarize incrementally, building on prior context.
    
    Used for chunked transcription - each chunk builds on previous summary.
    
    Args:
        new_transcript: Transcript from the current audio chunk
        prior_summary: Summary from all previous chunks (or "" for first)
        model: Ollama model to use
    
    Returns:
        Updated unified summary
    """
    if not _check_ollama():
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )
    
    url = f"{OLLAMA_URL}/api/generate"
    
    if prior_summary:
        prompt = f"""You are an executive meeting analyst analyzing a meeting in segments.

The meeting is being analyzed progressively. Here's the summary so far:
---
{prior_summary}
---

Now analyze this new segment of the meeting:

Transcript segment:
{new_transcript}

IMPORTANT: Respond in ENGLISH even if the meeting was in Tagalog or mixed English/Tagalog.

Update the summary to incorporate this new segment. Keep the same structure:
- Executive Summary (3 sentences in English)
- Key Decisions (with names, in English)
- Action Items (with owners and deadlines, in English)
- Open Questions

Rules:
- Do NOT invent names
- Do NOT repeat information already in the summary
- Focus on NEW information from this segment
- Respond in English

Updated summary:"""
    else:
        # First chunk - use standard extraction
        prompt = _build_extraction_prompt(new_transcript)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=300)
    response.raise_for_status()
    
    data = response.json()
    return data.get("response", "")


def _build_extraction_prompt(transcript: str) -> str:
    """Build the standard extraction prompt."""
    return f"""You are an executive meeting analyst.

Analyze the meeting transcript and extract the key information.

IMPORTANT: The meeting may be in English, Tagalog, or mixed. Respond in ENGLISH regardless of the input language.

Extract:

1. Executive Summary (exactly 3 sentences in English)
2. Key Decisions
   - Decision (in English)
   - Decision-maker (name)
3. Action Items
   - Task (in English)
   - Owner (must be named)
   - Deadline (infer if needed)
4. Open Questions

Rules:
- Do NOT invent names
- Do NOT use vague terms like "team"
- Respond in English even if input is Tagalog/mixed
- Be concise and structured

Transcript:
{transcript}"""

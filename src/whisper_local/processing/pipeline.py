import os
import pathlib
import tempfile
import shutil
import concurrent.futures
import json

# Internal imports
from whisper_local.audio.transcriber import _get_file_hash, format_transcript, transcribe
from whisper_local.audio.utils import save_summary, split_audio
from whisper_local.core.progress import complete, is_cancelled, log_message, reset_progress, set_phase, update_chunk
from whisper_local.paths import CACHE_DIR, PROJECT_ROOT, SUMMARIES_DIR
from whisper_local.processing.chunk_and_merge import process_full_transcript

# Settings
CHUNK_DURATION_SECONDS = 180 
BASE_DIR = PROJECT_ROOT
DEFAULT_LLM_MODEL = "llama3.2:3b"  # Lightweight 3b model for faster inference

def _log(msg: str):
    print(f"[Pipeline] {msg}")


def _safe_filename(name: str | None, fallback: str) -> str:
    """Return a filesystem-safe filename segment with no path traversal."""

    base_name = os.path.basename(name or "")
    safe_name = "".join(c for c in base_name if c.isalnum() or c in (".", "-", "_"))
    safe_name = safe_name.strip(" ._")

    if not safe_name or safe_name in {".", ".."}:
        return fallback

    return safe_name[:160]


def _safe_cache_folder(name: str | None, fallback: str) -> pathlib.Path:
    cache_root = CACHE_DIR
    safe_name = _safe_filename(name, fallback)
    cache_folder = cache_root / safe_name
    cache_root_resolved = cache_root.resolve()
    cache_folder_resolved = cache_folder.resolve()

    if cache_root_resolved != cache_folder_resolved and cache_root_resolved not in cache_folder_resolved.parents:
        raise ValueError("Resolved cache path escapes cache directory")

    return cache_folder


def _legacy_cache_name_candidates(original_filename: str | None) -> list[str]:
    """Return pre-rearchitecture folder names for backwards-compatible cache reads."""

    if not original_filename:
        return []

    base_name = os.path.basename(original_filename)
    safe_name = _safe_filename(base_name, "")

    candidates = []
    for candidate in [
        # Old pipeline kept alnum, dot, dash, and underscore from the original
        # filename, dropping spaces and other punctuation.
        "".join(c for c in base_name if c.isalnum() or c in (".", "-", "_")),
        safe_name,
        # Some existing operator caches were created from display names where
        # spaces became underscores and were then omitted.
        safe_name.replace("_", ""),
    ]:
        candidate = candidate.strip(" ._")
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _find_legacy_cache_folder(original_filename: str | None) -> pathlib.Path | None:
    """Find an existing legacy cache folder that can satisfy a cache read."""

    for candidate in _legacy_cache_name_candidates(original_filename):
        folder = _safe_cache_folder(candidate, "")
        if (folder / "result.json").exists() and (folder / "transcript.txt").exists():
            return folder

    return None

def run_pipeline(audio_path: str = None, duration: int = 60, chunk_duration: int = CHUNK_DURATION_SECONDS, transcript_format: str = 'raw', original_filename: str = None, mode: str = 'full') -> dict:
    """Run the transcription and analysis pipeline.
    
    Args:
        audio_path: Path to audio file, or None to record from microphone
        duration: Recording duration in seconds
        chunk_duration: Audio chunk duration for splitting
        transcript_format: 'raw' or 'formatted'
        original_filename: Original filename for caching
        mode: 'full' (transcribe + summarize) or 'transcribe_only'
    
    Returns:
        dict with 'transcript', 'summary', etc.
    """
    temp_file = False

    try:
        if not audio_path:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                audio_path = temp_audio.name
            from whisper_local.audio.recorder import record_audio
            _log(f"Recording audio for {duration} seconds...")
            record_audio(audio_path, duration=duration)
            temp_file = True

        return _process_audio(audio_path, chunk_duration, transcript_format, original_filename, mode)

    finally:
        if temp_file and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


def _process_audio(audio_path: str, chunk_duration: int = CHUNK_DURATION_SECONDS, transcript_format: str = 'raw', original_filename: str = None, mode: str = 'full') -> dict:
    """Process audio file with accurate progress and full-file caching.
    
    Args:
        mode: 'full' (transcribe + summarize) or 'transcribe_only'
    """
    # Use a content hash in every cache key so two uploads with the same name do
    # not accidentally share transcripts/summaries.
    file_hash = _get_file_hash(audio_path)
    legacy_cache = False
    legacy_cache_folder = None
    if original_filename:
        safe_original_name = _safe_filename(original_filename, "audio")[:80]
        cache_folder = _safe_cache_folder(f"{safe_original_name}_{file_hash}", file_hash)
        legacy_cache_folder = _find_legacy_cache_folder(original_filename)
    else:
        cache_folder = _safe_cache_folder(file_hash, file_hash)

    if legacy_cache_folder and not ((cache_folder / "result.json").exists() and (cache_folder / "transcript.txt").exists()):
        cache_folder = legacy_cache_folder
        legacy_cache = True

    cache_folder.mkdir(parents=True, exist_ok=True)
    cache_path = cache_folder / "result.json"
    transcript_path = cache_folder / "transcript.txt"
    formatted_transcript_path = cache_folder / "transcript_formatted.txt"

    # Check if FULL cache exists (json + all transcript files)
    cache_valid = cache_path.exists() and transcript_path.exists()
    if cache_valid:
        cache_kind = "legacy cache" if legacy_cache else "cache"
        _log(f"CACHE HIT: Loading existing results from {cache_folder.name}/")
        log_message(f"{cache_kind.capitalize()} hit — loading cached results from {cache_folder.name}/")
        with open(cache_path, 'r') as f:
            cached_data = json.load(f)

        cached_hash = cached_data.get('source_hash')
        if cached_hash is not None and cached_hash != file_hash:
            cache_valid = False
        elif cached_hash is None and not legacy_cache:
            cache_valid = False
        elif transcript_format == 'formatted' and not formatted_transcript_path.exists():
            cache_valid = False
        else:
            if transcript_format == 'formatted':
                return {
                    "transcript": cached_data.get('formatted_transcript', ''),
                    "raw_transcript": cached_data.get('raw_transcript', ''),
                    "summary": cached_data.get('summary', ''),
                    "output_file": cached_data.get('output_file', '')
                }
            else:
                return {
                    "transcript": cached_data.get('raw_transcript', ''),
                    "raw_transcript": cached_data.get('raw_transcript', ''),
                    "summary": cached_data.get('summary', ''),
                    "output_file": cached_data.get('output_file', '')
                }
    if not cache_valid:
        _log(f"Cache miss in {cache_folder.name}/ — will re-process.")
        log_message(f"Processing audio: {cache_folder.name}")
        for stale in [cache_path, transcript_path, formatted_transcript_path]:
            if stale.exists():
                stale.unlink()

    if is_cancelled():
        return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}

    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    
    try:
        # Phase 2: Split audio
        set_phase(2)
        _log("Splitting audio into chunks...")
        log_message("Splitting audio into chunks for transcription...")
        chunk_paths = split_audio(audio_path, chunk_dir, chunk_duration)
        
        total_chunks = len(chunk_paths)
        _log(f"Audio split into {total_chunks} chunks")
        log_message(f"Audio split into {total_chunks} chunk(s)")
        set_phase(3, total_chunks)

        if is_cancelled():
            return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}
        
        # Phase 3: Parallel Transcription
        transcripts_dict = {}
        initial_context = "Meeting regarding AI analytics, Firebase, SQL, Cloud Functions, and Digital Ocean in English, Tagalog, and Bicolano dialect."

        def transcribe_task(idx, path, prompt):
            """Transcribe a single chunk with error handling."""
            try:
                _log(f"Transcribing chunk {idx + 1}/{total_chunks}...")
                # Pass cache_folder so per-chunk cache goes inside audio folder
                text = transcribe(path, prompt=prompt, cache_dir=str(cache_folder))
                return idx, text, None
            except Exception as e:
                _log(f"Error transcribing chunk {idx + 1}: {e}")
                return idx, "", str(e)

        log_message(f"Starting transcription ({total_chunks} chunk(s))...")

        errors = []
        # NOTE: Must NOT use `with ThreadPoolExecutor(...)` — the context manager
        # calls shutdown(wait=True) on exit, which BLOCKS until ALL submitted
        # futures complete (including queued ones). When cancelling, we need to
        # shutdown with wait=False,cancel_futures=True so remaining queued chunks
        # are NOT executed, letting the pipeline stop immediately.
        import sys as _sys
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            futures = [executor.submit(transcribe_task, i, path, initial_context)
                       for i, path in enumerate(chunk_paths)]

            completed = 0
            for future in concurrent.futures.as_completed(futures):
                if is_cancelled():
                    # Shutdown without waiting — cancel all queued futures
                    if _sys.version_info >= (3, 9):
                        executor.shutdown(wait=False, cancel_futures=True)
                    else:
                        executor.shutdown(wait=False)
                    return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}
                idx, text, error = future.result()
                if error:
                    errors.append(f"Chunk {idx + 1}: {error}")
                    _log(f"Warning: Chunk {idx + 1} failed: {error}")
                transcripts_dict[idx] = text
                completed += 1
                _log(f"Chunk {completed}/{total_chunks} complete.")
                update_chunk()
        finally:
            executor.shutdown(wait=False)

        if errors:
            _log(f"Warning: {len(errors)} chunks had errors: {errors}")
            log_message(f"Transcription completed with {len(errors)} warning(s)")
        else:
            log_message(f"All {total_chunks} chunks transcribed successfully!")
            _log(f"All {total_chunks} chunks transcribed successfully!")
        
        transcripts = [transcripts_dict[i] for i in range(len(chunk_paths)) if transcripts_dict.get(i)]
        full_transcript = " ".join(transcripts)
        
        if is_cancelled():
            return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}

        if not full_transcript.strip():
            raise ValueError("No speech detected in the audio.")

        if is_cancelled():
            return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}

        # Phase 4: LLM Analysis (skip for transcribe-only mode)
        if mode == 'transcribe_only':
            summary = ''
            log_message("Transcribe-only mode — skipping LLM analysis.")
            _log("Transcribe-only mode — skipping analysis.")
        else:
            set_phase(4, 1)
            log_message("Analyzing transcript with LLM...")
            _log(f"Generating meeting record from {len(full_transcript)} chars of transcript...")
            summary = process_full_transcript(full_transcript, model=DEFAULT_LLM_MODEL)
            if is_cancelled():
                return {"transcript": "", "raw_transcript": "", "summary": "", "output_file": ""}
            _log("Analysis complete!")
            log_message("LLM analysis complete.")
            update_chunk()

        # Phase 5: Save & Cache Result (ALL files inside the audio folder)
        set_phase(5)
        log_message("Saving results to cache folder...")
        _log("Saving results...")

        original_file_name = _safe_filename(
            original_filename if original_filename else (os.path.basename(audio_path) if audio_path else "audio"),
            "audio",
        )

        formatted_transcript = ""
        if transcript_format == 'formatted':
            formatted_transcript = format_transcript(
                full_transcript,
                file_name=original_file_name,
                language=None,
                audio_path=audio_path
            )

        # Save summary markdown INSIDE the cache folder
        summary_filename = f"summary_{original_file_name}.md" if original_file_name else "summary.md"
        summary_path = cache_folder / summary_filename
        safe_summary = f"```\n{summary}\n```" if summary else "(No summary generated)"
        safe_transcript = f"```\n{full_transcript}\n```" if full_transcript else "(No transcript)"
        summary_content = f"""## Executive Summary
{safe_summary}

## Raw Transcript
{safe_transcript}
"""
        with open(summary_path, 'w') as f:
            f.write(summary_content)
        output_file = str(summary_path)

        _log(f"Summary saved to {summary_path}")

        # Also save to summaries/ for backward compatibility
        try:
            save_summary(full_transcript, summary, str(SUMMARIES_DIR))
        except Exception:
            pass

        # Store BOTH formats in cache
        cached_data = {
            "source_hash": file_hash,
            "raw_transcript": full_transcript,
            "formatted_transcript": formatted_transcript,
            "summary": summary,
            "output_file": output_file
        }

        with open(cache_path, 'w') as f:
            json.dump(cached_data, f)
        with open(transcript_path, 'w') as f:
            f.write(full_transcript)
        if transcript_format == 'formatted':
            with open(formatted_transcript_path, 'w') as f:
                f.write(formatted_transcript)

        _log(f"Cached all files in {cache_folder.name}/")

        if transcript_format == 'formatted':
            result = {
                "transcript": formatted_transcript,
                "raw_transcript": full_transcript,
                "summary": summary,
                "output_file": output_file
            }
        else:
            result = {
                "transcript": full_transcript,
                "raw_transcript": full_transcript,
                "summary": summary,
                "output_file": output_file
            }
            
        log_message("Done!")
        complete()
        return result

    finally:
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)


def _get_text_hash(text: str) -> str:
    """Generate a cache-friendly hash from text content."""
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def process_text(text: str, transcript_format: str = 'raw') -> dict:
    """Process text directly through the LLM pipeline (skip transcription).
    
    Takes raw transcript text and generates a meeting document via LLM.
    Uses the same chunk-and-merge logic as the audio pipeline.
    
    Text analysis is cached by content hash in data/cache/text_<hash>/.
    
    Args:
        text: Raw transcript text to analyze
        transcript_format: 'raw' or 'formatted' (formatted not applicable for text)
    
    Returns:
        dict with 'transcript' (input text), 'summary' (LLM output), etc.
    """
    _log(f"Processing text ({len(text)} chars)...")
    log_message("Analyzing transcript text...")

    if is_cancelled():
        return {"transcript": text, "raw_transcript": text, "summary": "", "output_file": ""}

    # Check text cache
    text_hash = _get_text_hash(text)
    cache_folder = CACHE_DIR / f"text_{text_hash}"
    cache_folder.mkdir(parents=True, exist_ok=True)
    cache_path = cache_folder / "result.json"

    if cache_path.exists():
        _log(f"TEXT CACHE HIT: Loading from text_{text_hash}/")
        with open(cache_path, 'r') as f:
            cached = json.load(f)
        if cached.get('source_hash') == text_hash and cached.get('source_length') == len(text):
            log_message("Text cache hit — loading cached analysis.")
            complete()
            return cached

        _log("Text cache hash mismatch — reprocessing.")

    log_message("No text cache — running LLM analysis...")

    if is_cancelled():
        return {"transcript": text, "raw_transcript": text, "summary": "", "output_file": ""}

    # Phase 4: LLM Analysis (skip transcription phases 1-3)
    set_phase(4, 1)
    log_message("Analyzing transcript...")
    summary = process_full_transcript(text, model=DEFAULT_LLM_MODEL)
    if is_cancelled():
        return {"transcript": text, "raw_transcript": text, "summary": "", "output_file": ""}
    _log("Analysis complete!")
    log_message("Analysis complete.")
    update_chunk()

    # Phase 5: Save & cache
    set_phase(5)
    log_message("Saving text analysis results...")

    # Save summary inside text cache folder
    summary_filename = "summary.txt"
    summary_path = cache_folder / summary_filename
    with open(summary_path, 'w') as f:
        f.write(summary)

    # Also save to summaries/ for backward compatibility
    output_file = str(summary_path)
    try:
        save_summary(text, summary, str(SUMMARIES_DIR))
    except Exception:
        pass

    _log(f"Saved to {output_file}")

    result = {
        "source_hash": text_hash,
        "source_length": len(text),
        "transcript": text,
        "raw_transcript": text,
        "summary": summary,
        "output_file": output_file
    }

    # Cache the result
    with open(cache_path, 'w') as f:
        json.dump(result, f)
    _log(f"Cached to text_{text_hash}/")

    log_message("Done!")
    complete()
    return result

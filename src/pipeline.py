import os
import tempfile
import shutil
import pathlib
import concurrent.futures
import json

# Internal imports
from audio_utils import split_audio, save_summary
from transcriber import transcribe, _get_file_hash
from chunk_and_merge import process_full_transcript
from progress import set_phase, update_chunk, complete, reset_progress, log_message

# Settings
CHUNK_DURATION_SECONDS = 180 
BASE_DIR = pathlib.Path(__file__).parent.parent
DEFAULT_LLM_MODEL = "llama3.2:3b"  # Lightweight 3b model for faster inference

def _log(msg: str):
    print(f"[Pipeline] {msg}")

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
            audio_path = os.path.join(tempfile.gettempdir(), "temp_recording.wav")
            from recorder import record_audio
            start_record = True
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
    # Use original filename for foldered cache, or fallback to hash-based name
    if original_filename:
        # Sanitize filename for folder name
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in ('.', '-', '_'))
        cache_folder = BASE_DIR / "data" / "cache" / safe_name
    else:
        file_hash = _get_file_hash(audio_path)
        cache_folder = BASE_DIR / "data" / "cache" / file_hash

    cache_folder.mkdir(parents=True, exist_ok=True)
    cache_path = cache_folder / "result.json"

    # Check if cache exists
    if cache_path.exists():
        _log(f"CACHE HIT: Loading existing results from {cache_folder.name}/")
        with open(cache_path, 'r') as f:
            cached_data = json.load(f)

        # Return the requested format
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

    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    
    try:
        # Phase 2: Split audio
        set_phase(2)
        _log("Splitting audio into chunks...")
        chunk_paths = split_audio(audio_path, chunk_dir, chunk_duration)
        
        total_chunks = len(chunk_paths)
        set_phase(3, total_chunks)
        
        # Phase 3: Parallel Transcription
        transcripts_dict = {}
        initial_context = "Meeting regarding AI analytics, Firebase, SQL, Cloud Functions, and Digital Ocean in English, Tagalog, and Bicolano dialect."

        def transcribe_task(idx, path, prompt):
            """Transcribe a single chunk with error handling."""
            try:
                _log(f"Transcribing chunk {idx + 1}/{total_chunks}...")
                text = transcribe(path, prompt=prompt)
                return idx, text, None
            except Exception as e:
                _log(f"Error transcribing chunk {idx + 1}: {e}")
                return idx, "", str(e)

        _log(f"Starting parallel transcription with 2 workers...")
        log_message(f"Starting transcription ({total_chunks} chunks)...")

        errors = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Submit all tasks
            futures = [executor.submit(transcribe_task, i, path, initial_context)
                       for i, path in enumerate(chunk_paths)]

            completed = 0
            for future in concurrent.futures.as_completed(futures):
                idx, text, error = future.result()
                if error:
                    errors.append(f"Chunk {idx + 1}: {error}")
                    _log(f"Warning: Chunk {idx + 1} failed: {error}")
                transcripts_dict[idx] = text
                completed += 1
                # Log immediately for UI visibility
                msg = f"Chunk {completed}/{total_chunks} complete."
                _log(msg)
                log_message(msg)
                update_chunk() # Progress in Phase 3

        if errors:
            _log(f"Warning: {len(errors)} chunks had errors: {errors}")
        else:
            _log(f"All {total_chunks} chunks transcribed successfully!")
        
        # Reconstruct transcript in order
        transcripts = [transcripts_dict[i] for i in range(len(chunk_paths)) if transcripts_dict.get(i)]
        full_transcript = " ".join(transcripts)
        
        if not full_transcript.strip():
            raise ValueError("No speech detected in the audio.")

        # Phase 4: LLM Analysis (skip for transcribe-only mode)
        if mode == 'transcribe_only':
            summary = ''
            log_message("Transcribe-only mode — skipping LLM analysis.")
            _log("Transcribe-only mode — skipping analysis.")
        else:
            set_phase(4, 1)
            log_message("Analyzing transcript (chunked)...")
            _log(f"Generating meeting record from {len(full_transcript)} chars of transcript...")
            summary = process_full_transcript(full_transcript, model=DEFAULT_LLM_MODEL)
            _log("Analysis complete!")
            log_message("Analysis complete.")
            update_chunk()

        # Phase 5: Save & Cache Result
        set_phase(5)
        _log("Saving results...")

        # Get the original file name for formatting
        original_file_name = original_filename if original_filename else (os.path.basename(audio_path) if audio_path else "audio")

        # Always generate both raw and formatted transcripts
        from transcriber import format_transcript
        formatted_transcript = format_transcript(
            full_transcript,
            file_name=original_file_name,
            language=None,
            audio_path=audio_path
        )

        output_file = save_summary(full_transcript, summary, "summaries")

        # Store BOTH formats in cache
        cached_data = {
            "raw_transcript": full_transcript,
            "formatted_transcript": formatted_transcript,
            "summary": summary,
            "output_file": output_file
        }

        # Save to foldered cache
        with open(cache_path, 'w') as f:
            json.dump(cached_data, f)

        # Return the requested format
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
            
        complete()
        return result

    finally:
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)


def process_text(text: str, transcript_format: str = 'raw') -> dict:
    """Process text directly through the LLM pipeline (skip transcription).
    
    Takes raw transcript text and generates a meeting document via LLM.
    Uses the same chunk-and-merge logic as the audio pipeline.
    
    Args:
        text: Raw transcript text to analyze
        transcript_format: 'raw' or 'formatted' (formatted not applicable for text)
    
    Returns:
        dict with 'transcript' (input text), 'summary' (LLM output), etc.
    """
    _log(f"Processing text ({len(text)} chars)...")
    log_message("Processing text...")

    # Phase 4: LLM Analysis (skip transcription phases 1-3)
    set_phase(4, 1)
    log_message("Analyzing transcript...")
    summary = process_full_transcript(text, model=DEFAULT_LLM_MODEL)
    _log("Analysis complete!")
    log_message("Analysis complete.")
    update_chunk()

    # Phase 5: Save
    set_phase(5)
    output_file = save_summary(text, summary, "summaries")
    _log(f"Saved to {output_file}")

    complete()
    return {
        "transcript": text,
        "raw_transcript": text,
        "summary": summary,
        "output_file": output_file
    }

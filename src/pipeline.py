import os
import tempfile
import shutil
import pathlib
import concurrent.futures
import json

# Internal imports
from audio_utils import split_audio, save_summary
from transcriber import transcribe, _get_file_hash
from llm import summarize
from progress import set_phase, update_chunk, complete, reset_progress, log_message

# Settings
CHUNK_DURATION_SECONDS = 180 
BASE_DIR = pathlib.Path(__file__).parent.parent

def _log(msg: str):
    print(f"[Pipeline] {msg}")

def run_pipeline(audio_path: str = None, duration: int = 60, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """Run the transcription and analysis pipeline."""
    temp_file = False
    
    try:
        if not audio_path:
            audio_path = os.path.join(tempfile.gettempdir(), "temp_recording.wav")
            from recorder import record_audio
            start_record = True
            _log(f"Recording audio for {duration} seconds...")
            record_audio(audio_path, duration=duration)
            temp_file = True
        
        return _process_audio(audio_path, chunk_duration)
        
    finally:
        if temp_file and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


def _process_audio(audio_path: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """Process audio file with accurate progress and full-file caching."""
    # 1. Check Full File Cache
    file_hash = _get_file_hash(audio_path)
    cache_dir = BASE_DIR / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"full_{file_hash}.json"
    
    if cache_path.exists():
        _log("CACHE HIT: Loading existing results for this file.")
        with open(cache_path, 'r') as f:
            cached_data = json.load(f)
            complete() # Mark 100% in UI
            return cached_data

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
            # Log starting state to UI immediately
            log_message(f"Transcribing Chunk {idx+1}...")
            text = transcribe(path, prompt=prompt)
            return idx, text

        _log(f"Starting parallel transcription with 2 workers...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Submit all tasks
            futures = [executor.submit(transcribe_task, i, path, initial_context) 
                       for i, path in enumerate(chunk_paths)]
            
            for future in concurrent.futures.as_completed(futures):
                idx, text = future.result()
                transcripts_dict[idx] = text
                log_message(f"Chunk {idx+1} complete.")
                update_chunk() # Progress in Phase 3
        
        # Reconstruct transcript in order
        transcripts = [transcripts_dict[i] for i in range(len(chunk_paths)) if transcripts_dict.get(i)]
        full_transcript = " ".join(transcripts)
        
        if not full_transcript.strip():
            raise ValueError("No speech detected in the audio.")

        # Phase 4: Batch Summary
        set_phase(4, 1)
        _log("Generating batch summary...")
        summary = summarize(full_transcript)
        update_chunk()

        # Phase 5: Save & Cache Result
        set_phase(5)
        _log("Saving results...")
        output_file = save_summary(full_transcript, summary, "summaries")
        
        result = {
            "transcript": full_transcript,
            "summary": summary,
            "output_file": output_file
        }
        
        # Save to cache for next time
        with open(cache_path, 'w') as f:
            json.dump(result, f)
            
        complete()
        return result

    finally:
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)
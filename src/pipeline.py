from src.recorder import record_audio
from src.transcriber import transcribe
from src.llm import summarize, summarize_with_context
from src.audio_utils import split_audio, cleanup_chunks, get_audio_duration, CHUNK_DURATION_SECONDS, _ensure_wav
from src.storage import save_summary
from src.progress import start, set_phase, update_chunk, complete, get, reset, is_active
import tempfile
import os
import shutil
import sys

def _log(msg):
    """Print with immediate flush."""
    print(msg, flush=True)
    sys.stdout.flush()

def run_pipeline(audio_path: str = None, duration: int = 30, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """
    Run the full meeting transcription pipeline with accurate progress tracking.
    """
    # Check if already in progress (don't reset if webui started it)
    if is_active():
        # Continue from current state - just process the audio
        return _process_audio(audio_path, chunk_duration)
    
    # Not in progress - start fresh (CLI mode)
    reset()
    temp_file = False
    
    try:
        if not audio_path:
            audio_path = os.path.join(tempfile.gettempdir(), "temp_recording.wav")
            start(1, 'record')
            _log(f"Recording audio for {duration} seconds...")
            record_audio(audio_path, duration=duration)
            temp_file = True
        
        return _process_audio(audio_path, chunk_duration)
        
    finally:
        if temp_file and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


def _process_audio(audio_path: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """Process audio file with accurate progress tracking."""
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    
    try:
        # Phase 2: Split audio
        set_phase(2)
        _log("Splitting audio into chunks...")
        chunk_paths = split_audio(audio_path, chunk_dir, chunk_duration)
        
        total_chunks = len(chunk_paths)
        
        # Update chunks (only if not already tracking)
        if total_chunks > 1:
            set_phase(3, total_chunks)
        
        if total_chunks <= 1:
            # Single chunk - simple path
            set_phase(3, 1)
            _log("Transcribing audio...")
            transcript = transcribe(chunk_paths[0])
            
            if not transcript.strip():
                raise ValueError("Transcript is empty.")
            
            set_phase(4, 1)
            _log("Summarizing transcript...")
            summary = summarize(transcript)
            
            set_phase(5)
            _log("Saving results...")
            output_file = save_summary(transcript, summary, "summaries")
            
            complete()
            
            return {
                "transcript": transcript,
                "summary": summary,
                "output_file": output_file
            }
        
        # Multiple chunks - process on-the-fly
        set_phase(3, total_chunks)
        _log(f"Processing {total_chunks} chunks...")
        
        cumulative_summary = ""
        full_transcript = ""
        
        for i, chunk_path in enumerate(chunk_paths):
            chunk_num = i + 1
            
            # Transcribe this chunk
            _log(f"[{chunk_num}/{total_chunks}] Transcribing...")
            transcript = transcribe(chunk_path)
            
            if not transcript.strip():
                _log(f"[{chunk_num}] Empty, skipping...")
                update_chunk()
                continue
            
            full_transcript += transcript + " "
            update_chunk()
            
            # Summarize with context
            set_phase(4, total_chunks)
            _log(f"[{chunk_num}] Analyzing...")
            cumulative_summary = summarize_with_context(
                new_transcript=transcript,
                prior_summary=cumulative_summary
            )
            update_chunk()
        
        if not full_transcript.strip():
            raise ValueError("No valid transcripts from any chunk.")
        
        set_phase(5)
        _log("Saving results...")
        output_file = save_summary(full_transcript, cumulative_summary, "summaries")
        
        complete()
        
        return {
            "transcript": full_transcript,
            "summary": cumulative_summary,
            "output_file": output_file
        }
    finally:
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)
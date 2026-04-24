from src.recorder import record_audio
from src.transcriber import transcribe
from src.llm import summarize, summarize_with_context
from src.audio_utils import split_audio, cleanup_chunks, get_audio_duration, CHUNK_DURATION_SECONDS, _ensure_wav
from src.storage import save_summary
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
    Run the full meeting transcription pipeline.
    
    Processing starts IMMEDIATELY without pre-calculating duration.
    For long files, processes chunk-by-chunk on-the-fly.
    
    Args:
        audio_path: Path to audio file. If None, records from microphone.
        duration: Recording duration in seconds (default 30s). Only used if audio_path is None.
        chunk_duration: Audio chunk duration in seconds for long files (default 300s = 5min)
    
    Returns:
        dict with transcript, summary, and output_file
    """
    temp_file = False
    
    try:
        if not audio_path:
            audio_path = os.path.join(tempfile.gettempdir(), "temp_recording.wav")
            _log(f"Recording audio for {duration} seconds...")
            record_audio(audio_path, duration=duration)
            temp_file = True
        
        # Process IMMEDIATELY - don't wait for duration calculation
        _log("Processing audio...")
        return _process_audio(audio_path, chunk_duration)
        
    finally:
        if temp_file and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


def _process_audio(audio_path: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """
    Process audio in chunks without pre-calculating total duration.
    
    Workflow:
    1. Convert to WAV if needed
    2. Split into chunks (just enough to start)
    3. Process first chunk immediately
    4. If more audio, process next chunk
    5. Continue until end
    """
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    
    try:
        # Split audio - this creates chunk files
        chunk_paths = split_audio(audio_path, chunk_dir, chunk_duration)
        
        if len(chunk_paths) <= 1:
            # Single chunk - simple path
            _log(f"Transcribing {audio_path}...")
            transcript = transcribe(chunk_paths[0])
            
            if not transcript.strip():
                raise ValueError("Transcript is empty.")
            
            _log("Summarizing transcript...")
            summary = summarize(transcript)
            
            _log("Saving results...")
            output_file = save_summary(transcript, summary, "summaries")
            
            return {
                "transcript": transcript,
                "summary": summary,
                "output_file": output_file
            }
        
        # Multiple chunks - process on-the-fly
        total_chunks = len(chunk_paths)
        _log(f"Processing {total_chunks} chunks (streaming)...\n")
        
        cumulative_summary = ""
        full_transcript = ""
        
        for i, chunk_path in enumerate(chunk_paths):
            chunk_num = i + 1
            _log(f"[{chunk_num}/{total_chunks}] Transcribing...")
            transcript = transcribe(chunk_path)
            
            if not transcript.strip():
                _log(f"[{chunk_num}] Empty, skipping...\n")
                continue
            
            full_transcript += transcript + " "
            
            _log(f"[{chunk_num}] Analyzing (building summary)...\n")
            cumulative_summary = summarize_with_context(
                new_transcript=transcript,
                prior_summary=cumulative_summary
            )
        
        if not full_transcript.strip():
            raise ValueError("No valid transcripts from any chunk.")
        
        print("Saving results...")
        output_file = save_summary(full_transcript, cumulative_summary, "summaries")
        
        return {
            "transcript": full_transcript,
            "summary": cumulative_summary,
            "output_file": output_file
        }
    finally:
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)
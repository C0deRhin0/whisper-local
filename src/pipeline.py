from src.recorder import record_audio
from src.transcriber import transcribe
from src.llm import summarize, summarize_with_context
from src.audio_utils import split_audio, cleanup_chunks, get_audio_duration, CHUNK_DURATION_SECONDS
from src.storage import save_summary
import tempfile
import os
import shutil

def run_pipeline(audio_path: str = None, duration: int = 30, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """
    Run the full meeting transcription pipeline.
    
    Args:
        audio_path: Path to audio file. If None, records from microphone.
        duration: Recording duration in seconds (default 30s). Only used if audio_path is None.
        chunk_duration: Audio chunk duration in seconds for long files (default 300s = 5min)
    
    Returns:
        dict with transcript, summary, and output_file
    """
    temp_file = False
    chunk_dir = None
    
    try:
        if not audio_path:
            audio_path = os.path.join(tempfile.gettempdir(), "temp_recording.wav")
            print(f"Recording audio for {duration} seconds...")
            record_audio(audio_path, duration=duration)
            temp_file = True
        
        # Check if we need chunked processing
        file_duration = get_audio_duration(audio_path)
        
        if file_duration > chunk_duration:
            print(f"Long audio detected ({file_duration:.0f}s > {chunk_duration}s). Using chunked processing...")
            return _run_chunked_pipeline(audio_path, chunk_duration)
        
        # Short file - single pass
        print(f"Transcribing {audio_path}...")
        transcript = transcribe(audio_path)
        
        if not transcript.strip():
            raise ValueError("Transcript is empty.")
        
        print("Summarizing transcript...")
        summary = summarize(transcript)
        
        print("Saving results...")
        output_file = save_summary(transcript, summary, "summaries")
        
        return {
            "transcript": transcript,
            "summary": summary,
            "output_file": output_file
        }
    finally:
        if temp_file and audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if chunk_dir and os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)


def _run_chunked_pipeline(audio_path: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> dict:
    """
    Process long audio file in chunks with incremental summarization.
    """
    chunk_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
    
    try:
        # Split audio into chunks
        print(f"Splitting audio into {chunk_duration}s chunks...")
        chunk_paths = split_audio(audio_path, chunk_dir, chunk_duration)
        print(f"Created {len(chunk_paths)} audio chunks")
        
        # Process each chunk
        cumulative_summary = ""
        full_transcript = ""
        
        for i, chunk_path in enumerate(chunk_paths):
            print(f"\n[Chunk {i+1}/{len(chunk_paths)}] Transcribing...")
            transcript = transcribe(chunk_path)
            
            if not transcript.strip():
                print(f"[Chunk {i+1}] Empty transcript, skipping...")
                continue
            
            full_transcript += transcript + " "
            
            print(f"[Chunk {i+1}] Summarizing (building on prior context)...")
            cumulative_summary = summarize_with_context(
                new_transcript=transcript,
                prior_summary=cumulative_summary
            )
        
        if not full_transcript.strip():
            raise ValueError("No valid transcripts from any chunk.")
        
        # Save results
        print("\nSaving results...")
        output_file = save_summary(full_transcript, cumulative_summary, "summaries")
        
        return {
            "transcript": full_transcript,
            "summary": cumulative_summary,
            "output_file": output_file
        }
    finally:
        # Cleanup chunks
        if os.path.exists(chunk_dir):
            shutil.rmtree(chunk_dir)

"""
Audio utilities for chunking long audio files.
"""
import wave
import os
from pathlib import Path

CHUNK_DURATION_SECONDS = 300  # 5 minutes per chunk
CHUNK_OVERLAP_SECONDS = 0  # No overlap between chunks


def get_audio_duration(audio_path: str) -> float:
    """Get duration of WAV file in seconds."""
    with wave.open(str(audio_path), 'rb') as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / rate


def split_audio(audio_path: str, output_dir: str, chunk_duration: int = CHUNK_DURATION_SECONDS) -> list[str]:
    """
    Split audio file into chunks of chunk_duration seconds each.
    
    Returns list of paths to chunk files.
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with wave.open(str(audio_path), 'rb') as wf:
        # Audio properties
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        total_frames = wf.getnframes()
        chunk_size = int(frame_rate * chunk_duration)
        
        # Calculate number of chunks
        num_chunks = (total_frames + chunk_size - 1) // chunk_size
        
        chunk_paths = []
        
        for i in range(num_chunks):
            # Read chunk frames
            wf.seek(i * chunk_size)
            frames = wf.readframes(chunk_size)
            
            if len(frames) == 0:
                break
            
            # Write chunk file
            chunk_name = f"chunk_{i:04d}.wav"
            chunk_path = output_dir / chunk_name
            
            with wave.open(str(chunk_path), 'wb') as chunk_wf:
                chunk_wf.setnchannels(n_channels)
                chunk_wf.setsampwidth(sample_width)
                chunk_wf.setframerate(frame_rate)
                chunk_wf.writeframes(frames)
            
            chunk_paths.append(str(chunk_path))
        
        return chunk_paths


def cleanup_chunks(chunk_paths: list[str]) -> None:
    """Delete chunk files after processing."""
    for path in chunk_paths:
        try:
            os.remove(path)
        except OSError:
            pass
"""
Audio utilities for smart chunking long audio files.

Features:
- Silence/pause detection for natural boundaries
- Configurable overlap to avoid cutting mid-sentence
- Adaptive chunking for dialectal/noisy audio
"""
import wave
import os
import subprocess
import shutil
import tempfile
import re
from pathlib import Path

# Default settings
CHUNK_DURATION_SECONDS = 180  # 3 minutes - good for mixed language
CHUNK_OVERLAP_SECONDS = 0    # 0 seconds overlap - we use prompting instead to avoid duplication
SILENCE_THRESHOLD_DB = -40    # Silence threshold in dB
MIN_SILENCE_DURATION = 0.5    # Min silence (sec) to be considered a breakpoint
MAX_CHUNK_DURATION = 600     # Max chunk (10 min) for safety

# Formats that need conversion
NEED_CONVERSION = {'.mp3', '.m4a', '.aac', '.ogg', '.aiff', '.aif', '.wma', '.flac'}


def _ensure_wav(audio_path: str) -> str:
    """Convert audio to WAV if needed. Returns path to WAV file."""
    path = Path(audio_path)
    ext = path.suffix.lower()
    
    if ext == '.wav':
        return str(path.absolute())
    
    if not shutil.which('ffmpeg'):
        raise RuntimeError("ffmpeg required. Install: brew install ffmpeg")
    
    wav_path = tempfile.mktemp(suffix='.wav')
    result = subprocess.run([
        'ffmpeg', '-y', '-i', str(path.absolute()),
        '-ar', '16000', '-ac', '1', wav_path
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Conversion failed: {result.stderr}")
    
    return wav_path


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds."""
    audio_path = Path(audio_path)
    ext = audio_path.suffix.lower()
    
    if ext == '.wav':
        with wave.open(str(audio_path), 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / rate
    else:
        if not shutil.which('ffmpeg'):
            raise RuntimeError("ffmpeg required. Install: brew install ffmpeg")
        
        result = subprocess.run(
            ['ffmpeg', '-i', str(audio_path.absolute())],
            capture_output=True, text=True
        )
        
        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', result.stderr)
        if match:
            h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
            return h * 3600 + m * 60 + s
        
        file_size = audio_path.stat().st_size
        return (file_size / 128 / 1000) * 8


def _find_silence_points(wav_path: str, silence_thresh: float = -40, min_silence: float = 0.5) -> list:
    """
    Find natural breakpoints using silence detection.
    
    Returns list of timestamps (seconds) where chunk boundaries should be.
    """
    if not shutil.which('ffmpeg'):
        return []  # Fallback to fixed chunks
    
    # Use ffmpeg's silencedetect to find pauses
    result = subprocess.run([
        'ffmpeg', '-i', wav_path,
        '-af', f'silencedetect=n={silence_thresh}dB:d={min_silence}',
        '-f', 'null', '-'
    ], capture_output=True, text=True)
    
    silence_points = []
    
    # Parse silence end points (these are good chunk boundaries)
    for match in re.finditer(r'silence_end: ([0-9.]+)', result.stderr):
        silence_points.append(float(match.group(1)))
    
    return silence_points


def split_audio_smart(
    audio_path: str,
    output_dir: str,
    chunk_duration: int = CHUNK_DURATION_SECONDS,
    overlap: int = CHUNK_OVERLAP_SECONDS,
    max_chunk: int = MAX_CHUNK_DURATION
) -> list[str]:
    """
    Split audio using smart boundaries (silence detection + overlap).
    
    Args:
        audio_path: Input audio file
        output_dir: Directory for chunk files
        chunk_duration: Target chunk duration (sec). For mixed language, 2-3 min recommended.
        overlap: Overlap between chunks (sec). 15-30 sec recommended for dialect.
        max_chunk: Maximum chunk duration (sec) for safety
    
    Returns:
        List of chunk file paths
    """
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Convert to WAV
    wav_path = _ensure_wav(str(audio_path))
    
    # Get audio properties
    with wave.open(wav_path, 'rb') as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        total_frames = wf.getnframes()
        total_duration = total_frames / frame_rate
    
    # Find silence points for natural boundaries
    silence_points = _find_silence_points(wav_path, SILENCE_THRESHOLD_DB, MIN_SILENCE_DURATION)
    
    # Build chunk boundaries
    boundaries = [0]  # Start at 0
    
    if silence_points:
        # Use silence points as soft boundaries
        # Add silence points that are reasonably spaced (not too close, not too far)
        target_chunk_frames = int(frame_rate * chunk_duration)
        overlap_frames = int(frame_rate * overlap)
        
        current_pos = 0
        while current_pos < total_frames:
            # Find next silence point that's at least 1/3 chunk away from current
            min_boundary = current_pos + int(frame_rate * chunk_duration * 0.3)
            max_boundary = min(current_pos + target_chunk_frames + overlap_frames, total_frames)
            
            next_silence = None
            for sp in silence_points:
                sp_frames = int(sp * frame_rate)
                if min_boundary <= sp_frames <= max_boundary:
                    next_silence = sp_frames
                    break
            
            if next_silence:
                # Round to nearest 0.1 sec for cleaner boundaries
                boundary = round(next_silence / frame_rate, 1)
                if boundary not in boundaries and boundary < total_duration:
                    boundaries.append(boundary)
                current_pos = next_silence + overlap_frames
            else:
                # No silence point found, use fixed interval
                current_pos += target_chunk_frames
                boundary = round(current_pos / frame_rate, 1)
                if boundary < total_duration:
                    boundaries.append(boundary)
    
    else:
        # No silence detected, use fixed intervals with overlap
        chunk_samples = int(frame_rate * chunk_duration)
        overlap_samples = int(frame_rate * overlap)
        stride = chunk_samples - overlap_samples
        
        pos = 0
        while pos < total_frames:
            boundary = round(pos / frame_rate, 1)
            if boundary < total_duration:
                boundaries.append(boundary)
            pos += stride
    
    # Add end point
    boundaries.append(round(total_duration, 1))
    
    # Remove duplicates and sort
    boundaries = sorted(set(boundaries))
    
    # Ensure max chunk duration
    final_boundaries = [boundaries[0]]
    for i in range(1, len(boundaries)):
        if boundaries[i] - final_boundaries[-1] > max_chunk:
            # Insert intermediate point
            mid = final_boundaries[-1] + max_chunk
            final_boundaries.append(round(mid, 1))
        final_boundaries.append(boundaries[i])
    
    # Create chunk files
    chunk_paths = []
    
    for i in range(len(final_boundaries) - 1):
        start_time = final_boundaries[i]
        end_time = final_boundaries[i + 1]
        
        start_frame = int(start_time * frame_rate)
        end_frame = int(end_time * frame_rate)
        
        if end_frame <= start_frame:
            continue
        
        chunk_name = f"chunk_{i:04d}.wav"
        chunk_path = output_dir / chunk_name
        
        # Use ffmpeg for precise extraction (handles overlaps better)
        result = subprocess.run([
            'ffmpeg', '-y', '-i', wav_path,
            '-ss', str(start_time),
            '-to', str(end_time),
            '-ar', '16000', '-ac', '1',
            str(chunk_path)
        ], capture_output=True, text=True)
        
        if result.returncode == 0 and chunk_path.exists():
            chunk_paths.append(str(chunk_path))
    
    return chunk_paths


def split_audio(
    audio_path: str,
    output_dir: str,
    chunk_duration: int = CHUNK_DURATION_SECONDS
) -> list[str]:
    """
    Split audio using smart boundaries with overlap.
    
    For mixed language (Tagalog + dialects + English), recommended settings:
    - chunk_duration: 180 (3 minutes) - balances context and accuracy
    - overlap: 15 (15 seconds) - prevents cutting mid-sentence
    
    Returns list of chunk file paths.
    """
    return split_audio_smart(
        audio_path,
        output_dir,
        chunk_duration=chunk_duration,
        overlap=CHUNK_OVERLAP_SECONDS,
        max_chunk=MAX_CHUNK_DURATION
    )


def cleanup_chunks(chunk_paths: list[str]) -> None:
    """Delete chunk files after processing."""
    for path in chunk_paths:
        try:
            os.remove(path)
        except OSError:
            pass

def save_summary(transcript: str, summary: str, output_dir: str = "summaries") -> str:
    """Save transcript and summary to a markdown file."""
    import time
    from pathlib import Path
    
    # Ensure directory exists
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"meeting_notes_{timestamp}.md"
    file_path = out_path / filename
    
    # Format content
    content = f"# Meeting Notes - {time.strftime('%B %d, %Y')}\n\n{summary}\n\n---\n# Full Transcript\n{transcript}"
    
    with open(file_path, "w", encoding='utf-8') as f:
        f.write(content)
        
    return str(file_path)
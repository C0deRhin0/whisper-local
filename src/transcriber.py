import subprocess
import os
import re
import pathlib
import tempfile
import shutil

# Base directory for whisper.cpp
BASE_DIR = pathlib.Path(__file__).parent.parent

# Formats that need conversion to WAV
NEED_CONVERSION = {'.mp3', '.m4a', '.aac', '.ogg', '.aiff', '.aif', '.wma', '.flac'}

# Repetitive patterns to filter - tuples of (pattern, replacement)
BASIC_PATTERNS = [
    (r'\b(so what I\'m talking about is|that\'s what I\'m talking about)\b', ''),
    (r'\b(um|uh|ah|er)\b', ''),
]


def _clean_transcript(text: str) -> str:
    """Clean transcript - remove repetitions and filler from rugged recordings."""
    # Remove duplicate lines (same line repeated 3+ times)
    lines = text.split('\n')
    cleaned = []
    prev_line = None
    repeat_count = 0
    
    for line in lines:
        line = line.strip()
        if line == prev_line:
            repeat_count += 1
            if repeat_count <= 2:  # Keep max 2 duplicates
                cleaned.append(line)
        else:
            repeat_count = 0
            cleaned.append(line)
        prev_line = line
    
    text = ' '.join(cleaned)
    
    # Apply basic regex patterns
    import re
    for pattern, replacement in BASIC_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Clean up extra spaces
    text = re.sub(r'\s{2,}', ' ', text)
    
    return text.strip()


def _convert_to_wav(audio_path: str) -> str:
    """Convert audio to WAV format using ffmpeg.
    
    Returns path to temporary WAV file (caller must delete).
    """
    path = pathlib.Path(audio_path)
    ext = path.suffix.lower()
    
    if ext == '.wav':
        return str(path.absolute())  # Return absolute path
    
    # Check ffmpeg available
    if not shutil.which('ffmpeg'):
        raise RuntimeError(
            "ffmpeg required for this format. Install: brew install ffmpeg"
        )
    
    # Create temp file in temp dir
    wav_path = tempfile.mktemp(suffix='.wav')
    
    # Convert: 16kHz mono
    result = subprocess.run([
        'ffmpeg', '-y', '-i', str(path.absolute()),
        '-ar', '16000', '-ac', '1', wav_path
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Conversion failed: {result.stderr}")
    
    return wav_path


def _is_supported_format(audio_path: str) -> bool:
    """Check if audio format is supported natively or with conversion."""
    ext = pathlib.Path(audio_path).suffix.lower()
    return ext in NEED_CONVERSION or ext == '.wav'


def transcribe(audio_path: str) -> str:
    """Transcribe audio file to text."""
    path = pathlib.Path(audio_path).absolute()
    
    # Check if format supported
    if not _is_supported_format(str(path)):
        raise ValueError(
            f"Unsupported format: {path.suffix}. "
            f"Supported: .wav, .mp3, .m4a, .aac, .ogg, .aiff, .flac"
        )
    
    # Check whisper.cpp binaries exist
    model_path = BASE_DIR / "whisper.cpp" / "models" / "ggml-small.bin"
    whisper_bin = BASE_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli"
    
    if not whisper_bin.exists():
        raise FileNotFoundError(f"whisper-cli binary not found at {whisper_bin}. Compile it first.")
    
    if not model_path.exists():
        raise FileNotFoundError(f"whisper model not found at {model_path}. Download it first.")
    
    # Convert to WAV if needed
    temp_wav = None
    try:
        if path.suffix.lower() != '.wav':
            temp_wav = _convert_to_wav(str(path))
            audio_path = temp_wav
        else:
            audio_path = str(path)
        
        result = subprocess.run(
            [str(whisper_bin), "-m", str(model_path), "-f", audio_path, "-l", "tl"],
            capture_output=True, text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Transcription failed: {result.stderr}")
        
        # whisper-cli outputs transcript to stdout, logs to stderr
        output = result.stdout
        
        # Extract text from timestamp format: [00:00:00.000 --> 00:00:10.500]   transcript
        lines = output.split('\n')
        transcript_lines = []
        for line in lines:
            if line.startswith('[') and '-->' in line:
                text = line.split(']', 1)[1].strip()
                if text:
                    transcript_lines.append(text)
        
        transcript = ' '.join(transcript_lines)
        
        # Strip any remaining timestamps
        transcript = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}\]', '', transcript)
        
        # Clean transcript - remove repetitions/filler from rugged recordings
        transcript = _clean_transcript(transcript.strip())
        
        return transcript
    
    finally:
        # Clean up temp WAV
        if temp_wav and os.path.exists(temp_wav):
            os.remove(temp_wav)

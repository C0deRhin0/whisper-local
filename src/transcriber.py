import subprocess
import os
import re
import pathlib
import tempfile
import shutil
import hashlib

# Base directory
BASE_DIR = pathlib.Path(__file__).parent.parent
CACHE_DIR = BASE_DIR / "data" / "cache"

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_file_hash(file_path: str) -> str:
    """Generate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _clean_transcript(text: str) -> str:
    """Clean transcript - remove duplicates and redundant timestamps."""
    lines = text.split('\n')
    cleaned = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # whisper.cpp output format is [00:00:00.000 --> 00:00:05.000] text
        line = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*', '', line)
        
        if not line.strip():
            continue
            
        cleaned.append(line.strip())
    
    deduped = []
    prev = None
    for line in cleaned:
        if line != prev:
            deduped.append(line)
        prev = line
        
    return ' '.join(deduped)

def transcribe(audio_path: str, prompt: str = "") -> str:
    """Transcribe audio file using whisper.cpp CLI with caching and format conversion."""
    
    # 1. Check Cache
    file_hash = _get_file_hash(audio_path)
    # We include prompt in cache key to ensure context changes trigger re-transcription if needed
    # (Or we can just hash the audio if the prompt is always the same)
    cache_file = CACHE_DIR / f"{file_hash}.txt"
    
    if cache_file.exists():
        return cache_file.read_text(encoding='utf-8')

    # 2. Prepare Paths
    model_path = BASE_DIR / "whisper.cpp" / "models" / "ggml-medium.bin"
    whisper_bin = BASE_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli"
    
    if not whisper_bin.exists():
        raise FileNotFoundError(f"whisper-cli binary not found at {whisper_bin}")

    # 3. Audio Conversion (Ensure 16kHz WAV for whisper.cpp)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
        converted_wav = tmp_wav.name
        
    try:
        # Convert to 16kHz mono WAV using ffmpeg
        conv_cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            converted_wav
        ]
        subprocess.run(conv_cmd, capture_output=True, check=True)

        # 4. Transcription
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp_out:
            output_base = tmp_out.name[:-4]
            tmp_txt_name = tmp_out.name

        try:
            # Use half the cores if we expect parallel runs to avoid contention
            threads = max(1, os.cpu_count() // 2)
            
            cmd = [
                str(whisper_bin),
                "-m", str(model_path),
                "-f", converted_wav,
                "-l", "tl",
                "-t", str(threads),
                "-fa",
                "-otxt",
                "-of", output_base
            ]
            
            if prompt:
                cmd.extend(["--prompt", prompt])

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Whisper failed: {result.stderr}")

            output_file = output_base + ".txt"
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    raw_text = f.read()
                os.remove(output_file)
                
                final_text = _clean_transcript(raw_text)
                
                # 5. Save to Cache
                cache_file.write_text(final_text, encoding='utf-8')
                return final_text
            
            return ""

        finally:
            if os.path.exists(tmp_txt_name):
                os.remove(tmp_txt_name)
    
    finally:
        if os.path.exists(converted_wav):
            os.remove(converted_wav)

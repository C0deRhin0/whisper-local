import subprocess
import os
import re
import pathlib

# Base directory for whisper.cpp
BASE_DIR = pathlib.Path(__file__).parent.parent

def transcribe(audio_path: str) -> str:
    model_path = BASE_DIR / "whisper.cpp" / "models" / "ggml-base.bin"
    whisper_bin = BASE_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli"
    
    if not whisper_bin.exists():
        raise FileNotFoundError(f"whisper-cli binary not found at {whisper_bin}. Compile it first.")
    
    if not model_path.exists():
        raise FileNotFoundError(f"whisper model not found at {model_path}. Download it first.")

    result = subprocess.run([str(whisper_bin), "-m", str(model_path), "-f", audio_path], capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"Transcription failed: {result.stderr}")
    
    # whisper-cli outputs transcript to stdout, logs to stderr
    output = result.stdout
    
    # Extract text from timestamp format: [00:00:00.000 --> 00:00:10.500]   transcript
    lines = output.split('\n')
    transcript_lines = []
    for line in lines:
        # Look for lines starting with [ and containing -->
        if line.startswith('[') and '-->' in line:
            # Extract text after timestamp closing ]
            text = line.split(']', 1)[1].strip()
            if text:
                transcript_lines.append(text)
    
    transcript = ' '.join(transcript_lines)
    
    # Strip any remaining timestamps
    transcript = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}\]', '', transcript)
    return transcript.strip()

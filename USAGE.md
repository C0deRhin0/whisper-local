# Meeting Analyzer — Usage Guide

## Prerequisites

1. **Ollama running**

```bash
brew services start ollama
ollama pull llama3.2:3b
```

2. **Python venv activated**

```bash
cd /path/to/meeting-analyzer
source .venv/bin/activate
```

## Basic Usage

### Process a pre-recorded audio file

```bash
python src/app.py path/to/meeting.wav
```

### Record from microphone

```bash
python src/app.py
```

### Record with custom duration

```bash
python src/app.py --duration 60
```

## Long Audio Files (60+ minutes)

The pipeline automatically detects long files (>5 min) and uses **chunked processing**:

- Audio is split into 5-minute segments
- Each chunk is transcribed sequentially
- LLM synthesizes incrementally — each iteration builds on prior context
- Final output = unified summary as if processed as a whole

### Custom chunk duration

```python
from src.pipeline import run_pipeline
run_pipeline(audio_path="long_meeting.wav", chunk_duration=600)  # 10 min chunks
```

## Output

Each run creates `summaries/meeting_YYYYMMDD_HHMMSS.md`:

```markdown
## Executive Summary
[Summary]

## Raw Transcript
[Full transcript]
```

## Python API

```python
from src.pipeline import run_pipeline

# From file
result = run_pipeline("meeting.wav")
print(result["summary"])

# From microphone
result = run_pipeline(duration=60)

# Long file with custom chunks
result = run_pipeline("long.wav", chunk_duration=600)
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `Ollama not running` | `brew services start ollama` |
| `whisper-cli not found` | Build: `cd whisper.cpp && make -j` |
| `ModuleNotFoundError` | `source .venv/bin/activate` |
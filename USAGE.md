# Whisper Local — Usage Guide

## Prerequisites

1. **Ollama setup**
```bash
ollama pull llama3.2:3b
```

2. **Environment**
```bash
source .venv/bin/activate
```

## Modes of Operation

### 1. Web UI (Recommended)
The Web UI is the primary way to use Whisper Local. It provides real-time feedback and a two-column layout for immediate analysis.
- **Start**: `./serverctl start`
- **Features**: 
    - Parallel transcription for 2x speed.
    - Automatic SHA-256 caching (instant re-analysis).
    - Auto-reset input panel after completion.
    - Professional Markdown (.md) summary downloads.

### 2. CLI Mode
For quick terminal-based processing:
```bash
# Process a file
python src/app.py path/to/meeting.m4a

# Record from microphone (default 60s)
python src/app.py

# Record with custom duration
python src/app.py --duration 120
```

## High-Performance Pipeline

The system automatically optimizes for long audio files:
- **Parallelism**: Uses 2 concurrent workers for transcription on Apple Silicon.
- **Smart Chunking**: Splits audio into 3-minute segments at natural silence points.
- **Full-File Caching**: Analysis results are stored in `data/cache/`. If the same file is uploaded again, results appear instantly without re-processing.

## Output Formats

### Manual Downloads (Web UI)
- **Executive Summary**: Downloaded as `.md` (Markdown) for easy integration into Notion, Obsidian, or Slack.
- **Transcript**: Downloaded as `.txt` for raw reference.

### Automated Files
Each run automatically saves a timestamped record to the `summaries/` directory:
- `meeting_notes_YYYYMMDD_HHMMSS.md`

## Prompting & Accuracy
- **Dialect Handling**: Automatically translates Tagalog and Bikol terms into professional English.
- **No-Naming Policy**: The LLM focuses on technical roles and decisions rather than individual names to eliminate hallucinations.
- **Minimal Fallback**: For recordings under 3 sentences, the system provides a simple "Status" update instead of a full template.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `source .venv/bin/activate` or check for direct imports. |
| `pyaudio` errors | Ensure `brew install portaudio` is completed before `pip install`. |
| `whisper-cli` missing | Run `./serverctl build` to compile the engine for Metal. |
| LLM Hallucinations | Ensure you are using the `llama3.2:3b` model for best results. |
# Whisper Local — Usage Guide

## Prerequisites

### 1. Activate Virtual Environment

```bash
source .venv/bin/activate
```

### 2. Setup Ollama

```bash
ollama pull llama3.2:3b
```

### 3. Ensure Dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) PDF Support

If PDF export fails, install pango:

```bash
brew install pango
```

## Modes of Operation

### 1. Web UI (Recommended)

The Web UI is the primary way to use Whisper Local. It provides real-time feedback and a two-column layout for immediate analysis.

- **Start**: `./serverctl start`
- **Features**: 
    - Parallel transcription for 2x speed.
    - Automatic SHA-256 caching (instant re-analysis).
    - Auto-reset input panel after completion.
    - **Meeting Record** downloads as `.md` or `.pdf`

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

### Web UI Downloads

After processing, you have two download options:

| Button | Format | Description |
|--------|--------|-------------|
| **PDF** | `.pdf` | Styled document with page numbers (via WeasyPrint) |
| **Download** | `.md` | Markdown for Notion, Obsidian, Slack |

### Automated Files

Each run automatically saves a timestamped record to the `summaries/` directory:

- `meeting_notes_YYYYMMDD_HHMMSS.md`

## Meeting Record Format

The LLM generates a **full meeting reconstruction** (not a summary):

### Structure

```markdown
# [Session Title]

## Executive Summary
[4-8 sentences covering purpose, key themes, decisions, outcome]

---

## Full Meeting Record

### 1. [Section Title]
[Who spoke, what they said, decisions, questions, reactions]

### 2. [Section Title]
[Content]

... continues chronologically ...
```

### Key Characteristics

- Captures every **name**, **number**, **quote**, **anecdote**
- Preserves the full story (not compressed)
- Uses chronological numbered sections
- Handles code-switched speech (English + Tagalog + Bicolano)
- Includes all personal stories and demonstrations
- Page numbers in PDF footer

### Edge Cases

- **Short clips** (< 5 sentences): Outputs `**Status:** Short audio test or greeting detected.`
- **Inaudible segments**: Notes `[Inaudible or unclear segment — transcription artifact]`

## PDF Export

The PDF button generates a styled document with:

- A4 page size with 25mm/30mm margins
- Latin Modern Roman typography
- Page numbers in footer
- Proper heading hierarchies
- Blockquotes styled with left border
- Horizontal rules between major sections

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `source .venv/bin/activate` |
| `pyaudio` errors | Ensure `brew install portaudio` before `pip install` |
| `whisper-cli` missing | Run `./serverctl build` |
| PDF generation fails | Run `brew install pango` |
| LLM errors | Ensure `ollama pull llama3.2:3b` completed |
| Port 8080 in use | Run `./serverctl stop` then `./serverctl start` |

## Quick Reference

```bash
# Start server
./serverctl start

# Stop server
./serverctl stop

# Check status
./serverctl status

# Rebuild whisper.cpp
./serverctl build

# Access from other devices only when explicitly enabled:
# WHISPER_LOCAL_HOST=0.0.0.0 WHISPER_LOCAL_AUTH_TOKEN=choose-a-strong-token ./serverctl start
# Then use the IP shown in server output (e.g., http://192.168.x.x:8080)
# Enter WHISPER_LOCAL_AUTH_TOKEN in the browser prompt when asked.
```

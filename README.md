# Whisper Local

> Transcribe meeting audio and extract structured insights — entirely offline.

A local transcription + LLM system for analyzing meeting recordings. 100% offline, privacy-first.

## Features

- **100% local** — No cloud APIs, no data leaves your machine
- **Long audio support** — Handles 60+ minute meetings with chunked processing
- **Structured output** — Extracts decisions, action items, owners
- **Privacy-first** — Your meeting data stays on your machine
- **Multiple formats** — Works with WAV, MP3, M4A, AAC, OGG, AIFF, FLAC
- **Smart chunking** — 3-min chunks with 15s overlap for context
- **Real-time progress** — Accurate progress bar + timeline
- **Audio cleanup** — Filters repetitions from rugged recordings
- **Web UI** — Beautiful browser interface for non-tech users
- **Server control** — Easy start/stop script manages everything

## Requirements

- macOS (Linux support coming)
- [Homebrew](https://brew.sh)
- 4GB+ RAM recommended
- **ffmpeg**: `brew install ffmpeg`

## Quick Start

```bash
# Clone and enter project
git clone https://github.com/yourusername/whisper-local.git
cd whisper-local

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start everything (Ollama + Web UI)
./serverctl start
```

Then open **http://localhost:8080** in your browser.

## Usage

### Via Web UI (Recommended)

```bash
./serverctl start    # Start
./serverctl stop     # Stop
./serverctl status  # Check status
```

1. Open http://localhost:8080
2. Upload audio file OR set duration and record
3. Watch real-time progress bar and timeline
4. View summary and transcript
5. Download as text files

### Via CLI

```bash
# Process a file
python src/app.py path/to/meeting.wav

# Or record from microphone
python src/app.py
```

## Progress Tracking

The web UI shows accurate progress:

| Phase | Progress | Description |
|-------|----------|-------------|
| Preparing | 1-5% | File upload/recording |
| Preparing audio | 5-15% | Audio splitting |
| Transcribing | 15-55% | Speech-to-text (per chunk) |
| Analyzing | 55-90% | LLM summarization (per chunk) |
| Saving | 90-98% | Saving results |
| Complete | 100% | Done |

Timeline shows each step with timestamps and status dots.

## Project Structure

```
whisper-local/
├── serverctl           # Server control script
├── run.sh             # Simple launcher
├── src/
│   ├── app.py        # CLI entry point
│   ├── webui.py      # Web UI (Flask)
│   ├── pipeline.py    # Main processing pipeline
│   ├── progress.py   # Progress tracking
│   ├── recorder.py   # Microphone recording
│   ├── transcriber.py # whisper.cpp wrapper
│   ├── llm.py       # Ollama integration
│   ├── audio_utils.py # Smart audio chunking
│   └── storage.py    # Output persistence
├── summaries/         # Generated meeting notes
├── whisper.cpp/      # Local transcription engine
└── requirements.txt   # Python dependencies
```

## How It Works

```
Audio Input → whisper.cpp → Transcript → Ollama → Structured Summary
  (WAV)        (local STT)     (text)      (local LLM)     (markdown)
```

1. **Audio** — Load a file or record from microphone
2. **Split** — Divides into 3-min chunks with 15s overlap
3. **Transcribe** — whisper-cli converts speech to text locally
4. **Analyze** — Ollama extracts decisions, action items (cumulatively for chunks)
5. **Save** — Results saved to `summaries/meeting_<timestamp>.md`

## Web UI Features

- Beautiful midnight blue gradient background
- Glassmorphism cards with blur effect
- **Accurate progress bar that fills 0-100%**
- **Real-time timeline with timestamps**
- **Chunk tracking** (1/3, 2/3, etc.)
- Progress phase name displayed
- Download Summary/Transcript as text files
- Auto-cleanup of temp files
- Page refresh resets state
- Access from phone/tablet on same network

## Server Control

The `serverctl` script manages everything:

```bash
./serverctl start   # Start Ollama + Web UI together
./serverctl stop    # Stop both when done
./serverctl restart
./serverctl status
```

**Features:**
- Starts Ollama automatically (if not running as system service)
- Starts Web UI on http://localhost:8080
- Shows network URL for phone access
- Stops both when done (only if started by script)

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--duration` | 30s | Recording duration (mic) |
| `chunk_duration` | 180s (3min) | Audio chunk size |

## Output Format

Each run produces:

```markdown
## Executive Summary
[3-sentence summary of the meeting]

## Decisions
- [Key decision] — [Decision-maker]

## Action Items
- [Task] — @[Owner] — [Deadline]

## Open Questions
- [Unresolved issue]
```

## Setup (First Time)

```bash
# 1. Setup whisper.cpp (if not already)
git clone https://github.com/ggerganov/whisper.cpp.git whisper.cpp
cd whisper.cpp
make -j
bash ./models/download-ggml-model.sh small  # ~465MB

# 2. Setup Ollama (if not already)
brew install ollama
ollama pull llama3.2:3b

# 3. Return to project
cd ..

# 4. Start the server
./serverctl start
```

## Models

### Whisper (Transcription)

| Model | Size | Use |
|-------|------|-----|
| tiny | ~39MB | Testing |
| **small** | ~465MB | Recommended |
| medium | ~1.5GB | Best accuracy |

### Ollama (LLM)

```bash
# Default (good for summaries)
ollama pull llama3.2:3b

# More capable
ollama pull llama3.2:7b
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Can't access localhost:8080 | `./serverctl start` |
| Ollama not running | `./serverctl start` |
| whisper-cli not found | Build in whisper.cpp: `make -j` |
| portaudio not found | `brew install portaudio` |
| Module errors | Ensure venv: `source .venv/bin/activate` |

## Tech Stack

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) — Local speech-to-text
- [Ollama](https://ollama.ai) — Local LLM runtime
- PyAudio — Microphone input
- Flask — Web interface

## License

MIT — See [LICENSE](LICENSE)

## Acknowledgments

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov
- [Ollama](https://ollama.ai) for local LLM inference
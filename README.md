# Whisper Local

> Transcribe meeting audio and extract structured meeting records — entirely offline.

A local transcription + LLM system for analyzing meeting recordings. 100% offline, privacy-first, and optimized for Apple Silicon (M1/M2/M3).

## Features

- **100% Local** — No cloud APIs, no data leaves your machine.
- **Parallel Pipeline** — 2x concurrent transcription workers for massive speedups on multi-core machines.
- **Foldered Caching** — Cache organized by filename for easy management and deletion.
- **Dual Transcript Format** — Toggle between raw (plain text) and formatted (speaker labels) output.
- **Metal Accelerated** — Native GPU support via `whisper.cpp` for lightning-fast STT on Mac.
- **Full Meeting Records** — No summarization; reconstructs the complete meeting with all names, quotes, anecdotes.
- **Minimal Content Fallback** — Smart detection prevents corporate summaries for short test clips or greetings.
- **Long Audio Support** — Handles 60+ minute meetings with chunked processing.
- **Smart Chunking** — Natural silence detection ensures sentences aren't cut mid-stream.
- **Real-time Progress** — Accurate progress bar + timeline with Chunk-by-Chunk tracking.
- **Enhanced Transcript Format** — Structured output with speaker labels, auto-detected language, and professional formatting.
- **Speaker Diarization** — Neural network-based speaker detection using pyannote.audio for accurate speaker identification.
- **Web UI** — Premium browser interface with a two-panel layout and dark theme.
- **PDF Export** — Download meeting records as styled PDFs with page numbers.
- **Server Control** — Easy start/stop script manages everything.

## Requirements

### System Dependencies (macOS)

```bash
# Install Homebrew dependencies
brew install ffmpeg
brew install ollama
brew install portaudio
```

### Python Dependencies

The project uses a virtual environment. Install dependencies with:

```bash
# Create virtual environment (first time)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# For PDF export (recommended)
# No additional pip needed - already in requirements.txt
# But may need system-level pango (rarely required on macOS)
brew install pango
```

### Ollama Model

```bash
ollama pull llama3.2:3b
```

### Low-memory tuning and language context

On macOS, transcription uses one Whisper worker by default so an 8 GB unified-memory machine does not load two copies of the model at once. To opt into parallel workers on a higher-memory Mac, set `WHISPER_TRANSCRIBE_WORKERS=2` before starting the server.

The default recognition language is Tagalog (`tl`), which is helpful for Tagalog/Bikol/English recordings. You can change it with `WHISPER_LANGUAGE` and provide organization-specific vocabulary without hard-coding it into every meeting using `WHISPER_INITIAL_PROMPT`.

Long meeting records use a local map–reduce pipeline. The defaults use a 4,096-token Ollama context; advanced users can tune `WHISPER_OLLAMA_CONTEXT_TOKENS`, `WHISPER_SUMMARY_CHUNK_TOKENS`, and `WHISPER_SUMMARY_REDUCE_TOKENS` if their installed model and memory permit it.

### HuggingFace Token (for Speaker Diarization)

Speaker diarization requires a HuggingFace token for the pyannote models:

1. Create an account at [huggingface.co](https://huggingface.co)
2. Go to Settings → Access Tokens → Create new token
3. Copy `.env.example` to `.env` and set `HF_TOKEN`, or export `HF_TOKEN` in your shell.

On first run, the app will use `HF_TOKEN` to download the diarization model.

## Quick Start

```bash
# Clone and enter project
git clone https://github.com/C0deRhin0/whisper-local.git
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
2. Upload audio file OR set duration and record.
3. Watch real-time progress as parallel workers process chunks.
4. View meeting record (Markdown) and transcript (Text).
5. Download results using the **Download** or **PDF** buttons.

### Via CLI

```bash
# Process a file
python src/app.py path/to/meeting.wav

# Or record from microphone
python src/app.py
```

## Download Options

### Web UI Downloads

After processing, you can download the meeting record in two formats:

| Button | Format | Description |
|--------|--------|-------------|
| **PDF** | `.pdf` | Styled document with page numbers, proper margins, Latin Modern typography |
| **Download** | `.md` | Markdown file for Notion, Obsidian, or further editing |

### Automated Files

Each run automatically saves a timestamped record to the `summaries/` directory:
- `meeting_notes_YYYYMMDD_HHMMSS.md`

## Progress Tracking

The web UI shows accurate, multi-phase progress with a real-time timeline:

### Progress Phases

| Phase | Progress | Description |
|-------|----------|-------------|
| Preparing | 1-5% | File upload / recording |
| Preparing audio | 5-15% | Smart silence-based chunking |
| Transcribing | 15-55% | Parallel Speech-to-Text (GPU) |
| Analyzing | 55-90% | LLM meeting record generation |
| Saving | 90-98% | Caching results for future use |
| Complete | 100% | Done |

### Timeline Features

- **Real-time updates**: Each chunk completion is logged with timestamp
- **Status dots**: Visual indicators for completed, current, and pending steps
- **Chunk tracking**: Shows "Chunk 1/26 complete", "Chunk 2/26 complete", etc.
- **Error visibility**: Failed chunks are logged with error details

Timeline shows each step with timestamps and status dots. Parallel chunks (e.g., "Chunk 1", "Chunk 2") are logged as they finish.

## Transcript Format Options

The web UI allows you to choose between two transcript formats before processing:

### Raw (Plain Text)
- Simple, unformatted transcript
- Just the transcribed text with no speaker labels or headers
- Ideal for quick reference or when you don't need speaker identification

### Formatted (Speaker Labels)
- Professional structured output with:
  - Header showing filename and detected language
  - Speaker labels ([SPEAKER A], [SPEAKER B], etc.) based on audio analysis
  - Separators and "END OF TRANSCRIPT" footer

### Toggle Location
The format selector is located in the input panel, above the "Upload and Process" button. Select your preferred format before uploading or recording.

## Enhanced Transcript Format

The system now outputs transcripts in a professional, structured format:

```
RAW TRANSCRIPT
File: Talk1_PaloAlto.m4a
Language: Mixed English / Tagalog
===============================================================

[SPEAKER A] Okay? So mas mapapadali 'yung attack at mas...
[SPEAKER A] Okay. Based on what we've seen 'no?...
[SPEAKER B] ...
[SPEAKER A] ...

===============================================================
END OF TRANSCRIPT
```

### Features

- **Auto-detected language**: Analyzes transcript to detect English, Tagalog, and/or Bikol
- **Dynamic speaker labels**: Supports 2 or more speakers (SPEAKER A, B, C, etc.)
- **Professional formatting**: Header with file name, language, separators, and footer
- **Speaker diarization**: Uses neural networks to identify actual speakers from audio

### Language Detection

The system automatically detects languages present in the transcript:
- **English**: Detected via common words (the, is, security, attack, etc.)
- **Tagalog**: Detected via common words (ang, ng, sa, ako, kasi, etc.)
- **Bikol**: Detected via Bicolano dialect words (bako, iyo, garo, ining, etc.)

Output examples:
- `"Mixed English / Tagalog"` (if both detected)
- `"English"` (if only English)
- `"Mixed English / Tagalog / Bikol"` (if all three)

## Speaker Diarization

The system uses **pyannote.audio** for accurate speaker identification:

### How It Works

1. **Neural diarization**: Analyzes voice patterns in the audio
2. **Speaker mapping**: Assigns SPEAKER A, B, C, etc. based on actual voice segments
3. **Timestamp alignment**: Matches transcribed text with speaker segments

### Requirements

- **HuggingFace token**: Required for downloading pyannote models (pre-configured)
- **First run**: Downloads ~1.2GB model on first use, then caches locally

### Fallback

If diarization fails or no audio path is provided, the system falls back to heuristic-based speaker detection (alternates every 3 segments).

## Project Structure

```
whisper-local/
├── serverctl           # Server control script
├── run.sh             # Simple launcher
├── src/
│   ├── app.py          # Compatibility CLI entry point
│   ├── webui.py        # Compatibility Web UI launcher
│   └── whisper_local/
│       ├── audio/      # Recording, chunking, transcription, diarization
│       ├── core/       # Progress/cancellation state
│       ├── export/     # Markdown-to-PDF conversion
│       ├── integrations/ # Ollama integration
│       ├── processing/ # Audio/text processing pipelines
│       ├── web/        # Flask app and routes
│       ├── cli.py      # CLI implementation
│       ├── paths.py    # Repository-root path helpers
│       └── storage.py  # Output persistence (legacy)
├── data/
│   └── cache/        # SHA-256 result cache
├── summaries/         # Generated meeting notes (.md)
├── whisper.cpp/      # Local transcription engine (Submodule)
└── requirements.txt   # Python dependencies
```

## How It Works

```
Audio Input → ffmpeg (16kHz Mono) → whisper.cpp (Metal/GPU) → pyannote (Diarization) → Ollama (LLM) → Meeting Record
```

1. **Audio Prep**: Standardizes any format to 16kHz Mono WAV using FFmpeg.
2. **Parallel STT**: Splits audio into chunks and uses `ThreadPoolExecutor` to transcribe 2 segments at a time on the GPU.
3. **Speaker Diarization**: Uses pyannote.audio to identify distinct speakers in the audio.
4. **Transcript Formatting**: Applies structured format with speaker labels and auto-detected language.
5. **Meeting Reconstruction**: Reconstructs the full meeting with all details (names, quotes, anecdotes).
6. **PDF Export**: Converts the Markdown record to a styled PDF with proper pagination.
7. **Caching**: Results are cached in foldered structure. If re-uploaded, results are served instantly from cache.

## Caching System

The system uses a **foldered caching** mechanism for easy cache management:

### Cache Structure
```
data/cache/
├── Talk1_PaloAlto.m4a_<sha256>/
│   └── result.json    # Contains both raw + formatted transcripts
├── sample.wav_<sha256>/
│   └── result.json
└── 9f8e7d6c5b4a3210.../
    └── result.json
```

### How It Works
- **First processing**: Audio is transcribed and both raw and formatted transcripts are generated and stored
- **Subsequent requests**: Toggle between raw/formatted instantly from cache (no reprocessing)
- **Easy deletion**: Simply delete the folder for a specific file to clear its cache

### Cache Contents
Each `result.json` contains:
- `raw_transcript`: Plain text transcript
- `formatted_transcript`: Full formatted output with speaker labels
- `summary`: LLM-generated meeting summary
- `output_file`: Path to saved summary file

## Web UI Features

- **Premium Design**: Dark theme with glassmorphism effects.
- **Dual Panel**: Side-by-side view for progress/input and results.
- **Accurate Tracking**: Progress bar tracks specific chunk completion.
- **Timeline**: Real-time status updates with timestamps and status dots.
- **PDF Download**: Export meeting records as professional PDFs with page numbers.
- **Auto-Reset**: Input panel automatically returns to the upload state after completion.
- **Mobile Access (opt-in)**: Bind to `0.0.0.0` with `WHISPER_LOCAL_AUTH_TOKEN` when you intentionally want network access.

## Server Control

The `serverctl` script manages the entire lifecycle:

```bash
./serverctl start   # Start Ollama + Web UI together
./serverctl stop    # Stop both when done
./serverctl restart
./serverctl status
./serverctl build   # Compile whisper.cpp for Metal acceleration
```

## Setup (First Time)

```bash
# 1. Setup whisper.cpp
git submodule update --init --recursive
./serverctl build
bash ./whisper.cpp/models/download-ggml-model.sh small

# 2. Setup Ollama
brew install ollama
ollama pull llama3.2:3b

# 3. Setup Python dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Start the server
./serverctl start
```

## LLM Prompt

The system uses a **full meeting reconstruction** prompt (not summarization):

- Captures every name, number, quote, anecdote
- Uses chronological numbered sections
- Includes an Executive Summary section
- Translates Tagalog/Bicolano to English
- Handles edge cases (short clips, inaudible segments)

See `src/whisper_local/integrations/llm.py` for the complete prompt.

## Models

### Whisper (Transcription)
Standardized on `small` (Metal-optimized) for the best balance of speed and accuracy. Use `medium` for complex dialectal audio if hardware allows, and update `src/whisper_local/audio/transcriber.py` to point to the matching downloaded model.

### Ollama (LLM)
Optimized for `llama3.2:3b`. Higher parameter models (7b, 8b) can be swapped in `src/whisper_local/processing/pipeline.py`.

### Speaker Diarization
Uses `pyannote/speaker-diarization-3.1` (or 2.0 as fallback) from HuggingFace.

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `source .venv/bin/activate` |
| `pyaudio` errors | Ensure `brew install portaudio` before `pip install` |
| `whisper-cli` missing | Run `./serverctl build` |
| PDF generation fails | Run `brew install pango` |
| Ollama connection error | Run `./serverctl start` (starts Ollama) |
| Diarization fails | Check that `HF_TOKEN` is set in your shell or local `.env` file |

## Tech Stack

- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — Local STT (Metal optimized).
- **[pyannote.audio](https://github.com/pyannote/pyannote-audio)** — Neural speaker diarization.
- **[Ollama](https://ollama.ai)** — Local LLM runtime.
- **FFmpeg** — Professional audio standardization.
- **Flask** — Web interface.
- **Markdown** — Markdown parsing.
- **WeasyPrint** — PDF generation with CSS styling.

## License

MIT — See [LICENSE](LICENSE)

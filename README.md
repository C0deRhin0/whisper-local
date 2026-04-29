# Whisper Local

> Transcribe meeting audio and extract structured insights — entirely offline, now 2x faster.

A local transcription + LLM system for analyzing meeting recordings. 100% offline, privacy-first, and optimized for Apple Silicon (M1/M2/M3).

## Features

- **100% Local** — No cloud APIs, no data leaves your machine.
- **Parallel Pipeline** — 2x concurrent transcription workers for massive speedups on multi-core machines.
- **Full-File Caching** — SHA-256 hashing allows instant re-processing of previously analyzed files.
- **Metal Accelerated** — Native GPU support via `whisper.cpp` for lightning-fast STT on Mac.
- **Objective Summaries** — Strict "No-Naming" policy prevents AI hallucinations and ensures professional reporting.
- **Minimal Content Fallback** — Smart detection prevents corporate summaries for short test clips or greetings.
- **Long Audio Support** — Handles 60+ minute meetings with chunked processing.
- **Smart Chunking** — Natural silence detection ensures sentences aren't cut mid-stream.
- **Real-time Progress** — Accurate progress bar + timeline with Chunk-by-Chunk tracking.
- **Web UI** — Premium browser interface with a two-panel layout and dark theme.
- **Server Control** — Easy start/stop script manages everything.

## Requirements

- macOS (Apple Silicon highly recommended for Metal acceleration)
- [Homebrew](https://brew.sh)
- **ffmpeg**: `brew install ffmpeg`
- **Ollama**: `brew install ollama` (with `llama3.2:3b` pulled)
- **portaudio**: `brew install portaudio` (for microphone support)


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
4. View summary (Markdown) and transcript (Text).
5. Download results using the dedicated buttons.

### Via CLI

```bash
# Process a file
python src/app.py path/to/meeting.wav

# Or record from microphone
python src/app.py
```

## Progress Tracking

The web UI shows accurate, multi-phase progress:

| Phase | Progress | Description |
|-------|----------|-------------|
| Preparing | 1-5% | File upload / recording |
| Preparing audio | 5-15% | Smart silence-based chunking |
| Transcribing | 15-55% | Parallel Speech-to-Text (GPU) |
| Analyzing | 55-90% | Executive LLM Summarization |
| Saving | 90-98% | Caching results for future use |
| Complete | 100% | Done |

Timeline shows each step with timestamps and status dots. Parallel chunks (e.g., "Chunk 1", "Chunk 2") are logged as they finish.

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
│   └── storage.py    # Output persistence (legacy)
├── data/
│   └── cache/        # SHA-256 result cache
├── summaries/         # Generated meeting notes (.md)
├── whisper.cpp/      # Local transcription engine (Submodule)
└── requirements.txt   # Python dependencies
```

## How It Works

```
Audio Input → ffmpeg (16kHz Mono) → whisper.cpp (Metal/GPU) → Ollama (Executive LLM)
```

1. **Audio Prep**: Standardizes any format to 16kHz Mono WAV using FFmpeg.
2. **Parallel STT**: Splits audio into chunks and uses `ThreadPoolExecutor` to transcribe 2 segments at a time on the GPU.
3. **Batch Analysis**: Reconstructs the transcript and provides it to the LLM for high-fidelity professional synthesis.
4. **Caching**: Hashes the full file via SHA-256. If re-uploaded, results are served instantly from `data/cache/`.

## Web UI Features

- **Premium Design**: Midnight blue gradient background with glassmorphism effects.
- **Dual Panel**: Side-by-side view for progress/input and results.
- **Accurate Tracking**: Progress bar tracks specific chunk completion.
- **Auto-Reset**: Input panel automatically returns to the upload state after completion.
- **Mobile Access**: Responsive design accessible from your network URL.
- **Overscroll Fix**: Fixed background pinning prevents white flashes on Mac browsers.

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

# 3. Start the server
./serverctl start
```

## Models

### Whisper (Transcription)
Standardized on `small` (Metal-optimized) for the best balance of speed and accuracy. Use `medium` for complex dialectal audio if hardware allows.

### Ollama (LLM)
Optimized for `llama3.2:3b`. Higher parameter models (7b, 8b) can be swapped in `src/llm.py`.

## Tech Stack

- **[whisper.cpp](https://github.com/ggerganov/whisper.cpp)** — Local STT (Metal optimized).
- **[Ollama](https://ollama.ai)** — Local LLM runtime.
- **FFmpeg** — Professional audio standardization.
- **Flask** — Web interface.

## License

MIT — See [LICENSE](LICENSE)
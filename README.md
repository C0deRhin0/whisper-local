# Whisper Local

> Transcribe meeting audio and extract structured insights — entirely offline.

Whisper Local processes meeting recordings through local speech recognition and local LLMs to produce structured summaries with key decisions, action items, and open questions.

## Features

- **100% local** — No cloud APIs, no data leaves your machine
- **Long audio support** — Handles 60+ minute meetings with chunked processing
- **Structured output** — Extracts decisions, action items, owners, deadlines
- **Privacy-first** — Your meeting data stays on your machine

## Requirements

- macOS (Linux support coming)
- [Homebrew](https://brew.sh)
- 4GB+ RAM recommended

## Quick Start

```bash
# 1. Clone and enter project
git clone https://github.com/yourusername/whisper-local.git
cd whisper-local

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start Ollama (in another terminal)
brew services start ollama
ollama pull llama3.2:3b

# 5. Run with a file
python src/app.py path/to/meeting.wav
```

Or record from microphone:

```bash
python src/app.py
```

## Project Structure

```
whisper-local/
├── src/
│   ├── app.py            # CLI entry point
│   ├── pipeline.py       # Main orchestration
│   ├── recorder.py       # Microphone recording
│   ├── transcriber.py    # whisper.cpp wrapper
│   ├── llm.py            # Ollama integration
│   ├── audio_utils.py    # Long-audio chunking
│   └── storage.py        # Output persistence
├── summaries/             # Generated meeting notes
├── whisper.cpp/         # Local transcription engine
└── USAGE.md             # Detailed usage guide
```

## How It Works

```
Audio Input → whisper.cpp → Transcript → Ollama → Structured Summary
  (WAV)        (local STT)     (text)      (local LLM)     (markdown)
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Whisper Local                           │
├─────────────────────────────────────────────────────────────┤
│  app.py                                               │
│    └→ pipeline.py (orchestration)                       │
│         ├→ recorder.py    (PyAudio → WAV)               │
│         ├→ transcriber.py (subprocess → whisper-cli)     │
│         ├→ llm.py       (requests → Ollama API)       │
│         ├→ audio_utils.py (chunking for long audio)       │
│         └→ storage.py   (markdown output)               │
└─────────────────────────────────────────────────────────────┘
```

1. **Audio** — Load a file or record from microphone (PyAudio)
2. **Transcribe** — whisper-cli (from whisper.cpp) converts speech to text locally
3. **Analyze** — Ollama extracts decisions, action items, owners
4. **Save** — Results saved to `summaries/meeting_<timestamp>.md`

### Why whisper.cpp?

This project uses [whisper.cpp](https://github.com/ggerganov/whisper.cpp) instead of the original OpenAI Python package:

- **No Python/PyTorch required** — Runs as a standalone binary
- **CPU + Apple Metal** — Works on Mac without GPU
- **Small footprint** — ~150MB model vs 1GB+
- **100% offline** — No API calls toOpenAI

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

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `--duration` | 30s | Recording duration (mic) |
| `chunk_duration` | 300s (5min) | Audio chunk size for long files |

## Setup

### whisper.cpp (transcription engine)

```bash
# Clone and build
git clone https://github.com/ggerganov/whisper.cpp.git whisper.cpp
cd whisper.cpp
make -j

# Download base model
bash ./models/download-ggml-model.sh base
```

### Verify

```bash
# Test transcription
./build/bin/whisper-cli -m ./models/ggml-base.bin -f ./samples/jfk.wav

# Test Ollama
curl -s http://localhost:11434/api/generate \
  -d '{"model":"llama3.2:3b","prompt":"Say hi","stream":false}'
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Ollama not running` | `brew services start ollama` |
| `whisper-cli not found` | Build: `cd whisper.cpp && make -j` |
| `portaudio not found` | `brew install portaudio` |
| Module errors | Ensure venv: `source .venv/bin/activate` |

## Tech Stack

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) — Local speech-to-text (built on top of OpenAI Whisper)
- [Ollama](https://ollama.ai) — Local LLM runtime
- PyAudio — Microphone input
- Python 3.13+ — Core logic

## License

MIT — See [LICENSE](LICENSE)

## Acknowledgments

This project would not exist without [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov — bringing OpenAI's Whisper model to run locally on consumer hardware.

## Credits

- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov
- [Ollama](https://ollama.ai) for local LLM inference
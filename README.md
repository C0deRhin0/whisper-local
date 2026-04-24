# Whisper Local

> Transcribe meeting audio and extract structured insights — entirely offline.

⚠️ **Proof of Concept** — This project demonstrates local transcription + LLM processing. Quality improves with better hardware and models.

## Features

- **100% local** — No cloud APIs, no data leaves your machine
- **Long audio support** — Handles 60+ minute meetings with streaming chunked processing
- **Structured output** — Extracts decisions, action items, owners, deadlines
- **Privacy-first** — Your meeting data stays on your machine
- **Multiple formats** — Works with WAV, MP3, M4A, AAC, OGG, AIFF, FLAC
- **On-the-fly processing** — Starts immediately, no pre-calculation
- **Audio cleanup** — Filters repetitions and filler from rugged recordings

## Requirements

- macOS (Linux support coming)
- [Homebrew](https://brew.sh)
- 4GB+ RAM recommended
- **ffmpeg** (for non-WAV formats): `brew install ffmpeg`

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

# 4. Setup whisper.cpp (transcription engine)
git clone https://github.com/ggerganov/whisper.cpp.git whisper.cpp
cd whisper.cpp
make -j
bash ./models/download-ggml-model.sh small  # ~465MB
cd ..

# 5. Start Ollama (in another terminal)
brew services start ollama
ollama pull llama3.2:3b

# 6. Run with a file
python src/app.py path/to/meeting.wav
```

Or record from microphone:

```bash
python src/app.py
```

## Realistic Usage

Here's how you'd use Whisper Local for a weekly team meeting:

### Step 1: Record the meeting (before)

Record using your video conferencing app (Zoom/Meet/Teams) and download the audio:

```
# In Zoom: Recording → Download
# In Meet: More → Download meeting recording
# In Teams: Meeting chat → Download
```

### Step 2: Process the audio

```bash
cd /path/to/whisper-local
source .venv/bin/activate

# Option A: From file
python src/app.py recordings/team-standup-feb-14.wav

# Option B: Direct from microphone (30 sec demo)
python src/app.py

# Option C: Custom mic duration
python src/app.py --duration 120   # 2 min recording
```

### Step 3: Get your summary

Output is saved to `summaries/meeting_YYYYMMDD_HHMMSS.md`:

```markdown
## Executive Summary
The team reviewed Q1 progress. Key focus areas are product launch in March, 
hiring two additional engineers, and addressing customer feedback on the beta.

## Decisions
- Proceed with March product launch — Sarah
- Open 2 senior engineer roles — David

## Action Items
- Finalize launch timeline — Sarah — Feb 28
- Post job listings — David — Feb 21
- Schedule beta user interviews — Jordan — Feb 24

## Open Questions
- Should we delay launch by one week for more testing?
```

### Step 4: Review and share

Open the markdown file, copy relevant sections to Notion/Slack/email, or paste into your task tracker.

### Weekly workflow

```bash
# Monday: Download recording
# Tuesday:
source .venv/bin/activate
python src/app.py monday-meeting.wav
# Files auto-saved to summaries/
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
- **Small footprint** — ~465MB model (small) vs 1GB+ (PyTorch)
- **100% offline** — No API calls to OpenAI
- **Handles rugged audio** — Built-in filtering of repetitions and filler

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

## Improving Quality

This is a proof of concept. To improve:

### Better Transcription Model

```bash
# Download better whisper model
cd whisper.cpp
bash ./models/download-ggml-model.sh medium  # ~1.5GB, best accuracy

# Then edit src/transcriber.py:
# Change: "ggml-small.bin" → "ggml-medium.bin"
```

### Better LLM

```bash
# More capable model (7B vs 3B)
ollama pull llama3.2:7b

# Then edit src/llm.py:
DEFAULT_MODEL = "llama3.2:7b"
```

### Multilingual Support

```bash
ollama pull llama3.2:latest  # Better for mixed language

# Then edit src/llm.py:
DEFAULT_MODEL = "llama3.2:latest"
```

## Setup

### whisper.cpp (transcription engine)

```bash
# Clone and build
git clone https://github.com/ggerganov/whisper.cpp.git whisper.cpp
cd whisper.cpp
make -j

# Download small model (recommended - best accuracy/speed balance)
bash ./models/download-ggml-model.sh small

# Or download base model (faster but less accurate)
# bash ./models/download-ggml-model.sh base
```

**Model sizes:**
| Model | Size | Accuracy | Use Case |
|-------|------|----------|----------|
| tiny | ~39MB | Basic | Testing |
| **small** | ~465MB | High | ✅ Recommended |
| medium | ~1.5GB | Higher | Best accuracy |
| base | ~147MB | Medium | Fast but less accurate |

## Real-World Usage

### Scenario: Weekly Team Meeting (30-60 min)

```
1. Before meeting
   - Plug in your laptop
   - Open Terminal: `source .venv/bin/activate`

2. During meeting
   - Just focus on listening and participating
   - Optionally record the meeting video/audio

3. After meeting
   $ python src/app.py recording.wav
   
   Whisper Local:
   ├→ Transcribes the audio
   ├→ Extracts decisions & action items
   └→ Saves to summaries/meeting_20241015_143022.md

4. Share with team
   - Upload the .md file to Slack/Notion/Google Docs
```

### Multilingual Meetings (English + Tagalog/Filipino)

whisper.cpp supports **99 languages**. This project is optimized for Filipino meetings.

**Current setting:** Transcription uses forced Tagalog (`-l tl`) for better accuracy.

| Language | Transcription | Summary Output |
|----------|---------------|----------------|
| English | ✅ Works | English |
| Tagalog/Filipino | ✅ Works well (forced) | English |
| Mixed EN+TL | ✅ Works well (forced) | English |

**For English-only recordings:**

```bash
# Edit src/transcriber.py, change "-l tl" to "-l en"
```

**For automatic detection (all languages):**

```bash
# Edit src/transcriber.py, change "-l tl" to "-l auto"
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
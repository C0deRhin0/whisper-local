# Whisper Local — Web UI Guide

## Quick Start

```bash
# Start the server (Ollama + Web UI)
./serverctl start

# Or use the simple launcher:
./run.sh
```

Then open **http://localhost:8080** in your browser.

## Server Control

Use `serverctl` to manage the entire service:

```bash
./serverctl start   # Start Ollama + Web UI
./serverctl stop    # Stop Web UI + Ollama
./serverctl restart # Restart everything
./serverctl status # Show status
```

## Usage

### Option 1: Upload Audio File
1. Open browser (http://localhost:8080)
2. Click the file picker box
3. Select your meeting audio (WAV, MP3, M4A, AAC)
4. Click "Upload and Process"
5. Watch progress bar and timeline update in real-time
6. View summary and transcript
7. Download as text files

### Option 2: Record Directly
1. Open browser (http://localhost:8080)
2. Enter duration in seconds
3. Click "Start Recording"
4. Speak into the host computer's microphone
5. Watch progress bar and timeline
6. View summary and transcript
7. Download as text files

## Network Access

Access from other devices on your network:
```
http://[YOUR_IP]:8080
```

To find your IP, check the footer on the web page after starting.

**Note:** Recording uses the host computer's microphone.

## Features

- Upload WAV, MP3, M4A, AAC, OGG files
- Record directly from microphone (host computer)
- **Accurate progress bar** (0-100% based on actual pipeline phase)
- **Real-time timeline** showing each step with timestamps
- **Chunk tracking** for long audio (e.g., "Transcribing audio (2/5)")
- Smooth fade-out animation when complete
- Clean summary output
- Full transcript view
- Download Summary/Transcript as text files
- Auto-cleanup of temp files after processing
- Page refresh cancels and resets state
- Works offline (100% local)
- Access from phone/tablet on same network
- Beautiful glassmorphism UI

## Progress Tracking

The progress bar accurately reflects pipeline phases:

| Phase | Progress | Description |
|-------|----------|-------------|
| Preparing | 1-5% | File upload/recording |
| Preparing audio | 5-15% | Audio splitting |
| Transcribing | 15-55% | Speech-to-text (per chunk) |
| Analyzing | 55-90% | LLM summarization (per chunk) |
| Saving | 90-98% | Saving results |
| Complete | 100% | Done |

### Timeline
Shows each step as it happens:
- Green dot = completed
- Blue pulsing dot = in progress
- Timestamp + message for each step

### Long Audio Processing
For audio with multiple chunks:
- "Transcribing audio (1/3)", "Transcribing audio (2/3)", etc.
- "Analyzing content (1/3)", etc.
- Progress interpolates across all chunks

## Beautiful UI

- Midnight blue gradient background (#1a1a2e)
- Glassmorphism cards with blur effect
- Gradient buttons
- Custom scrollbars
- Smooth animations
- Progress phase name displayed
- Clean timeline design

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Can't access localhost:8080 | `./serverctl start` |
| Ollama not running | `./serverctl start` |
| Microphone not working | Check system permissions |
| Page freezes on refresh | State auto-resets |
| File upload shows nothing | Make sure to select file first |

## Files

- `src/webui.py` - Flask web server
- `src/progress.py` - Progress tracking system
- `src/pipeline.py` - Audio processing pipeline
- `serverctl` - Server control script
import subprocess
import os
import re
import pathlib
import tempfile
import shutil
import hashlib

from whisper_local.paths import CACHE_DIR, PROJECT_ROOT, load_env_file


load_env_file()

# Base directory
BASE_DIR = PROJECT_ROOT

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_model_path() -> pathlib.Path:
    """Resolve the whisper.cpp model without forcing a fresh download."""

    configured_path = os.environ.get("WHISPER_MODEL_PATH")
    if configured_path:
        path = pathlib.Path(configured_path).expanduser()
        return path if path.is_absolute() else BASE_DIR / path

    model_dir = BASE_DIR / "whisper.cpp" / "models"
    configured_name = os.environ.get("WHISPER_MODEL_NAME")
    candidate_names = []
    if configured_name:
        candidate_names.append(configured_name if configured_name.startswith("ggml-") else f"ggml-{configured_name}.bin")

    # Keep the documented small model as the first choice, but preserve existing
    # local setups that already have medium/base downloaded from pre-migration use.
    candidate_names.extend(["ggml-small.bin", "ggml-medium.bin", "ggml-base.bin"])

    for name in candidate_names:
        candidate = model_dir / name
        if candidate.exists():
            return candidate

    return model_dir / candidate_names[0]


def _whisper_runtime_env() -> dict:
    """Build an environment that lets relocated whisper.cpp binaries find dylibs."""

    env = os.environ.copy()
    build_dir = BASE_DIR / "whisper.cpp" / "build"
    library_dirs = [
        build_dir / "src",
        build_dir / "ggml" / "src",
        build_dir / "ggml" / "src" / "ggml-blas",
        build_dir / "ggml" / "src" / "ggml-cpu",
        build_dir / "ggml" / "src" / "ggml-metal",
    ]
    existing_library_dirs = [str(path) for path in library_dirs if path.exists()]

    if existing_library_dirs:
        existing = env.get("DYLD_LIBRARY_PATH")
        env["DYLD_LIBRARY_PATH"] = ":".join(existing_library_dirs + ([existing] if existing else []))

    return env

def _get_file_hash(file_path: str) -> str:
    """Generate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def _clean_transcript(text: str) -> str:
    """Clean transcript - remove duplicates and redundant timestamps."""
    lines = text.split('\n')
    cleaned = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # whisper.cpp output format is [00:00:00.000 --> 00:00:05.000] text
        line = re.sub(r'\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]\s*', '', line)

        if not line.strip():
            continue

        cleaned.append(line.strip())

    deduped = []
    prev = None
    for line in cleaned:
        if line != prev:
            deduped.append(line)
        prev = line

    return ' '.join(deduped)


def detect_languages(text: str) -> str:
    """
    Detect languages present in the transcript.
    Looks for common words/phrases to identify English, Tagalog, and Bikol.
    """
    text_lower = text.lower()

    # Common Tagalog words/phrases
    tagalog_indicators = [
        'ang', 'ng', 'sa', 'ako', 'ikaw', 'siya', 'kami', 'kayo', 'sila',
        'mga', 'yung', 'nang', 'pero', 'at', 'ang', 'ito', 'iyon', 'iyang',
        'kasi', 'kayong', 'naman', 'lang', 'ba', 'nga', 'po', 'sir', "ma'am",
        'may', 'meron', 'wala', 'hindi', 'oo', 'hindi', 'sige', 'okay',
        'kumbaga', 'meaning', 'actually', 'so', 'well', 'right', 'di ba',
        'no?', 'ano', 'pa', 'nga', 'daw', 'raw', 'kayo', 'natin', 'sayo',
        'samin', 'nila', 'niya', 'niyo', 'namin', 'kanyan', 'ganun', 'ganyan',
        'dito', 'doon', 'diyan', 'saan', 'kailan', 'paano', 'bakit', 'dahil',
        'kung', 'kasi', 'kay', 'para', 'para sa', 'tungkol', 'regarding',
        'thanks', 'salamat', 'maraming', 'salamat', 'po', 'sir', 'maam'
    ]

    # Common Bikol words (Bicolano dialect)
    bikol_indicators = [
        'ka', 'na', 'nga', 'man', 'pa', 'lang', 'nga', 'ka', 'ta', 'mo',
        'ko', 'niya', 'nila', 'nato', 'nimo', 'ninyo', 'sila', 'kami',
        'kayo', 'ikaw', 'siya', 'ako', ' diri', 'didto', 'diri', 'didto',
        'ni', 'sa', 'para', 'kay', 'og', 'ang', 'sa', 'ka', 'na', 'nga',
        'bako', 'iyo', 'garo', 'ining'
    ]

    # Common English words
    english_indicators = [
        'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can',
        'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where',
        'how', 'what', 'who', 'which', 'that', 'this', 'these', 'those',
        'we', 'you', 'they', 'he', 'she', 'it', 'i', 'me', 'him', 'her',
        'our', 'your', 'their', 'its', 'my', 'his', 'hers', 'theirs',
        'security', 'attack', 'vulnerability', 'system', 'network', 'data',
        'ai', 'model', 'cloud', 'application', 'endpoint', 'identity'
    ]

    # Count occurrences
    tagalog_count = sum(1 for word in tagalog_indicators if word in text_lower)
    english_count = sum(1 for word in english_indicators if word in text_lower)
    bikol_count = sum(1 for word in bikol_indicators if word in text_lower)

    # Determine languages (at least 3 occurrences to be considered present)
    languages = []
    if english_count >= 3:
        languages.append("English")
    if tagalog_count >= 3:
        languages.append("Tagalog")
    if bikol_count >= 3:
        languages.append("Bikol")

    # Default to Tagalog/English if nothing detected
    if not languages:
        return "Mixed English / Tagalog"

    if len(languages) == 1:
        return languages[0]

    return "Mixed " + " / ".join(languages)


def get_speaker_diarization(audio_path: str) -> list:
    """
    Use pyannote.audio to detect speakers from the audio file.

    Returns a list of (start_time, end_time, speaker_label) tuples.
    Applies merging logic to reduce over-segmentation from voice variations.
    """
    try:
        from pyannote.audio import Pipeline

        # HuggingFace token for pyannote models
        HF_TOKEN = os.environ.get("HF_TOKEN", "")

        # Load the pretrained pipeline with authentication
        # Using 3.1 for better quality (requires token)
        try:
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=HF_TOKEN
            )
            print("[Diarization] Using pyannote/speaker-diarization-3.1")
        except Exception as e:
            print(f"[Diarization] 3.1 failed: {e}, trying 2.0")
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-2.0",
                use_auth_token=HF_TOKEN
            )
            print("[Diarization] Using pyannote/speaker-diarization-2.0")

        # Run diarization on the audio file
        diarization = pipeline(audio_path)

        # Collect all segments with their raw speaker labels
        raw_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            raw_segments.append({
                'start': turn.start,
                'end': turn.end,
                'speaker': speaker
            })

        print(f"[Diarization] Raw segments: {len(raw_segments)}")

        # Merge segments that are very close together (within 3 seconds)
        # and belong to the same speaker
        MIN_MERGE_GAP = 3.0  # seconds
        merged_segments = []

        if raw_segments:
            current = raw_segments[0].copy()
            for seg in raw_segments[1:]:
                # If same speaker and gap is small, merge them
                if seg['speaker'] == current['speaker'] and seg['start'] - current['end'] < MIN_MERGE_GAP:
                    current['end'] = seg['end']
                else:
                    merged_segments.append(current)
                    current = seg.copy()
            merged_segments.append(current)

        print(f"[Diarization] After merging: {len(merged_segments)} segments")

        # Map to speaker labels - allow all unique speakers but map to A, B, C, etc.
        unique_speakers = {}
        speaker_idx = 0

        for seg in merged_segments:
            spk = seg['speaker']
            if spk not in unique_speakers:
                unique_speakers[spk] = speaker_idx
                speaker_idx += 1

            # Map to A, B, C, D, E, F, G, H, I, J (max 10)
            label_idx = unique_speakers[spk] % 26
            label = f"SPEAKER {chr(65 + label_idx)}"
            seg['speaker'] = label

        # Remove very short segments (less than 2 seconds) - likely noise
        MIN_SEGMENT_DURATION = 2.0
        filtered_segments = [s for s in merged_segments if s['end'] - s['start'] >= MIN_SEGMENT_DURATION]

        # Count unique speakers after filtering
        final_speakers = set(s['speaker'] for s in filtered_segments)
        print(f"[Diarization] Final: {len(final_speakers)} speakers ({', '.join(final_speakers)}), {len(filtered_segments)} segments")

        return filtered_segments

    except Exception as e:
        print(f"[Diarization] Error: {e}")
        print("[Diarization] Falling back to heuristic-based speaker detection")
        return None


def format_transcript(clean_text: str, file_name: str = "audio", language: str = None, audio_path: str = None) -> str:
    """
    Format cleaned transcript to match the online LLM output format.

    This adds:
    - Header with file name and auto-detected language
    - Dynamic speaker labels (SPEAKER A, B, C, etc.) based on audio analysis
    - Separators
    - END OF TRANSCRIPT footer

    If audio_path is provided, uses pyannote.audio for accurate speaker diarization.
    Otherwise falls back to heuristic-based detection.
    """
    import re

    # Auto-detect language if not provided
    if language is None:
        language = detect_languages(clean_text)

    # Try to use pyannote diarization if audio path is available
    diarization_segments = None
    if audio_path and os.path.exists(audio_path):
        print(f"[Format] Running speaker diarization on {audio_path}")
        diarization_segments = get_speaker_diarization(audio_path)

    if diarization_segments:
        # Use pyannote's diarization results
        formatted_lines = []

        # Split text into sentences for better assignment
        import re
        sentences = re.split(r'(?<=[.!?])\s+', clean_text)

        # Group sentences into diarization segments
        # Each diarization segment gets a proportional number of sentences
        total_diar_duration = sum(seg['end'] - seg['start'] for seg in diarization_segments)

        if total_diar_duration > 0 and sentences:
            # Calculate how many sentences per second of audio
            sentences_per_second = len(sentences) / total_diar_duration

            current_sentence_idx = 0
            for seg in diarization_segments:
                seg_duration = seg['end'] - seg['start']
                estimated_sentences = max(1, int(seg_duration * sentences_per_second))

                # Get sentences for this segment
                segment_sentences = []
                for _ in range(estimated_sentences):
                    if current_sentence_idx < len(sentences):
                        segment_sentences.append(sentences[current_sentence_idx])
                        current_sentence_idx += 1

                if segment_sentences:
                    text_chunk = ' '.join(segment_sentences)
                    formatted_lines.append(f"[{seg['speaker']}] {text_chunk}")

            # Add any remaining sentences to the last segment
            if current_sentence_idx < len(sentences):
                remaining = ' '.join(sentences[current_sentence_idx:])
                if remaining and formatted_lines:
                    formatted_lines[-1] = formatted_lines[-1] + ' ' + remaining
        else:
            # Fallback if no sentences found
            formatted_lines.append(f"[SPEAKER A] {clean_text}")

        formatted_text = '\n\n'.join(formatted_lines)
    else:
        # Fallback to heuristic-based speaker detection
        # Split into sentences/segments for speaker detection
        segments = re.split(r'(?<=[.!?])\s+(?=[A-Z])', clean_text)

        if not segments or len(segments) <= 1:
            # If no clear sentence boundaries, just split by chunks of ~80 words
            words = clean_text.split()
            segments = []
            for i in range(0, len(words), 80):
                segments.append(' '.join(words[i:i+80]))

        # Dynamic speaker assignment based on segment characteristics
        formatted_lines = []

        # Start with speaker A
        speaker_labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        current_speaker_idx = 0

        # Heuristic: Switch speaker every 3 segments to simulate natural conversation
        segments_per_speaker = 3

        for i, segment in enumerate(segments):
            segment = segment.strip()
            if not segment:
                continue

            # Switch speaker periodically
            if i > 0 and i % segments_per_speaker == 0:
                current_speaker_idx = (current_speaker_idx + 1) % len(speaker_labels)

            speaker_label = f"SPEAKER {speaker_labels[current_speaker_idx]}"
            formatted_lines.append(f"[{speaker_label}] {segment}")

        formatted_text = '\n\n'.join(formatted_lines)

    # Build the final output
    separator = "=" * 60

    output = f"""RAW TRANSCRIPT
File: {file_name}
Language: {language}
{separator}

{formatted_text}

{separator}
END OF TRANSCRIPT"""

    return output

def transcribe(audio_path: str, prompt: str = "", format_output: bool = False, file_name: str = "audio", cache_dir: str = None) -> str:
    """
    Transcribe audio file using whisper.cpp CLI with caching and format conversion.

    Args:
        audio_path: Path to the audio file
        prompt: Optional prompt for context
        format_output: If True, return formatted output with speaker labels
        file_name: Name of the file for the formatted output header
        cache_dir: If provided, save chunk cache inside this directory instead of global CACHE_DIR

    Returns:
        Transcribed text (raw or formatted based on format_output)
    """
    import time
    from whisper_local.core.progress import is_cancelled, register_pid, unregister_pid
    start_time = time.time()

    # 1. Check Cache — use cache_dir if provided, else global CACHE_DIR
    file_hash = _get_file_hash(audio_path)
    if cache_dir:
        cache_path = pathlib.Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        cache_file = cache_path / f"{file_hash}.txt"
    else:
        cache_file = CACHE_DIR / f"{file_hash}.txt"

    if cache_file.exists():
        print(f"[Transcribe] Cache hit for {audio_path} ({time.time() - start_time:.1f}s)")
        raw_text = cache_file.read_text(encoding='utf-8')

        if format_output:
            return format_transcript(raw_text, file_name=file_name)
        return raw_text

    if is_cancelled():
        return ""

    print(f"[Transcribe] Starting transcription for {audio_path}...")

    # 2. Prepare Paths
    model_path = _resolve_model_path()
    whisper_bin = BASE_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli"
    
    if not whisper_bin.exists():
        raise FileNotFoundError(f"whisper-cli binary not found at {whisper_bin}")
    if not model_path.exists():
        raise FileNotFoundError(f"Whisper model not found at {model_path}")

    # 3. Audio Conversion (Ensure 16kHz WAV for whisper.cpp)
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_wav:
        converted_wav = tmp_wav.name
        
    try:
        if is_cancelled():
            return ""

        # Convert to 16kHz mono WAV using ffmpeg
        conv_cmd = [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            converted_wav
        ]
        subprocess.run(conv_cmd, capture_output=True, check=True)

        if is_cancelled():
            return ""

        # 4. Transcription — use Popen so process can be killed on cancel
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp_out:
            output_base = tmp_out.name[:-4]
            tmp_txt_name = tmp_out.name

        try:
            # Use half the cores if we expect parallel runs to avoid contention
            threads = max(1, os.cpu_count() // 2)
            
            cmd = [
                str(whisper_bin),
                "-m", str(model_path),
                "-f", converted_wav,
                "-l", "tl",
                "-t", str(threads),
                "-fa",
                "-otxt",
                "-of", output_base
            ]
            
            if prompt:
                cmd.extend(["--prompt", prompt])

            # Launch subprocess and register for kill-on-cancel
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=_whisper_runtime_env(),
            )
            register_pid(proc.pid)

            try:
                stdout, stderr = proc.communicate()
                if is_cancelled():
                    print(f"[Transcribe] Cancelled — aborting transcription of {audio_path}")
                    return ""
                if proc.returncode != 0:
                    error_msg = stderr or "Unknown error"
                    print(f"[Transcribe] Whisper error: {error_msg}")
                    raise RuntimeError(f"Whisper failed: {error_msg}")
            finally:
                unregister_pid(proc.pid)

            output_file = output_base + ".txt"
            if os.path.exists(output_file):
                with open(output_file, 'r', encoding='utf-8') as f:
                    raw_text = f.read()
                os.remove(output_file)

                final_text = _clean_transcript(raw_text)

                # 5. Save to Cache (always save raw text) — inside the provided cache_dir
                cache_file.write_text(final_text, encoding='utf-8')
                elapsed = time.time() - start_time
                print(f"[Transcribe] Completed in {elapsed:.1f}s, text length: {len(final_text)} chars")

                if is_cancelled():
                    return ""

                # Return formatted or raw based on option
                if format_output:
                    return format_transcript(final_text, file_name=file_name)
                return final_text

            print(f"[Transcribe] Warning: No output file generated")
            return ""

        finally:
            if os.path.exists(tmp_txt_name):
                os.remove(tmp_txt_name)
    
    finally:
        if os.path.exists(converted_wav):
            os.remove(converted_wav)

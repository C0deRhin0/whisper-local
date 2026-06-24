"""Audio recording, chunking, and transcription helpers."""

__all__ = [
    "format_transcript",
    "record_audio",
    "record_audio_manual",
    "save_summary",
    "split_audio",
    "transcribe",
]


def __getattr__(name):
    """Lazily expose audio helpers so imports do not require PyAudio."""

    if name in {"record_audio", "record_audio_manual"}:
        from whisper_local.audio.recorder import record_audio, record_audio_manual

        return {"record_audio": record_audio, "record_audio_manual": record_audio_manual}[name]

    if name in {"format_transcript", "transcribe"}:
        from whisper_local.audio.transcriber import format_transcript, transcribe

        return {"format_transcript": format_transcript, "transcribe": transcribe}[name]

    if name in {"save_summary", "split_audio"}:
        from whisper_local.audio.utils import save_summary, split_audio

        return {"save_summary": save_summary, "split_audio": split_audio}[name]

    raise AttributeError(f"module 'whisper_local.audio' has no attribute {name!r}")

__all__ = [
    "record_audio",
    "record_audio_manual",
    "transcribe",
    "summarize",
    "save_summary",
    "run_pipeline",
    "process_text"
]


def __getattr__(name):
    """Lazily expose common public helpers without importing heavy dependencies."""

    if name in {"record_audio", "record_audio_manual"}:
        from whisper_local.audio.recorder import record_audio, record_audio_manual

        return {"record_audio": record_audio, "record_audio_manual": record_audio_manual}[name]

    if name == "transcribe":
        from whisper_local.audio.transcriber import transcribe

        return transcribe

    if name == "summarize":
        from whisper_local.integrations.llm import summarize

        return summarize

    if name == "save_summary":
        from whisper_local.audio.utils import save_summary

        return save_summary

    if name in {"run_pipeline", "process_text"}:
        from whisper_local.processing.pipeline import process_text, run_pipeline

        return {"run_pipeline": run_pipeline, "process_text": process_text}[name]

    raise AttributeError(f"module 'whisper_local' has no attribute {name!r}")

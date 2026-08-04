"""Unit tests for bounded, ordered local meeting-document generation."""

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from whisper_local.processing import chunk_and_merge
from whisper_local.processing import pipeline


class SummaryPipelineTests(unittest.TestCase):
    def test_chunker_preserves_all_text_and_honors_small_boundaries(self) -> None:
        text = "One sentence. Second question? Third answer! " * 40
        chunks = chunk_and_merge.split_into_chunks(text, chunk_size=64)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(" ".join(chunks), text.strip())
        self.assertTrue(all(chunk_and_merge.count_tokens(chunk) <= 64 for chunk in chunks))

    def test_full_pipeline_writes_one_final_document_from_ordered_evidence(self) -> None:
        transcript = "First item happened. Second item happened. Third item happened. Fourth item happened. Fifth item happened."
        replies = iter([
            "### Segment 1\n- first evidence",
            "# Meeting\n## Executive Summary\nA factual overview.\n---\n## Full Meeting Record\n### 1. Discussion\nfirst evidence",
        ])

        with patch.object(chunk_and_merge, "_generate", side_effect=lambda *args, **kwargs: next(replies)):
            result = chunk_and_merge.process_full_transcript(transcript)

        self.assertIn("# Meeting", result)
        self.assertIn("## Full Meeting Record", result)

    def test_ollama_request_is_bounded(self) -> None:
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"response": "ok"}

        post = MagicMock(return_value=Response())
        # requests is imported lazily by production code; a tiny stand-in keeps
        # this unit test independent of optional runtime dependencies.
        with patch.dict(sys.modules, {"requests": types.SimpleNamespace(post=post)}):
            self.assertEqual(chunk_and_merge._generate("hello", "model", num_predict=7), "ok")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_ctx"], chunk_and_merge.OLLAMA_CONTEXT_TOKENS)
        self.assertEqual(payload["options"]["num_predict"], 7)

    def test_transcribe_only_skips_llm_and_later_full_run_reuses_cached_transcript(self) -> None:
        """The three user-facing modes must not accidentally re-transcribe audio."""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "meeting.wav"
            audio.write_bytes(b"not-real-audio; dependencies are mocked")
            cache = root / "cache"
            summaries = root / "summaries"

            with (
                patch.object(pipeline, "CACHE_DIR", cache),
                patch.object(pipeline, "SUMMARIES_DIR", summaries),
                patch.object(pipeline, "split_audio", return_value=["chunk.wav"]) as split_audio,
                patch.object(pipeline, "transcribe", return_value="raw meeting transcript") as transcribe,
                patch.object(pipeline, "process_full_transcript", return_value="generated meeting record") as summarize,
            ):
                raw_only = pipeline._process_audio(str(audio), original_filename="meeting.wav", mode="transcribe_only")
                self.assertEqual(raw_only["summary"], "")
                summarize.assert_not_called()

                full = pipeline._process_audio(str(audio), original_filename="meeting.wav", mode="full")

            self.assertEqual(full["transcript"], "raw meeting transcript")
            self.assertEqual(full["summary"], "generated meeting record")
            split_audio.assert_called_once()
            transcribe.assert_called_once()
            summarize.assert_called_once_with("raw meeting transcript", model=pipeline.DEFAULT_LLM_MODEL)

    def test_summary_only_processes_text_without_audio_transcription(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with (
                patch.object(pipeline, "CACHE_DIR", root / "cache"),
                patch.object(pipeline, "SUMMARIES_DIR", root / "summaries"),
                patch.object(pipeline, "process_full_transcript", return_value="text-only meeting record") as summarize,
            ):
                result = pipeline.process_text("A pasted transcript with enough content.")

            self.assertEqual(result["transcript"], "A pasted transcript with enough content.")
            self.assertEqual(result["summary"], "text-only meeting record")
            summarize.assert_called_once_with(
                "A pasted transcript with enough content.", model=pipeline.DEFAULT_LLM_MODEL
            )


if __name__ == "__main__":
    unittest.main()

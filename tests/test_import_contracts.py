"""Smoke tests for public import and entrypoint contracts.

These tests intentionally avoid starting the Flask server, invoking whisper.cpp,
or calling Ollama. They verify that the rearchitecture preserves the import
surface used by scripts, operators, and future tests.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ImportContractTests(unittest.TestCase):
    def test_enterprise_package_exports_pipeline_contract(self) -> None:
        module = importlib.import_module("whisper_local.processing.pipeline")

        self.assertTrue(callable(module.run_pipeline))
        self.assertTrue(callable(module.process_text))

    def test_pipeline_sanitizes_cache_filename_segments(self) -> None:
        module = importlib.import_module("whisper_local.processing.pipeline")

        self.assertEqual(module._safe_filename("..", "fallback"), "fallback")
        self.assertEqual(module._safe_filename("../../meeting.wav", "fallback"), "meeting.wav")

        cache_folder = module._safe_cache_folder("../../meeting.wav", "fallback")
        paths = importlib.import_module("whisper_local.paths")
        cache_root = paths.CACHE_DIR.resolve()
        self.assertIn(cache_root, cache_folder.resolve().parents)

    def test_runtime_data_uses_outer_workspace_in_codebase_layout(self) -> None:
        paths = importlib.import_module("whisper_local.paths")

        self.assertEqual(paths.PROJECT_ROOT, ROOT)
        self.assertEqual(paths.RUNTIME_ROOT, ROOT.parent)
        self.assertEqual(paths.CACHE_DIR, ROOT.parent / "data" / "cache")

    def test_legacy_cache_candidates_support_pre_rearchitecture_names(self) -> None:
        module = importlib.import_module("whisper_local.processing.pipeline")

        candidates = module._legacy_cache_name_candidates("MEETING_06_15_26_-_AI.m4a")

        self.assertIn("MEETING061526-AI.m4a", candidates)

    def test_text_hash_uses_full_sha256(self) -> None:
        module = importlib.import_module("whisper_local.processing.pipeline")

        self.assertEqual(len(module._get_text_hash("hello")), 64)

    def test_enterprise_package_exports_transcriber_contracts(self) -> None:
        transcriber = importlib.import_module("whisper_local.audio.transcriber")

        self.assertTrue(callable(transcriber.transcribe))
        self.assertTrue(callable(transcriber.format_transcript))

    def test_transcriber_model_resolution_has_safe_default(self) -> None:
        transcriber = importlib.import_module("whisper_local.audio.transcriber")

        model_path = transcriber._resolve_model_path()
        self.assertTrue(model_path.name.startswith("ggml-"))
        self.assertEqual(model_path.suffix, ".bin")

    def test_enterprise_package_exports_recorder_contracts(self) -> None:
        if importlib.util.find_spec("pyaudio") is None:
            self.skipTest("PyAudio is not installed in this environment")

        recorder = importlib.import_module("whisper_local.audio.recorder")

        self.assertTrue(callable(recorder.record_audio))

    def test_legacy_cli_wrapper_still_exports_main(self) -> None:
        module = importlib.import_module("app")

        self.assertTrue(callable(module.main))

    def test_web_app_imports_without_starting_server(self) -> None:
        if importlib.util.find_spec("flask") is None:
            self.skipTest("Flask is not installed in this environment")

        module = importlib.import_module("whisper_local.web.app")

        self.assertTrue(hasattr(module, "app"))
        self.assertTrue(callable(module.get_local_ip))

    def test_web_upload_filename_validation_when_flask_available(self) -> None:
        if importlib.util.find_spec("flask") is None:
            self.skipTest("Flask is not installed in this environment")

        module = importlib.import_module("whisper_local.web.app")

        self.assertEqual(module._safe_audio_upload_name("../../meeting.m4a"), ("meeting.m4a", ".m4a"))
        with self.assertRaises(ValueError):
            module._safe_audio_upload_name("payload.exe")


if __name__ == "__main__":
    unittest.main()

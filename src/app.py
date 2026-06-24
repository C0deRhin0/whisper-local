"""Compatibility CLI entrypoint.

Existing usage remains:

    python src/app.py [audio-file]
"""

from whisper_local.cli import main


if __name__ == "__main__":
    main()

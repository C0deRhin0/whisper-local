"""Compatibility Web UI entrypoint.

Existing usage remains:

    python src/webui.py [port]
"""

from __future__ import annotations

import argparse

__all__ = ["app", "main", "run_server"]


def __getattr__(name):
    if name in {"app", "run_server"}:
        from whisper_local.web.app import app, run_server

        return {"app": app, "run_server": run_server}[name]

    raise AttributeError(f"module 'webui' has no attribute {name!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Whisper Local Web UI")
    parser.add_argument("port", nargs="?", type=int, default=8080, help="Port to bind")
    parser.add_argument("--host", default=None, help="Host to bind; defaults to 127.0.0.1")
    args = parser.parse_args()

    from whisper_local.web.app import run_server

    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

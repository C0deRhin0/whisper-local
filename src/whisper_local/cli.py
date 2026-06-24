import sys
import argparse

from whisper_local.processing.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Meeting Transcription Pipeline")
    parser.add_argument("audio_file", nargs="?", help="Path to an existing audio file (WAV)")
    parser.add_argument("--duration", type=int, default=60, help="Recording duration in seconds when no audio file is provided")
    args = parser.parse_args()

    try:
        results = run_pipeline(args.audio_file, duration=args.duration)
        print("\n" + "="*50)
        print("PIPELINE COMPLETE")
        print("="*50)
        print(f"\nSaved to: {results['output_file']}")
        print("\nSUMMARY:\n")
        print(results['summary'])
        print("\n" + "="*50)
    except Exception as e:
        print(f"Error running pipeline: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

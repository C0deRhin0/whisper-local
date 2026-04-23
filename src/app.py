import sys
import argparse
import os

# Add parent dir to PYTHONPATH so `from src.X import Y` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.pipeline import run_pipeline

def main():
    parser = argparse.ArgumentParser(description="Meeting Transcription Pipeline")
    parser.add_argument("audio_file", nargs="?", help="Path to an existing audio file (WAV)")
    args = parser.parse_args()

    try:
        results = run_pipeline(args.audio_file)
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

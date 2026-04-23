import os
import pathlib
from datetime import datetime

# Base directory
BASE_DIR = pathlib.Path(__file__).parent.parent

def save_summary(transcript: str, summary: str, output_dir: str = None) -> str:
    if output_dir is None:
        output_dir = BASE_DIR / "summaries"
    else:
        output_dir = pathlib.Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"meeting_{timestamp}.md"
    
    # Basic escaping - wrap in markdown code blocks to prevent injection
    safe_summary = f"```\n{summary}\n```" if summary else "(No summary generated)"
    safe_transcript = f"```\n{transcript}\n```" if transcript else "(No transcript)"
    
    content = f"""## Executive Summary
{safe_summary}

## Raw Transcript
{safe_transcript}
"""
    with open(filepath, 'w') as f:
        f.write(content)
        
    return str(filepath)

import requests
import json

def summarize(new_transcript: str, prior_summary: str = "", model: str = "llama3.2:3b") -> str:
    """Send transcript to local Ollama LLM for structured analysis."""
    url = "http://localhost:11434/api/generate"
    
    prompt = f"""You are an executive assistant summarizing a meeting transcript for senior leadership.
The audio is a mix of English, Tagalog, and Bicolano dialect. 
Your goal is to produce a concise, structured English summary. 

CRITICAL INSTRUCTIONS:
1. DO NOT identify or name specific individuals (e.g., do not say 'Sergiya', 'Jannick', 'Paul'). 
2. If names are mentioned in the transcript, ignore them or refer to them by their functional role if clear (e.g., 'The developer', 'The lead').
3. Focus strictly on WHAT happened and WHAT was decided.
4. Output the final summary ONLY in professional English. Translate dialect (Bikol/Tagalog) terms into professional English.
5. If the transcript is extremely short (e.g., just testing, greetings, or less than 3 sentences), do NOT use the template. Instead, provide a single-sentence summary titled "Status" (e.g., "Status: Short audio test/greeting detected.").
6. Ignore filler, repetitions, and language-specific translations.

FORMAT FOR STANDARD MEETINGS:
1. Meeting Overview (2–3 sentences)
- Purpose and overall outcome of the discussion.

2. Key Decisions
- List clear decisions made during the meeting.

3. Key Discussion Points
- Summarize important topics and technical points debated.

4. Action Items
- List specific tasks to be completed (Format: - [Task Description]). Do not assign names.

5. Risks / Issues
- Problems, blockers, or concerns raised.

6. Follow-ups / Next Steps
- What needs to happen next.

{"PREVIOUS SUMMARY TO UPDATE:" if prior_summary else ""}
{prior_summary if prior_summary else ""}

NEW TRANSCRIPT SEGMENT TO PROCESS:
{new_transcript}

Updated Senior Leadership Summary:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        return f"Error during summarization: {str(e)}"

"""
JARVIS Anticipatory Engine — Proactive Intelligence
───────────────────────────────────────────────────
Predicts user needs based on OS activity and pre-fetches
context or provides suggestions before they are requested.
"""
import json
import time
from pathlib import Path
from jarvis.api_manager import call_with_rotation

def analyze_context_and_suggest(class_name: str, title: str):
    """
    Called by daemon on window events.
    Decides if a proactive push is needed.
    """
    cl = class_name.lower()
    ti = title.lower()

    # 1. Look for patterns
    intent = None
    if "obsidian" in cl:
        intent = "The user is taking notes or planning."
    elif "code" in cl or "cursor" in cl:
        intent = "The user is developing software."
    elif "arxiv" in ti or "pubmed" in ti:
        intent = "The user is doing academic research."

    if not intent:
        return None

    # 2. Ask a fast model for a proactive suggestion
    prompt = f"User is currently using: {class_name} ({title}).\n" \
             f"Intent: {intent}\n\n" \
             f"Provide a 1-sentence proactive suggestion or data point that would be helpful. " \
             f"Example: 'I've pulled your recent notes on this topic.' or 'Should I check for code errors?'"

    messages = [{"role": "user", "content": prompt}]
    
    try:
        response = call_with_rotation(
            task="Anticipatory suggest",
            task_type="speed",
            messages=messages,
            system="You are a proactive OS partner. Be brief (1 sentence)."
        )
        
        suggestion = ""
        if hasattr(response, "content"):
            suggestion = response.content[0].text
        else:
            suggestion = str(response)
            
        return suggestion.strip()
    except Exception:
        return None

if __name__ == "__main__":
    # Test
    print(analyze_context_and_suggest("Code", "agent.py — Jarvis V2"))

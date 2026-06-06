"""
JARVIS Failure Pattern Analyzer — Self-Correction
────────────────────────────────────────────────
Autonomously analyzes task logs to identify recurring failures.
Suggests fixes for system prompts or tool logic.
"""
import json
import logging
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from jarvis.config import LOG_FILE, BASE_DIR
from jarvis.api_manager import call_with_rotation

_log = logging.getLogger(__name__)

REPORTS_DIR = BASE_DIR / "failure_reports"

def analyze_failures():
    """Identify patterns in failed tasks and suggest improvements."""
    if not REPORTS_DIR.exists():
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if not LOG_FILE.exists():
        return "No logs found to analyze."

    # 1. Collect failed or poorly rated tasks
    failures = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                data = json.loads(line)
                # Consider it a failure if success is False OR user rated it "bad"
                if not data.get("success") or data.get("user_rating") == "bad":
                    failures.append(data)
    except Exception as e:
        return f"Error reading logs: {e}"

    if len(failures) < 5:
        return "Not enough failure data for analysis yet (need 5+)."

    # 2. Group by task type or tool used
    patterns = defaultdict(list)
    for f in failures:
        # Use first tool in sequence or task_type as key
        key = f.get("task_type", "unknown")
        if f.get("tools_used"):
            key = f["tools_used"][0]
        patterns[key].append({
            "task": f["task"],
            "result": f.get("result_preview", ""),
            "error": f.get("error_msg", "Unknown error")
        })

    # 3. Analyze with high-IQ model
    analysis_input = []
    for key, examples in list(patterns.items())[:5]: # Cap to top 5 patterns
        analysis_input.append({
            "pattern_key": key,
            "count": len(examples),
            "examples": examples[-3:] # Last 3 examples
        })

    prompt = f"Analyze these recurring failure patterns in an AI system for user Dhairya: {json.dumps(analysis_input)}\n\n" \
             f"For each pattern, identify the LIKELY CAUSE (e.g., prompt ambiguity, tool timeout, model reasoning gap) " \
             f"and provide a RECOMMENDED PATCH. " \
             f"The patch should be either a specific sentence to add to the system prompt or a logic fix."

    messages = [{"role": "user", "content": prompt}]
    
    try:
        _log.info("Searching for failure clusters...")
        response = call_with_rotation(
            task="Analyze failure patterns",
            task_type="logic", # High IQ
            messages=messages,
            system="You are a system reliability engineer for an autonomous AI."
        )
        
        report = ""
        if hasattr(response, "content"):
            report = response.content[0].text
        else:
            report = str(response)

        # 4. Save report
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = REPORTS_DIR / f"failure_analysis_{ts}.md"
        report_file.write_text(report)
        
        return f"Failure analysis complete. Report saved: {report_file.name}"
    except Exception as e:
        return f"Failure analysis failed: {e}"

if __name__ == "__main__":
    print(analyze_failures())

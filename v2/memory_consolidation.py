from __future__ import annotations

import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any, List, Tuple, Optional

from config import LOG_FILE, BASE_DIR
from api_manager import call_with_rotation

_LOG = logging.getLogger(__name__)

SKILLS_DIR = BASE_DIR / "skills"


def consolidate_memory() -> str:
    """Analyze task logs to extract reusable skills and patterns.

    This function reads the log file, extracts successful tasks, identifies common
    tool sequences, and uses a high-IQ model to generate a skill description.

    Returns:
        str: Status message indicating success or failure.
    """
    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        _LOG.debug("Created skills directory: %s", SKILLS_DIR)

    if not LOG_FILE.exists():
        msg = "No logs found to consolidate."
        _LOG.warning(msg)
        return msg

    # 1. Load successful logs
    successes: List[dict[str, Any]] = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                data = json.loads(line)
                if data.get("success") and data.get("user_rating") != "bad":
                    successes.append(data)
    except Exception as e:
        msg = f"Error reading logs: {e}"
        _LOG.error(msg)
        return msg

    if len(successes) < 10:
        msg = "Not enough data for consolidation yet (need 10+ successes)."
        _LOG.info(msg)
        return msg

    # 2. Extract common tool sequences
    sequences: List[Tuple[Any, ...]] = [
        tuple(s.get("tools_used", [])) for s in successes if s.get("tools_used")
    ]
    common_seqs = Counter(sequences).most_common(3)
    _LOG.debug("Found common tool sequences: %s", common_seqs)

    # 3. Ask a high-IQ model to describe the user's patterns
    # We use a summarized sample of successes
    sample = successes[-20:]  # Last 20
    summary_data: List[dict[str, Any]] = []
    for s in sample:
        summary_data.append({
            "task": s["task"],
            "tools": s["tools_used"],
            "type": s["task_type"]
        })

    prompt = (
        f"Analyze these successful task logs for the user Dhairya: {json.dumps(summary_data)}\n\n"
        f"Identify 2-3 recurring 'Skills' or 'Workflows' this user uses often. "
        f"For each, provide a 1-sentence description and a recommended system instruction for future use."
    )

    messages = [{"role": "user", "content": prompt}]
    
    # Priority: High IQ Reasoning
    try:
        _LOG.info("[DREAM] Analyzing patterns...")
        response = call_with_rotation(
            task="Consolidate memory",
            task_type="logic",  # Use DeepSeek-R1 / SambaNova 405B
            messages=messages,
            system="You are a meta-cognitive analyst for an AI system."
        )
        
        analysis: str = ""
        if hasattr(response, "content"):
            analysis = response.content[0].text
        else:
            analysis = str(response)

        # Save analysis to skills folder
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        skill_file = SKILLS_DIR / f"consolidation_{ts}.md"
        skill_file.write_text(analysis)
        
        msg = f"Memory consolidated into {skill_file.name}"
        _LOG.info(msg)
        return msg
    except Exception as e:
        msg = f"Consolidation analysis failed: {e}"
        _LOG.error(msg)
        return msg


if __name__ == "__main__":
    print(consolidate_memory())


# Define public API
__all__: List[str] = [
    "consolidate_memory",
]
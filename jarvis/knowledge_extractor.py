"""
JARVIS Knowledge Extractor — Graph Growth
─────────────────────────────────────────
Automatically extracts entities and relations from tool outputs
and adds them to the persistent concept graph.
"""
import json
import re
from jarvis.api_manager import call_with_rotation
from jarvis.memory import add_knowledge_edge

def extract_and_add_to_graph(task: str, result: str):
    """
    Extracts knowledge triples from task results.
    Target: Subjects, Relations, Objects.
    """
    # 1. Skip very short results
    if len(result) < 100:
        return

    # 2. Fast extraction prompt
    # We use a speed-tier model (Groq/Cerebras) for this to minimize overhead
    prompt = f"Task: {task}\nResult: {result[:2000]}\n\n" \
             f"Extract 2-4 factual 'Knowledge Triples' from the result above. " \
             f"Format: Subject | Relation | Object\n" \
             f"Example: NVDA | has price | $218\n" \
             f"Example: CRISPR | is a | gene editing tool"

    messages = [{"role": "user", "content": prompt}]
    
    try:
        response = call_with_rotation(
            task="Extract knowledge",
            task_type="speed", # Fast & Cheap
            messages=messages,
            system="You are a knowledge graph extractor. Be extremely concise."
        )

        text = ""
        if hasattr(response, "content"):
            text = response.content[0].text
        else:
            text = str(response)

        # 3. Parse and add to graph
        lines = text.strip().split("\n")
        added = 0
        for line in lines:
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    s, r, o = parts[0], parts[1], parts[2]
                    # Filter out common boilerplate
                    if s.lower() not in ["subject", "none"] and len(s) < 50:
                        add_knowledge_edge(s, r, o)
                        added += 1
        
        if added:
            print(f"[GRAPH] Added {added} new knowledge edges.")

    except Exception as e:
        print(f"[GRAPH] Knowledge extraction failed: {e}")

if __name__ == "__main__":
    # Test
    extract_and_add_to_graph("What is NVDA price?", "NVIDIA Corporation (NVDA) is trading at $218.66. It is a leader in AI chips.")

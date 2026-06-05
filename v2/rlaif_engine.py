"""
JARVIS RLAIF Engine — Preference Data Generation
────────────────────────────────────────────────
Generates pairs of (Chosen, Rejected) responses for DPO training.
Uses the Critic specialist to score competing model outputs.
"""
import json
import time
from api_manager import call_with_rotation, PROVIDERS
from swarm import run_sub_agent

def generate_preference_pair(task: str):
    """Run task with two models and have Critic judge them."""
    
    # 1. Get Model A response (Primary Logic)
    resp_a = call_with_rotation(task, "logic", [{"role": "user", "content": task}])
    text_a = resp_a.content[0].text if hasattr(resp_a, "content") else str(resp_a)
    
    # 2. Get Model B response (Slightly varied or fallback)
    # We force a different provider for Model B
    resp_b = call_with_rotation(task, "logic", [{"role": "user", "content": task}], 
                               tried={"openrouter"}, temperature=0.9) # Avoid deepseek for diversity
    text_b = resp_b.content[0].text if hasattr(resp_b, "content") else str(resp_b)

    # 3. Critic Score
    critique_prompt = f"Task: {task}\n\n" \
                      f"Response A: {text_a}\n\n" \
                      f"Response B: {text_b}\n\n" \
                      f"Which response is better for the user Dhairya? " \
                      f"Explain why in 1 sentence, then output 'WINNER: A' or 'WINNER: B'."
    
    judge_res = run_sub_agent("critic", critique_prompt)
    decision = judge_res["result"]

    pair = {
        "prompt": task,
        "chosen": text_a if "WINNER: A" in decision else text_b,
        "rejected": text_b if "WINNER: A" in decision else text_a,
        "critic_reason": decision.split("WINNER:")[0].strip()
    }
    
    return pair

if __name__ == "__main__":
    print("[RLAIF] Generating preference pair...")
    p = generate_preference_pair("Explain how a transformer model works in one paragraph.")
    print(json.dumps(p, indent=2))

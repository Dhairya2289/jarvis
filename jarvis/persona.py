"""JARVIS Persona — voice tone and behavior based on time of day."""
from datetime import datetime

PERSONAS = {
    "morning": "Calm and gentle, brief updates only. Morning energy, no long explanations.",
    "working": "Efficient, no pleasantries, just results. Direct and concise.",
    "evening": "Reflective, ask about day's progress. Warm and conversational.",
    "focused": "Silent unless critical — notifications suppressed. Ultra-minimal.",
}

_OVERRIDE: str | None = None


def get_current_persona() -> str:
    """Return the active persona mode, respecting manual overrides."""
    if _OVERRIDE is not None:
        return _OVERRIDE
    hour = datetime.now().hour
    if 6 <= hour < 10:
        return "morning"
    if 10 <= hour < 18:
        return "working"
    if 18 <= hour < 22:
        return "evening"
    return "working"  # late night / default


def get_persona_text() -> str:
    """Return the description for the active persona."""
    return PERSONAS[get_current_persona()]


def set_persona(mode: str) -> None:
    """Manually override the persona mode."""
    global _OVERRIDE
    if mode not in PERSONAS:
        raise ValueError(
            f"Unknown persona mode: {mode}. Choose from {list(PERSONAS.keys())}"
        )
    _OVERRIDE = mode


def clear_persona() -> None:
    """Clear the manual override and revert to time-based persona."""
    global _OVERRIDE
    _OVERRIDE = None

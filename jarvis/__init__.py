"""JARVIS Unified — V2 + V3 merger."""

__version__ = "2.5.0"
__all__ = [
    # Core modules
    "agent", "api_manager", "config", "memory", "orchestrator", "tools",
    # V2 legacy
    "agent", "api_server", "automation_hub", "browser_agent", "clip_watcher",
    "daemon", "doctor", "failure_analyzer", "file_watcher", "jarvis_cli",
    "launch_gui", "memory_consolidation", "omniscience", "planner",
    "queue_manager", "queue_worker", "remote_control", "rlaif_engine",
    "sandbox", "semantic", "speed_ops", "swarm", "task_orchestrator",
    "telegram_bot", "test_cli", "training_pipeline", "train_jarvis",
    "tts", "vision_agent", "voice_assistant", "world_model",
    # V3 new
    "auto_dream", "background_review", "cli", "cli_workflows",
    "context_compressor", "context_engine", "coordinator", "cron_scheduler",
    "confidence", "debate", "episodic_memory", "fast_path_router",
    "gui_server", "knowledge_extractor", "life_state_manager",
    "obsidian_brain", "prompt_variants", "self_evolution",
    "session_memory", "skill_system", "vision_tool",
    # Subpackages
    "compat", "plugins",
]

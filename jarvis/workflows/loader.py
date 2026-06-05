"""
JARVIS V3 — Workflow Loader
──────────────────────────────────────────────────────────────
Load workflows from YAML files into Pydantic models.
"""

from pathlib import Path
from typing import Union

import yaml

from jarvis.workflows.schema import Workflow


def load_workflow(path: Union[str, Path]) -> Workflow:
    """Load and validate a workflow from YAML."""
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Workflow file must contain a YAML mapping: {path}")
    # Pydantic v2 handles list-of-union via model_validate
    return Workflow.model_validate(raw)

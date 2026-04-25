"""Prompt template loader for chat/rag flows."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

from src.utils.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"


@lru_cache(maxsize=256)
def load_prompt(template_path: str) -> str:
    """Load raw prompt template text from src/rag/prompts."""
    target = (_PROMPTS_ROOT / template_path).resolve()
    if not str(target).startswith(str(_PROMPTS_ROOT.resolve())):
        raise ValueError(f"Prompt path escapes prompts root: {template_path}")
    if not target.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    return target.read_text(encoding="utf-8")


def render_prompt(template_path: str, **variables: object) -> str:
    """Render prompt template with string.Template substitution."""
    raw = load_prompt(template_path)
    normalized = {key: "" if value is None else str(value) for key, value in variables.items()}
    try:
        return Template(raw).safe_substitute(**normalized)
    except Exception:
        logger.error("Failed to render prompt template '%s'", template_path, exc_info=True)
        raise

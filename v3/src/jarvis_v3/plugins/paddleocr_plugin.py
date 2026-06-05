"""PaddleOCR integration plugin for JARVIS V3.

Provides image-to-text extraction via PaddleOCR.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def _lazy_ocr() -> Any:
    try:
        from paddleocr import PaddleOCR
        return PaddleOCR(use_angle_cls=True, lang="en")
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR is not installed. Run: pip install paddleocr"
        ) from exc


_ocr: Any = None


def _get_ocr() -> Any:
    global _ocr
    if _ocr is None:
        _ocr = _lazy_ocr()
    return _ocr


def extract_text(image_path: str | Path) -> str:
    """Extract text from an image using PaddleOCR.

    Args:
        image_path: Path to an image file.

    Returns:
        Concatenated text with newlines.
    """
    ocr = _get_ocr()
    path = str(Path(image_path).expanduser())
    _log.info("Running PaddleOCR on %s", path)
    try:
        result = ocr.ocr(path, cls=True)
    except Exception as exc:
        _log.error("PaddleOCR failed: %s", exc, exc_info=True)
        return f"[OCR ERROR] {exc}"

    lines: list[str] = []
    if result and result[0]:
        for line in result[0]:
            if line:
                text = line[1][0] if len(line) > 1 else str(line)
                lines.append(text)
    return "\n".join(lines)


__all__ = ["extract_text"]

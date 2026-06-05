"""
JARVIS V3 — Vision Tool
──────────────────────────────────────────────────────────────
Send a PIL Image to a vision-capable model and get a text answer.
Uses the async ApiManager with task_type='vision' for optimal routing.
"""

import asyncio
from io import BytesIO
from typing import Optional

from PIL import Image

from jarvis.api_manager import get_manager
from jarvis.screen_region import image_to_base64


async def ask_about_image(
    image: Image.Image,
    question: str = "What do you see in this image?",
    task_type: str = "vision",
) -> str:
    """
    Send a PIL Image to the vision model and return the answer.
    """
    b64_uri = image_to_base64(image, fmt="PNG")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {
                    "type": "image_url",
                    "image_url": {"url": b64_uri},
                },
            ],
        }
    ]

    mgr = await get_manager()
    async with mgr:
        response = await mgr.call(
            task=question,
            task_type=task_type,
            messages=messages,
            system="You are a vision assistant. Describe what you see concisely.",
            max_tokens=2048,
        )

    # Extract text from response
    texts = [c for c in response.content if getattr(c, "type", None) == "text"]
    if texts:
        return texts[0].text.strip()
    return "[VISION] No text response from model."


async def capture_and_ask(
    question: str = "What do you see?",
    region: Optional[tuple] = None,
) -> str:
    """
    Capture screen (full or region) and ask the vision model about it.
    region = (left, top, width, height) or None for full screen.
    """
    from jarvis.screen_region import capture_region, capture_full

    if region:
        img = capture_region(*region)
    else:
        img = capture_full()
    return await ask_about_image(img, question)

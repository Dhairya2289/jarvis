"""
Tests for jarvis_v3.screen_region and jarvis_v3.vision_tool
"""

from io import BytesIO
from unittest.mock import patch, AsyncMock

import pytest
from PIL import Image

from jarvis_v3.screen_region import image_to_base64, base64_to_image


class TestImageHelpers:
    def test_image_to_base64_roundtrip(self):
        img = Image.new("RGB", (10, 10), color="red")
        b64 = image_to_base64(img, fmt="PNG")
        assert b64.startswith("data:image/png;base64,")
        img2 = base64_to_image(b64)
        assert img2.size == (10, 10)

    def test_base64_to_image_without_prefix(self):
        import base64
        img = Image.new("RGB", (5, 5), color="blue")
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        img2 = base64_to_image(b64)
        assert img2.size == (5, 5)


class TestVisionTool:
    @patch("jarvis_v3.vision_tool.get_manager")
    @patch("jarvis_v3.vision_tool.image_to_base64")
    def test_ask_about_image(self, mock_b64, mock_get_mgr):
        import asyncio
        from jarvis_v3.vision_tool import ask_about_image
        mock_b64.return_value = "data:image/png;base64,test"

        class FakeContent:
            type = "text"
            text = "I see a red square."

        class FakeResponse:
            content = [FakeContent()]

        class FakeMgr:
            async def call(self, **kwargs):
                return FakeResponse()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return None

        async def fake_get_manager():
            return FakeMgr()

        mock_get_mgr.side_effect = fake_get_manager

        img = Image.new("RGB", (10, 10), color="red")
        result = asyncio.run(ask_about_image(img, "What do you see?"))
        assert result == "I see a red square."

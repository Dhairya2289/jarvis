"""JARVIS Desktop Orchestration — chunk 5.

Exports all desktop modules for convenient access.
"""

from jarvis.desktop.workspace_memory import WorkspaceMemory
from jarvis.desktop.smart_launcher import SmartLauncher, smart_launch
from jarvis.desktop.clipboard_history import ClipboardHistory
from jarvis.desktop.notification_triage import (
    NotificationTriage,
    NotificationEntry,
    classify_notification,
    triage_notifications,
)
from jarvis.desktop.screenshot_manager import ScreenshotManager
from jarvis.desktop.window_logger import WindowLogger, WindowEvent

__all__ = [
    "WorkspaceMemory",
    "SmartLauncher",
    "smart_launch",
    "ClipboardHistory",
    "NotificationTriage",
    "NotificationEntry",
    "classify_notification",
    "triage_notifications",
    "ScreenshotManager",
    "WindowLogger",
    "WindowEvent",
]
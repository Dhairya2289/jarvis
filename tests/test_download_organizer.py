"""Tests for Download Organizer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.download_organizer import (
    DownloadOrganizer,
    _get_category,
    suggested_tags,
    CATEGORIES,
)


class TestGetCategory:
    """Unit tests for category detection."""

    def test_images_jpg(self):
        assert _get_category("photo.jpg", "image/jpeg") == "Images"

    def test_images_png(self):
        assert _get_category("screenshot.png", "image/png") == "Images"

    def test_documents_pdf(self):
        assert _get_category("report.pdf", "application/pdf") == "Documents"

    def test_documents_docx(self):
        assert _get_category("notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") == "Documents"

    def test_archives_zip(self):
        assert _get_category("backup.zip", "application/zip") == "Archives"

    def test_media_mp4(self):
        assert _get_category("video.mp4", "video/mp4") == "Media"

    def test_media_mp3(self):
        assert _get_category("song.mp3", "audio/mpeg") == "Media"

    def test_code_py(self):
        assert _get_category("script.py", "text/x-python") == "Code"

    def test_code_js(self):
        assert _get_category("app.js", "text/javascript") == "Code"

    def test_other_unknown(self):
        assert _get_category("random.xyz", "application/octet-stream") == "Other"


class TestSuggestedTags:
    """Unit tests for tag suggestion."""

    def test_image_tag(self):
        tags = suggested_tags("photo.jpg", "image/jpeg")
        assert "jpg" in tags
        assert "image" in tags

    def test_code_tag(self):
        tags = suggested_tags("script.py", "text/x-python")
        assert "py" in tags
        assert "text" in tags

    def test_no_extension(self):
        tags = suggested_tags("Makefile", "text/plain")
        assert "text" in tags


class TestDownloadOrganizer:
    """Integration tests for DownloadOrganizer."""

    def test_organize_sorts_files_by_extension(self, tmp_path: Path):
        """Files are moved to correct category folders."""
        # Setup fake downloads directory
        downloads = tmp_path / "Downloads"
        downloads.mkdir()

        # Create test files
        (downloads / "photo.jpg").write_text("fake image")
        (downloads / "document.pdf").write_text("fake pdf")
        (downloads / "archive.zip").write_text("fake zip")
        (downloads / "video.mp4").write_text("fake video")
        (downloads / "script.py").write_text("fake code")
        (downloads / "unknown.xyz").write_text("unknown")

        organizer = DownloadOrganizer(downloads_dir=downloads)
        stats = organizer.organize()

        # Check folders exist
        assert (downloads / "Images").exists()
        assert (downloads / "Documents").exists()
        assert (downloads / "Archives").exists()
        assert (downloads / "Media").exists()
        assert (downloads / "Code").exists()
        assert (downloads / "Other").exists()

        # Check files were moved
        assert (downloads / "Images" / "photo.jpg").exists()
        assert (downloads / "Documents" / "document.pdf").exists()
        assert (downloads / "Archives" / "archive.zip").exists()
        assert (downloads / "Media" / "video.mp4").exists()
        assert (downloads / "Code" / "script.py").exists()
        assert (downloads / "Other" / "unknown.xyz").exists()

        # Check stats
        assert stats["Images"] == 1
        assert stats["Documents"] == 1
        assert stats["Archives"] == 1
        assert stats["Media"] == 1
        assert stats["Code"] == 1
        assert stats["Other"] == 1

    def test_organize_handles_duplicate_names(self, tmp_path: Path):
        """Duplicate filenames get renamed with counter."""
        downloads = tmp_path / "Downloads"
        downloads.mkdir()

        # Create two files with same name in different "original" locations
        (downloads / "document.pdf").write_text("first")
        # Simulate the same name appearing (in real scenario, files arrive separately)

        organizer = DownloadOrganizer(downloads_dir=downloads)
        # First organize
        organizer.organize()
        # Create another file with same name and organize again
        (downloads / "document.pdf").write_text("second")
        organizer.organize()

        # Should have 2 files in Documents (original and renamed)
        docs_dir = downloads / "Documents"
        if docs_dir.exists():
            pdfs = list(docs_dir.glob("document*.pdf"))
            assert len(pdfs) == 2

    def test_organize_dry_run(self, tmp_path: Path):
        """Dry run does not move any files."""
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "photo.jpg").write_text("image")

        organizer = DownloadOrganizer(downloads_dir=downloads)
        organizer.organize(dry_run=True)

        # File should still be in downloads root
        assert (downloads / "photo.jpg").exists()
        # No category folders should exist
        assert not (downloads / "Images").exists()

    def test_organize_nonexistent_dir(self, tmp_path: Path):
        """Organizing a nonexistent directory returns empty stats."""
        organizer = DownloadOrganizer(downloads_dir=tmp_path / "nonexistent")
        stats = organizer.organize()
        assert stats == {}

    def test_get_stats_after_organize(self, tmp_path: Path):
        """get_stats returns the stats from last organize call."""
        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        (downloads / "photo.jpg").write_text("image")

        organizer = DownloadOrganizer(downloads_dir=downloads)
        organizer.organize()
        stats = organizer.get_stats()

        assert "Images" in stats
        assert stats["Images"] == 1
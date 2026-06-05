"""Tests for desktop app discovery."""
from __future__ import annotations

import pytest
from jarvis.apps.desktop import DesktopApp, _parse_desktop_file, list_apps, search_apps


class TestParseDesktopFile:
    def test_parses_valid_app(self, tmp_path: Path):
        f = tmp_path / "test.desktop"
        f.write_text(
            "[Desktop Entry]\n"
            "Name=TestApp\n"
            "Exec=/usr/bin/testapp %f\n"
            "Icon=testapp\n"
            "Type=Application\n"
            "Categories=Utility;\n"
            "Comment=A test app\n"
        )
        app = _parse_desktop_file(f)
        assert app is not None
        assert app.name == "TestApp"
        assert app.exec == "/usr/bin/testapp"
        assert app.icon == "testapp"
        assert "Utility" in app.categories
        assert app.comment == "A test app"

    def test_skips_no_display(self, tmp_path: Path):
        f = tmp_path / "hidden.desktop"
        f.write_text(
            "[Desktop Entry]\nName=Hidden\nExec=/bin/hidden\nNoDisplay=true\n"
        )
        assert _parse_desktop_file(f) is None

    def test_skips_non_application(self, tmp_path: Path):
        f = tmp_path / "link.desktop"
        f.write_text(
            "[Desktop Entry]\nName=Link\nExec=/bin/lnk\nType=Link\n"
        )
        assert _parse_desktop_file(f) is None


class TestListApps:
    def test_returns_apps(self):
        apps = list_apps()
        assert isinstance(apps, list)
        assert len(apps) > 0
        names = [a.name for a in apps]
        assert len(names) == len(set(names))  # no duplicates
        assert all(a.exec for a in apps)


class TestSearchApps:
    def test_search_by_name(self):
        results = search_apps("terminal")
        assert isinstance(results, list)

    def test_search_no_match(self):
        results = search_apps("xyznonexistent")
        assert results == []

"""Persistent user preferences (window layout, theme). The desktop stand-in for localStorage."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from . import APP_NAME, ORGANIZATION

#: Bump when docks are added, removed or renamed so stale layouts are ignored.
LAYOUT_VERSION = 1


class Settings:
    def __init__(self, backend: QSettings | None = None) -> None:
        self._backend = backend or QSettings(ORGANIZATION, APP_NAME)

    @classmethod
    def ephemeral(cls) -> "Settings":
        """Settings stored in a throw-away file: nothing is read from or written to the user's profile."""
        path = Path(tempfile.mkdtemp(prefix="hdd-studio-settings-")) / "settings.ini"
        return cls(QSettings(str(path), QSettings.Format.IniFormat))

    # ------------------------------------------------------------------- theme
    def theme_mode(self) -> str:
        value = self._backend.value("ui/theme", "system")
        return value if value in ("system", "light", "dark") else "system"

    def set_theme_mode(self, mode: str) -> None:
        self._backend.setValue("ui/theme", mode)

    # -------------------------------------------------------------- workspaces
    def last_workspace(self) -> str | None:
        value = self._backend.value("workspace/last")
        return value if isinstance(value, str) and value else None

    def recent_workspaces(self) -> list[str]:
        value = self._backend.value("workspace/recent", [])
        if isinstance(value, str):
            value = [value]
        return [v for v in (value or []) if isinstance(v, str)]

    def remember_workspace(self, path: str) -> None:
        recent = [path] + [p for p in self.recent_workspaces() if p != path]
        self._backend.setValue("workspace/recent", recent[:8])
        self._backend.setValue("workspace/last", path)
        self._backend.sync()

    # ------------------------------------------------------------------ layout
    def window_geometry(self) -> QByteArray | None:
        return self._bytes("window/geometry")

    def window_state(self) -> QByteArray | None:
        return self._bytes("window/state")

    def save_window(self, geometry: QByteArray, state: QByteArray) -> None:
        self._backend.setValue("window/geometry", geometry)
        self._backend.setValue("window/state", state)
        self._backend.sync()

    def bottom_panel(self) -> tuple[bool, int | None]:
        """``(collapsed, expanded height)`` of the bottom panel at the last close."""
        collapsed = str(self._backend.value("window/bottom_collapsed", "false")).lower() == "true"
        try:
            height = int(self._backend.value("window/bottom_height", 0)) or None
        except (TypeError, ValueError):
            height = None
        return collapsed, height

    def save_bottom_panel(self, collapsed: bool, height: int) -> None:
        self._backend.setValue("window/bottom_collapsed", "true" if collapsed else "false")
        self._backend.setValue("window/bottom_height", int(height))
        self._backend.sync()

    def _bytes(self, key: str) -> QByteArray | None:
        value = self._backend.value(key)
        return value if isinstance(value, QByteArray) and not value.isEmpty() else None

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

    # ------------------------------------------------------------------ layout
    def window_geometry(self) -> QByteArray | None:
        return self._bytes("window/geometry")

    def window_state(self) -> QByteArray | None:
        return self._bytes("window/state")

    def save_window(self, geometry: QByteArray, state: QByteArray) -> None:
        self._backend.setValue("window/geometry", geometry)
        self._backend.setValue("window/state", state)
        self._backend.sync()

    def _bytes(self, key: str) -> QByteArray | None:
        value = self._backend.value(key)
        return value if isinstance(value, QByteArray) and not value.isEmpty() else None

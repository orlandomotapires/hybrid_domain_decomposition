"""Theme: applies design tokens to the running application.

One ``Theme`` exists per application. It owns the palette, the fonts, the
generated style sheet and the icon cache, and re-applies all of them when the
user (or the system) switches between light and dark.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import weakref
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

from . import icons as _icons
from .qss import GLYPH_NAMES, build_stylesheet
from .tokens import DARK, LIGHT, THEMES, Tokens

MODES = ("system", "light", "dark")

__all__ = ["MODES", "Theme", "Tokens", "LIGHT", "DARK", "THEMES"]


def build_palette(tokens: Tokens) -> QPalette:
    c = tokens.colors
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    palette = QPalette()
    for color_role, value in (
        (role.Window, c.panel),
        (role.WindowText, c.text),
        (role.Base, c.base),
        (role.AlternateBase, c.base_alt),
        (role.Text, c.text),
        (role.Button, c.base if not tokens.is_dark else c.panel),
        (role.ButtonText, c.text),
        (role.BrightText, "#FFFFFF"),
        (role.Highlight, c.accent),
        (role.HighlightedText, c.accent_text),
        (role.Accent, c.accent),
        (role.ToolTipBase, c.menu),
        (role.ToolTipText, c.text),
        (role.PlaceholderText, c.text_disabled),
        (role.Link, c.accent_fg),
        (role.LinkVisited, c.accent_fg),
        (role.Light, c.base),
        (role.Midlight, c.panel),
        (role.Mid, c.border),
        (role.Dark, c.border_strong),
        (role.Shadow, c.border_strong),
    ):
        palette.setColor(color_role, QColor(value))
    for color_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, color_role, QColor(c.text_disabled))
    palette.setColor(group.Disabled, role.Highlight, QColor(c.selection_inactive))
    palette.setColor(group.Disabled, role.HighlightedText, QColor(c.text_disabled))
    return palette


class Theme(QObject):
    """Applies tokens to the application and hands out themed fonts and icons."""

    changed = Signal()

    _instance: "Theme | None" = None

    def __init__(self, app: QApplication, mode: str = "system") -> None:
        super().__init__(app)
        Theme._instance = self
        self._app = app
        self._mode = "system"
        self._tokens: Tokens = LIGHT
        self._icon_cache: dict[tuple[str, str, str], QIcon] = {}
        self._bound: list[tuple[weakref.ref, str, str]] = []
        self._glyph_root = Path(tempfile.mkdtemp(prefix="hdd-studio-theme-"))
        self._glyph_sets: dict[str, dict[str, str]] = {}
        atexit.register(shutil.rmtree, self._glyph_root, True)

        general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
        fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._ui_family = os.environ.get("HDD_STUDIO_FONT") or general.family()
        self._mono_family = os.environ.get("HDD_STUDIO_MONO_FONT") or fixed.family()

        app.setStyle("Fusion")
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        self.apply(mode)

    # ------------------------------------------------------------------ access
    @classmethod
    def instance(cls) -> "Theme":
        if cls._instance is None:
            raise RuntimeError("Theme has not been created yet")
        return cls._instance

    @property
    def tokens(self) -> Tokens:
        return self._tokens

    @property
    def mode(self) -> str:
        """The requested mode: ``system``, ``light`` or ``dark``."""
        return self._mode

    # ------------------------------------------------------------------- apply
    def apply(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown theme mode: {mode!r}")
        self._mode = mode
        self._tokens = self._resolve(mode)
        self._app.setPalette(build_palette(self._tokens))
        self._app.setFont(self.ui_font())
        self._app.setStyleSheet(build_stylesheet(self._tokens, self._glyphs(self._tokens)))
        self._icon_cache.clear()
        self._rebind_icons()
        self.changed.emit()

    def _resolve(self, mode: str) -> Tokens:
        if mode == "system":
            scheme = self._app.styleHints().colorScheme()
            return DARK if scheme == Qt.ColorScheme.Dark else LIGHT
        return THEMES[mode]

    def _on_system_scheme_changed(self, *_args) -> None:
        if self._mode == "system":
            self.apply("system")

    # ------------------------------------------------------------------- fonts
    def ui_font(self, *, small: bool = False, semibold: bool = False) -> QFont:
        font = QFont(self._ui_family)
        font.setPointSizeF(self._tokens.type.small_pt if small else self._tokens.type.base_pt)
        if semibold:
            font.setWeight(QFont.Weight.DemiBold)
        return font

    def mono_font(self) -> QFont:
        font = QFont(self._mono_family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSizeF(self._tokens.type.base_pt)
        return font

    def numeric_font(self) -> QFont:
        """UI font with tabular figures, for columns of numbers."""
        font = self.ui_font()
        font.setFeature(QFont.Tag("tnum"), 1)
        return font

    # ------------------------------------------------------------------- icons
    def color(self, role: str) -> str:
        """Token colour for an icon/ink role (``default``, ``muted``, ``accent``, ``ok``...)."""
        c = self._tokens.colors
        return {
            "default": c.icon,
            "muted": c.text_muted,
            "disabled": c.text_disabled,
            "accent": c.accent_fg,
            "on_accent": c.accent_text,
            "ok": c.ok,
            "warning": c.warn,
            "error": c.error,
            "info": c.info,
        }[role]

    def icon(self, name: str, role: str = "default") -> QIcon:
        key = (self._tokens.name, name, role)
        icon = self._icon_cache.get(key)
        if icon is None:
            icon = _icons.build_icon(
                _icons.ICONS[name],
                self.color(role),
                self._tokens.colors.text_disabled,
                self._tokens.metrics.icon_stroke,
            )
            self._icon_cache[key] = icon
        return icon

    def pixmap(self, name: str, size: int, role: str = "default", dpr: float = 1.0) -> QPixmap:
        svg = _icons.svg_source(_icons.ICONS[name], self.color(role), self._tokens.metrics.icon_stroke)
        return _icons.render_pixmap(svg, size, dpr)

    def bind_icon(self, target: QObject, name: str, role: str = "default") -> None:
        """Set ``target``'s icon now and again whenever the theme changes."""
        target.setIcon(self.icon(name, role))
        self._bound.append((weakref.ref(target), name, role))

    def _rebind_icons(self) -> None:
        alive = []
        for ref, name, role in self._bound:
            target = ref()
            if target is None:
                continue
            try:
                target.setIcon(self.icon(name, role))
            except RuntimeError:  # underlying C++ object already deleted
                continue
            alive.append((ref, name, role))
        self._bound = alive

    # ------------------------------------------------------------------ glyphs
    def _glyphs(self, tokens: Tokens) -> dict[str, str]:
        """Write the small recoloured SVGs the style sheet references; return their paths."""
        cached = self._glyph_sets.get(tokens.name)
        if cached is not None:
            return cached
        c = tokens.colors
        sources = {
            "chevron_down": _icons.svg_source("chevron-down", c.text_muted, 2, 12),
            "chevron_right": _icons.svg_source("chevron-right", c.text_muted, 2, 12),
            "caret_up": _icons.caret_svg("up", c.text_muted),
            "caret_down": _icons.caret_svg("down", c.text_muted),
            "check": _icons.svg_source("check", c.text, 2.25, 14),
            "check_on_accent": _icons.svg_source("check", c.accent_text, 3, 11),
            "radio_dot": _icons.dot_svg(c.accent if not tokens.is_dark else c.accent_fg),
        }
        directory = self._glyph_root / tokens.name
        directory.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name in GLYPH_NAMES:
            path = directory / f"{name}.svg"
            path.write_text(sources[name], encoding="utf-8")
            paths[name] = str(path)
        self._glyph_sets[tokens.name] = paths
        return paths

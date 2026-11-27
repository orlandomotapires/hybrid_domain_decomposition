"""SVG icons, recoloured from design tokens.

The icon files are Tabler Icons (MIT, see ``resources/icons/LICENSE-tabler-icons.txt``).
Code refers to icons by a semantic name (``"run"``, ``"coarsening"``) so the
drawing behind a concept can change in one place.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "resources" / "icons"

#: semantic name -> SVG file stem in ``ICON_DIR``
ICONS: dict[str, str] = {
    # actions
    "new": "file-plus",
    "open": "folder-open",
    "save": "device-floppy",
    "undo": "arrow-back-up",
    "redo": "arrow-forward-up",
    "run": "player-play",
    "stop": "player-stop",
    "validate": "circle-check",
    "compare": "arrows-diff",
    "import": "file-import",
    "export": "download",
    "copy": "copy",
    "delete": "trash",
    "rename": "pencil",
    "refresh": "refresh",
    "search": "search",
    "filter": "filter",
    "close": "x",
    "add": "plus",
    "remove": "minus",
    "settings": "settings",
    "external": "external-link",
    "float": "maximize",
    "follow": "arrow-bar-to-down",
    "expanded": "chevron-down",
    "collapsed": "chevron-right",
    "panel-expand": "chevron-up",
    "panel-collapse": "chevron-down",
    # project tree
    "workspace": "box",
    "matrices": "database",
    "matrix": "grid-dots",
    "simulations": "flask",
    "simulation": "flask",
    "coarsening": "stack-2",
    "partitioning": "category",
    "refinement": "adjustments",
    "outputs": "file-export",
    "presets": "bookmarks",
    "tuning": "adjustments-horizontal",
    "study": "chart-dots",
    "results": "chart-line",
    "result": "file-text",
    "batch": "list-details",
    "history": "history",
    "hardware": "cpu",
    "folder": "folder",
    "file": "file",
    # panels and views
    "console": "terminal-2",
    "jobs": "list",
    "problems": "alert-triangle",
    "help": "help-circle",
    "docs": "book-2",
    "sparsity": "grid-dots",
    "curve": "chart-line",
    "scatter": "chart-scatter",
    "table": "table",
    "json": "braces",
    "image": "photo",
    "fit": "zoom-reset",
    "zoom_in": "zoom-in",
    # state
    "ok": "circle-check",
    "error": "circle-x",
    "warning": "alert-triangle",
    "info": "info-circle",
    "running": "player-play",
    "pending": "clock",
    "cancelled": "circle-dot",
    # theme
    "theme": "contrast",
    "theme_light": "sun",
    "theme_dark": "moon",
}

_CARET = '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 8 8"><path d="{d}" fill="{color}"/></svg>'
_DOT = '<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 13 13"><circle cx="6.5" cy="6.5" r="3" fill="{color}"/></svg>'


def svg_source(stem: str, color: str, stroke: float, size: int | None = None) -> str:
    """Return the SVG text of icon file ``stem`` drawn in ``color``."""
    text = (ICON_DIR / f"{stem}.svg").read_text(encoding="utf-8")
    text = text.replace('stroke="currentColor"', f'stroke="{color}"')
    text = text.replace('stroke-width="2"', f'stroke-width="{stroke:g}"')
    if size is not None:
        text = re.sub(r'width="24"', f'width="{size}"', text, count=1)
        text = re.sub(r'height="24"', f'height="{size}"', text, count=1)
    return text


def caret_svg(direction: str, color: str) -> str:
    path = "M1 5.5 L4 2.5 L7 5.5 Z" if direction == "up" else "M1 2.5 L4 5.5 L7 2.5 Z"
    return _CARET.format(d=path, color=color)


def dot_svg(color: str) -> str:
    return _DOT.format(color=color)


def render_pixmap(svg: str, size: int, dpr: float = 1.0) -> QPixmap:
    """Rasterise SVG text into a ``size`` x ``size`` logical-pixel pixmap."""
    pixels = max(1, round(size * dpr))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode("utf-8"))).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def build_icon(stem: str, color: str, disabled_color: str, stroke: float) -> QIcon:
    """Build a multi-resolution icon with normal and disabled variants."""
    icon = QIcon()
    normal = svg_source(stem, color, stroke)
    disabled = svg_source(stem, disabled_color, stroke)
    for size in (16, 20, 24):
        for dpr in (1.0, 2.0):
            icon.addPixmap(render_pixmap(normal, size, dpr), QIcon.Mode.Normal)
            icon.addPixmap(render_pixmap(disabled, size, dpr), QIcon.Mode.Disabled)
    return icon

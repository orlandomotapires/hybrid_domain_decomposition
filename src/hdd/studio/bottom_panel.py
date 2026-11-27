"""Collapse the tabbed bottom panels (Console, Jobs, Problems) to their row of tabs, and back.

Collapsed, only the tabs stay on screen and the graphics area above takes the room. Clicking a tab,
the chevron at the right end of the tab row, View > Bottom panel or Ctrl+J expands the panel again
to the height it had. A panel the user moved elsewhere (floated, docked on a side) is left alone.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDockWidget, QMainWindow, QTabBar, QToolButton

from .theme import Theme

MIN_EXPANDED_HEIGHT = 60  # a smaller panel is treated as collapsed and its height is not remembered
_UNLIMITED = 16777215  # QWIDGETSIZE_MAX


class BottomPanel(QObject):
    """Collapse and expand the docks that sit in the main window's bottom area."""

    collapsedChanged = Signal(bool)

    def __init__(self, window: QMainWindow, docks: list[QDockWidget], height: int = 230) -> None:
        super().__init__(window)
        self._window = window
        self._docks = docks
        self._collapsed = False
        self._height = height
        self._bar: QTabBar | None = None

        self.action = QAction("&Bottom panel", window)
        self.action.setCheckable(True)
        self.action.setChecked(True)
        self.action.setShortcut(QKeySequence("Ctrl+J"))
        self.action.setToolTip("Show or collapse the Console, Jobs and Problems panel (Ctrl+J)")
        self.action.triggered.connect(lambda checked: self.expand() if checked else self.collapse())

        # Owned by the window, not the tab bar: Qt deletes and recreates the tab bar when docks move.
        self.button = QToolButton(window)
        self.button.setObjectName("BottomPanelToggle")
        self.button.setAutoRaise(True)
        self.button.setFixedSize(28, 24)
        self.button.clicked.connect(self.toggle)
        self.button.hide()
        self._update_button()
        Theme.instance().changed.connect(self._update_button)

    # ------------------------------------------------------------ state
    def is_collapsed(self) -> bool:
        return self._collapsed

    def height(self) -> int:
        """Height the panel has (or will have again) when expanded."""
        return self._height

    def toggle(self) -> None:
        if self._collapsed:
            self.expand()
        else:
            self.collapse()

    def collapse(self) -> None:
        docked = self._docked()
        if self._collapsed or not docked:
            return
        current = docked[0].height()
        if current >= MIN_EXPANDED_HEIGHT:
            self._height = current
        for dock in docked:
            dock.widget().setMinimumHeight(0)
            dock.widget().setMaximumHeight(0)
        self._window.resizeDocks([docked[0]], [1], Qt.Orientation.Vertical)
        self._set_collapsed(True)

    def expand(self, dock: QDockWidget | None = None) -> None:
        """Expand to the last height; ``dock`` becomes the visible tab (it is shown if it was closed)."""
        if dock is not None:
            dock.show()
            dock.raise_()
        if not self._collapsed:
            return
        for each in self._docks:
            each.widget().setMaximumHeight(_UNLIMITED)
        docked = self._docked()
        if docked:
            target = dock if dock in docked else docked[0]
            self._window.resizeDocks([target], [self._height], Qt.Orientation.Vertical)
        self._set_collapsed(False)

    def set_height(self, height: int) -> None:
        self._height = max(MIN_EXPANDED_HEIGHT, int(height))

    def _set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.action.setChecked(not collapsed)
        self._update_button()
        self.collapsedChanged.emit(collapsed)

    def _docked(self) -> list[QDockWidget]:
        """Open panels docked in the bottom area, the one on screen (the current tab) first."""
        bottom = Qt.DockWidgetArea.BottomDockWidgetArea
        docked = [d for d in self._docks
                  if d.toggleViewAction().isChecked() and not d.isFloating() and self._window.dockWidgetArea(d) == bottom]
        return sorted(docked, key=lambda d: not d.isVisible())

    # ------------------------------------------------------------ tab row
    def sync(self) -> None:
        """Find the tab row of the bottom panels (Qt recreates it when docks move) and attach to it."""
        names = {dock.windowTitle().split(" (")[0] for dock in self._docks}
        bar = None
        for candidate in self._window.findChildren(QTabBar):
            if candidate.parent() is not self._window or not candidate.isVisible():
                continue
            titles = {candidate.tabText(i).split(" (")[0] for i in range(candidate.count())}
            if titles & names:
                bar = candidate
                if not candidate.property("hddBottomPanelHooked"):
                    candidate.setProperty("hddBottomPanelHooked", True)
                    candidate.tabBarClicked.connect(self._tab_clicked)
                    candidate.installEventFilter(self)
                break
        self._bar = bar
        self._place_button()

    def _tab_clicked(self, _index: int) -> None:
        if self._collapsed:
            self.expand()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._bar and event.type() in (QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide):
            self._place_button()
        return False

    def _place_button(self) -> None:
        """Keep the chevron at the right end of the tab row; hide it when there is no row."""
        bar = self._bar
        try:
            visible = bar is not None and bar.isVisible()
        except RuntimeError:  # the tab bar was deleted since the last sync
            self._bar, visible = None, False
        if not visible:
            self.button.hide()
            return
        geometry = bar.geometry()
        self.button.move(geometry.right() - self.button.width() - 4,
                         geometry.top() + max(0, (geometry.height() - self.button.height()) // 2))
        self.button.show()
        self.button.raise_()

    def _update_button(self) -> None:
        icon = "panel-expand" if self._collapsed else "panel-collapse"
        self.button.setIcon(Theme.instance().icon(icon, "muted"))
        self.button.setToolTip(("Expand" if self._collapsed else "Collapse") + " the panel (Ctrl+J)")

"""Console: a levelled log view with filter, search and follow-tail."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QGuiApplication, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget

from ..theme import Theme

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
_RANK = {level: rank for rank, level in enumerate(LEVELS)}


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    level: str
    message: str


class LogView(QPlainTextEdit):
    """Read-only log text. Keeps the entries so filters and theme changes can re-render."""

    def __init__(self, parent: QWidget | None = None, max_entries: int = 20000) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setUndoRedoEnabled(False)
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._min_rank = 0
        self._needle = ""
        self._follow = True
        Theme.instance().changed.connect(self._render)
        self.setFont(Theme.instance().mono_font())

    # ------------------------------------------------------------------- input
    def append_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self._matches(entry):
            self._write(entry)
            if self._follow:
                self._scroll_to_end()

    def clear_entries(self) -> None:
        self._entries.clear()
        self.clear()

    # ----------------------------------------------------------------- filters
    def set_minimum_level(self, level: str) -> None:
        self._min_rank = _RANK[level]
        self._render()

    def set_search(self, text: str) -> None:
        self._needle = text.strip().lower()
        self._render()

    def set_follow(self, follow: bool) -> None:
        self._follow = follow
        if follow:
            self._scroll_to_end()

    def visible_text(self) -> str:
        return self.toPlainText()

    def visible_count(self) -> int:
        return sum(1 for entry in self._entries if self._matches(entry))

    # ---------------------------------------------------------------- internal
    def _matches(self, entry: LogEntry) -> bool:
        if _RANK.get(entry.level, 1) < self._min_rank:
            return False
        return not self._needle or self._needle in entry.message.lower()

    def _formats(self) -> dict[str, QTextCharFormat]:
        colors = Theme.instance().tokens.colors
        result = {}
        for key, value in (
            ("time", colors.text_muted),
            ("DEBUG", colors.text_muted),
            ("INFO", colors.text),
            ("WARNING", colors.warn),
            ("ERROR", colors.error),
        ):
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(value))
            result[key] = text_format
        return result

    def _write(self, entry: LogEntry, formats: dict[str, QTextCharFormat] | None = None) -> None:
        formats = formats or self._formats()
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self.document().isEmpty():
            cursor.insertBlock()
        level_format = formats.get(entry.level, formats["INFO"])
        cursor.insertText(f"{entry.timestamp}  ", formats["time"])
        cursor.insertText(f"{entry.level:<7}  ", level_format)
        cursor.insertText(entry.message, level_format if entry.level in ("WARNING", "ERROR") else formats["INFO"])

    def _render(self) -> None:
        self.setFont(Theme.instance().mono_font())
        self.clear()
        formats = self._formats()
        for entry in self._entries:
            if self._matches(entry):
                self._write(entry, formats)
        if self._follow:
            self._scroll_to_end()

    def _scroll_to_end(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())


class ConsolePanel(QWidget):
    """Log view plus its tool row."""

    FILTERS = (
        ("All levels", "DEBUG"),
        ("Info and above", "INFO"),
        ("Warnings and errors", "WARNING"),
        ("Errors only", "ERROR"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = Theme.instance()
        self.view = LogView()

        self.level = QComboBox()
        for label, level in self.FILTERS:
            self.level.addItem(label, level)
        self.level.setFixedWidth(150)
        self.level.currentIndexChanged.connect(lambda _i: self.view.set_minimum_level(self.level.currentData()))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search log")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(240)
        self._search_action = QAction(self.search)
        theme.bind_icon(self._search_action, "search", "muted")
        self.search.addAction(self._search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search.textChanged.connect(self.view.set_search)

        self.follow = self._tool("follow", "Follow the end of the log", checkable=True)
        self.follow.setChecked(True)
        self.follow.toggled.connect(self.view.set_follow)
        self.copy = self._tool("copy", "Copy visible log")
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.view.visible_text()))
        self.clear = self._tool("delete", "Clear console")
        self.clear.clicked.connect(self.view.clear_entries)

        row = QWidget()
        row.setObjectName("ToolRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 6, 4)
        row_layout.setSpacing(6)
        row_layout.addWidget(self.level)
        row_layout.addWidget(self.search)
        row_layout.addStretch(1)
        for button in (self.follow, self.copy, self.clear):
            row_layout.addWidget(button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(row)
        layout.addWidget(self.view, 1)

    def _tool(self, icon: str, tooltip: str, *, checkable: bool = False) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setIconSize(QSize(16, 16))
        Theme.instance().bind_icon(button, icon)
        return button

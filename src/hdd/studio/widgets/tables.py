"""Compact read-only data table sized to its content."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ..theme import Theme


def fmt(value: Any, decimals: int = 0) -> str:
    """Numbers with a thousands separator; None as an em dash."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.{decimals}f}"
    return str(value)


class DataTable(QTableWidget):
    """Read-only table. ``numeric`` columns are right-aligned in tabular figures."""

    def __init__(
        self,
        headers: list[str],
        rows: list[list[Any]] | None = None,
        *,
        numeric: set[int] | None = None,
        max_visible_rows: int | None = 14,
        stretch: int | None = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(headers), parent)
        self._numeric = numeric or set()
        self._max_rows = max_visible_rows
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrap(False)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if stretch is not None:
            header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        for column in self._numeric:
            item = self.horizontalHeaderItem(column)
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setDefaultSectionSize(Theme.instance().tokens.metrics.row_height)
        self.set_rows(rows or [])

    def set_rows(self, rows: list[list[Any]], data: list[Any] | None = None) -> None:
        numeric_font = Theme.instance().numeric_font()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value if isinstance(value, str) else fmt(value))
                if c in self._numeric:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(numeric_font)
                if data is not None and c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, data[r])
                self.setItem(r, c, item)
        visible = len(rows) if self._max_rows is None else min(len(rows), self._max_rows)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if visible < len(rows) else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        row_h = self.verticalHeader().defaultSectionSize()
        self.setFixedHeight(self.horizontalHeader().sizeHint().height() + max(visible, 1) * row_h + 2)

    def on_activate(self, callback: Callable[[Any], None]) -> None:
        """Call ``callback(row_data)`` when a row is double-clicked or Enter is pressed."""
        self.itemActivated.connect(lambda item: callback(self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)))

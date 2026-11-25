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


AUTO = "auto"


class DataTable(QTableWidget):
    """Read-only table. ``numeric`` columns are right-aligned in tabular figures.

    Sizing: the first column (the row's name) always shows in full. One column takes
    the remaining width and elides its text in the middle: ``stretch`` names it, and
    the default picks the widest other text column (else the last column). When the
    columns still do not fit, the table scrolls sideways instead of hiding any. Every
    cell shows its full text as a tooltip.
    """

    def __init__(
        self,
        headers: list[str],
        rows: list[list[Any]] | None = None,
        *,
        numeric: set[int] | None = None,
        max_visible_rows: int | None = 14,
        stretch: int | str | None = AUTO,
        multi_select: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(0, len(headers), parent)
        self._numeric = numeric or set()
        self._max_rows = max_visible_rows
        self._stretch = stretch
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi_select else QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setWordWrap(False)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setMinimumSectionSize(36)
        for column in self._numeric:
            item = self.horizontalHeaderItem(column)
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().setDefaultSectionSize(Theme.instance().tokens.metrics.row_height)
        self.horizontalScrollBar().rangeChanged.connect(lambda *_: self._fit_height())
        self.set_rows(rows or [])

    def _stretch_column(self) -> int | None:
        if self._stretch != AUTO:
            return self._stretch
        columns = self.columnCount()
        text = [c for c in range(1, columns) if c not in self._numeric]
        if not text:
            return columns - 1 if columns > 1 else 0
        return max(text, key=lambda c: self.sizeHintForColumn(c))

    def _apply_sizing(self) -> None:
        header = self.horizontalHeader()
        stretch = self._stretch_column()
        for column in range(self.columnCount()):
            mode = QHeaderView.ResizeMode.Stretch if column == stretch else QHeaderView.ResizeMode.ResizeToContents
            header.setSectionResizeMode(column, mode)
        if stretch not in (None, 0):
            # The stretched column gives way first; the name column never shrinks below its content.
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

    def set_rows(self, rows: list[list[Any]], data: list[Any] | None = None) -> None:
        numeric_font = Theme.instance().numeric_font()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = value if isinstance(value, str) else fmt(value)
                item = QTableWidgetItem(text)
                if c in self._numeric:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(numeric_font)
                elif len(text) > 12:
                    item.setToolTip(text)
                if data is not None and c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, data[r])
                self.setItem(r, c, item)
        self._apply_sizing()
        self._fit_height()

    def _fit_height(self) -> None:
        rows = self.rowCount()
        visible = rows if self._max_rows is None else min(rows, self._max_rows)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if visible < rows else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        row_h = self.verticalHeader().defaultSectionSize()
        scroll = self.horizontalScrollBar()
        extra = scroll.sizeHint().height() if scroll.maximum() > 0 else 0
        self.setFixedHeight(self.horizontalHeader().sizeHint().height() + max(visible, 1) * row_h + 2 + extra)

    def selected_data(self) -> list[Any]:
        rows = sorted({index.row() for index in self.selectionModel().selectedRows()})
        return [self.item(row, 0).data(Qt.ItemDataRole.UserRole) for row in rows]

    def on_activate(self, callback: Callable[[Any], None]) -> None:
        """Call ``callback(row_data)`` when a row is double-clicked or Enter is pressed."""
        self.itemActivated.connect(lambda item: callback(self.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)))

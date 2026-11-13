"""Property table: name, value, unit. The Studio's way of showing KPIs and metadata."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from ..theme import Theme


class PropertyTable(QTableWidget):
    """Read-only three-column table sized to its content (the page scrolls, not the table)."""

    HEADERS = ("Property", "Value", "Unit")

    def __init__(self, rows: list[tuple[str, str, str]] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(0, 3, parent)
        self.setProperty("role", "properties")
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrap(False)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(2, 84)
        self._row_height = Theme.instance().tokens.metrics.row_height
        self.verticalHeader().setDefaultSectionSize(self._row_height)
        Theme.instance().changed.connect(self._restyle)
        if rows:
            self.set_rows(rows)

    def set_rows(self, rows: list[tuple[str, str, str]]) -> None:
        self.setRowCount(len(rows))
        for index, (name, value, unit) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            unit_item = QTableWidgetItem(unit)
            self.setItem(index, 0, name_item)
            self.setItem(index, 1, value_item)
            self.setItem(index, 2, unit_item)
        self._restyle()
        self._fit_height()

    def _restyle(self) -> None:
        theme = Theme.instance()
        numeric = theme.numeric_font()
        muted = QBrush(QColor(theme.tokens.colors.text_muted))
        for row in range(self.rowCount()):
            value_item, unit_item = self.item(row, 1), self.item(row, 2)
            if value_item is not None:
                value_item.setFont(numeric)
            if unit_item is not None:
                unit_item.setForeground(muted)

    def _fit_height(self) -> None:
        height = self.horizontalHeader().sizeHint().height() + self.rowCount() * self._row_height + 2
        self.setFixedHeight(height)

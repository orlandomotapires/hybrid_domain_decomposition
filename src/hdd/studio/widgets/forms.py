"""Form building blocks: sections, aligned label/field grids, inline messages."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..theme import Theme

LABEL_WIDTH = 176
NUMBER_WIDTH = 112
TEXT_WIDTH = 232


def repolish(widget: QWidget) -> None:
    """Re-evaluate style sheet rules after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class HLine(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "hline")
        self.setFixedHeight(1)


class Section(QWidget):
    """A titled, collapsible block of a settings page."""

    def __init__(self, title: str, *, expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._toggle = QToolButton()
        self._toggle.setProperty("role", "section")
        self._toggle.setText(title)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setIconSize(QSize(12, 12))
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.toggled.connect(self._on_toggled)

        self._body = QWidget()
        self.body = QVBoxLayout(self._body)
        self.body.setContentsMargins(0, 8, 0, 14)
        self.body.setSpacing(8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(HLine())
        layout.addWidget(self._body)

        Theme.instance().changed.connect(self._refresh_icon)
        self._on_toggled(expanded)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(expanded)

    def _on_toggled(self, expanded: bool) -> None:
        self._body.setVisible(expanded)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        name = "expanded" if self._toggle.isChecked() else "collapsed"
        self._toggle.setIcon(Theme.instance().icon(name, "muted"))


class FormGrid(QWidget):
    """Label-left form: label, field, unit, with an inline error line under the field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(0)
        self._grid.setColumnMinimumWidth(0, LABEL_WIDTH)
        self._grid.setColumnStretch(3, 1)
        self._rows: list[tuple[QWidget, QLabel]] = []

    def add_row(self, label: str, field: QWidget, unit: str = "", tooltip: str = "") -> int:
        """Append a row and return its index (for ``set_error``)."""
        index = len(self._rows)
        grid_row = index * 2
        caption = QLabel(label)
        caption.setBuddy(field)
        if tooltip:
            caption.setToolTip(tooltip)
            field.setToolTip(tooltip)
        if isinstance(field, QAbstractSpinBox):
            field.setFixedWidth(NUMBER_WIDTH)
            field.setAlignment(Qt.AlignmentFlag.AlignRight)
        elif isinstance(field, (QComboBox, QLineEdit)):
            field.setFixedWidth(TEXT_WIDTH)
        self._grid.addWidget(caption, grid_row, 0, Qt.AlignmentFlag.AlignVCenter)
        self._grid.addWidget(field, grid_row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if unit:
            unit_label = QLabel(unit)
            unit_label.setProperty("role", "unit")
            self._grid.addWidget(unit_label, grid_row, 2, Qt.AlignmentFlag.AlignVCenter)
        error = QLabel()
        error.setProperty("role", "error")
        error.setWordWrap(True)
        error.setVisible(False)
        self._grid.addWidget(error, grid_row + 1, 1, 1, 3)
        self._grid.setRowMinimumHeight(grid_row, 30)
        self._rows.append((field, error))
        return index

    def set_error(self, row: int, message: str | None) -> None:
        """Show ``message`` under the field of ``row``; ``None`` clears it."""
        field, error = self._rows[row]
        error.setText(message or "")
        error.setVisible(bool(message))
        field.setProperty("invalid", "true" if message else "false")
        repolish(field)

    def field(self, row: int) -> QWidget:
        return self._rows[row][0]


class InlineMessage(QFrame):
    """A one-line note inside a page: state colour on the edge, icon and text."""

    def __init__(self, severity: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if severity not in ("info", "ok", "warning", "error"):
            raise ValueError(f"unknown severity: {severity!r}")
        self._severity = severity
        self.setProperty("role", "message")
        self.setProperty("severity", severity)
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._text, 1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        Theme.instance().changed.connect(self._refresh_icon)
        self._refresh_icon()

    def severity(self) -> str:
        return self._severity

    def _refresh_icon(self) -> None:
        dpr = self.devicePixelRatioF()
        self._icon.setPixmap(Theme.instance().pixmap(self._severity, 16, self._severity, dpr))


def segmented(labels: list[str], checked: int = 0) -> tuple[QWidget, QButtonGroup]:
    """A row of mutually exclusive, joined buttons. Returns the widget and its button group."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    group = QButtonGroup(container)
    group.setExclusive(True)
    for index, text in enumerate(labels):
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setChecked(index == checked)
        button.setProperty("role", "segment")
        position = "first" if index == 0 else "last" if index == len(labels) - 1 else "middle"
        button.setProperty("pos", position)
        group.addButton(button, index)
        layout.addWidget(button)
    return container, group

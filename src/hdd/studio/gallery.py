"""Widget gallery: every styled control on one page, for reviewing the visual identity.

Open it with ``hdd-studio --gallery`` or from *Ajuda → Galeria de widgets*.
"""

from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from .prototype.plots import LocalityPlot
from .theme import Theme
from .theme.icons import ICONS
from .widgets import FormGrid, HLine, InlineMessage, LogView, PropertyTable, Section, segmented
from .widgets.log_view import LogEntry

COLOR_GROUPS = (
    ("Surfaces", ("window", "panel", "base", "base_alt", "menu")),
    ("Interaction", ("hover", "hover_soft", "pressed", "selection", "selection_inactive")),
    ("Lines", ("border", "border_strong")),
    ("Text and icons", ("text", "text_muted", "text_disabled", "icon")),
    ("Accent", ("accent", "accent_hover", "accent_pressed", "accent_fg")),
    ("State", ("ok", "warn", "error", "info", "ok_bg", "warn_bg", "error_bg", "info_bg")),
)


def _block(title: str, body: QWidget) -> QWidget:
    block = QWidget()
    layout = QVBoxLayout(block)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    heading = QLabel(title)
    heading.setProperty("role", "section")
    layout.addWidget(heading)
    layout.addWidget(HLine())
    layout.addWidget(body)
    return block


def _column(*widgets: QWidget, spacing: int = 8) -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return holder


def _row(*widgets: QWidget, spacing: int = 8) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    layout.addStretch(1)
    return holder


def _swatch(name: str, value: str) -> QWidget:
    chip = QFrame()
    chip.setProperty("role", "swatch")
    chip.setFixedSize(30, 18)
    chip.setStyleSheet(f"background: {value};")
    label = QLabel(name)
    code = QLabel(value.upper())
    code.setProperty("role", "caption")
    code.setFont(Theme.instance().mono_font())
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(chip)
    layout.addWidget(label)
    layout.addStretch(1)
    layout.addWidget(code)
    return holder


class Gallery(QWidget):
    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setWindowTitle(f"Widget gallery — {APP_NAME}")
        self.resize(1180, 860)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        self.content: QWidget = QWidget()
        theme.changed.connect(self._rebuild)
        self._rebuild()

    # The page is rebuilt on theme change because swatches show token values.
    def _rebuild(self) -> None:
        tokens = self._theme.tokens
        content = QWidget()
        content.setObjectName("Page")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(18)

        title = QLabel(f"Visual identity — {'dark' if tokens.is_dark else 'light'} theme")
        title.setProperty("role", "heading")
        note = QLabel("Every value comes from src/hdd/studio/theme/tokens.py.")
        note.setProperty("role", "caption")
        outer.addWidget(_column(title, note, spacing=2))

        grid = QGridLayout()
        grid.setHorizontalSpacing(32)
        grid.setVerticalSpacing(18)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        left = _column(
            _block("Colours", self._colors()),
            _block("Typography", self._typography()),
            _block("Buttons", self._buttons()),
            _block("Fields", self._fields()),
            spacing=18,
        )
        right = _column(
            _block("Messages", self._messages()),
            _block("Property table", self._properties()),
            _block("Sections", self._sections()),
            _block("Progress", self._progress()),
            _block("Plot palette", self._plot_palette()),
            _block("Console", self._console()),
            spacing=18,
        )
        grid.addWidget(left, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(right, 0, 1, Qt.AlignmentFlag.AlignTop)
        outer.addLayout(grid)
        outer.addWidget(_block("Icons", self._icons()))
        outer.addStretch(1)

        self.content = content
        self.scroll.setWidget(content)

    # ------------------------------------------------------------------ blocks
    def _colors(self) -> QWidget:
        values = asdict(self._theme.tokens.colors)
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(3)
        column = row = 0
        for group, names in COLOR_GROUPS:
            if row + len(names) + 1 > 14:
                column, row = column + 1, 0
            caption = QLabel(group)
            caption.setProperty("role", "caption")
            grid.addWidget(caption, row, column)
            row += 1
            for name in names:
                grid.addWidget(_swatch(name, values[name]), row, column)
                row += 1
            row += 1
        return holder

    def _typography(self) -> QWidget:
        heading = QLabel("Page title")
        heading.setProperty("role", "heading")
        section = QLabel("Section title")
        section.setProperty("role", "section")
        body = QLabel("Interface text: labels, menus, table cells.")
        muted = QLabel("Secondary text: units, hints, paths.")
        muted.setProperty("role", "muted")
        caption = QLabel("Caption: panel headers and notes.")
        caption.setProperty("role", "caption")
        mono = QLabel("14:15:03  INFO     Stage 3/5  partitioning")
        mono.setFont(self._theme.mono_font())
        numbers = QLabel("1,234,567.89     0.0200     600")
        numbers.setFont(self._theme.numeric_font())
        return _column(heading, section, body, muted, caption, mono, numbers, spacing=5)

    def _buttons(self) -> QWidget:
        primary = QPushButton("Run")
        primary.setProperty("role", "primary")
        self._theme.bind_icon(primary, "run", "on_accent")
        default = QPushButton("Validate")
        with_icon = QPushButton("Export…")
        self._theme.bind_icon(with_icon, "export")
        disabled = QPushButton("Unavailable")
        disabled.setEnabled(False)
        disabled_primary = QPushButton("Run")
        disabled_primary.setProperty("role", "primary")
        disabled_primary.setEnabled(False)

        tools = []
        for icon, checkable, enabled in (("save", False, True), ("undo", False, True), ("follow", True, True), ("redo", False, False)):
            button = QToolButton()
            button.setIconSize(QSize(20, 20))
            button.setCheckable(checkable)
            button.setChecked(checkable)
            button.setEnabled(enabled)
            self._theme.bind_icon(button, icon)
            tools.append(button)
        segment, _group = segmented(["Original", "Permuted", "Difference"], 1)
        return _column(
            _row(primary, default, with_icon, disabled, disabled_primary),
            _row(*tools, segment, spacing=4),
        )

    def _fields(self) -> QWidget:
        form = FormGrid()
        text = QLineEdit("simulation_01")
        form.add_row("Text", text)
        empty = QLineEdit()
        empty.setPlaceholderText("Preset name")
        form.add_row("Empty text", empty)
        number = QSpinBox()
        number.setRange(0, 100000)
        number.setValue(1000)
        form.add_row("Integer", number, "reads")
        decimal = QDoubleSpinBox()
        decimal.setDecimals(3)
        decimal.setValue(0.02)
        form.add_row("Decimal", decimal)
        invalid = QSpinBox()
        invalid.setRange(0, 1000)
        invalid.setValue(24)
        row = form.add_row("Upper limit", invalid, "nodes")
        form.set_error(row, "Must be greater than the lower limit (32).")
        combo = QComboBox()
        combo.addItems(["METIS", "Quantum annealing", "QAOA"])
        form.add_row("List", combo)
        disabled = QLineEdit("Set when hardware is selected")
        disabled.setEnabled(False)
        form.add_row("Disabled", disabled)

        checked = QCheckBox("Checked option")
        checked.setChecked(True)
        unchecked = QCheckBox("Unchecked option")
        check_disabled = QCheckBox("Disabled")
        check_disabled.setEnabled(False)
        radio_a = QRadioButton("Emulated")
        radio_a.setChecked(True)
        radio_b = QRadioButton("Hardware")
        return _column(form, _row(checked, unchecked, check_disabled, spacing=18), _row(radio_a, radio_b, spacing=18))

    def _messages(self) -> QWidget:
        return _column(
            InlineMessage("info", "Estimate: 3 bisections and 3,000 reads on the emulator."),
            InlineMessage("ok", "Parameters are valid."),
            InlineMessage("warning", "The balance tolerance may be infeasible at this level."),
            InlineMessage("error", "The upper limit must be greater than the lower limit."),
            spacing=6,
        )

    def _properties(self) -> QWidget:
        return PropertyTable(
            [
                ("Edge cut", "128", "edges"),
                ("Imbalance", "0.00", "%"),
                ("Bandwidth, permuted", "466", ""),
                ("Total time", "1.19", "s"),
            ]
        )

    def _sections(self) -> QWidget:
        open_section = Section("Expanded section")
        open_section.add(QLabel("Section content: forms, tables or messages."))
        closed_section = Section("Collapsed section", expanded=False)
        closed_section.add(QLabel("Hidden"))
        return _column(open_section, closed_section, spacing=4)

    def _progress(self) -> QWidget:
        determinate = QProgressBar()
        determinate.setRange(0, 100)
        determinate.setValue(54)
        determinate.setTextVisible(False)
        label = QLabel("Partitioning, 54 %")
        label.setProperty("role", "muted")
        return _column(determinate, label, spacing=4)

    def _plot_palette(self) -> QWidget:
        plot = self._theme.tokens.plot
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(3)
        names = [f"series {index + 1}" for index in range(len(plot.series))]
        for index, (name, value) in enumerate(zip(names, plot.series)):
            grid.addWidget(_swatch(name, value), index % 4, index // 4)
        grid.addWidget(_swatch("reference", plot.reference), 4, 0)
        grid.addWidget(_swatch("grid", plot.grid), 4, 1)
        chart = LocalityPlot()
        chart.setFixedHeight(230)
        return _column(holder, chart, spacing=10)

    def _console(self) -> QWidget:
        view = LogView()
        view.setFixedHeight(104)
        for entry in (
            LogEntry("14:15:02", "DEBUG", "level 4: 86 -> 48 nodes"),
            LogEntry("14:15:03", "INFO", "Stage 3/5  partitioning (quantum annealing, emulated, k = 4)"),
            LogEntry("14:15:03", "WARNING", "balance_tolerance 0.02 is tight for 48 nodes"),
            LogEntry("14:15:09", "ERROR", "Partitioning failed: no balanced solution found"),
        ):
            view.append_entry(entry)
        return view

    def _icons(self) -> QWidget:
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)
        columns = 6
        for index, name in enumerate(sorted(ICONS)):
            picture = QLabel()
            picture.setFixedSize(16, 16)
            picture.setPixmap(self._theme.pixmap(name, 16, "default", self.devicePixelRatioF()))
            label = QLabel(name)
            label.setProperty("role", "muted")
            grid.addWidget(_row(picture, label, spacing=8), index // columns, index % columns)
        return holder

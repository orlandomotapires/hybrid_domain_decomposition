"""Generates the application style sheet from design tokens.

The style sheet is the only place where widget appearance is written down. It is
a template: every colour and size comes from ``Tokens``; ``glyphs`` maps glyph
names (small arrows, check marks) to recoloured SVG files on disk.
"""

from __future__ import annotations

from dataclasses import asdict
from string import Template

from .tokens import Tokens

_TEMPLATE = Template(
    r"""
/* ---------------------------------------------------------------- chrome */
QMainWindow, QDialog { background-color: $window; }
QMainWindow::separator { background: $window; width: ${separator}px; height: ${separator}px; }
QMainWindow::separator:hover { background: $accent_fg; }

QMenuBar { background-color: $window; border-bottom: 1px solid $border; padding: 1px 4px; }
QMenuBar::item { background: transparent; padding: 4px 9px; border-radius: ${radius}px; }
QMenuBar::item:selected { background: $hover; }
QMenuBar::item:pressed { background: $pressed; }

QMenu { background-color: $menu; border: 1px solid $border_strong; padding: 4px 0; }
QMenu::item { padding: 5px 28px 5px 12px; }
QMenu::item:selected { background: $selection; color: $selection_text; }
QMenu::item:disabled { color: $text_disabled; }
QMenu::separator { height: 1px; background: $border; margin: 4px 0; }
QMenu::icon { padding-left: 10px; }
QMenu::indicator { width: 14px; height: 14px; left: 8px; }
QMenu::indicator:checked { image: url($g_check); }
QMenu::right-arrow { image: url($g_chevron_right); width: 12px; height: 12px; right: 6px; }

QToolBar { background-color: $window; border: none; border-bottom: 1px solid $border; padding: 3px 6px; spacing: 2px; }
QToolBar::separator { background: $border; width: 1px; margin: 4px 5px; }

QToolButton { background: transparent; border: 1px solid transparent; border-radius: ${radius}px; padding: 3px 5px; }
QToolButton:hover { background: $hover; }
QToolButton:pressed { background: $pressed; }
QToolButton:checked { background: $pressed; }
QToolButton:disabled { color: $text_disabled; }
QToolButton::menu-indicator { image: none; }

QToolButton[role="section"] { font-weight: 600; padding: 3px 0; border: none; background: transparent; }
QToolButton[role="section"]:hover { color: $accent_fg; }

QToolButton[role="segment"] { background: $base; border: 1px solid $border_strong; border-radius: 0; padding: 2px 10px; }
QToolButton[role="segment"]:hover { background: $hover_soft; }
QToolButton[role="segment"]:checked { background: $selection; color: $selection_text; }
QToolButton[role="segment"][pos="first"] { border-top-left-radius: ${radius}px; border-bottom-left-radius: ${radius}px; }
QToolButton[role="segment"][pos="last"] { border-left: none; border-top-right-radius: ${radius}px; border-bottom-right-radius: ${radius}px; }
QToolButton[role="segment"][pos="middle"] { border-left: none; }

QStatusBar { background-color: $window; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: $text_muted; padding: 0 6px; }

QWidget#DockTitle { background-color: $window; }
QWidget#TabStrip { background-color: $window; border-bottom: 1px solid $border; }
QWidget#PanelHeader { background-color: $panel; border-bottom: 1px solid $border; }
QWidget#ToolRow { background-color: $panel; border-bottom: 1px solid $border; }
QWidget#Page { background-color: $panel; }
QWidget#Surface { background-color: $base; }

/* ------------------------------------------------------------------ tabs */
QTabWidget::pane { border: none; border-top: 1px solid $border; }
QTabBar { background: transparent; qproperty-drawBase: 0; }
QTabBar::tab { background: transparent; color: $text_muted; padding: 6px 12px; border: none; border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected { color: $text; border-bottom: 2px solid $accent_fg; }
QTabBar::tab:disabled { color: $text_disabled; }

/* ------------------------------------------------------------ item views */
QTreeView, QTableView, QListView {
    background-color: $base; alternate-background-color: $base_alt;
    border: none; outline: 0; show-decoration-selected: 1;
}
QTreeView::item, QListView::item { min-height: ${row_height}px; padding: 0 2px; border: none; }
QTableView::item { padding: 0 6px; border: none; }
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover { background: $hover_soft; }
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected { background: $selection; color: $selection_text; }
QTreeView::item:selected:!active, QListView::item:selected:!active, QTableView::item:selected:!active { background: $selection_inactive; color: $text; }
QTreeView::branch { background: $base; }
QTreeView::branch:selected { background: $selection; }
QTreeView::branch:selected:!active { background: $selection_inactive; }
QTreeView::branch:has-children:!has-siblings:closed, QTreeView::branch:closed:has-children:has-siblings { image: url($g_chevron_right); }
QTreeView::branch:open:has-children:!has-siblings, QTreeView::branch:open:has-children:has-siblings { image: url($g_chevron_down); }
QTableView { gridline-color: $border; }
QTableView[role="properties"]::item { border-bottom: 1px solid $border; }

QHeaderView { background-color: $panel; border: none; }
QHeaderView::section {
    background-color: $panel; color: $text_muted; padding: 0 6px; min-height: ${row_height}px;
    border: none; border-bottom: 1px solid $border; border-right: 1px solid $border;
}
QHeaderView::section:last { border-right: none; }
QHeaderView::up-arrow { image: url($g_caret_up); width: 8px; height: 8px; }
QHeaderView::down-arrow { image: url($g_caret_down); width: 8px; height: 8px; }
QTableCornerButton::section { background-color: $panel; border: none; border-bottom: 1px solid $border; border-right: 1px solid $border; }

/* ---------------------------------------------------------------- inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: $base; color: $text; border: 1px solid $border_strong; border-radius: ${radius}px;
    padding: 2px 6px; min-height: 20px; selection-background-color: $accent; selection-color: $accent_text;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { border-color: $text_muted; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: $accent_fg; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { background-color: $panel; color: $text_disabled; border-color: $border; }
QLineEdit[invalid="true"], QSpinBox[invalid="true"], QDoubleSpinBox[invalid="true"], QComboBox[invalid="true"] { border-color: $error; }

QComboBox { padding-right: 22px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }
QComboBox::down-arrow { image: url($g_chevron_down); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background-color: $menu; border: 1px solid $border_strong; outline: 0;
    selection-background-color: $selection; selection-color: $selection_text;
}

QSpinBox, QDoubleSpinBox { padding-right: 18px; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right; width: 17px;
    border: none; border-left: 1px solid $border; border-bottom: 1px solid $border; background: transparent;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right; width: 17px;
    border: none; border-left: 1px solid $border; background: transparent;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: $hover; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url($g_caret_up); width: 8px; height: 8px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url($g_caret_down); width: 8px; height: 8px; }

QPlainTextEdit, QTextEdit, QTextBrowser {
    background-color: $base; color: $text; border: none;
    selection-background-color: $accent; selection-color: $accent_text;
}

/* --------------------------------------------------------------- buttons */
QPushButton {
    background-color: $base; color: $text; border: 1px solid $border_strong; border-radius: ${radius}px;
    padding: 3px 14px; min-height: 20px; min-width: 56px;
}
QPushButton:hover { background-color: $hover_soft; border-color: $text_muted; }
QPushButton:pressed { background-color: $pressed; }
QPushButton:focus { border-color: $accent_fg; }
QPushButton:disabled { background-color: $panel; color: $text_disabled; border-color: $border; }
QPushButton[role="primary"] { background-color: $accent; color: $accent_text; border-color: $accent; }
QPushButton[role="primary"]:hover { background-color: $accent_hover; border-color: $accent_hover; }
QPushButton[role="primary"]:pressed { background-color: $accent_pressed; border-color: $accent_pressed; }
QPushButton[role="primary"]:disabled { background-color: $panel; color: $text_disabled; border-color: $border; }

QCheckBox, QRadioButton { spacing: 6px; }
QCheckBox::indicator, QTreeView::indicator, QTableView::indicator, QListView::indicator {
    width: 13px; height: 13px; border: 1px solid $border_strong; border-radius: ${radius}px; background: $base;
}
QCheckBox::indicator:hover, QTreeView::indicator:hover, QTableView::indicator:hover { border-color: $accent_fg; }
QCheckBox::indicator:checked, QTreeView::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {
    background: $accent; border-color: $accent; image: url($g_check_on_accent);
}
QCheckBox::indicator:disabled { background: $panel; border-color: $border; }
QRadioButton::indicator { width: 13px; height: 13px; border: 1px solid $border_strong; border-radius: 7px; background: $base; }
QRadioButton::indicator:hover { border-color: $accent_fg; }
QRadioButton::indicator:checked { border-color: $accent; image: url($g_radio_dot); }
QRadioButton::indicator:disabled { background: $panel; border-color: $border; }

/* ------------------------------------------------------------- scrolling */
QScrollArea { background: transparent; border: none; }
QAbstractScrollArea::corner { background: transparent; }
QScrollBar:vertical { background: transparent; width: ${scrollbar}px; margin: 0; border: none; }
QScrollBar:horizontal { background: transparent; height: ${scrollbar}px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: $border_strong; min-height: 28px; margin: 2px 3px; border-radius: 3px; }
QScrollBar::handle:horizontal { background: $border_strong; min-width: 28px; margin: 3px 2px; border-radius: 3px; }
QScrollBar::handle:hover { background: $text_muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle { background: $border; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

/* ------------------------------------------------------------------ misc */
QProgressBar { background: $border; border: none; border-radius: ${radius}px; max-height: 6px; min-height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: $accent; border-radius: ${radius}px; }

QToolTip { background-color: $menu; color: $text; border: 1px solid $border_strong; padding: 3px 6px; }

QGroupBox { border: none; border-top: 1px solid $border; margin-top: 22px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 0 5px 0; }

QFrame[role="hline"] { background: $border; border: none; max-height: 1px; min-height: 1px; }
QFrame[role="vline"] { background: $border; border: none; max-width: 1px; min-width: 1px; }

QFrame[role="message"] { border: none; border-left: 2px solid $info; background: $info_bg; }
QFrame[role="message"][severity="ok"] { border-left-color: $ok; background: $ok_bg; }
QFrame[role="message"][severity="warning"] { border-left-color: $warn; background: $warn_bg; }
QFrame[role="message"][severity="error"] { border-left-color: $error; background: $error_bg; }
QFrame[role="swatch"] { border: 1px solid $border; }

QLabel[role="muted"], QLabel[role="unit"] { color: $text_muted; }
QLabel[role="heading"] { font-size: ${heading_pt}pt; font-weight: 600; }
QLabel[role="section"] { font-weight: 600; }
QLabel[role="caption"] { color: $text_muted; font-size: ${small_pt}pt; }
QLabel[role="error"] { color: $error; font-size: ${small_pt}pt; }
QLabel[role="dirty"] { color: $warn; font-weight: 600; font-size: ${small_pt}pt; }
QLabel[role="dock-title"] { color: $text_muted; font-weight: 600; font-size: ${small_pt}pt; }
"""
)

#: Glyph names the template refers to as ``$g_<name>``.
GLYPH_NAMES = (
    "chevron_down",
    "chevron_right",
    "caret_up",
    "caret_down",
    "check",
    "check_on_accent",
    "radio_dot",
)


def build_stylesheet(tokens: Tokens, glyphs: dict[str, str]) -> str:
    """Return the application style sheet for ``tokens``.

    ``glyphs`` maps every name in ``GLYPH_NAMES`` to the path of an SVG file.
    """
    values: dict[str, object] = {}
    values.update(asdict(tokens.colors))
    values.update(asdict(tokens.metrics))
    values.update(asdict(tokens.type))
    for name in GLYPH_NAMES:
        values[f"g_{name}"] = glyphs[name].replace("\\", "/")
    return _TEMPLATE.substitute(values)

from hdd.studio.gallery import Gallery
from hdd.studio.prototype import sample_data
from hdd.studio.widgets import FormGrid, InlineMessage, Section
from hdd.studio.widgets.log_view import LogEntry, LogView


def test_sample_decomposition_is_self_consistent():
    data = sample_data.decomposition()
    assert sorted(data.original.tolist()) == sorted(data.permuted.tolist()) == list(range(data.n))
    assert data.nnz == data.n + 2 * sample_data.edge_count()
    widths = sample_data.np.array([0.0, 100.0])
    for ordering in ("original", "permuted"):
        low, high = data.locality_curve(ordering, widths)
        assert 0 < low < high == 100.0


def test_log_view_filters_by_level_and_text(qtbot, theme):
    view = LogView()
    qtbot.addWidget(view)
    for level, message in (("DEBUG", "level 1"), ("INFO", "Stage 2/5"), ("WARNING", "tight balance"), ("ERROR", "failed")):
        view.append_entry(LogEntry("10:00:00", level, message))
    assert view.visible_count() == 4
    view.set_minimum_level("WARNING")
    assert view.visible_count() == 2 and "Stage" not in view.visible_text()
    view.set_search("FAILED")
    assert view.visible_count() == 1 and view.visible_text().endswith("failed")


def test_form_shows_and_clears_inline_errors(qtbot, theme):
    from PySide6.QtWidgets import QSpinBox

    form = FormGrid()
    qtbot.addWidget(form)
    row = form.add_row("Upper limit", QSpinBox(), "nodes")
    form.set_error(row, "Must be greater than the lower limit.")
    assert form.field(row).property("invalid") == "true"
    form.set_error(row, None)
    assert form.field(row).property("invalid") == "false"


def test_section_collapses_and_messages_validate_severity(qtbot, theme):
    import pytest

    section = Section("Limits")
    qtbot.addWidget(section)
    section.set_expanded(False)
    assert not section.is_expanded()
    assert InlineMessage("warning", "x").severity() == "warning"
    with pytest.raises(ValueError):
        InlineMessage("fatal", "x")


def test_gallery_builds_in_both_themes(qtbot, theme):
    gallery = Gallery(theme)
    qtbot.addWidget(gallery)
    first = gallery.content
    theme.apply("dark")
    assert gallery.content is not first


def test_double_spin_box_uses_separators_and_scientific_notation(qapp):
    from hdd.studio.editors import DoubleSpinBox

    box = DoubleSpinBox()
    box.setDecimals(3)
    box.setRange(0, 1e18)
    assert box.textFromValue(1234.5) == "1,234.500"
    assert box.textFromValue(1e15) == "1e15"
    assert box.textFromValue(2.5e6) == "2.5e6"
    assert box.valueFromText("1e18") == 1e18
    assert box.valueFromText("1,234.5") == 1234.5


def test_property_values_align_by_kind():
    from hdd.studio.widgets.property_table import is_numeric

    assert all(is_numeric(v) for v in ("1,800", "3.240", "20 of 20", "2 / 0", "—", "1e15", "-0.5"))
    assert not any(is_numeric(v) for v in ("METIS (Classical)", "simulation_parameters.json", "Matrix Market, coordinate"))


def test_formulas_use_unicode_sub_and_superscripts():
    from hdd.studio.help import pretty_formula

    assert pretty_formula("P_{k-1} + x^{2}") == "Pₖ₋₁ + x²"
    assert pretty_formula("G_{coarse}") == "G_{coarse}"  # no subscript "c" in Unicode: left as written

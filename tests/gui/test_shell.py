from PySide6.QtCore import Qt

from hdd.studio.gallery import Gallery
from hdd.studio.main_window import KIND_ROLE, MainWindow
from hdd.studio.prototype import sample_data
from hdd.studio.widgets import FormGrid, InlineMessage, Section
from hdd.studio.widgets.log_view import LogEntry, LogView


def make_window(qtbot, theme, settings):
    window = MainWindow(theme, settings)
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(20)
    return window


def test_window_has_the_commercial_layout(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    names = {dock.objectName() for dock in window.docks}
    assert names == {"ProjectDock", "SettingsDock", "ConsoleDock", "JobsDock", "ProblemsDock"}
    assert window.dockWidgetArea(window.project_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    assert window.dockWidgetArea(window.console_dock) == Qt.DockWidgetArea.BottomDockWidgetArea
    assert window.centralWidget() is window.graphics
    menus = [action.text().replace("&", "") for action in window.menuBar().actions()]
    assert menus == ["File", "Edit", "Simulation", "Batch", "Tuning", "View", "Help"]


def test_tabbed_docks_hide_their_redundant_title(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    assert not window.console_dock.title_visible()
    assert not window.jobs_dock.title_visible()
    assert window.project_dock.title_visible()


def test_tree_lists_the_project_and_drives_the_settings_panel(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    proxy = window.project.proxy
    top = [proxy.index(row, 0).data() for row in range(proxy.rowCount())]
    assert top == ["Matrices", "Simulations", "Batch", "Quantum hardware"]
    assert window.settings_panel.kind == "coarsening"

    assert window.select_node("partitioning")
    assert window.settings_panel.title.text() == "Partitioning"
    assert "simulation_01" in window.settings_panel.path.text()
    assert window.select_node("run")
    assert window.graphics.stack.currentWidget() is window.graphics.locality
    assert not window.select_node("no-such-kind")


def test_tree_filter_keeps_matching_branches(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    window.project.filter.setText("coarsening")
    proxy = window.project.proxy
    assert [proxy.index(row, 0).data() for row in range(proxy.rowCount())] == ["Simulations"]
    assert window.project.find("coarsening").data(KIND_ROLE) == "coarsening"
    assert not window.project.find("hardware").isValid()


def test_layout_survives_a_restart_and_can_be_reset(qtbot, theme, settings):
    first = make_window(qtbot, theme, settings)
    first.jobs_dock.setFloating(True)
    first.problems_dock.close()
    first.close()

    second = make_window(qtbot, theme, settings)
    assert second.jobs_dock.isFloating()
    assert not second.problems_dock.isVisible()
    second.reset_layout()
    qtbot.wait(20)
    assert not second.jobs_dock.isFloating()
    assert second.dockWidgetArea(second.problems_dock) == Qt.DockWidgetArea.BottomDockWidgetArea


def test_theme_choice_is_applied_and_remembered(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    window.set_theme("dark")
    assert theme.tokens.is_dark
    assert settings.theme_mode() == "dark"
    assert window.theme_actions["dark"].isChecked()


def test_sparsity_view_switches_ordering(qtbot, theme, settings):
    window = make_window(qtbot, theme, settings)
    plot = window.graphics.sparsity
    assert plot.ordering() == "permuted"
    window.graphics._ordering_group.button(0).click()
    assert plot.ordering() == "original"


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

"""Main window: menus, tool bar, dockable panels, graphics area and status bar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence, QUndoGroup
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hdd.services import batch, matrices, results, simulations, tuning, workspace
from hdd.services.errors import ServiceError

from . import APP_NAME, batch_page, diagnostics, pages, sim_pages
from .batch_doc import BatchDocument
from .bottom_panel import BottomPanel
from .context import AppContext
from .dialogs import CompareDialog, NewSimulationDialog, NewStudyDialog
from .documents import SimulationDocument
from .graphics.area import GraphicsArea
from .help import HelpPanel
from .jobs_panel import JobConsole, JobsPanel, job_stage
from .project import ProjectSnapshot, load_snapshot
from .settings import LAYOUT_VERSION, Settings
from .theme import MODES, Theme
from .tree import Node, ProjectPanel
from .widgets import ConsolePanel
from .widgets.tables import DataTable

# Help topic shown by F1 when no parameter has the focus, per project-tree node kind.
HELP_TOPIC_FOR_NODE = {
    "matrices": "stage-1", "matrix": "stage-1-mtx-tools", "simulations": "stage-1", "simulation": "stage-1", "input": "stage-1",
    "coarsening": "stage-2", "partitioning": "stage-3", "refinement": "stage-4", "outputs": "stage-5", "presets": "param-preset-file",
    "preset": "param-preset-file", "results": "metric-bandwidth", "run": "metric-bandwidth", "batch": "batch-study",
    "batch_config": "batch-study", "batch_runs": "batch-study", "batch_run": "batch-study", "hardware": "hardware-backends",
}

THEME_LABELS = {"system": "Follow system", "light": "Light", "dark": "Dark"}


def _short_path(path: Path) -> str:
    """``path`` with the home folder written as ``~``."""
    try:
        return "~/" + Path(path).relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


class DockTitleBar(QWidget):
    """Flat title bar for a dock: name on the left, float and close on the right."""

    def __init__(self, dock: QDockWidget) -> None:
        super().__init__(dock)
        self.setObjectName("DockTitle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        label = QLabel(dock.windowTitle())
        label.setProperty("role", "dock-title")
        float_button = self._button("float", "Float or dock this panel")
        float_button.clicked.connect(lambda: dock.setFloating(not dock.isFloating()))
        close_button = self._button("close", "Close panel")
        close_button.clicked.connect(dock.close)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 3, 2)
        layout.setSpacing(1)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(float_button)
        layout.addWidget(close_button)

    def _button(self, icon: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setIconSize(QSize(12, 12))
        Theme.instance().bind_icon(button, icon, "muted")
        return button


class Dock(QDockWidget):
    """Dock whose title bar collapses while it is one tab of a tabbed group."""

    def __init__(self, title: str, name: str, parent: QMainWindow) -> None:
        super().__init__(title, parent)
        self.setObjectName(name)
        self._bar = DockTitleBar(self)
        self._empty = QWidget(self)
        self._title_visible = True
        self.setTitleBarWidget(self._bar)

    def set_title_visible(self, visible: bool) -> None:
        if visible == self._title_visible:
            return
        self._title_visible = visible
        self.setTitleBarWidget(self._bar if visible else self._empty)
        self._bar.setVisible(visible)

    def title_visible(self) -> bool:
        return self._title_visible


class SettingsPanel(QWidget):
    """Page for the node selected in the project tree."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = QLabel()
        self.path.setProperty("role", "caption")
        self.title = QLabel()
        self.title.setProperty("role", "heading")
        header = QWidget()
        header.setObjectName("PanelHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        box = QVBoxLayout(header)
        box.setContentsMargins(14, 8, 14, 9)
        box.setSpacing(1)
        self.dirty = QLabel("● Unsaved changes")
        self.dirty.setProperty("role", "dirty")
        self.dirty.setToolTip("Save with Ctrl+S, or revert from the File menu")
        self.dirty.setVisible(False)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addWidget(self.title)
        title_row.addStretch(1)
        title_row.addWidget(self.dirty)
        box.addWidget(self.path)
        box.addLayout(title_row)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.scroll, 1)
        self.node: Node | None = None

    def show_header(self, node: Node | None, breadcrumb: list[str]) -> None:
        self.node = node
        self.path.setText("  ›  ".join(breadcrumb[:-1]) if len(breadcrumb) > 1 else "Project")
        self.title.setText(breadcrumb[-1] if breadcrumb else "")

    def show_text(self, text: str) -> None:
        page = pages.Page()
        page.note(text)
        self.scroll.setWidget(page.finish())

    def show_widget(self, widget: QWidget) -> None:
        self.scroll.setWidget(widget)

    def page(self) -> QWidget | None:
        return self.scroll.widget()


class MainWindow(QMainWindow):
    def __init__(self, theme: Theme, settings: Settings, root: Path) -> None:
        super().__init__()
        self._theme = theme
        self._settings = settings
        self.ctx = AppContext(root, self)
        self.snapshot: ProjectSnapshot | None = None
        self.docs: dict[str, SimulationDocument] = {}
        self.batch_doc: BatchDocument | None = None
        self.undo_group = QUndoGroup(self)
        self._pending_focus: str | None = None
        self.setObjectName("MainWindow")
        self.resize(1440, 900)
        self.setAnimated(False)
        self.setDockNestingEnabled(True)
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.graphics = GraphicsArea(self.ctx.tasks)
        self.setCentralWidget(self.graphics)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._connect_context()
        diagnostics.set_reporter(lambda text: self.statusBar().showMessage(text, 15000))

        self.project.nodeSelected.connect(self._on_node_selected)
        self.jobs.jobSelected.connect(self._follow_job)
        self.jobs.showResult.connect(lambda rel: self.select_key(f"run:{rel}"))
        self._default_state = self.saveState(LAYOUT_VERSION)
        self._restore_layout()
        QTimer.singleShot(0, self._sync_dock_titles)
        self._settings.remember_workspace(str(self.ctx.root))
        self._update_title()
        self.reload()

    # ------------------------------------------------------------------ docks
    def _build_docks(self) -> None:
        self.project = ProjectPanel()
        self.settings_panel = SettingsPanel()
        self.console_panel = ConsolePanel()
        self.console = JobConsole(self.ctx.jobs, self.console_panel)
        self.jobs = JobsPanel(self.ctx.jobs)
        self.problems = DataTable(["Description", "Location"], max_visible_rows=None, stretch=0)
        self.problems.setMaximumHeight(16777215)
        self.problems.on_activate(self._go_to_problem)
        self.project.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.project.tree.customContextMenuRequested.connect(self._tree_menu)

        self.project_dock = self._dock("Project", "ProjectDock", self.project)
        self.settings_dock = self._dock("Settings", "SettingsDock", self.settings_panel)
        self.console_dock = self._dock("Console", "ConsoleDock", self.console_panel)
        self.jobs_dock = self._dock("Jobs", "JobsDock", self.jobs)
        self.problems_dock = self._dock("Problems", "ProblemsDock", self.problems)
        self.help = HelpPanel()
        self.help_dock = self._dock("Help", "HelpDock", self.help)
        self.docks = [self.project_dock, self.settings_dock, self.console_dock, self.jobs_dock, self.problems_dock, self.help_dock]
        left, bottom = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea
        self.addDockWidget(left, self.project_dock)
        self.splitDockWidget(self.project_dock, self.settings_dock, Qt.Orientation.Horizontal)
        self.addDockWidget(bottom, self.console_dock)
        self.tabifyDockWidget(self.console_dock, self.jobs_dock)
        self.tabifyDockWidget(self.jobs_dock, self.problems_dock)
        self.console_dock.raise_()
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.help_dock)
        self.help_dock.hide()
        self.bottom = BottomPanel(self, [self.console_dock, self.jobs_dock, self.problems_dock])
        self._error_count: int | None = None  # errors in the Problems list; None until the first refresh
        self._apply_default_sizes()

    def _dock(self, title: str, name: str, widget: QWidget) -> Dock:
        dock = Dock(title, name, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        for signal in (dock.dockLocationChanged, dock.topLevelChanged, dock.visibilityChanged):
            signal.connect(lambda *_args: QTimer.singleShot(0, self._sync_dock_titles))
        return dock

    def _apply_default_sizes(self) -> None:
        self.resizeDocks([self.project_dock, self.settings_dock], [270, 560], Qt.Orientation.Horizontal)
        self.resizeDocks([self.console_dock], [230], Qt.Orientation.Vertical)

    def _sync_dock_titles(self) -> None:
        for dock in self.docks:
            dock.set_title_visible(not (self.tabifiedDockWidgets(dock) and not dock.isFloating()))
        self.bottom.sync()

    # ---------------------------------------------------------------- actions
    def _action(self, text: str, slot, icon: str | None = None, shortcut=None, tint: str = "default", tip: str | None = None) -> QAction:
        action = QAction(text, self)
        if icon:
            self._theme.bind_icon(action, icon, tint)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        name = text.replace("&", "").rstrip("…")
        keys = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        action.setToolTip(tip or (f"{name} ({keys})" if keys else name))
        action.triggered.connect(lambda _checked=False: slot())
        return action

    def _build_actions(self) -> None:
        a = self._action
        self.act_new_workspace = a("&New workspace…", self.new_workspace, "new", QKeySequence.StandardKey.New)
        self.act_open_workspace = a("&Open workspace…", self.choose_workspace, "open", QKeySequence.StandardKey.Open)
        self.act_reload = a("&Reload", self.reload, "refresh", "Ctrl+R", tip="Reload the workspace from disk (Ctrl+R)")
        self.act_import_matrix = a("&Import matrix…", self.import_matrix, "import")
        self.act_open_folder = a("Open workspace &folder", lambda: self.open_path("."), "folder")
        self.act_quit = a("&Quit", self.close, None, QKeySequence.StandardKey.Quit)
        self.act_run = a("&Run", self.run_selected, "run", "F5", tint="ok", tip="Run the selected simulation (F5)")
        self.act_stop = a("&Stop", self.stop_job, "stop", "Shift+F5", tint="error", tip="Stop the job shown in the console (Shift+F5)")
        self.act_run_batch = a("Run &batch…", self.run_batch, "batch")
        self.act_save = a("&Save", self.save_current, "save", QKeySequence.StandardKey.Save, tip="Save the simulation's parameters (Ctrl+S)")
        self.act_revert = a("Re&vert", self.revert_current, None)
        self.act_save_preset = a("Save as &preset…", lambda: self.save_as_preset(self._current_sim()), "presets")
        self.act_compare = a("&Compare parameters…", lambda: self.compare(self._current_sim(), None), "compare")
        self.act_new_sim = a("&New simulation…", self.new_simulation, "simulation", "Ctrl+Shift+N")
        self.act_rename_sim = a("&Rename simulation…", lambda: self.rename_simulation(self._current_sim()), "rename")
        self.act_delete_sim = a("&Delete simulation…", lambda: self.delete_simulation(self._current_sim()), "delete")
        self.act_validate = a("&Check parameters", self.show_problems, "validate", "F7")
        self.act_preview = a("&Preview coarsening", lambda: self._select_stage("coarsening"), "coarsening", "F6")
        self.act_auto_select = a("&Auto-select parameters", lambda: self.auto_select(self._current_sim()), "tuning")
        self.act_demo_matrix = a("&Generate demo matrix…", self.generate_demo_matrix, "matrix")
        self.act_undo = self.undo_group.createUndoAction(self, "&Undo")
        self.act_undo.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self._theme.bind_icon(self.act_undo, "undo")
        self.act_redo = self.undo_group.createRedoAction(self, "&Redo")
        self.act_redo.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        self._theme.bind_icon(self.act_redo, "redo")
        self.act_new_study = a("&New study…", lambda: self.new_study(self._current_sim()), "add")
        self.act_edit_batch = a("&Edit configuration", lambda: self.select_key("batch_config"), "settings")
        self.act_help = a("&Documentation", self.show_help, "docs", "F1", tip="Documentation for the selected item or parameter (F1)")
        self.act_reset_layout = a("&Reset layout", self.reset_layout)
        self.act_gallery = a("&Widget gallery", self.show_gallery)
        self.act_about = a(f"&About {APP_NAME}", self.about)
        self.theme_group = QActionGroup(self)
        self.theme_actions: dict[str, QAction] = {}
        for mode in MODES:
            action = QAction(THEME_LABELS[mode], self, checkable=True)
            action.setChecked(mode == self._theme.mode)
            action.triggered.connect(lambda _checked=False, m=mode: self.set_theme(m))
            self.theme_group.addAction(action)
            self.theme_actions[mode] = action
        self.act_toggle_theme = QAction("Switch light/dark theme", self)
        self.act_toggle_theme.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.act_toggle_theme.triggered.connect(self.toggle_theme)
        self._update_theme_toggle()
        self._theme.changed.connect(self._update_theme_toggle)  # also when following the system

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.act_new_workspace, self.act_open_workspace])
        self.recent_menu = file_menu.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        file_menu.addActions([self.act_reload, self.act_open_folder])
        file_menu.addSeparator()
        file_menu.addActions([self.act_new_sim, self.act_import_matrix, self.act_demo_matrix])
        file_menu.addSeparator()
        file_menu.addActions([self.act_save, self.act_save_preset, self.act_revert])
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)
        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.act_undo, self.act_redo])
        sim_menu = bar.addMenu("&Simulation")
        sim_menu.addActions([self.act_validate, self.act_preview])
        sim_menu.addSeparator()
        sim_menu.addActions([self.act_run, self.act_stop])
        sim_menu.addSeparator()
        sim_menu.addActions([self.act_auto_select, self.act_compare])
        sim_menu.addSeparator()
        sim_menu.addActions([self.act_rename_sim, self.act_delete_sim])
        batch_menu = bar.addMenu("&Batch")
        batch_menu.addActions([self.act_edit_batch, self.act_run_batch])
        tuning_menu = bar.addMenu("&Tuning")
        tuning_menu.addActions([self.act_auto_select, self.act_new_study])
        view_menu = bar.addMenu("&View")
        for dock in self.docks:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addAction(self.bottom.action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addActions(list(self.theme_actions.values()))
        view_menu.addSeparator()
        view_menu.addAction(self.act_reset_layout)
        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_help)
        help_menu.addSeparator()
        help_menu.addAction(self.act_gallery)
        help_menu.addSeparator()
        help_menu.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main", self)
        bar.setObjectName("MainToolBar")
        bar.setMovable(False)
        bar.setFloatable(False)
        size = self._theme.tokens.metrics.icon_toolbar
        bar.setIconSize(QSize(size, size))
        bar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        bar.addActions([self.act_new_workspace, self.act_open_workspace, self.act_save])
        bar.addSeparator()
        bar.addActions([self.act_undo, self.act_redo])
        bar.addSeparator()
        bar.addActions([self.act_validate, self.act_run, self.act_stop])
        bar.addSeparator()
        bar.addActions([self.act_compare, self.act_import_matrix, self.act_reload])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        bar.addAction(self.act_toggle_theme)
        for action in (self.act_run, self.act_stop):
            bar.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(bar)
        self.toolbar = bar

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(8, 0, 6, 0)
        self.status_icon = QLabel()
        self.status_icon.setFixedSize(16, 16)
        self.status_job = QLabel()
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 100)
        self.status_progress.setTextVisible(False)
        self.status_progress.setFixedWidth(120)
        self.status_percent = QLabel()
        self.status_running = QLabel()
        self.status_workspace = QLabel()
        for widget in (self.status_icon, self.status_job, self.status_progress, self.status_percent):
            bar.addWidget(widget)
        bar.addPermanentWidget(self.status_running)
        bar.addPermanentWidget(self.status_workspace)
        # A temporary message ("Saved …") is drawn where the job labels are: hide them meanwhile.
        bar.messageChanged.connect(lambda message: self._update_status())
        self._theme.changed.connect(self._update_status)
        self._update_status()

    # ---------------------------------------------------------------- context
    def _connect_context(self) -> None:
        self.ctx.bridge.jobChanged.connect(self._on_job_changed)

    def _on_job_changed(self, event: str, job_id: str) -> None:
        self.jobs.schedule_refresh()
        if job_id == self.console.job_id:
            self.console.pull()
        if event == "finished":
            job = self.ctx.jobs.get_job(job_id, log_offset=10**9) or {}
            if job.get("status") == "completed":
                self.statusBar().showMessage(f"{job.get('title')} finished.", 6000)
            elif job.get("status") == "failed":
                self.statusBar().showMessage(f"{job.get('title')} failed: {job.get('error_message') or 'see the console'}", 10000)
            self.reload()
        self._update_status()

    def _follow_job(self, job_id: str) -> None:
        self.console.follow(job_id)
        self._update_status()

    def _update_status(self) -> None:
        job = self.ctx.jobs.get_job(self.console.job_id, log_offset=10**9) if self.console.job_id else None
        running = job is not None and job["status"] == "running"
        show_job = job is not None and not self.statusBar().currentMessage()
        for widget in (self.status_icon, self.status_job, self.status_progress, self.status_percent):
            widget.setVisible(show_job)
        if job is not None:
            icon, tint = {"running": ("running", "accent"), "completed": ("ok", "ok"), "failed": ("error", "error")}.get(job["status"], ("cancelled", "muted"))
            self.status_icon.setPixmap(self._theme.pixmap(icon, 16, tint, self.devicePixelRatioF()))
            stage = job_stage(job) if running else job["status"].capitalize()
            target = job.get("demonstrator_id") or job["title"]
            self.status_job.setText(f"{target} · {stage}")
            self.status_progress.setValue(int(job.get("stage_progress") or 0))
            self.status_progress.setVisible(running and show_job)
            self.status_percent.setText(f"{job.get('stage_progress', 0)} %")
            self.status_percent.setVisible(running and show_job)
        count = len(self.ctx.jobs.running_jobs())
        self.status_running.setText(f"{count} job running" if count == 1 else f"{count} jobs running")
        self.status_workspace.setText(_short_path(self.ctx.root))
        self.status_workspace.setToolTip(str(self.ctx.root))
        self.act_stop.setEnabled(running)

    # ---------------------------------------------------------------- project
    def reload(self) -> None:
        self.ctx.tasks.run(self._load_snapshot, self._on_snapshot, self._on_snapshot_error, key="snapshot")

    def _load_snapshot(self) -> ProjectSnapshot:
        return load_snapshot(self.ctx.jobs)

    def _on_snapshot(self, snap: ProjectSnapshot) -> None:
        self.snapshot = snap
        known = {sim["id"] for sim in snap.simulations if not sim.get("error")}
        for sim_id in [s for s in self.docs if s not in known]:
            self._drop_document(sim_id)
        for sim in snap.simulations:
            doc = self.docs.get(sim["id"])
            if doc is not None and not sim.get("error"):
                doc.reload_from(sim)
        self.project.set_snapshot(snap)
        self._refresh_problems()
        if self.project.current_node() is None:
            self.project.select_kind("simulation") or self.project.select_kind("matrices")

    def _on_snapshot_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, APP_NAME, f"The workspace could not be read:\n\n{exc}")

    def select_key(self, key: str) -> None:
        if not self.project.select_key(key):
            self._reload_and_select(key)  # a new run may not be in the tree yet

    def select_node(self, kind: str) -> bool:
        return self.project.select_kind(kind)

    def _breadcrumb(self) -> list[str]:
        index = self.project.tree.currentIndex()
        names = []
        while index.isValid():
            names.insert(0, index.data(Qt.ItemDataRole.DisplayRole))
            index = index.parent()
        return names

    def _current_sim(self) -> str | None:
        node = self.project.current_node()
        return node.simulation_id if node else None

    def _select_stage(self, kind: str, sim_id: str | None = None, focus: str | None = None) -> None:
        sim_id = sim_id or self._current_sim()
        if not sim_id:
            return
        self._pending_focus = focus
        key = f"simulation:{sim_id}" if kind == "simulation" else f"{kind}:{sim_id}"
        if not self.project.select_key(key):
            self._pending_focus = None

    def _on_node_selected(self, node: Node | None) -> None:
        sim_id = node.simulation_id if node else None
        for action in (self.act_run, self.act_save_preset, self.act_compare, self.act_rename_sim, self.act_delete_sim,
                       self.act_preview, self.act_auto_select, self.act_new_study):
            action.setEnabled(bool(sim_id))
        doc = self.docs.get(sim_id) if sim_id else None
        if node is not None and node.kind == "batch_config" and self.batch_doc is not None:
            self.undo_group.setActiveStack(self.batch_doc.undo)
        else:
            self.undo_group.setActiveStack(doc.undo if doc else None)
        self._update_dirty_state()
        if node is None:
            self.settings_panel.show_header(None, [])
            self.settings_panel.show_text("Select an item in the project tree.")
            self.graphics.clear()
            return
        self.settings_panel.show_header(node, self._breadcrumb())
        self.settings_panel.show_text("Loading…")
        self._show_context_plot(node)
        if node.kind in sim_pages.BUILDERS and node.kind != "preset" and doc is not None:
            self._show_page(node, None)  # the open document is the source of truth
            return
        if node.kind == "batch_config":
            self.ctx.tasks.run(self._load_batch, lambda data, n=node: self._show_batch_config(n, data),
                               lambda exc, n=node: self._show_page_error(n, exc), key="page")
            return
        jobs = self.ctx.jobs
        self.ctx.tasks.run(
            lambda: pages.load(node, jobs),
            lambda data, n=node: self._show_page(n, data),
            lambda exc, n=node: self._show_page_error(n, exc),
            key="page",
        )

    # Plot area for items that have no plot of their own.
    _PLACEHOLDERS = {
        "matrices": "Select a matrix to see its sparsity pattern.",
        "simulations": "Select a simulation to see its latest run, or its matrix if it has not run yet.",
        "batch": "Select a batch run to compare its methods.",
        "batch_runs": "Select a batch run to compare its methods.",
        "batch_config": "The plan on the left lists every case. Run the batch, then select its run to compare methods.",
        "hardware": "Nothing to plot for the hardware checks.",
    }
    _SIMULATION_CONTEXT = ("simulation", "partitioning", "refinement", "outputs", "presets", "preset", "results")

    def _show_context_plot(self, node: Node) -> None:
        kind = node.kind
        if kind == "matrix":
            self.graphics.show_matrix(node.data["matrix"])
        elif kind in self._SIMULATION_CONTEXT:
            self._show_simulation_context(node.simulation_id)
        elif kind == "tuning":
            self._show_latest_study(node.simulation_id)
        elif kind in self._PLACEHOLDERS:
            self.graphics.clear(self._PLACEHOLDERS[kind])
        # input, coarsening, run, study and batch_run pages draw their own plot

    def _show_simulation_context(self, sim_id: str) -> None:
        """The simulation's latest successful run, else its input matrix."""
        sim = self._simulation_data(sim_id) if self.snapshot else None
        matrix = ((sim or {}).get("simulation_config") or {}).get("input_matrix")

        def load():
            for run in results.list_runs(sim_id)["runs"]:
                if run.get("status") == "completed" and (run.get("can_render_plots") or run.get("kpi_summary")):
                    return run, results.get_run_detail(run["result_dir"])
            return None

        def show(found) -> None:
            node = self.project.current_node()
            if node is None or node.simulation_id != sim_id or node.kind not in self._SIMULATION_CONTEXT:
                return
            if found is not None:
                from .tree import run_label

                run, detail = found
                self.graphics.show_run(run["result_dir"], detail, caption=f"Latest run · {run_label(run)}")
            elif matrix:
                self.graphics.show_matrix(matrix, caption="Input matrix · no successful run yet")
            else:
                self.graphics.clear("This simulation has no matrix and no runs yet.")

        self.ctx.tasks.run(load, show, lambda exc: self.graphics.clear(f"Could not load the latest run: {exc}"), key="graphics")

    def _show_latest_study(self, sim_id: str) -> None:
        jobs = self.ctx.jobs

        def load():
            studies = tuning.list_studies(sim_id, jobs)
            if not studies:
                return None
            labels = {o["key"]: o["label"] for o in tuning.meta()["objectives"]}
            return tuning.get_study(sim_id, studies[0]["id"], jobs), labels

        def show(found) -> None:
            node = self.project.current_node()
            if node is None or node.kind != "tuning" or node.simulation_id != sim_id:
                return
            if found is None:
                self.graphics.clear("No tuning studies yet. Create one to see its trials here.")
                return
            study, labels = found
            self.graphics.show_study(study, labels)
            self.graphics.set_caption(f"Latest study · {study['id']}")

        self.ctx.tasks.run(load, show, lambda exc: self.graphics.clear(f"Could not load the studies: {exc}"), key="graphics")

    def _page_actions(self) -> pages.PageActions:
        return pages.PageActions(
            run_simulation=self.run_simulation,
            open_path=self.open_path,
            export_run=self.export_run,
            select_key=self.select_key,
            compare_runs=self.compare_runs,
            show_batch=self.show_batch_analysis,
            new_study=self.new_study,
            study_action=self.study_action,
            run_task=lambda fn, ok, err, owner=None: self.ctx.tasks.run(fn, ok, err, key="probe", owner=owner),
            show_study=self.show_study,
        )

    # ---------------------------------------------------------------- batch
    @staticmethod
    def _load_batch() -> dict:
        return {"loaded": batch.load_configuration(), "estimates": batch.duration_estimates(), "library": matrices.list_matrices()["matrices"]}

    def _show_batch_config(self, node: Node, data: dict) -> None:
        if self.settings_panel.node is not node:
            return
        if self.batch_doc is None:
            self.batch_doc = BatchDocument(data["loaded"], data["estimates"], self)
            self.batch_doc.dirtyChanged.connect(lambda _d: self._update_dirty_state())
            self.undo_group.addStack(self.batch_doc.undo)
        else:
            self.batch_doc.estimates = data["estimates"]
            self.batch_doc.reload_from(data["loaded"])
        self.undo_group.setActiveStack(self.batch_doc.undo)
        actions = batch_page.BatchActions(save=self.save_batch, revert=self.revert_batch, run=self.run_batch, open_path=self.open_path)
        self.settings_panel.show_widget(batch_page.build_batch_config(self.batch_doc, data["library"], actions).finish())
        self._update_dirty_state()

    def save_batch(self) -> bool:
        doc = self.batch_doc
        if doc is None or not doc.is_dirty():
            return True
        problems = doc.problems()
        if problems:
            QMessageBox.warning(self, "Save batch configuration", "\n".join(problems))
            return False
        try:
            doc.save()
        except ServiceError as exc:
            QMessageBox.warning(self, "Save batch configuration", f"The configuration could not be saved:\n\n{exc}")
            return False
        self.statusBar().showMessage("Saved the batch configuration.", 4000)
        return True

    def revert_batch(self) -> None:
        if self.batch_doc is not None and self.batch_doc.is_dirty():
            if QMessageBox.question(self, "Revert", "Discard the unsaved changes to the batch configuration?") == QMessageBox.StandardButton.Yes:
                self.batch_doc.revert()

    # --------------------------------------------------------------- tuning
    def show_study(self, study: dict) -> None:
        def labels() -> dict:
            return {o["key"]: o["label"] for o in tuning.meta()["objectives"]}

        self.ctx.tasks.run(labels, lambda names: self.graphics.show_study(study, names),
                           lambda exc: self.graphics.clear(f"Could not plot the study: {exc}"), key="graphics")

    def new_study(self, sim_id: str | None) -> None:
        if not sim_id:
            return
        doc = self.docs.get(sim_id)
        if doc is not None and doc.is_dirty():
            answer = QMessageBox.question(self, "New study", f"{sim_id} has unsaved changes. A study starts from the saved parameters. Save them first?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel or (answer == QMessageBox.StandardButton.Yes and not self.save_simulation(sim_id)):
                return
        self.statusBar().showMessage("Preparing the study (matrix features and search space)…")
        self.ctx.tasks.run(
            lambda: (tuning.meta(), tuning.study_defaults(sim_id)),
            lambda result: self._open_study_dialog(sim_id, *result),
            lambda exc: (self.statusBar().clearMessage(), QMessageBox.warning(self, "New study", str(exc))),
        )

    def _open_study_dialog(self, sim_id: str, meta: dict, defaults: dict) -> None:
        self.statusBar().clearMessage()
        dialog = NewStudyDialog(meta, defaults, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self.create_study(sim_id, dialog.request(), dialog.start.isChecked())

    def create_study(self, sim_id: str, request: dict, start: bool) -> dict | None:
        try:
            result = tuning.create_study(sim_id, request, start=start, jobs=self.ctx.jobs)
        except (ServiceError, OSError) as exc:
            QMessageBox.warning(self, "New study", f"The study could not be created:\n\n{exc}")
            return None
        if result.get("job"):
            self._started(result["job"])
        self._reload_and_select(f"study:{sim_id}/{result['study']['id']}")
        return result

    def study_action(self, sim_id: str, study_id: str, action: str) -> None:
        try:
            if action == "stop":
                tuning.stop_study(sim_id, study_id)
                self.statusBar().showMessage(f"{study_id} stops after its current trial.", 6000)
            elif action == "resume":
                self._started(tuning.resume_study(sim_id, study_id, self.ctx.jobs)["job"])
            elif action == "apply":
                doc = self.docs.get(sim_id)
                if doc is not None and doc.is_dirty():
                    if QMessageBox.question(self, "Apply best parameters", f"This replaces the unsaved changes to {sim_id}. Continue?") != QMessageBox.StandardButton.Yes:
                        return
                tuning.apply_study(sim_id, study_id)
                if doc is not None:
                    doc.reset_to(simulations.get_simulation(sim_id))
                self.statusBar().showMessage(f"Applied the best parameters of {study_id} to {sim_id}.", 6000)
            elif action == "delete":
                if QMessageBox.question(self, "Delete study", f"Delete {study_id} and its trial runs? This cannot be undone.") != QMessageBox.StandardButton.Yes:
                    return
                tuning.delete_study(sim_id, study_id, self.ctx.jobs)
                self._reload_and_select(f"tuning:{sim_id}")
                return
        except (ServiceError, OSError) as exc:
            QMessageBox.warning(self, "Tuning", str(exc))
            return
        self._reload_and_select(f"study:{sim_id}/{study_id}")

    # ----------------------------------------------------------------- help
    def show_help(self) -> None:
        """Open the documentation at the parameter that has the focus, else at the selected item's topic."""
        from .editors import FieldEditor

        widget = self.focusWidget()
        while widget is not None and not isinstance(widget, FieldEditor):
            widget = widget.parentWidget()
        shown = False
        if widget is not None:
            doc = self.docs.get(self._current_sim() or "")
            value = doc.value(widget.spec) if doc is not None else None
            from hdd.services import wiki

            topic = wiki.topic_for_parameter(widget.spec.key, value)
            shown = bool(topic) and self.help.show_topic(topic["id"])
        if not shown:
            node = self.project.current_node()
            topic_id = HELP_TOPIC_FOR_NODE.get(node.kind) if node else None
            if topic_id:
                self.help.show_topic(topic_id)
        first = not self.help_dock.isVisible() and not getattr(self, "_help_sized", False)
        left = [self.project_dock.width(), self.settings_dock.width()]
        self.help_dock.show()
        self.help_dock.raise_()
        if first:
            # The panel takes its width from the plot area, not from the tree or the settings.
            self._help_sized = True
            self.resizeDocks([self.project_dock, self.settings_dock, self.help_dock], [*left, 420], Qt.Orientation.Horizontal)

    def compare_runs(self, result_dirs: list[str]) -> None:
        """Overlay the locality curves of up to five runs and list their KPIs side by side."""
        if not result_dirs:
            return
        if len(result_dirs) == 1:
            self.select_key(f"run:{result_dirs[0]}")
            return
        node = self.project.current_node()

        def load() -> list[dict]:
            return [results.get_run_detail(d) for d in result_dirs]

        def show(details: list[dict]) -> None:
            labels = [self._run_label(d) for d in details]
            self.graphics.show_comparison([{"label": label, "curves": d.get("curves")} for label, d in zip(labels, details)])
            page = self.settings_panel.page()
            if self.project.current_node() is node and isinstance(page, pages.Page):
                old = getattr(page, "_comparison", None)
                if old is not None:
                    old.setParent(None)
                section = pages.Section("Comparison")
                section.add(pages.build_comparison_table(details, labels))
                page.box.insertWidget(page.box.count() - 1, section)
                page._comparison = section

        self.ctx.tasks.run(load, show, lambda exc: QMessageBox.warning(self, "Compare runs", str(exc)), key="graphics")

    @staticmethod
    def _run_label(detail: dict) -> str:
        """Short legend label of a run: method, k and time."""
        from hdd.services.catalog import method_label

        pp = (detail.get("run_parameters") or {}).get("partitioning_parameters") or {}
        strategy = pp.get("partitioning_strategy")
        stamp = Path(detail["result_dir"]).name.removeprefix("run_")
        time = f"{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}" if len(stamp) >= 15 else stamp
        if not strategy:
            return time
        simulated = (pp.get("strategies") or {}).get(strategy, {}).get("simulated")
        return f"{method_label(strategy, simulated, short=True)} k={(pp.get('common') or {}).get('k_target')} · {time}"

    def show_batch_analysis(self, batch_id: str, matrix: str, scale: str) -> None:
        def load() -> dict | None:
            analysis = results.batch_analysis(batch_id, matrix)
            return next((c for c in analysis["comparison_curves"] if c["coarsening_size"] == scale), None)

        self.ctx.tasks.run(
            load,
            lambda curve: self.graphics.show_band_concentration(curve, f"{matrix} · {scale} coarsening"),
            lambda exc: self.graphics.clear(f"Could not load the batch analysis: {exc}"),
            key="graphics",
        )

    def _simulation_actions(self) -> sim_pages.SimulationActions:
        return sim_pages.SimulationActions(
            document=self.document_for,
            run=self.run_simulation,
            save=self.save_simulation,
            revert=self.revert_simulation,
            save_as_preset=self.save_as_preset,
            compare=self.compare,
            auto_select=self.auto_select,
            load_preset=self.load_preset,
            activate_preset=self.activate_preset,
            delete_preset=self.delete_preset,
            open_path=self.open_path,
            run_task=lambda fn, ok, err, owner=None: self.ctx.tasks.run(fn, ok, err, key="preview", owner=owner),
            show_coarsening=self._show_coarsening,
            show_matrix=self.graphics.show_matrix,
            matrix_ids=lambda: [m["id"] for m in (self.snapshot.matrices if self.snapshot else [])],
        )

    def _show_page(self, node: Node, data) -> None:
        if self.settings_panel.node is not node:
            return
        if node.kind in sim_pages.BUILDERS:
            if data is None:
                data = self._simulation_data(node.simulation_id)
            page = sim_pages.BUILDERS[node.kind](node, data, self._simulation_actions()).finish()
            doc = self.docs.get(node.simulation_id)
            self.undo_group.setActiveStack(doc.undo if doc else None)
            self._update_dirty_state()
        else:
            page = pages.build(node, data, self._page_actions())
        self.settings_panel.show_widget(page)
        if self._pending_focus and hasattr(page, "focus"):
            page.focus(self._pending_focus)
        self._pending_focus = None
        if node.kind == "run":
            self.graphics.show_run(node.data["result_dir"], data)

    def _simulation_data(self, sim_id: str) -> dict:
        """The simulation as listed in the last snapshot (used when its document already exists)."""
        sims = self.snapshot.simulations if self.snapshot else []
        return next((s for s in sims if s["id"] == sim_id), None) or simulations.get_simulation(sim_id)

    def _show_page_error(self, node: Node, exc: Exception) -> None:
        if self.settings_panel.node is node:
            self.settings_panel.show_widget(pages.build_error(str(exc)))

    def _show_coarsening(self, preview: dict | None) -> None:
        node = self.project.current_node()
        if node is None or node.kind != "coarsening":
            return
        doc = self.docs.get(node.simulation_id)
        if doc is not None:
            cp = doc.params["coarsening_parameters"]
            self.graphics.set_coarsening_limits(cp.get("coarsen_inferior_limit"), cp.get("coarsen_superior_limit"))
        self.graphics.show_coarsening(preview)

    # -------------------------------------------------------------- documents
    def document_for(self, simulation: dict) -> SimulationDocument:
        doc = self.docs.get(simulation["id"])
        if doc is None:
            doc = SimulationDocument(simulation, self)
            doc.dirtyChanged.connect(lambda _d: self._update_dirty_state())
            doc.validated.connect(self._refresh_problems)
            self.undo_group.addStack(doc.undo)
            self.docs[simulation["id"]] = doc
            self._refresh_problems()
        else:
            doc.reload_from(simulation)
        return doc

    def _drop_document(self, sim_id: str) -> None:
        doc = self.docs.pop(sim_id, None)
        if doc is not None:
            self.undo_group.removeStack(doc.undo)
            doc.deleteLater()

    def dirty_documents(self) -> list[SimulationDocument]:
        return [d for d in self.docs.values() if d.is_dirty()]

    def _update_dirty_state(self) -> None:
        if self._batch_selected():
            dirty = bool(self.batch_doc and self.batch_doc.is_dirty())
        else:
            doc = self.docs.get(self._current_sim() or "")
            dirty = bool(doc and doc.is_dirty())
        self.settings_panel.dirty.setVisible(dirty)
        self.act_save.setEnabled(dirty)
        self.act_revert.setEnabled(dirty)
        batch_dirty = bool(self.batch_doc and self.batch_doc.is_dirty())
        self.setWindowModified(bool(self.dirty_documents()) or batch_dirty)
        self._update_title()

    def _refresh_problems(self) -> None:
        rows, targets = [], []
        for severity, message, location in (self.snapshot.problems if self.snapshot else []):
            rows.append((severity, message, location))
            targets.append(None)
        for sim_id, doc in sorted(self.docs.items()):
            for issue in doc.issues:
                stage = sim_pages.node_kind_for_key(issue.key)
                where = {"simulation": "", "input": "Input matrix", "coarsening": "Coarsening", "partitioning": "Partitioning",
                         "refinement": "Refinement"}.get(stage, "")
                rows.append((issue.severity, issue.message, f"{sim_id} › {where}" if where else sim_id))
                targets.append((sim_id, stage, issue.key))
        self._problem_targets = targets
        self.problems.set_rows([[message, location] for _s, message, location in rows], list(range(len(rows))))
        for row, (severity, _m, _l) in enumerate(rows):
            self.problems.item(row, 0).setIcon(self._theme.icon(severity, severity))
        errors = sum(1 for r in rows if r[0] == "error")
        if self._error_count is not None and errors > self._error_count and self.bottom.is_collapsed():
            self.bottom.expand(self.problems_dock)  # a new error opens the panel on it
        self._error_count = errors
        self.problems_dock.setWindowTitle(f"Problems ({len(rows)})" if rows else "Problems")
        self.act_validate.setToolTip(f"Check parameters (F7) — {errors} errors" if errors else "Check parameters (F7)")

    def _go_to_problem(self, row: int) -> None:
        target = self._problem_targets[row] if 0 <= row < len(self._problem_targets) else None
        if target:
            sim_id, stage, key = target
            self._select_stage(stage, sim_id, key)

    def show_problems(self) -> None:
        for doc in self.docs.values():
            doc.validate()
        self.bottom.expand(self.problems_dock)

    def _batch_selected(self) -> bool:
        node = self.project.current_node()
        return node is not None and node.kind == "batch_config"

    def save_current(self) -> None:
        if self._batch_selected():
            self.save_batch()
        elif self._current_sim():
            self.save_simulation(self._current_sim())

    def revert_current(self) -> None:
        if self._batch_selected():
            self.revert_batch()
        elif self._current_sim():
            self.revert_simulation(self._current_sim())

    def save_simulation(self, sim_id: str) -> bool:
        doc = self.docs.get(sim_id)
        if doc is None or not doc.is_dirty():
            return True
        if doc.errors():
            QMessageBox.warning(self, "Save", "Fix the errors listed in the Problems panel before saving.")
            self.show_problems()
            return False
        try:
            doc.save()
        except ServiceError as exc:
            QMessageBox.warning(self, "Save", f"The parameters could not be saved:\n\n{exc}")
            return False
        self.statusBar().showMessage(f"Saved {sim_id} ({doc.active_preset}).", 4000)
        self.reload()
        return True

    def revert_simulation(self, sim_id: str) -> None:
        doc = self.docs.get(sim_id)
        if doc is not None and doc.is_dirty():
            answer = QMessageBox.question(self, "Revert", f"Discard the unsaved changes to {sim_id}?")
            if answer == QMessageBox.StandardButton.Yes:
                doc.revert()

    def save_as_preset(self, sim_id: str | None) -> None:
        if not sim_id:
            return
        doc = self.document_for(self._simulation_data(sim_id))
        name, ok = QInputDialog.getText(self, "Save as preset", "Preset name:", text="my_preset")
        if not ok or not name.strip():
            return
        activate = QMessageBox.question(self, "Save as preset", "Make the new preset the active one?") == QMessageBox.StandardButton.Yes
        try:
            result = doc.save_as_preset(name.strip(), activate)
        except ServiceError as exc:
            QMessageBox.warning(self, "Save as preset", str(exc))
            return
        self.statusBar().showMessage(f"Saved preset for {sim_id}; active: {result['active_parameters_file']}.", 5000)
        self.reload()

    def compare(self, sim_id: str | None, preset: str | None) -> None:
        if not sim_id:
            return
        doc = self.document_for(self._simulation_data(sim_id))
        sources = {"Current (unsaved)": lambda: doc.params, f"Saved ({doc.active_preset})": lambda: doc.saved_params}
        for name in self._simulation_data(sim_id).get("preset_files", []):
            sources[f"Preset {name}"] = lambda n=name: simulations.load_preset(sim_id, n)["parameters"]
        for sim in (self.snapshot.simulations if self.snapshot else []):
            if sim["id"] != sim_id and not sim.get("error"):
                sources[f"Simulation {sim['id']}"] = lambda s=sim: s["simulation_parameters"]
        right = f"Preset {preset}" if preset else f"Saved ({doc.active_preset})"
        CompareDialog(sources, "Current (unsaved)", right, self).exec()

    def auto_select(self, sim_id: str | None) -> None:
        if not sim_id:
            return
        doc = self.document_for(self._simulation_data(sim_id))
        params = doc.params
        self.statusBar().showMessage("Selecting parameters for the matrix…")
        self.ctx.tasks.run(
            lambda: tuning.auto_select(sim_id, params, apply=False),
            lambda result: self._apply_auto_selection(doc, result),
            lambda exc: QMessageBox.warning(self, "Auto-select", str(exc)),
        )

    def _apply_auto_selection(self, doc: SimulationDocument, result: dict) -> None:
        if not result.get("feasible"):
            QMessageBox.information(self, "Auto-select", "No feasible parameter set was found for this matrix.\n\n" + "\n".join(result.get("rationale", [])))
            return
        doc.load_parameters(result["parameters"], "Auto-select parameters")
        detail = "\n".join(f"• {line}" for line in result.get("rationale", []))
        self.statusBar().showMessage("Auto-selected parameters loaded into the editor (not saved yet).", 6000)
        QMessageBox.information(self, "Auto-select", f"Parameters loaded into the editor. Review them, then save.\n\n{detail}")

    def load_preset(self, sim_id: str, preset: str) -> None:
        doc = self.document_for(self._simulation_data(sim_id))
        try:
            parameters = simulations.load_preset(sim_id, preset)["parameters"]
        except ServiceError as exc:
            QMessageBox.warning(self, "Load preset", str(exc))
            return
        doc.load_parameters(parameters, f"Load preset {preset}")
        self.statusBar().showMessage(f"Loaded {preset} into the editor (not saved yet).", 5000)

    def activate_preset(self, sim_id: str, preset: str) -> None:
        doc = self.document_for(self._simulation_data(sim_id))
        if doc.is_dirty():
            answer = QMessageBox.question(self, "Make active", "Switching the active preset discards the unsaved changes. Continue?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        config = dict(doc.saved_config, parameters_file_path=preset)

        def switch() -> dict[str, Any]:  # worker thread: writes the config, reads the new preset
            simulations.save_config(sim_id, config)
            return simulations.get_simulation(sim_id)

        def done(simulation: dict[str, Any]) -> None:
            if self.docs.get(sim_id) is doc:  # not closed or replaced meanwhile
                doc.reset_to(simulation)
            self.reload()

        # A second click supersedes the first (same key), so only the last choice is applied.
        self.ctx.tasks.run(switch, done, lambda exc: QMessageBox.warning(self, "Make active", str(exc)),
                           key=f"activate-preset:{sim_id}")

    def delete_preset(self, sim_id: str, preset: str) -> None:
        if QMessageBox.question(self, "Delete preset", f"Delete {preset}? This cannot be undone.") != QMessageBox.StandardButton.Yes:
            return
        try:
            simulations.delete_preset(sim_id, preset)
        except ServiceError as exc:
            QMessageBox.warning(self, "Delete preset", str(exc))
            return
        self.reload()

    # ----------------------------------------------------------- simulations
    def new_simulation(self) -> None:
        snap = self.snapshot
        matrices_ids = [m["id"] for m in (snap.matrices if snap else []) if m.get("ready", True)]
        sim_ids = [s["id"] for s in (snap.simulations if snap else []) if not s.get("error")]
        dialog = NewSimulationDialog(matrices_ids, sim_ids, simulations.next_simulation_id(), self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        self.statusBar().showMessage("Creating simulation…")
        self.ctx.tasks.run(
            lambda: simulations.create_simulation(**values),
            lambda sim: (self.statusBar().showMessage(f"Created {sim['id']}.", 4000), self._reload_and_select(f"simulation:{sim['id']}")),
            lambda exc: QMessageBox.warning(self, "New simulation", str(exc)),
        )

    def rename_simulation(self, sim_id: str | None) -> None:
        if not sim_id:
            return
        if sim_id in self.docs and self.docs[sim_id].is_dirty() and not self.save_simulation(sim_id):
            return
        if not self._confirm_no_running_job(sim_id, "Rename"):
            return
        name, ok = QInputDialog.getText(self, "Rename simulation", "New name:", text=sim_id)
        if not ok or not name.strip() or name.strip() == sim_id:
            return
        try:
            sim = simulations.rename_simulation(sim_id, name.strip())
        except ServiceError as exc:
            QMessageBox.warning(self, "Rename simulation", str(exc))
            return
        self._drop_document(sim_id)
        self._reload_and_select(f"simulation:{sim['id']}")

    def delete_simulation(self, sim_id: str | None) -> None:
        if not sim_id or not self._confirm_no_running_job(sim_id, "Delete"):
            return
        answer = QMessageBox.warning(
            self, "Delete simulation", f"Delete {sim_id} with all its presets, runs and tuning studies? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.statusBar().showMessage(f"Deleting {sim_id}…")
        self.ctx.tasks.run(  # removing every run and study folder can take a while
            lambda: simulations.delete_simulation(sim_id),
            # The open document goes only once the files are gone: a failed delete keeps its edits.
            lambda _result: (self._drop_document(sim_id), self.statusBar().showMessage(f"Deleted {sim_id}.", 4000),
                             self.reload()),
            lambda exc: (self.statusBar().clearMessage(), QMessageBox.warning(self, "Delete simulation", str(exc)),
                         self.reload()),
        )

    def _confirm_no_running_job(self, sim_id: str, what: str) -> bool:
        busy = [j for j in self.ctx.jobs.list_jobs(None) if j["status"] == "running" and j.get("demonstrator_id") == sim_id]
        if busy:
            QMessageBox.information(self, what, f"{sim_id} has a running job. Stop it first.")
            return False
        return True

    def generate_demo_matrix(self) -> None:
        name, ok = QInputDialog.getText(self, "Generate demo matrix", "Name in the library:", text="demo_fem")
        if not ok or not name.strip():
            return
        self.ctx.tasks.run(
            lambda: matrices.generate_demo_matrix(name.strip()),
            lambda info: self._reload_and_select(f"matrix:{info['id']}"),
            lambda exc: QMessageBox.warning(self, "Generate demo matrix", str(exc)),
        )

    def delete_matrix(self, matrix_id: str) -> None:
        if QMessageBox.question(self, "Delete matrix", f"Delete {matrix_id} from the library? This cannot be undone.") != QMessageBox.StandardButton.Yes:
            return
        try:
            matrices.delete_matrix(matrix_id)
        except ServiceError as exc:
            QMessageBox.warning(self, "Delete matrix", str(exc))
            return
        self.reload()

    def _tree_menu(self, pos) -> None:
        index = self.project.tree.indexAt(pos)
        if not index.isValid():
            return
        node = index.data(Qt.ItemDataRole.UserRole + 1)
        self.project.tree.setCurrentIndex(index)
        menu = QMenu(self)
        if node.simulation_id:
            menu.addActions([self.act_run, self.act_save, self.act_revert])
            menu.addSeparator()
            menu.addActions([self.act_save_preset, self.act_compare, self.act_auto_select, self.act_new_study])
            menu.addSeparator()
            menu.addActions([self.act_rename_sim, self.act_delete_sim])
        elif node.kind == "simulations":
            menu.addAction(self.act_new_sim)
        elif node.kind == "matrices":
            menu.addActions([self.act_import_matrix, self.act_demo_matrix])
        elif node.kind == "matrix":
            action = menu.addAction(self._theme.icon("delete"), "Delete matrix…")
            action.triggered.connect(lambda: self.delete_matrix(node.data["matrix"]))
        elif node.kind in ("batch", "batch_config"):
            menu.addActions([self.act_edit_batch, self.act_run_batch])
        if node.data.get("result_dir"):
            open_action = menu.addAction(self._theme.icon("folder"), "Open folder")
            open_action.triggered.connect(lambda: self.open_path(node.data["result_dir"]))
        if not menu.isEmpty():
            menu.exec(self.project.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------- jobs
    def run_selected(self) -> None:
        node = self.project.current_node()
        if node and node.simulation_id:
            self.run_simulation(node.simulation_id)

    def run_simulation(self, simulation_id: str) -> None:
        doc = self.docs.get(simulation_id)
        override = None
        if doc is not None and doc.is_dirty():
            if doc.errors():
                QMessageBox.warning(self, "Run", "Fix the errors listed in the Problems panel before running.")
                self.show_problems()
                return
            box = QMessageBox(QMessageBox.Icon.Question, "Run", f"{simulation_id} has unsaved changes.", parent=self)
            save_run = box.addButton("Save and run", QMessageBox.ButtonRole.AcceptRole)
            run_only = None
            if doc.config == doc.saved_config:
                run_only = box.addButton("Run without saving", QMessageBox.ButtonRole.ActionRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is save_run:
                if not self.save_simulation(simulation_id):
                    return
            elif run_only is not None and box.clickedButton() is run_only:
                override = doc.params
            else:
                return
        try:
            if override is not None:
                job = self.ctx.jobs.start_single_simulation(f"simulations/{simulation_id}", parameters_override=override)
            else:
                job = self.ctx.run_simulation(simulation_id)
        except (ServiceError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"The simulation could not start:\n\n{exc}")
            return
        self._started(job)

    def _started(self, job: dict) -> None:
        self.jobs.refresh()
        self.jobs.select(job["job_id"], emit=False)
        self.console.follow(job["job_id"])
        self.bottom.expand(self.console_dock)  # a run opens the panel on its live log
        self.statusBar().showMessage(f"Started {job['title']}.", 4000)
        self._update_status()

    def stop_job(self) -> None:
        if self.console.job_id:
            self.ctx.jobs.cancel_job(self.console.job_id)
            self.jobs.refresh()
            self._update_status()

    def run_batch(self) -> None:
        if self.batch_doc is not None and self.batch_doc.is_dirty():
            answer = QMessageBox.question(self, "Run batch", "The batch configuration has unsaved changes. Save them and run?")
            if answer != QMessageBox.StandardButton.Yes or not self.save_batch():
                return
        def prepare() -> tuple[dict[str, Any], dict[str, Any]]:  # worker thread: reads every batch log
            config = batch.load_configuration()
            return config, batch.plan(config["configuration"], batch.duration_estimates())

        self.statusBar().showMessage("Planning the batch…")
        self.ctx.tasks.run(
            prepare,
            lambda result: (self.statusBar().clearMessage(), self._confirm_and_start_batch(*result)),
            lambda exc: (self.statusBar().clearMessage(),
                         QMessageBox.warning(self, APP_NAME, f"The batch cannot run:\n\n{exc}")),
            key="plan-batch",  # clicking twice asks once
        )

    def _confirm_and_start_batch(self, config: dict[str, Any], plan: dict[str, Any]) -> None:
        totals = plan["totals"]
        lines = [f"{config['case_count']} cases will run."]
        if totals["estimated"]:
            lines.append(f"Estimated duration: about {totals['seconds'] / 60:.0f} min.")
        if totals["submissions"]:
            lines.append(f"Remote QPU submissions: {totals['submissions']:,}.")
        if totals["over_capacity"]:
            lines.append(f"{totals['over_capacity']} cases exceed their backend's capacity and will fail.")
        answer = QMessageBox.question(self, "Run batch", "\n".join(lines) + "\n\nStart the batch now?")
        if answer == QMessageBox.StandardButton.Yes:
            self._started(self.ctx.jobs.start_batch_study())

    # ---------------------------------------------------------------- files
    def open_path(self, relative: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str((self.ctx.root / relative).resolve())))

    def export_run(self, result_dir: str) -> None:
        default = str(Path.home() / f"{Path(result_dir).name}_bundle.zip")
        path, _ = QFileDialog.getSaveFileName(self, "Export run", default, "Zip archive (*.zip)")
        if not path:
            return
        self.ctx.tasks.run(
            lambda: results.export_run_bundle(result_dir, path),
            lambda _r: self.statusBar().showMessage(f"Exported {path}", 6000),
            lambda exc: QMessageBox.warning(self, APP_NAME, f"Export failed:\n\n{exc}"),
        )

    def import_matrix(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import matrix", str(Path.home()), "Matrix Market (*.mtx)")
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Import matrix", "Name in the library:", text=Path(path).stem)
        if not ok or not name.strip():
            return
        self.statusBar().showMessage(f"Importing {Path(path).name}…")
        self.ctx.tasks.run(
            lambda: matrices.import_matrix(name, path),
            lambda info: (self.statusBar().showMessage(f"Imported {info['id']}.", 6000), self._reload_and_select(f"matrix:{info['id']}")),
            lambda exc: QMessageBox.warning(self, APP_NAME, f"The matrix could not be imported:\n\n{exc}"),
        )

    def _reload_and_select(self, key: str) -> None:
        self.ctx.tasks.run(self._load_snapshot, lambda snap: (self._on_snapshot(snap), self.project.select_key(key)), self._on_snapshot_error, key="snapshot")

    # ------------------------------------------------------------- workspaces
    def choose_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open workspace", str(self.ctx.root.parent))
        if path:
            self.open_workspace(Path(path))

    def new_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose an empty folder for the new workspace", str(Path.home()))
        if not path:
            return
        folder = Path(path)
        if any(folder.iterdir()) and not workspace.is_workspace(folder):
            answer = QMessageBox.question(self, "New workspace", f"{folder} is not empty. Create the workspace folders inside it anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        workspace.create_workspace(folder)
        self.open_workspace(folder)

    def open_workspace(self, root: Path) -> bool:
        root = root.resolve()
        if root == self.ctx.root:
            self.reload()
            return True
        if not self._confirm_unsaved("Open another workspace"):
            return False
        choice = self._confirm_stop_jobs("Open another workspace")
        if choice is None:
            return False
        # Background work reads and writes the open workspace. Switching while it runs could make
        # it write into the new one, so wait for it, and refuse the switch if it does not finish.
        if not self.ctx.tasks.wait(30000):
            QMessageBox.warning(self, "Open another workspace",
                                "Background work on this workspace is still running. Try again in a moment.")
            return False
        for sim_id in list(self.docs):
            self._drop_document(sim_id)
        if self.batch_doc is not None:
            self.undo_group.removeStack(self.batch_doc.undo)
            self.batch_doc.deleteLater()
            self.batch_doc = None
        if choice == "stop":
            self.ctx.jobs.cancel_all()
        old = self.ctx
        old.close()
        self.ctx = AppContext(root, self)
        old.deleteLater()
        self._connect_context()
        self.graphics.set_tasks(self.ctx.tasks)
        self.jobs.set_manager(self.ctx.jobs)
        self.console = JobConsole(self.ctx.jobs, self.console_panel)
        self.console_panel.view.clear_entries()
        self.project.reset_expansion()
        self._settings.remember_workspace(str(root))
        self._update_title()
        self._update_status()
        self.reload()
        return True

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        for path in self._settings.recent_workspaces():
            action = self.recent_menu.addAction(path)
            action.setEnabled(Path(path).is_dir())
            action.triggered.connect(lambda _c=False, p=path: self.open_workspace(Path(p)))
        if self.recent_menu.isEmpty():
            self.recent_menu.addAction("No recent workspaces").setEnabled(False)

    def _update_title(self) -> None:
        self.setWindowTitle(f"{self.ctx.root.name}[*] — {APP_NAME}")

    def _confirm_unsaved(self, what: str) -> bool:
        """Offer to save edited simulations. Returns False when the user cancels."""
        dirty = self.dirty_documents()
        batch_dirty = bool(self.batch_doc and self.batch_doc.is_dirty())
        if not dirty and not batch_dirty:
            return True
        names = ", ".join([d.simulation_id for d in dirty] + (["the batch configuration"] if batch_dirty else []))
        box = QMessageBox(QMessageBox.Icon.Warning, what, f"Unsaved changes in {names}.", parent=self)
        save = box.addButton("Save all", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is save:
            return all(self.save_simulation(d.simulation_id) for d in dirty) and self.save_batch()
        if box.clickedButton() is discard:
            for doc in dirty:
                doc.revert()
            if self.batch_doc is not None:
                self.batch_doc.revert()
            return True
        return False

    def _confirm_stop_jobs(self, what: str) -> str | None:
        """Ask what to do with running jobs: ``"keep"`` them running, ``"stop"`` them, or ``None`` to cancel."""
        running = self.ctx.jobs.running_jobs()
        if not running:
            return "keep"
        noun = "job is" if len(running) == 1 else "jobs are"
        box = QMessageBox(QMessageBox.Icon.Question, what, f"{len(running)} {noun} still running.", parent=self)
        box.setInformativeText("They can keep running in the background. Opening this workspace again shows their progress and results.")
        keep = box.addButton("Keep running", QMessageBox.ButtonRole.AcceptRole)
        stop = box.addButton("Stop jobs", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(keep)
        box.exec()
        return {id(keep): "keep", id(stop): "stop"}.get(id(box.clickedButton()))

    # ------------------------------------------------------------------- misc
    def set_theme(self, mode: str) -> None:
        self._theme.apply(mode)
        self._settings.set_theme_mode(mode)
        self.theme_actions[mode].setChecked(True)
        self._update_theme_toggle()

    def toggle_theme(self) -> None:
        """Switch between light and dark (leaves "follow system")."""
        self.set_theme("light" if self._theme.tokens.is_dark else "dark")

    def _update_theme_toggle(self) -> None:
        # The button shows where it goes: a moon in light mode, a sun in dark mode.
        dark = self._theme.tokens.is_dark
        self.act_toggle_theme.setIcon(self._theme.icon("theme_light" if dark else "theme_dark"))
        self.act_toggle_theme.setToolTip(f"Switch to the {'light' if dark else 'dark'} theme (Ctrl+Shift+L)")

    def show_gallery(self) -> None:
        from .gallery import Gallery

        self._gallery = Gallery(self._theme)
        self._gallery.show()

    def about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Hybrid quantum-classical graph partitioning and sparse matrix permutation."
            f"<br><br>Workspace: {self.ctx.root}",
        )

    def reset_layout(self) -> None:
        self.bottom.expand()
        self.restoreState(self._default_state, LAYOUT_VERSION)
        self._apply_default_sizes()
        QTimer.singleShot(0, self._sync_dock_titles)

    def _restore_layout(self) -> None:
        geometry, state = self._settings.window_geometry(), self._settings.window_state()
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state, LAYOUT_VERSION)
        else:
            QTimer.singleShot(0, self._apply_default_sizes)
        collapsed, height = self._settings.bottom_panel()
        if height:
            self.bottom.set_height(height)
        if collapsed:
            QTimer.singleShot(0, self.bottom.collapse)  # once the restored layout has settled

    def save_layout(self) -> None:
        self._settings.save_window(self.saveGeometry(), self.saveState(LAYOUT_VERSION))
        self._settings.save_bottom_panel(self.bottom.is_collapsed(), self.bottom.height())

    def closeEvent(self, event: QCloseEvent) -> None:
        choice = self._confirm_stop_jobs("Quit") if self._confirm_unsaved("Quit") else None
        if choice is None:
            event.ignore()
            return
        if choice == "stop":
            self.ctx.jobs.cancel_all()
        self.save_layout()
        self.ctx.close()
        diagnostics.set_reporter(None)
        super().closeEvent(event)

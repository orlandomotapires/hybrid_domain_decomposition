"""Main window: menus, tool bar, dockable panels, graphics area and status bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hdd.services import batch, matrices, results
from hdd.services.catalog import STAGE_LABELS
from hdd.services.errors import ServiceError
from libs.runtime import workspace

from . import APP_NAME, pages
from .context import AppContext
from .graphics.area import GraphicsArea
from .jobs_panel import JobConsole, JobsPanel
from .project import ProjectSnapshot, load_snapshot
from .settings import LAYOUT_VERSION, Settings
from .theme import MODES, Theme
from .tree import Node, ProjectPanel
from .widgets import ConsolePanel
from .widgets.tables import DataTable

THEME_LABELS = {"system": "Follow system", "light": "Light", "dark": "Dark"}


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
        box.addWidget(self.path)
        box.addWidget(self.title)
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


class MainWindow(QMainWindow):
    def __init__(self, theme: Theme, settings: Settings, root: Path) -> None:
        super().__init__()
        self._theme = theme
        self._settings = settings
        self.ctx = AppContext(root, self)
        self.snapshot: ProjectSnapshot | None = None
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

        self.project_dock = self._dock("Project", "ProjectDock", self.project)
        self.settings_dock = self._dock("Settings", "SettingsDock", self.settings_panel)
        self.console_dock = self._dock("Console", "ConsoleDock", self.console_panel)
        self.jobs_dock = self._dock("Jobs", "JobsDock", self.jobs)
        self.problems_dock = self._dock("Problems", "ProblemsDock", self.problems)
        self.docks = [self.project_dock, self.settings_dock, self.console_dock, self.jobs_dock, self.problems_dock]
        left, bottom = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea
        self.addDockWidget(left, self.project_dock)
        self.splitDockWidget(self.project_dock, self.settings_dock, Qt.Orientation.Horizontal)
        self.addDockWidget(bottom, self.console_dock)
        self.tabifyDockWidget(self.console_dock, self.jobs_dock)
        self.tabifyDockWidget(self.jobs_dock, self.problems_dock)
        self.console_dock.raise_()
        self._apply_default_sizes()

    def _dock(self, title: str, name: str, widget: QWidget) -> Dock:
        dock = Dock(title, name, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        for signal in (dock.dockLocationChanged, dock.topLevelChanged, dock.visibilityChanged):
            signal.connect(lambda *_args: QTimer.singleShot(0, self._sync_dock_titles))
        return dock

    def _apply_default_sizes(self) -> None:
        self.resizeDocks([self.project_dock, self.settings_dock], [280, 500], Qt.Orientation.Horizontal)
        self.resizeDocks([self.console_dock], [230], Qt.Orientation.Vertical)

    def _sync_dock_titles(self) -> None:
        for dock in self.docks:
            dock.set_title_visible(not (self.tabifiedDockWidgets(dock) and not dock.isFloating()))

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

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.act_new_workspace, self.act_open_workspace])
        self.recent_menu = file_menu.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        file_menu.addActions([self.act_reload, self.act_open_folder])
        file_menu.addSeparator()
        file_menu.addAction(self.act_import_matrix)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)
        sim_menu = bar.addMenu("&Simulation")
        sim_menu.addActions([self.act_run, self.act_stop])
        batch_menu = bar.addMenu("&Batch")
        batch_menu.addAction(self.act_run_batch)
        view_menu = bar.addMenu("&View")
        for dock in self.docks:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addActions(list(self.theme_actions.values()))
        view_menu.addSeparator()
        view_menu.addAction(self.act_reset_layout)
        help_menu = bar.addMenu("&Help")
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
        bar.addActions([self.act_new_workspace, self.act_open_workspace, self.act_reload])
        bar.addSeparator()
        bar.addActions([self.act_run, self.act_stop])
        bar.addSeparator()
        bar.addAction(self.act_import_matrix)
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
        for widget in (self.status_icon, self.status_job, self.status_progress, self.status_percent):
            widget.setVisible(job is not None)
        if job is not None:
            icon, tint = {"running": ("running", "accent"), "completed": ("ok", "ok"), "failed": ("error", "error")}.get(job["status"], ("cancelled", "muted"))
            self.status_icon.setPixmap(self._theme.pixmap(icon, 16, tint, self.devicePixelRatioF()))
            stage = STAGE_LABELS.get(job.get("current_stage") or "", "") if running else job["status"].capitalize()
            target = job.get("demonstrator_id") or job["title"]
            self.status_job.setText(f"{target} · {stage}")
            self.status_progress.setValue(int(job.get("stage_progress") or 0))
            self.status_progress.setVisible(running)
            self.status_percent.setText(f"{job.get('stage_progress', 0)} %")
            self.status_percent.setVisible(running)
        count = len(self.ctx.jobs.running_jobs())
        self.status_running.setText(f"{count} job running" if count == 1 else f"{count} jobs running")
        self.status_workspace.setText(str(self.ctx.root))
        self.act_stop.setEnabled(running)

    # ---------------------------------------------------------------- project
    def reload(self) -> None:
        self.ctx.tasks.run(load_snapshot, self._on_snapshot, self._on_snapshot_error, key="snapshot")

    def _on_snapshot(self, snap: ProjectSnapshot) -> None:
        self.snapshot = snap
        self.project.set_snapshot(snap)
        self.problems.set_rows([[message, location] for _severity, message, location in snap.problems])
        for row, (severity, _message, _location) in enumerate(snap.problems):
            self.problems.item(row, 0).setIcon(self._theme.icon(severity, severity))
        self.problems_dock.setWindowTitle(f"Problems ({len(snap.problems)})" if snap.problems else "Problems")
        if self.project.current_node() is None:
            self.project.select_kind("simulation") or self.project.select_kind("matrices")

    def _on_snapshot_error(self, exc: Exception) -> None:
        QMessageBox.critical(self, APP_NAME, f"The workspace could not be read:\n\n{exc}")

    def select_key(self, key: str) -> None:
        if not self.project.select_key(key):
            self.reload()  # a new run may not be in the tree yet

    def select_node(self, kind: str) -> bool:
        return self.project.select_kind(kind)

    def _breadcrumb(self) -> list[str]:
        index = self.project.tree.currentIndex()
        names = []
        while index.isValid():
            names.insert(0, index.data(Qt.ItemDataRole.DisplayRole))
            index = index.parent()
        return names

    def _on_node_selected(self, node: Node | None) -> None:
        self.act_run.setEnabled(bool(node and node.simulation_id))
        if node is None:
            self.settings_panel.show_header(None, [])
            self.settings_panel.show_text("Select an item in the project tree.")
            self.graphics.clear()
            return
        self.settings_panel.show_header(node, self._breadcrumb())
        self.settings_panel.show_text("Loading…")
        if node.kind == "matrix":
            self.graphics.show_matrix(node.data["matrix"])
        elif node.kind not in ("input", "run"):
            self.graphics.clear()
        self.ctx.tasks.run(
            lambda: pages.load(node),
            lambda data, n=node: self._show_page(n, data),
            lambda exc, n=node: self._show_page_error(n, exc),
            key="page",
        )

    def _page_actions(self) -> pages.PageActions:
        return pages.PageActions(
            run_simulation=self.run_simulation, open_path=self.open_path, export_run=self.export_run, select_key=self.select_key
        )

    def _show_page(self, node: Node, data) -> None:
        if self.settings_panel.node is not node:
            return
        self.settings_panel.show_widget(pages.build(node, data, self._page_actions()))
        if node.kind == "run":
            self.graphics.show_run(node.data["result_dir"], data)
        elif node.kind == "input":
            matrix = (data.get("matrix") or {}).get("id")
            if matrix and (data.get("matrix") or {}).get("ready", True):
                self.graphics.show_matrix(matrix)
            else:
                self.graphics.clear("The input matrix is not available.")

    def _show_page_error(self, node: Node, exc: Exception) -> None:
        if self.settings_panel.node is node:
            self.settings_panel.show_widget(pages.build_error(str(exc)))

    # ------------------------------------------------------------------- jobs
    def run_selected(self) -> None:
        node = self.project.current_node()
        if node and node.simulation_id:
            self.run_simulation(node.simulation_id)

    def run_simulation(self, simulation_id: str) -> None:
        try:
            job = self.ctx.run_simulation(simulation_id)
        except (ServiceError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"The simulation could not start:\n\n{exc}")
            return
        self._started(job)

    def _started(self, job: dict) -> None:
        self.jobs.refresh()
        self.jobs.select(job["job_id"], emit=False)
        self.console.follow(job["job_id"])
        self.console_dock.raise_()
        self.statusBar().showMessage(f"Started {job['title']}.", 4000)
        self._update_status()

    def stop_job(self) -> None:
        if self.console.job_id:
            self.ctx.jobs.cancel_job(self.console.job_id)
            self.jobs.refresh()
            self._update_status()

    def run_batch(self) -> None:
        try:
            config = batch.load_configuration()
            plan = batch.plan(config["configuration"], batch.duration_estimates())
        except ServiceError as exc:
            QMessageBox.warning(self, APP_NAME, f"The batch cannot run:\n\n{exc}")
            return
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
        self.ctx.tasks.run(load_snapshot, lambda snap: (self._on_snapshot(snap), self.project.select_key(key)), self._on_snapshot_error, key="snapshot")

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
        if any(folder.iterdir()) and not (folder / workspace.STATE_DIR_NAME).exists():
            answer = QMessageBox.question(self, "New workspace", f"{folder} is not empty. Create the workspace folders inside it anyway?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        workspace.init(folder)
        self.open_workspace(folder)

    def open_workspace(self, root: Path) -> bool:
        root = root.resolve()
        if root == self.ctx.root:
            self.reload()
            return True
        if not self._confirm_stop_jobs("Open another workspace"):
            return False
        self.ctx.jobs.cancel_all()
        self.ctx.close()
        self.ctx = AppContext(root, self)
        self._connect_context()
        self.graphics.set_tasks(self.ctx.tasks)
        self.jobs.set_manager(self.ctx.jobs)
        self.console = JobConsole(self.ctx.jobs, self.console_panel)
        self.console_panel.view.clear_entries()
        self.project._loaded = False
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
        self.setWindowTitle(f"{self.ctx.root.name} — {APP_NAME}")

    def _confirm_stop_jobs(self, what: str) -> bool:
        running = self.ctx.jobs.running_jobs()
        if not running:
            return True
        noun = "job is" if len(running) == 1 else "jobs are"
        box = QMessageBox(QMessageBox.Icon.Warning, what, f"{len(running)} {noun} still running. They will be stopped.", parent=self)
        stop = box.addButton("Stop jobs and continue", QMessageBox.ButtonRole.AcceptRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is stop

    # ------------------------------------------------------------------- misc
    def set_theme(self, mode: str) -> None:
        self._theme.apply(mode)
        self._settings.set_theme_mode(mode)
        self.theme_actions[mode].setChecked(True)

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

    def save_layout(self) -> None:
        self._settings.save_window(self.saveGeometry(), self.saveState(LAYOUT_VERSION))

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_stop_jobs("Quit"):
            event.ignore()
            return
        self.ctx.jobs.cancel_all()
        self.save_layout()
        self.ctx.close()
        super().closeEvent(event)

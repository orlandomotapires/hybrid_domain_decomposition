"""Main window: menus, tool bar, dockable panels, graphics area and status bar.

Phase 1 fills the panels with example data (``hdd.studio.prototype``); the
window structure, the docking behaviour and every visual rule are the real ones.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME
from .prototype import pages, sample_data
from .prototype.plots import LocalityPlot, SparsityPlot
from .settings import LAYOUT_VERSION, Settings
from .theme import MODES, Theme
from .widgets import ConsolePanel, segmented
from .widgets.log_view import LogEntry

KIND_ROLE = Qt.ItemDataRole.UserRole + 1
ICON_ROLE = Qt.ItemDataRole.UserRole + 2
ICON_TINT_ROLE = Qt.ItemDataRole.UserRole + 3

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


class ProjectPanel(QWidget):
    """Project tree with a filter field."""

    node_selected = Signal(str, str, list)  # kind, label, breadcrumb

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme = Theme.instance()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter")
        self.filter.setClearButtonEnabled(True)
        self._filter_action = QAction(self.filter)
        theme.bind_icon(self._filter_action, "search", "muted")
        self.filter.addAction(self._filter_action, QLineEdit.ActionPosition.LeadingPosition)

        self.model = QStandardItemModel(self)
        self._populate(self.model.invisibleRootItem(), sample_data.project_tree())
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.filter.textChanged.connect(self._on_filter_changed)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setAnimated(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.selectionModel().currentChanged.connect(self._on_current_changed)
        self._expand_defaults()

        header = QWidget()
        header.setObjectName("ToolRow")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 4, 6, 4)
        header_layout.addWidget(self.filter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.tree, 1)
        theme.changed.connect(self._refresh_icons)

    # --------------------------------------------------------------- populate
    def _populate(self, parent: QStandardItem, nodes: list) -> None:
        theme = Theme.instance()
        for kind, label, icon, tint, children in nodes:
            item = QStandardItem(theme.icon(icon, tint), label)
            item.setData(kind, KIND_ROLE)
            item.setData(icon, ICON_ROLE)
            item.setData(tint, ICON_TINT_ROLE)
            parent.appendRow(item)
            self._populate(item, children)

    def _refresh_icons(self) -> None:
        theme = Theme.instance()
        stack = [self.model.invisibleRootItem()]
        while stack:
            item = stack.pop()
            for row in range(item.rowCount()):
                child = item.child(row)
                child.setIcon(theme.icon(child.data(ICON_ROLE), child.data(ICON_TINT_ROLE)))
                stack.append(child)

    def _expand_defaults(self) -> None:
        """Open the top-level groups and the first simulation, as a returning user would find them."""
        self.tree.expandToDepth(0)
        first_simulation = self.find("simulation")
        if first_simulation.isValid():
            self.tree.expand(first_simulation)
            for row in range(self.proxy.rowCount(first_simulation)):
                child = self.proxy.index(row, 0, first_simulation)
                if child.data(KIND_ROLE) == "results":
                    self.tree.expand(child)

    # ------------------------------------------------------------- navigation
    def find(self, kind: str):
        """Proxy index of the first node of ``kind`` (depth-first), or an invalid index."""
        stack = [self.proxy.index(row, 0) for row in reversed(range(self.proxy.rowCount()))]
        while stack:
            index = stack.pop()
            if index.data(KIND_ROLE) == kind:
                return index
            stack.extend(self.proxy.index(row, 0, index) for row in reversed(range(self.proxy.rowCount(index))))
        return self.proxy.index(-1, -1)

    def select(self, kind: str) -> bool:
        index = self.find(kind)
        if not index.isValid():
            return False
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)
        return True

    def _on_filter_changed(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        if text:
            self.tree.expandAll()
        else:
            self._expand_defaults()

    def _on_current_changed(self, current, _previous) -> None:
        if not current.isValid():
            return
        breadcrumb = []
        index = current
        while index.isValid():
            breadcrumb.insert(0, index.data(Qt.ItemDataRole.DisplayRole))
            index = index.parent()
        self.node_selected.emit(current.data(KIND_ROLE), breadcrumb[-1], breadcrumb)


class SettingsPanel(QWidget):
    """Editor for the node selected in the project tree."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = QLabel()
        self.path.setProperty("role", "caption")
        self.title = QLabel()
        self.title.setProperty("role", "heading")
        header = QWidget()
        header.setObjectName("PanelHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 9)
        header_layout.setSpacing(1)
        header_layout.addWidget(self.path)
        header_layout.addWidget(self.title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.scroll, 1)
        self.kind = ""

    def show_node(self, kind: str, label: str, breadcrumb: list[str]) -> None:
        self.kind = kind
        self.path.setText("  ›  ".join(breadcrumb[:-1]) if len(breadcrumb) > 1 else "Project")
        self.title.setText(label)
        self.scroll.setWidget(pages.build_page(kind, label))


class GraphicsArea(QWidget):
    """Central area: a tab strip with view controls and the plots."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.stack = QStackedWidget()

        self.sparsity = SparsityPlot()
        self.locality = LocalityPlot()
        for title, widget in (("Sparsity", self.sparsity), ("Locality curve", self.locality)):
            self.tabs.addTab(title)
            self.stack.addWidget(widget)

        self.ordering, self._ordering_group = segmented(["Original", "Permuted"], 1)
        self._ordering_group.idClicked.connect(
            lambda index: self.sparsity.set_ordering("original" if index == 0 else "permuted")
        )
        self.fit_button = self._tool("fit", "Fit to window")
        self.fit_button.clicked.connect(lambda: self.stack.currentWidget().fit())
        self.export_button = self._tool("image", "Export image…")

        strip = QWidget()
        strip.setObjectName("TabStrip")
        strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(4, 0, 6, 0)
        strip_layout.setSpacing(6)
        strip_layout.addWidget(self.tabs)
        strip_layout.addStretch(1)
        strip_layout.addWidget(self.ordering)
        strip_layout.addWidget(self.fit_button)
        strip_layout.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(strip)
        layout.addWidget(self.stack, 1)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(0)

    def _tool(self, icon: str, tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setIconSize(QSize(16, 16))
        Theme.instance().bind_icon(button, icon)
        return button

    def _on_tab_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.ordering.setVisible(self.stack.currentWidget() is self.sparsity)

    def show_view(self, name: str) -> None:
        self.tabs.setCurrentIndex(0 if name == "sparsity" else 1)


class MainWindow(QMainWindow):
    def __init__(self, theme: Theme, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._settings = settings
        self.setObjectName("MainWindow")
        self.setWindowTitle(f"{sample_data.WORKSPACE_LABEL} — {APP_NAME}")
        self.resize(1440, 900)
        self.setAnimated(False)
        self.setDockNestingEnabled(True)
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        self.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.BottomDockWidgetArea)

        self.graphics = GraphicsArea()
        self.setCentralWidget(self.graphics)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()

        self.project.node_selected.connect(self._on_node_selected)
        self._default_state = self.saveState(LAYOUT_VERSION)
        self._restore_layout()
        self.project.select("coarsening")
        QTimer.singleShot(0, self._sync_dock_titles)

    # ------------------------------------------------------------------- docks
    def _build_docks(self) -> None:
        self.project = ProjectPanel()
        self.settings_panel = SettingsPanel()
        self.console = ConsolePanel()
        for time, level, message in sample_data.log_lines():
            self.console.view.append_entry(LogEntry(time, level, message))
        self.jobs = self._jobs_table()
        self.problems = self._problems_table()

        self.project_dock = self._dock("Project", "ProjectDock", self.project)
        self.settings_dock = self._dock("Settings", "SettingsDock", self.settings_panel)
        self.console_dock = self._dock("Console", "ConsoleDock", self.console)
        self.jobs_dock = self._dock("Jobs", "JobsDock", self.jobs)
        self.problems_dock = self._dock("Problems", "ProblemsDock", self.problems)
        self.docks = [self.project_dock, self.settings_dock, self.console_dock, self.jobs_dock, self.problems_dock]
        self._arrange_default()

    def _dock(self, title: str, name: str, widget: QWidget) -> Dock:
        dock = Dock(title, name, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        for signal in (dock.dockLocationChanged, dock.topLevelChanged, dock.visibilityChanged):
            signal.connect(lambda *_args: QTimer.singleShot(0, self._sync_dock_titles))
        return dock

    def _arrange_default(self) -> None:
        left, bottom = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea
        self.addDockWidget(left, self.project_dock)
        self.splitDockWidget(self.project_dock, self.settings_dock, Qt.Orientation.Horizontal)
        self.addDockWidget(bottom, self.console_dock)
        self.tabifyDockWidget(self.console_dock, self.jobs_dock)
        self.tabifyDockWidget(self.jobs_dock, self.problems_dock)
        self.console_dock.raise_()
        self._apply_default_sizes()

    def _apply_default_sizes(self) -> None:
        self.resizeDocks([self.project_dock, self.settings_dock], [270, 480], Qt.Orientation.Horizontal)
        self.resizeDocks([self.console_dock], [230], Qt.Orientation.Vertical)

    def _sync_dock_titles(self) -> None:
        """A dock inside a tab group is titled by its tab; hide the redundant title bar."""
        for dock in self.docks:
            tabbed = bool(self.tabifiedDockWidgets(dock)) and not dock.isFloating()
            dock.set_title_visible(not tabbed)

    def _jobs_table(self) -> QTableWidget:
        table = self._table(sample_data.JOB_HEADERS, len(sample_data.JOBS))
        for row, (job, kind, target, state, stage, progress, started, duration) in enumerate(sample_data.JOBS):
            label, _icon, _tint = sample_data.JOB_STATE[state]
            values = (job, kind, target, label, stage, f"{progress} %", started, duration)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column >= 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((90, 96, 210, 130, 170, 92, 84)):
            table.setColumnWidth(column, width)
        for column in (5, 6, 7):
            table.horizontalHeaderItem(column).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._theme.changed.connect(self._restyle_tables)
        return table

    def _problems_table(self) -> QTableWidget:
        table = self._table(sample_data.PROBLEM_HEADERS, len(sample_data.PROBLEMS))
        for row, (_severity, description, location) in enumerate(sample_data.PROBLEMS):
            table.setItem(row, 0, QTableWidgetItem(description))
            table.setItem(row, 1, QTableWidgetItem(location))
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(1, 320)
        return table

    def _table(self, headers: tuple[str, ...], rows: int) -> QTableWidget:
        table = QTableWidget(rows, len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(self._theme.tokens.metrics.row_height)
        table.setShowGrid(False)
        table.setIconSize(QSize(16, 16))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return table

    def _restyle_tables(self) -> None:
        """State icons and numeric fonts depend on the theme."""
        numeric = self._theme.numeric_font()
        for row, job in enumerate(sample_data.JOBS):
            _label, icon, tint = sample_data.JOB_STATE[job[3]]
            self.jobs.item(row, 3).setIcon(self._theme.icon(icon, tint))
            for column in (5, 6, 7):
                self.jobs.item(row, column).setFont(numeric)
        for row, (severity, _description, _location) in enumerate(sample_data.PROBLEMS):
            self.problems.item(row, 0).setIcon(self._theme.icon(severity, severity))

    # ----------------------------------------------------------------- actions
    def _action(self, text: str, icon: str | None = None, shortcut: str | QKeySequence.StandardKey | None = None, tint: str = "default") -> QAction:
        action = QAction(text, self)
        if icon:
            self._theme.bind_icon(action, icon, tint)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda _checked=False, name=text: self._not_available(name))
        return action

    def _not_available(self, name: str) -> None:
        clean = name.replace("&", "").rstrip("…")
        self.statusBar().showMessage(f"“{clean}” is not available in this visual prototype yet.", 4000)

    def _build_actions(self) -> None:
        a = self._action
        self.act_new_workspace = a("&New workspace…", "new", QKeySequence.StandardKey.New)
        self.act_open_workspace = a("&Open workspace…", "open", QKeySequence.StandardKey.Open)
        self.act_new_simulation = a("New &simulation…", "simulation")
        self.act_import_matrix = a("&Import matrix…", "import")
        self.act_save = a("&Save", "save", QKeySequence.StandardKey.Save)
        self.act_export = a("&Export results…", "export")
        self.act_quit = QAction("&Quit", self)
        self.act_quit.setShortcut(QKeySequence(QKeySequence.StandardKey.Quit))
        self.act_quit.triggered.connect(self.close)

        self.act_undo = a("&Undo", "undo", QKeySequence.StandardKey.Undo)
        self.act_redo = a("&Redo", "redo", QKeySequence.StandardKey.Redo)
        self.act_redo.setEnabled(False)
        self.act_preferences = a("&Preferences…", "settings")

        self.act_validate = a("&Validate parameters", "validate", "F7")
        self.act_preview = a("&Preview coarsening", "coarsening", "F6")
        self.act_run = a("&Run", "run", "F5", tint="ok")
        self.act_stop = a("&Stop", "stop", "Shift+F5", tint="error")
        self.act_compare = a("&Compare runs…", "compare")

        self.act_batch_config = a("&Configure batch…", "batch")
        self.act_batch_run = a("&Run batch", "run")
        self.act_auto_select = a("&Auto-select parameters", "tuning")
        self.act_new_study = a("&New study…", "study")

        self.act_reset_layout = QAction("&Reset layout", self)
        self.act_reset_layout.triggered.connect(self.reset_layout)

        self.act_docs = a("&Documentation", "docs", QKeySequence.StandardKey.HelpContents)
        self.act_shortcuts = a("&Keyboard shortcuts")
        self.act_gallery = QAction("&Widget gallery", self)
        self.act_gallery.triggered.connect(self.show_gallery)
        self.act_about = a(f"&About {APP_NAME}")

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
        file_menu.addSeparator()
        file_menu.addActions([self.act_new_simulation, self.act_import_matrix])
        file_menu.addSeparator()
        file_menu.addActions([self.act_save, self.act_export])
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.act_undo, self.act_redo])
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_preferences)

        simulation_menu = bar.addMenu("&Simulation")
        simulation_menu.addActions([self.act_validate, self.act_preview])
        simulation_menu.addSeparator()
        simulation_menu.addActions([self.act_run, self.act_stop])
        simulation_menu.addSeparator()
        simulation_menu.addAction(self.act_compare)

        batch_menu = bar.addMenu("&Batch")
        batch_menu.addActions([self.act_batch_config, self.act_batch_run])

        tuning_menu = bar.addMenu("&Tuning")
        tuning_menu.addActions([self.act_auto_select, self.act_new_study])

        view_menu = bar.addMenu("&View")
        for dock in self.docks:
            view_menu.addAction(dock.toggleViewAction())
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("&Theme")
        theme_menu.addActions(list(self.theme_actions.values()))
        view_menu.addSeparator()
        view_menu.addAction(self.act_reset_layout)

        help_menu = bar.addMenu("&Help")
        help_menu.addActions([self.act_docs, self.act_shortcuts])
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
        bar.addAction(self.act_compare)
        for action in (self.act_run, self.act_stop):
            bar.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for action in bar.actions():
            if not action.isSeparator():
                shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                name = action.text().replace("&", "").rstrip("…")
                action.setToolTip(f"{name} ({shortcut})" if shortcut else name)
        self.addToolBar(bar)
        self.toolbar = bar

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setContentsMargins(8, 0, 6, 0)
        running = sample_data.JOBS[0]
        self.status_job_icon = QLabel()
        self.status_job_icon.setFixedSize(16, 16)
        self.status_job = QLabel(f"{running[2]} · {running[4]}")
        self.status_progress = QProgressBar()
        self.status_progress.setRange(0, 100)
        self.status_progress.setValue(running[5])
        self.status_progress.setTextVisible(False)
        self.status_progress.setFixedWidth(120)
        self.status_percent = QLabel(f"{running[5]} %")
        self.status_workspace = QLabel(sample_data.WORKSPACE_LABEL)
        self.status_qpu = QLabel("QPU: emulated")
        bar.addWidget(self.status_job_icon)
        bar.addWidget(self.status_job)
        bar.addWidget(self.status_progress)
        bar.addWidget(self.status_percent)
        bar.addPermanentWidget(self.status_workspace)
        bar.addPermanentWidget(self.status_qpu)
        self._theme.changed.connect(self._restyle_status)
        self._restyle_status()
        self._restyle_tables()

    def _restyle_status(self) -> None:
        self.status_job_icon.setPixmap(self._theme.pixmap("running", 16, "accent", self.devicePixelRatioF()))

    # ------------------------------------------------------------------ slots
    def _on_node_selected(self, kind: str, label: str, breadcrumb: list) -> None:
        self.settings_panel.show_node(kind, label, breadcrumb)
        if kind == "run":
            self.graphics.show_view("locality")
        elif kind in ("matrix", "input"):
            self.graphics.show_view("sparsity")

    def select_node(self, kind: str) -> bool:
        return self.project.select(kind)

    def set_theme(self, mode: str) -> None:
        self._theme.apply(mode)
        self._settings.set_theme_mode(mode)
        self.theme_actions[mode].setChecked(True)

    def show_gallery(self) -> None:
        from .gallery import Gallery

        self._gallery = Gallery(self._theme)
        self._gallery.show()

    # ------------------------------------------------------------------ layout
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
        self.save_layout()
        super().closeEvent(event)

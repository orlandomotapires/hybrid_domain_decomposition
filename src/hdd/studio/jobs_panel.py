"""Jobs dock (live table of jobs) and the console that follows one job's log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMenu, QTableView, QToolButton, QVBoxLayout, QWidget

from hdd.services.catalog import JOB_STATUS_LABELS, JOB_TYPE_LABELS, STAGE_LABELS
from hdd.services.jobs import JobManager

from .theme import Theme
from .widgets import ConsolePanel
from .widgets.log_view import LogEntry

STATUS_ICON = {"running": ("running", "accent"), "completed": ("ok", "ok"), "failed": ("error", "error"), "cancelled": ("cancelled", "muted")}
COLUMNS = ("Job", "Type", "Target", "State", "Stage", "Progress", "Started", "Duration")
NUMERIC = {5, 6, 7}


def job_target(job: dict[str, Any]) -> str:
    for key in ("demonstrator_id", "study_dir", "batch_dir"):
        if job.get(key):
            return str(job[key]).rstrip("/").split("/")[-1]
    return "—"


def job_stage(job: dict[str, Any]) -> str:
    t = job.get("telemetry") or {}
    if job["job_type"] == "batch" and t.get("batch_total"):
        return f"{t.get('batch_done', 0)} of {t['batch_total']} cases"
    if job["job_type"] == "tuning" and t.get("tuning_total"):
        return f"{t.get('tuning_done', 0)} of {t['tuning_total']} trials"
    if job["status"] == "completed":
        return "Done"
    return STAGE_LABELS.get(job.get("current_stage") or "", "—")


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def format_started(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        stamp = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return stamp.strftime("%H:%M:%S") if stamp.date() == datetime.now().date() else stamp.strftime("%Y-%m-%d %H:%M")


class JobsTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._jobs: list[dict[str, Any]] = []

    def set_jobs(self, jobs: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._jobs = jobs
        self.endResetModel()

    def job(self, row: int) -> dict[str, Any]:
        return self._jobs[row]

    def row_of(self, job_id: str) -> int:
        return next((i for i, j in enumerate(self._jobs) if j["job_id"] == job_id), -1)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._jobs)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole:
                right = section in NUMERIC
                return int((Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        job = self._jobs[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                job["title"],
                JOB_TYPE_LABELS.get(job["job_type"], job["job_type"]),
                job_target(job),
                JOB_STATUS_LABELS.get(job["status"], job["status"]),
                job_stage(job),
                f"{job.get('stage_progress', 0)} %",
                format_started(job.get("created_at")),
                format_duration(job.get("elapsed_sec")),
            )[column]
        if role == Qt.ItemDataRole.DecorationRole and column == 3:
            icon, tint = STATUS_ICON.get(job["status"], ("info", "muted"))
            return Theme.instance().icon(icon, tint)
        if role == Qt.ItemDataRole.TextAlignmentRole and column in NUMERIC:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole and column in NUMERIC:
            return Theme.instance().numeric_font()
        if role == Qt.ItemDataRole.ToolTipRole:
            return job.get("error_message") or job["title"]
        return None


class JobsPanel(QWidget):
    """Table of jobs with Stop / Show result / Remove."""

    jobSelected = Signal(str)
    showResult = Signal(str)  # workspace-relative result folder

    def __init__(self, manager: JobManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self.model = JobsTableModel(self)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.verticalHeader().setVisible(False)
        self.view.verticalHeader().setDefaultSectionSize(Theme.instance().tokens.metrics.row_height)
        self.view.setShowGrid(False)
        self.view.setIconSize(QSize(16, 16))
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.view.doubleClicked.connect(lambda _i: self._show_result())
        header = self.view.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((260, 90, 170, 120, 150, 80, 90)):
            self.view.setColumnWidth(column, width)
        self.view.selectionModel().currentRowChanged.connect(self._on_row)

        self.stop_button = self._tool("stop", "Stop the selected job", self.cancel_selected, "error")
        self.result_button = self._tool("results", "Show the result of the selected job", self._show_result)
        self.remove_button = self._tool("delete", "Remove the selected job from the list", self._remove)
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        row = QWidget()
        row.setObjectName("ToolRow")
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        tools = QHBoxLayout(row)
        tools.setContentsMargins(8, 4, 6, 4)
        tools.setSpacing(4)
        tools.addWidget(self.summary)
        tools.addStretch(1)
        for button in (self.stop_button, self.result_button, self.remove_button):
            tools.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(row)
        layout.addWidget(self.view, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(150)
        self._refresh_timer.timeout.connect(self.refresh)
        self._clock = QTimer(self)  # keeps running durations moving between log lines
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._tick)
        self._clock.start()
        self.refresh()

    def _tool(self, icon: str, tooltip: str, slot, tint: str = "default") -> QToolButton:
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setIconSize(QSize(16, 16))
        Theme.instance().bind_icon(button, icon, tint)
        button.clicked.connect(slot)
        return button

    def set_manager(self, manager: JobManager) -> None:
        self._manager = manager
        self.refresh()

    # ---------------------------------------------------------------- data
    def schedule_refresh(self) -> None:
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def refresh(self) -> None:
        selected = self.selected_job_id()
        jobs = self._manager.list_jobs(limit=200)
        self.model.set_jobs(jobs)
        if selected:
            self.select(selected, emit=False)
        running = sum(1 for j in jobs if j["status"] == "running")
        self.summary.setText(f"{running} running · {len(jobs)} total" if jobs else "No jobs yet")
        self._update_buttons()

    def _tick(self) -> None:
        if any(self.model.job(r)["status"] == "running" for r in range(self.model.rowCount())):
            self.refresh()

    def selected_job_id(self) -> str | None:
        index = self.view.selectionModel().currentIndex()
        return self.model.job(index.row())["job_id"] if index.isValid() and index.row() < self.model.rowCount() else None

    def selected_job(self) -> dict[str, Any] | None:
        index = self.view.selectionModel().currentIndex()
        return self.model.job(index.row()) if index.isValid() and index.row() < self.model.rowCount() else None

    def select(self, job_id: str, emit: bool = True) -> None:
        row = self.model.row_of(job_id)
        if row < 0:
            return
        self.view.selectionModel().blockSignals(not emit)
        self.view.selectRow(row)
        self.view.selectionModel().blockSignals(False)
        self._update_buttons()

    def _on_row(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self._update_buttons()
        if current.isValid():
            self.jobSelected.emit(self.model.job(current.row())["job_id"])

    def _update_buttons(self) -> None:
        job = self.selected_job()
        self.stop_button.setEnabled(bool(job and job["status"] == "running"))
        self.result_button.setEnabled(bool(job and job.get("result_dir")))
        self.remove_button.setEnabled(bool(job and job["status"] != "running"))

    # -------------------------------------------------------------- actions
    def cancel_selected(self) -> None:
        job_id = self.selected_job_id()
        if job_id:
            self._manager.cancel_job(job_id)
            self.refresh()

    def _show_result(self) -> None:
        job = self.selected_job()
        if job and job.get("result_dir"):
            self.showResult.emit(job["result_dir"])

    def _remove(self) -> None:
        job_id = self.selected_job_id()
        if job_id and self._manager.delete_job(job_id):
            self.refresh()

    def _menu(self, pos) -> None:
        if self.selected_job() is None:
            return
        menu = QMenu(self)
        for button, text in ((self.stop_button, "Stop"), (self.result_button, "Show result"), (self.remove_button, "Remove from list")):
            action = QAction(button.icon(), text, menu)
            action.setEnabled(button.isEnabled())
            action.triggered.connect(button.click)
            menu.addAction(action)
        menu.exec(self.view.viewport().mapToGlobal(pos))


class JobConsole:
    """Feeds one job's log into the console panel, pulling only new lines."""

    def __init__(self, manager: JobManager, panel: ConsolePanel) -> None:
        self._manager = manager
        self.panel = panel
        self.job_id: str | None = None
        self._offset = 0

    def follow(self, job_id: str | None) -> None:
        if job_id == self.job_id:
            return
        self.job_id = job_id
        self._offset = 0
        self.panel.view.clear_entries()
        self.pull()

    def pull(self) -> None:
        if not self.job_id:
            return
        snapshot = self._manager.get_job(self.job_id, log_offset=self._offset)
        if snapshot is None:
            return
        for entry in snapshot.get("logs", []):
            self.panel.view.append_entry(LogEntry(entry["timestamp"], entry["level"], entry["message"]))
        self._offset = snapshot["log_count"]

"""Project tree: the workspace as a COMSOL-style model tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QModelIndex, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QAction, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLineEdit, QTreeView, QVBoxLayout, QWidget

from hdd.services.catalog import method_label

from .project import ProjectSnapshot
from .theme import Theme

NODE_ROLE = Qt.ItemDataRole.UserRole + 1

#: Stages of a simulation shown as children, in pipeline order: (kind, label, icon).
SIMULATION_STAGES = (
    ("input", "Input matrix", "matrix"),
    ("coarsening", "Coarsening", "coarsening"),
    ("partitioning", "Partitioning", "partitioning"),
    ("refinement", "Refinement", "refinement"),
    ("outputs", "Outputs", "outputs"),
)


@dataclass
class Node:
    kind: str
    label: str
    icon: str
    key: str  # stable identity across reloads, e.g. "run:simulation_01/run_2026..."
    data: dict[str, Any] = field(default_factory=dict)
    tint: str = "default"
    children: list["Node"] = field(default_factory=list)

    @property
    def simulation_id(self) -> str | None:
        return self.data.get("simulation")


# (icon, tint) of a run in the tree, by outcome.
_RUN_ICON = {"completed": ("ok", "ok"), "failed": ("error", "error"), "incomplete": ("result", "default")}


def run_time(run_id: str) -> str:
    """``run_20261125_000647_474443`` as ``2026-11-25 00:06:47``."""
    stamp = run_id.removeprefix("run_")
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}" if len(stamp) >= 15 else run_id


def run_label(run: dict[str, Any]) -> str:
    pretty = run_time(run["run_id"])
    if run.get("status") == "failed":
        return f"{pretty} · failed"
    strategy = run.get("partitioning_strategy")
    if not strategy or strategy == "unknown":
        return f"{pretty} · incomplete"
    return f"{pretty} · {method_label(strategy, run.get('simulated'), short=True)}"


def build_nodes(snap: ProjectSnapshot) -> list[Node]:
    matrices = Node("matrices", "Matrices", "matrices", "matrices", children=[
        Node("matrix", m["id"], "matrix", f"matrix:{m['id']}", {"matrix": m["id"]}, "error" if m.get("error") else "default")
        for m in snap.matrices
    ])
    sims = Node("simulations", "Simulations", "simulations", "simulations")
    for sim in snap.simulations:
        sid = sim["id"]
        base = {"simulation": sid}
        if sim.get("error"):
            sims.children.append(Node("simulation", sid, "simulation", f"simulation:{sid}", base, "error"))
            continue
        node = Node("simulation", sid, "simulation", f"simulation:{sid}", base)
        node.children = [Node(kind, label, icon, f"{kind}:{sid}", dict(base)) for kind, label, icon in SIMULATION_STAGES]
        presets = Node("presets", "Presets", "presets", f"presets:{sid}", dict(base))
        for preset in sim.get("preset_files", []):
            active = preset == sim.get("active_parameters_file")
            presets.children.append(Node("preset", f"{preset} (active)" if active else preset, "file", f"preset:{sid}/{preset}", {**base, "preset": preset}))
        tuning = Node("tuning", "Tuning", "tuning", f"tuning:{sid}", dict(base), children=[
            Node("study", s["id"], "study", f"study:{sid}/{s['id']}", {**base, "study": s["id"]}, "accent" if s.get("running_job_id") else "default")
            for s in snap.studies.get(sid, [])
        ])
        runs = Node("results", "Results", "results", f"results:{sid}", dict(base), children=[
            Node("run", run_label(r), _RUN_ICON.get(r.get("status"), ("result", "default"))[0], f"run:{r['result_dir']}",
                 {**base, "result_dir": r["result_dir"], "run": r["run_id"]}, _RUN_ICON.get(r.get("status"), ("result", "default"))[1])
            for r in snap.runs.get(sid, [])
        ])
        node.children += [presets, tuning, runs]
        sims.children.append(node)
    batch = Node("batch", "Batch", "batch", "batch", children=[
        Node("batch_config", "Configuration", "settings", "batch_config", tint="default" if snap.has_batch_config else "warning"),
        Node("batch_runs", "Runs", "history", "batch_runs", children=[
            Node("batch_run", b["id"], "error" if b.get("failed_cases") else "result", f"batch_run:{b['id']}", {"batch": b["id"]},
                 "error" if b.get("failed_cases") else "default")
            for b in snap.batch_runs
        ]),
    ])
    hardware = Node("hardware", "Quantum hardware", "hardware", "hardware")
    return [matrices, sims, batch, hardware]


class ProjectPanel(QWidget):
    """Tree plus filter. Emits ``nodeSelected`` with the selected :class:`Node` (or None)."""

    nodeSelected = Signal(object)
    nodeActivated = Signal(object)  # double click / Enter

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
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.filter.textChanged.connect(self._on_filter)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setAnimated(False)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.selectionModel().currentChanged.connect(self._on_current)
        self.tree.activated.connect(lambda index: self.nodeActivated.emit(index.data(NODE_ROLE)))

        header = QWidget()
        header.setObjectName("ToolRow")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(header)
        row.setContentsMargins(6, 4, 6, 4)
        row.addWidget(self.filter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self.tree, 1)
        theme.changed.connect(self._refresh_icons)
        self._loaded = False

    # --------------------------------------------------------------- content
    def set_snapshot(self, snap: ProjectSnapshot) -> None:
        """Rebuild the tree, keeping the selection and the expanded branches."""
        expanded = self._expanded_keys()
        current = self.current_node()
        first_load = not self._loaded
        self.tree.selectionModel().blockSignals(True)
        self.model.clear()
        self._append(self.model.invisibleRootItem(), build_nodes(snap))
        self.tree.selectionModel().blockSignals(False)
        if first_load:
            self.tree.expandToDepth(0)
            first_sim = self.find_kind("simulation")
            if first_sim.isValid():
                self.tree.expand(first_sim)
        else:
            for key in expanded:
                index = self.find_key(key)
                if index.isValid():
                    self.tree.expand(index)
        self._loaded = True
        if current is not None and self.select_key(current.key):
            return
        self.nodeSelected.emit(None)

    def _append(self, parent: QStandardItem, nodes: list[Node]) -> None:
        theme = Theme.instance()
        for node in nodes:
            item = QStandardItem(theme.icon(node.icon, node.tint), node.label)
            item.setData(node, NODE_ROLE)
            item.setToolTip(node.label)
            parent.appendRow(item)
            self._append(item, node.children)

    def _refresh_icons(self) -> None:
        theme = Theme.instance()
        stack = [self.model.invisibleRootItem()]
        while stack:
            item = stack.pop()
            for row in range(item.rowCount()):
                child = item.child(row)
                node = child.data(NODE_ROLE)
                child.setIcon(theme.icon(node.icon, node.tint))
                stack.append(child)

    # ------------------------------------------------------------- navigation
    def _walk(self, parent: QModelIndex | None = None):
        parent = parent or QModelIndex()
        for row in range(self.proxy.rowCount(parent)):
            index = self.proxy.index(row, 0, parent)
            yield index
            yield from self._walk(index)

    def find_key(self, key: str) -> QModelIndex:
        return next((i for i in self._walk() if i.data(NODE_ROLE).key == key), QModelIndex())

    def find_kind(self, kind: str) -> QModelIndex:
        return next((i for i in self._walk() if i.data(NODE_ROLE).kind == kind), QModelIndex())

    def select_key(self, key: str) -> bool:
        index = self.find_key(key)
        return self._select(index)

    def select_kind(self, kind: str) -> bool:
        return self._select(self.find_kind(kind))

    def _select(self, index: QModelIndex) -> bool:
        if not index.isValid():
            return False
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        already_current = self.tree.currentIndex() == index
        self.tree.setCurrentIndex(index)  # emits through currentChanged when it moves
        self.tree.scrollTo(index)
        if already_current:
            self.nodeSelected.emit(index.data(NODE_ROLE))
        return True

    def current_node(self) -> Node | None:
        index = self.tree.currentIndex()
        return index.data(NODE_ROLE) if index.isValid() else None

    def _expanded_keys(self) -> list[str]:
        return [i.data(NODE_ROLE).key for i in self._walk() if self.tree.isExpanded(i)]

    def _on_filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text)
        if text:
            self.tree.expandAll()

    def _on_current(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if current.isValid():
            self.nodeSelected.emit(current.data(NODE_ROLE))

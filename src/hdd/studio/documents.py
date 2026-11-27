"""Editable simulation: a working copy of its parameters and configuration with undo, validation and save."""

from __future__ import annotations

import copy
import json
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from hdd.services import batch, catalog, simulations
from hdd.services.catalog import ParamSpec, get_path, set_path

_MERGE_ID = 4711


class Issue:
    """A validation finding. ``key`` is the parameter it is about, when known."""

    def __init__(self, severity: str, message: str, key: str | None = None) -> None:
        message = message.replace(">=", "≥").replace("<=", "≤")
        self.severity, self.message, self.key = severity, message, key

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Issue({self.severity!r}, {self.message!r}, {self.key!r})"


class _SetValue(QUndoCommand):
    def __init__(self, doc: "SimulationDocument", target: str, path: tuple[str, ...], old: Any, new: Any, text: str) -> None:
        super().__init__(text)
        self.doc, self.target, self.path, self.old, self.new = doc, target, path, old, new

    def id(self) -> int:
        return _MERGE_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        # Consecutive edits of one field (spin box steps, typing) undo as one step.
        if not isinstance(other, _SetValue) or (other.target, other.path) != (self.target, self.path):
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        self.doc._apply(self.target, self.path, self.new)

    def undo(self) -> None:
        self.doc._apply(self.target, self.path, self.old)


class _Replace(QUndoCommand):
    def __init__(self, doc: "SimulationDocument", old: dict, new: dict, text: str) -> None:
        super().__init__(text)
        self.doc, self.old, self.new = doc, old, new

    def redo(self) -> None:
        self.doc._replace(self.new)

    def undo(self) -> None:
        self.doc._replace(self.old)


class Binding(QObject):
    """Connects a signal to any callable for as long as ``owner`` lives.

    Lambdas and closures connected directly stay connected after the widget that
    created them is destroyed; routing them through a child QObject disconnects
    them together with their owner.
    """

    def __init__(self, owner: QObject, signal, fn) -> None:
        super().__init__(owner)
        self._fn = fn
        signal.connect(self._call)

    def _call(self, *args) -> None:
        self._fn(*args)


def bind(owner: QObject, signal, fn) -> Binding:
    return Binding(owner, signal, fn)


def _labels() -> dict[str, str]:
    return {spec.key: spec.label for spec in catalog.ALL_SPECS}


class SimulationDocument(QObject):
    changed = Signal(str)  # parameter key, "config.<key>", or "" when everything may have changed
    dirtyChanged = Signal(bool)
    validated = Signal()
    saved = Signal()

    def __init__(self, simulation: dict[str, Any], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.simulation_id: str = simulation["id"]
        self.undo = QUndoStack(self)
        self.undo.cleanChanged.connect(self._on_clean_changed)
        self.issues: list[Issue] = []
        self._validate_timer = QTimer(self)
        self._validate_timer.setSingleShot(True)
        self._validate_timer.setInterval(150)
        self._validate_timer.timeout.connect(self.validate)
        self._load(simulation)

    def _on_clean_changed(self, clean: bool) -> None:
        self.dirtyChanged.emit(not clean)

    # ------------------------------------------------------------------ state
    def _load(self, simulation: dict[str, Any]) -> None:
        self.saved_params = copy.deepcopy(simulation["simulation_parameters"])
        self.saved_config = copy.deepcopy(simulation["simulation_config"])
        self.active_preset: str = simulation.get("active_parameters_file", "simulation_parameters.json")
        self.params = copy.deepcopy(self.saved_params)
        self.config = copy.deepcopy(self.saved_config)
        self.validate()

    def reload_from(self, simulation: dict[str, Any]) -> bool:
        """Take the files' current state when nothing is being edited. Returns True when it reloaded."""
        if self.is_dirty():
            return False
        if simulation["simulation_parameters"] == self.saved_params and simulation["simulation_config"] == self.saved_config:
            return False
        self.reset_to(simulation)
        return True

    def reset_to(self, simulation: dict[str, Any]) -> None:
        """Take the files' state, discarding any edits and the undo history."""
        self.undo.clear()
        self._load(simulation)
        self.changed.emit("")

    def is_dirty(self) -> bool:
        return not self.undo.isClean()

    def value(self, spec: ParamSpec) -> Any:
        return get_path(self.params, spec.path)

    def strategy(self) -> str:
        return self.params["partitioning_parameters"]["partitioning_strategy"]

    # ---------------------------------------------------------------- editing
    def set_value(self, spec: ParamSpec, value: Any) -> None:
        old = get_path(self.params, spec.path)
        if old == value:
            return
        self.undo.push(_SetValue(self, "params", spec.path, copy.deepcopy(old), value, f"Change {spec.label.lower()}"))

    def set_config(self, key: str, value: Any, text: str) -> None:
        old = self.config.get(key)
        if old == value:
            return
        self.undo.push(_SetValue(self, "config", (key,), copy.deepcopy(old), copy.deepcopy(value), text))

    def load_parameters(self, parameters: dict[str, Any], text: str) -> None:
        """Replace every parameter (a preset, an auto-selection) as one undoable step."""
        normalized = simulations.validate_and_normalize_simulation_parameters(copy.deepcopy(parameters))
        # Keep the blocks of strategies the incoming set does not define.
        strategies = {**self.params["partitioning_parameters"].get("strategies", {}), **normalized["partitioning_parameters"]["strategies"]}
        normalized["partitioning_parameters"]["strategies"] = strategies
        if normalized == self.params:
            return
        self.undo.push(_Replace(self, copy.deepcopy(self.params), normalized, text))

    def _apply(self, target: str, path: tuple[str, ...], value: Any) -> None:
        if target == "params":
            set_path(self.params, path, copy.deepcopy(value))
            self.changed.emit(".".join(path))
        else:
            self.config[path[0]] = copy.deepcopy(value)
            self.changed.emit(f"config.{path[0]}")
        self._validate_timer.start()

    def _replace(self, params: dict[str, Any]) -> None:
        self.params = copy.deepcopy(params)
        self.changed.emit("")
        self._validate_timer.start()

    # ------------------------------------------------------------- validation
    def validate(self) -> list[Issue]:
        issues: list[Issue] = []
        result = simulations.validate_parameters(copy.deepcopy(self.params))
        if not result["valid"]:
            spec = catalog.spec_for_error(result["error"])
            issues.append(Issue("error", self._readable(result["error"]), spec.key if spec else None))
        else:
            normalized = result["normalized_parameters"]
            strategy = normalized["partitioning_parameters"]["partitioning_strategy"]
            block = normalized["partitioning_parameters"]["strategies"].get(strategy, {})
            capacity = batch.capacity_for(strategy, block)
            upper = normalized["coarsening_parameters"].get("coarsen_superior_limit")
            ceiling = upper if upper is not None else normalized["coarsening_parameters"]["coarsen_inferior_limit"]
            if capacity and ceiling > capacity["limit"]:
                issues.append(Issue(
                    "error",
                    f"The coarse graph may have up to {ceiling} nodes, but {capacity['what']} handles at most {capacity['limit']}. "
                    f"Lower the coarsening upper limit to {capacity['limit']} or less.",
                    "coarsening_parameters.coarsen_superior_limit",
                ))
            k = normalized["partitioning_parameters"]["common"]["k_target"]
            if upper is not None and upper < k:
                issues.append(Issue("error", f"The coarse graph ({upper} nodes at most) cannot be split into k = {k} parts.",
                                    "partitioning_parameters.common.k_target"))
            for warning in (result.get("estimates") or {}).get("warnings", []):
                issues.append(Issue("warning", warning))
        if not self.config.get("input_matrix") or self.config.get("input_matrix") == "none":
            issues.append(Issue("error", "Choose an input matrix.", "config.input_matrix"))
        self.issues = issues
        self.validated.emit()
        return issues

    @staticmethod
    def _readable(message: str) -> str:
        """Replace dotted parameter keys in a validation message with their labels."""
        for key, label in sorted(_labels().items(), key=lambda kv: -len(kv[0])):
            message = message.replace(key, label)
        return message[:1].upper() + message[1:]

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def issue_for(self, key: str) -> Issue | None:
        return next((i for i in self.issues if i.key == key and i.severity == "error"), None)

    def estimates(self) -> dict[str, Any]:
        result = simulations.validate_parameters(copy.deepcopy(self.params))
        return result.get("estimates") or {}

    # ------------------------------------------------------------------- save
    def save(self) -> dict[str, Any]:
        """Write the active preset (and the configuration when it changed). Raises ServiceError."""
        if self.config != self.saved_config:
            simulations.save_config(self.simulation_id, self.config)
        result = simulations.save_parameters(self.simulation_id, self.params)
        self.saved_params = copy.deepcopy(result["simulation_parameters"])
        self.saved_config = copy.deepcopy(result["simulation_config"])
        self.params = copy.deepcopy(self.saved_params)
        self.undo.setClean()
        self.saved.emit()
        return result

    def save_as_preset(self, filename: str, set_active: bool) -> dict[str, Any]:
        result = simulations.save_preset(self.simulation_id, filename, copy.deepcopy(self.params), set_active)
        if set_active:
            self.active_preset = result["active_parameters_file"]
            self.saved_params = copy.deepcopy(result["simulation_parameters"])
            self.undo.setClean()
        self.saved.emit()
        return result

    def revert(self) -> None:
        self.undo.clear()
        self.params = copy.deepcopy(self.saved_params)
        self.config = copy.deepcopy(self.saved_config)
        self.changed.emit("")
        self.validate()
        self.dirtyChanged.emit(False)

    def unsaved_summary(self) -> str:
        changes = catalog.diff(self.saved_params, self.params)
        return json.dumps([c[0] for c in changes])

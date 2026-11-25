"""Editable batch configuration: a working copy of ``batch/batch_configuration.json`` with undo and save."""

from __future__ import annotations

import copy
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from hdd.services import batch

_MERGE_ID = 4712


class _Edit(QUndoCommand):
    """Replaces the whole configuration. Consecutive edits of one field merge into one undo step."""

    def __init__(self, doc: "BatchDocument", old: dict, new: dict, text: str, merge_key: str | None) -> None:
        super().__init__(text)
        self.doc, self.old, self.new, self.merge_key = doc, old, new, merge_key

    def id(self) -> int:
        return _MERGE_ID if self.merge_key else -1

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, _Edit) or other.merge_key != self.merge_key:
            return False
        self.new = other.new
        return True

    def redo(self) -> None:
        self.doc._set(self.new)

    def undo(self) -> None:
        self.doc._set(self.old)


class BatchDocument(QObject):
    changed = Signal()
    dirtyChanged = Signal(bool)

    def __init__(self, loaded: dict[str, Any], estimates: dict[str, Any] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.undo = QUndoStack(self)
        self.undo.cleanChanged.connect(lambda clean: self.dirtyChanged.emit(not clean))
        self.estimates = estimates
        self.saved = copy.deepcopy(loaded["configuration"])
        self.config = copy.deepcopy(self.saved)

    # ------------------------------------------------------------------ state
    def is_dirty(self) -> bool:
        return not self.undo.isClean()

    def edit(self, text: str, change: Callable[[dict[str, Any]], None], merge_key: str | None = None) -> None:
        """Apply ``change`` to a copy of the configuration as one undoable step."""
        new = copy.deepcopy(self.config)
        change(new)
        if new != self.config:
            self.undo.push(_Edit(self, copy.deepcopy(self.config), new, text, merge_key))

    def _set(self, config: dict[str, Any]) -> None:
        self.config = copy.deepcopy(config)
        self.changed.emit()

    def reload_from(self, loaded: dict[str, Any]) -> bool:
        """Take the file's current state when nothing is being edited. Returns True when it reloaded."""
        if self.is_dirty():
            return False
        self.saved = copy.deepcopy(loaded["configuration"])
        self.undo.clear()
        self._set(self.saved)
        return True

    def revert(self) -> None:
        self.undo.clear()
        self._set(self.saved)

    def save(self) -> dict[str, Any]:
        """Validate and write the configuration. Raises ``ServiceError`` when it is invalid."""
        result = batch.save_configuration(copy.deepcopy(self.config))
        self.saved = copy.deepcopy(self.config)
        self.undo.setClean()
        return result

    # --------------------------------------------------------------- derived
    def plan(self) -> dict[str, Any]:
        return batch.plan(self.config, self.estimates)

    def problems(self) -> list[str]:
        """What stops this configuration from running, in words."""
        out = []
        if not self.config.get("matrices"):
            out.append("Choose at least one matrix.")
        keys = [p.get("key") for p in self.config.get("coarsening_presets", [])]
        for preset in self.config.get("coarsening_presets", []):
            low, high = preset.get("coarsen_inferior_limit"), preset.get("coarsen_superior_limit")
            if high is not None and low is not None and low > high:
                out.append(f"Scale {preset.get('key')}: the lower limit is above the upper limit.")
        if len(set(keys)) != len(keys):
            out.append("Two coarsening scales have the same name.")
        if not batch.dry_run_cases(self.config):
            out.append("No case is selected: tick at least one scale for one method.")
        return out

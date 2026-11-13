"""Simulations API. Thin adapter over ``hdd.services.simulations``.

"Demonstrators" are simulations; the route prefix keeps its historical name.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from hdd.services import simulations

router = APIRouter(prefix="/api/demonstrators", tags=["matrices"])

# Used by backend.routes.tuning.
_sanitize_dem_name = simulations.sanitize_simulation_id


class CreateDemonstratorRequest(BaseModel):
    # Empty -> next free simulation_NN.
    name: str | None = None
    # Copy parameters/presets (and matrix) from this simulation.
    clone_from: str | None = None
    # Library matrix to use; defaults to the cloned simulation's matrix, else the first library matrix.
    matrix: str | None = None


class SavePresetRequest(BaseModel):
    filename: str
    parameters: dict[str, Any]
    set_active: bool = True


class RenameDemonstratorRequest(BaseModel):
    new_name: str


@router.get("")
def list_demonstrators() -> dict[str, Any]:
    return simulations.list_simulations()


@router.get("/{dem_id}")
def get_demonstrator(dem_id: str) -> dict[str, Any]:
    return simulations.get_simulation(dem_id)


@router.post("")
def create_demonstrator(req: CreateDemonstratorRequest) -> dict[str, Any]:
    return simulations.create_simulation(name=req.name, clone_from=req.clone_from, matrix=req.matrix)


@router.put("/{dem_id}/config")
def update_simulation_config(dem_id: str, config_payload: dict[str, Any]) -> dict[str, Any]:
    return simulations.save_config(dem_id, config_payload)


@router.put("/{dem_id}/parameters")
def update_simulation_parameters(dem_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    return simulations.save_parameters(dem_id, params_payload)


@router.get("/{dem_id}/presets/{preset_file}")
def get_parameter_preset(dem_id: str, preset_file: str) -> dict[str, Any]:
    return simulations.load_preset(dem_id, preset_file)


@router.post("/{dem_id}/presets")
def save_parameter_preset(dem_id: str, req: SavePresetRequest) -> dict[str, Any]:
    return simulations.save_preset(dem_id, req.filename, req.parameters, req.set_active)


@router.post("/validate-parameters")
def validate_parameters_endpoint(params_payload: dict[str, Any]) -> dict[str, Any]:
    return simulations.validate_parameters(params_payload)


@router.put("/{dem_id}/rename")
def rename_demonstrator(dem_id: str, req: RenameDemonstratorRequest) -> dict[str, Any]:
    return simulations.rename_simulation(dem_id, req.new_name)


@router.delete("/{dem_id}")
def delete_demonstrator(dem_id: str) -> dict[str, Any]:
    return simulations.delete_simulation(dem_id)


@router.delete("/{dem_id}/presets/{preset_file}")
def delete_parameter_preset(dem_id: str, preset_file: str) -> dict[str, Any]:
    return simulations.delete_preset(dem_id, preset_file)


@router.post("/{dem_id}/preview-coarsening")
def preview_coarsening_trajectory(dem_id: str, params_payload: dict[str, Any]) -> dict[str, Any]:
    return simulations.preview_coarsening(dem_id, params_payload)

from __future__ import annotations

import configparser
import importlib.metadata
import importlib.util
import os
import platform
import sys
from pathlib import Path
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel

from libs.multilevel_scheme.partitioning.qa import (
    get_qlm_qpu_api_summary,
    get_qpu_dense_clique_capacity,
)

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


class DWaveCheckRequest(BaseModel):
    qpu_solver_name: str | None = "Advantage2_system2.1"
    qpu_region: str | None = "eu-central-1"


class QLMInspectRequest(BaseModel):
    qlm_qpu_name: str | None = "qat.qpus:QSolidQPU10"


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


def _dwave_credentials() -> dict[str, Any]:
    """Report whether a D-Wave Leap token is configured (env var or dwave config file). Never returns the token."""
    if os.environ.get("DWAVE_API_TOKEN"):
        return {"ok": True, "detail": "DWAVE_API_TOKEN environment variable is set"}
    try:
        from dwave.cloud.config import load_config

        cfg = load_config()
        if cfg.get("token"):
            region = cfg.get("region")
            return {
                "ok": True,
                "detail": f"Token found in dwave config{f' (region {region})' if region else ''}",
            }
        return {
            "ok": False,
            "detail": "No Leap API token found. Run `dwave setup` or set DWAVE_API_TOKEN.",
        }
    except Exception as exc:
        return {"ok": False, "detail": f"Could not read dwave config: {type(exc).__name__}"}


def _qlm_connection_config() -> dict[str, Any]:
    """Best-effort check for a QLMaaS connection config (env vars or ~/.qlmaas/config.ini)."""
    env_keys = [k for k in os.environ if k.startswith("QLMAAS_")]
    if env_keys:
        return {"ok": True, "detail": f"QLMaaS settings from environment ({', '.join(sorted(env_keys))})"}
    cfg_file = Path.home() / ".qlmaas" / "config.ini"
    if cfg_file.exists():
        return {"ok": True, "detail": f"QLMaaS config found at {cfg_file}"}
    return {
        "ok": False,
        "detail": "No QLMaaS config found (~/.qlmaas/config.ini or QLMAAS_* variables). Use Inspect below to test the connection.",
    }


# (distribution name, display name, what the studio uses it for)
_VERSIONED_PACKAGES: list[tuple[str, str, str]] = [
    ("numpy", "numpy", "Array maths for matrices and metrics"),
    ("scipy", "scipy", "Sparse matrix I/O, permutation and profiling"),
    ("networkx", "networkx", "Graph construction, coarsening and refinement"),
    ("pymetis", "pymetis", "METIS classical partitioning"),
    ("pennylane", "pennylane", "QAOA emulation (gate-based simulator)"),
    ("dwave-neal", "dwave-neal", "Quantum annealing emulation (simulated annealing)"),
    ("dwave-system", "dwave-system", "D-Wave QPU samplers and embedding composites"),
    ("dwave-cloud-client", "dwave-cloud-client", "D-Wave Leap connection and credentials"),
    ("minorminer", "minorminer", "Minor embedding onto the D-Wave QPU topology"),
    ("myqlm", "myqlm", "QLM / myQLM gate-based QPU access"),
]


def _package_version(dist: str) -> str | None:
    try:
        return importlib.metadata.version(dist)
    except Exception:
        return None


def _package_versions() -> list[dict[str, Any]]:
    return [
        {"name": name, "version": _package_version(dist), "purpose": purpose}
        for dist, name, purpose in _VERSIONED_PACKAGES
    ]


def _dwave_config_info() -> dict[str, Any]:
    """Which dwave config file / profile would be used. Never returns token values."""
    info: dict[str, Any] = {
        "token_env_set": bool(os.environ.get("DWAVE_API_TOKEN")),
        "token_present": False,
        "config_file": None,
        "config_file_env": os.environ.get("DWAVE_CONFIG_FILE") or None,
        "profile": os.environ.get("DWAVE_PROFILE") or None,
        "region": None,
        "error": None,
    }
    try:
        from dwave.cloud.config import get_configfile_path, load_config
    except Exception:
        info["error"] = "dwave-cloud-client not installed"
        info["token_present"] = info["token_env_set"]
        return info
    try:
        cfg_path = info["config_file_env"] or get_configfile_path()
        if cfg_path:
            info["config_file"] = str(cfg_path)
            if not info["profile"]:
                parser = configparser.ConfigParser()
                parser.read(cfg_path)
                default_profile = parser.defaults().get("profile")
                sections = parser.sections()
                info["profile"] = default_profile or (sections[0] if sections else None)
    except Exception as exc:
        info["error"] = f"Could not locate dwave config: {type(exc).__name__}"
    try:
        cfg = load_config()
        info["token_present"] = info["token_env_set"] or bool(cfg.get("token"))
        info["region"] = cfg.get("region") or None
    except Exception as exc:
        info["token_present"] = info["token_env_set"]
        info["error"] = info["error"] or f"Could not read dwave config: {type(exc).__name__}"
    return info


def _qlmaas_config_info() -> dict[str, Any]:
    cfg_file = Path.home() / ".qlmaas" / "config.ini"
    return {
        "config_file": str(cfg_file) if cfg_file.exists() else None,
        "expected_config_file": str(cfg_file),
        "env_vars": sorted(k for k in os.environ if k.startswith("QLMAAS_")),
    }


def _environment_info() -> dict[str, Any]:
    try:
        dwave = _dwave_config_info()
    except Exception as exc:  # pragma: no cover - best effort
        dwave = {"error": f"{type(exc).__name__}"}
    try:
        qlmaas = _qlmaas_config_info()
    except Exception as exc:  # pragma: no cover - best effort
        qlmaas = {"error": f"{type(exc).__name__}"}
    return {
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "dwave": dwave,
        "qlmaas": qlmaas,
    }


def _sdk_check(installed: bool, packages: str) -> dict[str, Any]:
    return {
        "ok": installed,
        "detail": f"{packages} installed" if installed else f"Missing: pip install {packages}",
    }


@router.get("/status")
def get_environment_status() -> dict[str, Any]:
    packages = {
        "numpy": _is_installed("numpy"),
        "scipy": _is_installed("scipy"),
        "networkx": _is_installed("networkx"),
        "pymetis": _is_installed("pymetis"),
        "pennylane": _is_installed("pennylane"),
        "dwave_neal": _is_installed("neal"),
        "dwave_system": _is_installed("dwave.system"),
        "minorminer": _is_installed("minorminer"),
        "myqlm_qat": _is_installed("qat"),
    }

    dwave_sdk = packages["dwave_system"] and packages["minorminer"]
    dwave_creds = _dwave_credentials() if dwave_sdk else {"ok": False, "detail": "Install the SDK first"}
    qlm_cfg = _qlm_connection_config() if packages["myqlm_qat"] else {"ok": False, "detail": "Install the SDK first"}

    backends: dict[str, dict[str, Any]] = {
        "metis": {
            "label": "METIS (Classical)",
            "description": "Classical weighted multilevel k-way partitioning via PyMETIS",
            "checks": [_sdk_check(packages["pymetis"], "pymetis")],
        },
        "qa_emulated": {
            "label": "Quantum Annealing (Emulated)",
            "description": "Local simulated annealing QUBO solver via dwave-neal",
            "checks": [_sdk_check(packages["dwave_neal"], "dwave-neal")],
        },
        "qa_hardware": {
            "label": "Quantum Annealing (D-Wave QPU)",
            "description": "Remote D-Wave Leap QPU via dwave-system",
            "checks": [_sdk_check(dwave_sdk, "dwave-system minorminer"), {"label": "Credentials", **dwave_creds}],
            "remote": True,
        },
        "qaoa_emulated": {
            "label": "QAOA (Emulated)",
            "description": "Local gate-based QAOA simulator via PennyLane",
            "checks": [_sdk_check(packages["pennylane"], "pennylane")],
        },
        "qaoa_hardware": {
            "label": "QAOA (QLM Hardware)",
            "description": "Remote QLM / myQLM gate-based QPU",
            "checks": [_sdk_check(packages["myqlm_qat"], "myqlm"), {"label": "Connection config", **qlm_cfg}],
            "remote": True,
        },
    }
    for info in backends.values():
        info["checks"][0]["label"] = "SDK"
        info["ready"] = all(c["ok"] for c in info["checks"])
        # Remote backends are only confirmed by a live probe; local ones are ready once installed.
        info["status"] = (
            "missing_sdk"
            if not info["checks"][0]["ok"]
            else "needs_credentials"
            if not info["ready"]
            else "configured"
            if info.get("remote")
            else "ready"
        )

    return {
        "packages": packages,
        "backends": backends,
        "python_version": platform.python_version(),
        "package_versions": _package_versions(),
        "environment": _environment_info(),
    }


@router.post("/dwave-check")
def check_dwave_qpu(req: DWaveCheckRequest) -> dict[str, Any]:
    try:
        solver_name, clique_capacity = get_qpu_dense_clique_capacity(
            req.qpu_solver_name,
            req.qpu_region,
        )
        return {
            "reachable": True,
            "solver_name": solver_name,
            "largest_clique_capacity": clique_capacity,
            "region": req.qpu_region,
            "error": None,
        }
    except Exception as exc:
        return {
            "reachable": False,
            "solver_name": req.qpu_solver_name,
            "largest_clique_capacity": None,
            "region": req.qpu_region,
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.post("/qlm-inspect")
def inspect_qlm_qpu(req: QLMInspectRequest) -> dict[str, Any]:
    summary = get_qlm_qpu_api_summary(qlm_qpu_name=req.qlm_qpu_name)
    reachable = "inspection_error" not in summary
    return {
        "reachable": reachable,
        "requested_qpu_name": req.qlm_qpu_name,
        "summary": summary,
    }


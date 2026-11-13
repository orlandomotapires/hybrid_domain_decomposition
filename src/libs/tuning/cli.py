"""Command line entry for the parameter-selection subsystem.

Examples::

    ./run.sh --tune simulations/simulation_01 --n-trials 20 --objectives edge_cut,imbalance
    ./run.sh --tune simulations/simulation_01 --config my_study.json
    ./run.sh --tune --resume simulations/simulation_01/tuning/study_20261105_101500
    ./run.sh --tune simulations/simulation_01 --auto          # Mode A only, prints parameters
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from libs.runtime import workspace
from libs.runtime.utils import resolve_parameters_file_path, validate_and_normalize_simulation_config


def _load_simulation(sim_arg: str) -> tuple[str, dict, dict]:
    sim_dir = Path(sim_arg)
    if not sim_dir.is_absolute():
        sim_dir = (Path.cwd() / sim_dir) if (Path.cwd() / sim_dir).exists() else workspace.root() / sim_dir
    data_dir = sim_dir / "data"
    cfg = validate_and_normalize_simulation_config(json.loads((data_dir / "simulation_config.json").read_text(encoding="utf-8")))
    params_path = resolve_parameters_file_path(data_dir, cfg.get("parameters_file_path"))
    params = json.loads(params_path.read_text(encoding="utf-8"))
    return sim_dir.name, cfg, params


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HDD parameter selection: auto-select or iterative tuning (Optuna)")
    parser.add_argument("simulation_dir", nargs="?", help="Simulation folder, e.g. simulations/simulation_01")
    parser.add_argument("--resume", help="Resume (or run) an existing study folder")
    parser.add_argument("--auto", action="store_true", help="Only run auto-selection (Mode A) and print the result")
    parser.add_argument("--config", help="JSON file with study options (objectives, sampler, search_space, ...)")
    parser.add_argument("--objectives", help="Comma separated: edge_cut,imbalance,band_quality,bandwidth,time")
    parser.add_argument("--aggregation", choices=["pareto", "weighted"])
    parser.add_argument("--sampler", choices=["auto", "tpe", "nsga2", "random", "qmc", "cmaes"])
    parser.add_argument("--n-trials", type=int)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--timeout-sec", type=float)
    parser.add_argument("--patience", type=int)
    parser.add_argument("--free", help="Comma separated search-space keys to set free (e.g. k_target,partitioning_strategy)")
    parser.add_argument("--fixed", help="Comma separated search-space keys to fix")
    args = parser.parse_args(argv)

    from libs.tuning import tuner

    if args.resume:
        tuner.run_study(Path(args.resume).resolve())
        return 0
    if not args.simulation_dir:
        parser.error("simulation_dir is required unless --resume is given")

    sim_name, sim_cfg, base = _load_simulation(args.simulation_dir)
    matrix_id = sim_cfg["input_matrix"]

    if args.auto:
        from libs.tuning.auto_select import auto_select_parameters

        result = auto_select_parameters(matrix_id, base)
        for line in result["rationale"]:
            print(f"[auto] {line}")
        print(json.dumps({"feasible": result["feasible"], "reasons": result["reasons"], "parameters": result["parameters"]}, indent=2))
        return 0 if result["feasible"] else 1

    raw = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
    raw.setdefault("matrix_id", matrix_id)
    raw.setdefault("simulation", sim_name)
    raw.setdefault("base_parameters", base)
    if args.objectives:
        raw["objectives"] = [o.strip() for o in args.objectives.split(",") if o.strip()]
    for key in ("aggregation", "sampler", "n_trials", "repeats", "timeout_sec", "patience"):
        value = getattr(args, key)
        if value is not None:
            raw[key] = value
    space = raw.setdefault("search_space", {})
    for flag, free in ((args.free, True), (args.fixed, False)):
        for key in (flag or "").split(","):
            if key.strip():
                space.setdefault(key.strip(), {})["free"] = free

    config = tuner.normalize_study_config(raw)
    study_dir = tuner.create_study_dir(config)
    print(f"[tuning] study folder: {study_dir}", flush=True)
    tuner.run_study(study_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

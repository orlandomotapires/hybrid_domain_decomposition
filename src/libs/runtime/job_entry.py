"""Single entry point of every background job the Studio starts.

    python -m libs.runtime.job_entry single <simulation_dir> [--payload JSON]
    python -m libs.runtime.job_entry batch [--stop-on-error]
    python -m libs.runtime.job_entry tune <study_dir>

The workspace comes from ``HDD_WORKSPACE``. Output goes to stdout, which the job
manager reads; progress is reported as structured events (``libs.runtime.events``),
and the last event, ``exit``, records the exit code in the log itself so that a job
that finishes while the Studio is closed is still known to have succeeded or failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback

from libs.runtime import events


def _single(simulation_dir: str, payload: dict) -> int:
    from libs.runtime.log import close_log_file, log
    from libs.runtime.runtime import run_simulation

    try:
        out_dir = run_simulation(
            simulation_dir,
            parameters_file_override=payload.get("parameters_file_override"),
            simulation_parameters_override=payload.get("parameters_override"),
        )
        log("INFO", "Simulation Completed Successfully")
        log("VERBOSE", f"Results saved in {out_dir}")
        events.emit("result", result_dir=str(out_dir))
        return 0
    except Exception as exc:
        log("ERROR", f"Simulation failed: {exc}")
        for line in traceback.format_exc().splitlines():
            log("ERROR", line)
        return 1
    finally:
        close_log_file()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m libs.runtime.job_entry")
    sub = parser.add_subparsers(dest="kind", required=True)
    single = sub.add_parser("single", help="run one simulation")
    single.add_argument("simulation_dir", help="workspace-relative simulation folder, e.g. simulations/simulation_01")
    single.add_argument("--payload", default="{}", help="JSON with parameters_override / parameters_file_override")
    batch = sub.add_parser("batch", help="run the workspace's batch configuration")
    batch.add_argument("--stop-on-error", action="store_true")
    tune = sub.add_parser("tune", help="run (or resume) a tuning study")
    tune.add_argument("study_dir")
    args = parser.parse_args(argv)
    code = 1
    try:
        code = _run(args)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        events.emit("exit", code=code)
    return code


def _run(args: argparse.Namespace) -> int:
    if args.kind == "single":
        return _single(args.simulation_dir, json.loads(args.payload))
    if args.kind == "batch":
        from libs.batch.run_batch import main as run_batch

        return int(run_batch(["--stop-on-error"] if args.stop_on_error else []) or 0)
    from libs.tuning.cli import main as run_tuning

    return int(run_tuning(["--resume", args.study_dir]) or 0)


if __name__ == "__main__":
    sys.exit(main())

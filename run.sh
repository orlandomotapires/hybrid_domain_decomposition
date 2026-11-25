#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_python() {
	# An activated environment (a conda env other than base, or a venv) wins over the folders next to this script.
	if [[ -n "${CONDA_PREFIX:-}" && "${CONDA_DEFAULT_ENV:-base}" != "base" && -x "$CONDA_PREFIX/bin/python" ]]; then
		echo "$CONDA_PREFIX/bin/python"
		return
	fi
	if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
		echo "$VIRTUAL_ENV/bin/python"
		return
	fi
	if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
		echo "$ROOT_DIR/.venv/bin/python"
		return
	fi
	if [[ -x "$ROOT_DIR/.env_ocean/bin/python" ]]; then
		echo "$ROOT_DIR/.env_ocean/bin/python"
		return
	fi
	echo "python3"
}

show_usage() {
	echo "Usage:" >&2
	echo "  ./run.sh                     open the desktop app (same as --desktop)" >&2
	echo "  ./run.sh --desktop [--workspace DIR] [--theme system|light|dark] [--gallery]" >&2
	echo "  ./run.sh <simulation_dir>" >&2
	echo "  ./run.sh --run_batch [batch_args...]" >&2
	echo "  ./run.sh --tune <simulation_dir> [--auto | tuning_args...]" >&2
	echo "  ./run.sh --qlm_inspect [inspect_args...]" >&2
	echo "" >&2
	echo "Examples:" >&2
	echo "  ./run.sh simulations/simulation_01" >&2
	echo "  ./run.sh --desktop --workspace ~/hdd-projects/blade" >&2
	echo "  ./run.sh --run_batch --dry-run" >&2
	echo "  ./run.sh --tune simulations/simulation_01 --n-trials 20 --objectives edge_cut,imbalance" >&2
	echo "  ./run.sh --qlm_inspect --help" >&2
}

PYTHON_BIN="$(resolve_python)"

if [[ $# -lt 1 ]]; then
	set -- --desktop
fi

case "$1" in
	--desktop)
		shift
		export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
		exec "$PYTHON_BIN" -m hdd.studio "$@"
		;;
	--run_batch)
		shift
		cd "$ROOT_DIR/src"
		exec "$PYTHON_BIN" -m libs.batch.run_batch "$@"
		;;
	--tune)
		shift
		cd "$ROOT_DIR/src"
		exec "$PYTHON_BIN" -m libs.tuning.cli "$@"
		;;
	--qlm_inspect)
		shift
		cd "$ROOT_DIR/src"
		exec "$PYTHON_BIN" -m libs.multilevel_scheme.partitioning.qaoa.qlm_inspect "$@"
		;;
	--help|-h)
		show_usage
		exit 0
		;;
	--*)
		echo "Unknown option: $1" >&2
		show_usage
		exit 1
		;;
esac

if [[ $# -ne 1 ]]; then
	show_usage
	exit 1
fi

cd "$ROOT_DIR/src"
exec "$PYTHON_BIN" -m main "$1"

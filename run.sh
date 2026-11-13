#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

resolve_python() {
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
	echo "  ./run.sh <simulation_dir>" >&2
	echo "  ./run.sh --ui [--host HOST] [--port PORT] [--reload]" >&2
	echo "  ./run.sh --desktop [--theme system|light|dark] [--gallery]" >&2
	echo "  ./run.sh --run_batch [batch_args...]" >&2
	echo "  ./run.sh --tune <simulation_dir> [--auto | tuning_args...]" >&2
	echo "  ./run.sh --qlm_inspect [inspect_args...]" >&2
	echo "" >&2
	echo "Examples:" >&2
	echo "  ./run.sh simulations/simulation_01" >&2
	echo "  ./run.sh --ui" >&2
	echo "  ./run.sh --run_batch --dry-run" >&2
	echo "  ./run.sh --tune simulations/simulation_01 --n-trials 20 --objectives edge_cut,imbalance" >&2
	echo "  ./run.sh --qlm_inspect --help" >&2
}

if [[ $# -lt 1 ]]; then
	show_usage
	exit 1
fi

PYTHON_BIN="$(resolve_python)"

case "$1" in
	--ui|--studio)
		shift
		if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
			echo "Installing frontend dependencies..."
			npm --prefix "$ROOT_DIR/frontend" install
		fi
		echo "Building frontend studio bundle..."
		npm --prefix "$ROOT_DIR/frontend" run build
		cd "$ROOT_DIR"
		exec "$PYTHON_BIN" -m backend.app "$@"
		;;
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

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Python interpreters to try, best first: the activated conda env or venv, then the folders next to
# this script, then whatever python3 is on PATH.
candidate_pythons() {
	[[ -n "${CONDA_PREFIX:-}" ]] && echo "$CONDA_PREFIX/bin/python"
	[[ -n "${VIRTUAL_ENV:-}" ]] && echo "$VIRTUAL_ENV/bin/python"
	echo "$ROOT_DIR/.venv/bin/python"
	echo "$ROOT_DIR/.env_ocean/bin/python"
	command -v python3 || true
}

# The first candidate that can import the given modules (the pipeline's, plus PySide6 for the app).
resolve_python() {
	local modules="$1" candidate
	while read -r candidate; do
		if [[ -n "$candidate" && -x "$candidate" ]] && "$candidate" -c "import $modules" >/dev/null 2>&1; then
			echo "$candidate"
			return
		fi
	done < <(candidate_pythons)
	echo "No Python environment with the dependencies was found (needs: $modules)." >&2
	echo "Install them into your environment first:  pip install -e \".[gui]\"" >&2
	exit 1
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

if [[ $# -lt 1 ]]; then
	set -- --desktop
fi

if [[ "$1" == "--desktop" ]]; then
	PYTHON_BIN="$(resolve_python "numpy, scipy, networkx, matplotlib, PySide6, pyqtgraph")"
elif [[ "$1" == "--help" || "$1" == "-h" ]]; then
	PYTHON_BIN=""
else
	PYTHON_BIN="$(resolve_python "numpy, scipy, networkx, matplotlib")"
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

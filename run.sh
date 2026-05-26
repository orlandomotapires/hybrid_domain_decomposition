#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_usage() {
	echo "Usage:" >&2
	echo "  ./run <simulation_dir>" >&2
	echo "  ./run --run_batch [batch_args...]" >&2
	echo "  ./run --qlm_inspect [inspect_args...]" >&2
	echo "" >&2
	echo "Examples:" >&2
	echo "  ./run simulations/simulation_01_yannick" >&2
	echo "  ./run --run_batch --dry-run" >&2
	echo "  ./run --qlm_inspect --help" >&2
}

if [[ $# -lt 1 ]]; then
	show_usage
	exit 1
fi

case "$1" in
	--run_batch)
		shift
		if [[ -x "$ROOT_DIR/.env_ocean/bin/python" ]]; then
			exec "$ROOT_DIR/.env_ocean/bin/python" "$ROOT_DIR/batch/run_batch.py" "$@"
		fi
		exec python3 "$ROOT_DIR/batch/run_batch.py" "$@"
		;;
	--qlm_inspect)
		shift
		cd "$ROOT_DIR/src"

		if [[ -x "$ROOT_DIR/.env_ocean/bin/python" ]]; then
			exec "$ROOT_DIR/.env_ocean/bin/python" -m libs.multilevel_scheme.partitioning.qaoa.qlm_inspect "$@"
		fi

		exec python3 -m libs.multilevel_scheme.partitioning.qaoa.qlm_inspect "$@"
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

if [[ -x "$ROOT_DIR/.env_ocean/bin/python" ]]; then
	exec "$ROOT_DIR/.env_ocean/bin/python" -m main "$1"
fi

exec python3 -m main "$1"#!/usr/bin/env bash
from __future__ import annotations

import argparse
from pathlib import Path
import traceback
from libs.runtime.log import (
	log,
	close_log_file,
)
from libs.runtime.runtime import run_simulation

def cli_main(argv: list[str] | None = None) -> None:
	parser = argparse.ArgumentParser(
		description=(
			"Reads <demonstrator_dir>/data/simulation_config.json and the referenced parameters JSON. "
			"Runs the strategy from partitioning_parameters.PARTITIONING_STRATEGY. "
			"Only writes outputs listed in simulation_config.save_output into <demonstrator_dir>/results/<timestamp>/."
		),
		epilog=(
			"Run in background:\n"
			"  nohup ./run demonstrators/demonstrator_01 > demonstrators/demonstrator_01.log 2>&1 &"
		),
		formatter_class=argparse.RawTextHelpFormatter,
	)
	parser.add_argument(
		"demonstrator_dir",
		help="Demonstrator directory, e.g. ./demonstrators/demonstrator_01",
	)

	args = parser.parse_args(argv)

	out_dir: Path | None = None
	try:
		out_dir = run_simulation(args.demonstrator_dir)
		log("INFO", f"Simulation Completed Successfully")
		log("VERBOSE", f"Results saved in {out_dir}")
	except Exception as exc:
		log("ERROR", f"Simulation failed: {exc}")
		for line in traceback.format_exc().splitlines():
			log("ERROR", line)
		raise
	finally:
		close_log_file()

if __name__ == "__main__":
	cli_main()

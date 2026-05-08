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
			"Reads <sim_dir>/data/simulation_config.json and the referenced parameters JSON. "
			"Runs the strategy from partitioning_parameters.PARTITIONING_STRATEGY. "
			"Only writes outputs listed in simulation_config.save_output into <sim_dir>/results/<timestamp>/."
		),
		epilog=(
			"Run in background:\n"
			"  nohup ./scripts/run simulations/simulation_01_yannick > simulation_01_yannick.log 2>&1 &"
		),
		formatter_class=argparse.RawTextHelpFormatter,
	)
	parser.add_argument(
		"simulation_dir",
		help="Simulation directory, e.g. ./simulations/simulation_01",
	)

	args = parser.parse_args(argv)

	out_dir: Path | None = None
	try:
		out_dir = run_simulation(args.simulation_dir)
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

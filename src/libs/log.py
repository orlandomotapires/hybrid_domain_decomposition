from __future__ import annotations

import os
import sys
import time
from io import TextIOBase
from pathlib import Path


class Ansi:
	RESET = "\033[0m"
	BLUE = "\033[34m"
	YELLOW = "\033[33m"
	WHITE = "\033[37m"
	GREEN = "\033[32m"
	RED = "\033[31m"


_log_file: TextIOBase | None = None

def set_log_file(path: str | Path) -> None:
	global _log_file
	log_path = Path(path)
	log_path.parent.mkdir(parents=True, exist_ok=True)
	_log_file = log_path.open("a", encoding="utf-8")


def close_log_file() -> None:
	global _log_file
	if _log_file is not None:
		_log_file.close()
		_log_file = None


def supports_color(stream: TextIOBase) -> bool:
	if os.environ.get("NO_COLOR") is not None:
		return False
	term = os.environ.get("TERM", "")
	if term.lower() == "dumb":
		return False
	return bool(getattr(stream, "isatty", lambda: False)())


def log(level: str, message: str, *, color: str | None = None, stream: TextIOBase | None = None) -> None:
	out = stream or sys.stdout
	prefix = f"[{level}] "
	if supports_color(out) and color:
		out.write(f"{color}{prefix}{message}{Ansi.RESET}\n")
	else:
		out.write(f"{prefix}{message}\n")
	out.flush()
	if _log_file is not None:
		_log_file.write(f"{prefix}{message}\n")
		_log_file.flush()


def info(message: str) -> None:
	log("INFO", message, color=Ansi.WHITE)

def simulation_started(message: str) -> None:
	started_at_hour = time.strftime("%H:%M:%S", time.localtime())
	log("SIMULATION STARTED", f"{message} (started at {started_at_hour} UTC)", color=Ansi.YELLOW)

def simulation_finished(message: str, started_at: float) -> None:
	current_time = time.strftime("%H:%M:%S", time.localtime())
	elapsed_time = time.perf_counter() - started_at
	elapsed_time_hour_format = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
	log("SIMULATION FINISHED", f"{message} (finished at {current_time} UTC) (total elapsed time {elapsed_time_hour_format})", color=Ansi.YELLOW)

def progress(message: str) -> None:
	started_at_hour = time.strftime("%H:%M:%S", time.localtime())
	log("PROGRESS", f"{message} (started at {started_at_hour} UTC)", color=Ansi.BLUE)

def finished(message: str, started_at: float) -> None:
	elapsed_time = time.perf_counter() - started_at
	elapsed_time_hour_format = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
	log("FINISHED", f"{message} (elapsed time {elapsed_time_hour_format})", color=Ansi.GREEN)

def error(message: str) -> None:
	log("ERROR", message, color=Ansi.RED, stream=sys.stderr)

def start_timer() -> float:
	return time.perf_counter()

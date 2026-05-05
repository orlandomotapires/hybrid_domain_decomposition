from __future__ import annotations

from datetime import datetime
import os
import sys
import time
from io import TextIOBase
from pathlib import Path

try:
	from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
	ZoneInfo = None
	ZoneInfoNotFoundError = Exception

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

def _current_timestamp() -> str:
	timezone_name = os.environ.get("APP_TIMEZONE") or os.environ.get("TZ")
	if timezone_name and ZoneInfo is not None:
		try:
			current_dt = datetime.now(ZoneInfo(timezone_name))
			return current_dt.strftime("%d %b %Y %H:%M:%S %Z")
		except ZoneInfoNotFoundError:
			pass

	# Use the host machine's configured local timezone by default.
	return datetime.now().astimezone().strftime("%d %b %Y %H:%M:%S %Z")

def log(log_type: str, message: str) -> None:
	out = sys.stdout
	current_time = _current_timestamp()
	prefix = f"[{current_time} {log_type}] "
	color = {
		"INFO": Ansi.BLUE,
		"WARNING": Ansi.YELLOW,
		"ERROR": Ansi.RED,
		"VERBOSE": Ansi.WHITE,
	}.get(log_type.upper(), Ansi.WHITE)

	out.write(f"{color}{prefix}{message}{Ansi.RESET}\n")
	out.flush()
	if _log_file is not None:
		_log_file.write(f"{prefix} {message}\n")
		_log_file.flush()

def start_timer() -> float:
	return time.perf_counter()

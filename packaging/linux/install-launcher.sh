#!/usr/bin/env bash
# Add HDD Studio to the desktop's application menu for the current user.
#
#   packaging/linux/install-launcher.sh            install (or update)
#   packaging/linux/install-launcher.sh --remove   uninstall
#
# The launcher runs this checkout through run.sh --desktop, so it always starts the
# code in this repository. It remembers the Python that has the app's dependencies
# when you install it (your activated conda env or venv), because the application
# menu does not activate environments. Run it again after switching environments.
# Nothing outside ~/.local/share is touched.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_FILE="$APPS_DIR/hdd-studio.desktop"
ICON_FILE="$ICON_DIR/hdd-studio.svg"

refresh_caches() {
	command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
	command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
}

if [[ "${1:-}" == "--remove" ]]; then
	rm -f "$DESKTOP_FILE" "$ICON_FILE"
	refresh_caches
	echo "Removed the HDD Studio launcher."
	exit 0
fi

PYTHON_BIN="$("$ROOT_DIR/run.sh" --which-python)"  # exits with instructions when none has the dependencies

mkdir -p "$APPS_DIR" "$ICON_DIR"
install -m 0644 "$ROOT_DIR/src/hdd/studio/resources/app/hdd-studio.svg" "$ICON_FILE"
exec_line="env HDD_PYTHON=$PYTHON_BIN \"$ROOT_DIR/run.sh\" --desktop"
sed -e "s|@EXEC@|$exec_line|" -e "s|@TRYEXEC@|$ROOT_DIR/run.sh|" "$ROOT_DIR/packaging/linux/hdd-studio.desktop.in" > "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"
if command -v desktop-file-validate >/dev/null; then
	desktop-file-validate "$DESKTOP_FILE"
fi
refresh_caches
echo "Installed $DESKTOP_FILE (Python: $PYTHON_BIN)"
echo "HDD Studio is now in the application menu. Remove it with: $0 --remove"

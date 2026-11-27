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
SMALL_SIZES=(16x16 24x24 32x32)  # the simplified icon, legible at small sizes

# A value of type string in a desktop entry: a literal backslash is written "\\".
desktop_string() {
	local s=$1 bs='\'
	printf '%s' "${s//"$bs"/"$bs$bs"}"
}

# One Exec argument, quoted as the Desktop Entry spec asks: inside double quotes, '"', '`', '$' and
# '\' are escaped with a backslash, that backslash is itself escaped by the string rule, and '%'
# (a field code) is doubled. The replacements use quoted variables so every bash version treats
# them literally.
desktop_arg() {
	local s=$1 bs='\' dq='"' dl='$' bt='`'
	s=${s//"$bs"/"$bs$bs$bs$bs"}
	s=${s//"$dq"/"$bs$bs$dq"}
	s=${s//"$dl"/"$bs$bs$dl"}
	s=${s//"$bt"/"$bs$bs$bt"}
	s=${s//%/%%}
	printf '"%s"' "$s"
}

refresh_caches() {
	command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
	command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
}

if [[ "${1:-}" == "--remove" ]]; then
	rm -f "$DESKTOP_FILE" "$ICON_FILE"
	for size in "${SMALL_SIZES[@]}"; do rm -f "$DATA_HOME/icons/hicolor/$size/apps/hdd-studio.svg"; done
	refresh_caches
	echo "Removed the HDD Studio launcher."
	exit 0
fi

PYTHON_BIN="$("$ROOT_DIR/run.sh" --which-python)"  # exits with instructions when none has the dependencies

mkdir -p "$APPS_DIR" "$ICON_DIR"
install -m 0644 "$ROOT_DIR/src/hdd/studio/resources/app/hdd-studio.svg" "$ICON_FILE"
for size in "${SMALL_SIZES[@]}"; do
	install -D -m 0644 "$ROOT_DIR/src/hdd/studio/resources/app/hdd-studio-small.svg" "$DATA_HOME/icons/hicolor/$size/apps/hdd-studio.svg"
done
# Paths may contain spaces or characters the desktop entry format treats specially, so the Exec
# arguments are quoted as the Desktop Entry spec asks, and the file is filled in without sed (whose
# replacement text would interpret '&', '|' and '\').
exec_line="env $(desktop_arg "HDD_PYTHON=$PYTHON_BIN") $(desktop_arg "$ROOT_DIR/run.sh") --desktop"
template="$(cat "$ROOT_DIR/packaging/linux/hdd-studio.desktop.in")"
content=${template//@EXEC@/"$exec_line"}
content=${content//@TRYEXEC@/"$(desktop_string "$ROOT_DIR/run.sh")"}
printf '%s\n' "$content" > "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"
if command -v desktop-file-validate >/dev/null; then
	desktop-file-validate "$DESKTOP_FILE"
fi
refresh_caches
echo "Installed $DESKTOP_FILE (Python: $PYTHON_BIN)"
echo "HDD Studio is now in the application menu. Remove it with: $0 --remove"

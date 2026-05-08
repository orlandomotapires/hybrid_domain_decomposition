#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRASH_ROOT="$SCRIPT_DIR/staged_deletions"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_TRASH_DIR="$TRASH_ROOT/$RUN_STAMP"
MOVED_ANYTHING=0

if [[ ! -d "$REPO_ROOT/simulations" || ! -d "$REPO_ROOT/src" ]]; then
    echo "Repository root check failed: $REPO_ROOT" >&2
    exit 1
fi

mkdir -p "$RUN_TRASH_DIR"

move_to_trash() {
    local source_path="$1"
    local relative_path="${source_path#"$REPO_ROOT"/}"
    local destination_path="$RUN_TRASH_DIR/$relative_path"

    mkdir -p "$(dirname "$destination_path")"
    mv "$source_path" "$destination_path"
    echo "Moved $relative_path -> ${destination_path#"$REPO_ROOT"/}"
    MOVED_ANYTHING=1
}

echo "Moving generated outputs into: ${RUN_TRASH_DIR#"$REPO_ROOT"/}"

if [[ -d "$REPO_ROOT/batch_runs" ]]; then
    move_to_trash "$REPO_ROOT/batch_runs"
fi

while IFS= read -r -d '' results_dir; do
    move_to_trash "$results_dir"
done < <(find "$REPO_ROOT/simulations" -mindepth 2 -maxdepth 2 -type d -name results -print0)

if [[ "$MOVED_ANYTHING" -eq 0 ]]; then
    rmdir "$RUN_TRASH_DIR"
    echo "Nothing to move"
else
    echo "Cleanup complete; staged outputs are in ${RUN_TRASH_DIR#"$REPO_ROOT"/}"
fi
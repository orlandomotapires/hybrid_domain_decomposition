#!/bin/bash
# Run parameter sweeps for quantum graph partitioning
# Usage: ./scripts/run_sweep.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_ROOT/.venv"

# Check if venv exists
if [ ! -d "$VENV" ]; then
    echo "❌ Virtual environment not found at $VENV"
    echo "Please create it first: python3 -m venv .venv"
    exit 1
fi

# Activate venv
echo "🔧 Activating virtual environment..."
source "$VENV/bin/activate"

echo "🔬 Running parameter sweep..."
echo "Project root: $PROJECT_ROOT"
echo ""

# Run sweep
cd "$PROJECT_ROOT"
python src/run_parameter_sweep.py

echo ""
echo "✅ Done! Check results/sweeps/ for output"

#!/usr/bin/env bash
# ==============================================================================
# Pre-commit hook: Verify image and registry pins before allowing commit
# Install: cp scripts/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
# ==============================================================================
set -euo pipefail

echo "Running pre-commit image pin verification..."
python3 scripts/verify_pins.py


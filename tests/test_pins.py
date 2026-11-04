"""
Test suite validating pinned container image digests and actions.
Executes scripts/verify_pins.py and ensures all registry pins resolve.
If network is unavailable, skips gracefully and reports NOT VERIFIED.
"""

import sys
import subprocess
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = BASE_DIR / "scripts" / "verify_pins.py"


def test_pinned_image_digests_resolve():
    """Validates that all @sha256: pinned references resolve against their respective registries."""
    assert SCRIPT_PATH.exists(), f"Pin verification script must exist at {SCRIPT_PATH}"

    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
    )

    if proc.returncode == 2:
        pytest.skip("NOT VERIFIED: Public container registries unreachable (no network available)")

    assert proc.returncode == 0, (
        f"Pin verification script failed (exit code {proc.returncode}):\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )


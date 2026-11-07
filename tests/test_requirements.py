import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEV_PACKAGES = {
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "httpx",
    "flake8",
    "mypy",
    "ruff",
    "black",
    "isort",
    "coverage",
    "pre-commit",
}

UNUSED_OR_DUPLICATE_PACKAGES = {
    "airportsdata",
    "pycountry",
    "requests",
    "tavily-python",
    "langchain-tavily",
}


def test_requirements_txt_pinned_and_no_dev_packages():
    """Parses requirements.txt and verifies:
    1. Every entry is strictly pinned with '=='
    2. No dev packages (e.g. pytest, httpx) appear in runtime requirements.txt
    3. Unused packages are removed
    """
    req_file = BASE_DIR / "requirements.txt"
    assert req_file.exists(), "requirements.txt must exist"

    lines = req_file.read_text(encoding="utf-8").splitlines()

    entries = []
    unpinned_entries = []
    dev_entries_found = []
    unused_entries_found = []
    seen_names = set()
    duplicates = []

    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or cleaned.startswith("-r"):
            continue

        entries.append(cleaned)
        # Extract package name (ignoring extras like [binary] or [hiredis])
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[.*?\])?(.*)$", cleaned)
        if not match:
            unpinned_entries.append(cleaned)
            continue

        pkg_name = match.group(1).lower()
        version_spec = match.group(2).strip()

        if pkg_name in seen_names:
            duplicates.append(pkg_name)
        seen_names.add(pkg_name)

        if not version_spec.startswith("==") or ">=" in version_spec or "<=" in version_spec or "~=" in version_spec:
            unpinned_entries.append(cleaned)

        if pkg_name in DEV_PACKAGES:
            dev_entries_found.append(pkg_name)

        if pkg_name in UNUSED_OR_DUPLICATE_PACKAGES:
            unused_entries_found.append(pkg_name)

    assert not duplicates, f"Duplicate packages found in requirements.txt: {duplicates}"
    assert not unpinned_entries, f"Unpinned package specifications in requirements.txt: {unpinned_entries}"
    assert not dev_entries_found, f"Dev packages found in runtime requirements.txt: {dev_entries_found}"
    assert not unused_entries_found, f"Unused packages found in requirements.txt: {unused_entries_found}"

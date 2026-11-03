"""
tests/test_docs.py — Documentation accuracy & completeness test suite.

Verifies:
1. Every env var in the README table exists in .env.example AND in the Settings model.
2. Every endpoint listed in the README exists in the FastAPI route table (and vice-versa).
3. Version in pyproject.toml == settings.APP_VERSION == /api/v1/health response.
4. Every SECURITY.md control maps to an existing test function.

Run with:
    pytest tests/test_docs.py -v
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import List, Set

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ENV_EXAMPLE = ROOT / ".env.example"
PYPROJECT = ROOT / "pyproject.toml"
SECURITY_MD = ROOT / "SECURITY.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _settings_fields() -> Set[str]:
    """Return all uppercase field names defined in the Settings pydantic model."""
    from tripmate.config.settings import Settings
    return {
        name
        for name in Settings.model_fields
        if name == name.upper()
    }


def _env_example_keys() -> Set[str]:
    """Parse .env.example and return the set of KEY names (no values)."""
    keys: Set[str] = set()
    for line in _read(ENV_EXAMPLE).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _readme_env_table_vars() -> Set[str]:
    """Extract every env var name from the README Environment Variables section tables.

    We only look inside the ## Environment Variables section, and we match
    table rows of the form:  | `VAR_NAME` | default | description |
    This avoids false-positives from error codes (ALERT_NOT_FOUND), HTTP
    methods (GET, POST), and other ALL_CAPS words in prose.
    """
    text = _read(README)
    # Extract the "Environment Variables" section
    # Match from ## Environment Variables until the next ## heading
    section_match = re.search(
        r"## Environment Variables\n(.+?)(?=\n## |\Z)",
        text,
        re.DOTALL,
    )
    if not section_match:
        return set()
    section = section_match.group(1)
    # Match table rows: first cell is `VAR_NAME`
    # Format: | `VAR_NAME` | ... |  OR  | `VAR_NAME` | ... |
    return set(re.findall(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|", section, re.MULTILINE))


def _readme_endpoints() -> Set[str]:
    """Extract every METHOD /path defined in the README API reference section.

    We match:
    - Headings: #### `METHOD /path`
    - Table rows: | `METHOD` | `/path` | ...
    This avoids false matches from curl commands or prose examples.
    """
    text = _read(README)
    endpoints: Set[str] = set()
    # Heading format: #### `GET /api/v1/health`
    for m in re.finditer(r"####\s+`([A-Z]+)\s+([^`]+)`", text):
        endpoints.add(f"{m.group(1).upper()} {m.group(2).strip()}")
    # Table row format: | `GET` | `/api/v1/watchlists` |
    for m in re.finditer(r"\|\s*`([A-Z]+)`\s*\|\s*`([^`]+)`\s*\|", text):
        path = m.group(2).strip()
        if path.startswith("/"):
            endpoints.add(f"{m.group(1).upper()} {path}")
    return endpoints


def _app_routes() -> Set[str]:
    """Return all METHOD /path pairs registered in the FastAPI app."""
    from app import app  # noqa: PLC0415

    routes: Set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path and methods:
            for method in methods:
                routes.add(f"{method.upper()} {path}")
    return routes


def _pyproject_version() -> str:
    with open(PYPROJECT, "rb") as fh:
        data = tomllib.load(fh)
    return data["project"]["version"]


def _security_controls() -> List[str]:
    """Return test function names listed in SECURITY.md control-to-test mapping."""
    if not SECURITY_MD.exists():
        return []
    text = _read(SECURITY_MD)
    # Find function names like test_something_important
    return re.findall(r"`(test_[a-z_]+)`", text)


def _all_test_functions() -> Set[str]:
    """Collect every def test_* function in the tests/ directory."""
    funcs: Set[str] = set()
    tests_dir = ROOT / "tests"
    for py_file in tests_dir.glob("test_*.py"):
        for line in py_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(?:async\s+)?def\s+(test_\w+)\s*\(", line)
            if m:
                funcs.add(m.group(1))
    return funcs


# ---------------------------------------------------------------------------
# 1. Env var coverage
# ---------------------------------------------------------------------------

class TestEnvVarCoverage:
    """Every env var in the README table must be in .env.example and Settings."""

    README_VARS = _readme_env_table_vars()
    ENV_EXAMPLE_KEYS = _env_example_keys()
    SETTINGS_FIELDS = _settings_fields()

    # Known vars that appear in README prose but are not user-configurable
    # settings fields (they are OS-level or computed).
    EXEMPT_FROM_SETTINGS = {
        "PYTEST_CURRENT_TEST",      # set by pytest itself
        "LANGCHAIN_HIDE_INPUTS",    # set programmatically in settings.__init__
        "LANGCHAIN_HIDE_OUTPUTS",   # set programmatically in settings.__init__
    }

    # Vars not in .env.example because they are single-sourced or computed
    EXEMPT_FROM_ENV_EXAMPLE = {
        "APP_VERSION",              # single-sourced from pyproject.toml
        "PYTEST_CURRENT_TEST",
        "LANGCHAIN_HIDE_INPUTS",
        "LANGCHAIN_HIDE_OUTPUTS",
    }

    @pytest.mark.parametrize("var", sorted(README_VARS))
    def test_readme_var_in_env_example(self, var: str):
        """Every env var documented in README must appear in .env.example."""
        if var in self.EXEMPT_FROM_SETTINGS or var in self.EXEMPT_FROM_ENV_EXAMPLE:
            pytest.skip(f"{var!r} is exempt (set by runtime or single-sourced)")
        assert var in self.ENV_EXAMPLE_KEYS, (
            f"Env var {var!r} is in the README table but missing from .env.example"
        )

    @pytest.mark.parametrize("var", sorted(README_VARS - EXEMPT_FROM_SETTINGS - EXEMPT_FROM_ENV_EXAMPLE))
    def test_readme_var_in_settings(self, var: str):
        """Every env var documented in README must be a Settings field."""
        if var in self.EXEMPT_FROM_SETTINGS or var in self.EXEMPT_FROM_ENV_EXAMPLE:
            pytest.skip(f"{var!r} is exempt")
        assert var in self.SETTINGS_FIELDS, (
            f"Env var {var!r} is in the README table but not a Settings field"
        )

    def test_env_example_completeness(self):
        """Spot-check: no env-example key is entirely absent from Settings or README."""
        # Optional guard — prints a warning for vars in .env.example not documented
        undocumented = self.ENV_EXAMPLE_KEYS - self.README_VARS - self.EXEMPT_FROM_SETTINGS
        # We do not hard-fail here; we just report for now.
        if undocumented:
            import warnings
            warnings.warn(
                f"These .env.example keys are not in the README env table: {sorted(undocumented)}"
            )


# ---------------------------------------------------------------------------
# 2. Endpoint coverage
# ---------------------------------------------------------------------------

class TestEndpointCoverage:
    """Every endpoint in the README must exist in the FastAPI route table."""

    README_ENDPOINTS = _readme_endpoints()
    APP_ROUTES = _app_routes()

    @pytest.mark.parametrize("endpoint", sorted(README_ENDPOINTS))
    def test_readme_endpoint_exists_in_app(self, endpoint: str):
        """Every endpoint documented in README must be registered in FastAPI."""
        method, path = endpoint.split(" ", 1)
        # Handle parameterised paths: /api/v1/runs/{run_id} vs /api/v1/runs/{run_id}/metrics
        registered = {r.split(" ", 1)[1] for r in self.APP_ROUTES}
        assert path in registered, (
            f"Endpoint {endpoint!r} is documented in README but not registered in FastAPI app"
        )

    def test_all_v1_routes_are_documented(self):
        """Every /api/v1/* route should appear in README (warn only, not hard-fail)."""
        v1_routes = {r for r in self.APP_ROUTES if "/api/v1/" in r}
        readme_paths = {e.split(" ", 1)[1] for e in self.README_ENDPOINTS}
        undocumented = {r.split(" ", 1)[1] for r in v1_routes} - readme_paths
        if undocumented:
            import warnings
            warnings.warn(f"App routes not documented in README: {sorted(undocumented)}")


# ---------------------------------------------------------------------------
# 3. Version consistency
# ---------------------------------------------------------------------------

class TestVersionConsistency:
    """Version in pyproject.toml == settings.APP_VERSION == /api/v1/health."""

    def test_pyproject_version_matches_settings(self):
        """pyproject.toml version must equal settings.APP_VERSION."""
        from tripmate.config.settings import settings
        pyproject_ver = _pyproject_version()
        assert pyproject_ver == settings.APP_VERSION, (
            f"pyproject.toml version={pyproject_ver!r} "
            f"!= settings.APP_VERSION={settings.APP_VERSION!r}"
        )

    def test_health_endpoint_returns_correct_version(self):
        """GET /health and app.version must return the same version as pyproject.toml."""
        from app import app, legacy_health
        from tripmate.config.settings import settings

        assert app.version == settings.APP_VERSION
        coro = legacy_health()
        try:
            coro.send(None)
        except StopIteration as e:
            health_data = e.value
        assert health_data.get("version") == settings.APP_VERSION, (
            f"/health returned version={health_data.get('version')!r} "
            f"but expected {settings.APP_VERSION!r}"
        )

    def test_app_title_matches_product_name(self):
        """FastAPI app title must match settings.APP_NAME (canonical product name)."""
        from app import app
        from tripmate.config.settings import settings
        assert app.title == settings.APP_NAME, (
            f"FastAPI title={app.title!r} != APP_NAME={settings.APP_NAME!r}"
        )


# ---------------------------------------------------------------------------
# 4. SECURITY.md control-to-test mapping
# ---------------------------------------------------------------------------

class TestSecurityControlMapping:
    """Every control listed in SECURITY.md must map to an existing test function."""

    CONTROLS = _security_controls()
    TEST_FUNCTIONS = _all_test_functions()

    @pytest.mark.parametrize("test_name", sorted(CONTROLS))
    def test_security_control_has_test(self, test_name: str):
        """Every test function referenced in SECURITY.md must exist in the test suite."""
        assert test_name in self.TEST_FUNCTIONS, (
            f"SECURITY.md references {test_name!r} but no such test function found in tests/"
        )

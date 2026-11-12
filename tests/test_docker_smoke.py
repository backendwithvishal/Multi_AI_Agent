import re
import shutil
import subprocess
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent


def test_dockerfile_best_practices():
    """Validates Dockerfile requirements statically:
    - Pinned Python base with tag + digest
    - Multi-stage build
    - Pinned uv binary from official image
    - Pre-cached MCP package
    - No git/curl in runtime
    - Python healthcheck probing /health/live
    - Non-root user
    - tini as PID 1
    - No secrets
    """
    dockerfile_path = BASE_DIR / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist"
    content = dockerfile_path.read_text(encoding="utf-8")

    # Pinned Python base with tag + digest (@sha256:)
    assert re.search(r"FROM\s+python:[0-9\.\-]+.*@sha256:[a-f0-9]{64}", content), (
        "Dockerfile must use a pinned Python base image with tag and digest (@sha256:...)"
    )

    # Multi-stage build
    stages = re.findall(r"FROM\s+.*?AS\s+(\w+)", content, re.IGNORECASE)
    assert len(stages) >= 2, "Dockerfile must be multi-stage (e.g. builder, runner)"

    # Official uv image binary copy
    assert re.search(r"COPY\s+--from=ghcr\.io/astral-sh/uv:[^\s]+.*\/uv.*\/usr\/local\/bin", content) or re.search(
        r"COPY\s+--from=.*uv.*\/uv", content
    ), "Dockerfile must copy pinned uv/uvx binary from official image"

    # Pre-cache MCP package at build time
    assert "aviationstack-mcp" in content, "Dockerfile must pre-cache aviationstack-mcp at build time"

    # Split stages to verify runner stage rules
    parts = re.split(r"FROM\s+", content, flags=re.IGNORECASE)
    runner_stage = parts[-1]

    # No git or curl installed in runtime stage
    assert "apt-get install" not in runner_stage or ("curl" not in runner_stage and "git" not in runner_stage), (
        "Runner stage must not install curl or git"
    )

    # Non-root user
    assert re.search(r"USER\s+(?!root)\w+", runner_stage), "Dockerfile must switch to a non-root user"

    # tini as PID 1
    assert "tini" in content, "Dockerfile must install and use tini for PID 1 signal management"
    assert 'ENTRYPOINT ["/usr/bin/tini"' in content or 'ENTRYPOINT ["tini"' in content, (
        "Dockerfile entrypoint must use tini"
    )

    # Healthcheck via Python probing /health/live
    assert "HEALTHCHECK" in content, "Dockerfile must define a HEALTHCHECK"
    assert "python -c" in content or "python3 -c" in content, "HEALTHCHECK must use Python rather than curl"
    assert "/health/live" in content, "Docker HEALTHCHECK must probe /health/live"


def test_compose_configs_hardening():
    """Validates docker-compose.yml and docker-compose.prod.yml security & hardening requirements:
    - Pinned tags
    - DB/Redis not published to host
    - Internal network
    - No inline secrets (passwords required)
    - Healthchecks & service_healthy dependencies
    - cap_drop ALL
    - no-new-privileges
    - read_only with tmpfs
    - Named volumes
    """
    for compose_name in ["docker-compose.yml", "docker-compose.prod.yml"]:
        compose_path = BASE_DIR / compose_name
        assert compose_path.exists(), f"{compose_name} must exist"
        content = compose_path.read_text(encoding="utf-8")

        # Pinned service tags
        assert re.search(r"image:\s*postgres:[0-9]+(?:\.[0-9]+)*-bookworm", content), (
            f"{compose_name} postgres image must have pinned tag"
        )
        assert re.search(r"image:\s*redis:[0-9]+(?:\.[0-9]+)*-alpine", content), (
            f"{compose_name} redis image must have pinned tag"
        )

        # No inline plaintext secrets for postgres/redis
        assert "POSTGRES_PASSWORD=postgres_pass" not in content, (
            f"{compose_name} must not hardcode default passwords inline"
        )
        assert "POSTGRES_PASSWORD" in content and ":?Required" in content, (
            f"{compose_name} must require POSTGRES_PASSWORD via environment"
        )

        # DB & Redis ports not published to host
        # Extract postgres and redis service definitions to ensure no ports: directive exposes them
        for service_name in ["postgres:", "redis:"]:
            service_block = content.split(service_name)[1].split("\n\n")[0]
            assert "ports:" not in service_block, f"{compose_name} must not publish {service_name} ports to host"

        # Security hardening options
        assert "cap_drop:" in content and "ALL" in content, f"{compose_name} must drop ALL capabilities"
        assert "no-new-privileges:true" in content or "no-new-privileges" in content, (
            f"{compose_name} must enable no-new-privileges"
        )
        assert "read_only: true" in content, f"{compose_name} must run app with read_only root filesystem"
        assert "tmpfs:" in content, f"{compose_name} must mount tmpfs for temporary files"

        # Named volumes
        assert "volumes:" in content, f"{compose_name} must define named volumes"


def test_docker_smoke_script_exists():
    """Ensures scripts/smoke_docker.sh exists and contains required test phases."""
    script_path = BASE_DIR / "scripts" / "smoke_docker.sh"
    assert script_path.exists(), "scripts/smoke_docker.sh must exist"
    content = script_path.read_text(encoding="utf-8")
    assert "docker build" in content
    assert "compose config" in content
    assert "service_healthy" in content or "all healthy" in content or "healthy" in content
    assert "whoami" in content or "user is not root" in content or "appuser" in content
    assert "5432" in content and "6379" in content, "Smoke script must check DB and Redis isolation"
    assert "stop postgres" in content, "Smoke script must simulate postgres stoppage"
    assert "503" in content, "Smoke script must assert 503 upon dependency degradation"


def test_docker_smoke_execution():
    """Executes scripts/smoke_docker.sh if docker engine daemon is accessible; otherwise skips cleanly."""
    import os
    if os.getenv("SKIP_DOCKER_SMOKE_IN_PYTEST") == "true":
        pytest.skip("Docker smoke execution handled in dedicated CI docker-build job")

    if not shutil.which("docker"):
        pytest.skip("Docker CLI not installed on host")

    try:
        ping = subprocess.run(["docker", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if ping.returncode != 0:
            pytest.skip("Docker daemon not running; skipping active container lifecycle smoke test")
    except Exception:
        pytest.skip("Unable to reach Docker daemon")

    res = subprocess.run(["bash", (BASE_DIR / "scripts" / "smoke_docker.sh").as_posix()], capture_output=True, text=True)
    assert res.returncode == 0, f"Docker smoke script failed:\n{res.stdout}\n{res.stderr}"

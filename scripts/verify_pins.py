#!/usr/bin/env python3
"""
Pin & Digest Verification Script for Container Images & Registry References
Finds all '@sha256:' image digests in Dockerfile, Compose files, and Workflows
and asserts each digest genuinely resolves with HTTP 200 in the target registry.
Exits 0 if all resolve, exits 1 on invalid/missing digest, exits 2 on network failure.
"""

import sys
import re
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Files to scan for pinned digests
SCAN_PATTERNS = [
    "Dockerfile*",
    "docker-compose*.yml",
    ".github/workflows/*.yml",
]


def check_network():
    """Returns True if public registry network is accessible."""
    try:
        req = urllib.request.Request("https://registry-1.docker.io/v2/", headers={"User-Agent": "PinVerifier/1.0"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except urllib.error.HTTPError as e:
        # HTTP 401 Unauthorized is expected for unauthenticated /v2/ ping and confirms network connectivity
        return e.code in (401, 200)
    except Exception:
        return False


def verify_ghcr_digest(repo: str, digest: str) -> bool:
    """Verifies digest exists in GitHub Container Registry."""
    token_url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repo}:pull"
    req = urllib.request.Request(token_url, headers={"User-Agent": "PinVerifier/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode())["token"]

    manifest_url = f"https://ghcr.io/v2/{repo}/manifests/{digest}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "PinVerifier/1.0",
        "Accept": (
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json, "
            "application/vnd.oci.image.manifest.v1+json"
        ),
    }
    req2 = urllib.request.Request(manifest_url, headers=headers)
    try:
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            return resp2.getcode() == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def verify_dockerhub_digest(repo: str, digest: str) -> bool:
    """Verifies digest exists in Docker Hub Registry."""
    if "/" not in repo:
        repo = f"library/{repo}"

    token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    req = urllib.request.Request(token_url, headers={"User-Agent": "PinVerifier/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        token = json.loads(resp.read().decode())["token"]

    manifest_url = f"https://registry-1.docker.io/v2/{repo}/manifests/{digest}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "PinVerifier/1.0",
        "Accept": (
            "application/vnd.docker.distribution.manifest.list.v2+json, "
            "application/vnd.oci.image.index.v1+json, "
            "application/vnd.docker.distribution.manifest.v2+json, "
            "application/vnd.oci.image.manifest.v1+json"
        ),
    }
    req2 = urllib.request.Request(manifest_url, headers=headers)
    try:
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            return resp2.getcode() == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def parse_reference(ref_str: str):
    """
    Parses a reference like:
    python:3.11.11-slim-bookworm@sha256:081075...
    ghcr.io/astral-sh/uv:0.5.29@sha256:88d7b4...
    """
    image_part, digest = ref_str.split("@")
    if ":" in image_part:
        image_name, tag = image_part.split(":", 1)
    else:
        image_name, tag = image_part, "latest"

    registry = "dockerhub"
    repo = image_name
    if image_name.startswith("ghcr.io/"):
        registry = "ghcr"
        repo = image_name[len("ghcr.io/"):]

    return registry, repo, tag, digest


def main():
    print("=== TripMate AI Pin & Digest Verifier ===")

    if not check_network():
        print("WARNING: Public container registries unreachable (no network).")
        print("RESULT: NOT VERIFIED (network unavailable)")
        sys.exit(2)

    found_refs = []
    # Collect files
    for pattern in SCAN_PATTERNS:
        for file_path in BASE_DIR.glob(pattern):
            if file_path.is_file():
                content = file_path.read_text(encoding="utf-8")
                # Match image:tag@sha256:[64hex] or image@sha256:[64hex]
                matches = re.finditer(r"([a-zA-Z0-9_./:-]+@sha256:[a-f0-9]{64})", content)
                for m in matches:
                    ref = m.group(1)
                    line_no = content[:m.start()].count("\n") + 1
                    found_refs.append((ref, file_path.relative_to(BASE_DIR), line_no))

    if not found_refs:
        print("No @sha256: references found to verify.")
        sys.exit(0)

    print(f"Discovered {len(found_refs)} pinned reference(s) to verify:")
    failures = 0
    checked_digests = {}

    for ref, rel_path, line_no in found_refs:
        registry, repo, tag, digest = parse_reference(ref)
        key = (registry, repo, digest)

        if key in checked_digests:
            exists = checked_digests[key]
        else:
            try:
                if registry == "ghcr":
                    exists = verify_ghcr_digest(repo, digest)
                else:
                    exists = verify_dockerhub_digest(repo, digest)
                checked_digests[key] = exists
            except Exception as e:
                print(f"  [ERROR] {ref} in {rel_path}:{line_no} -> Failed to query registry: {e}")
                failures += 1
                continue

        status_str = "RESOLVED (200 OK)" if exists else "NOT FOUND (404)"
        print(f"  [{status_str}] {ref} ({rel_path}:{line_no})")
        if not exists:
            failures += 1

    if failures > 0:
        print(f"\nVerification FAILED: {failures} digest reference(s) do NOT exist in the registry!")
        sys.exit(1)

    print(f"\nAll {len(found_refs)} pinned digest reference(s) successfully verified!")
    sys.exit(0)


if __name__ == "__main__":
    main()


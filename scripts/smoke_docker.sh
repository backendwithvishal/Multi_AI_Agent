#!/usr/bin/env bash
# ==============================================================================
# TripMate AI — End-to-End Docker Production Smoke Verification Script
# ==============================================================================
set -euo pipefail

echo "=== [1/7] Building production Docker image ==="
docker build -t tripmate:test .

echo "=== [2/7] Validating Compose configs without inline secrets ==="
export POSTGRES_PASSWORD="test_postgres_smoke_password"
CONFIG_DEV=$(docker compose -f docker-compose.yml config)
CONFIG_PROD=$(docker compose -f docker-compose.prod.yml config)

if echo "$CONFIG_DEV $CONFIG_PROD" | grep -E "postgres_pass"; then
    echo "ERROR: Plaintext default password found in compose config output!"
    exit 1
fi

echo "=== [3/7] Starting services with Docker Compose ==="
docker compose -f docker-compose.yml up -d

cleanup() {
    echo "=== Teardown / Cleanup ==="
    docker compose -f docker-compose.yml down -v --remove-orphans || true
}
trap cleanup EXIT

echo "=== [4/7] Waiting for all services to become healthy ==="
for service in postgres redis app; do
    echo "Waiting for $service to be healthy..."
    until [ "$(docker compose -f docker-compose.yml ps -q $service | xargs docker inspect -f '{{.State.Health.Status}}' 2>/dev/null || echo 'starting')" == "healthy" ]; do
        sleep 2
    done
    echo "$service is healthy."
done

echo "=== [5/7] Verifying container user is non-root ==="
USER_NAME=$(docker compose -f docker-compose.yml exec -T app whoami)
echo "Container user: $USER_NAME"
if [ "$USER_NAME" == "root" ]; then
    echo "ERROR: Container is running as root!"
    exit 1
fi

echo "=== [6/7] Verifying DB and Redis ports are unreachable from host ==="
if nc -z -w2 127.0.0.1 5432 2>/dev/null || timeout 2 bash -c "</dev/tcp/127.0.0.1/5432" 2>/dev/null; then
    echo "ERROR: PostgreSQL port 5432 is published to host!"
    exit 1
fi
if nc -z -w2 127.0.0.1 6379 2>/dev/null || timeout 2 bash -c "</dev/tcp/127.0.0.1/6379" 2>/dev/null; then
    echo "ERROR: Redis port 6379 is published to host!"
    exit 1
fi
echo "Postgres and Redis are isolated inside internal network."

echo "=== [7/7] Testing health endpoints & readiness degradation when Postgres is stopped ==="
LIVE_STATUS=$(docker compose -f docker-compose.yml exec -T app python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/live').getcode())")
if [ "$LIVE_STATUS" != "200" ]; then
    echo "ERROR: /health/live did not return 200"
    exit 1
fi
echo "/health/live is 200 OK."

echo "Stopping postgres container..."
docker compose -f docker-compose.yml stop postgres

READY_STATUS=$(docker compose -f docker-compose.yml exec -T app python -c "import urllib.request, urllib.error; 
try:
    urllib.request.urlopen('http://127.0.0.1:8000/health/ready')
    print('200')
except urllib.error.HTTPError as e:
    print(e.code)
")

if [ "$READY_STATUS" != "503" ]; then
    echo "ERROR: Expected 503 when Postgres is down, got: $READY_STATUS"
    exit 1
fi
echo "/health/ready correctly returned 503 when Postgres is stopped."

echo "=== All Docker smoke tests passed successfully! ==="


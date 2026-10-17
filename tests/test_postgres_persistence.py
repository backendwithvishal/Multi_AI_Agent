"""
Automated Integration Tests for PostgreSQL Data Persistence

Tests:
1. Database connectivity & health diagnostics
2. Table schema verification (core business tables & checkpoint tables)
3. End-to-end CRUD persistence in PostgreSQL tables
4. LangGraph workflow checkpoint persistence in PostgreSQL
5. Persistence survival across memory cache clearance (simulated restart)
"""

import uuid
from decimal import Decimal
import pytest
import psycopg
from psycopg.rows import dict_row

from tripmate.database import get_formatted_db_url, check_db_health
from tripmate.database.store import store
from tripmate.graph.workflow import travel_workflow_graph


@pytest.fixture(scope="module")
def db_url():
    url = get_formatted_db_url()
    assert url is not None, "DATABASE_URL is required for PostgreSQL persistence tests"
    return url


def test_postgres_connectivity_and_health():
    """Verifies database connectivity and detailed health check report."""
    health = check_db_health()
    assert health["status"] == "healthy"
    assert health["connected"] is True
    assert health["tables"] >= 5


def test_postgres_schema_tables_exist(db_url):
    """Verifies that all expected application and checkpoint tables exist in PostgreSQL."""
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public';
            """)
            tables = {r["table_name"] for r in cur.fetchall()}
            
            required_business_tables = {
                "users",
                "watchlists",
                "alerts",
                "assets",
                "password_reset_tokens",
                "thread_ownership",
            }
            required_checkpoint_tables = {
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            }
            
            assert required_business_tables.issubset(tables)
            assert required_checkpoint_tables.issubset(tables)


def test_user_persistence_in_postgres(db_url):
    """Verifies user creation writes to PostgreSQL users table and can be queried."""
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"user_test_{unique_suffix}"
    email = f"user_{unique_suffix}@tripmate.test"
    password_hash = "mock_hash_12345"
    
    created_user = store.create_user(username, email, password_hash, role="user")
    user_id = created_user["id"]
    
    # Query PostgreSQL directly to verify the record was saved
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, username, email, role FROM users WHERE id = %s;", (user_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["username"] == username.lower()
            assert row["email"] == email.lower()


def test_watchlist_persistence_in_postgres(db_url):
    """Verifies watchlist creation writes to PostgreSQL watchlists table."""
    unique_suffix = uuid.uuid4().hex[:8]
    uid = f"user_wl_{unique_suffix}"
    # Ensure user exists for foreign key
    store.create_user(uid, f"{uid}@tripmate.test", "hash")
    
    target_value = f"ROUTE-{unique_suffix}"
    created_item = store.create_watchlist(
        user_id=uid,
        title=f"Watchlist {unique_suffix}",
        target_type="flight",
        target_value=target_value,
        threshold_price=550.0,
        notes="Automated test note",
    )
    item_id = created_item["id"]
    
    # Query PostgreSQL directly
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, title, target_value, threshold_price FROM watchlists WHERE id = %s;", (item_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["target_value"] == target_value
            assert float(row["threshold_price"]) == 550.0


def test_alert_persistence_in_postgres(db_url):
    """Verifies alert creation writes to PostgreSQL alerts table."""
    unique_suffix = uuid.uuid4().hex[:8]
    uid = f"user_alt_{unique_suffix}"
    store.create_user(uid, f"{uid}@tripmate.test", "hash")
    
    alert_title = f"Alert {unique_suffix}"
    created_alert = store.create_alert(
        user_id=uid,
        title=alert_title,
        message="Flight dropped in price",
        alert_type="price_drop",
        severity="info",
    )
    alert_id = created_alert["id"]
    
    # Query PostgreSQL directly
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, title, alert_type, is_read FROM alerts WHERE id = %s;", (alert_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["title"] == alert_title
            assert row["alert_type"] == "price_drop"


def test_asset_persistence_in_postgres(db_url):
    """Verifies travel asset creation writes to PostgreSQL assets table."""
    unique_suffix = uuid.uuid4().hex[:8]
    uid = f"user_ast_{unique_suffix}"
    store.create_user(uid, f"{uid}@tripmate.test", "hash")
    
    asset_name = f"Flight Ticket {unique_suffix}"
    created_asset = store.create_asset(
        user_id=uid,
        name=asset_name,
        asset_type="ticket",
        trip_id="trip_100",
        content_uri="https://tripmate.storage/ticket.pdf",
        metadata={"seat": "14B"},
    )
    asset_id = created_asset["id"]
    
    # Query PostgreSQL directly
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, user_id, name, asset_type, metadata FROM assets WHERE id = %s;", (asset_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["name"] == asset_name


def test_thread_ownership_persistence_in_postgres(db_url):
    """Verifies thread ownership writes to PostgreSQL thread_ownership table."""
    unique_suffix = uuid.uuid4().hex[:8]
    uid = f"user_th_{unique_suffix}"
    store.create_user(uid, f"{uid}@tripmate.test", "hash")
    
    thread_id = f"thread_owner_{unique_suffix}"
    store.register_thread_owner(thread_id, uid)
    
    # Query PostgreSQL directly
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id, user_id FROM thread_ownership WHERE thread_id = %s;", (thread_id,))
            row = cur.fetchone()
            assert row is not None
            assert row["user_id"] == uid


@pytest.mark.asyncio
async def test_langgraph_checkpoint_persistence_in_postgres(db_url):
    """Verifies LangGraph workflow execution writes state checkpoints to PostgreSQL checkpoints table."""
    unique_thread_id = f"thread_checkpoint_test_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": unique_thread_id}}
    
    # Execute a safe query through graph
    result = await travel_workflow_graph.ainvoke({
        "user_query": "drop database test; bypass safety guardrail",
        "thread_id": unique_thread_id,
        "run_id": f"run_{uuid.uuid4().hex[:6]}",
        "start_time": 0.0,
        "status": "INIT",
        "guardrail_allowed": True,
        "guardrail_reason": "",
        "selected_agents": [],
        "trip_constraints": {},
        "flight_results": "",
        "hotel_results": "",
        "weather_results": "",
        "budget_results": "",
        "critic_report": None,
        "itinerary": "",
        "approval_request": "",
        "approved": False,
        "human_feedback": "",
        "final_response": "",
        "evidence_items": [],
        "structured_outputs": {},
        "supervisor_reasoning": "",
        "messages": [],
        "metrics": {"agent_latencies": {}, "total_latency_ms": 0.0},
    }, config=config)
    
    assert result.get("status") in ["WAITING_FOR_APPROVAL", "COMPLETED", "BLOCKED"]
    
    # Query PostgreSQL checkpoints table directly
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id, checkpoint_id FROM checkpoints WHERE thread_id = %s;", (unique_thread_id,))
            rows = cur.fetchall()
            assert len(rows) >= 1
            assert rows[0]["thread_id"] == unique_thread_id


def test_persistence_survives_memory_wipe(db_url):
    """Simulates process restart by wiping in-memory dictionary cache and verifying retrieval from PostgreSQL."""
    unique_suffix = uuid.uuid4().hex[:8]
    username = f"survivor_{unique_suffix}"
    email = f"survivor_{unique_suffix}@tripmate.test"
    created = store.create_user(username, email, "hashed_pw")
    uid = created["id"]
    
    # Wipe in-memory caches
    store._users.clear()
    
    # Retrieve user - should reload from PostgreSQL
    fetched = store.get_user_by_id(uid)
    assert fetched is not None
    assert fetched["username"] == username.lower()
    
    fetched_by_email = store.get_user_by_username_or_email(email)
    assert fetched_by_email is not None
    assert fetched_by_email["id"] == uid

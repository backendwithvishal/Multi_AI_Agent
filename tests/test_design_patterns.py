"""
Comprehensive Test Suite for 10 Software Design Patterns & Architectural Concepts:
1. Repository Pattern (Interfaces, Store Implementations, Mock Injection)
2. Factory Pattern (AgentFactory, LLMClientFactory, Config Validation)
3. Singleton Pattern (SingletonMeta, Thread Safety, Lifecycle, Double-Checked Locking)
4. Strategy Pattern (LLM Providers: Groq, OpenRouter, HF; GDS Search Strategies)
5. Observer Pattern (WorkflowEventDispatcher, Event Isolation, SSE Bridge)
6. Builder Pattern (TravelWorkflowStateBuilder, TravelPlanResponseBuilder)
7. Adapter Pattern (WeatherServiceAdapter, FlightServiceAdapter, TavilySearchAdapter)
8. Decorator Pattern (@timed_async, @retry_async, @circuit_protected)
9. CQRS Pattern (Command & Query Separation, Bus Dispatching, Zero Side-Effect Queries)
10. Circuit Breaker Pattern (CLOSED -> OPEN -> HALF_OPEN, Transient vs Permanent Discrimination, Trial Concurrency Guard)
"""

import asyncio
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

# Core & Patterns
from tripmate.core.decorators import circuit_protected, retry_async, timed_async
from tripmate.core.singleton import SingletonMeta
from tripmate.repositories.interfaces import IWatchlistRepository
from tripmate.repositories.store_repositories import (
    StoreAlertRepository,
    StoreAssetRepository,
    StoreBookingRepository,
    StoreThreadOwnerRepository,
    StoreUserRepository,
    StoreWatchlistRepository,
    alert_repository,
    asset_repository,
    booking_repository,
    user_repository,
    watchlist_repository,
)
from tripmate.factories.agent_factory import AgentFactory
from tripmate.factories.llm_factory import LLMClientFactory
from tripmate.strategies.llm_strategies import (
    GroqProviderStrategy,
    HuggingFaceProviderStrategy,
    LLMProviderStrategy,
    ModelTier,
    OpenRouterProviderStrategy,
)
from tripmate.strategies.booking_strategies import (
    AmadeusSandboxFlightStrategy,
    AmadeusSandboxHotelStrategy,
)
from tripmate.events.events import (
    ApprovalRequiredEvent,
    CriticCompletedEvent,
    SupervisorCompletedEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowStartedEvent,
)
from tripmate.events.dispatcher import IWorkflowEventSubscriber, WorkflowEventDispatcher
from tripmate.events.subscribers import SSEEventBridgeSubscriber
from tripmate.builders.workflow_state_builder import TravelWorkflowStateBuilder
from tripmate.builders.response_builder import TravelPlanResponseBuilder
from tripmate.adapters.weather_adapter import WeatherServiceAdapter
from tripmate.adapters.flight_adapter import FlightServiceAdapter
from tripmate.adapters.tavily_adapter import TavilySearchAdapter
from tripmate.cqrs.commands import (
    CreateAlertCommand,
    CreateAssetCommand,
    CreateWatchlistCommand,
    DeleteWatchlistCommand,
)
from tripmate.cqrs.queries import (
    GetWatchlistQuery,
    ListAlertsQuery,
    ListWatchlistsQuery,
)
from tripmate.cqrs.handlers import (
    AlertCommandHandlers,
    AlertQueryHandlers,
    WatchlistCommandHandlers,
    WatchlistQueryHandlers,
)
from tripmate.cqrs.bus import CommandBus, QueryBus
from tripmate.integrations.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitState,
)
from tripmate.services.watchlist_service import WatchlistService
from tripmate.services.model_router import ModelRouter
from tripmate.schemas import WatchlistCreateRequest


# =========================================================
# 1. Repository Pattern Tests
# =========================================================

def test_repository_pattern_crud_operations():
    """Tests concrete repository data access and persistence logic."""
    # User Repository
    users = user_repository.list_all()
    assert len(users) >= 2
    admin = user_repository.get_by_username_or_email("admin")
    assert admin is not None
    assert admin["role"] == "admin"

    # Watchlist Repository
    created_wl = watchlist_repository.create(
        user_id="user_test_repo",
        title="Tokyo Cherry Blossom Trip",
        target_type="flight",
        target_value="HND",
        threshold_price=650.0,
    )
    assert created_wl["id"].startswith("wl_")
    assert created_wl["title"] == "Tokyo Cherry Blossom Trip"

    fetched_wl = watchlist_repository.get_by_id(created_wl["id"], "user_test_repo")
    assert fetched_wl is not None
    assert fetched_wl["id"] == created_wl["id"]

    deleted = watchlist_repository.delete(created_wl["id"], "user_test_repo")
    assert deleted is True
    assert watchlist_repository.get_by_id(created_wl["id"], "user_test_repo") is None


def test_repository_mock_injection():
    """Verifies that services accept mock repositories for isolated unit testing."""
    class FakeWatchlistRepository(IWatchlistRepository):
        def __init__(self):
            self.items = {}

        def create(self, user_id, title, target_type, target_value, threshold_price=None, notes=""):
            item = {
                "id": "wl_fake_123",
                "user_id": user_id,
                "title": title,
                "target_type": target_type,
                "target_value": target_value,
                "threshold_price": threshold_price,
                "current_price_estimate": 500.0,
                "currency": "USD",
                "notes": notes,
                "created_at": "2026-01-01T00:00:00Z",
                "active": True,
            }
            self.items[item["id"]] = item
            return item

        def get_by_id(self, item_id, user_id=None):
            return self.items.get(item_id)

        def list_by_user(self, user_id=None):
            return list(self.items.values())

        def delete(self, item_id, user_id=None):
            if item_id in self.items:
                del self.items[item_id]
                return True
            return False

    fake_repo = FakeWatchlistRepository()
    service = WatchlistService(repo=fake_repo)

    req = WatchlistCreateRequest(title="Rome Holiday", target_type="destination", target_value="FCO")
    item = service.add_item("user_fake", req)
    assert item.id == "wl_fake_123"
    assert len(service.list_items("user_fake")) == 1

    assert service.delete_item("wl_fake_123", "user_fake") is True
    assert len(service.list_items("user_fake")) == 0


# =========================================================
# 2. Factory Pattern Tests
# =========================================================

def test_agent_factory_creation():
    """Tests AgentFactory dynamic instantiation and metadata registration."""
    agent_names = ["flight_agent", "hotel_agent", "weather_agent", "budget_agent", "itinerary_agent"]
    for name in agent_names:
        agent = AgentFactory.create_agent(name)
        assert agent is not None
        assert agent.name == name
        assert len(agent.metadata.capabilities) > 0


def test_agent_factory_unsupported_type():
    """Tests AgentFactory fails with descriptive error on unknown agent type."""
    with pytest.raises(ValueError, match="Unsupported agent type 'unknown_agent'"):
        AgentFactory.create_agent("unknown_agent")


def test_llm_client_factory_validation():
    """Tests LLMClientFactory configuration validation and error reporting."""
    with pytest.raises(ValueError, match="Unsupported LLM provider 'cohere'"):
        LLMClientFactory.create_client("cohere")


# =========================================================
# 3. Singleton Pattern Tests
# =========================================================

def test_singleton_thread_safety_and_identity():
    """Tests SingletonMeta guarantees single instance across multiple threads."""
    class ExpensiveConnectionPool(metaclass=SingletonMeta):
        def __init__(self):
            self.created_at = time.time()
            self.connection_count = 10

    instances = []

    def worker():
        instances.append(ExpensiveConnectionPool())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All instances across all threads must be the exact same object in memory
    first = instances[0]
    for inst in instances:
        assert inst is first

    # Test reset instance
    SingletonMeta.reset_instance(ExpensiveConnectionPool)
    new_inst = ExpensiveConnectionPool()
    assert new_inst is not first


# =========================================================
# 4. Strategy Pattern Tests
# =========================================================

def test_llm_provider_strategies():
    """Tests individual LLM provider strategies and ranking."""
    groq = GroqProviderStrategy()
    openrouter = OpenRouterProviderStrategy()
    hf = HuggingFaceProviderStrategy()

    assert groq.provider_name == "groq"
    assert openrouter.provider_name == "openrouter"
    assert hf.provider_name == "huggingface"

    assert groq.priority < openrouter.priority < hf.priority


def test_model_router_strategy_delegation():
    """Tests ModelRouter delegates execution to configured strategies."""
    class MockCustomStrategy(LLMProviderStrategy):
        @property
        def provider_name(self) -> str:
            return "mock_custom"

        @property
        def priority(self) -> int:
            return 0  # Highest priority

        def is_configured(self) -> bool:
            return True

        def create_model(self, tier: ModelTier, timeout: float):
            return "MockChatModelInstance"

    mock_strat = MockCustomStrategy()
    SingletonMeta.reset_instance(ModelRouter)
    router = ModelRouter(strategies=[mock_strat])
    assert router.has_active_provider() is True
    assert router.get_active_provider_name() == "mock_custom"
    assert router.get_model() == "MockChatModelInstance"
    SingletonMeta.reset_instance(ModelRouter)


@pytest.mark.asyncio
async def test_booking_search_strategies():
    """Tests interchangeable flight and hotel search strategies."""
    flight_strat = AmadeusSandboxFlightStrategy()
    hotel_strat = AmadeusSandboxHotelStrategy()

    flights = await flight_strat.search_flights("JFK", "LHR", "2026-06-01", 1, "ECONOMY")
    assert flights["offers_count"] >= 1
    assert flights["origin"] == "JFK"

    hotels = await hotel_strat.search_hotels("PAR", "2026-06-01", "2026-06-05")
    assert hotels["hotels_count"] >= 1
    assert hotels["city_code"] == "PAR"


# =========================================================
# 5. Observer Pattern Tests
# =========================================================

@pytest.mark.asyncio
async def test_observer_event_dispatching():
    """Tests event dispatching and notification delivery to subscribers."""
    dispatcher = WorkflowEventDispatcher()
    received_events = []

    class TestSubscriber(IWorkflowEventSubscriber):
        async def on_event(self, event: WorkflowEvent) -> None:
            received_events.append(event)

    sub = TestSubscriber()
    dispatcher.subscribe(sub)

    event = WorkflowStartedEvent(thread_id="t1", run_id="r1", request_id="req1")
    await dispatcher.publish(event)

    assert len(received_events) == 1
    assert received_events[0].thread_id == "t1"
    assert received_events[0].event_type == "workflow.started"

    dispatcher.unsubscribe(sub)


@pytest.mark.asyncio
async def test_observer_failure_isolation():
    """Tests that a failing subscriber does not disrupt other subscribers or main flow."""
    dispatcher = WorkflowEventDispatcher()
    success_received = []

    class BrokenSubscriber(IWorkflowEventSubscriber):
        async def on_event(self, event: WorkflowEvent) -> None:
            raise RuntimeError("Database logging connection dropped!")

    class HealthySubscriber(IWorkflowEventSubscriber):
        async def on_event(self, event: WorkflowEvent) -> None:
            success_received.append(event)

    dispatcher.subscribe(BrokenSubscriber())
    dispatcher.subscribe(HealthySubscriber())

    # Dispatch should NOT raise RuntimeError; broken subscriber must be isolated
    await dispatcher.publish(WorkflowStartedEvent(thread_id="t2", run_id="r2"))

    assert len(success_received) == 1
    assert success_received[0].thread_id == "t2"
    dispatcher.clear_subscribers()


@pytest.mark.asyncio
async def test_sse_bridge_subscriber():
    """Tests SSEEventBridgeSubscriber translates events into SSE text lines."""
    queue = asyncio.Queue()
    bridge = SSEEventBridgeSubscriber(queue)

    await bridge.on_event(SupervisorCompletedEvent(thread_id="t3", run_id="r3", selected_agents=["flight_agent"]))
    sse_text = await queue.get()
    assert sse_text.startswith("event: supervisor.completed\ndata: ")
    assert "flight_agent" in sse_text


# =========================================================
# 6. Builder Pattern Tests
# =========================================================

def test_travel_workflow_state_builder():
    """Tests TravelWorkflowStateBuilder validation, defaults, and construction."""
    builder = TravelWorkflowStateBuilder()
    builder.with_user_query("Plan a trip to Barcelona")
    builder.with_thread_id("thread_bcn_100")
    builder.with_user_id("user_123")

    state = builder.build()

    assert state["user_query"] == "Plan a trip to Barcelona"
    assert state["thread_id"] == "thread_bcn_100"
    assert state["user_id"] == "user_123"
    assert state["status"] == "RUNNING"
    assert state["guardrail_allowed"] is True
    assert isinstance(state["messages"], list)
    assert len(state["messages"]) == 1
    assert "agent_latencies" in state["metrics"]


def test_travel_workflow_state_builder_validation():
    """Tests that builder raises ValueError when mandatory fields are missing."""
    builder = TravelWorkflowStateBuilder()
    with pytest.raises(ValueError, match="user_query cannot be empty"):
        builder.with_user_query("   ")


def test_travel_plan_response_builder():
    """Tests TravelPlanResponseBuilder formatting, metrics, and token cost estimation."""
    raw_graph_data = {
        "user_query": "Rome 3 days",
        "final_response": "Day 1: Colosseum, Day 2: Vatican, Day 3: Trastevere",
        "status": "COMPLETED",
        "flight_results": "Direct flights available",
        "metrics": {"agent_latencies": {"supervisor": 12.0}},
    }
    builder = TravelPlanResponseBuilder(raw_graph_data, thread_id="t_rome")
    builder.with_run_id("r_rome_01")
    resp = builder.build()

    assert resp["run_id"] == "r_rome_01"
    assert resp["thread_id"] == "t_rome"
    assert resp["status"] == "COMPLETED"
    assert "token_usage" in resp["metrics"]
    assert resp["metrics"]["estimated_cost_usd"] >= 0.0


# =========================================================
# 7. Adapter Pattern Tests
# =========================================================

def test_weather_service_adapter():
    """Tests WeatherServiceAdapter parsing and EvidenceItem generation."""
    raw_output = """Current Weather:
Temperature: 22C, Clear sky

Forecast:
Day 1: Sunny, Day 2: Light rain"""

    adapted = WeatherServiceAdapter.adapt_weather_response("Nice", raw_output)
    assert adapted.city == "Nice"
    assert adapted.is_live is True
    assert "22C" in adapted.current_weather

    evidence = WeatherServiceAdapter.create_evidence_item(adapted)
    assert evidence.confidence == 0.95
    assert evidence.source_name == "OpenWeather MCP"


def test_flight_service_adapter():
    """Tests FlightServiceAdapter normalization of GDS offers."""
    raw_gds = {
        "offers": [
            {
                "offer_id": "flt_123",
                "airline": "Delta Air Lines",
                "origin": "JFK",
                "destination": "CDG",
                "total_price": 550.0,
                "currency": "USD",
                "stops": 0,
            }
        ]
    }
    offers = FlightServiceAdapter.adapt_gds_offers(raw_gds)
    assert len(offers) == 1
    assert offers[0].offer_id == "flt_123"
    assert offers[0].price == 550.0


def test_tavily_search_adapter():
    """Tests TavilySearchAdapter normalization."""
    citations = TavilySearchAdapter.adapt_search_text("Top 5 hotels in Zurich with lake view", "Zurich hotels")
    assert len(citations) == 1
    assert "Zurich" in citations[0].title
    evidence = TavilySearchAdapter.create_evidence_item(is_live=True)
    assert evidence.confidence == 0.94


# =========================================================
# 8. Decorator Pattern Tests
# =========================================================

@pytest.mark.asyncio
async def test_timed_async_decorator():
    """Tests @timed_async records execution latency and preserves docstring."""
    metrics_map = {}

    @timed_async(metric_name="test_operation", metrics_target=metrics_map)
    async def sample_task():
        """Sample docstring to verify signature preservation."""
        await asyncio.sleep(0.02)
        return 42

    assert sample_task.__doc__ == "Sample docstring to verify signature preservation."
    result = await sample_task()
    assert result == 42
    assert "test_operation" in metrics_map
    assert metrics_map["test_operation"] >= 15.0


@pytest.mark.asyncio
async def test_retry_async_decorator_transient():
    """Tests @retry_async retries on transient exceptions and succeeds."""
    attempts = 0

    @retry_async(max_retries=3, base_delay=0.01, backoff_factor=1.0)
    async def transient_operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ConnectionError("Temporary connection reset")
        return "recovered"

    result = await transient_operation()
    assert result == "recovered"
    assert attempts == 3


@pytest.mark.asyncio
async def test_retry_async_decorator_permanent_error():
    """Tests @retry_async fails immediately without retry on non-transient errors."""
    attempts = 0

    @retry_async(max_retries=3, base_delay=0.01)
    async def invalid_arg_operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid parameter supplied")

    with pytest.raises(ValueError, match="Invalid parameter supplied"):
        await invalid_arg_operation()
    # Permanent error must fail on first attempt without retrying
    assert attempts == 1


# =========================================================
# 9. CQRS Pattern Tests
# =========================================================

def test_cqrs_command_query_separation():
    """Tests CQRS separation: commands mutate state, queries strictly read without side effects."""
    cmd_handlers = WatchlistCommandHandlers(watchlist_repository)
    query_handlers = WatchlistQueryHandlers(watchlist_repository)

    # 1. State-changing Command
    cmd = CreateWatchlistCommand(
        user_id="user_cqrs",
        title="Kyoto Ryokan Search",
        target_type="hotel",
        target_value="Kyoto",
        threshold_price=250.0,
    )
    created = cmd_handlers.handle_create(cmd)
    item_id = created["id"]
    assert item_id.startswith("wl_")

    # 2. Read-only Query (pure query, zero mutations)
    query = GetWatchlistQuery(item_id=item_id, user_id="user_cqrs")
    fetched = query_handlers.handle_get(query)
    assert fetched is not None
    assert fetched["title"] == "Kyoto Ryokan Search"

    # Verify query again returns identical data
    fetched_again = query_handlers.handle_get(query)
    assert fetched_again == fetched

    # 3. Clean up via Delete Command
    del_cmd = DeleteWatchlistCommand(item_id=item_id, user_id="user_cqrs")
    assert cmd_handlers.handle_delete(del_cmd) is True
    assert query_handlers.handle_get(query) is None


def test_command_and_query_buses():
    """Tests CommandBus and QueryBus dispatching."""
    bus_cmd = CommandBus()
    bus_query = QueryBus()

    bus_cmd.register(CreateWatchlistCommand, lambda c: {"dispatched_cmd": c.title})
    bus_query.register(GetWatchlistQuery, lambda q: {"dispatched_query": q.item_id})

    res_cmd = bus_cmd.execute(CreateWatchlistCommand(user_id="u1", title="Trip A", target_type="city", target_value="A"))
    assert res_cmd == {"dispatched_cmd": "Trip A"}

    res_query = bus_query.execute(GetWatchlistQuery(item_id="item_99", user_id="u1"))
    assert res_query == {"dispatched_query": "item_99"}


# =========================================================
# 10. Circuit Breaker Pattern Tests
# =========================================================

@pytest.mark.asyncio
async def test_circuit_breaker_transient_vs_permanent():
    """Tests circuit breaker counts transient failures but ignores permanent errors."""
    breaker = CircuitBreaker("discriminated_breaker", failure_threshold=2, cooldown_seconds=0.5)

    # 1. Permanent error (ValueError): should raise, but failure_count should NOT increase
    async def permanent_fail():
        raise ValueError("Invalid format")

    with pytest.raises(ValueError):
        await breaker.call(permanent_fail)
    assert breaker.failure_count == 0
    assert breaker.state == CircuitState.CLOSED

    # 2. Transient error (ConnectionError): should increment failure_count
    async def transient_fail():
        raise ConnectionError("Connection refused by upstream host")

    with pytest.raises(ConnectionError):
        await breaker.call(transient_fail)
    assert breaker.failure_count == 1
    assert breaker.state == CircuitState.CLOSED

    # Second transient failure -> trips to OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(transient_fail)
    assert breaker.failure_count == 2
    assert breaker.state == CircuitState.OPEN

    # Subsequent request rejected fast by circuit breaker
    with pytest.raises(CircuitBreakerOpenException):
        await breaker.call(transient_fail)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_trial_concurrency():
    """Tests that HALF_OPEN state limits trial capacity and rejects excess concurrent requests."""
    breaker = CircuitBreaker(
        "concurrency_breaker",
        failure_threshold=1,
        cooldown_seconds=0.1,
        half_open_max_trials=1,
    )

    # Trip to OPEN
    with pytest.raises(ConnectionError):
        await breaker.call(AsyncMock(side_effect=ConnectionError("Downstream down")))
    assert breaker.state == CircuitState.OPEN

    # Wait for cooldown to expire
    await asyncio.sleep(0.15)

    # In HALF_OPEN: trial 1 is slow, trial 2 should be rejected due to trial saturation
    trial1_event = asyncio.Event()

    async def slow_trial():
        await trial1_event.wait()
        return "success"

    trial1_task = asyncio.create_task(breaker.call(slow_trial))
    await asyncio.sleep(0.01)  # Let trial 1 enter execution

    # Concurrent trial 2 must be rejected immediately
    with pytest.raises(CircuitBreakerOpenException, match="trial capacity is saturated"):
        await breaker.call(AsyncMock())

    # Release trial 1
    trial1_event.set()
    res1 = await trial1_task
    assert res1 == "success"
    assert breaker.state == CircuitState.CLOSED


def test_circuit_breaker_registry():
    """Tests CircuitBreakerRegistry centralized tracking and manual reset."""
    registry = CircuitBreakerRegistry()
    b1 = CircuitBreaker("reg_test_1", failure_threshold=2)
    b2 = CircuitBreaker("reg_test_2", failure_threshold=2)

    registry.register(b1)
    registry.register(b2)

    assert registry.get("reg_test_1") is b1
    all_breakers = registry.get_all()
    assert "reg_test_1" in all_breakers
    assert "reg_test_2" in all_breakers

    status = registry.get_all_status()
    assert "reg_test_1" in status
    assert status["reg_test_1"]["state"] == "CLOSED"

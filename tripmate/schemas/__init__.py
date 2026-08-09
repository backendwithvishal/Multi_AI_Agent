"""
TripMate AI Platform Schemas & Data Transfer Objects (DTOs)

This module defines Pydantic v2 schemas for all 10 platform API domains:
1. Health & Diagnostics
2. Status & Telemetry
3. AI Analysis
4. Authentication & RBAC
5. Watchlists
6. Alerts
7. Assets
8. Financial Calculations
9. Administration
10. AI Orchestration
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# =========================================================
# Generic API Response & Error Containers
# =========================================================

class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error classification code.")
    message: str = Field(description="Human-readable error summary message.")
    details: Optional[Any] = Field(default=None, description="Optional extra diagnostic details.")


class APIResponse(BaseModel, Generic[T]):
    success: bool = Field(description="Indicates successful execution.")
    data: Optional[T] = Field(default=None, description="Response payload data when successful.")
    error: Optional[ErrorDetail] = Field(default=None, description="Error detail container when unsuccessful.")
    request_id: str = Field(description="Unique correlation ID attached to request.")


# =========================================================
# 1. Health & 2. System Status Schemas
# =========================================================

class SystemStatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    uptime_seconds: float
    status: str
    circuit_breakers: Dict[str, str]
    agent_registry: List[str]
    model_tiers: Dict[str, bool]
    cache_backend: str


# =========================================================
# 3. AI Analysis Schemas
# =========================================================

class AIAnalysisRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000, description="Travel plan or prompt to analyze.")
    itinerary: Optional[str] = Field(default="", description="Optional candidate itinerary text to evaluate.")
    budget: Optional[float] = Field(default=None, ge=0, description="Optional target budget limit.")
    destination: Optional[str] = Field(default="", description="Optional target destination.")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty.")
        return cleaned


class AIAnalysisResponse(BaseModel):
    is_feasible: bool
    quality_score: float
    destination: str
    estimated_budget: Optional[float] = None
    risk_factors: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    suggested_agents: List[str] = Field(default_factory=list)
    critic_evaluation: Optional[Dict[str, Any]] = None


# =========================================================
# 4. Authentication Schemas
# =========================================================

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field(default="user", pattern="^(user|admin)$")

    @field_validator("username", "email")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip().lower()


class UserLoginRequest(BaseModel):
    username_or_email: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str


class UserProfile(BaseModel):
    id: str
    username: str
    email: str
    role: str
    created_at: str


# =========================================================
# 5. Watchlists Schemas
# =========================================================

class WatchlistCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Watchlist label, e.g. Summer in Tokyo")
    target_type: str = Field(..., pattern="^(destination|flight|hotel)$", description="Type of watched travel item")
    target_value: str = Field(..., min_length=1, max_length=200, description="Destination city, flight route (e.g. JFK-CDG), or hotel name")
    threshold_price: Optional[float] = Field(default=None, ge=0.0, description="Target price alert threshold in USD")
    notes: str = Field(default="", max_length=500)


class WatchlistItem(BaseModel):
    id: str
    user_id: str
    title: str
    target_type: str
    target_value: str
    threshold_price: Optional[float] = None
    current_price_estimate: Optional[float] = None
    currency: str = "USD"
    created_at: str
    active: bool = True


# =========================================================
# 6. Alerts Schemas
# =========================================================

class AlertCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=500)
    alert_type: str = Field(default="price_drop", pattern="^(price_drop|weather_warning|flight_status|system)$")
    severity: str = Field(default="info", pattern="^(info|warning|critical)$")
    watchlist_id: Optional[str] = None


class AlertItem(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    alert_type: str
    severity: str
    watchlist_id: Optional[str] = None
    is_read: bool = False
    created_at: str


# =========================================================
# 7. Assets Schemas
# =========================================================

class AssetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Asset display name, e.g. Flight Ticket to Paris")
    asset_type: str = Field(..., pattern="^(ticket|hotel_voucher|passport_copy|packing_list|itinerary_pdf|receipt)$")
    trip_id: Optional[str] = Field(default=None, description="Associated conversation thread or trip ID")
    content_uri: Optional[str] = Field(default="", description="Resource URI, URL, or data locator")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AssetItem(BaseModel):
    id: str
    user_id: str
    name: str
    asset_type: str
    trip_id: Optional[str] = None
    content_uri: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


# =========================================================
# 8. Financial Engine Schemas (Deterministic)
# =========================================================

class FinancialCalculationRequest(BaseModel):
    flight_estimate: float = Field(default=0.0, ge=0.0)
    hotel_nightly_rate: float = Field(default=0.0, ge=0.0)
    nights: int = Field(default=1, ge=1, le=90)
    daily_food_allowance: float = Field(default=50.0, ge=0.0)
    activities_budget: float = Field(default=0.0, ge=0.0)
    tax_rate_pct: float = Field(default=12.0, ge=0.0, le=100.0)
    contingency_buffer_pct: float = Field(default=10.0, ge=0.0, le=50.0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class FinancialCalculationResponse(BaseModel):
    subtotal: float
    hotel_total: float
    food_total: float
    flight_total: float
    activities_total: float
    taxes_and_fees: float
    contingency_buffer: float
    grand_total: float
    currency: str
    daily_average: float


class CurrencyConversionRequest(BaseModel):
    amount: float = Field(..., ge=0.0)
    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)


class CurrencyConversionResponse(BaseModel):
    original_amount: float
    from_currency: str
    converted_amount: float
    to_currency: str
    exchange_rate: float


class BudgetAnalysisRequest(BaseModel):
    target_budget: float = Field(..., gt=0.0)
    estimated_total: float = Field(..., ge=0.0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class BudgetAnalysisResponse(BaseModel):
    target_budget: float
    estimated_total: float
    currency: str
    variance: float
    is_within_budget: bool
    utilization_pct: float
    financial_advice: str


# =========================================================
# 9. Admin Management Schemas
# =========================================================

class AdminStatsResponse(BaseModel):
    total_users: int
    total_runs: int
    total_watchlists: int
    total_alerts: int
    total_assets: int
    circuit_breakers: Dict[str, str]
    cache_stats: Dict[str, Any]
    active_environment: str


class AdminResetBreakerRequest(BaseModel):
    service_name: str = Field(..., pattern="^(tavily_api|aviationstack_api|openweather_api|all)$")


# =========================================================
# 10. AI Orchestration Schemas
# =========================================================

class TravelRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's travel planning request or query.",
    )
    thread_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional unique identifier for continuing an existing conversation thread.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional identity string for authorization and thread ownership validation.",
    )

    @field_validator("message")
    @classmethod
    def validate_message_not_whitespace(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Message cannot consist only of whitespace.")
        return cleaned


class ApprovalRequest(BaseModel):
    thread_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Required thread ID of the paused execution graph.",
    )
    approved: bool = Field(
        ...,
        description="True to finalize the plan; False to request revisions.",
    )
    feedback: str = Field(
        default="",
        max_length=1000,
        description="Optional feedback instructions for revisions when rejected.",
    )
    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional identity string for authorization and thread ownership validation.",
    )

    @field_validator("feedback")
    @classmethod
    def validate_feedback(cls, v: str) -> str:
        return v.strip()


class AIPlanRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)


class AIAgentInvokeRequest(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=50)
    query: str = Field(..., min_length=1, max_length=2000)
    context: Dict[str, Any] = Field(default_factory=dict)

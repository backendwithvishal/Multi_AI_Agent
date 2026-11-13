"""
Pydantic Schemas for Trips and Itineraries
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TripCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128, description="Title of the trip project.")
    destination: str = Field(min_length=1, max_length=128, description="Primary destination.")
    start_date: Optional[str] = Field(default=None, max_length=32, description="Start date (YYYY-MM-DD).")
    end_date: Optional[str] = Field(default=None, max_length=32, description="End date (YYYY-MM-DD).")
    budget: Optional[float] = Field(default=None, ge=0, description="Allocated budget amount.")


class TripUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=128)
    destination: Optional[str] = Field(default=None, min_length=1, max_length=128)
    start_date: Optional[str] = Field(default=None, max_length=32)
    end_date: Optional[str] = Field(default=None, max_length=32)
    budget: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, max_length=32)


class TripItem(BaseModel):
    id: str
    user_id: str
    title: str
    destination: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    budget: Optional[float] = None
    status: str = "PLANNING"
    created_at: str
    updated_at: str


class ItineraryCreateRequest(BaseModel):
    content: Optional[str] = Field(default=None, description="Markdown or text representation of itinerary.")
    day_plans: Optional[Dict[str, Any]] = Field(default=None, description="Structured day-by-day activity plan.")
    status: str = Field(default="DRAFT", max_length=32)


class ItineraryUpdateRequest(BaseModel):
    content: Optional[str] = None
    day_plans: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class ItineraryItem(BaseModel):
    id: str
    trip_id: str
    user_id: str
    content: Optional[str] = None
    day_plans: Optional[Dict[str, Any]] = None
    status: str = "DRAFT"
    created_at: str
    updated_at: str


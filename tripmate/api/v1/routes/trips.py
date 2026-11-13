"""
Trips & Itineraries API Router
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import APIResponse
from tripmate.schemas.trips import (
    ItineraryCreateRequest,
    ItineraryItem,
    ItineraryUpdateRequest,
    TripCreateRequest,
    TripItem,
    TripUpdateRequest,
)
from tripmate.services.trip_service import trip_service

router = APIRouter(prefix="/trips", tags=["Trips"])


@router.get("", response_model=APIResponse[List[TripItem]])
async def list_trips(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[List[TripItem]]:
    request_id = getattr(request.state, "request_id", "req_trips")
    trips = await asyncio.to_thread(trip_service.list_trips, current_user["id"])
    return APIResponse(success=True, data=trips, error=None, request_id=request_id)


@router.post("", response_model=APIResponse[TripItem], status_code=status.HTTP_201_CREATED)
async def create_trip(
    req: TripCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[TripItem]:
    request_id = getattr(request.state, "request_id", "req_trips")
    trip = await asyncio.to_thread(trip_service.create_trip, current_user["id"], req)
    return APIResponse(success=True, data=trip, error=None, request_id=request_id)


@router.get("/{trip_id}", response_model=APIResponse[TripItem])
async def get_trip(
    trip_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[TripItem]:
    request_id = getattr(request.state, "request_id", "req_trips")
    trip = await asyncio.to_thread(trip_service.get_trip, trip_id, current_user["id"])
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_NOT_FOUND", "message": f"Trip '{trip_id}' not found."},
        )
    return APIResponse(success=True, data=trip, error=None, request_id=request_id)


@router.put("/{trip_id}", response_model=APIResponse[TripItem])
async def update_trip(
    trip_id: str,
    req: TripUpdateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[TripItem]:
    request_id = getattr(request.state, "request_id", "req_trips")
    trip = await asyncio.to_thread(trip_service.update_trip, trip_id, current_user["id"], req)
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_NOT_FOUND", "message": f"Trip '{trip_id}' not found."},
        )
    return APIResponse(success=True, data=trip, error=None, request_id=request_id)


@router.delete("/{trip_id}", response_model=APIResponse[Dict[str, Any]])
async def delete_trip(
    trip_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[Dict[str, Any]]:
    request_id = getattr(request.state, "request_id", "req_trips")
    deleted = await asyncio.to_thread(trip_service.delete_trip, trip_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_NOT_FOUND", "message": f"Trip '{trip_id}' not found."},
        )
    return APIResponse(success=True, data={"deleted": True, "id": trip_id}, error=None, request_id=request_id)


# --- Itineraries within a Trip ---


@router.get("/{trip_id}/itineraries", response_model=APIResponse[List[ItineraryItem]])
async def list_itineraries(
    trip_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[List[ItineraryItem]]:
    request_id = getattr(request.state, "request_id", "req_trips")
    try:
        itineraries = await asyncio.to_thread(trip_service.list_itineraries, trip_id, current_user["id"])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_NOT_FOUND", "message": str(exc)},
        )
    return APIResponse(success=True, data=itineraries, error=None, request_id=request_id)


@router.post(
    "/{trip_id}/itineraries",
    response_model=APIResponse[ItineraryItem],
    status_code=status.HTTP_201_CREATED,
)
async def create_itinerary(
    trip_id: str,
    req: ItineraryCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[ItineraryItem]:
    request_id = getattr(request.state, "request_id", "req_trips")
    try:
        itinerary = await asyncio.to_thread(trip_service.create_itinerary, trip_id, current_user["id"], req)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TRIP_NOT_FOUND", "message": str(exc)},
        )
    return APIResponse(success=True, data=itinerary, error=None, request_id=request_id)


@router.get("/{trip_id}/itineraries/{itinerary_id}", response_model=APIResponse[ItineraryItem])
async def get_itinerary(
    trip_id: str,
    itinerary_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[ItineraryItem]:
    request_id = getattr(request.state, "request_id", "req_trips")
    it = await asyncio.to_thread(trip_service.get_itinerary, itinerary_id, current_user["id"])
    if not it or it.trip_id != trip_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ITINERARY_NOT_FOUND", "message": f"Itinerary '{itinerary_id}' not found."},
        )
    return APIResponse(success=True, data=it, error=None, request_id=request_id)


@router.delete("/{trip_id}/itineraries/{itinerary_id}", response_model=APIResponse[Dict[str, Any]])
async def delete_itinerary(
    trip_id: str,
    itinerary_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> APIResponse[Dict[str, Any]]:
    request_id = getattr(request.state, "request_id", "req_trips")
    deleted = await asyncio.to_thread(trip_service.delete_itinerary, itinerary_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ITINERARY_NOT_FOUND", "message": f"Itinerary '{itinerary_id}' not found."},
        )
    return APIResponse(success=True, data={"deleted": True, "id": itinerary_id}, error=None, request_id=request_id)


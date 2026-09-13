"""
GDS Travel Booking & Reservation API Router

Endpoints:
- GET /api/v1/booking/flights/search: Live GDS flight offers search
- GET /api/v1/booking/hotels/search: Live GDS hotel offers search
- POST /api/v1/booking/price-lock: Lock fare rate for 15 minutes
- POST /api/v1/booking/reserve: Complete reservation & generate GDS PNR
- GET /api/v1/booking/reservations/{booking_id}: Get reservation details
"""

import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from tripmate.api.dependencies import get_current_user
from tripmate.integrations.gds import gds_client
from tripmate.schemas import APIResponse

router = APIRouter(prefix="/booking", tags=["GDS Travel Booking & Search"])


class PriceLockRequest(BaseModel):
    offer_id: str = Field(..., description="Flight or hotel offer identifier")
    offer_type: str = Field(..., description="Type of offer ('flight' or 'hotel')")
    total_price: float = Field(..., gt=0, description="Total price to lock")
    currency: str = Field(default="USD", description="Currency code")


class ReservationRequest(BaseModel):
    lock_id: str = Field(..., description="Active price lock identifier")
    passenger_name: str = Field(..., min_length=2, description="Full name of primary passenger")
    passenger_email: str = Field(..., min_length=5, description="Contact email address")
    special_requests: str = Field(default="", description="Optional special dietary/seating/room requests")


@router.get("/flights/search", response_model=APIResponse[Dict[str, Any]], summary="Search live GDS flights")
async def search_flights(
    request: Request,
    origin: str = Query(..., min_length=3, max_length=4, description="Origin IATA airport code (e.g. JFK)"),
    destination: str = Query(..., min_length=3, max_length=4, description="Destination IATA airport code (e.g. LHR)"),
    departure_date: str = Query(..., description="Departure date (YYYY-MM-DD)"),
    return_date: Optional[str] = Query(None, description="Optional return date (YYYY-MM-DD)"),
    adults: int = Query(1, ge=1, le=9, description="Number of adult passengers"),
    cabin_class: str = Query("ECONOMY", description="Cabin class (ECONOMY, PREMIUM, BUSINESS)"),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    try:
        results = await gds_client.search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            cabin_class=cabin_class,
        )
        return APIResponse(
            success=True,
            data=results,
            error=None,
            request_id=request_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GDS_SEARCH_ERROR", "message": f"Flight search failed: {exc}"},
        )


@router.get("/hotels/search", response_model=APIResponse[Dict[str, Any]], summary="Search live GDS hotels")
async def search_hotels(
    request: Request,
    city_code: str = Query(..., min_length=3, max_length=4, description="City / Airport IATA code (e.g. PAR, NYC)"),
    check_in_date: str = Query(..., description="Check-in date (YYYY-MM-DD)"),
    check_out_date: str = Query(..., description="Check-out date (YYYY-MM-DD)"),
    guests: int = Query(2, ge=1, le=8, description="Number of guests"),
    rooms: int = Query(1, ge=1, le=4, description="Number of rooms"),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    try:
        results = await gds_client.search_hotels(
            city_code=city_code,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            guests=guests,
            rooms=rooms,
        )
        return APIResponse(
            success=True,
            data=results,
            error=None,
            request_id=request_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "GDS_SEARCH_ERROR", "message": f"Hotel search failed: {exc}"},
        )


@router.post("/price-lock", response_model=APIResponse[Dict[str, Any]], summary="Lock fare price for 15 minutes")
async def lock_price(
    req: PriceLockRequest,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    lock_record = await gds_client.lock_price(
        offer_id=req.offer_id,
        offer_type=req.offer_type,
        total_price=req.total_price,
        currency=req.currency,
    )
    return APIResponse(
        success=True,
        data=lock_record,
        error=None,
        request_id=request_id,
    )


@router.post("/reserve", response_model=APIResponse[Dict[str, Any]], summary="Finalize booking reservation & generate PNR")
async def create_reservation(
    req: ReservationRequest,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else "user_anonymous"
    try:
        reservation = await gds_client.create_reservation(
            user_id=user_id,
            lock_id=req.lock_id,
            passenger_name=req.passenger_name,
            passenger_email=req.passenger_email,
            special_requests=req.special_requests,
        )
        return APIResponse(
            success=True,
            data=reservation,
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "RESERVATION_FAILED", "message": str(exc)},
        )


@router.get("/reservations/{booking_id}", response_model=APIResponse[Dict[str, Any]], summary="Get booking details")
async def get_reservation(
    booking_id: str,
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", f"req_{uuid.uuid4().hex[:12]}")
    user_id = current_user.get("id") or current_user.get("uid") if current_user else None
    user_role = current_user.get("role") or current_user.get("rol") if current_user else "user"

    effective_user_id = None if user_role == "admin" else user_id
    reservation = gds_client.get_reservation(booking_id, user_id=effective_user_id)
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BOOKING_NOT_FOUND", "message": f"Reservation '{booking_id}' not found."},
        )
    return APIResponse(
        success=True,
        data=reservation,
        error=None,
        request_id=request_id,
    )

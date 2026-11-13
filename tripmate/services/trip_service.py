"""
Trip & Itinerary Domain Service
"""

from typing import Any, Dict, List, Optional

from tripmate.repositories.interfaces import IItineraryRepository, ITripRepository
from tripmate.repositories.store_repositories import itinerary_repository, trip_repository
from tripmate.schemas.trips import (
    ItineraryCreateRequest,
    ItineraryItem,
    ItineraryUpdateRequest,
    TripCreateRequest,
    TripItem,
    TripUpdateRequest,
)


class TripService:
    """Domain service managing user-scoped trips and day-by-day itineraries."""

    def __init__(
        self,
        trip_repo: Optional[ITripRepository] = None,
        itinerary_repo: Optional[IItineraryRepository] = None,
    ):
        self._trip_repo = trip_repo or trip_repository
        self._itinerary_repo = itinerary_repo or itinerary_repository

    def create_trip(self, user_id: str, req: TripCreateRequest) -> TripItem:
        trip = self._trip_repo.create(
            user_id=user_id,
            title=req.title,
            destination=req.destination,
            start_date=req.start_date,
            end_date=req.end_date,
            budget=req.budget,
        )
        return TripItem(**trip)

    def get_trip(self, trip_id: str, user_id: str) -> Optional[TripItem]:
        trip = self._trip_repo.get_by_id(trip_id, user_id)
        return TripItem(**trip) if trip else None

    def list_trips(self, user_id: str) -> List[TripItem]:
        trips = self._trip_repo.list_by_user(user_id)
        return [TripItem(**t) for t in trips]

    def update_trip(self, trip_id: str, user_id: str, req: TripUpdateRequest) -> Optional[TripItem]:
        updates = req.model_dump(exclude_unset=True)
        trip = self._trip_repo.update(trip_id, user_id, updates)
        return TripItem(**trip) if trip else None

    def delete_trip(self, trip_id: str, user_id: str) -> bool:
        return self._trip_repo.delete(trip_id, user_id)

    def create_itinerary(self, trip_id: str, user_id: str, req: ItineraryCreateRequest) -> ItineraryItem:
        # Verify trip exists and belongs to user
        trip = self._trip_repo.get_by_id(trip_id, user_id)
        if not trip:
            raise ValueError(f"Trip '{trip_id}' not found or access denied.")

        itinerary = self._itinerary_repo.create(
            trip_id=trip_id,
            user_id=user_id,
            content=req.content,
            day_plans=req.day_plans,
            status=req.status,
        )
        return ItineraryItem(**itinerary)

    def get_itinerary(self, itinerary_id: str, user_id: str) -> Optional[ItineraryItem]:
        it = self._itinerary_repo.get_by_id(itinerary_id, user_id)
        return ItineraryItem(**it) if it else None

    def list_itineraries(self, trip_id: str, user_id: str) -> List[ItineraryItem]:
        trip = self._trip_repo.get_by_id(trip_id, user_id)
        if not trip:
            raise ValueError(f"Trip '{trip_id}' not found or access denied.")
        itineraries = self._itinerary_repo.list_by_trip(trip_id, user_id)
        return [ItineraryItem(**i) for i in itineraries]

    def update_itinerary(
        self, itinerary_id: str, user_id: str, req: ItineraryUpdateRequest
    ) -> Optional[ItineraryItem]:
        updates = req.model_dump(exclude_unset=True)
        it = self._itinerary_repo.update(itinerary_id, user_id, updates)
        return ItineraryItem(**it) if it else None

    def delete_itinerary(self, itinerary_id: str, user_id: str) -> bool:
        return self._itinerary_repo.delete(itinerary_id, user_id)


trip_service = TripService()


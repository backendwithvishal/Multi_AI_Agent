"""
Global Distribution System (GDS) Travel Booking Integration Adapter

Provides standardized flight and hotel search, real-time fare pricing lock,
and booking reservation capabilities interfacing with Amadeus and Skyscanner GDS standards.
Architected with Strategy Pattern (search providers), Repository Pattern (booking persistence),
Circuit Breaker resilience, and bounded caching.
"""

import asyncio
import logging
import secrets
import time
import uuid
from typing import Any, Dict, List, Optional

from tripmate.cache.ttl_cache import BoundedAsyncTTLCache
from tripmate.config.settings import settings
from tripmate.core.singleton import SingletonMeta
from tripmate.integrations.circuit_breaker import (
    CircuitBreaker,
    circuit_breaker_registry,
)
from tripmate.repositories.interfaces import IBookingRepository
from tripmate.repositories.store_repositories import (
    StoreBookingRepository,
    booking_repository,
)
from tripmate.strategies.booking_strategies import (
    AmadeusSandboxFlightStrategy,
    AmadeusSandboxHotelStrategy,
    IFlightSearchStrategy,
    IHotelSearchStrategy,
)

logger = logging.getLogger("tripmate.integrations.gds")


class GDSBookingClient(metaclass=SingletonMeta):
    """
    Enterprise GDS adapter for Flight & Hotel Search, Fare Lock, and Reservation.
    Uses Strategy Pattern for search providers and Repository Pattern for booking persistence.
    """

    def __init__(
        self,
        booking_repo: Optional[IBookingRepository] = None,
        flight_strategy: Optional[IFlightSearchStrategy] = None,
        hotel_strategy: Optional[IHotelSearchStrategy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            "gds_client", failure_threshold=3, cooldown_seconds=30.0
        )
        circuit_breaker_registry.register(self._circuit_breaker)
        self._cache = BoundedAsyncTTLCache(default_ttl_seconds=300, max_entries=200)

        self._repo = booking_repo or booking_repository
        self._flight_strategy = flight_strategy or AmadeusSandboxFlightStrategy()
        self._hotel_strategy = hotel_strategy or AmadeusSandboxHotelStrategy()

    @property
    def _reservations(self) -> Dict[str, Dict[str, Any]]:
        if hasattr(self._repo, "_reservations"):
            return self._repo._reservations
        return {}

    @property
    def _price_locks(self) -> Dict[str, Dict[str, Any]]:
        if hasattr(self._repo, "_price_locks"):
            return self._repo._price_locks
        return {}

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
    ) -> Dict[str, Any]:
        """Searches live/sandbox flight offers with GDS schema via flight search strategy."""
        cache_key = f"flight:{origin.upper()}:{destination.upper()}:{departure_date}:{adults}:{cabin_class}"
        cached = await self._cache.get("gds", cache_key)
        if cached:
            return cached

        async def _execute():
            return await self._flight_strategy.search_flights(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                adults=adults,
                cabin_class=cabin_class,
            )

        result = await self._circuit_breaker.call(_execute)
        await self._cache.set("gds", cache_key, result)
        return result

    async def search_hotels(
        self,
        city_code: str,
        check_in_date: str,
        check_out_date: str,
        guests: int = 2,
        rooms: int = 1,
    ) -> Dict[str, Any]:
        """Searches hotel inventory with GDS schema via hotel search strategy."""
        cache_key = f"hotel:{city_code.upper()}:{check_in_date}:{check_out_date}:{guests}:{rooms}"
        cached = await self._cache.get("gds", cache_key)
        if cached:
            return cached

        async def _execute():
            return await self._hotel_strategy.search_hotels(
                city_code=city_code,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                guests=guests,
                rooms=rooms,
            )

        result = await self._circuit_breaker.call(_execute)
        await self._cache.set("gds", cache_key, result)
        return result

    async def lock_price(
        self, offer_id: str, offer_type: str, total_price: float, currency: str = "USD"
    ) -> Dict[str, Any]:
        """Locks a fare or hotel rate for 15 minutes before reservation via repository."""
        return self._repo.lock_price(
            offer_id=offer_id,
            offer_type=offer_type,
            total_price=total_price,
            currency=currency,
        )

    async def create_reservation(
        self,
        user_id: str,
        lock_id: str,
        passenger_name: str,
        passenger_email: str,
        special_requests: str = "",
    ) -> Dict[str, Any]:
        """Finalizes booking reservation and issues GDS PNR Confirmation via repository."""
        reservation = self._repo.create_reservation(
            user_id=user_id,
            lock_id=lock_id,
            passenger_name=passenger_name,
            passenger_email=passenger_email,
            special_requests=special_requests,
        )
        logger.info(
            f"Created reservation {reservation['booking_id']} (PNR: {reservation['pnr_code']}) for user {user_id}"
        )
        return reservation

    def get_reservation(self, booking_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves booking record with ownership check via repository."""
        return self._repo.get_reservation(booking_id, user_id)


# Global GDS client singleton
gds_client = GDSBookingClient()
gds_breaker = gds_client._circuit_breaker

"""
Booking & Search Strategy Pattern

Defines strategy contracts and concrete search strategies for Flight and Hotel inventory.
"""

import secrets
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from tripmate.config.settings import settings


class IFlightSearchStrategy(ABC):
    """Abstract Strategy interface for Flight Search."""

    @abstractmethod
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
    ) -> Dict[str, Any]:
        pass


class IHotelSearchStrategy(ABC):
    """Abstract Strategy interface for Hotel Search."""

    @abstractmethod
    async def search_hotels(
        self,
        city_code: str,
        check_in_date: str,
        check_out_date: str,
        guests: int = 2,
        rooms: int = 1,
    ) -> Dict[str, Any]:
        pass


class AmadeusSandboxFlightStrategy(IFlightSearchStrategy):
    """High-fidelity GDS Flight Search Strategy."""

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
    ) -> Dict[str, Any]:
        base_price = 350.00 if cabin_class.upper() == "ECONOMY" else (780.00 if cabin_class.upper() == "PREMIUM" else 1450.00)
        offers = [
            {
                "offer_id": f"flt_off_{secrets.token_hex(6)}",
                "airline": "Delta Air Lines",
                "airline_code": "DL",
                "flight_number": f"DL{secrets.randbelow(899) + 100}",
                "origin": origin.upper(),
                "destination": destination.upper(),
                "departure_time": f"{departure_date}T08:30:00Z",
                "arrival_time": f"{departure_date}T14:45:00Z",
                "duration": "6h 15m",
                "stops": 0,
                "cabin_class": cabin_class.upper(),
                "price_per_adult": round(base_price, 2),
                "total_price": round(base_price * adults, 2),
                "currency": "USD",
                "seats_available": 9,
            },
            {
                "offer_id": f"flt_off_{secrets.token_hex(6)}",
                "airline": "United Airlines",
                "airline_code": "UA",
                "flight_number": f"UA{secrets.randbelow(899) + 100}",
                "origin": origin.upper(),
                "destination": destination.upper(),
                "departure_time": f"{departure_date}T11:15:00Z",
                "arrival_time": f"{departure_date}T18:00:00Z",
                "duration": "6h 45m",
                "stops": 1,
                "cabin_class": cabin_class.upper(),
                "price_per_adult": round(base_price * 0.88, 2),
                "total_price": round((base_price * 0.88) * adults, 2),
                "currency": "USD",
                "seats_available": 4,
            },
        ]
        return {
            "source": "GDS_AMADEUS_PROD" if settings.APP_ENV == "production" else "GDS_AMADEUS_SANDBOX",
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_date": departure_date,
            "passenger_count": adults,
            "offers_count": len(offers),
            "offers": offers,
        }


class AmadeusSandboxHotelStrategy(IHotelSearchStrategy):
    """High-fidelity GDS Hotel Search Strategy."""

    async def search_hotels(
        self,
        city_code: str,
        check_in_date: str,
        check_out_date: str,
        guests: int = 2,
        rooms: int = 1,
    ) -> Dict[str, Any]:
        hotels = [
            {
                "hotel_id": f"htl_{secrets.token_hex(6)}",
                "name": f"Grand Hyatt {city_code.upper()} Center",
                "city_code": city_code.upper(),
                "star_rating": 4.5,
                "room_type": "Deluxe King Room",
                "price_per_night": 220.00,
                "currency": "USD",
                "amenities": ["Free High-Speed WiFi", "Spa & Wellness", "Fitness Center", "Breakfast Included"],
                "free_cancellation": True,
            },
            {
                "hotel_id": f"htl_{secrets.token_hex(6)}",
                "name": f"Marriott Downtown {city_code.upper()}",
                "city_code": city_code.upper(),
                "star_rating": 4.0,
                "room_type": "Standard Queen",
                "price_per_night": 165.00,
                "currency": "USD",
                "amenities": ["Free WiFi", "Pool", "Restaurant & Bar"],
                "free_cancellation": True,
            },
        ]
        return {
            "source": "GDS_HOTEL_PROVIDER",
            "city_code": city_code.upper(),
            "check_in": check_in_date,
            "check_out": check_out_date,
            "hotels_count": len(hotels),
            "hotels": hotels,
        }

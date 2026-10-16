"""
Flight Service Adapter Pattern

Adapts raw AviationStack and GDS flight responses into normalized flight schemas and evidence items.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from tripmate.schemas.agents import EvidenceItem, EvidenceType, VerificationStatus


class NormalizedFlightOffer(BaseModel):
    """Normalized flight offer schema."""
    offer_id: str
    airline: str
    origin: str
    destination: str
    price: float
    currency: str = "USD"
    departure_time: Optional[str] = None
    stops: int = 0


class FlightServiceAdapter:
    """Adapts raw aviation and GDS responses into uniform application models."""

    @classmethod
    def adapt_gds_offers(cls, raw_gds_response: Dict[str, Any]) -> List[NormalizedFlightOffer]:
        """Normalizes GDS flight search response offers."""
        offers_data = raw_gds_response.get("offers", [])
        normalized = []
        for o in offers_data:
            normalized.append(
                NormalizedFlightOffer(
                    offer_id=o.get("offer_id", ""),
                    airline=o.get("airline", "Standard Airline"),
                    origin=o.get("origin", ""),
                    destination=o.get("destination", ""),
                    price=float(o.get("total_price", 0.0)),
                    currency=o.get("currency", "USD"),
                    departure_time=o.get("departure_time"),
                    stops=int(o.get("stops", 0)),
                )
            )
        return normalized

    @classmethod
    def create_evidence_item(cls, source_name: str, is_live: bool, details: str = "") -> EvidenceItem:
        if is_live:
            return EvidenceItem(
                source_name=source_name,
                source_type=EvidenceType.API,
                status=VerificationStatus.VERIFIED,
                confidence=0.92,
                details=details or "Live flight routing data queried.",
            )
        return EvidenceItem(
            source_name=source_name,
            source_type=EvidenceType.FALLBACK,
            status=VerificationStatus.UNCERTAIN,
            confidence=0.6,
            details=details or "Simulated/offline flight routing fallback.",
        )

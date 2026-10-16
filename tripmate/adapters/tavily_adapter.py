"""
Tavily Web Search Adapter Pattern

Adapts raw Tavily Search MCP responses into normalized search citations and evidence items.
"""

from typing import Any, Dict, List
from pydantic import BaseModel
from tripmate.schemas.agents import EvidenceItem, EvidenceType, VerificationStatus


class NormalizedSearchCitation(BaseModel):
    """Normalized search citation result."""
    title: str
    content: str
    url: str = ""
    relevance_score: float = 0.85


class TavilySearchAdapter:
    """Adapts raw Tavily search results into application models and evidence items."""

    @classmethod
    def adapt_search_text(cls, raw_text: str, query: str) -> List[NormalizedSearchCitation]:
        cleaned = raw_text.strip() if raw_text else ""
        if not cleaned:
            return []

        # Parse basic snippets or return full snippet
        return [
            NormalizedSearchCitation(
                title=f"Search findings for '{query[:40]}'",
                content=cleaned[:1500],
                url="https://tavily.com",
                relevance_score=0.9 if "temporarily unavailable" not in cleaned else 0.5,
            )
        ]

    @classmethod
    def create_evidence_item(cls, is_live: bool, details: str = "") -> EvidenceItem:
        if is_live:
            return EvidenceItem(
                source_name="Tavily Search MCP",
                source_type=EvidenceType.API,
                status=VerificationStatus.VERIFIED,
                confidence=0.94,
                details=details or "Live web destination & hotel data queried.",
            )
        return EvidenceItem(
            source_name="Tavily Fallback Cache",
            source_type=EvidenceType.FALLBACK,
            status=VerificationStatus.UNCERTAIN,
            confidence=0.55,
            details=details or "Fallback destination advice provided.",
        )

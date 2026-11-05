"""
Watchlist Domain Service

Manages travel price watchlists for destinations, flights, and hotels.
"""

from typing import List, Optional
from tripmate.database.store import store
from tripmate.schemas import WatchlistCreateRequest, WatchlistItem


class WatchlistService:
    """Service managing destination, flight, and hotel price watchlists."""

    def __init__(self, data_store=None):
        self._store = data_store or store

    def add_item(self, user_id: str, req: WatchlistCreateRequest) -> WatchlistItem:
        item_data = self._store.create_watchlist(
            user_id=user_id,
            title=req.title,
            target_type=req.target_type,
            target_value=req.target_value,
            threshold_price=req.threshold_price,
            notes=req.notes,
        )
        return WatchlistItem(**item_data)

    def list_items(self, user_id: str) -> List[WatchlistItem]:
        items = self._store.list_watchlists(user_id=user_id)
        return [WatchlistItem(**item) for item in items]

    def get_item(self, item_id: str, user_id: str) -> Optional[WatchlistItem]:
        item = self._store.get_watchlist(item_id=item_id, user_id=user_id)
        return WatchlistItem(**item) if item else None

    def delete_item(self, item_id: str, user_id: str) -> bool:
        return self._store.delete_watchlist(item_id=item_id, user_id=user_id)


watchlist_service = WatchlistService()

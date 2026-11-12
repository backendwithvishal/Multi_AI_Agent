"""
Price Watch Domain Service

Manages travel price watches for destinations, flights, and hotels.
"""

from typing import List, Optional

from tripmate.database.store import store
from tripmate.schemas import WatchlistCreateRequest, WatchlistItem


class PriceWatchService:
    """Service managing destination, flight, and hotel price watches."""

    def __init__(self, data_store=None, repo=None):
        self._repo = repo
        self._store = data_store or store

    def add_item(self, user_id: str, req: WatchlistCreateRequest) -> WatchlistItem:
        if self._repo:
            item_data = self._repo.create(
                user_id=user_id,
                title=req.title,
                target_type=req.target_type,
                target_value=req.target_value,
                threshold_price=req.threshold_price,
                notes=req.notes,
            )
        else:
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
        if self._repo:
            items = self._repo.list_by_user(user_id=user_id)
        else:
            items = self._store.list_watchlists(user_id=user_id)
        return [WatchlistItem(**item) for item in items]

    def get_item(self, item_id: str, user_id: str) -> Optional[WatchlistItem]:
        if self._repo:
            item = self._repo.get_by_id(item_id=item_id, user_id=user_id)
        else:
            item = self._store.get_watchlist(item_id=item_id, user_id=user_id)
        return WatchlistItem(**item) if item else None

    def delete_item(self, item_id: str, user_id: str) -> bool:
        if self._repo:
            return self._repo.delete(item_id=item_id, user_id=user_id)
        return self._store.delete_watchlist(item_id=item_id, user_id=user_id)


price_watch_service = PriceWatchService()
WatchlistService = PriceWatchService
watchlist_service = price_watch_service

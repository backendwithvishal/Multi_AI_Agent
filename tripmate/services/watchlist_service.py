"""
Watchlist Domain Service (Refactored with CQRS & Repository Patterns)

Manages travel watchlists for destinations, flights, and hotels, and checks price threshold triggers.
Routes all mutations through Command Handlers and all retrievals through Query Handlers.
"""

from typing import List, Optional
from tripmate.cqrs.commands import CreateWatchlistCommand, DeleteWatchlistCommand
from tripmate.cqrs.handlers import WatchlistCommandHandlers, WatchlistQueryHandlers
from tripmate.cqrs.queries import GetWatchlistQuery, ListWatchlistsQuery
from tripmate.repositories.interfaces import IWatchlistRepository
from tripmate.repositories.store_repositories import watchlist_repository
from tripmate.schemas import WatchlistCreateRequest, WatchlistItem


class WatchlistService:
    """Service managing destination, flight, and hotel price watchlists using CQRS."""

    def __init__(
        self,
        command_handler: Optional[WatchlistCommandHandlers] = None,
        query_handler: Optional[WatchlistQueryHandlers] = None,
        repo: Optional[IWatchlistRepository] = None,
    ):
        repository = repo or watchlist_repository
        self._command_handler = command_handler or WatchlistCommandHandlers(repository)
        self._query_handler = query_handler or WatchlistQueryHandlers(repository)

    def add_item(self, user_id: str, req: WatchlistCreateRequest) -> WatchlistItem:
        """Executes CreateWatchlistCommand to persist new watchlist entry."""
        cmd = CreateWatchlistCommand(
            user_id=user_id,
            title=req.title,
            target_type=req.target_type,
            target_value=req.target_value,
            threshold_price=req.threshold_price,
            notes=req.notes,
        )
        item_data = self._command_handler.handle_create(cmd)
        return WatchlistItem(**item_data)

    def list_items(self, user_id: str) -> List[WatchlistItem]:
        """Executes ListWatchlistsQuery (read-only)."""
        query = ListWatchlistsQuery(user_id=user_id)
        items = self._query_handler.handle_list(query)
        return [WatchlistItem(**item) for item in items]

    def get_item(self, item_id: str, user_id: str) -> Optional[WatchlistItem]:
        """Executes GetWatchlistQuery (read-only)."""
        query = GetWatchlistQuery(item_id=item_id, user_id=user_id)
        item = self._query_handler.handle_get(query)
        return WatchlistItem(**item) if item else None

    def delete_item(self, item_id: str, user_id: str) -> bool:
        """Executes DeleteWatchlistCommand to remove watchlist entry."""
        cmd = DeleteWatchlistCommand(item_id=item_id, user_id=user_id)
        return self._command_handler.handle_delete(cmd)


watchlist_service = WatchlistService()

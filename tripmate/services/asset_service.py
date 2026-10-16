"""
Travel Asset & Document Management Service (Refactored with CQRS & Repository Patterns)

Manages itinerary documents, e-tickets, hotel booking vouchers, and packing checklists.
Routes mutations through Command Handlers and read requests through Query Handlers.
"""

from typing import List, Optional
from tripmate.cqrs.commands import CreateAssetCommand, DeleteAssetCommand
from tripmate.cqrs.handlers import AssetCommandHandlers, AssetQueryHandlers
from tripmate.cqrs.queries import GetAssetQuery, ListAssetsQuery
from tripmate.repositories.interfaces import IAssetRepository
from tripmate.repositories.store_repositories import asset_repository
from tripmate.schemas import AssetCreateRequest, AssetItem


class AssetService:
    """Service managing trip assets and travel documentation using CQRS."""

    def __init__(
        self,
        command_handler: Optional[AssetCommandHandlers] = None,
        query_handler: Optional[AssetQueryHandlers] = None,
        repo: Optional[IAssetRepository] = None,
    ):
        repository = repo or asset_repository
        self._command_handler = command_handler or AssetCommandHandlers(repository)
        self._query_handler = query_handler or AssetQueryHandlers(repository)

    def create_asset(self, user_id: str, req: AssetCreateRequest) -> AssetItem:
        """Executes CreateAssetCommand to persist travel asset."""
        cmd = CreateAssetCommand(
            user_id=user_id,
            name=req.name,
            asset_type=req.asset_type,
            trip_id=req.trip_id,
            content_uri=req.content_uri,
            metadata=req.metadata,
        )
        asset_data = self._command_handler.handle_create(cmd)
        return AssetItem(**asset_data)

    def list_assets(self, user_id: str, trip_id: Optional[str] = None) -> List[AssetItem]:
        """Executes ListAssetsQuery (read-only)."""
        query = ListAssetsQuery(user_id=user_id, trip_id=trip_id)
        assets = self._query_handler.handle_list(query)
        return [AssetItem(**a) for a in assets]

    def get_asset(self, asset_id: str, user_id: str) -> Optional[AssetItem]:
        """Executes GetAssetQuery (read-only)."""
        query = GetAssetQuery(asset_id=asset_id, user_id=user_id)
        asset = self._query_handler.handle_get(query)
        return AssetItem(**asset) if asset else None

    def delete_asset(self, asset_id: str, user_id: str) -> bool:
        """Executes DeleteAssetCommand to remove a travel asset."""
        cmd = DeleteAssetCommand(asset_id=asset_id, user_id=user_id)
        return self._command_handler.handle_delete(cmd)


asset_service = AssetService()

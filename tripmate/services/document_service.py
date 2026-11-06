"""
Travel Document & Asset Management Service

Manages itinerary documents, e-tickets, hotel booking vouchers, and packing checklists.
"""

from typing import List, Optional

from tripmate.database.store import store
from tripmate.schemas import AssetCreateRequest, AssetItem


class DocumentService:
    """Service managing trip documentation and travel assets."""

    def __init__(self, data_store=None):
        self._store = data_store or store

    def create_asset(self, user_id: str, req: AssetCreateRequest) -> AssetItem:
        asset_data = self._store.create_asset(
            user_id=user_id,
            name=req.name,
            asset_type=req.asset_type,
            trip_id=req.trip_id,
            content_uri=req.content_uri,
            metadata=req.metadata,
        )
        return AssetItem(**asset_data)

    def list_assets(self, user_id: str, trip_id: Optional[str] = None) -> List[AssetItem]:
        assets = self._store.list_assets(user_id=user_id, trip_id=trip_id)
        return [AssetItem(**a) for a in assets]

    def get_asset(self, asset_id: str, user_id: str) -> Optional[AssetItem]:
        asset = self._store.get_asset(asset_id=asset_id, user_id=user_id)
        return AssetItem(**asset) if asset else None

    def delete_asset(self, asset_id: str, user_id: str) -> bool:
        return self._store.delete_asset(asset_id=asset_id, user_id=user_id)


document_service = DocumentService()
AssetService = DocumentService
asset_service = document_service

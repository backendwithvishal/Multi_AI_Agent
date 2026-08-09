"""
Travel Asset & Document Management Service

Manages itinerary documents, e-tickets, hotel booking vouchers, and packing checklists.
"""

from typing import Any, Dict, List, Optional
from tripmate.database.store import store
from tripmate.schemas import AssetCreateRequest, AssetItem


class AssetService:
    """Service managing trip assets and travel documentation."""

    def create_asset(self, user_id: str, req: AssetCreateRequest) -> AssetItem:
        asset_data = store.create_asset(
            user_id=user_id,
            name=req.name,
            asset_type=req.asset_type,
            trip_id=req.trip_id,
            content_uri=req.content_uri,
            metadata=req.metadata,
        )
        return AssetItem(**asset_data)

    def list_assets(self, user_id: str, trip_id: Optional[str] = None) -> List[AssetItem]:
        assets = store.list_assets(user_id=user_id, trip_id=trip_id)
        return [AssetItem(**a) for a in assets]

    def get_asset(self, asset_id: str, user_id: str) -> Optional[AssetItem]:
        asset = store.get_asset(asset_id, user_id)
        return AssetItem(**asset) if asset else None

    def delete_asset(self, asset_id: str, user_id: str) -> bool:
        return store.delete_asset(asset_id, user_id)


asset_service = AssetService()

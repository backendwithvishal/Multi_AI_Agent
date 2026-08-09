"""
Travel Assets & Document Management API Router

Endpoints:
- GET /api/v1/assets: List user travel assets (optionally filtered by trip_id)
- POST /api/v1/assets: Register/attach a travel asset (e-ticket, hotel voucher, packing list)
- GET /api/v1/assets/{asset_id}: Retrieve asset metadata
- DELETE /api/v1/assets/{asset_id}: Delete a travel asset
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from tripmate.schemas import APIResponse, AssetCreateRequest, AssetItem
from tripmate.services.asset_service import asset_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/assets", tags=["Travel Assets & Documents"])


@router.get(
    "",
    summary="List Travel Assets",
    description="Returns all travel documents and assets for the authenticated user.",
    response_model=APIResponse[List[AssetItem]],
)
async def list_assets(
    request: Request,
    trip_id: Optional[str] = Query(None, description="Optional filter by associated trip ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ast")
    assets = asset_service.list_assets(current_user["id"], trip_id=trip_id)
    return APIResponse(
        success=True,
        data=assets,
        error=None,
        request_id=request_id,
    )


@router.post(
    "",
    summary="Create / Attach Travel Asset",
    description="Attaches a travel document, voucher, e-ticket, or checklist to a trip.",
    response_model=APIResponse[AssetItem],
)
async def create_asset(
    req: AssetCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ast")
    asset = asset_service.create_asset(current_user["id"], req)
    return APIResponse(
        success=True,
        data=asset,
        error=None,
        request_id=request_id,
    )


@router.get(
    "/{asset_id}",
    summary="Get Travel Asset Details",
    description="Retrieves metadata for a specific travel asset.",
    response_model=APIResponse[AssetItem],
)
async def get_asset(
    asset_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ast")
    asset = asset_service.get_asset(asset_id, current_user["id"])
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_FOUND", "message": f"Asset ID '{asset_id}' not found."},
        )
    return APIResponse(
        success=True,
        data=asset,
        error=None,
        request_id=request_id,
    )


@router.delete(
    "/{asset_id}",
    summary="Delete Travel Asset",
    description="Deletes a travel asset from the user's account.",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_asset(
    asset_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ast")
    deleted = asset_service.delete_asset(asset_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_FOUND", "message": f"Asset ID '{asset_id}' not found."},
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": asset_id},
        error=None,
        request_id=request_id,
    )

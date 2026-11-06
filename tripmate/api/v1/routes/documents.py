"""
Travel Documents & Assets API Router

Endpoints:
- GET /api/v1/documents: List user travel documents/vouchers (optionally filtered by trip_id)
- POST /api/v1/documents: Register/attach a travel document (e-ticket, hotel voucher, packing list)
- GET /api/v1/documents/{doc_id}: Retrieve document metadata
- DELETE /api/v1/documents/{doc_id}: Delete a travel document
"""

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import APIResponse, AssetCreateRequest, AssetItem
from tripmate.services.document_service import document_service

router = APIRouter(prefix="/documents", tags=["Travel Documents"])
legacy_router = APIRouter(prefix="/assets", tags=["Travel Documents (Legacy Asset Alias)"])


async def _handle_list(
    request: Request,
    trip_id: Optional[str],
    current_user: Dict[str, Any],
) -> APIResponse[List[AssetItem]]:
    request_id = getattr(request.state, "request_id", "req_doc")
    assets = await asyncio.to_thread(document_service.list_assets, current_user["id"], trip_id=trip_id)
    return APIResponse(success=True, data=assets, error=None, request_id=request_id)


async def _handle_create(
    req: AssetCreateRequest,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[AssetItem]:
    request_id = getattr(request.state, "request_id", "req_doc")
    asset = await asyncio.to_thread(document_service.create_asset, current_user["id"], req)
    return APIResponse(success=True, data=asset, error=None, request_id=request_id)


async def _handle_get(
    doc_id: str,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[AssetItem]:
    request_id = getattr(request.state, "request_id", "req_doc")
    asset = await asyncio.to_thread(document_service.get_asset, doc_id, current_user["id"])
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ASSET_NOT_FOUND",
                "message": f"Asset ID '{doc_id}' not found.",
            },
        )
    return APIResponse(success=True, data=asset, error=None, request_id=request_id)


async def _handle_delete(
    doc_id: str,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[Dict[str, Any]]:
    request_id = getattr(request.state, "request_id", "req_doc")
    deleted = await asyncio.to_thread(document_service.delete_asset, doc_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ASSET_NOT_FOUND",
                "message": f"Asset ID '{doc_id}' not found.",
            },
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": doc_id},
        error=None,
        request_id=request_id,
    )


# Canonical /documents
@router.get("", summary="List Travel Documents", response_model=APIResponse[List[AssetItem]])
async def list_documents(
    request: Request,
    trip_id: Optional[str] = Query(None, description="Optional filter by associated trip ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_list(request, trip_id, current_user)


@router.post("", summary="Create / Attach Travel Document", response_model=APIResponse[AssetItem])
async def create_document(
    req: AssetCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@router.get(
    "/{doc_id}",
    summary="Get Travel Document Details",
    response_model=APIResponse[AssetItem],
)
async def get_document(
    doc_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_get(doc_id, request, current_user)


@router.delete(
    "/{doc_id}",
    summary="Delete Travel Document",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_document(
    doc_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(doc_id, request, current_user)


# Legacy /assets
@legacy_router.get("", summary="Legacy List Travel Assets", response_model=APIResponse[List[AssetItem]])
async def list_assets(
    request: Request,
    trip_id: Optional[str] = Query(None, description="Optional filter by associated trip ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_list(request, trip_id, current_user)


@legacy_router.post("", summary="Legacy Attach Travel Asset", response_model=APIResponse[AssetItem])
async def create_asset(
    req: AssetCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@legacy_router.get(
    "/{asset_id}",
    summary="Legacy Get Travel Asset Details",
    response_model=APIResponse[AssetItem],
)
async def get_asset(
    asset_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_get(asset_id, request, current_user)


@legacy_router.delete(
    "/{asset_id}",
    summary="Legacy Delete Travel Asset",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_asset(
    asset_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(asset_id, request, current_user)

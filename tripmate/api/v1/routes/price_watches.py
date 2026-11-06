"""
Travel Price Watches API Router

Endpoints:
- GET /api/v1/price-watches: List all watched travel targets
- POST /api/v1/price-watches: Add a destination, flight, or hotel to price watch
- GET /api/v1/price-watches/{item_id}: Retrieve specific price watch item
- DELETE /api/v1/price-watches/{item_id}: Remove item from price watch
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import APIResponse, WatchlistCreateRequest, WatchlistItem
from tripmate.services.price_watch_service import price_watch_service

router = APIRouter(prefix="/price-watches", tags=["Travel Price Watches"])
legacy_router = APIRouter(prefix="/watchlists", tags=["Travel Price Watches (Legacy Alias)"])


async def _handle_list(request: Request, current_user: Dict[str, Any]) -> APIResponse[List[WatchlistItem]]:
    request_id = getattr(request.state, "request_id", "req_pw")
    items = await asyncio.to_thread(price_watch_service.list_items, current_user["id"])
    return APIResponse(success=True, data=items, error=None, request_id=request_id)


async def _handle_create(
    req: WatchlistCreateRequest, request: Request, current_user: Dict[str, Any]
) -> APIResponse[WatchlistItem]:
    request_id = getattr(request.state, "request_id", "req_pw")
    item = await asyncio.to_thread(price_watch_service.add_item, current_user["id"], req)
    return APIResponse(success=True, data=item, error=None, request_id=request_id)


async def _handle_get(item_id: str, request: Request, current_user: Dict[str, Any]) -> APIResponse[WatchlistItem]:
    request_id = getattr(request.state, "request_id", "req_pw")
    item = await asyncio.to_thread(price_watch_service.get_item, item_id, current_user["id"])
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WATCHLIST_NOT_FOUND",
                "message": f"Watchlist ID '{item_id}' not found.",
            },
        )
    return APIResponse(success=True, data=item, error=None, request_id=request_id)


async def _handle_delete(item_id: str, request: Request, current_user: Dict[str, Any]) -> APIResponse[Dict[str, Any]]:
    request_id = getattr(request.state, "request_id", "req_pw")
    deleted = await asyncio.to_thread(price_watch_service.delete_item, item_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WATCHLIST_NOT_FOUND",
                "message": f"Watchlist ID '{item_id}' not found.",
            },
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": item_id},
        error=None,
        request_id=request_id,
    )


# Canonical /price-watches
@router.get("", summary="List Price Watches", response_model=APIResponse[List[WatchlistItem]])
async def list_price_watches(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    return await _handle_list(request, current_user)


@router.post("", summary="Create Price Watch", response_model=APIResponse[WatchlistItem])
async def create_price_watch(
    req: WatchlistCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@router.get(
    "/{item_id}",
    summary="Get Price Watch Details",
    response_model=APIResponse[WatchlistItem],
)
async def get_price_watch(
    item_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_get(item_id, request, current_user)


@router.delete(
    "/{item_id}",
    summary="Delete Price Watch",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_price_watch(
    item_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(item_id, request, current_user)


# Legacy /watchlists
@legacy_router.get(
    "",
    summary="Legacy List Watchlists",
    response_model=APIResponse[List[WatchlistItem]],
)
async def list_watchlists(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    return await _handle_list(request, current_user)


@legacy_router.post("", summary="Legacy Create Watchlist", response_model=APIResponse[WatchlistItem])
async def create_watchlist(
    req: WatchlistCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_create(req, request, current_user)


@legacy_router.get(
    "/{watchlist_id}",
    summary="Legacy Get Watchlist",
    response_model=APIResponse[WatchlistItem],
)
async def get_watchlist(
    watchlist_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_get(watchlist_id, request, current_user)


@legacy_router.delete(
    "/{watchlist_id}",
    summary="Legacy Delete Watchlist",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_watchlist(
    watchlist_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_delete(watchlist_id, request, current_user)

"""
Watchlists API Router

Endpoints:
- GET /api/v1/watchlists: List all watched travel targets
- POST /api/v1/watchlists: Add a destination, flight, or hotel to watchlist
- GET /api/v1/watchlists/{watchlist_id}: Retrieve specific watchlist item
- DELETE /api/v1/watchlists/{watchlist_id}: Remove item from watchlist
"""

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import APIResponse, WatchlistCreateRequest, WatchlistItem
from tripmate.services.watchlist_service import watchlist_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/watchlists", tags=["Travel Watchlists"])


@router.get(
    "",
    summary="List Watchlist Items",
    description="Returns all active travel watchlists for the authenticated user.",
    response_model=APIResponse[List[WatchlistItem]],
)
async def list_watchlists(request: Request, current_user: Dict[str, Any] = Depends(get_current_user)):
    request_id = getattr(request.state, "request_id", "req_wl")
    items = watchlist_service.list_items(current_user["id"])
    return APIResponse(
        success=True,
        data=items,
        error=None,
        request_id=request_id,
    )


@router.post(
    "",
    summary="Create Watchlist Item",
    description="Adds a destination, flight route, or hotel to user's price watchlist.",
    response_model=APIResponse[WatchlistItem],
)
async def create_watchlist(
    req: WatchlistCreateRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_wl")
    item = watchlist_service.add_item(current_user["id"], req)
    return APIResponse(
        success=True,
        data=item,
        error=None,
        request_id=request_id,
    )


@router.get(
    "/{watchlist_id}",
    summary="Get Watchlist Item Details",
    description="Retrieves price details and status for a specific watchlist entry.",
    response_model=APIResponse[WatchlistItem],
)
async def get_watchlist(
    watchlist_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_wl")
    item = watchlist_service.get_item(watchlist_id, current_user["id"])
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WATCHLIST_NOT_FOUND", "message": f"Watchlist ID '{watchlist_id}' not found."},
        )
    return APIResponse(
        success=True,
        data=item,
        error=None,
        request_id=request_id,
    )


@router.delete(
    "/{watchlist_id}",
    summary="Delete Watchlist Item",
    description="Removes a watchlist item from the user's account.",
    response_model=APIResponse[Dict[str, Any]],
)
async def delete_watchlist(
    watchlist_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_wl")
    deleted = watchlist_service.delete_item(watchlist_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WATCHLIST_NOT_FOUND", "message": f"Watchlist ID '{watchlist_id}' not found."},
        )
    return APIResponse(
        success=True,
        data={"deleted": True, "id": watchlist_id},
        error=None,
        request_id=request_id,
    )

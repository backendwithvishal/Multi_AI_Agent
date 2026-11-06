"""
Backward-compatibility alias module for tripmate.api.v1.routes.documents.
"""

from tripmate.api.v1.routes.documents import (
    create_asset,
    delete_asset,
    get_asset,
    legacy_router,
    list_assets,
)
from tripmate.api.v1.routes.documents import (
    legacy_router as router,
)

__all__ = [
    "router",
    "legacy_router",
    "list_assets",
    "create_asset",
    "get_asset",
    "delete_asset",
]

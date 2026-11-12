"""
Backward-compatibility alias module for tripmate.services.document_service.
"""

from tripmate.services.document_service import (
    AssetService,
    DocumentService,
    asset_service,
    document_service,
)

__all__ = [
    "DocumentService",
    "document_service",
    "AssetService",
    "asset_service",
]

"""
Backward-compatibility alias module for tripmate.api.v1.routes.budget.
"""

from tripmate.api.v1.routes.budget import (
    analyze_budget,
    calculate_finances,
    convert_currency,
    legacy_router,
)
from tripmate.api.v1.routes.budget import (
    legacy_router as router,
)

__all__ = [
    "router",
    "legacy_router",
    "calculate_finances",
    "convert_currency",
    "analyze_budget",
]

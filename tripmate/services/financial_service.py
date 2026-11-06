"""
Backward-compatibility alias module for tripmate.services.budget_service.
"""

from tripmate.services.budget_service import (
    EXCHANGE_RATES,
    BudgetService,
    FinancialService,
    budget_service,
    financial_service,
)

__all__ = [
    "BudgetService",
    "budget_service",
    "FinancialService",
    "financial_service",
    "EXCHANGE_RATES",
]

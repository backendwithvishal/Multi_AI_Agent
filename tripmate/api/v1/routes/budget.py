"""
Travel Budget & Cost Calculation API Router

Endpoints:
- POST /api/v1/budget/calculate: Calculates itemized trip finances, taxes, and buffers
- POST /api/v1/budget/convert: Deterministic multi-currency conversion
- POST /api/v1/budget/budget-analysis: Analyzes budget variance and utilization
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from tripmate.api.dependencies import get_current_user
from tripmate.schemas import (
    APIResponse,
    BudgetAnalysisRequest,
    BudgetAnalysisResponse,
    CurrencyConversionRequest,
    CurrencyConversionResponse,
    FinancialCalculationRequest,
    FinancialCalculationResponse,
)
from tripmate.services.budget_service import budget_service

router = APIRouter(prefix="/budget", tags=["Travel Budget & Calculations"])
legacy_router = APIRouter(prefix="/financial", tags=["Financial Engine & Calculations (Legacy Alias)"])


async def _handle_calculate(
    req: FinancialCalculationRequest,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[FinancialCalculationResponse]:
    request_id = getattr(request.state, "request_id", "req_budget")
    result = budget_service.calculate_trip_finances(req)
    return APIResponse(
        success=True,
        data=result,
        error=None,
        request_id=request_id,
    )


async def _handle_convert(
    req: CurrencyConversionRequest,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[CurrencyConversionResponse]:
    request_id = getattr(request.state, "request_id", "req_budget")
    try:
        result = budget_service.convert_currency(req)
        return APIResponse(
            success=True,
            data=result,
            error=None,
            request_id=request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNSUPPORTED_CURRENCY", "message": str(exc)},
        )


async def _handle_analyze(
    req: BudgetAnalysisRequest,
    request: Request,
    current_user: Dict[str, Any],
) -> APIResponse[BudgetAnalysisResponse]:
    request_id = getattr(request.state, "request_id", "req_budget")
    result = budget_service.analyze_budget_variance(req)
    return APIResponse(
        success=True,
        data=result,
        error=None,
        request_id=request_id,
    )


# Canonical endpoints
@router.post(
    "/calculate",
    summary="Deterministic Trip Cost Calculator",
    response_model=APIResponse[FinancialCalculationResponse],
)
async def calculate_finances(
    req: FinancialCalculationRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_calculate(req, request, current_user)


@router.post(
    "/convert",
    summary="Currency Converter",
    response_model=APIResponse[CurrencyConversionResponse],
)
async def convert_currency(
    req: CurrencyConversionRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_convert(req, request, current_user)


@router.post(
    "/budget-analysis",
    summary="Budget Variance & Feasibility Analysis",
    response_model=APIResponse[BudgetAnalysisResponse],
)
async def analyze_budget(
    req: BudgetAnalysisRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_analyze(req, request, current_user)


# Legacy endpoints (/financial/...)
@legacy_router.post(
    "/calculate",
    summary="Legacy Trip Cost Calculator",
    response_model=APIResponse[FinancialCalculationResponse],
)
async def legacy_calculate_finances(
    req: FinancialCalculationRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_calculate(req, request, current_user)


@legacy_router.post(
    "/convert",
    summary="Legacy Currency Converter",
    response_model=APIResponse[CurrencyConversionResponse],
)
async def legacy_convert_currency(
    req: CurrencyConversionRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_convert(req, request, current_user)


@legacy_router.post(
    "/budget-analysis",
    summary="Legacy Budget Analysis",
    response_model=APIResponse[BudgetAnalysisResponse],
)
async def legacy_analyze_budget(
    req: BudgetAnalysisRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    return await _handle_analyze(req, request, current_user)

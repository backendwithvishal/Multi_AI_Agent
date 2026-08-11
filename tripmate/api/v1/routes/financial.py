"""
Deterministic Financial Calculations API Router

Endpoints:
- POST /api/v1/financial/calculate: Calculates itemized trip finances, taxes, and buffers
- POST /api/v1/financial/convert: Deterministic multi-currency conversion
- POST /api/v1/financial/budget-analysis: Analyzes budget variance and utilization
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import (
    APIResponse,
    FinancialCalculationRequest,
    FinancialCalculationResponse,
    CurrencyConversionRequest,
    CurrencyConversionResponse,
    BudgetAnalysisRequest,
    BudgetAnalysisResponse,
)
from tripmate.services.financial_service import financial_service
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/financial", tags=["Financial Engine & Calculations"])


@router.post(
    "/calculate",
    summary="Deterministic Trip Cost Calculator",
    description="Calculates itemized subtotal, taxes/fees, contingency buffers, and daily spend averages.",
    response_model=APIResponse[FinancialCalculationResponse],
)
async def calculate_finances(
    req: FinancialCalculationRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_fin")
    result = financial_service.calculate_trip_finances(req)
    return APIResponse(
        success=True,
        data=result,
        error=None,
        request_id=request_id,
    )


@router.post(
    "/convert",
    summary="Currency Converter",
    description="Converts currency amounts between major global currencies using deterministic exchange matrices.",
    response_model=APIResponse[CurrencyConversionResponse],
)
async def convert_currency(
    req: CurrencyConversionRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_fin")
    try:
        result = financial_service.convert_currency(req)
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


@router.post(
    "/budget-analysis",
    summary="Budget Variance & Feasibility Analysis",
    description="Evaluates budget variance, spending thresholds, and budget utilization percentages.",
    response_model=APIResponse[BudgetAnalysisResponse],
)
async def analyze_budget(
    req: BudgetAnalysisRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_fin")
    result = financial_service.analyze_budget_variance(req)
    return APIResponse(
        success=True,
        data=result,
        error=None,
        request_id=request_id,
    )

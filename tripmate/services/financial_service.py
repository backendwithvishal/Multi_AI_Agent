"""
Deterministic Financial & Budget Calculation Service

Implements pure mathematical calculations for trip budgeting, currency conversion,
tax/fee modeling, and budget variance analysis without LLM hallucinations.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict
from tripmate.schemas import (
    FinancialCalculationRequest,
    FinancialCalculationResponse,
    CurrencyConversionRequest,
    CurrencyConversionResponse,
    BudgetAnalysisRequest,
    BudgetAnalysisResponse,
)

# Standard baseline exchange rates relative to USD (1 USD = X Currency)
EXCHANGE_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 155.40,
    "CAD": 1.36,
    "AUD": 1.52,
    "INR": 83.50,
    "SGD": 1.35,
    "CHF": 0.90,
}


def _round2(val: float | Decimal) -> float:
    d = Decimal(str(val))
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class FinancialService:
    """Deterministic financial computation engine."""

    def calculate_trip_finances(self, req: FinancialCalculationRequest) -> FinancialCalculationResponse:
        """Calculates itemized subtotal, taxes/fees, contingency buffer, and grand total."""
        hotel_total = req.hotel_nightly_rate * req.nights
        food_total = req.daily_food_allowance * req.nights
        flight_total = req.flight_estimate
        activities_total = req.activities_budget

        subtotal = hotel_total + food_total + flight_total + activities_total
        taxes_and_fees = subtotal * (req.tax_rate_pct / 100.0)
        contingency_buffer = subtotal * (req.contingency_buffer_pct / 100.0)
        grand_total = subtotal + taxes_and_fees + contingency_buffer
        daily_average = grand_total / max(1, req.nights)

        return FinancialCalculationResponse(
            subtotal=_round2(subtotal),
            hotel_total=_round2(hotel_total),
            food_total=_round2(food_total),
            flight_total=_round2(flight_total),
            activities_total=_round2(activities_total),
            taxes_and_fees=_round2(taxes_and_fees),
            contingency_buffer=_round2(contingency_buffer),
            grand_total=_round2(grand_total),
            currency=req.currency.upper(),
            daily_average=_round2(daily_average),
        )

    def convert_currency(self, req: CurrencyConversionRequest) -> CurrencyConversionResponse:
        """Converts currency using deterministic cross-currency rates."""
        from_curr = req.from_currency.upper()
        to_curr = req.to_currency.upper()

        if from_curr not in EXCHANGE_RATES:
            raise ValueError(f"Unsupported source currency '{from_curr}'. Available: {list(EXCHANGE_RATES.keys())}")
        if to_curr not in EXCHANGE_RATES:
            raise ValueError(f"Unsupported target currency '{to_curr}'. Available: {list(EXCHANGE_RATES.keys())}")

        # Convert to USD base first, then to target currency
        usd_amount = req.amount / EXCHANGE_RATES[from_curr]
        converted = usd_amount * EXCHANGE_RATES[to_curr]
        effective_rate = EXCHANGE_RATES[to_curr] / EXCHANGE_RATES[from_curr]

        return CurrencyConversionResponse(
            original_amount=_round2(req.amount),
            from_currency=from_curr,
            converted_amount=_round2(converted),
            to_currency=to_curr,
            exchange_rate=_round2(effective_rate),
        )

    def analyze_budget_variance(self, req: BudgetAnalysisRequest) -> BudgetAnalysisResponse:
        """Evaluates budget variance and utilization percentages."""
        target = req.target_budget
        estimated = req.estimated_total
        variance = target - estimated
        is_within = estimated <= target
        utilization = (estimated / target) * 100.0 if target > 0 else 0.0

        if is_within:
            advice = (
                f"Trip is within budget with a surplus of {_round2(variance)} {req.currency.upper()} "
                f"({_round2(100.0 - utilization)}% remaining buffer)."
            )
        else:
            advice = (
                f"Trip exceeds target budget by {_round2(abs(variance))} {req.currency.upper()} "
                f"({_round2(utilization - 100.0)}% over budget). Consider adjusting hotel or flight tiers."
            )

        return BudgetAnalysisResponse(
            target_budget=_round2(target),
            estimated_total=_round2(estimated),
            currency=req.currency.upper(),
            variance=_round2(variance),
            is_within_budget=is_within,
            utilization_pct=_round2(utilization),
            financial_advice=advice,
        )


financial_service = FinancialService()

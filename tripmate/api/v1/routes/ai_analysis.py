"""
AI Travel Analysis & Evaluation API Router

Endpoint:
- POST /api/v1/ai/analysis: Evaluates feasibility, budget constraints, risk factors, and critic score
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, Request
from tripmate.schemas import APIResponse, AIAnalysisRequest, AIAnalysisResponse
from tripmate.agents.planner import planner
from tripmate.agents.critic import critic_agent
from tripmate.agents.guardrail import deterministic_input_check
from tripmate.services.model_router import model_router, ModelTier
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/ai", tags=["AI Analysis & Intelligence"])


@router.post(
    "/analysis",
    summary="AI Travel Plan Analysis & Validation",
    description="Analyzes a travel request or itinerary for feasibility, risk factors, budget alignment, and quality scoring.",
    response_model=APIResponse[AIAnalysisResponse],
)
async def analyze_travel_request(
    req: AIAnalysisRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ai_analysis")
    
    # Check guardrails first
    is_safe, reason = deterministic_input_check(req.query)
    if not is_safe:
        return APIResponse(
            success=True,
            data=AIAnalysisResponse(
                is_feasible=False,
                quality_score=0.0,
                destination=req.destination or "Unknown",
                risk_factors=[f"Safety/Guardrail Violation: {reason}"],
                recommendations=["Please submit a valid travel planning request."],
                suggested_agents=[],
            ),
            error=None,
            request_id=request_id,
        )

    reasoning_llm = model_router.get_model(ModelTier.REASONING)
    
    # 1. Generate Task DAG plan to extract constraints and dependencies
    plan_dag = await planner.create_plan(reasoning_llm, req.query)
    extracted_dest = req.destination or plan_dag.trip_constraints.get("destination") or "Destination"
    suggested_agents = [task.agent for task in plan_dag.tasks]

    # 2. Run Critic validation on candidate itinerary or prompt
    critic_report = await critic_agent.evaluate_plan(
        llm=reasoning_llm,
        user_query=req.query,
        constraints=plan_dag.trip_constraints,
        agent_outputs={"plan_dag": plan_dag.model_dump()},
        draft_itinerary=req.itinerary or "Standard draft itinerary for analysis",
    )

    risk_factors = list(critic_report.violations)
    if req.budget and req.budget < 500:
        risk_factors.append("Low budget threshold may limit accommodation and direct flight availability.")

    recommendations = list(critic_report.recommendations)
    if not recommendations:
        recommendations.append("Plan structure is balanced. Proceed with flight and hotel reservation steps.")

    analysis_result = AIAnalysisResponse(
        is_feasible=critic_report.is_valid,
        quality_score=critic_report.score,
        destination=extracted_dest,
        estimated_budget=req.budget,
        risk_factors=risk_factors,
        recommendations=recommendations,
        suggested_agents=suggested_agents,
        critic_evaluation=critic_report.model_dump(),
    )

    return APIResponse(
        success=True,
        data=analysis_result,
        error=None,
        request_id=request_id,
    )

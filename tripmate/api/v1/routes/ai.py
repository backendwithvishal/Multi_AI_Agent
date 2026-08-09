"""
AI Agent Management & Planning API Router

Endpoints:
- POST /api/v1/ai/plan: Decomposes a travel request into a dependency-aware Task DAG
- POST /api/v1/ai/agents/{agent_name}/invoke: Directly invokes a registered specialist agent
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, status
from tripmate.schemas import APIResponse, AIPlanRequest, AIAgentInvokeRequest
from tripmate.agents.planner import planner
from tripmate.agents.registry import agent_registry
from tripmate.services.model_router import model_router, ModelTier
from tripmate.api.dependencies import get_current_user

router = APIRouter(prefix="/ai", tags=["AI Orchestration & Agents"])


@router.post(
    "/plan",
    summary="Generate Dynamic Task DAG Plan",
    description="Decomposes a user query into parallel tasks, agent assignments, and dependencies.",
    response_model=APIResponse[Dict[str, Any]],
)
async def generate_plan(
    req: AIPlanRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ai_plan")
    reasoning_llm = model_router.get_model(ModelTier.REASONING)
    plan_dag = await planner.create_plan(reasoning_llm, req.query)
    return APIResponse(
        success=True,
        data=plan_dag.model_dump(),
        error=None,
        request_id=request_id,
    )


@router.post(
    "/agents/{agent_name}/invoke",
    summary="Direct Agent Invocation",
    description="Directly invokes a registered specialist agent with custom query and context.",
    response_model=APIResponse[Dict[str, Any]],
)
async def invoke_agent(
    agent_name: str,
    req: AIAgentInvokeRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    request_id = getattr(request.state, "request_id", "req_ai_agent")
    agent = agent_registry.get(agent_name)
    if not agent:
        available = [a.name for a in agent_registry.list_agents()]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "AGENT_NOT_FOUND",
                "message": f"Agent '{agent_name}' not registered. Available: {available}",
            },
        )

    reasoning_llm = model_router.get_model(ModelTier.REASONING)
    output = await agent.run(reasoning_llm, req.query, context=req.context)
    return APIResponse(
        success=True,
        data=output.model_dump(),
        error=None,
        request_id=request_id,
    )

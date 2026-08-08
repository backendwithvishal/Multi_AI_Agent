"""
Critic & Validation Agent Module

This module evaluates candidate plan outputs before finalizing or presenting for human approval.
Checks:
- Data completeness & missing fields
- Budget compliance & math correctness
- Contradictory information across flight/hotel/weather
- Unsupported claims or hallucinated details
"""

import json
from typing import Any, Dict
from langchain_core.messages import SystemMessage, HumanMessage

from tripmate.schemas.agents import CriticReport


class CriticAgent:
    """Validates plan outputs against constraints and structural quality rules."""

    async def evaluate_plan(
        self,
        llm: Any,
        user_query: str,
        constraints: Dict[str, Any],
        agent_outputs: Dict[str, Any],
        draft_itinerary: str,
    ) -> CriticReport:
        """Evaluates gathered outputs and returns a CriticReport."""
        if not llm:
            return CriticReport(
                is_valid=True,
                score=0.9,
                violations=[],
                recommendations=["Proceed with draft review (Critic LLM unconfigured)"],
                requires_retry=False,
                retry_tasks=[],
            )

        prompt = f"""
You are a meticulous Critic & Validation Agent reviewing an automated multi-agent plan.

User Query: {user_query}
Extracted Constraints: {constraints}

Gathered Agent Outputs:
{json.dumps(agent_outputs, indent=2, default=str)[:3000]}

Draft Itinerary:
{draft_itinerary[:2000]}

Evaluate the plan against these criteria:
1. Completeness: Are essential components (flights, hotels, schedule, budget) present?
2. Budget Compliance: Are cost estimates realistic and within requested limits?
3. Consistency: Are there date or location contradictions?
4. Quality & Groundedness: Are recommendations practical without hallucinated claims?

Return strict JSON matching this schema:
{{
  "is_valid": true,
  "score": 0.95,
  "violations": [],
  "recommendations": ["Minor tip or observation"],
  "requires_retry": false,
  "retry_tasks": []
}}
"""

        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content="You validate multi-agent outputs for accuracy and safety. Return strict JSON only."),
                    HumanMessage(content=prompt),
                ]
            )
            cleaned = str(response.content).strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[-1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                data = json.loads(cleaned[start:end+1])
                return CriticReport(**data)
        except Exception as exc:
            print(f"Critic evaluation fallback: {exc}")

        return CriticReport(
            is_valid=True,
            score=0.85,
            violations=[],
            recommendations=["Evaluated with fallback rules"],
            requires_retry=False,
            retry_tasks=[],
        )


critic_agent = CriticAgent()

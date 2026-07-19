"""
Ledgerline Routing & Optimization Service
Handles intelligent routing, A/B testing, and CRISPE prompt engineering
"""
import logging
import os
import random
from typing import Optional, List, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROUTING_DECISIONS = Counter(
    'ledgerline_routing_decisions_total',
    'Total routing decisions',
    ['strategy', 'provider', 'model']
)

ROUTING_LATENCY = Histogram(
    'ledgerline_routing_latency_seconds',
    'Routing decision latency'
)

class RoutingRequest(BaseModel):
    tenant_id: str
    use_case: str
    messages: List[Dict]
    max_tokens: int = 2048
    temperature: float = 0.7
    ab_test_id: Optional[str] = None

class CRISPEPrompt(BaseModel):
    """CRISPE Framework: Context, Role, Instruction, Specifics, Personality, Experiment"""
    context: str
    role: str
    instruction: str
    specifics: List[str]
    personality: str
    experiment: Optional[str] = None

app = FastAPI(
    title="Ledgerline Routing Service",
    description="Intelligent routing and prompt optimization",
    version="1.0.0"
)

# Routing strategies
ROUTING_STRATEGIES = {
    "cost_optimized": {
        "primary": {"provider": "anthropic", "model": "claude-3-haiku"},
        "fallback": {"provider": "openai", "model": "gpt-3.5-turbo"}
    },
    "quality_optimized": {
        "primary": {"provider": "openai", "model": "gpt-4"},
        "fallback": {"provider": "anthropic", "model": "claude-3-opus"}
    },
    "balanced": {
        "primary": {"provider": "openai", "model": "gpt-4-turbo"},
        "fallback": {"provider": "anthropic", "model": "claude-3-sonnet"}
    }
}

def apply_crispe_template(prompt: CRISPEPrompt) -> str:
    """Transform user prompt using CRISPE framework"""
    enhanced_prompt = f"""Context: {prompt.context}

Role: You are {prompt.role}

Instruction: {prompt.instruction}

Specifics:
{chr(10).join(f"- {s}" for s in prompt.specifics)}

Personality: {prompt.personality}
"""
    
    if prompt.experiment:
        enhanced_prompt += f"\nExperiment: {prompt.experiment}"
    
    return enhanced_prompt

@app.post("/v1/route")
def route_request(request: RoutingRequest):
    """
    Determine optimal provider and model for request
    Supports A/B testing and cost/quality optimization
    """
    try:
        # Default strategy
        strategy = "balanced"
        
        # A/B testing override
        if request.ab_test_id:
            # In production, look up A/B test configuration
            # For now, randomize for demo
            if random.random() < 0.5:
                strategy = "cost_optimized"
            else:
                strategy = "quality_optimized"
        
        # Get routing decision
        route = ROUTING_STRATEGIES[strategy]["primary"]
        
        ROUTING_DECISIONS.labels(
            strategy=strategy,
            provider=route["provider"],
            model=route["model"]
        ).inc()
        
        logger.info(f"Routed to {route['provider']}/{route['model']} using {strategy} strategy")
        
        return {
            "provider": route["provider"],
            "model": route["model"],
            "strategy": strategy,
            "fallback_provider": ROUTING_STRATEGIES[strategy]["fallback"]["provider"],
            "fallback_model": ROUTING_STRATEGIES[strategy]["fallback"]["model"]
        }
        
    except Exception as e:
        logger.error(f"Routing failed: {e}")
        raise HTTPException(status_code=500, detail="Routing failed")

@app.post("/v1/optimize-prompt")
def optimize_prompt(crispe: CRISPEPrompt):
    """Apply CRISPE framework to enhance prompts"""
    try:
        enhanced = apply_crispe_template(crispe)
        
        return {
            "original_length": len(crispe.instruction),
            "enhanced_length": len(enhanced),
            "enhanced_prompt": enhanced,
            "framework": "CRISPE"
        }
    except Exception as e:
        logger.error(f"Prompt optimization failed: {e}")
        raise HTTPException(status_code=500, detail="Optimization failed")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "routing"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8087"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

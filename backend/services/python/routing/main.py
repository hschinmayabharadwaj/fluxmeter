"""
Ledgerline Routing & Optimization Service
Handles intelligent routing, A/B testing, and CRISPE prompt engineering
CRISPE Framework: Capacity, Role, Insight, Statement, Personality, Experiment
"""
import logging
import os
import random
import re
import hashlib
import psycopg2
import psycopg2.extras
from typing import Optional, List, Dict
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field, validator
from prometheus_client import Counter, Histogram, Gauge, generate_latest
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

CRISPE_VALIDATIONS = Counter(
    'ledgerline_crispe_validations_total',
    'CRISPE prompt validations',
    ['status']
)

CRISPE_USAGE = Counter(
    'ledgerline_crispe_template_usage_total',
    'CRISPE template usage',
    ['template_name', 'version']
)

ACTIVE_CRISPE_TEMPLATES = Gauge(
    'ledgerline_active_crispe_templates',
    'Number of active CRISPE templates by tenant',
    ['tenant_id']
)

class RoutingRequest(BaseModel):
    tenant_id: str
    use_case: str
    messages: List[Dict]
    max_tokens: int = 2048
    temperature: float = 0.7
    ab_test_id: Optional[str] = None

class CRISPEPrompt(BaseModel):
    """CRISPE Framework: Capacity, Role, Insight, Statement, Personality, Experiment"""
    capacity: str = Field(..., min_length=10, max_length=5000, 
                         description="Task capacity and context")
    role: str = Field(..., min_length=5, max_length=500,
                     description="AI role definition")
    insight: str = Field(..., min_length=10, max_length=2000,
                        description="Key insight or background knowledge")
    statement: str = Field(..., min_length=10, max_length=5000,
                          description="Core instruction or task statement")
    personality: str = Field(..., min_length=5, max_length=500,
                            description="Tone, style, and personality")
    experiment: Optional[str] = Field(None, max_length=1000,
                                     description="Optional experimental instructions")
    
    @validator('capacity')
    def validate_capacity(cls, v):
        if len(v.split()) < 5:
            raise ValueError("Capacity must contain at least 5 words")
        return v
    
    @validator('role')
    def validate_role(cls, v):
        # Role should start with "You are" or similar
        if not re.match(r'^(You are|Act as|Behave as|Function as)', v, re.IGNORECASE):
            raise ValueError("Role should start with 'You are', 'Act as', etc.")
        return v
    
    @validator('statement')
    def validate_statement(cls, v):
        # Statement should contain actionable instructions
        action_words = ['create', 'generate', 'analyze', 'provide', 'explain', 
                       'summarize', 'evaluate', 'compare', 'list', 'describe']
        if not any(word in v.lower() for word in action_words):
            raise ValueError("Statement must contain clear action words")
        return v

class CRISPETemplateCreate(BaseModel):
    tenant_id: str
    template_name: str = Field(..., min_length=3, max_length=255)
    crispe: CRISPEPrompt
    created_by: Optional[str] = None

class CRISPETemplateUse(BaseModel):
    tenant_id: str
    template_name: str
    version: Optional[int] = None  # If None, use latest active version
    variables: Optional[Dict[str, str]] = {}  # Variable substitution

app = FastAPI(
    title="Ledgerline Routing Service",
    description="Intelligent routing and prompt optimization with CRISPE framework",
    version="2.0.0"
)

def get_db():
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL", "postgres://ledgerline:ledgerline@localhost:5432/ledgerline")
    )
    try:
        yield conn
    finally:
        conn.close()

def validate_crispe_quality(crispe: CRISPEPrompt) -> tuple[float, List[str]]:
    """
    Validate CRISPE prompt quality and return score (0-1) and issues
    """
    score = 1.0
    issues = []
    
    # Check capacity depth
    capacity_words = len(crispe.capacity.split())
    if capacity_words < 20:
        score -= 0.1
        issues.append("Capacity should be more detailed (>20 words)")
    
    # Check role clarity
    if "expert" not in crispe.role.lower() and "specialist" not in crispe.role.lower():
        score -= 0.05
        issues.append("Consider specifying expertise level in role")
    
    # Check insight specificity
    if len(crispe.insight.split()) < 15:
        score -= 0.1
        issues.append("Insight could be more specific")
    
    # Check statement clarity
    if crispe.statement.count('.') < 2:
        score -= 0.1
        issues.append("Statement should have multiple clear instructions")
    
    # Check personality definition
    if len(crispe.personality.split()) < 5:
        score -= 0.1
        issues.append("Personality should be more defined")
    
    # Bonus for experiment
    if crispe.experiment and len(crispe.experiment) > 20:
        score += 0.05
    
    return max(0.0, min(1.0, score)), issues

def apply_crispe_template(crispe: CRISPEPrompt, variables: Optional[Dict[str, str]] = None) -> str:
    """Transform components into final prompt using CRISPE framework"""
    
    # Apply variable substitution if provided
    capacity = crispe.capacity
    role = crispe.role
    insight = crispe.insight
    statement = crispe.statement
    personality = crispe.personality
    experiment = crispe.experiment
    
    if variables:
        for key, value in variables.items():
            capacity = capacity.replace(f"{{{key}}}", value)
            role = role.replace(f"{{{key}}}", value)
            insight = insight.replace(f"{{{key}}}", value)
            statement = statement.replace(f"{{{key}}}", value)
            personality = personality.replace(f"{{{key}}}", value)
            if experiment:
                experiment = experiment.replace(f"{{{key}}}", value)
    
    enhanced_prompt = f"""CAPACITY: {capacity}

ROLE: {role}

INSIGHT: {insight}

STATEMENT: {statement}

PERSONALITY: {personality}"""
    
    if experiment:
        enhanced_prompt += f"\n\nEXPERIMENT: {experiment}"
    
    return enhanced_prompt

@app.post("/v1/route")
def route_request(request: RoutingRequest, db = Depends(get_db)):
    """
    Determine optimal provider and model for request
    Supports A/B testing with sibling attempt tracking
    """
    try:
        cursor = db.cursor()
        
        # Default strategy
        strategy = "balanced"
        variant_assigned = None
        
        # A/B testing: get or assign consistent variant for sibling attempts
        if request.ab_test_id:
            # Check if this A/B test has a variant assigned for this tenant
            cursor.execute("""
                SELECT variant_assigned, attempt_count
                FROM ab_tests
                WHERE ab_test_id = %s AND tenant_id = %s
                FOR UPDATE  -- Lock row to prevent race conditions
            """, (request.ab_test_id, request.tenant_id))
            
            result = cursor.fetchone()
            
            if result:
                # Existing A/B test: use assigned variant for consistency
                variant_assigned, attempt_count = result
                strategy = variant_assigned
                
                # Increment sibling attempt count
                cursor.execute("""
                    UPDATE ab_tests
                    SET attempt_count = attempt_count + 1,
                        last_attempt_at = CURRENT_TIMESTAMP
                    WHERE ab_test_id = %s AND tenant_id = %s
                """, (request.ab_test_id, request.tenant_id))
                
                logger.info(f"A/B Test {request.ab_test_id}: sibling attempt #{attempt_count + 1} using {strategy}")
            else:
                # New A/B test: assign variant and track it
                # Deterministic: hash to ensure same AB test ID always gets same variant
                test_hash = hashlib.md5(f"{request.ab_test_id}:{request.tenant_id}".encode()).hexdigest()
                variant_seed = int(test_hash, 16)
                
                # Ensure consistent variant assignment (never changes)
                if variant_seed % 2 == 0:
                    strategy = "cost_optimized"
                else:
                    strategy = "quality_optimized"
                
                variant_assigned = strategy
                
                # Insert new A/B test tracking record
                cursor.execute("""
                    INSERT INTO ab_tests (
                        ab_test_id, tenant_id, variant_assigned,
                        attempt_count, created_at, last_attempt_at
                    ) VALUES (%s, %s, %s, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (ab_test_id, tenant_id) DO NOTHING
                """, (request.ab_test_id, request.tenant_id, strategy))
                
                logger.info(f"A/B Test {request.ab_test_id}: new test assigned variant {strategy}")
        
        db.commit()
        
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
            "ab_test_id": request.ab_test_id,
            "variant_assigned": variant_assigned,
            "fallback_provider": ROUTING_STRATEGIES[strategy]["fallback"]["provider"],
            "fallback_model": ROUTING_STRATEGIES[strategy]["fallback"]["model"]
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Routing failed: {e}")
        raise HTTPException(status_code=500, detail="Routing failed")

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

@app.post("/v1/crispe/template")
def create_crispe_template(template: CRISPETemplateCreate, db = Depends(get_db)):
    """Create a new CRISPE prompt template with validation"""
    try:
        cursor = db.cursor()
        
        # Validate CRISPE quality
        quality_score, issues = validate_crispe_quality(template.crispe)
        
        if quality_score < 0.5:
            CRISPE_VALIDATIONS.labels(status='rejected').inc()
            raise HTTPException(
                status_code=400, 
                detail=f"CRISPE quality too low ({quality_score:.2f}). Issues: {', '.join(issues)}"
            )
        
        # Get next version number
        cursor.execute("""
            SELECT COALESCE(MAX(version), 0) + 1
            FROM crispe_prompts
            WHERE tenant_id = %s AND template_name = %s
        """, (template.tenant_id, template.template_name))
        
        next_version = cursor.fetchone()[0]
        
        # Insert new template
        cursor.execute("""
            INSERT INTO crispe_prompts (
                tenant_id, template_name, version,
                capacity, role, insight, statement, personality, experiment,
                validation_score, created_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING prompt_id, created_at
        """, (
            template.tenant_id, template.template_name, next_version,
            template.crispe.capacity, template.crispe.role, template.crispe.insight,
            template.crispe.statement, template.crispe.personality, template.crispe.experiment,
            quality_score, template.created_by
        ))
        
        result = cursor.fetchone()
        db.commit()
        
        CRISPE_VALIDATIONS.labels(status='accepted').inc()
        ACTIVE_CRISPE_TEMPLATES.labels(tenant_id=template.tenant_id).inc()
        
        logger.info(f"CRISPE template created: {template.template_name} v{next_version} (score: {quality_score:.2f})")
        
        return {
            "prompt_id": str(result[0]),
            "template_name": template.template_name,
            "version": next_version,
            "validation_score": round(quality_score, 2),
            "issues": issues if issues else [],
            "created_at": result[1].isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create CRISPE template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/crispe/apply")
def apply_crispe(use_request: CRISPETemplateUse, db = Depends(get_db)):
    """Apply a CRISPE template with optional variable substitution"""
    try:
        cursor = db.cursor()
        
        # Get template
        if use_request.version:
            cursor.execute("""
                SELECT prompt_id, capacity, role, insight, statement, personality, experiment, version
                FROM crispe_prompts
                WHERE tenant_id = %s AND template_name = %s AND version = %s
            """, (use_request.tenant_id, use_request.template_name, use_request.version))
        else:
            # Get latest active version
            cursor.execute("""
                SELECT prompt_id, capacity, role, insight, statement, personality, experiment, version
                FROM crispe_prompts
                WHERE tenant_id = %s AND template_name = %s AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """, (use_request.tenant_id, use_request.template_name))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="CRISPE template not found")
        
        prompt_id, capacity, role, insight, statement, personality, experiment, version = result
        
        # Construct CRISPE object
        crispe = CRISPEPrompt(
            capacity=capacity,
            role=role,
            insight=insight,
            statement=statement,
            personality=personality,
            experiment=experiment
        )
        
        # Apply template with variables
        enhanced_prompt = apply_crispe_template(crispe, use_request.variables)
        
        # Update usage metrics
        cursor.execute("""
            UPDATE crispe_prompts
            SET usage_count = usage_count + 1
            WHERE prompt_id = %s
        """, (prompt_id,))
        
        db.commit()
        
        CRISPE_USAGE.labels(
            template_name=use_request.template_name,
            version=str(version)
        ).inc()
        
        return {
            "template_name": use_request.template_name,
            "version": version,
            "enhanced_prompt": enhanced_prompt,
            "original_length": len(statement),
            "enhanced_length": len(enhanced_prompt),
            "expansion_ratio": round(len(enhanced_prompt) / len(statement), 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply CRISPE template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/crispe/templates/{tenant_id}")
def list_crispe_templates(tenant_id: str, active_only: bool = True, db = Depends(get_db)):
    """List all CRISPE templates for a tenant"""
    try:
        cursor = db.cursor()
        
        if active_only:
            cursor.execute("""
                SELECT template_name, version, validation_score, usage_count,
                       avg_response_time_ms, avg_token_count, success_rate,
                       created_by, created_at
                FROM crispe_prompts
                WHERE tenant_id = %s AND is_active = true
                ORDER BY template_name, version DESC
            """, (tenant_id,))
        else:
            cursor.execute("""
                SELECT template_name, version, validation_score, usage_count,
                       avg_response_time_ms, avg_token_count, success_rate,
                       is_active, created_by, created_at
                FROM crispe_prompts
                WHERE tenant_id = %s
                ORDER BY template_name, version DESC
            """, (tenant_id,))
        
        templates = []
        for row in cursor.fetchall():
            template_data = {
                "template_name": row[0],
                "version": row[1],
                "validation_score": float(row[2]) if row[2] else None,
                "usage_count": row[3],
                "avg_response_time_ms": row[4],
                "avg_token_count": row[5],
                "success_rate": float(row[6]) if row[6] else None,
                "created_by": row[7] if active_only else row[8],
                "created_at": (row[8] if active_only else row[9]).isoformat()
            }
            if not active_only:
                template_data["is_active"] = row[7]
            templates.append(template_data)
        
        return {
            "tenant_id": tenant_id,
            "templates": templates,
            "total_count": len(templates)
        }
        
    except Exception as e:
        logger.error(f"Failed to list CRISPE templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/crispe/template/{tenant_id}/{template_name}/{version}")
def get_crispe_template(tenant_id: str, template_name: str, version: int, db = Depends(get_db)):
    """Get full CRISPE template details"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT capacity, role, insight, statement, personality, experiment,
                   validation_score, usage_count, is_active, created_by, created_at
            FROM crispe_prompts
            WHERE tenant_id = %s AND template_name = %s AND version = %s
        """, (tenant_id, template_name, version))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return {
            "tenant_id": tenant_id,
            "template_name": template_name,
            "version": version,
            "crispe": {
                "capacity": result[0],
                "role": result[1],
                "insight": result[2],
                "statement": result[3],
                "personality": result[4],
                "experiment": result[5]
            },
            "validation_score": float(result[6]) if result[6] else None,
            "usage_count": result[7],
            "is_active": result[8],
            "created_by": result[9],
            "created_at": result[10].isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get CRISPE template: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

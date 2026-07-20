"""
Ledgerline EEOC Compliance Module
Handles bias monitoring and adverse impact analysis (4/5ths rule)
Includes automated bias testing framework and explainability tracking
"""
import logging
import os
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from collections import defaultdict

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from prometheus_client import Counter, Gauge, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EEOC_OPERATIONS = Counter(
    'ledgerline_eeoc_operations_total',
    'Total EEOC compliance operations',
    ['operation', 'status']
)

BIAS_VIOLATIONS = Gauge(
    'ledgerline_bias_violations_active',
    'Active bias violations by tenant and model',
    ['tenant_id', 'model', 'protected_group']
)

ADVERSE_IMPACT_RATIO = Gauge(
    'ledgerline_adverse_impact_ratio',
    'Current adverse impact ratio by model',
    ['model', 'protected_group']
)

class ScreeningDecision(BaseModel):
    """Record of an AI screening decision with explainability"""
    tenant_id: str
    correlation_id: Optional[str] = None
    candidate_id: str
    job_id: str
    decision: str = Field(..., regex="^(selected|rejected|waitlist)$")
    confidence_score: float = Field(..., ge=0, le=1)
    decision_factors: Dict[str, float]  # e.g., {"skills_match": 0.85, "experience": 0.72}
    top_reasons: List[str]
    model: str
    provider: str
    protected_attributes: Optional[Dict[str, str]] = None  # For bias testing only

class BiasTestCreate(BaseModel):
    tenant_id: str
    test_date: date
    model: str
    job_id: Optional[str] = None
    protected_group: str
    selection_rate_protected: float = Field(..., ge=0, le=1)
    selection_rate_comparison: float = Field(..., ge=0, le=1)
    sample_size: int = Field(..., gt=0)
    # New fields for detailed tracking
    protected_selected: int = Field(..., ge=0)
    protected_total: int = Field(..., gt=0)
    comparison_selected: int = Field(..., ge=0)
    comparison_total: int = Field(..., gt=0)

class AutomatedBiasTestRequest(BaseModel):
    """Request automated bias testing for a job"""
    tenant_id: str
    job_id: str
    model: str
    protected_groups: List[str] = ["gender", "age_range", "ethnicity"]

app = FastAPI(
    title="Ledgerline EEOC Compliance",
    description="EEOC bias monitoring and adverse impact analysis",
    version="1.0.0"
)

def get_db():
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL", "postgres://ledgerline:ledgerline@localhost:5432/ledgerline")
    )
    try:
        yield conn
    finally:
        conn.close()

def calculate_adverse_impact(protected_rate: float, comparison_rate: float) -> tuple:
    """Calculate adverse impact ratio (4/5ths rule = 0.8)"""
    if comparison_rate == 0:
        return 0.0, False
    
    ratio = protected_rate / comparison_rate
    passes = ratio >= 0.8
    return ratio, passes

@app.post("/v1/screening-decision")
def record_screening_decision(decision: ScreeningDecision, db = Depends(get_db)):
    """Record an AI screening decision with explainability data"""
    try:
        cursor = db.cursor()
        
        # Validate decision factors
        if not decision.decision_factors or len(decision.decision_factors) == 0:
            raise HTTPException(status_code=400, detail="decision_factors required for EEOC compliance")
        
        # Validate top reasons
        if not decision.top_reasons or len(decision.top_reasons) == 0:
            raise HTTPException(status_code=400, detail="top_reasons required for explainability")
        
        cursor.execute("""
            INSERT INTO ai_screening_decisions (
                tenant_id, correlation_id, candidate_id, job_id,
                decision, confidence_score, decision_factors, top_reasons,
                model, provider, protected_attributes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING decision_id, created_at
        """, (
            decision.tenant_id, decision.correlation_id, decision.candidate_id, decision.job_id,
            decision.decision, decision.confidence_score, psycopg2.extras.Json(decision.decision_factors),
            decision.top_reasons, decision.model, decision.provider,
            psycopg2.extras.Json(decision.protected_attributes) if decision.protected_attributes else None
        ))
        
        result = cursor.fetchone()
        db.commit()
        EEOC_OPERATIONS.labels(operation='screening_decision', status='success').inc()
        
        logger.info(f"Screening decision recorded: {decision.candidate_id} / {decision.job_id} - {decision.decision}")
        
        return {
            "decision_id": str(result[0]),
            "candidate_id": decision.candidate_id,
            "job_id": decision.job_id,
            "decision": decision.decision,
            "created_at": result[1].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record screening decision: {e}")
        EEOC_OPERATIONS.labels(operation='screening_decision', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/bias-test")
def create_bias_test(test: BiasTestCreate, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        
        # Calculate adverse impact ratio
        ratio, passes = calculate_adverse_impact(
            test.selection_rate_protected,
            test.selection_rate_comparison
        )
        
        cursor.execute("""
            INSERT INTO bias_monitoring (
                tenant_id, test_date, model, job_id, protected_group,
                selection_rate_protected, selection_rate_comparison,
                adverse_impact_ratio, passes_compliance,
                sample_size, flagged_for_review,
                protected_selected, protected_total,
                comparison_selected, comparison_total
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            test.tenant_id, test.test_date, test.model, test.job_id, test.protected_group,
            test.selection_rate_protected, test.selection_rate_comparison,
            ratio, passes, test.sample_size, not passes,
            test.protected_selected, test.protected_total,
            test.comparison_selected, test.comparison_total
        ))
        
        result = cursor.fetchone()
        db.commit()
        EEOC_OPERATIONS.labels(operation='bias_test_create', status='success').inc()
        
        # Update Prometheus metrics
        if not passes:
            BIAS_VIOLATIONS.labels(
                tenant_id=test.tenant_id,
                model=test.model,
                protected_group=test.protected_group
            ).inc()
        
        ADVERSE_IMPACT_RATIO.labels(
            model=test.model,
            protected_group=test.protected_group
        ).set(ratio)
        
        logger.info(f"Bias test recorded: {test.model} / {test.protected_group} - Ratio: {ratio:.3f} (Passes: {passes})")
        
        return {
            "test_id": str(result[0]),
            "adverse_impact_ratio": round(ratio, 4),
            "passes_compliance": passes,
            "flagged_for_review": not passes,
            "created_at": result[1].isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create bias test: {e}")
        EEOC_OPERATIONS.labels(operation='bias_test_create', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/automated-bias-test")
async def run_automated_bias_test(
    request: AutomatedBiasTestRequest, 
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Automatically analyze screening decisions for adverse impact
    Runs in background and flags violations
    """
    try:
        cursor = db.cursor()
        
        # Get all screening decisions for this job
        cursor.execute("""
            SELECT decision, protected_attributes
            FROM ai_screening_decisions
            WHERE tenant_id = %s AND job_id = %s AND model = %s
              AND protected_attributes IS NOT NULL
        """, (request.tenant_id, request.job_id, request.model))
        
        decisions = cursor.fetchall()
        
        if len(decisions) < 30:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient sample size ({len(decisions)} < 30 required for statistical validity)"
            )
        
        # Calculate selection rates by protected group
        results = []
        for protected_group in request.protected_groups:
            stats = calculate_group_statistics(decisions, protected_group)
            
            if stats["protected_total"] == 0 or stats["comparison_total"] == 0:
                logger.warning(f"Skipping {protected_group}: insufficient data")
                continue
            
            # Calculate selection rates
            protected_rate = stats["protected_selected"] / stats["protected_total"]
            comparison_rate = stats["comparison_selected"] / stats["comparison_total"]
            
            # Calculate adverse impact
            ratio, passes = calculate_adverse_impact(protected_rate, comparison_rate)
            
            # Store bias test result
            cursor.execute("""
                INSERT INTO bias_monitoring (
                    tenant_id, test_date, model, job_id, protected_group,
                    selection_rate_protected, selection_rate_comparison,
                    adverse_impact_ratio, passes_compliance,
                    sample_size, flagged_for_review,
                    protected_selected, protected_total,
                    comparison_selected, comparison_total
                ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                request.tenant_id, request.model, request.job_id, protected_group,
                protected_rate, comparison_rate, ratio, passes, len(decisions), not passes,
                stats["protected_selected"], stats["protected_total"],
                stats["comparison_selected"], stats["comparison_total"]
            ))
            
            test_id = cursor.fetchone()[0]
            
            results.append({
                "test_id": str(test_id),
                "protected_group": protected_group,
                "adverse_impact_ratio": round(ratio, 4),
                "passes_compliance": passes,
                "protected_selection_rate": round(protected_rate, 4),
                "comparison_selection_rate": round(comparison_rate, 4),
                "sample_size": len(decisions)
            })
            
            # Update metrics
            if not passes:
                BIAS_VIOLATIONS.labels(
                    tenant_id=request.tenant_id,
                    model=request.model,
                    protected_group=protected_group
                ).inc()
            
            ADVERSE_IMPACT_RATIO.labels(
                model=request.model,
                protected_group=protected_group
            ).set(ratio)
        
        db.commit()
        EEOC_OPERATIONS.labels(operation='automated_bias_test', status='success').inc()
        
        logger.info(f"Automated bias test completed for job {request.job_id}: {len(results)} groups tested")
        
        return {
            "tenant_id": request.tenant_id,
            "job_id": request.job_id,
            "model": request.model,
            "total_decisions": len(decisions),
            "tests_run": len(results),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Automated bias test failed: {e}")
        EEOC_OPERATIONS.labels(operation='automated_bias_test', status='error').inc()
        raise HTTPException(status_code=500, detail=str(e))

def calculate_group_statistics(decisions: List[tuple], protected_group: str) -> Dict[str, int]:
    """Calculate selection statistics for a protected group"""
    protected_selected = 0
    protected_total = 0
    comparison_selected = 0
    comparison_total = 0
    
    for decision, protected_attrs in decisions:
        if not protected_attrs:
            continue
        
        # Check if candidate is in protected group
        is_protected = protected_attrs.get(protected_group) is not None
        is_selected = decision == "selected"
        
        if is_protected:
            protected_total += 1
            if is_selected:
                protected_selected += 1
        else:
            comparison_total += 1
            if is_selected:
                comparison_selected += 1
    
    return {
        "protected_selected": protected_selected,
        "protected_total": protected_total,
        "comparison_selected": comparison_selected,
        "comparison_total": comparison_total
    }

@app.get("/v1/screening-explainability/{decision_id}")
def get_decision_explainability(decision_id: str, db = Depends(get_db)):
    """Get explainability data for a specific screening decision"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT candidate_id, job_id, decision, confidence_score,
                   decision_factors, top_reasons, model, provider, created_at
            FROM ai_screening_decisions
            WHERE decision_id = %s
        """, (decision_id,))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Decision not found")
        
        EEOC_OPERATIONS.labels(operation='get_explainability', status='success').inc()
        
        return {
            "decision_id": decision_id,
            "candidate_id": result[0],
            "job_id": result[1],
            "decision": result[2],
            "confidence_score": float(result[3]),
            "decision_factors": result[4],
            "top_reasons": result[5],
            "model": result[6],
            "provider": result[7],
            "created_at": result[8].isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get explainability: {e}")
        EEOC_OPERATIONS.labels(operation='get_explainability', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/v1/bias-report/{tenant_id}")
def get_bias_report(tenant_id: str, days: int = 30, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT model, protected_group, job_id,
                   AVG(adverse_impact_ratio) as avg_ratio,
                   COUNT(*) as test_count,
                   SUM(CASE WHEN NOT passes_compliance THEN 1 ELSE 0 END) as failed_count,
                   MAX(test_date) as last_test_date
            FROM bias_monitoring
            WHERE tenant_id = %s 
              AND test_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY model, protected_group, job_id
            ORDER BY avg_ratio ASC
        """, (tenant_id, days))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "model": row[0],
                "protected_group": row[1],
                "job_id": row[2],
                "avg_adverse_impact_ratio": round(float(row[3]), 4),
                "test_count": row[4],
                "failed_tests": row[5],
                "compliance_rate": round((row[4] - row[5]) / row[4] * 100, 2) if row[4] > 0 else 0,
                "last_test_date": row[6].isoformat() if row[6] else None
            })
        
        EEOC_OPERATIONS.labels(operation='bias_report', status='success').inc()
        
        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "tests": results
        }
    except Exception as e:
        logger.error(f"Failed to generate bias report: {e}")
        EEOC_OPERATIONS.labels(operation='bias_report', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "eeoc-compliance"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8086"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

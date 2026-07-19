"""
Ledgerline EEOC Compliance Module
Handles bias monitoring and adverse impact analysis (4/5ths rule)
"""
import logging
import os
from datetime import datetime, date
from typing import Optional

import psycopg2
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EEOC_OPERATIONS = Counter(
    'ledgerline_eeoc_operations_total',
    'Total EEOC compliance operations',
    ['operation', 'status']
)

class BiasTestCreate(BaseModel):
    tenant_id: str
    test_date: date
    model: str
    protected_group: str
    selection_rate_protected: float = Field(..., ge=0, le=1)
    selection_rate_comparison: float = Field(..., ge=0, le=1)
    sample_size: int = Field(..., gt=0)

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
                tenant_id, test_date, model, protected_group,
                selection_rate_protected, selection_rate_comparison,
                adverse_impact_ratio, passes_compliance,
                sample_size, flagged_for_review
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            test.tenant_id, test.test_date, test.model, test.protected_group,
            test.selection_rate_protected, test.selection_rate_comparison,
            ratio, passes, test.sample_size, not passes
        ))
        
        result = cursor.fetchone()
        db.commit()
        EEOC_OPERATIONS.labels(operation='bias_test_create', status='success').inc()
        
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

@app.get("/v1/bias-report/{tenant_id}")
def get_bias_report(tenant_id: str, days: int = 30, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT model, protected_group, 
                   AVG(adverse_impact_ratio) as avg_ratio,
                   COUNT(*) as test_count,
                   SUM(CASE WHEN NOT passes_compliance THEN 1 ELSE 0 END) as failed_count
            FROM bias_monitoring
            WHERE tenant_id = %s 
              AND test_date >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY model, protected_group
            ORDER BY avg_ratio ASC
        """, (tenant_id, days))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "model": row[0],
                "protected_group": row[1],
                "avg_adverse_impact_ratio": round(float(row[2]), 4),
                "test_count": row[3],
                "failed_tests": row[4],
                "compliance_rate": round((row[3] - row[4]) / row[3] * 100, 2) if row[3] > 0 else 0
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

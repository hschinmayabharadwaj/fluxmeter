"""
Ledgerline GDPR Compliance Module
Handles consent management, data deletion, and privacy rights (GDPR Articles 13/14/17)
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

import psycopg2
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GDPR_OPERATIONS = Counter(
    'ledgerline_gdpr_operations_total',
    'Total GDPR compliance operations',
    ['operation', 'status']
)

class ConsentType(str, Enum):
    DATA_PROCESSING = "data_processing"
    AI_SCREENING = "ai_screening"
    MARKETING = "marketing"
    ANALYTICS = "analytics"

class ConsentCreate(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    consent_type: ConsentType
    consent_given: bool
    consent_method: str
    ip_address: Optional[str] = None
    expires_days: Optional[int] = 365

class DeletionRequest(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    request_type: str = Field(..., regex="^(erasure|export|rectification)$")

app = FastAPI(
    title="Ledgerline GDPR Compliance",
    description="GDPR Article 13/14/17 compliance",
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

@app.post("/v1/consent")
def create_consent(consent: ConsentCreate, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        expires_at = datetime.utcnow() + timedelta(days=consent.expires_days) if consent.expires_days else None
        
        cursor.execute("""
            INSERT INTO candidate_consent (
                tenant_id, candidate_email, consent_type,
                consent_given, consent_method, ip_address, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, candidate_email, consent_type)
            DO UPDATE SET consent_given = EXCLUDED.consent_given,
                          created_at = CURRENT_TIMESTAMP
            RETURNING consent_id, created_at
        """, (consent.tenant_id, consent.candidate_email, consent.consent_type.value,
              consent.consent_given, consent.consent_method, consent.ip_address, expires_at))
        
        result = cursor.fetchone()
        db.commit()
        GDPR_OPERATIONS.labels(operation='consent_create', status='success').inc()
        
        return {
            "consent_id": str(result[0]),
            "tenant_id": consent.tenant_id,
            "candidate_email": consent.candidate_email,
            "consent_type": consent.consent_type.value,
            "created_at": result[1].isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record consent: {e}")
        GDPR_OPERATIONS.labels(operation='consent_create', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/deletion-request")
def create_deletion_request(request: DeletionRequest, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO data_deletion_requests (
                tenant_id, candidate_email, request_type, status
            ) VALUES (%s, %s, %s, 'pending')
            RETURNING request_id, created_at
        """, (request.tenant_id, request.candidate_email, request.request_type))
        
        result = cursor.fetchone()
        db.commit()
        GDPR_OPERATIONS.labels(operation='deletion_request', status='success').inc()
        
        return {
            "request_id": str(result[0]),
            "status": "pending",
            "created_at": result[1].isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create deletion request: {e}")
        GDPR_OPERATIONS.labels(operation='deletion_request', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "gdpr-compliance"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8085"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

"""
Ledgerline GDPR Compliance Module
Handles consent management, data deletion, and privacy rights (GDPR Articles 13/14/15/17)
Includes consent withdrawal, verification, audit trails, and data export
"""
import logging
import os
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from enum import Enum

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends, Response as FastAPIResponse
from pydantic import BaseModel, EmailStr, Field
from prometheus_client import Counter, Gauge, generate_latest
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GDPR_OPERATIONS = Counter(
    'ledgerline_gdpr_operations_total',
    'Total GDPR compliance operations',
    ['operation', 'status']
)

ACTIVE_CONSENTS = Gauge(
    'ledgerline_active_consents',
    'Active consents by tenant and type',
    ['tenant_id', 'consent_type']
)

PENDING_DELETIONS = Gauge(
    'ledgerline_pending_deletion_requests',
    'Pending data deletion requests by tenant',
    ['tenant_id']
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

class ConsentWithdraw(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    consent_type: ConsentType
    withdrawal_reason: Optional[str] = None

class ConsentVerification(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    consent_types: List[ConsentType]

class DeletionRequest(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    request_type: str = Field(..., regex="^(erasure|export|rectification)$")
    reason: Optional[str] = None

class DataExportRequest(BaseModel):
    tenant_id: str
    candidate_email: EmailStr
    format: str = Field("csv", regex="^(csv|json)$")

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

def log_gdpr_audit(cursor, tenant_id: str, candidate_email: str, operation: str, details: Dict):
    """Log GDPR operations to audit trail"""
    cursor.execute("""
        INSERT INTO audit_log (
            correlation_id, tenant_id, event_type, event_source,
            actor, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        f"gdpr_{candidate_email}_{int(datetime.utcnow().timestamp())}",
        tenant_id,
        operation,
        "gdpr-compliance",
        candidate_email,
        psycopg2.extras.Json(details)
    ))

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
                          created_at = CURRENT_TIMESTAMP,
                          revoked_at = NULL
            RETURNING consent_id, created_at
        """, (consent.tenant_id, consent.candidate_email, consent.consent_type.value,
              consent.consent_given, consent.consent_method, consent.ip_address, expires_at))
        
        result = cursor.fetchone()
        
        # Log to audit trail
        log_gdpr_audit(cursor, consent.tenant_id, consent.candidate_email, "consent_created", {
            "consent_type": consent.consent_type.value,
            "consent_given": consent.consent_given,
            "consent_method": consent.consent_method,
            "ip_address": consent.ip_address
        })
        
        db.commit()
        GDPR_OPERATIONS.labels(operation='consent_create', status='success').inc()
        
        # Update metrics
        if consent.consent_given:
            ACTIVE_CONSENTS.labels(
                tenant_id=consent.tenant_id,
                consent_type=consent.consent_type.value
            ).inc()
        
        logger.info(f"Consent recorded: {consent.candidate_email} / {consent.consent_type.value} - Given: {consent.consent_given}")
        
        return {
            "consent_id": str(result[0]),
            "tenant_id": consent.tenant_id,
            "candidate_email": consent.candidate_email,
            "consent_type": consent.consent_type.value,
            "consent_given": consent.consent_given,
            "created_at": result[1].isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record consent: {e}")
        GDPR_OPERATIONS.labels(operation='consent_create', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/consent/withdraw")
def withdraw_consent(withdrawal: ConsentWithdraw, db = Depends(get_db)):
    """Withdraw previously given consent (GDPR Article 7(3))"""
    try:
        cursor = db.cursor()
        
        # Check if consent exists
        cursor.execute("""
            SELECT consent_id, consent_given
            FROM candidate_consent
            WHERE tenant_id = %s AND candidate_email = %s AND consent_type = %s
        """, (withdrawal.tenant_id, withdrawal.candidate_email, withdrawal.consent_type.value))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Consent record not found")
        
        consent_id, currently_given = result
        
        if not currently_given:
            raise HTTPException(status_code=400, detail="Consent already withdrawn")
        
        # Withdraw consent
        cursor.execute("""
            UPDATE candidate_consent
            SET consent_given = false, revoked_at = CURRENT_TIMESTAMP
            WHERE consent_id = %s
        """, (consent_id,))
        
        # Log to audit trail
        log_gdpr_audit(cursor, withdrawal.tenant_id, withdrawal.candidate_email, "consent_withdrawn", {
            "consent_type": withdrawal.consent_type.value,
            "reason": withdrawal.withdrawal_reason
        })
        
        db.commit()
        GDPR_OPERATIONS.labels(operation='consent_withdraw', status='success').inc()
        
        # Update metrics
        ACTIVE_CONSENTS.labels(
            tenant_id=withdrawal.tenant_id,
            consent_type=withdrawal.consent_type.value
        ).dec()
        
        logger.info(f"Consent withdrawn: {withdrawal.candidate_email} / {withdrawal.consent_type.value}")
        
        return {
            "consent_id": str(consent_id),
            "status": "withdrawn",
            "revoked_at": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to withdraw consent: {e}")
        GDPR_OPERATIONS.labels(operation='consent_withdraw', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/consent/verify")
def verify_consent(verification: ConsentVerification, db = Depends(get_db)):
    """Verify that candidate has given required consents before processing"""
    try:
        cursor = db.cursor()
        
        results = {}
        all_valid = True
        
        for consent_type in verification.consent_types:
            cursor.execute("""
                SELECT consent_given, expires_at, revoked_at
                FROM candidate_consent
                WHERE tenant_id = %s AND candidate_email = %s AND consent_type = %s
            """, (verification.tenant_id, verification.candidate_email, consent_type.value))
            
            result = cursor.fetchone()
            
            if not result:
                results[consent_type.value] = {
                    "valid": False,
                    "reason": "no_consent_recorded"
                }
                all_valid = False
                continue
            
            consent_given, expires_at, revoked_at = result
            
            # Check if consent is valid
            if not consent_given or revoked_at:
                results[consent_type.value] = {
                    "valid": False,
                    "reason": "consent_withdrawn"
                }
                all_valid = False
            elif expires_at and expires_at < datetime.utcnow():
                results[consent_type.value] = {
                    "valid": False,
                    "reason": "consent_expired",
                    "expired_at": expires_at.isoformat()
                }
                all_valid = False
            else:
                results[consent_type.value] = {
                    "valid": True,
                    "expires_at": expires_at.isoformat() if expires_at else None
                }
        
        GDPR_OPERATIONS.labels(operation='consent_verify', status='success').inc()
        
        return {
            "tenant_id": verification.tenant_id,
            "candidate_email": verification.candidate_email,
            "all_valid": all_valid,
            "consents": results
        }
    except Exception as e:
        logger.error(f"Failed to verify consent: {e}")
        GDPR_OPERATIONS.labels(operation='consent_verify', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/v1/consent/{tenant_id}/{candidate_email}")
def get_consents(tenant_id: str, candidate_email: str, db = Depends(get_db)):
    """Get all consent records for a candidate"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT consent_type, consent_given, consent_method,
                   created_at, expires_at, revoked_at
            FROM candidate_consent
            WHERE tenant_id = %s AND candidate_email = %s
            ORDER BY created_at DESC
        """, (tenant_id, candidate_email))
        
        consents = []
        for row in cursor.fetchall():
            consents.append({
                "consent_type": row[0],
                "consent_given": row[1],
                "consent_method": row[2],
                "created_at": row[3].isoformat(),
                "expires_at": row[4].isoformat() if row[4] else None,
                "revoked_at": row[5].isoformat() if row[5] else None,
                "is_active": row[1] and (not row[4] or row[4] > datetime.utcnow()) and not row[5]
            })
        
        GDPR_OPERATIONS.labels(operation='get_consents', status='success').inc()
        
        return {
            "tenant_id": tenant_id,
            "candidate_email": candidate_email,
            "consents": consents
        }
    except Exception as e:
        logger.error(f"Failed to get consents: {e}")
        GDPR_OPERATIONS.labels(operation='get_consents', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/deletion-request")
def create_deletion_request(request: DeletionRequest, db = Depends(get_db)):
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO data_deletion_requests (
                tenant_id, candidate_email, request_type, status, metadata
            ) VALUES (%s, %s, %s, 'pending', %s)
            RETURNING request_id, created_at
        """, (
            request.tenant_id, 
            request.candidate_email, 
            request.request_type,
            psycopg2.extras.Json({"reason": request.reason} if request.reason else {})
        ))
        
        result = cursor.fetchone()
        
        # Log to audit trail
        log_gdpr_audit(cursor, request.tenant_id, request.candidate_email, "deletion_request_created", {
            "request_type": request.request_type,
            "reason": request.reason
        })
        
        db.commit()
        GDPR_OPERATIONS.labels(operation='deletion_request', status='success').inc()
        
        # Update metrics
        PENDING_DELETIONS.labels(tenant_id=request.tenant_id).inc()
        
        logger.info(f"Deletion request created: {request.candidate_email} / {request.request_type}")
        
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

@app.post("/v1/data-export")
def export_candidate_data(export_request: DataExportRequest, db = Depends(get_db)):
    """Export all candidate data (GDPR Article 15 - Right of Access)"""
    try:
        cursor = db.cursor()
        
        # Collect all candidate data
        data_export = {
            "tenant_id": export_request.tenant_id,
            "candidate_email": export_request.candidate_email,
            "export_date": datetime.utcnow().isoformat(),
            "consents": [],
            "screening_decisions": [],
            "deletion_requests": []
        }
        
        # Get consent records
        cursor.execute("""
            SELECT consent_type, consent_given, consent_method,
                   created_at, expires_at, revoked_at, metadata
            FROM candidate_consent
            WHERE tenant_id = %s AND candidate_email = %s
        """, (export_request.tenant_id, export_request.candidate_email))
        
        for row in cursor.fetchall():
            data_export["consents"].append({
                "consent_type": row[0],
                "consent_given": row[1],
                "consent_method": row[2],
                "created_at": row[3].isoformat(),
                "expires_at": row[4].isoformat() if row[4] else None,
                "revoked_at": row[5].isoformat() if row[5] else None,
                "metadata": row[6]
            })
        
        # Get screening decisions (without protected attributes)
        cursor.execute("""
            SELECT decision_id, job_id, decision, confidence_score,
                   decision_factors, top_reasons, model, created_at
            FROM ai_screening_decisions
            WHERE tenant_id = %s AND candidate_id = %s
        """, (export_request.tenant_id, export_request.candidate_email))
        
        for row in cursor.fetchall():
            data_export["screening_decisions"].append({
                "decision_id": str(row[0]),
                "job_id": row[1],
                "decision": row[2],
                "confidence_score": float(row[3]),
                "decision_factors": row[4],
                "top_reasons": row[5],
                "model": row[6],
                "created_at": row[7].isoformat()
            })
        
        # Get deletion requests
        cursor.execute("""
            SELECT request_id, request_type, status, created_at, completed_at
            FROM data_deletion_requests
            WHERE tenant_id = %s AND candidate_email = %s
        """, (export_request.tenant_id, export_request.candidate_email))
        
        for row in cursor.fetchall():
            data_export["deletion_requests"].append({
                "request_id": str(row[0]),
                "request_type": row[1],
                "status": row[2],
                "created_at": row[3].isoformat(),
                "completed_at": row[4].isoformat() if row[4] else None
            })
        
        # Log to audit trail
        log_gdpr_audit(cursor, export_request.tenant_id, export_request.candidate_email, "data_exported", {
            "format": export_request.format,
            "records_exported": {
                "consents": len(data_export["consents"]),
                "screening_decisions": len(data_export["screening_decisions"]),
                "deletion_requests": len(data_export["deletion_requests"])
            }
        })
        
        db.commit()
        GDPR_OPERATIONS.labels(operation='data_export', status='success').inc()
        
        # Return data in requested format
        if export_request.format == "json":
            return data_export
        else:  # CSV
            # Create CSV from flattened data
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write metadata
            writer.writerow(["Export Date", datetime.utcnow().isoformat()])
            writer.writerow(["Tenant ID", export_request.tenant_id])
            writer.writerow(["Candidate Email", export_request.candidate_email])
            writer.writerow([])
            
            # Write consents
            if data_export["consents"]:
                writer.writerow(["Consents"])
                writer.writerow(["Type", "Given", "Method", "Created", "Expires", "Revoked"])
                for consent in data_export["consents"]:
                    writer.writerow([
                        consent["consent_type"],
                        consent["consent_given"],
                        consent["consent_method"],
                        consent["created_at"],
                        consent["expires_at"] or "",
                        consent["revoked_at"] or ""
                    ])
                writer.writerow([])
            
            # Write screening decisions
            if data_export["screening_decisions"]:
                writer.writerow(["Screening Decisions"])
                writer.writerow(["Decision ID", "Job ID", "Decision", "Confidence", "Model", "Created"])
                for decision in data_export["screening_decisions"]:
                    writer.writerow([
                        decision["decision_id"],
                        decision["job_id"],
                        decision["decision"],
                        decision["confidence_score"],
                        decision["model"],
                        decision["created_at"]
                    ])
            
            return FastAPIResponse(
                content=output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=candidate_data_{export_request.candidate_email}.csv"
                }
            )
            
    except Exception as e:
        logger.error(f"Failed to export data: {e}")
        GDPR_OPERATIONS.labels(operation='data_export', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/deletion-request/{request_id}/execute")
def execute_deletion(request_id: str, db = Depends(get_db)):
    """Execute a pending deletion request (GDPR Article 17)"""
    try:
        cursor = db.cursor()
        
        # Get deletion request
        cursor.execute("""
            SELECT tenant_id, candidate_email, request_type, status
            FROM data_deletion_requests
            WHERE request_id = %s
        """, (request_id,))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Deletion request not found")
        
        tenant_id, candidate_email, request_type, status = result
        
        if status != "pending":
            raise HTTPException(status_code=400, detail=f"Request already {status}")
        
        # Update status to processing
        cursor.execute("""
            UPDATE data_deletion_requests
            SET status = 'processing'
            WHERE request_id = %s
        """, (request_id,))
        
        records_affected = 0
        
        try:
            if request_type == "erasure":
                # Delete from ai_screening_decisions (anonymize decision factors)
                cursor.execute("""
                    UPDATE ai_screening_decisions
                    SET candidate_id = 'DELETED',
                        decision_factors = '{"anonymized": true}'::jsonb,
                        top_reasons = ARRAY['Data deleted per GDPR request'],
                        protected_attributes = NULL,
                        metadata = metadata || '{"deleted": true, "deletion_date": "%s"}'::jsonb
                    WHERE tenant_id = %%s AND candidate_id = %%s
                    RETURNING decision_id
                """ % datetime.utcnow().isoformat(), (tenant_id, candidate_email))
                records_affected += cursor.rowcount
                
                # Delete or anonymize consent records
                cursor.execute("""
                    UPDATE candidate_consent
                    SET candidate_email = 'deleted_%s@anonymized.local',
                        ip_address = NULL,
                        user_agent = NULL,
                        consent_given = false,
                        revoked_at = CURRENT_TIMESTAMP,
                        metadata = metadata || '{"deleted": true, "deletion_date": "%s"}'::jsonb
                    WHERE tenant_id = %%s AND candidate_email = %%s
                """ % (request_id[:8], datetime.utcnow().isoformat()), (tenant_id, candidate_email))
                records_affected += cursor.rowcount
                
                # Update ledger to anonymize candidate references in cost_allocation_tags
                cursor.execute("""
                    UPDATE ledger
                    SET cost_allocation_tags = 
                        CASE 
                            WHEN cost_allocation_tags ? 'candidate_email' 
                            THEN cost_allocation_tags || '{"candidate_email": "DELETED"}'::jsonb
                            ELSE cost_allocation_tags
                        END
                    WHERE tenant_id = %s 
                      AND cost_allocation_tags->>'candidate_email' = %s
                """, (tenant_id, candidate_email))
                records_affected += cursor.rowcount
            
            # Mark request as completed
            cursor.execute("""
                UPDATE data_deletion_requests
                SET status = 'completed',
                    records_affected = %s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE request_id = %s
            """, (records_affected, request_id))
            
            # Log to audit trail
            log_gdpr_audit(cursor, tenant_id, candidate_email, "deletion_executed", {
                "request_id": request_id,
                "request_type": request_type,
                "records_affected": records_affected
            })
            
            db.commit()
            GDPR_OPERATIONS.labels(operation='deletion_execute', status='success').inc()
            
            # Update metrics
            PENDING_DELETIONS.labels(tenant_id=tenant_id).dec()
            
            logger.info(f"Deletion executed: {request_id} - {records_affected} records affected")
            
            return {
                "request_id": request_id,
                "status": "completed",
                "records_affected": records_affected,
                "completed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Mark as failed
            cursor.execute("""
                UPDATE data_deletion_requests
                SET status = 'failed',
                    metadata = metadata || %s
                WHERE request_id = %s
            """, (psycopg2.extras.Json({"error": str(e)}), request_id))
            db.commit()
            raise
            
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to execute deletion: {e}")
        GDPR_OPERATIONS.labels(operation='deletion_execute', status='error').inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/deletion-request/{request_id}/status")
def get_deletion_status(request_id: str, db = Depends(get_db)):
    """Get status of a deletion request"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT tenant_id, candidate_email, request_type, status,
                   records_affected, created_at, completed_at, metadata
            FROM data_deletion_requests
            WHERE request_id = %s
        """, (request_id,))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Deletion request not found")
        
        GDPR_OPERATIONS.labels(operation='deletion_status', status='success').inc()
        
        return {
            "request_id": request_id,
            "tenant_id": result[0],
            "candidate_email": result[1],
            "request_type": result[2],
            "status": result[3],
            "records_affected": result[4] or 0,
            "created_at": result[5].isoformat(),
            "completed_at": result[6].isoformat() if result[6] else None,
            "metadata": result[7]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get deletion status: {e}")
        GDPR_OPERATIONS.labels(operation='deletion_status', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/deletion-request/process-pending")
def process_pending_deletions(tenant_id: Optional[str] = None, limit: int = 10, db = Depends(get_db)):
    """Background job to process pending deletion requests"""
    try:
        cursor = db.cursor()
        
        # Get pending deletion requests
        if tenant_id:
            cursor.execute("""
                SELECT request_id
                FROM data_deletion_requests
                WHERE tenant_id = %s AND status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
            """, (tenant_id, limit))
        else:
            cursor.execute("""
                SELECT request_id
                FROM data_deletion_requests
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT %s
            """, (limit,))
        
        pending_requests = [row[0] for row in cursor.fetchall()]
        
        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "request_ids": []
        }
        
        for request_id in pending_requests:
            try:
                # Execute deletion for each request
                response = execute_deletion(str(request_id), db)
                results["succeeded"] += 1
                results["request_ids"].append({
                    "request_id": str(request_id),
                    "status": "completed"
                })
            except Exception as e:
                logger.error(f"Failed to process deletion {request_id}: {e}")
                results["failed"] += 1
                results["request_ids"].append({
                    "request_id": str(request_id),
                    "status": "failed",
                    "error": str(e)
                })
            finally:
                results["processed"] += 1
        
        GDPR_OPERATIONS.labels(operation='process_pending', status='success').inc()
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to process pending deletions: {e}")
        GDPR_OPERATIONS.labels(operation='process_pending', status='error').inc()
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

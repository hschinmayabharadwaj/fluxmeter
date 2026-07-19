"""
Ledgerline Tenant Management Service
Handles tenant lifecycle, RBAC, and API key management with HashiCorp Vault integration
"""
import logging
import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import psycopg2
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from prometheus_client import Counter, generate_latest
from starlette.responses import Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
TENANT_OPERATIONS = Counter(
    'ledgerline_tenant_operations_total',
    'Total tenant management operations',
    ['operation', 'status']
)

# Security
security = HTTPBearer()

# Database connection
def get_db():
    """Get PostgreSQL database connection"""
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL", "postgres://ledgerline:ledgerline@localhost:5432/ledgerline")
    )
    try:
        yield conn
    finally:
        conn.close()


class TenantCreate(BaseModel):
    """Tenant creation request"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    tpm_limit: int = Field(default=10000, gt=0)
    rpm_limit: int = Field(default=100, gt=0)
    billing_enabled: bool = True
    cost_multiplier: float = Field(default=1.0, gt=0)
    retention_days: int = Field(default=90, gt=0)


class TenantResponse(BaseModel):
    """Tenant response model"""
    tenant_id: str
    name: str
    email: str
    status: str
    tpm_limit: int
    rpm_limit: int
    billing_enabled: bool
    cost_multiplier: float
    retention_days: int
    created_at: str
    updated_at: str


class TenantUpdate(BaseModel):
    """Tenant update request"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[str] = None
    tpm_limit: Optional[int] = None
    rpm_limit: Optional[int] = None
    billing_enabled: Optional[bool] = None
    cost_multiplier: Optional[float] = None
    retention_days: Optional[int] = None


class APIKeyCreate(BaseModel):
    """API key creation request"""
    key_name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., regex="^(openai|anthropic|cohere)$")
    key_value: str = Field(..., min_length=10)
    expires_days: Optional[int] = Field(default=365, gt=0)


class APIKeyResponse(BaseModel):
    """API key response model"""
    key_id: str
    key_name: str
    provider: str
    key_hash: str
    vault_path: str
    status: str
    created_at: str
    expires_at: Optional[str]


class RoleAssignment(BaseModel):
    """Role assignment request"""
    user_email: str
    role: str = Field(..., regex="^(admin|viewer|editor)$")


app = FastAPI(
    title="Ledgerline Tenant Management",
    description="Tenant lifecycle, RBAC, and API key management",
    version="1.0.0"
)


def hash_api_key(key: str) -> str:
    """Hash API key for storage"""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_vault_path(tenant_id: str, provider: str, key_name: str) -> str:
    """Generate HashiCorp Vault path for API key storage"""
    # In production, this would interact with actual Vault
    return f"secret/ledgerline/tenants/{tenant_id}/providers/{provider}/{key_name}"


def store_key_in_vault(vault_path: str, key_value: str) -> bool:
    """
    Store API key in HashiCorp Vault
    In production, use hvac library to interact with Vault
    """
    # Mock implementation - in production, use:
    # import hvac
    # client = hvac.Client(url='http://vault:8200', token=os.getenv('VAULT_TOKEN'))
    # client.secrets.kv.v2.create_or_update_secret(path=vault_path, secret={'key': key_value})
    
    logger.info(f"Storing key in Vault at path: {vault_path}")
    # For development, we'll just log it (never do this in production!)
    return True


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token for admin access"""
    # In production, verify JWT token signature and claims
    # For now, simple token check
    token = credentials.credentials
    if not token or token == "invalid":
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return token


@app.post("/v1/tenants", response_model=TenantResponse)
def create_tenant(
    tenant: TenantCreate,
    db = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Create a new tenant"""
    try:
        cursor = db.cursor()
        
        # Insert tenant
        cursor.execute("""
            INSERT INTO tenants (
                name, email, status, tpm_limit, rpm_limit,
                billing_enabled, cost_multiplier, retention_days
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING tenant_id, created_at, updated_at
        """, (
            tenant.name,
            tenant.email,
            'active',
            tenant.tpm_limit,
            tenant.rpm_limit,
            tenant.billing_enabled,
            tenant.cost_multiplier,
            tenant.retention_days
        ))
        
        result = cursor.fetchone()
        db.commit()
        
        TENANT_OPERATIONS.labels(operation='create', status='success').inc()
        
        return TenantResponse(
            tenant_id=str(result[0]),
            name=tenant.name,
            email=tenant.email,
            status='active',
            tpm_limit=tenant.tpm_limit,
            rpm_limit=tenant.rpm_limit,
            billing_enabled=tenant.billing_enabled,
            cost_multiplier=tenant.cost_multiplier,
            retention_days=tenant.retention_days,
            created_at=result[1].isoformat(),
            updated_at=result[2].isoformat()
        )
        
    except psycopg2.IntegrityError as e:
        db.rollback()
        TENANT_OPERATIONS.labels(operation='create', status='error').inc()
        raise HTTPException(status_code=400, detail="Tenant with this email already exists")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create tenant: {e}")
        TENANT_OPERATIONS.labels(operation='create', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/v1/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    db = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Get tenant by ID"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT tenant_id, name, email, status, tpm_limit, rpm_limit,
                   billing_enabled, cost_multiplier, retention_days,
                   created_at, updated_at
            FROM tenants
            WHERE tenant_id = %s
        """, (tenant_id,))
        
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        TENANT_OPERATIONS.labels(operation='get', status='success').inc()
        
        return TenantResponse(
            tenant_id=str(result[0]),
            name=result[1],
            email=result[2],
            status=result[3],
            tpm_limit=result[4],
            rpm_limit=result[5],
            billing_enabled=result[6],
            cost_multiplier=float(result[7]),
            retention_days=result[8],
            created_at=result[9].isoformat(),
            updated_at=result[10].isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant: {e}")
        TENANT_OPERATIONS.labels(operation='get', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.patch("/v1/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str,
    updates: TenantUpdate,
    db = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Update tenant configuration"""
    try:
        cursor = db.cursor()
        
        # Build dynamic update query
        update_fields = []
        params = []
        
        if updates.name is not None:
            update_fields.append("name = %s")
            params.append(updates.name)
        if updates.email is not None:
            update_fields.append("email = %s")
            params.append(updates.email)
        if updates.status is not None:
            update_fields.append("status = %s")
            params.append(updates.status)
        if updates.tpm_limit is not None:
            update_fields.append("tpm_limit = %s")
            params.append(updates.tpm_limit)
        if updates.rpm_limit is not None:
            update_fields.append("rpm_limit = %s")
            params.append(updates.rpm_limit)
        if updates.billing_enabled is not None:
            update_fields.append("billing_enabled = %s")
            params.append(updates.billing_enabled)
        if updates.cost_multiplier is not None:
            update_fields.append("cost_multiplier = %s")
            params.append(updates.cost_multiplier)
        if updates.retention_days is not None:
            update_fields.append("retention_days = %s")
            params.append(updates.retention_days)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        params.append(tenant_id)
        
        query = f"""
            UPDATE tenants
            SET {', '.join(update_fields)}
            WHERE tenant_id = %s
            RETURNING tenant_id, name, email, status, tpm_limit, rpm_limit,
                      billing_enabled, cost_multiplier, retention_days,
                      created_at, updated_at
        """
        
        cursor.execute(query, params)
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        db.commit()
        TENANT_OPERATIONS.labels(operation='update', status='success').inc()
        
        return TenantResponse(
            tenant_id=str(result[0]),
            name=result[1],
            email=result[2],
            status=result[3],
            tpm_limit=result[4],
            rpm_limit=result[5],
            billing_enabled=result[6],
            cost_multiplier=float(result[7]),
            retention_days=result[8],
            created_at=result[9].isoformat(),
            updated_at=result[10].isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update tenant: {e}")
        TENANT_OPERATIONS.labels(operation='update', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/tenants/{tenant_id}/api-keys", response_model=APIKeyResponse)
def create_api_key(
    tenant_id: str,
    api_key: APIKeyCreate,
    db = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Create API key for tenant"""
    try:
        cursor = db.cursor()
        
        # Verify tenant exists
        cursor.execute("SELECT tenant_id FROM tenants WHERE tenant_id = %s", (tenant_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Hash the key
        key_hash = hash_api_key(api_key.key_value)
        
        # Generate Vault path
        vault_path = generate_vault_path(tenant_id, api_key.provider, api_key.key_name)
        
        # Store in Vault (mock for now)
        if not store_key_in_vault(vault_path, api_key.key_value):
            raise HTTPException(status_code=500, detail="Failed to store key in Vault")
        
        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(days=api_key.expires_days) if api_key.expires_days else None
        
        # Insert key metadata
        cursor.execute("""
            INSERT INTO tenant_api_keys (
                tenant_id, key_name, key_hash, vault_path, provider, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING key_id, created_at
        """, (
            tenant_id,
            api_key.key_name,
            key_hash,
            vault_path,
            api_key.provider,
            expires_at
        ))
        
        result = cursor.fetchone()
        db.commit()
        
        TENANT_OPERATIONS.labels(operation='create_api_key', status='success').inc()
        
        return APIKeyResponse(
            key_id=str(result[0]),
            key_name=api_key.key_name,
            provider=api_key.provider,
            key_hash=key_hash,
            vault_path=vault_path,
            status='active',
            created_at=result[1].isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create API key: {e}")
        TENANT_OPERATIONS.labels(operation='create_api_key', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.delete("/v1/tenants/{tenant_id}/api-keys/{key_id}")
def revoke_api_key(
    tenant_id: str,
    key_id: str,
    db = Depends(get_db),
    token: str = Depends(verify_admin_token)
):
    """Revoke API key"""
    try:
        cursor = db.cursor()
        
        cursor.execute("""
            UPDATE tenant_api_keys
            SET status = 'revoked'
            WHERE key_id = %s AND tenant_id = %s
            RETURNING key_id
        """, (key_id, tenant_id))
        
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=404, detail="API key not found")
        
        db.commit()
        TENANT_OPERATIONS.labels(operation='revoke_api_key', status='success').inc()
        
        return {"message": "API key revoked successfully", "key_id": key_id}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to revoke API key: {e}")
        TENANT_OPERATIONS.labels(operation='revoke_api_key', status='error').inc()
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "tenant-management"}


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8084"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

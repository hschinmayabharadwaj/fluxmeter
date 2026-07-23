"""
Ledgerline Semantic Cache Service using Qdrant
Implements triple-tag validation: Policy Version + Region + Provider
Integrated with billing, compliance, guardrails, and rate limiting
"""
import hashlib
import logging
import os
import psycopg2
import psycopg2.extras
import redis
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
from enum import Enum

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from starlette.responses import Response
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus Metrics
CACHE_OPERATIONS = Counter(
    'ledgerline_cache_operations_total',
    'Total cache operations',
    ['operation', 'result']
)

CACHE_LATENCY = Histogram(
    'ledgerline_cache_latency_seconds',
    'Cache operation latency'
)

CACHE_HIT_RATE = Gauge(
    'ledgerline_cache_hit_rate',
    'Cache hit rate by tenant',
    ['tenant_id']
)

POLICY_MISMATCHES = Counter(
    'ledgerline_cache_policy_mismatches',
    'Cache hits rejected due to policy changes'
)

CONSENT_VIOLATIONS = Counter(
    'ledgerline_cache_consent_violations',
    'Cache hits rejected due to consent withdrawal',
    ['consent_type']
)

RATE_LIMIT_BLOCKS = Counter(
    'ledgerline_cache_rate_limit_blocks',
    'Cache hits blocked by rate limiting'
)

class HitReason(str, Enum):
    VALID_HIT = "valid_hit"
    POLICY_MISMATCH = "policy_mismatch"
    CONSENT_MISSING = "consent_missing"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    EXPIRED = "expired"
    INVALID_TAGS = "invalid_tags"

class CacheQuery(BaseModel):
    tenant_id: str
    correlation_id: str
    prompt: str
    policy_version: str
    region: str
    provider: str
    model: str
    candidate_email: Optional[EmailStr] = None
    job_id: Optional[str] = None
    similarity_threshold: float = Field(0.95, ge=0, le=1)

class CacheEntry(BaseModel):
    tenant_id: str
    prompt: str
    response: str
    policy_version: str
    region: str
    provider: str
    model: str
    candidate_email: Optional[str] = None
    job_id: Optional[str] = None
    estimated_tokens: int = 0
    ttl_hours: int = 24
    created_by: Optional[str] = None

app = FastAPI(
    title="Ledgerline Semantic Cache",
    description="Vector-based semantic cache with compliance integration",
    version="2.0.0"
)

# Initialize Qdrant client
qdrant_host = os.getenv("QDRANT_HOST", "localhost")
qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)

# Initialize Redis client
redis_addr = os.getenv("REDIS_ADDR", "localhost:6379")
redis_host, redis_port = redis_addr.split(":")
redis_client = redis.Redis(
    host=redis_host,
    port=int(redis_port),
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=False
)

# Initialize PostgreSQL
def get_db():
    conn = psycopg2.connect(
        os.getenv("DATABASE_URL", "postgres://ledgerline:ledgerline@localhost:5432/ledgerline")
    )
    try:
        yield conn
    finally:
        conn.close()

COLLECTION_NAME = "ledgerline_cache"
VECTOR_SIZE = 384  # sentence-transformers default

def initialize_collection():
    """Initialize Qdrant collection if not exists"""
    try:
        collections = qdrant_client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
            logger.info(f"Created collection: {COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"Failed to initialize collection: {e}")

# Initialize on startup
try:
    initialize_collection()
except Exception as e:
    logger.warning(f"Qdrant initialization warning: {e}")

def generate_embedding(text: str) -> List[float]:
    """Generate embedding vector for text"""
    # Mock embedding - in production use sentence-transformers or OpenAI
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
    np.random.seed(hash_val % (2**32))
    return np.random.rand(VECTOR_SIZE).tolist()

def create_triple_tag_filter(policy_version: str, region: str, provider: str) -> Filter:
    """Create filter for triple-tag validation"""
    return Filter(
        must=[
            FieldCondition(key="policy_version", match=MatchValue(value=policy_version)),
            FieldCondition(key="region", match=MatchValue(value=region)),
            FieldCondition(key="provider", match=MatchValue(value=provider))
        ]
    )

def get_current_policy_version(db, tenant_id: str) -> Optional[str]:
    """Get current policy version for tenant"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT metadata->>'policy_version'
            FROM tenants
            WHERE tenant_id = %s
        """, (tenant_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Failed to get policy version: {e}")
        return None

def verify_consent_valid(db, tenant_id: str, candidate_email: str, consent_type: str = "ai_screening") -> bool:
    """Verify GDPR consent is valid (not withdrawn, not expired)"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT consent_given, expires_at, revoked_at
            FROM candidate_consent
            WHERE tenant_id = %s AND candidate_email = %s AND consent_type = %s
        """, (tenant_id, candidate_email, consent_type))
        
        result = cursor.fetchone()
        if not result:
            return False
        
        consent_given, expires_at, revoked_at = result
        
        # Check if consent is valid
        if not consent_given or revoked_at:
            return False
        if expires_at and expires_at < datetime.utcnow():
            return False
        
        return True
    except Exception as e:
        logger.error(f"Failed to verify consent: {e}")
        return False

def check_rate_limit(redis_conn, tenant_id: str) -> bool:
    """Check if tenant is within rate limits"""
    try:
        # Check RPM (requests per minute) against Redis-Cell token bucket
        key = f"rate_limit:rpm:{tenant_id}"
        
        # If rate limited, Redis returns error
        result = redis_conn.get(key)
        # Implementation depends on rate limiter configuration
        # For now, assume Redis-Cell integration exists
        return True  # TODO: integrate with actual rate limiter
    except Exception as e:
        logger.warning(f"Rate limit check warning: {e}")
        return True  # Fail open - don't block cache on rate limit errors

def record_cache_hit(db, cache_id: str, tenant_id: str, correlation_id: str, 
                     hit_reason: HitReason, similarity_score: float, 
                     ledger_id: Optional[int] = None):
    """Record cache hit in audit log"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO cache_hit_log (
                cache_id, tenant_id, correlation_id, ledger_id,
                hit_reason, similarity_score
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (cache_id, tenant_id, correlation_id, ledger_id, hit_reason.value, similarity_score))
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record cache hit: {e}")

def create_ledger_entry(db, correlation_id: str, tenant_id: str, cache_id: str,
                       provider: str, model: str, estimated_tokens: int) -> Optional[int]:
    """Create ledger entry for cache hit (zero tokens but record the event)"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO ledger (
                correlation_id, attempt_id, tenant_id,
                provider, model, request_type,
                token_count, prompt_tokens, completion_tokens,
                estimated_cost, actual_cost, currency,
                status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            correlation_id,
            f"cache_{cache_id[:8]}",
            tenant_id,
            provider,
            model,
            "cache_hit",
            0,  # No tokens consumed on cache hit
            0,
            0,
            0.0,
            0.0,
            "USD",
            "RECONCILED",
            psycopg2.extras.Json({
                "cache_id": cache_id,
                "cache_hit_time": datetime.utcnow().isoformat()
            })
        ))
        
        ledger_id = cursor.fetchone()[0]
        db.commit()
        return ledger_id
    except Exception as e:
        logger.error(f"Failed to create ledger entry: {e}")
        db.rollback()
        return None

@app.post("/v1/cache/query")
def query_cache_integrated(query: CacheQuery, db = Depends(get_db)):
    """
    Query semantic cache with full compliance integration
    
    Validates:
    1. Policy version matches current tenant policy
    2. GDPR consent is valid (if candidate_email provided)
    3. Rate limits not exceeded
    4. Cache entry not expired
    5. Triple-tag validation (policy_version, region, provider)
    """
    start_time = datetime.utcnow()
    
    try:
        # Step 1: Validate triple tags
        tag_filter = create_triple_tag_filter(
            query.policy_version,
            query.region,
            query.provider
        )
        
        # Generate embedding for query
        query_vector = generate_embedding(query.prompt)
        
        # Search in Qdrant
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=tag_filter,
            limit=1,
            score_threshold=query.similarity_threshold
        )
        
        if not results:
            CACHE_OPERATIONS.labels(operation='query', result='miss').inc()
            logger.info(f"Cache MISS for {query.prompt[:50]}... (similarity threshold)")
            return {"hit": False, "reason": "no_match", "latency_ms": 0}
        
        hit = results[0]
        hit_payload = hit.payload
        cache_id = str(hit.id)
        
        # Step 2: Check if entry is expired
        created_at = datetime.fromisoformat(hit_payload['created_at'])
        ttl_hours = hit_payload.get('ttl_hours', 24)
        expires_at = created_at + timedelta(hours=ttl_hours)
        
        if datetime.utcnow() > expires_at:
            CACHE_OPERATIONS.labels(operation='query', result='expired').inc()
            record_cache_hit(db, cache_id, query.tenant_id, query.correlation_id,
                           HitReason.EXPIRED, hit.score)
            logger.info(f"Cache entry expired: {cache_id}")
            return {"hit": False, "reason": "expired", "latency_ms": 0}
        
        # Step 3: Validate policy version (CRITICAL for compliance)
        cursor = db.cursor()
        cursor.execute("""
            SELECT policy_version
            FROM semantic_cache_metadata
            WHERE cache_id = %s
        """, (cache_id,))
        
        cached_policy = cursor.fetchone()
        if cached_policy and cached_policy[0] != query.policy_version:
            CACHE_OPERATIONS.labels(operation='query', result='policy_mismatch').inc()
            POLICY_MISMATCHES.inc()
            record_cache_hit(db, cache_id, query.tenant_id, query.correlation_id,
                           HitReason.POLICY_MISMATCH, hit.score)
            logger.warning(f"Cache policy mismatch: cached={cached_policy[0]}, current={query.policy_version}")
            return {"hit": False, "reason": "policy_changed", "latency_ms": 0}
        
        # Step 4: Check GDPR consent if candidate provided (CRITICAL for compliance)
        if query.candidate_email:
            if not verify_consent_valid(db, query.tenant_id, query.candidate_email, "ai_screening"):
                CACHE_OPERATIONS.labels(operation='query', result='consent_invalid').inc()
                CONSENT_VIOLATIONS.labels(consent_type="ai_screening").inc()
                record_cache_hit(db, cache_id, query.tenant_id, query.correlation_id,
                               HitReason.CONSENT_WITHDRAWN, hit.score)
                logger.warning(f"Cache blocked: consent withdrawn for {query.candidate_email}")
                return {"hit": False, "reason": "consent_withdrawn", "latency_ms": 0}
        
        # Step 5: Check rate limits
        if not check_rate_limit(redis_client, query.tenant_id):
            CACHE_OPERATIONS.labels(operation='query', result='rate_limited').inc()
            RATE_LIMIT_BLOCKS.inc()
            record_cache_hit(db, cache_id, query.tenant_id, query.correlation_id,
                           HitReason.RATE_LIMIT_EXCEEDED, hit.score)
            logger.warning(f"Cache rate limited for tenant {query.tenant_id}")
            return {"hit": False, "reason": "rate_limit_exceeded", "latency_ms": 0}
        
        # Step 6: All validations passed - prepare response and record hit
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        # Create ledger entry for billing/audit (zero cost cache hit)
        ledger_id = create_ledger_entry(
            db,
            query.correlation_id,
            query.tenant_id,
            cache_id,
            query.provider,
            query.model,
            hit_payload.get('estimated_tokens', 0)
        )
        
        # Record hit in audit log
        record_cache_hit(db, cache_id, query.tenant_id, query.correlation_id,
                        HitReason.VALID_HIT, hit.score, ledger_id)
        
        # Update hit count
        cursor.execute("""
            UPDATE semantic_cache_metadata
            SET hit_count = hit_count + 1,
                last_hit_at = CURRENT_TIMESTAMP
            WHERE cache_id = %s
        """, (cache_id,))
        
        db.commit()
        
        CACHE_OPERATIONS.labels(operation='query', result='hit').inc()
        
        logger.info(f"Cache HIT: {query.prompt[:50]}... (similarity: {hit.score:.3f}, policy: {query.policy_version})")
        
        return {
            "hit": True,
            "response": hit_payload['response'],
            "similarity": hit.score,
            "cache_id": cache_id,
            "ledger_id": ledger_id,
            "hit_count": hit_payload.get('hit_count', 0) + 1,
            "latency_ms": latency_ms
        }
        
    except Exception as e:
        logger.error(f"Cache query failed: {e}")
        CACHE_OPERATIONS.labels(operation='query', result='error').inc()
        raise HTTPException(status_code=500, detail=f"Cache query failed: {str(e)}")

@app.post("/v1/cache/store")
def store_in_cache_integrated(entry: CacheEntry, db = Depends(get_db)):
    """Store response in semantic cache with compliance metadata"""
    try:
        start_time = datetime.utcnow()
        
        # Generate embedding
        prompt_vector = generate_embedding(entry.prompt)
        
        # Create point
        point_id = hashlib.md5(
            f"{entry.tenant_id}:{entry.prompt}:{entry.policy_version}".encode()
        ).hexdigest()
        
        expires_at = start_time + timedelta(hours=entry.ttl_hours)
        
        point = PointStruct(
            id=point_id,
            vector=prompt_vector,
            payload={
                "tenant_id": entry.tenant_id,
                "prompt": entry.prompt,
                "response": entry.response,
                "policy_version": entry.policy_version,
                "region": entry.region,
                "provider": entry.provider,
                "model": entry.model,
                "ttl_hours": entry.ttl_hours,
                "estimated_tokens": entry.estimated_tokens,
                "candidate_email": entry.candidate_email,
                "job_id": entry.job_id,
                "created_at": start_time.isoformat(),
                "created_by": entry.created_by,
                "hit_count": 0
            }
        )
        
        # Store in Qdrant
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )
        
        # Store metadata in PostgreSQL
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO semantic_cache_metadata (
                tenant_id, qdrant_point_id,
                policy_version, region, provider,
                prompt_hash, response_preview,
                candidate_email, job_id, model, estimated_tokens,
                created_by, expires_at, ttl_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, policy_version, region, provider, prompt_hash)
            DO UPDATE SET
                hit_count = 0,
                last_hit_at = CURRENT_TIMESTAMP,
                expires_at = EXCLUDED.expires_at
            RETURNING cache_id
        """, (
            entry.tenant_id, point_id,
            entry.policy_version, entry.region, entry.provider,
            hashlib.md5(entry.prompt.encode()).hexdigest(),
            entry.response[:500],  # Preview only
            entry.candidate_email,
            entry.job_id,
            entry.model,
            entry.estimated_tokens,
            entry.created_by,
            expires_at,
            entry.ttl_hours * 3600
        ))
        
        cache_id = cursor.fetchone()[0]
        db.commit()
        
        CACHE_OPERATIONS.labels(operation='store', result='success').inc()
        
        latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        logger.info(f"Stored in cache: {entry.prompt[:50]}... (policy: {entry.policy_version}, tokens: {entry.estimated_tokens})")
        
        return {
            "cache_id": str(cache_id),
            "qdrant_point_id": point_id,
            "expires_at": expires_at.isoformat(),
            "latency_ms": latency_ms
        }
        
    except Exception as e:
        logger.error(f"Failed to store in cache: {e}")
        CACHE_OPERATIONS.labels(operation='store', result='error').inc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Cache store failed: {str(e)}")

@app.post("/v1/cache/invalidate/{cache_id}")
def invalidate_cache_entry(cache_id: str, reason: str = "manual", db = Depends(get_db)):
    """Invalidate cache entry (e.g., when policy changes)"""
    try:
        cursor = db.cursor()
        
        # Soft delete (mark as invalidated but keep for audit)
        cursor.execute("""
            UPDATE semantic_cache_metadata
            SET invalidation_reason = %s,
                invalidated_at = CURRENT_TIMESTAMP
            WHERE cache_id = %s
            RETURNING cache_id
        """, (reason, cache_id))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Cache entry not found")
        
        db.commit()
        CACHE_OPERATIONS.labels(operation='invalidate', result='success').inc()
        
        logger.info(f"Cache invalidated: {cache_id} (reason: {reason})")
        
        return {"cache_id": cache_id, "invalidated": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        CACHE_OPERATIONS.labels(operation='invalidate', result='error').inc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Invalidation failed")

@app.get("/v1/cache/stats/{tenant_id}")
def get_cache_stats(tenant_id: str, db = Depends(get_db)):
    """Get cache statistics for tenant"""
    try:
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT
                COUNT(*) as total_entries,
                SUM(hit_count) as total_hits,
                AVG(hit_count) as avg_hits,
                COUNT(CASE WHEN invalidated_at IS NOT NULL THEN 1 END) as invalidated_count
            FROM semantic_cache_metadata
            WHERE tenant_id = %s
        """, (tenant_id,))
        
        stats = cursor.fetchone()
        
        collection_info = qdrant_client.get_collection(COLLECTION_NAME)
        
        return {
            "tenant_id": tenant_id,
            "total_entries": stats[0] or 0,
            "total_hits": stats[1] or 0,
            "avg_hits_per_entry": float(stats[2]) if stats[2] else 0,
            "invalidated_entries": stats[3] or 0,
            "qdrant_points": collection_info.points_count,
            "vector_size": VECTOR_SIZE
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Stats retrieval failed")

@app.get("/v1/cache/audit/{cache_id}")
def get_cache_audit_trail(cache_id: str, db = Depends(get_db)):
    """Get audit trail for cache entry (compliance)"""
    try:
        cursor = db.cursor()
        
        cursor.execute("""
            SELECT hit_reason, similarity_score, created_at, ledger_id
            FROM cache_hit_log
            WHERE cache_id = %s
            ORDER BY created_at DESC
            LIMIT 100
        """, (cache_id,))
        
        hits = []
        for row in cursor.fetchall():
            hits.append({
                "reason": row[0],
                "similarity_score": float(row[1]) if row[1] else None,
                "timestamp": row[2].isoformat(),
                "ledger_id": row[3]
            })
        
        return {
            "cache_id": cache_id,
            "audit_trail": hits
        }
    except Exception as e:
        logger.error(f"Failed to get audit trail: {e}")
        raise HTTPException(status_code=500, detail="Audit retrieval failed")

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "semantic-cache"}

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8088"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

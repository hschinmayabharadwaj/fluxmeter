"""
Ledgerline Semantic Cache Service using Qdrant
Implements triple-tag validation: Policy Version + Region + Provider
"""
import hashlib
import logging
import os
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_OPERATIONS = Counter(
    'ledgerline_cache_operations_total',
    'Total cache operations',
    ['operation', 'result']
)

CACHE_LATENCY = Histogram(
    'ledgerline_cache_latency_seconds',
    'Cache operation latency'
)

class CacheQuery(BaseModel):
    tenant_id: str
    prompt: str
    policy_version: str
    region: str
    provider: str
    similarity_threshold: float = 0.95

class CacheEntry(BaseModel):
    tenant_id: str
    prompt: str
    response: str
    policy_version: str
    region: str
    provider: str
    model: str
    ttl_hours: int = 24

app = FastAPI(
    title="Ledgerline Semantic Cache",
    description="Vector-based semantic cache with triple-tag validation",
    version="1.0.0"
)

# Initialize Qdrant client
qdrant_host = os.getenv("QDRANT_HOST", "localhost")
qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
client = QdrantClient(host=qdrant_host, port=qdrant_port)

COLLECTION_NAME = "ledgerline_cache"
VECTOR_SIZE = 384  # Using sentence-transformers default

def initialize_collection():
    """Initialize Qdrant collection if not exists"""
    try:
        collections = client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
            logger.info(f"Created collection: {COLLECTION_NAME}")
    except Exception as e:
        logger.error(f"Failed to initialize collection: {e}")

# Initialize on startup
initialize_collection()

def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding vector for text
    In production, use actual embedding model (sentence-transformers, OpenAI, etc.)
    """
    # Mock embedding - in production use:
    # from sentence_transformers import SentenceTransformer
    # model = SentenceTransformer('all-MiniLM-L6-v2')
    # return model.encode(text).tolist()
    
    # Simple hash-based mock for demo
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

@app.post("/v1/cache/query")
def query_cache(query: CacheQuery):
    """
    Query semantic cache with triple-tag validation
    Returns cached response if similarity > threshold AND all tags match
    """
    try:
        start_time = datetime.utcnow()
        
        # Generate embedding for query prompt
        query_vector = generate_embedding(query.prompt)
        
        # Create triple-tag filter
        tag_filter = create_triple_tag_filter(
            query.policy_version,
            query.region,
            query.provider
        )
        
        # Search in Qdrant
        results = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=tag_filter,
            limit=1,
            score_threshold=query.similarity_threshold
        )
        
        latency = (datetime.utcnow() - start_time).total_seconds()
        CACHE_LATENCY.observe(latency)
        
        if results:
            hit = results[0]
            
            # Check if entry is expired
            created_at = datetime.fromisoformat(hit.payload['created_at'])
            ttl_hours = hit.payload.get('ttl_hours', 24)
            expires_at = created_at + timedelta(hours=ttl_hours)
            
            if datetime.utcnow() > expires_at:
                # Entry expired
                CACHE_OPERATIONS.labels(operation='query', result='expired').inc()
                return {
                    "hit": False,
                    "reason": "expired",
                    "latency_ms": int(latency * 1000)
                }
            
            # Cache hit!
            CACHE_OPERATIONS.labels(operation='query', result='hit').inc()
            
            # Update hit count
            hit_count = hit.payload.get('hit_count', 0) + 1
            client.set_payload(
                collection_name=COLLECTION_NAME,
                payload={"hit_count": hit_count, "last_hit_at": datetime.utcnow().isoformat()},
                points=[hit.id]
            )
            
            logger.info(f"Cache HIT: {query.prompt[:50]}... (similarity: {hit.score:.3f})")
            
            return {
                "hit": True,
                "response": hit.payload['response'],
                "similarity": hit.score,
                "cache_id": str(hit.id),
                "hit_count": hit_count,
                "latency_ms": int(latency * 1000)
            }
        else:
            # Cache miss
            CACHE_OPERATIONS.labels(operation='query', result='miss').inc()
            logger.info(f"Cache MISS: {query.prompt[:50]}...")
            
            return {
                "hit": False,
                "reason": "no_match",
                "latency_ms": int(latency * 1000)
            }
            
    except Exception as e:
        logger.error(f"Cache query failed: {e}")
        CACHE_OPERATIONS.labels(operation='query', result='error').inc()
        raise HTTPException(status_code=500, detail="Cache query failed")

@app.post("/v1/cache/store")
def store_in_cache(entry: CacheEntry):
    """Store response in semantic cache with triple-tag"""
    try:
        # Generate embedding
        prompt_vector = generate_embedding(entry.prompt)
        
        # Create point
        point_id = hashlib.md5(
            f"{entry.tenant_id}:{entry.prompt}:{entry.policy_version}".encode()
        ).hexdigest()
        
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
                "created_at": datetime.utcnow().isoformat(),
                "hit_count": 0
            }
        )
        
        # Store in Qdrant
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )
        
        # Store metadata in PostgreSQL
        # (Implementation depends on your PostgreSQL setup)
        
        CACHE_OPERATIONS.labels(operation='store', result='success').inc()
        logger.info(f"Stored in cache: {entry.prompt[:50]}...")
        
        return {
            "cache_id": point_id,
            "expires_at": (datetime.utcnow() + timedelta(hours=entry.ttl_hours)).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to store in cache: {e}")
        CACHE_OPERATIONS.labels(operation='store', result='error').inc()
        raise HTTPException(status_code=500, detail="Cache store failed")

@app.get("/v1/cache/stats")
def get_cache_stats():
    """Get cache statistics"""
    try:
        collection_info = client.get_collection(COLLECTION_NAME)
        
        return {
            "total_entries": collection_info.points_count,
            "vector_size": collection_info.config.params.vectors.size,
            "collection_name": COLLECTION_NAME
        }
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Stats retrieval failed")

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

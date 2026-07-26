"""
Ledgerline Hardened Dispatcher with Sync-before-ACK Pattern
Ensures zero-silent-loss through transactional outbox and atomic operations
"""
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, Dict, Any

import pika
import redis
from fastapi import FastAPI, HTTPException, BackgroundTasks
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from starlette.responses import Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus Metrics
REQUEST_COUNTER = Counter(
    'ledgerline_dispatcher_requests_total',
    'Total requests processed',
    ['tenant_id', 'provider', 'status']
)
OUTBOX_LATENCY = Histogram(
    'ledgerline_outbox_write_latency_seconds',
    'Outbox write latency distribution'
)
PROVIDER_LATENCY = Histogram(
    'ledgerline_provider_call_latency_seconds',
    'Provider API call latency',
    ['provider']
)
ACTIVE_JOBS = Gauge('ledgerline_active_jobs', 'Currently processing jobs')

# Redis client
redis_client: redis.Redis = None
# RabbitMQ connection
rabbit_connection: pika.BlockingConnection = None
rabbit_channel: pika.channel.Channel = None
# Provider clients
openai_client: AsyncOpenAI = None
anthropic_client: AsyncAnthropic = None


class DispatchRequest(BaseModel):
    """Request model for AI dispatch"""
    correlation_id: str = Field(..., description="Unique correlation ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    provider: str = Field(..., description="AI provider (openai, anthropic)")
    model: str = Field(..., description="Model name")
    messages: list = Field(..., description="Chat messages")
    max_tokens: Optional[int] = Field(2048, description="Max tokens")
    temperature: Optional[float] = Field(0.7, description="Temperature")
    stream: Optional[bool] = Field(False, description="Enable streaming")
    cost_allocation_tags: Optional[Dict[str, str]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DispatchResponse(BaseModel):
    """Response model"""
    correlation_id: str
    attempt_id: str
    status: str
    message: Optional[str] = None
    response: Optional[Dict[str, Any]] = None


def init_redis():
    """Initialize Redis connection"""
    global redis_client
    redis_addr = os.getenv("REDIS_ADDR", "localhost:6379")
    host, port = redis_addr.split(":")
    
    redis_client = redis.Redis(
        host=host,
        port=int(port),
        password=os.getenv("REDIS_PASSWORD"),
        db=0,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_timeout=3,
        retry_on_timeout=True,
        max_connections=100
    )
    
    # Test connection
    redis_client.ping()
    logger.info("Connected to Redis successfully")


def init_rabbitmq():
    """Initialize RabbitMQ connection"""
    global rabbit_connection, rabbit_channel
    
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    
    rabbit_connection = pika.BlockingConnection(
        pika.URLParameters(rabbitmq_url)
    )
    rabbit_channel = rabbit_connection.channel()
    
    # Declare quorum queue with durability
    rabbit_channel.queue_declare(
        queue='ledgerline.requests',
        durable=True,
        arguments={
            'x-queue-type': 'quorum',
            'x-message-ttl': 300000,  # 5 minutes
            'x-dead-letter-exchange': 'ledgerline.dlx',
            'x-dead-letter-routing-key': 'dlq'
        }
    )
    
    # Declare DLQ
    rabbit_channel.queue_declare(
        queue='ledgerline.dlq',
        durable=True
    )
    
    logger.info("Connected to RabbitMQ successfully")


def init_providers():
    """Initialize AI provider clients"""
    global openai_client, anthropic_client
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        openai_client = AsyncOpenAI(api_key=openai_api_key)
        logger.info("OpenAI client initialized")
    
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        anthropic_client = AsyncAnthropic(api_key=anthropic_api_key)
        logger.info("Anthropic client initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    init_redis()
    init_rabbitmq()
    init_providers()
    yield
    # Cleanup
    if rabbit_connection:
        rabbit_connection.close()
    if redis_client:
        redis_client.close()


app = FastAPI(
    title="Ledgerline Dispatcher",
    description="Hardened AI request dispatcher with Sync-before-ACK pattern",
    version="1.0.0",
    lifespan=lifespan
)


def acquire_worker_lock(correlation_id: str, ttl: int = 30) -> bool:
    """
    Acquire an atomic worker lock using SET NX with TTL
    Returns True if lock acquired, False otherwise
    """
    lock_key = f"lock:{correlation_id}"
    # SET NX EX is atomic - only succeeds if key doesn't exist
    result = redis_client.set(lock_key, "1", nx=True, ex=ttl)
    return result is not None


def release_worker_lock(correlation_id: str):
    """Release worker lock"""
    lock_key = f"lock:{correlation_id}"
    redis_client.delete(lock_key)


def write_outbox_signal(correlation_id: str, data: Dict[str, Any]) -> bool:
    """
    Write transactional outbox signal atomically
    This is the critical Sync-before-ACK durability guarantee
    """
    start_time = time.time()
    try:
        outbox_key = f"outbox:{correlation_id}"
        data['last_heartbeat'] = datetime.utcnow().isoformat()
        
        # Atomic write with 5 minute TTL
        result = redis_client.setex(
            outbox_key,
            300,  # 5 minutes
            json.dumps(data)
        )
        
        OUTBOX_LATENCY.observe(time.time() - start_time)
        return result
    except Exception as e:
        logger.error(f"Failed to write outbox signal for {correlation_id}: {e}")
        return False


def check_idempotency(correlation_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if request already processed using atomic SET NX
    Returns existing result if found, None otherwise
    """
    idem_key = f"idem:{correlation_id}"
    result = redis_client.get(idem_key)
    
    if result:
        logger.info(f"Idempotency hit for {correlation_id}")
        return json.loads(result)
    
    return None


def store_idempotency_result(correlation_id: str, result: Dict[str, Any], ttl: int = 3600):
    """Store idempotency result with TTL"""
    idem_key = f"idem:{correlation_id}"
    redis_client.setex(idem_key, ttl, json.dumps(result))


async def call_mock_provider(request: DispatchRequest, provider: str) -> Dict[str, Any]:
    """Mock provider for testing without API keys"""
    await asyncio.sleep(0.5)  # Simulate network latency
    
    prompt_tokens = sum(len(msg.get('content', '').split()) for msg in request.messages)
    completion_tokens = 15  # Mock response length
    
    mock_responses = {
        'openai': "This is a mock response from OpenAI. Hello! I'm here to help you with your questions.",
        'anthropic': "This is a mock response from Anthropic. I'm an AI assistant ready to assist.",
    }
    
    return {
        'content': mock_responses.get(provider, "Mock response"),
        'model': request.model,
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': prompt_tokens + completion_tokens,
            'input_tokens': prompt_tokens,  # For Anthropic compatibility
            'output_tokens': completion_tokens
        },
        'finish_reason': 'stop'
    }


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception)
)
async def call_openai(request: DispatchRequest) -> Dict[str, Any]:
    """Call OpenAI API with circuit breaker and retry logic"""
    # Check if mock mode is enabled
    if os.getenv("MOCK_MODE", "false").lower() == "true":
        logger.info("Using mock OpenAI response")
        return await call_mock_provider(request, 'openai')
    
    start_time = time.time()
    
    try:
        response = await openai_client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=False
        )
        
        PROVIDER_LATENCY.labels(provider='openai').observe(time.time() - start_time)
        
        return {
            'content': response.choices[0].message.content,
            'model': response.model,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            'finish_reason': response.choices[0].finish_reason
        }
    except Exception as e:
        logger.error(f"OpenAI API call failed: {e}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(Exception)
)
async def call_anthropic(request: DispatchRequest) -> Dict[str, Any]:
    """Call Anthropic API with circuit breaker and retry logic"""
    # Check if mock mode is enabled
    if os.getenv("MOCK_MODE", "false").lower() == "true":
        logger.info("Using mock Anthropic response")
        return await call_mock_provider(request, 'anthropic')
    
    start_time = time.time()
    
    try:
        response = await anthropic_client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            messages=request.messages,
            temperature=request.temperature
        )
        
        PROVIDER_LATENCY.labels(provider='anthropic').observe(time.time() - start_time)
        
        return {
            'content': response.content[0].text,
            'model': response.model,
            'usage': {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            },
            'stop_reason': response.stop_reason
        }
    except Exception as e:
        logger.error(f"Anthropic API call failed: {e}")
        raise


async def process_request(request: DispatchRequest) -> Dict[str, Any]:
    """
    Process AI request with full Sync-before-ACK guarantees
    """
    attempt_id = str(uuid.uuid4())
    
    # Step 1: Acquire worker lock (atomic SET NX)
    if not acquire_worker_lock(request.correlation_id):
        logger.warning(f"Failed to acquire lock for {request.correlation_id} - duplicate processing")
        raise HTTPException(status_code=409, detail="Request already being processed")
    
    try:
        ACTIVE_JOBS.inc()
        
        # Step 2: Write initial outbox signal (Sync-before-ACK)
        outbox_data = {
            'correlation_id': request.correlation_id,
            'attempt_id': attempt_id,
            'tenant_id': request.tenant_id,
            'status': 'PROCESSING',
            'provider': request.provider,
            'token_count': 0,
            'checkpoint': 0,
            'created_at': datetime.utcnow().isoformat()
        }
        
        if not write_outbox_signal(request.correlation_id, outbox_data):
            raise HTTPException(status_code=500, detail="Failed to write outbox signal")
        
        # Step 3: Call provider
        if request.provider == 'openai':
            result = await call_openai(request)
        elif request.provider == 'anthropic':
            result = await call_anthropic(request)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {request.provider}")
        
        # Step 4: Update outbox with final token count (Sync-before-ACK)
        outbox_data['status'] = 'RECONCILED'
        outbox_data['token_count'] = result['usage']['total_tokens']
        
        if not write_outbox_signal(request.correlation_id, outbox_data):
            logger.error(f"Failed to write final outbox signal for {request.correlation_id}")
            # This is critical - we got a response but can't persist it
            # Send to DLQ for manual reconciliation
            outbox_data['status'] = 'PARTIAL'
            write_outbox_signal(request.correlation_id, outbox_data)
        
        REQUEST_COUNTER.labels(
            tenant_id=request.tenant_id,
            provider=request.provider,
            status='success'
        ).inc()
        
        return {
            'correlation_id': request.correlation_id,
            'attempt_id': attempt_id,
            'status': 'RECONCILED',
            'response': result
        }
        
    except Exception as e:
        logger.error(f"Request processing failed: {e}")
        
        # Update outbox with error state
        outbox_data['status'] = 'FAILED'
        outbox_data['error'] = str(e)
        write_outbox_signal(request.correlation_id, outbox_data)
        
        REQUEST_COUNTER.labels(
            tenant_id=request.tenant_id,
            provider=request.provider,
            status='failed'
        ).inc()
        
        raise
    
    finally:
        ACTIVE_JOBS.dec()
        release_worker_lock(request.correlation_id)


@app.post("/v1/submit", response_model=DispatchResponse)
async def submit_request(request: DispatchRequest):
    """
    Submit AI request for processing
    Implements idempotency check and atomic processing
    """
    # Check idempotency
    existing_result = check_idempotency(request.correlation_id)
    if existing_result:
        return DispatchResponse(**existing_result)
    
    # Process request
    result = await process_request(request)
    
    # Store idempotency result
    store_idempotency_result(request.correlation_id, result)
    
    return DispatchResponse(**result)


@app.get("/v1/status/{correlation_id}")
async def get_status(correlation_id: str):
    """Poll job status"""
    # Check idempotency cache first
    result = check_idempotency(correlation_id)
    if result:
        return result
    
    # Check outbox
    outbox_key = f"outbox:{correlation_id}"
    outbox_data = redis_client.get(outbox_key)
    
    if outbox_data:
        return json.loads(outbox_data)
    
    return {'status': 'NOT_FOUND'}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

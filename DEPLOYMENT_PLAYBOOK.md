# Semantic Cache Deployment Playbook

**Date:** July 24, 2026  
**Status:** Ready for Execution  
**Estimated Duration:** 2-3 hours (initial deployment) + 3 days (gradual rollout)

---

## Pre-Deployment Checklist (30 minutes before)

```bash
# 1. Verify database connectivity
psql -U ledgerline -d ledgerline -c "SELECT version();"

# 2. Verify Docker is running
docker ps

# 3. Verify network connectivity to Qdrant
curl http://qdrant:6333/health

# 4. Verify network connectivity to Redis
redis-cli -h redis ping

# 5. Check disk space (need at least 2GB free)
df -h

# 6. Check database backups
ls -lh backup_*.sql | tail -5
```

---

## PHASE 1: Schema Migration (30-45 minutes)

### Step 1.1: Create Pre-Migration Backup

```bash
# Create timestamped backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backup_ledgerline_${TIMESTAMP}.sql"

echo "Creating database backup: $BACKUP_FILE"
docker exec postgres pg_dump -U ledgerline ledgerline > "$BACKUP_FILE"

# Verify backup
if [ -s "$BACKUP_FILE" ]; then
    echo "✅ Backup created successfully: $(du -h $BACKUP_FILE | cut -f1)"
else
    echo "❌ Backup failed - ABORTING"
    exit 1
fi

# Keep backup in secure location
cp "$BACKUP_FILE" /backups/"$BACKUP_FILE"
echo "✅ Backup copied to /backups"
```

### Step 1.2: Execute Migration Script

```bash
# Set environment variables
export DB_HOST="postgres"
export DB_PORT="5432"
export DB_USER="ledgerline"
export DB_PASSWORD="ledgerline"
export DB_NAME="ledgerline"

# Run migration
cd /app
python3 backend/scripts/migrate_semantic_cache.py migrate

# Wait for completion
sleep 10

# Verify results
psql -U ledgerline -d ledgerline -c "
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'semantic_cache_metadata' 
    AND column_name IN ('candidate_email', 'job_id', 'model')
    ORDER BY column_name;
"

# Expected output: candidate_email, job_id, model
```

### Step 1.3: Verify Schema

```bash
# Check new columns
psql -U ledgerline -d ledgerline -c "\d semantic_cache_metadata" | grep -E "(candidate_email|job_id|model|created_by)"

# Check new table
psql -U ledgerline -d ledgerline -c "\d cache_hit_log"

# Check indexes
psql -U ledgerline -d ledgerline -c "\di cache_hit_log*"

# Count tables (should have cache_hit_log now)
psql -U ledgerline -d ledgerline -c "\dt" | grep cache
```

**Expected Output:**
```
 cache_id         | uuid        | 
 candidate_email  | character varying(255)
 job_id           | character varying(255)
 model            | character varying(100)
 estimated_tokens | integer
 created_by       | character varying(255)
```

---

## PHASE 2: Service Deployment (45-60 minutes)

### Step 2.1: Build Cache Service Image

```bash
# Build image
docker build -t ledgerline-cache:2.0 backend/services/python/cache/

# Verify build
docker images | grep ledgerline-cache
# Expected: ledgerline-cache       2.0     [IMAGE_ID]  [AGE]
```

### Step 2.2: Start Cache Service

```bash
# Update docker-compose.yml to include cache service
cat >> docker-compose.override.yml <<EOF
cache:
  image: ledgerline-cache:2.0
  container_name: ledgerline_cache
  ports:
    - "8088:8088"
  environment:
    - QDRANT_HOST=qdrant
    - QDRANT_PORT=6333
    - REDIS_ADDR=redis:6379
    - REDIS_PASSWORD=${REDIS_PASSWORD}
    - DATABASE_URL=postgresql://ledgerline:ledgerline@postgres:5432/ledgerline
    - PORT=8088
  depends_on:
    - postgres
    - redis
    - qdrant
  networks:
    - ledgerline-network
  restart: unless-stopped
EOF

# Start cache service
docker-compose up -d cache

# Wait for service to start
sleep 10

# Check if service is running
docker ps | grep ledgerline_cache
# Expected: Container is up
```

### Step 2.3: Verify Service Health

```bash
# Check service logs
docker logs ledgerline_cache | tail -20
# Expected: "Connected to Redis successfully"
#           "Connected to PostgreSQL successfully"
#           "Created collection: ledgerline_cache"

# Health check endpoint
curl -s http://localhost:8088/health | jq .
# Expected: {"status": "healthy", "service": "semantic-cache"}

# Test metrics endpoint
curl -s http://localhost:8088/metrics | head -20
# Expected: Prometheus format metrics

# Verify database connection
curl -s http://localhost:8088/v1/cache/stats/test-tenant | jq .
# Expected: {"tenant_id": "test-tenant", "total_entries": 0, ...}
```

### Step 2.4: Basic Functionality Test

```bash
# Test cache query endpoint (should miss, cache is empty)
curl -X POST http://localhost:8088/v1/cache/query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "correlation_id": "test_001",
    "prompt": "test prompt",
    "policy_version": "v1",
    "region": "us-east-1",
    "provider": "openai",
    "model": "gpt-4",
    "similarity_threshold": 0.95
  }' | jq .

# Expected: {"hit": false, "reason": "no_match", "latency_ms": ...}

# Test cache store endpoint
curl -X POST http://localhost:8088/v1/cache/store \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "prompt": "test prompt",
    "response": "test response",
    "policy_version": "v1",
    "region": "us-east-1",
    "provider": "openai",
    "model": "gpt-4",
    "estimated_tokens": 100,
    "ttl_hours": 24,
    "created_by": "deployment_test"
  }' | jq .

# Expected: {"cache_id": "uuid", "qdrant_point_id": "...", "expires_at": "..."}

# Test cache query again (should hit now)
curl -X POST http://localhost:8088/v1/cache/query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "correlation_id": "test_001",
    "prompt": "test prompt",
    "policy_version": "v1",
    "region": "us-east-1",
    "provider": "openai",
    "model": "gpt-4",
    "similarity_threshold": 0.95
  }' | jq .

# Expected: {"hit": true, "response": "test response", "cache_id": "...", ...}
```

---

## PHASE 3: Dispatcher Integration (30 minutes)

### Step 3.1: Update Dispatcher Configuration

```bash
# Update dispatcher environment
docker-compose exec dispatcher bash -c 'cat >> .env <<EOF
CACHE_SERVICE_URL=http://cache:8088
USE_SEMANTIC_CACHE=true
CACHE_TRAFFIC_PERCENTAGE=0  # Start at 0%, will increase gradually
CACHE_FALLBACK=true         # Fall through to provider if cache errors
EOF'

# Restart dispatcher
docker-compose restart dispatcher

# Verify dispatcher logs
docker logs dispatcher | tail -20
# Expected: "Cache service configured: http://cache:8088"
```

### Step 3.2: Verify Integration

```bash
# Test dispatcher with cache
curl -X POST http://localhost:8000/v1/submit \
  -H "Content-Type: application/json" \
  -d '{
    "correlation_id": "test_integration_001",
    "tenant_id": "test-tenant",
    "provider": "openai",
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 100
  }' | jq .

# Should work (uses provider, no cache hit yet since no entries)
```

---

## PHASE 4: 24-Hour Monitoring (1440 minutes)

### Step 4.1: Setup Prometheus Scrape Config

```yaml
# prometheus.yml - Add cache service
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'semantic-cache'
    static_configs:
      - targets: ['cache:8088']
    metrics_path: '/metrics'
```

### Step 4.2: Setup Grafana Dashboard

```bash
# Access Grafana at http://localhost:3001
# Login: admin/admin

# Create new dashboard: "Semantic Cache Monitoring"

# Add panels:

# Panel 1: Cache Hit Rate
PromQL: rate(ledgerline_cache_operations_total{result="hit"}[5m])

# Panel 2: Operations by Result
PromQL: sum(rate(ledgerline_cache_operations_total[5m])) by (result)

# Panel 3: Policy Mismatches
PromQL: increase(ledgerline_cache_policy_mismatches[1h])

# Panel 4: Consent Violations
PromQL: increase(ledgerline_cache_consent_violations[1h])

# Panel 5: Service Latency (P99)
PromQL: histogram_quantile(0.99, ledgerline_cache_latency_seconds)

# Panel 6: Total Cache Entries
PromQL: sum(ledgerline_active_crispe_templates) by (tenant_id)
```

### Step 4.3: Setup Alert Rules

```yaml
# alerts.yml - Add cache alerts
groups:
  - name: semantic_cache
    rules:
      # Alert if cache service errors spike
      - alert: CacheServiceError
        expr: rate(ledgerline_cache_operations_total{result="error"}[5m]) > 0.1
        for: 5m
        annotations:
          summary: "Cache service errors detected"
          
      # Alert if policy mismatches detected
      - alert: CachePolicyMismatch
        expr: increase(ledgerline_cache_policy_mismatches[1h]) > 0
        for: 5m
        annotations:
          summary: "Policy mismatches in cache"
          
      # Alert if consent violations detected
      - alert: CacheConsentViolation
        expr: increase(ledgerline_cache_consent_violations{consent_type="ai_screening"}[1h]) > 5
        for: 5m
        annotations:
          summary: "GDPR consent violations in cache"
```

### Step 4.4: Monitor Continuously

**Hourly Checks (Every hour for 24 hours):**

```bash
#!/bin/bash
# monitoring.sh - Run hourly

HOUR=$(date +%H)
echo "=== Hour $HOUR Monitoring ==="

# Check service health
echo "Service Health:"
curl -s http://localhost:8088/health | jq .

# Check error rate
echo "Error Rate (last 5 min):"
curl -s http://localhost:9090/api/v1/query \
  'rate(ledgerline_cache_operations_total{result="error"}[5m])' | jq .

# Check cache stats
echo "Cache Stats:"
curl -s http://localhost:8088/v1/cache/stats/production | jq .

# Check for policy mismatches
echo "Policy Mismatches (last 1h):"
curl -s http://localhost:9090/api/v1/query \
  'increase(ledgerline_cache_policy_mismatches[1h])' | jq .

# Check for consent violations
echo "Consent Violations (last 1h):"
curl -s http://localhost:9090/api/v1/query \
  'increase(ledgerline_cache_consent_violations[1h])' | jq .

# Check for rate limit blocks
echo "Rate Limit Blocks (last 1h):"
curl -s http://localhost:9090/api/v1/query \
  'increase(ledgerline_cache_rate_limit_blocks[1h])' | jq .

# Verify ledger entries created
echo "Ledger Entries with cache_hit:"
psql -U ledgerline -d ledgerline -c \
  "SELECT COUNT(*) as cache_hits FROM ledger WHERE request_type = 'cache_hit'"
```

**Daily Decision Points:**

```
Hour 0-4: Service Stabilization
  - No errors expected
  - Zero cache hits (cache is empty)
  - Proceed if: All metrics nominal
  Decision: PROCEED

Hour 4-8: Initial Operations
  - First cache entries appearing
  - Policy validations running
  - Proceed if: No GDPR violations, no policy mismatches
  Decision: PROCEED

Hour 8-16: Peak Traffic Period
  - Cache hit rate 10-20% (initial)
  - Ledger entries being created
  - Proceed if: All compliance checks passing, no errors > 0.1/s
  Decision: PROCEED

Hour 16-24: Stability Confirmation
  - All metrics stable
  - No anomalies detected
  - Proceed if: Ready for gradual rollout
  Decision: PROCEED TO GRADUAL ROLLOUT
```

---

## PHASE 5: Gradual Traffic Migration

### Step 5.1: 10% Traffic (Day 2, 09:00)

```bash
# Update dispatcher
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=10 && systemctl restart dispatcher'

# Verify in logs
docker logs dispatcher | grep "CACHE_TRAFFIC_PERCENTAGE"

# Monitor for 1 hour
sleep 3600

# Check metrics
curl -s http://localhost:9090/api/v1/query \
  'rate(ledgerline_cache_operations_total{result="hit"}[5m])' | jq .
# Expected: Low hit rate (cache still warming up)

# Decision checkpoint
echo "10% Traffic - Decision Point:"
echo "1. Any errors? $(curl -s http://localhost:9090/api/v1/query 'rate(ledgerline_cache_operations_total{result=\"error\"}[5m])' | jq .value)"
echo "2. Policy mismatches? $(curl -s http://localhost:9090/api/v1/query 'increase(ledgerline_cache_policy_mismatches[1h])' | jq .value)"
echo "3. Consent violations? $(curl -s http://localhost:9090/api/v1/query 'increase(ledgerline_cache_consent_violations[1h])' | jq .value)"
echo ""
echo "Proceed to 25%? (yes/no)"
```

### Step 5.2: 25% Traffic (Day 2, 14:00)

```bash
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=25'
docker-compose restart dispatcher
sleep 7200  # 2-hour observation period

# Similar decision checkpoint
```

### Step 5.3: 50% Traffic (Day 3, 09:00)

```bash
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=50'
docker-compose restart dispatcher
sleep 14400  # 4-hour observation period

# Check cost savings appearing
echo "Estimated cost savings:"
psql -U ledgerline -d ledgerline -c \
  "SELECT COUNT(*) * 0 as cost_saved FROM ledger WHERE request_type = 'cache_hit'"
```

### Step 5.4: 100% Traffic (Day 3, 14:00)

```bash
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=100'
docker-compose restart dispatcher

# Monitor for 8+ hours
sleep 28800

# Final validation
echo "=== DEPLOYMENT COMPLETE ==="
echo "Final Metrics:"
curl -s http://localhost:8088/v1/cache/stats/production | jq .
```

---

## Rollback Procedure (If Issues Detected)

### Immediate Rollback (< 5 minutes)

```bash
# 1. Disable cache traffic immediately
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=0'
docker-compose restart dispatcher

# 2. Verify traffic routing to provider directly
curl http://localhost:8000/v1/submit [test payload]

# 3. Alert ops team
echo "🔴 CACHE ROLLBACK INITIATED"
slack-send "#oncall-devops" "Cache service disabled due to issues. Traffic routed to providers."
```

### Investigation

```bash
# 1. Check service logs
docker logs ledgerline_cache | tail -100 > cache_logs.txt

# 2. Check Prometheus metrics
curl -s 'http://localhost:9090/api/v1/query?query=ledgerline_cache_operations_total' > metrics.json

# 3. Check database queries
psql -U ledgerline -d ledgerline -c "SELECT * FROM cache_hit_log ORDER BY created_at DESC LIMIT 20" > cache_hits.txt

# 4. Collect diagnostics
tar czf diagnostics_$(date +%s).tar.gz cache_logs.txt metrics.json cache_hits.txt
```

### Resolution & Restart

```bash
# 1. Fix issue (code deployment, config change, etc.)
docker build -t ledgerline-cache:2.1 backend/services/python/cache/
docker-compose up -d cache

# 2. Re-enable at previous traffic level
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=10'
docker-compose restart dispatcher

# 3. Resume gradual migration
```

---

## Deployment Completion

### Final Sign-Off Checklist

- [ ] Schema migration successful
- [ ] Cache service deployed and healthy
- [ ] 24-hour monitoring completed
- [ ] Gradual traffic migration 100% complete
- [ ] No GDPR compliance violations
- [ ] Ledger entries accurate
- [ ] Performance metrics acceptable
- [ ] Cost savings quantified
- [ ] All alerts configured
- [ ] On-call team trained

### Post-Deployment Steps

1. **Update Documentation**
   - [ ] Add cache service to runbooks
   - [ ] Update architecture diagrams
   - [ ] Document cache invalidation procedures

2. **Team Communication**
   - [ ] Send deployment summary to stakeholders
   - [ ] Schedule knowledge transfer session
   - [ ] Update team wiki/documentation

3. **Continuous Improvement**
   - [ ] Schedule cache performance review (1 week)
   - [ ] Plan Phase 2 enhancements
   - [ ] Gather team feedback

---

**Deployment Runbook Status:** ✅ Ready for Execution  
**Last Updated:** July 23, 2026 22:43 UTC+5:30

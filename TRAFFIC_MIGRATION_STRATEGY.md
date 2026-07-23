# Gradual Traffic Migration Strategy (10% → 100%)

**Date:** July 24, 2026  
**Status:** Ready for Execution  
**Duration:** 3-4 days (4 phases over 3 days)

---

## Overview

Traffic migration follows a staged approach to minimize risk and validate compliance at each phase:

```
Day 1:  Baseline (0%)  →  Phase 1: 10%
Day 2:  Phase 2: 25%   →  Phase 3: 50%
Day 3:  Phase 4: 100%  →  Validation
```

Each phase includes:
- ✅ Decision gate with go/no-go criteria
- ✅ 1-4 hour observation period
- ✅ Compliance validation
- ✅ Rollback procedure if needed

---

## PHASE 1: 10% Traffic (24 hours after initial deployment)

### Scheduling

| Metric | Value |
|--------|-------|
| **Start Time** | Day 2, 09:00 UTC |
| **Duration** | 1+ hour observation |
| **Traffic %** | 10% of all requests |
| **Expected Volume** | ~10 requests/second (if baseline is 100 req/s) |

### Pre-Phase Validation

```bash
# Verify cache service health before phase 1
curl http://localhost:8088/health
# Expected: {"status": "healthy", "service": "semantic-cache"}

# Verify no cascading errors
curl 'http://localhost:9090/api/v1/query?query=rate(ledgerline_cache_operations_total{result="error"}[5m])'
# Expected: < 0.01 errors/sec

# Verify database connectivity
psql -U ledgerline -d ledgerline -c "SELECT COUNT(*) FROM cache_hit_log"
# Expected: Query succeeds

# Verify 24-hour monitoring passed
echo "Review monitoring logs for 24-hour period"
# Expected: No critical issues
```

### Phase 1 Configuration

```bash
# Update dispatcher configuration
cat > /config/dispatcher.env <<EOF
CACHE_SERVICE_URL=http://cache:8088
USE_SEMANTIC_CACHE=true
CACHE_TRAFFIC_PERCENTAGE=10
CACHE_FALLBACK=true
CACHE_TIMEOUT_MS=5000
EOF

# Apply configuration
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=10'
docker-compose restart dispatcher

# Verify in logs
sleep 5
docker logs dispatcher | grep "CACHE_TRAFFIC_PERCENTAGE" | tail -1
# Expected: CACHE_TRAFFIC_PERCENTAGE=10
```

### Phase 1 Observation (1+ hour)

```bash
#!/bin/bash
# Phase 1 observation script

echo "=== PHASE 1: 10% Traffic Observation ==="
echo "Start time: $(date)"
echo ""

# Observation period: 1 hour
OBSERVATION_SECONDS=3600
SAMPLE_INTERVAL=60

for i in $(seq 0 $((OBSERVATION_SECONDS / SAMPLE_INTERVAL))); do
  ELAPSED=$((i * SAMPLE_INTERVAL))
  MIN=$((ELAPSED / 60))
  
  echo "[$MIN min] Checking metrics..."
  
  # 1. Check error rate
  ERROR_RATE=$(curl -s http://localhost:9090/api/v1/query?query='rate(ledgerline_cache_operations_total{result="error"}[5m])' | jq '.data.result[0].value[1]' 2>/dev/null)
  
  # 2. Check hit rate
  HIT_RATE=$(curl -s http://localhost:9090/api/v1/query?query='rate(ledgerline_cache_operations_total{result="hit"}[5m])' | jq '.data.result[0].value[1]' 2>/dev/null)
  
  # 3. Check cache hits recorded
  CACHE_HITS=$(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE created_at > NOW() - INTERVAL '5 minutes'")
  
  # 4. Check ledger entries
  LEDGER_ENTRIES=$(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM ledger WHERE request_type = 'cache_hit' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  # 5. Check compliance events
  VIOLATIONS=$(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'consent_withdrawn' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  # 6. Check policy mismatches
  POLICY_MISMATCHES=$(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'policy_mismatch' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  echo "  Error rate: $ERROR_RATE errors/sec"
  echo "  Hit rate: $HIT_RATE hits/sec"
  echo "  Cache hits (5m): $CACHE_HITS"
  echo "  Ledger entries (5m): $LEDGER_ENTRIES"
  echo "  Violations (5m): $VIOLATIONS"
  echo "  Policy mismatches (5m): $POLICY_MISMATCHES"
  
  # Check for critical failures
  if [ "$(echo "$ERROR_RATE > 0.1" | bc)" -eq 1 ]; then
    echo "  ❌ ERROR RATE TOO HIGH - ABORT PHASE 1"
    exit 1
  fi
  
  if [ "$VIOLATIONS" -gt 0 ]; then
    echo "  ❌ GDPR VIOLATION DETECTED - ABORT PHASE 1"
    exit 1
  fi
  
  if [ "$POLICY_MISMATCHES" -gt 0 ]; then
    echo "  ❌ POLICY MISMATCH DETECTED - ABORT PHASE 1"
    exit 1
  fi
  
  sleep $SAMPLE_INTERVAL
done

echo ""
echo "=== PHASE 1 OBSERVATION COMPLETE ==="
```

### Phase 1 Decision Gate

```
✅ PROCEED TO PHASE 2 if:
  - Error rate < 0.1/sec ✓
  - Zero GDPR violations ✓
  - Zero policy mismatches ✓
  - Cache hits being recorded ✓
  - Ledger entries created ✓
  - Service latency < 100ms P99 ✓

❌ ROLLBACK to 0% if:
  - Error rate > 0.1/sec
  - Any GDPR violations
  - Any policy mismatches
  - Ledger recording failures
  - Service degradation
```

**Phase 1 Sign-Off:**
```
Date: ___________
Observer: ___________
Status: [ ] PASS → Proceed to Phase 2
         [ ] FAIL → Rollback & Investigate
```

---

## PHASE 2: 25% Traffic (5-6 hours after Phase 1)

### Scheduling

| Metric | Value |
|--------|-------|
| **Start Time** | Day 2, 14:00 UTC (5 hours after Phase 1 start) |
| **Duration** | 2+ hours observation |
| **Traffic %** | 25% of all requests |
| **Expected Volume** | ~25 requests/second (if baseline is 100 req/s) |

### Phase 2 Configuration

```bash
# Update traffic percentage
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=25'
docker-compose restart dispatcher

# Log the change
echo "Phase 2 started at $(date): 25% traffic" >> deployment.log
```

### Phase 2 Observation (2+ hours)

```bash
# Similar to Phase 1, but with 2+ hour observation
# Expected outcomes:
# - Cache warming effect visible (hit rate starting to increase)
# - Cost savings appearing in metrics
# - Compliance checks all passing
# - Latency impact minimal

# Key metric to watch: Hit rate progression
# 0-30 min: 0-5% hit rate (still warming)
# 30-60 min: 5-15% hit rate (warming up)
# 60-120 min: 15-25% hit rate (warmed)
```

### Phase 2 Validation

```sql
-- Verify cache is warming
SELECT 
  DATE_TRUNC('hour', created_at) as hour,
  SUM(CASE WHEN hit_reason = 'valid_hit' THEN 1 ELSE 0 END) as valid_hits,
  SUM(CASE WHEN hit_reason = 'no_match' THEN 1 ELSE 0 END) as misses,
  ROUND(100.0 * SUM(CASE WHEN hit_reason = 'valid_hit' THEN 1 ELSE 0 END) / 
        COUNT(*), 2) as hit_rate_pct
FROM cache_hit_log
WHERE created_at > NOW() - INTERVAL '3 hours'
GROUP BY DATE_TRUNC('hour', created_at)
ORDER BY hour DESC;

-- Expected: Hit rate gradually increasing over the 2 hours
```

### Phase 2 Decision Gate

```
✅ PROCEED TO PHASE 3 if:
  - All Phase 1 criteria still met ✓
  - Cache hit rate > 10% ✓
  - Cost savings visible ✓
  - Compliance checks passing ✓
  - Ledger accuracy verified ✓

⚠️ HOLD at 25% if:
  - Hit rate not increasing as expected
  - Slight issues detected (fixable during hold)

❌ ROLLBACK if:
  - Critical failures persist
  - Compliance violations detected
  - Service degradation significant
```

**Phase 2 Sign-Off:**
```
Date: ___________
Observer: ___________
Hit Rate Achieved: _____%
Status: [ ] PASS → Proceed to Phase 3
         [ ] HOLD → Investigate at 25%
         [ ] FAIL → Rollback & Investigate
```

---

## PHASE 3: 50% Traffic (9-10 hours after Phase 1)

### Scheduling

| Metric | Value |
|--------|-------|
| **Start Time** | Day 3, 09:00 UTC |
| **Duration** | 4+ hours observation |
| **Traffic %** | 50% of all requests |
| **Expected Volume** | ~50 requests/second |

### Phase 3 Configuration

```bash
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=50'
docker-compose restart dispatcher
```

### Phase 3 Metrics Tracking

```bash
#!/bin/bash
# Phase 3 detailed metrics tracking

echo "=== PHASE 3: 50% Traffic - Full Metrics Report ==="

# 1. Cache efficiency
echo "1. CACHE EFFICIENCY:"
psql -U ledgerline -d ledgerline -c "
  SELECT 
    SUM(CASE WHEN hit_reason = 'valid_hit' THEN 1 ELSE 0 END) as valid_hits,
    SUM(CASE WHEN hit_reason NOT IN ('valid_hit', 'policy_mismatch', 'consent_withdrawn') THEN 1 ELSE 0 END) as other_misses,
    SUM(CASE WHEN hit_reason = 'policy_mismatch' THEN 1 ELSE 0 END) as policy_blocks,
    SUM(CASE WHEN hit_reason = 'consent_withdrawn' THEN 1 ELSE 0 END) as consent_blocks,
    COUNT(*) as total
  FROM cache_hit_log
  WHERE created_at > NOW() - INTERVAL '1 hour';
"

# 2. Performance improvement
echo "2. PERFORMANCE IMPROVEMENT:"
echo "Cache query latency (P99): $(curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.99,ledgerline_cache_latency_seconds)' | jq '.data.result[0].value[1]')s"
echo "API latency without cache would be: ~0.5-1.0s"
echo "Savings per cache hit: ~450-950ms"

# 3. Cost analysis
echo "3. ESTIMATED COST SAVINGS:"
CACHE_HITS=$(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM ledger WHERE request_type = 'cache_hit' AND created_at > NOW() - INTERVAL '1 hour'")
echo "Cache hits (1h): $CACHE_HITS"
echo "Cost per API call: \$0.00002"
echo "Estimated savings (1h): \$$(echo "$CACHE_HITS * 0.00002" | bc)"

# 4. Compliance verification
echo "4. COMPLIANCE STATUS:"
echo "GDPR violations (1h): $(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'consent_withdrawn' AND created_at > NOW() - INTERVAL '1 hour'")"
echo "Policy mismatches (1h): $(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'policy_mismatch' AND created_at > NOW() - INTERVAL '1 hour'")"
echo "Rate limit blocks (1h): $(psql -U ledgerline -d ledgerline -t -c "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'rate_limit_exceeded' AND created_at > NOW() - INTERVAL '1 hour'")"
```

### Phase 3 Decision Gate

```
✅ PROCEED TO PHASE 4 (100%) if:
  - Hit rate stable at 20-30% ✓
  - Cost savings quantified and acceptable ✓
  - Zero GDPR/compliance violations ✓
  - Performance improvement confirmed ✓
  - Ledger accuracy verified ✓
  - All systems stable under 50% load ✓

⚠️ HOLD at 50% if:
  - Issues detected but manageable
  - Need more data before full rollout

❌ ROLLBACK if:
  - Critical failures
  - Compliance violations
  - Cannot proceed safely
```

**Phase 3 Sign-Off:**
```
Date: ___________
Observer: ___________
Hit Rate: _____%
Cost Savings (24h est.): $________
Status: [ ] PASS → Proceed to Phase 4
         [ ] HOLD → Investigate at 50%
         [ ] FAIL → Rollback & Investigate
```

---

## PHASE 4: 100% Traffic (22-23 hours after Phase 1)

### Scheduling

| Metric | Value |
|--------|-------|
| **Start Time** | Day 3, 14:00 UTC |
| **Duration** | 8+ hours observation + 1 week monitoring |
| **Traffic %** | 100% of all requests |
| **Expected Volume** | Full production traffic |

### Phase 4 Configuration

```bash
docker-compose exec dispatcher bash -c 'export CACHE_TRAFFIC_PERCENTAGE=100'
docker-compose restart dispatcher

# Verify 100% traffic
sleep 10
docker logs dispatcher | grep "CACHE_TRAFFIC_PERCENTAGE" | tail -1
# Expected: CACHE_TRAFFIC_PERCENTAGE=100
```

### Phase 4 Monitoring (8+ hours)

```bash
#!/bin/bash
# Phase 4 continuous monitoring

echo "=== PHASE 4: 100% Traffic - Production Monitoring ==="
echo "Deployment Time: $(date)"
echo ""

# Monitor for 8 hours
MONITORING_DURATION=$((8 * 3600))
SAMPLE_INTERVAL=300

ERRORS=0
VIOLATIONS=0
MISMATCHES=0

for i in $(seq 0 $((MONITORING_DURATION / SAMPLE_INTERVAL))); do
  ELAPSED=$((i * SAMPLE_INTERVAL))
  MIN=$((ELAPSED / 60))
  
  # Check critical metrics
  ERROR_COUNT=$(psql -U ledgerline -d ledgerline -t -c \
    "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'error' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  VIOLATION_COUNT=$(psql -U ledgerline -d ledgerline -t -c \
    "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'consent_withdrawn' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  MISMATCH_COUNT=$(psql -U ledgerline -d ledgerline -t -c \
    "SELECT COUNT(*) FROM cache_hit_log WHERE hit_reason = 'policy_mismatch' AND created_at > NOW() - INTERVAL '5 minutes'")
  
  TOTAL_VIOLATIONS=$((VIOLATIONS + VIOLATION_COUNT))
  TOTAL_MISMATCHES=$((MISMATCHES + MISMATCH_COUNT))
  
  echo "[$MIN min] Errors: $ERROR_COUNT | Violations: $VIOLATION_COUNT | Mismatches: $MISMATCH_COUNT"
  
  # Critical checks
  if [ "$ERROR_COUNT" -gt 100 ]; then
    echo "❌ ERROR SPIKE DETECTED - ABORT PHASE 4"
    exit 1
  fi
  
  if [ "$TOTAL_VIOLATIONS" -gt 0 ]; then
    echo "❌ GDPR VIOLATION DETECTED - ABORT PHASE 4"
    exit 1
  fi
  
  sleep $SAMPLE_INTERVAL
done

echo ""
echo "=== PHASE 4: 8-HOUR OBSERVATION COMPLETE ==="
echo "Result: All checks passed - Production deployment successful"
```

### Phase 4 Final Validation (Post-Deployment)

```bash
#!/bin/bash
# Final validation after Phase 4

echo "=== POST-DEPLOYMENT FINAL VALIDATION ==="

# 1. Verify cache hit rate stabilized
echo "1. Cache Hit Rate (Last 24h):"
psql -U ledgerline -d ledgerline -c "
  SELECT 
    ROUND(100.0 * SUM(CASE WHEN hit_reason = 'valid_hit' THEN 1 ELSE 0 END) / COUNT(*), 2) as hit_rate_pct
  FROM cache_hit_log
  WHERE created_at > NOW() - INTERVAL '24 hours';
"

# 2. Verify compliance
echo ""
echo "2. Compliance Status (Last 24h):"
psql -U ledgerline -d ledgerline -c "
  SELECT 
    SUM(CASE WHEN hit_reason = 'consent_withdrawn' THEN 1 ELSE 0 END) as gdpr_violations,
    SUM(CASE WHEN hit_reason = 'policy_mismatch' THEN 1 ELSE 0 END) as policy_mismatches,
    SUM(CASE WHEN hit_reason = 'rate_limit_exceeded' THEN 1 ELSE 0 END) as rate_limit_blocks
  FROM cache_hit_log
  WHERE created_at > NOW() - INTERVAL '24 hours';
"

# 3. Verify billing accuracy
echo ""
echo "3. Billing Accuracy:"
psql -U ledgerline -d ledgerline -c "
  SELECT 
    COUNT(*) as total_cache_hits,
    SUM(token_count) as total_tokens_charged
  FROM ledger
  WHERE request_type = 'cache_hit'
    AND created_at > NOW() - INTERVAL '24 hours';
"

# 4. Cost savings summary
echo ""
echo "4. Cost Savings Analysis:"
CACHE_HITS=$(psql -U ledgerline -d ledgerline -t -c \
  "SELECT COUNT(*) FROM ledger WHERE request_type = 'cache_hit' AND created_at > NOW() - INTERVAL '24 hours'")
echo "Cache hits (24h): $CACHE_HITS"
echo "Cost per hit saved: \$0.00002"
echo "Daily savings: \$$(echo "$CACHE_HITS * 0.00002" | bc)"
echo "Projected monthly savings: \$$(echo "$CACHE_HITS * 0.00002 * 30" | bc)"

echo ""
echo "=== FINAL VALIDATION COMPLETE ==="
```

### Phase 4 Decision Gate

```
✅ DEPLOYMENT SUCCESSFUL if:
  - Hit rate stable at 20-30% ✓
  - Zero GDPR violations in 24h ✓
  - Zero policy mismatches in 24h ✓
  - Ledger accuracy 100% ✓
  - No performance degradation ✓
  - Cost savings quantified ✓
  - All monitoring stable ✓

🎉 PRODUCTION DEPLOYMENT COMPLETE
```

**Phase 4 Sign-Off:**
```
Date: ___________
Observers: ___________
Final Hit Rate: _____%
Total Cost Savings (24h): $________
Monthly Projection: $________
Status: ✅ DEPLOYMENT SUCCESSFUL

Deployment Team Lead: ___________
Compliance Officer: ___________
Operations Lead: ___________

Date: ___________
```

---

## Rollback Decision Tree

```
Issue Detected
    ↓
Severity Check
    ├─→ CRITICAL (GDPR violation, Error rate > 1/sec)
    │   └─→ IMMEDIATE ROLLBACK (< 5 min)
    │   └─→ INVESTIGATE ROOT CAUSE
    │
    ├─→ HIGH (Error rate 0.1-1/sec)
    │   └─→ ROLLBACK TO LAST STABLE PHASE
    │   └─→ INVESTIGATE & FIX
    │   └─→ RETRY CURRENT PHASE
    │
    ├─→ MEDIUM (Partial failures, fixable)
    │   └─→ HOLD CURRENT PHASE
    │   └─→ INVESTIGATE & FIX
    │   └─→ RETRY IN 1 HOUR
    │
    └─→ LOW (Warnings, no impact)
        └─→ CONTINUE MONITORING
        └─→ DOCUMENT FOR REVIEW
```

---

## Success Metrics

| Metric | Target | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------|--------|---------|---------|---------|---------|
| Hit Rate | 20-30% | 0-5% | 5-15% | 15-25% | 20-30% |
| Error Rate | < 0.01/s | < 0.01/s | < 0.01/s | < 0.01/s | < 0.01/s |
| GDPR Violations | 0 | 0 | 0 | 0 | 0 |
| Policy Mismatches | 0 | 0 | 0 | 0 | 0 |
| Ledger Accuracy | 100% | 100% | 100% | 100% | 100% |
| Latency P99 | < 100ms | < 100ms | < 100ms | < 100ms | < 100ms |

---

## Timeline Summary

```
Day 1 (24h monitoring)
├─ Baseline deployment
├─ Service health verification
└─ 24-hour monitoring

Day 2 (Phases 1 & 2)
├─ 09:00 - Phase 1 start (10% traffic)
├─ 10:00 - Phase 1 decision gate
├─ 14:00 - Phase 2 start (25% traffic)
└─ 16:00 - Phase 2 decision gate

Day 3 (Phases 3 & 4)
├─ 09:00 - Phase 3 start (50% traffic)
├─ 13:00 - Phase 3 decision gate
├─ 14:00 - Phase 4 start (100% traffic)
└─ 22:00 - Phase 4 validation complete

Day 4+
├─ Week 1: Continuous monitoring
├─ Week 2: Performance review
└─ Month 1: Retrospective & optimization
```

---

**Traffic Migration Strategy Status:** ✅ Ready for Execution  
**Last Updated:** July 23, 2026 22:43 UTC+5:30

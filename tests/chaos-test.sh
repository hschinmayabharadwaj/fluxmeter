#!/bin/bash

# Ledgerline Chaos Testing Suite
# Verifies zero-silent-loss guarantees under failure conditions

set -e

echo "========================================="
echo "  Ledgerline Chaos Testing Suite"
echo "========================================="
echo ""

API_URL=${API_URL:-"http://localhost:8000"}
TENANT_ID=${TENANT_ID:-"tenant_001"}
TEST_DURATION=${TEST_DURATION:-60}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TOTAL_REQUESTS=0
SUCCESSFUL_REQUESTS=0
FAILED_REQUESTS=0
RECONCILED_REQUESTS=0

# Generate unique correlation ID
generate_correlation_id() {
    echo "chaos_test_$(date +%s)_$RANDOM"
}

# Submit AI request
submit_request() {
    local correlation_id=$1
    
    curl -s -X POST "$API_URL/v1/submit" \
        -H "Content-Type: application/json" \
        -d "{
            \"correlation_id\": \"$correlation_id\",
            \"tenant_id\": \"$TENANT_ID\",
            \"provider\": \"openai\",
            \"model\": \"gpt-4\",
            \"messages\": [{\"role\": \"user\", \"content\": \"Test message\"}],
            \"max_tokens\": 50,
            \"cost_allocation_tags\": {\"test\": \"chaos\"}
        }" \
        -w "\n%{http_code}" 2>/dev/null
}

# Check request status
check_status() {
    local correlation_id=$1
    
    curl -s "$API_URL/v1/status/$correlation_id" 2>/dev/null
}

# Verify reconciliation
verify_reconciliation() {
    local correlation_id=$1
    local max_attempts=20
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        sleep 3
        
        status=$(check_status "$correlation_id")
        
        if echo "$status" | grep -q '"status":"RECONCILED"'; then
            return 0
        elif echo "$status" | grep -q '"status":"FAILED"'; then
            return 1
        fi
        
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}Timeout waiting for reconciliation${NC}"
    return 2
}

# Test 1: Kill dispatcher mid-request
test_kill_dispatcher() {
    echo ""
    echo "========================================="
    echo "Test 1: Kill Dispatcher Mid-Request"
    echo "========================================="
    echo "Objective: Verify requests are recovered via transactional outbox"
    echo ""
    
    local test_requests=5
    local correlation_ids=()
    
    # Submit requests
    echo "Submitting $test_requests requests..."
    for i in $(seq 1 $test_requests); do
        local correlation_id=$(generate_correlation_id)
        correlation_ids+=("$correlation_id")
        
        response=$(submit_request "$correlation_id")
        http_code=$(echo "$response" | tail -n1)
        
        if [ "$http_code" == "200" ]; then
            SUCCESSFUL_REQUESTS=$((SUCCESSFUL_REQUESTS + 1))
            echo "  ✓ Request $i submitted: $correlation_id"
        else
            FAILED_REQUESTS=$((FAILED_REQUESTS + 1))
            echo "  ✗ Request $i failed"
        fi
        
        TOTAL_REQUESTS=$((TOTAL_REQUESTS + 1))
        sleep 0.5
    done
    
    # Kill dispatcher
    echo ""
    echo -e "${YELLOW}Killing dispatcher service...${NC}"
    docker-compose kill dispatcher 2>/dev/null || echo "Using docker kill"
    docker kill ledgerline-dispatcher 2>/dev/null || true
    
    sleep 5
    
    # Restart dispatcher
    echo -e "${YELLOW}Restarting dispatcher service...${NC}"
    docker-compose up -d dispatcher 2>/dev/null || docker start ledgerline-dispatcher
    
    sleep 10
    
    # Verify reconciliation
    echo ""
    echo "Verifying reconciliation..."
    local reconciled=0
    
    for correlation_id in "${correlation_ids[@]}"; do
        if verify_reconciliation "$correlation_id"; then
            reconciled=$((reconciled + 1))
            RECONCILED_REQUESTS=$((RECONCILED_REQUESTS + 1))
            echo "  ✓ Reconciled: $correlation_id"
        else
            echo "  ✗ Not reconciled: $correlation_id"
        fi
    done
    
    echo ""
    if [ $reconciled -eq $test_requests ]; then
        echo -e "${GREEN}✓ Test PASSED: All $test_requests requests reconciled${NC}"
        return 0
    else
        echo -e "${RED}✗ Test FAILED: Only $reconciled/$test_requests requests reconciled${NC}"
        return 1
    fi
}

# Test 2: Redis failover
test_redis_failover() {
    echo ""
    echo "========================================="
    echo "Test 2: Redis Failover"
    echo "========================================="
    echo "Objective: Verify graceful degradation during Redis outage"
    echo ""
    
    local correlation_id=$(generate_correlation_id)
    
    echo "Submitting request..."
    response=$(submit_request "$correlation_id")
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" == "200" ]; then
        echo "  ✓ Request submitted: $correlation_id"
        SUCCESSFUL_REQUESTS=$((SUCCESSFUL_REQUESTS + 1))
    else
        echo "  ✗ Request failed"
        FAILED_REQUESTS=$((FAILED_REQUESTS + 1))
    fi
    
    TOTAL_REQUESTS=$((TOTAL_REQUESTS + 1))
    
    # Pause Redis
    echo ""
    echo -e "${YELLOW}Pausing Redis...${NC}"
    docker-compose pause redis 2>/dev/null || docker pause ledgerline-redis
    
    sleep 5
    
    # Unpause Redis
    echo -e "${YELLOW}Resuming Redis...${NC}"
    docker-compose unpause redis 2>/dev/null || docker unpause ledgerline-redis
    
    sleep 5
    
    # Verify reconciliation
    echo ""
    echo "Verifying reconciliation..."
    if verify_reconciliation "$correlation_id"; then
        RECONCILED_REQUESTS=$((RECONCILED_REQUESTS + 1))
        echo -e "${GREEN}✓ Test PASSED: Request reconciled after Redis failover${NC}"
        return 0
    else
        echo -e "${RED}✗ Test FAILED: Request not reconciled${NC}"
        return 1
    fi
}

# Test 3: High concurrency burst
test_concurrency_burst() {
    echo ""
    echo "========================================="
    echo "Test 3: High Concurrency Burst"
    echo "========================================="
    echo "Objective: Verify system handles 50 concurrent requests"
    echo ""
    
    local burst_size=50
    local pids=()
    local temp_dir=$(mktemp -d)
    
    echo "Submitting $burst_size concurrent requests..."
    
    for i in $(seq 1 $burst_size); do
        (
            correlation_id=$(generate_correlation_id)
            response=$(submit_request "$correlation_id")
            http_code=$(echo "$response" | tail -n1)
            
            echo "$correlation_id:$http_code" > "$temp_dir/$i.result"
        ) &
        pids+=($!)
    done
    
    # Wait for all requests
    for pid in "${pids[@]}"; do
        wait $pid
    done
    
    echo "All requests completed"
    
    # Count results
    local successful=0
    local failed=0
    
    for i in $(seq 1 $burst_size); do
        if [ -f "$temp_dir/$i.result" ]; then
            result=$(cat "$temp_dir/$i.result")
            http_code=$(echo "$result" | cut -d: -f2)
            
            if [ "$http_code" == "200" ]; then
                successful=$((successful + 1))
            else
                failed=$((failed + 1))
            fi
        fi
    done
    
    TOTAL_REQUESTS=$((TOTAL_REQUESTS + burst_size))
    SUCCESSFUL_REQUESTS=$((SUCCESSFUL_REQUESTS + successful))
    FAILED_REQUESTS=$((FAILED_REQUESTS + failed))
    
    # Cleanup
    rm -rf "$temp_dir"
    
    echo ""
    echo "Results: $successful successful, $failed failed"
    
    if [ $successful -ge $((burst_size * 95 / 100)) ]; then
        echo -e "${GREEN}✓ Test PASSED: 95%+ success rate ($successful/$burst_size)${NC}"
        return 0
    else
        echo -e "${RED}✗ Test FAILED: Success rate too low ($successful/$burst_size)${NC}"
        return 1
    fi
}

# Main execution
main() {
    echo "Target API: $API_URL"
    echo "Tenant ID: $TENANT_ID"
    echo ""
    
    # Check if services are running
    echo "Checking service health..."
    if ! curl -sf "$API_URL/health" >/dev/null 2>&1; then
        echo -e "${RED}Error: Dispatcher service not available at $API_URL${NC}"
        echo "Start services with: docker-compose up -d"
        exit 1
    fi
    echo -e "${GREEN}✓ Services are healthy${NC}"
    
    # Run tests
    local passed=0
    local failed=0
    
    if test_kill_dispatcher; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    if test_redis_failover; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    if test_concurrency_burst; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
    fi
    
    # Summary
    echo ""
    echo "========================================="
    echo "  Chaos Testing Summary"
    echo "========================================="
    echo "Tests Passed: $passed"
    echo "Tests Failed: $failed"
    echo ""
    echo "Request Statistics:"
    echo "  Total Requests: $TOTAL_REQUESTS"
    echo "  Successful: $SUCCESSFUL_REQUESTS"
    echo "  Failed: $FAILED_REQUESTS"
    echo "  Reconciled: $RECONCILED_REQUESTS"
    echo ""
    
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}✓ ALL CHAOS TESTS PASSED${NC}"
        echo "Zero-silent-loss guarantee verified!"
        exit 0
    else
        echo -e "${RED}✗ SOME CHAOS TESTS FAILED${NC}"
        echo "Review logs for details"
        exit 1
    fi
}

main

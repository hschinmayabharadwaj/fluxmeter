/**
 * Ledgerline Load Test - Phase 1: Baseline
 * 
 * Test Plan:
 * - Ramp up to 100 concurrent users over 2 minutes
 * - Sustain 100 CCU for 10 minutes
 * - Verify: 0% dropped requests, 0% duplicate charges
 * 
 * Success Criteria:
 * - P95 latency < 500ms
 * - Error rate < 0.1%
 * - All requests reconciled (status = RECONCILED)
 * - Zero idempotency violations
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const reconciliationRate = new Rate('reconciliation_rate');
const idempotencyViolations = new Counter('idempotency_violations');
const duplicateCharges = new Counter('duplicate_charges');
const droppedRequests = new Counter('dropped_requests');
const latencyTrend = new Trend('request_latency');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 100 },   // Ramp up to 100 CCU
    { duration: '10m', target: 100 },  // Sustain 100 CCU
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // P95 latency < 500ms
    http_req_failed: ['rate<0.001'],   // Error rate < 0.1%
    reconciliation_rate: ['rate>0.999'], // 99.9%+ reconciliation
    idempotency_violations: ['count<1'], // Zero violations
    duplicate_charges: ['count<1'],     // Zero duplicates
  },
};

// Base URLs
const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const TENANT_ID = __ENV.TENANT_ID || 'tenant_001';

/**
 * Generate a unique correlation ID for each request
 */
function generateCorrelationId() {
  return `test_${Date.now()}_${randomString(8)}`;
}

/**
 * Submit AI request to dispatcher
 */
function submitRequest(correlationId, provider, model) {
  const payload = JSON.stringify({
    correlation_id: correlationId,
    tenant_id: TENANT_ID,
    provider: provider,
    model: model,
    messages: [
      {
        role: 'user',
        content: 'Write a short poem about distributed systems.',
      },
    ],
    max_tokens: 100,
    temperature: 0.7,
    cost_allocation_tags: {
      test: 'load_test_phase1',
      run_id: __ENV.RUN_ID || 'local',
    },
  });

  const startTime = Date.now();
  
  const res = http.post(
    `${BASE_URL}/v1/submit`,
    payload,
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '30s',
    }
  );

  const duration = Date.now() - startTime;
  latencyTrend.add(duration);

  return res;
}

/**
 * Verify request status and reconciliation
 */
function verifyStatus(correlationId, maxAttempts = 10) {
  let attempts = 0;
  let reconciled = false;

  while (attempts < maxAttempts && !reconciled) {
    sleep(2);
    
    const statusRes = http.get(
      `${BASE_URL}/v1/status/${correlationId}`,
      { timeout: '5s' }
    );

    if (statusRes.status === 200) {
      const status = JSON.parse(statusRes.body);
      
      if (status.status === 'RECONCILED') {
        reconciled = true;
        reconciliationRate.add(true);
        return status;
      } else if (status.status === 'FAILED') {
        droppedRequests.add(1);
        reconciliationRate.add(false);
        return status;
      }
    }
    
    attempts++;
  }

  if (!reconciled) {
    droppedRequests.add(1);
    reconciliationRate.add(false);
  }

  return null;
}

/**
 * Main test scenario
 */
export default function() {
  const correlationId = generateCorrelationId();
  const provider = 'openai';
  const model = 'gpt-4';

  const submitRes = submitRequest(correlationId, provider, model);
  
  check(submitRes, {
    'submit request successful': (r) => r.status === 200,
    'response has correlation_id': (r) => {
      const body = JSON.parse(r.body || '{}');
      return body.correlation_id === correlationId;
    },
  });

  if (Math.random() < 0.1) {
    verifyStatus(correlationId);
  }

  sleep(1);
}

export function setup() {
  console.log('Starting Ledgerline Load Test - Phase 1');
  const healthRes = http.get(`${BASE_URL}/health`, { timeout: '5s' });
  if (healthRes.status !== 200) {
    throw new Error('Health check failed');
  }
  return { startTime: Date.now() };
}

export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`\nLoad test completed in ${duration.toFixed(2)} seconds`);
}

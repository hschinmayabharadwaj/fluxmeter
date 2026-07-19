# Product Requirements Document (PRD): Ledgerline AI Orchestration & Billing Platform

## 1. Executive Summary
Ledgerline is a high-integrity AI orchestration and billing platform designed to provide "zero-silent-loss" guarantees for enterprise AI usage. Unlike standard AI gateways, Ledgerline treats every AI request as a financial transaction, ensuring that usage is accurately metered, billed, and reconciled even in the event of provider outages, network partitions, or system crashes. The system features a hardened core engine, a real-time streaming path with incremental checkpointing, and a comprehensive business layer for A/B testing and cost allocation.

## 2. Problem Statement
Enterprises deploying AI at scale face significant financial and operational risks:
*   **Silent Losses:** Unbilled usage due to interrupted streams or crashed worker processes.
*   **Double-Billing:** Spurious retries or race conditions leading to multiple charges for a single request.
*   **Lack of Transparency:** Difficulty in reconciling provider-side costs with internal department usage.
*   **Infrastructure Jitter:** Standard gateways fail to maintain state during Redis failovers or high-latency provider responses.

## 3. Goals & Objectives
*   **Zero-Silent-Loss:** 100% of requests must result in a reconciled ledger state or a flagged exception.
*   **Exactly-Once Processing:** Prevent double-charging through atomic idempotency and "Sync-before-ACK" logic.
*   **High Concurrency:** Support a baseline of 100+ concurrent requests without data corruption.
*   **Operational Transparency:** Provide a Manual Review UI for resolving partial states and an audit trail for all transactions.
*   **Cost Attribution:** Enable hierarchical billing through cost allocation tagging.

## 4. Target Users / Stakeholders
*   **Platform Engineers:** Require a reliable, scalable gateway for internal AI services.
*   **FinOps / Billing Teams:** Need accurate usage data for internal chargebacks and customer invoicing.
*   **Product Managers:** Require A/B testing capabilities and cost-per-feature analysis.
*   **Compliance Officers:** Need durable audit logs and data retention policy enforcement.

## 5. Functional Requirements

### 5.1 Core Request Handling
*   **Idempotency:** Support atomic `SET NX` idempotency at the gateway level using Correlation IDs.
*   **Sync-before-ACK:** Dispatchers must persist a durable outbox signal in Redis before acknowledging messages from RabbitMQ.
*   **Queued Processing:** Reliable job execution via RabbitMQ Quorum Queues with a 45s visibility timeout.

### 5.2 Hardened Streaming
*   **Incremental Checkpointing:** The Streaming Dispatcher must write running token totals to Redis every few seconds.
*   **Provider True-up:** Automated logic to query Provider APIs (OpenAI/Anthropic) to reconcile final usage for interrupted streams.
*   **10s Streaming Sweep:** High-frequency monitoring to detect and resolve orphaned streams within seconds.

### 5.3 Intelligence & Routing
*   **A/B Testing:** Support concurrent "sibling" attempts tagged with `ab-` prefixes to prevent retry-chain ambiguity in the ledger.
*   **Static Fallbacks:** Enforce a "Fixed Zero-Rate" billing rule for canned responses served during provider outages.
*   **Semantic Cache:** Vector-based caching (Qdrant) with triple-tag validation (Policy Version, Region, Provider).

### 5.4 Business & Revenue Operations
*   **Cost Allocation Tags:** Support for sub-tenant metadata (e.g., `department`, `project`) for internal chargebacks.
*   **Manual Review UI:** A dashboard for human intervention to resolve `PARTIAL` states (Approve at Checkpoint, Approve at Zero, or Request Info).
*   **Audit Export:** Automated usage data pushes to Stripe and S3 (Parquet format).

## 6. Non-Functional Requirements
*   **Reliability:** Use of RabbitMQ Quorum Queues and Redis Sentinel for high availability.
*   **Durability:** 30s worker locks with 10s heartbeat intervals and a 2-retry/5s grace period for Redis failovers.
*   **Performance:** P99 latency monitoring for Redis commands (Lock vs. Quota vs. Outbox).
*   **Security:** Per-tenant encrypted key storage via HashiCorp Vault.

## 7. System Architecture Overview
The system is divided into three primary layers:
1.  **The Edge Layer:** Kong Gateway handles entry, rate limiting, and initial idempotency.
2.  **The Core Integrity Engine:** RabbitMQ and the Hardened Dispatcher manage the "durability tax," ensuring every job is tracked via a Transactional Outbox.
3.  **The Platform Layer:** Mastra handles routing/A-B logic, while the DLQ Handler and Tenant Dashboard manage long-term reconciliation and manual reviews.

## 8. Tech Stack
*   **API Gateway:** Kong Gateway (Lua Plugins).
*   **Message Broker:** RabbitMQ (Quorum Queues).
*   **Services:** Go (Rate Limiter, DLQ Handler, Streaming), Python/FastAPI (Dispatcher, Routing).
*   **Databases:** PostgreSQL (Logs/Tenants), Redis Cluster (State/Outbox), Qdrant (Vector Cache).
*   **Observability:** Prometheus, Grafana, OpenTelemetry.
*   **Testing:** k6 (Load), Chaos Mesh (Chaos Engineering).

## 9. Data Requirements
*   **Ledger Schema:** Must include `correlation_id`, `attempt_id`, `tenant_id`, `cost_allocation_tags`, `token_count`, and `status` (RECONCILED, PARTIAL, ORPHANED).
*   **Transactional Outbox:** Redis-based durable signals used to bridge the gap between provider responses and ledger writes.
*   **Retention Policies:** Tenant-specific data retention rules enforced by the Retention Policy Engine.

## 10. API Specifications
*   **POST /v1/submit:** Idempotent request submission (Async/Sync).
*   **GET /v1/status/{correlation_id}:** Polling endpoint for job state.
*   **POST /v1/reconcile:** Internal API for Dispatchers to finalize billing.
*   **GET /v1/ledger:** Read-only access for tenants to view usage.
*   **POST /v1/manual-review/resolve:** Endpoint for the Dashboard to move `PARTIAL` records to terminal states.

## 11. Security Requirements
*   **Authentication:** JWT-based tenant authentication at the Gateway.
*   **Authorization:** RBAC for the Tenant Dashboard (Admin vs. Viewer).
*   **Data Protection:** PII masking and jailbreak detection via Enkrypt AI guardrails.
*   **Key Management:** All provider keys stored in Vault; never logged or stored in plaintext.

## 12. Deployment & Infrastructure
*   **Containerization:** All services deployed as Docker containers.
*   **Orchestration:** Kubernetes (implied) for scaling Dispatcher workers.
*   **CI/CD:** Automated pipeline including the Phase 1 Load Test Harness as a deployment gate.

## 13. Success Metrics
*   **Integrity:** 0% unbilled requests during "Dirty" Dispatcher crashes.
*   **Accuracy:** 0% duplicate charges during Redis Sentinel failovers.
*   **Latency:** Redis command P99 within empirically defined baselines.
*   **Resolution:** 100% of orphaned requests resolved by DLQ Handler within 90 seconds.

## 14. Timeline & Milestones
*   **Phase 1: Integrity Core:** Build Kong -> RabbitMQ -> Dispatcher -> Redis. Conduct 100+ CCU Load and Chaos tests.
*   **Phase 2: Hardened Streaming:** Implement Go-based Streaming Dispatcher and 10s Streaming Sweep.
*   **Phase 3: Intelligence Layer:** Deploy Mastra (Routing), Qdrant (Caching), and the Manual Review UI.

## 15. Open Questions & Risks
*   **Redis Throughput:** The "Redis Ceiling" must be empirically measured in Phase 1 to ensure locking/heartbeating doesn't bottleneck the system.
*   **Tenant Traffic Mix:** The prioritization of Phase 2 (Streaming) vs. Phase 3 (Intelligence) depends on whether the initial tenant base is human-facing (chat) or programmatic (batch).
*   **Provider API Latency:** Extreme provider slowness (>30s) may require dynamic lock TTL adjustments.
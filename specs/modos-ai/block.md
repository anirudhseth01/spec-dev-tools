# Block Specification: Modos AI

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: root
- parent: none

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|
| connected-data-spine | component | Unified data layer with connectors, normalization, and identity resolution |
| workflow-intelligence | component | Signal detection, case management, and workflow mining |
| safe-execution-runtime | component | Durable execution engine with tool registry and approval workflows |
| security | component | Multi-tenant isolation, permissions, and prompt injection defense |

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| MODOS-SEC-001 | Tenant Isolation | security | error | api_contract, security | check_tenant_context | All operations must include tenant context |
| MODOS-SEC-002 | Audit Logging | security | error | api_contract | check_audit_events | All mutations must emit audit events |
| MODOS-PERF-001 | Async First | performance | warning | implementation | check_async_patterns | Prefer async operations for I/O |

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: modos-ai
- version: 1.0.0
- status: draft
- tech_stack: Python, FastAPI, PostgreSQL, Redis, Temporal, Vector DB
- author: Modos AI Team
- created: 2024-01-15
- updated: 2024-02-19

## 2. Overview

### Summary

Modos AI is a connected-data intelligence platform that enables enterprise workflow automation through AI agents. It provides a unified data spine across enterprise systems, intelligent workflow detection and execution, and a safe runtime for AI-driven actions with human-in-the-loop approvals.

### Goals

- Unify enterprise data across disparate systems (CRM, ERP, HRIS, etc.) into a coherent graph
- Detect workflow patterns and anomalies through signal intelligence
- Enable AI agents to execute complex workflows with appropriate safeguards
- Provide multi-tenant SaaS with enterprise-grade security and isolation
- Support human-in-the-loop approval workflows for sensitive operations

### Non-Goals

- Replacing existing enterprise systems (we integrate, not replace)
- Real-time streaming analytics (we focus on workflow automation)
- Custom ML model training (we use foundation models)
- On-premise deployment in v1 (SaaS-first)

### Background

Enterprises struggle with fragmented data across dozens of SaaS tools. Knowledge workers spend significant time on manual data entry and workflow coordination. Modos AI addresses this by creating a unified data layer and using AI to automate repetitive workflows while maintaining human oversight for critical decisions.

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| tenant_id | UUID | yes | - | Tenant identifier for multi-tenancy |
| user_id | UUID | yes | - | Authenticated user identifier |
| workspace_id | UUID | no | default | Workspace within tenant |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| connector_configs | list[ConnectorConfig] | yes | - | Configured data source connections |
| workflow_definitions | list[WorkflowDef] | no | [] | Custom workflow definitions |
| approval_policies | list[ApprovalPolicy] | no | default | Policies for human-in-the-loop |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| DATABASE_URL | string | yes | - | PostgreSQL connection string |
| REDIS_URL | string | yes | - | Redis connection for caching/queues |
| TEMPORAL_HOST | string | yes | - | Temporal server for durable execution |
| ANTHROPIC_API_KEY | string | yes | - | Claude API key for AI operations |
| ENCRYPTION_KEY | string | yes | - | Key for encrypting sensitive data |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| unified_graph | EntityGraph | Normalized entity graph across all connected systems |
| detected_signals | list[Signal] | Workflow signals detected from data changes |
| execution_results | list[ExecutionResult] | Results from workflow executions |
| audit_log | list[AuditEvent] | Comprehensive audit trail |

### Side Effects

- Entity records created/updated in unified graph
- Workflow executions triggered in connected systems
- Notifications sent to users for approvals
- Audit events persisted for compliance

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| entity.created | EntityCreatedEvent | New entity added to graph |
| entity.updated | EntityUpdatedEvent | Entity properties changed |
| signal.detected | SignalDetectedEvent | Workflow signal identified |
| workflow.started | WorkflowStartedEvent | Workflow execution began |
| workflow.completed | WorkflowCompletedEvent | Workflow execution finished |
| approval.requested | ApprovalRequestedEvent | Human approval needed |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|
| connected-data-spine | Data connectivity and normalization |
| workflow-intelligence | Signal detection and case management |
| safe-execution-runtime | Workflow execution with safeguards |
| security | Authentication, authorization, isolation |

### External

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | ^0.109 | API framework |
| sqlalchemy | ^2.0 | Database ORM |
| temporalio | ^1.4 | Durable workflow execution |
| anthropic | ^0.18 | Claude AI integration |
| pydantic | ^2.6 | Data validation |

### Services

| Service | Purpose |
|---------|---------|
| PostgreSQL | Primary data store |
| Redis | Caching, rate limiting, pub/sub |
| Temporal | Durable workflow orchestration |
| Vector DB | Semantic search and embeddings |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | /api/v1/entities | EntityQuery | EntityList | Query unified entity graph |
| POST | /api/v1/entities | CreateEntityRequest | Entity | Create entity in graph |
| GET | /api/v1/signals | SignalQuery | SignalList | List detected signals |
| POST | /api/v1/workflows/execute | ExecuteWorkflowRequest | WorkflowExecution | Start workflow execution |
| POST | /api/v1/approvals/{id}/approve | ApprovalDecision | ApprovalResult | Approve pending action |
| GET | /api/v1/audit | AuditQuery | AuditLogList | Query audit trail |

### Error Codes

| Code | Description |
|------|-------------|
| TENANT_NOT_FOUND | Tenant does not exist |
| UNAUTHORIZED | Authentication required or failed |
| FORBIDDEN | User lacks permission for operation |
| CONNECTOR_ERROR | External system connection failed |
| WORKFLOW_FAILED | Workflow execution encountered error |
| APPROVAL_TIMEOUT | Approval request timed out |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | Entity normalization | Raw CRM contact | Normalized Person entity | Mock connector | - |
| UT-002 | Signal detection | Entity change event | Relevant signals identified | Seed rules | - |
| UT-003 | Tenant isolation | Cross-tenant query | Empty result (no leakage) | Multi-tenant data | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | End-to-end connector sync | Salesforce config | Entities in graph | Salesforce sandbox | Cleanup entities |
| IT-002 | Workflow execution | Workflow trigger | Actions completed | Test workflow | Rollback actions |
| IT-003 | Approval flow | Sensitive action | Blocked until approved | Approval policy | - |

- min_line_coverage: 85
- min_branch_coverage: 75

## 8. Edge Cases

### Boundary Conditions

- Empty connector response (no data to sync)
- Maximum entity graph size (pagination required)
- Concurrent updates to same entity (conflict resolution)
- Rate limit exhaustion on external APIs

### Concurrency

- Multiple workflows modifying same entity
- Parallel connector syncs for same tenant
- Approval timeout during workflow execution
- Graceful degradation under load

### Failure Modes

- External connector unavailable (retry with backoff)
- Temporal worker failure (workflow resumes from checkpoint)
- Database connection pool exhaustion (queue requests)
- AI service timeout (fallback to cached response or error)

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| ConnectorError | yes | Exponential backoff, max 5 retries |
| ValidationError | no | Return 400 with details |
| AuthorizationError | no | Return 403, log attempt |
| WorkflowError | depends | Checkpoint and alert |
| SystemError | yes | Circuit breaker pattern |

- max_retries: 5
- backoff_strategy: exponential
- circuit_breaker_threshold: 5
- circuit_breaker_timeout: 60

## 10. Performance

- p50: 100
- p95: 500
- p99: 2000
- target_rps: 1000
- memory_limit: 2048
- max_concurrent_workflows: 100
- connector_sync_timeout: 300

## 11. Security

- requires_auth: true
- auth_method: JWT with tenant claims
- handles_pii: true
- encryption_at_rest: true
- encryption_in_transit: true
- data_retention_days: 365

### Roles

| Role | Permissions |
|------|-------------|
| admin | Full access, manage connectors, approve all |
| operator | Execute workflows, view all data |
| analyst | Read-only access to entities and signals |
| approver | Approve/reject pending actions |

### Security Controls

- Tenant data isolation at database level (RLS)
- API rate limiting per tenant
- Prompt injection detection for AI inputs
- Audit logging for all mutations
- Secrets encrypted with tenant-specific keys

## 12. Implementation

### Algorithms

- **Entity Resolution**: Probabilistic matching using embeddings + rules
- **Signal Detection**: Event-driven pattern matching with temporal windows
- **Workflow Mining**: Process discovery from execution traces

### Patterns

- **CQRS**: Separate read/write models for scalability
- **Event Sourcing**: Audit trail and replay capability
- **Saga Pattern**: Distributed transactions across systems
- **Circuit Breaker**: Resilience for external dependencies

### Constraints

- All API calls must complete within 30 seconds
- Workflow steps must be idempotent for retry safety
- PII must never be logged in plaintext
- Cross-tenant data access is strictly prohibited

## 13. Acceptance

### Criteria

- [ ] Connectors successfully sync data from Salesforce, HubSpot, Workday
- [ ] Entity resolution achieves >90% precision on test dataset
- [ ] Signal detection latency <5s from source event
- [ ] Workflow execution survives worker restart
- [ ] Approval flow blocks sensitive actions until human decision
- [ ] Zero cross-tenant data leakage in security audit

### Definition of Done

- [ ] Code complete with type hints
- [ ] Unit tests passing (>85% coverage)
- [ ] Integration tests passing
- [ ] Security review completed
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Deployed to staging environment

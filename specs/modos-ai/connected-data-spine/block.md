# Block Specification: Connected Data Spine

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: modos-ai

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|
| connectors | module | Integration adapters for external systems (Salesforce, HubSpot, etc.) |
| normalization | module | Entity extraction, schema mapping, and data transformation |
| identity-resolution | module | Cross-system entity matching and deduplication |

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| CDS-001 | Schema Versioning | api | error | api_contract | check_schema_version | All entity schemas must be versioned |
| CDS-002 | Idempotent Sync | code_quality | error | implementation | check_idempotency | Sync operations must be idempotent |

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|
| security | ../security | security | extend |

## 1. Metadata

- spec_id: connected-data-spine
- version: 1.0.0
- status: draft
- tech_stack: Python, SQLAlchemy, Redis, Celery
- author: Modos AI Team
- created: 2024-01-15
- updated: 2024-02-19

## 2. Overview

### Summary

The Connected Data Spine provides unified data access across enterprise systems. It manages connectors to external platforms (CRM, ERP, HRIS), normalizes heterogeneous data into a canonical schema, and resolves entity identity across systems to build a coherent enterprise knowledge graph.

### Goals

- Provide plug-and-play connectors for popular enterprise systems
- Normalize diverse data formats into unified entity schemas
- Resolve entity identity across systems (e.g., same person in Salesforce and Workday)
- Maintain real-time sync with incremental updates
- Support full historical sync for initial onboarding

### Non-Goals

- Real-time CDC streaming (we use polling/webhooks)
- Custom connector development UI (API/config only in v1)
- Data warehousing or analytics (we focus on operational data)

### Background

Enterprise data is fragmented across 50+ SaaS tools on average. Each system has its own schema, IDs, and update patterns. The Connected Data Spine creates a unified view by extracting, normalizing, and linking entities across these systems.

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| connector_type | ConnectorType | yes | - | Type of system to connect (salesforce, hubspot, workday, etc.) |
| credentials | EncryptedCredentials | yes | - | OAuth tokens or API keys (encrypted) |
| sync_config | SyncConfig | no | default | Sync frequency, filters, field mappings |
| entity_types | list[str] | no | all | Which entity types to sync |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| tenant_id | UUID | yes | - | Tenant context for data isolation |
| schema_registry | SchemaRegistry | yes | - | Canonical entity schemas |
| identity_rules | list[IdentityRule] | no | default | Rules for entity matching |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| CONNECTOR_POOL_SIZE | int | no | 10 | Max concurrent connector operations |
| SYNC_BATCH_SIZE | int | no | 1000 | Records per sync batch |
| IDENTITY_MATCH_THRESHOLD | float | no | 0.85 | Minimum score for identity match |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| entities | list[NormalizedEntity] | Normalized entities from source system |
| sync_status | SyncStatus | Status of sync operation |
| identity_matches | list[IdentityMatch] | Cross-system entity matches |
| sync_metrics | SyncMetrics | Records synced, errors, duration |

### Side Effects

- Entities created/updated in unified graph database
- Identity links created between cross-system entities
- Sync checkpoint updated for incremental sync
- Webhook subscriptions created in source systems

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| connector.connected | ConnectorConnectedEvent | New connector successfully authenticated |
| sync.started | SyncStartedEvent | Sync operation began |
| sync.completed | SyncCompletedEvent | Sync operation finished |
| entity.extracted | EntityExtractedEvent | Entity extracted from source |
| identity.matched | IdentityMatchedEvent | Cross-system identity resolved |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|
| security | Credential encryption, tenant isolation |

### External

| Package | Version | Purpose |
|---------|---------|---------|
| simple-salesforce | ^1.12 | Salesforce API client |
| hubspot-api-client | ^8.1 | HubSpot API client |
| celery | ^5.3 | Async task processing |
| redis | ^5.0 | Task queue backend |

### Services

| Service | Purpose |
|---------|---------|
| PostgreSQL | Entity storage |
| Redis | Sync queue, caching |
| Vector DB | Embedding storage for identity resolution |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | /api/v1/connectors | CreateConnectorRequest | Connector | Register new connector |
| GET | /api/v1/connectors | - | list[Connector] | List tenant connectors |
| POST | /api/v1/connectors/{id}/sync | SyncRequest | SyncJob | Trigger sync |
| GET | /api/v1/connectors/{id}/status | - | ConnectorStatus | Get connector health |
| GET | /api/v1/entities | EntityQuery | EntityPage | Query normalized entities |
| GET | /api/v1/entities/{id}/sources | - | list[SourceReference] | Get source system references |

### Error Codes

| Code | Description |
|------|-------------|
| CONNECTOR_AUTH_FAILED | OAuth/API key validation failed |
| CONNECTOR_RATE_LIMITED | Source system rate limit hit |
| SYNC_IN_PROGRESS | Another sync already running |
| SCHEMA_MISMATCH | Source schema changed unexpectedly |
| IDENTITY_CONFLICT | Ambiguous identity match |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-CDS-001 | Salesforce contact normalization | SF Contact JSON | Person entity | - | - |
| UT-CDS-002 | HubSpot company normalization | HS Company JSON | Organization entity | - | - |
| UT-CDS-003 | Identity matching by email | Two entities, same email | Match with score > 0.9 | - | - |
| UT-CDS-004 | Identity matching by name fuzzy | Similar names | Match with appropriate score | - | - |
| UT-CDS-005 | Schema version migration | v1 entity | v2 entity with defaults | Schema registry | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-CDS-001 | Salesforce full sync | SF sandbox credentials | All contacts/accounts synced | SF sandbox data | Clear entities |
| IT-CDS-002 | Incremental sync | Modified records | Only changes synced | Baseline sync | - |
| IT-CDS-003 | Webhook processing | SF outbound message | Entity updated in real-time | Webhook config | - |

- min_line_coverage: 85
- min_branch_coverage: 75

## 8. Edge Cases

### Boundary Conditions

- Source system returns empty result set
- Entity has no matchable identifiers (email, phone)
- Sync batch exceeds memory limits
- Source system schema changes mid-sync

### Concurrency

- Multiple syncs for same connector
- Webhook arrives during batch sync
- Identity resolution conflicts

### Failure Modes

- OAuth token expired mid-sync
- Source system timeout
- Database connection pool exhaustion
- Identity matching service unavailable

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| AuthenticationError | no | Notify user, pause connector |
| RateLimitError | yes | Exponential backoff |
| NetworkError | yes | Retry with jitter |
| SchemaError | no | Log and skip record |
| IdentityError | no | Create unlinked entity |

- max_retries: 5
- backoff_strategy: exponential
- backoff_base: 2
- backoff_max: 300

## 10. Performance

- p50: 50
- p95: 200
- p99: 1000
- target_rps: 500
- memory_limit: 1024
- max_batch_size: 5000
- sync_parallelism: 4

## 11. Security

- requires_auth: true
- auth_method: JWT
- handles_pii: true
- encryption_at_rest: true
- encryption_in_transit: true

### Roles

| Role | Permissions |
|------|-------------|
| admin | Manage connectors, view credentials |
| operator | Trigger syncs, view status |
| analyst | Read entities only |

### Security Controls

- Credentials encrypted with tenant-specific keys
- OAuth tokens stored in secure vault
- PII fields marked and handled specially
- Audit log for all connector operations

## 12. Implementation

### Algorithms

- **Incremental Sync**: Checkpoint-based using source system timestamps
- **Identity Resolution**: Embedding similarity + deterministic rules
- **Schema Mapping**: Configurable field transformations with defaults

### Patterns

- **Adapter Pattern**: Connector interface with system-specific implementations
- **Factory Pattern**: Connector instantiation based on type
- **Observer Pattern**: Event emission on entity changes

### Constraints

- Connectors must implement the Connector interface
- All synced data must go through normalization
- PII fields must be tagged in schema
- Sync operations must be resumable

## 13. Acceptance

### Criteria

- [ ] Salesforce connector syncs contacts, accounts, opportunities
- [ ] HubSpot connector syncs contacts, companies, deals
- [ ] Identity resolution matches >90% of duplicate entities
- [ ] Incremental sync completes in <5 minutes for 10k changes
- [ ] Webhook processing latency <1 second

### Definition of Done

- [ ] Connector interface defined and documented
- [ ] 3+ connector implementations complete
- [ ] Identity resolution algorithm validated
- [ ] Unit tests >85% coverage
- [ ] Integration tests with sandbox accounts
- [ ] Performance benchmarks met

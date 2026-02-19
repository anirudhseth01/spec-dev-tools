# Block Specification: Security

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: modos-ai

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|
| tenant-isolation | module | Multi-tenant data isolation and context management |
| permissions | module | Role-based access control and policy enforcement |
| prompt-defense | module | Prompt injection detection and sanitization |

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| SEC-GLOBAL-001 | Tenant Context Required | security | error | api_contract | check_tenant_context | All requests must have tenant context |
| SEC-GLOBAL-002 | Audit All Mutations | security | error | api_contract | check_audit | All write operations must be audited |
| SEC-GLOBAL-003 | No PII in Logs | security | error | implementation | check_pii_logging | PII must never appear in logs |

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|

## 1. Metadata

- spec_id: security
- version: 1.0.0
- status: draft
- tech_stack: Python, FastAPI, PostgreSQL, Redis, HashiCorp Vault
- author: Modos AI Team
- created: 2024-01-15
- updated: 2024-02-19

## 2. Overview

### Summary

The Security component provides enterprise-grade security for the Modos AI platform. It implements multi-tenant isolation at the database level, role-based access control with fine-grained permissions, and prompt injection defense to protect AI operations from adversarial inputs.

### Goals

- Ensure complete data isolation between tenants
- Provide flexible, fine-grained access control
- Detect and prevent prompt injection attacks
- Maintain comprehensive audit trails
- Secure credential and secret management

### Non-Goals

- Network security (handled by infrastructure)
- DDoS protection (handled by CDN/WAF)
- Endpoint security (out of scope)
- Compliance certifications (separate effort)

### Background

Multi-tenant SaaS platforms must guarantee that one tenant cannot access another's data. With AI systems, there's additional risk of prompt injection where malicious inputs manipulate the AI. This component addresses both traditional security concerns and AI-specific threats.

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| jwt_token | string | yes | - | JWT containing tenant/user claims |
| requested_resource | Resource | yes | - | Resource being accessed |
| requested_action | Action | yes | - | Action being performed |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| role_definitions | list[Role] | yes | - | Defined roles and permissions |
| prompt_defense_rules | list[DefenseRule] | yes | default | Rules for prompt injection detection |
| audit_config | AuditConfig | no | default | What to audit and where |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| JWT_SECRET | string | yes | - | Secret for JWT validation |
| ENCRYPTION_KEY | string | yes | - | Master encryption key |
| VAULT_ADDR | string | no | - | HashiCorp Vault address |
| AUDIT_LOG_LEVEL | string | no | INFO | Audit logging verbosity |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| auth_result | AuthResult | Authentication result with tenant/user context |
| authz_result | AuthzResult | Authorization decision (allow/deny) |
| sanitized_input | string | Input with prompt injection attempts removed |
| audit_event | AuditEvent | Audit record for the operation |

### Side Effects

- Audit events persisted
- Failed auth attempts logged
- Suspicious activity flagged
- Rate limits applied

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| auth.success | AuthSuccessEvent | User authenticated |
| auth.failure | AuthFailureEvent | Authentication failed |
| authz.denied | AuthzDeniedEvent | Permission denied |
| injection.detected | InjectionDetectedEvent | Prompt injection attempt |
| audit.created | AuditCreatedEvent | Audit record created |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|

### External

| Package | Version | Purpose |
|---------|---------|---------|
| pyjwt | ^2.8 | JWT validation |
| cryptography | ^42.0 | Encryption operations |
| hvac | ^2.1 | HashiCorp Vault client |
| anthropic | ^0.18 | AI-based injection detection |

### Services

| Service | Purpose |
|---------|---------|
| PostgreSQL | Audit log storage, RLS policies |
| Redis | Rate limiting, session cache |
| HashiCorp Vault | Secret management |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | /api/v1/auth/token | TokenRequest | TokenResponse | Exchange credentials for JWT |
| POST | /api/v1/auth/refresh | RefreshRequest | TokenResponse | Refresh expired token |
| GET | /api/v1/auth/me | - | UserInfo | Get current user info |
| GET | /api/v1/permissions | - | list[Permission] | List user's permissions |
| POST | /api/v1/admin/roles | RoleDefinition | Role | Create role (admin only) |
| GET | /api/v1/audit | AuditQuery | list[AuditEvent] | Query audit log |

### Error Codes

| Code | Description |
|------|-------------|
| INVALID_TOKEN | JWT is invalid or expired |
| UNAUTHORIZED | Authentication required |
| FORBIDDEN | User lacks permission |
| RATE_LIMITED | Too many requests |
| INJECTION_DETECTED | Prompt injection blocked |
| TENANT_MISMATCH | Request tenant doesn't match token |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-SEC-001 | Valid JWT parsing | Valid JWT | Tenant/user extracted | - | - |
| UT-SEC-002 | Expired JWT rejection | Expired JWT | INVALID_TOKEN error | - | - |
| UT-SEC-003 | Permission check pass | User with permission | Allow | Mock roles | - |
| UT-SEC-004 | Permission check fail | User without permission | Deny | Mock roles | - |
| UT-SEC-005 | Prompt injection detect | Malicious input | Injection flagged | Defense rules | - |
| UT-SEC-006 | Clean input pass | Normal input | No flag | Defense rules | - |
| UT-SEC-007 | Tenant isolation | Cross-tenant query | Empty result | RLS policies | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-SEC-001 | End-to-end auth flow | Valid credentials | JWT issued | Test user | - |
| IT-SEC-002 | RLS enforcement | Query as Tenant A | Only Tenant A data | Multi-tenant data | - |
| IT-SEC-003 | Audit log creation | API mutation | Audit event recorded | - | - |
| IT-SEC-004 | Rate limiting | Burst requests | 429 after limit | Rate config | Reset limits |

- min_line_coverage: 90
- min_branch_coverage: 85

## 8. Edge Cases

### Boundary Conditions

- JWT at exact expiration time
- User with no roles
- Resource with no permissions defined
- Empty input to injection detector

### Concurrency

- Simultaneous token refresh
- Permission cache invalidation race
- Audit log write contention

### Failure Modes

- Vault unavailable for secrets
- Database connection failure
- Redis cache miss
- AI service timeout for injection detection

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| AuthenticationError | no | Return 401, log attempt |
| AuthorizationError | no | Return 403, audit |
| VaultError | yes | Retry, fallback to cached |
| RateLimitError | no | Return 429, include retry-after |
| InjectionError | no | Block request, alert security |

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- p50: 5
- p95: 20
- p99: 50
- target_rps: 10000
- memory_limit: 256
- jwt_validation_cache_ttl: 300
- permission_cache_ttl: 60

## 11. Security

- requires_auth: true (except /auth/token)
- auth_method: JWT
- handles_pii: true
- encryption_at_rest: true
- encryption_in_transit: true

### Roles

| Role | Permissions |
|------|-------------|
| super_admin | All permissions, manage tenants |
| tenant_admin | Manage tenant users and roles |
| security_admin | View audit logs, manage policies |

### Security Controls

- Row-Level Security (RLS) on all tenant tables
- JWT claims validated on every request
- Secrets never logged or exposed in errors
- Rate limiting per tenant and user
- Suspicious activity detection and alerting
- Regular security audit log review

### Prompt Injection Defense

| Defense | Description |
|---------|-------------|
| Input Sanitization | Remove known injection patterns |
| Delimiter Enforcement | Ensure system/user prompt separation |
| Output Validation | Check AI output for data leakage |
| Canary Tokens | Detect if injected prompts execute |
| Rate Limiting | Limit prompt submissions |

## 12. Implementation

### Algorithms

- **JWT Validation**: Standard RS256/HS256 with claim verification
- **Permission Resolution**: Role -> Permission lookup with caching
- **Injection Detection**: Pattern matching + AI classification
- **RLS Enforcement**: PostgreSQL policies with tenant_id

### Patterns

- **Middleware Pattern**: Auth/authz as request middleware
- **Decorator Pattern**: Permission checks on endpoints
- **Strategy Pattern**: Pluggable injection detectors

### Constraints

- JWT must include tenant_id claim
- All database queries must use tenant context
- PII must be encrypted before storage
- Audit logs are immutable (no deletes)
- Security component has no external dependencies on other Modos components

## 13. Acceptance

### Criteria

- [ ] Zero cross-tenant data leakage in penetration test
- [ ] JWT validation <10ms p95
- [ ] Prompt injection detection >95% accuracy
- [ ] Audit log captures all mutations
- [ ] Rate limiting prevents abuse
- [ ] Secrets never appear in logs

### Definition of Done

- [ ] RLS policies on all tenant tables
- [ ] JWT middleware implemented
- [ ] Permission system complete
- [ ] Prompt injection detector trained
- [ ] Audit logging implemented
- [ ] Unit tests >90% coverage
- [ ] Security review passed
- [ ] Penetration test passed

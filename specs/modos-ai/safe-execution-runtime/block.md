# Block Specification: Safe Execution Runtime

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: component
- parent: modos-ai

### 0.2: Sub-Blocks

| Name | Type | Description |
|------|------|-------------|
| durable-execution | module | Temporal-based workflow orchestration with checkpointing |
| tool-registry | module | Registry of available actions/tools with schemas |
| approvals | module | Human-in-the-loop approval workflows |

### 0.3: Scoped Rules

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| SER-001 | Tool Schema Required | api | error | api_contract | check_tool_schema | All tools must have JSON schema |
| SER-002 | Approval Required | security | error | security | check_approval_policy | Sensitive actions require approval |
| SER-003 | Idempotent Tools | code_quality | error | implementation | check_idempotency | Tool executions must be idempotent |

### 0.4: Same-As References

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|
| security | ../security | security | extend |

## 1. Metadata

- spec_id: safe-execution-runtime
- version: 1.0.0
- status: draft
- tech_stack: Python, Temporal, FastAPI, Redis
- author: Modos AI Team
- created: 2024-01-15
- updated: 2024-02-19

## 2. Overview

### Summary

The Safe Execution Runtime provides a secure, durable environment for AI agents to execute workflows. It features a tool registry for available actions, Temporal-based durable execution with automatic checkpointing, and human-in-the-loop approval workflows for sensitive operations.

### Goals

- Execute multi-step workflows durably (survive crashes/restarts)
- Provide a curated registry of safe, tested tools/actions
- Require human approval for sensitive or irreversible actions
- Support rollback and compensation for failed workflows
- Enable dry-run mode for testing workflows

### Non-Goals

- Arbitrary code execution (only registered tools)
- Real-time streaming execution (workflow-based)
- Custom tool development by end users (admin only in v1)

### Background

AI agents need to take actions in the real world (send emails, update CRM, create tickets). This is risky without safeguards. The Safe Execution Runtime ensures actions are auditable, reversible where possible, and require human approval for sensitive operations. Temporal provides durability guarantees.

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| workflow_definition | WorkflowDefinition | yes | - | Steps and conditions for execution |
| trigger_context | TriggerContext | yes | - | What triggered this workflow |
| approval_policy | ApprovalPolicy | no | default | When to require human approval |
| dry_run | bool | no | false | Simulate without executing |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| tenant_id | UUID | yes | - | Tenant context |
| user_id | UUID | yes | - | User initiating workflow |
| tool_registry | ToolRegistry | yes | - | Available tools |
| entity_context | EntityContext | no | - | Entities involved in workflow |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| TEMPORAL_HOST | string | yes | - | Temporal server address |
| TEMPORAL_NAMESPACE | string | no | default | Temporal namespace |
| APPROVAL_TIMEOUT_HOURS | int | no | 24 | Hours before approval expires |
| MAX_WORKFLOW_DURATION | int | no | 3600 | Maximum workflow runtime (seconds) |

## 4. Outputs

### Return Values

| Name | Type | Description |
|------|------|-------------|
| execution_id | UUID | Unique identifier for this execution |
| status | ExecutionStatus | Current status (running, completed, failed, pending_approval) |
| results | list[StepResult] | Results from each workflow step |
| audit_trail | list[AuditEntry] | Complete audit log |

### Side Effects

- Actions executed in external systems (email sent, record updated, etc.)
- Workflow state persisted in Temporal
- Audit entries created
- Approval requests sent to users

### Events

| Event | Payload | Description |
|-------|---------|-------------|
| workflow.started | WorkflowStartedEvent | Workflow execution began |
| workflow.step_completed | StepCompletedEvent | Individual step finished |
| workflow.approval_requested | ApprovalRequestedEvent | Human approval needed |
| workflow.approved | ApprovedEvent | Human approved action |
| workflow.rejected | RejectedEvent | Human rejected action |
| workflow.completed | WorkflowCompletedEvent | Workflow finished successfully |
| workflow.failed | WorkflowFailedEvent | Workflow encountered error |
| workflow.compensated | CompensatedEvent | Rollback completed |

## 5. Dependencies

### Internal

| Module | Purpose |
|--------|---------|
| workflow-intelligence | Trigger context and signals |
| connected-data-spine | Entity context |
| security | Permissions, tenant isolation |

### External

| Package | Version | Purpose |
|---------|---------|---------|
| temporalio | ^1.4 | Durable workflow execution |
| pydantic | ^2.6 | Tool input/output validation |
| anthropic | ^0.18 | AI agent reasoning |
| redis | ^5.0 | Approval state, caching |

### Services

| Service | Purpose |
|---------|---------|
| Temporal | Workflow orchestration |
| PostgreSQL | Audit log, workflow metadata |
| Redis | Approval state, notifications |

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | /api/v1/workflows/execute | ExecuteRequest | Execution | Start workflow execution |
| GET | /api/v1/workflows/{id} | - | ExecutionDetail | Get execution status |
| POST | /api/v1/workflows/{id}/cancel | - | Execution | Cancel running workflow |
| GET | /api/v1/approvals | ApprovalQuery | list[Approval] | List pending approvals |
| POST | /api/v1/approvals/{id}/approve | ApprovalDecision | Approval | Approve pending action |
| POST | /api/v1/approvals/{id}/reject | RejectionReason | Approval | Reject pending action |
| GET | /api/v1/tools | - | list[Tool] | List available tools |
| GET | /api/v1/tools/{id}/schema | - | JSONSchema | Get tool input schema |

### Error Codes

| Code | Description |
|------|-------------|
| WORKFLOW_NOT_FOUND | Workflow execution does not exist |
| TOOL_NOT_FOUND | Requested tool not in registry |
| TOOL_VALIDATION_ERROR | Tool input does not match schema |
| APPROVAL_EXPIRED | Approval request timed out |
| APPROVAL_ALREADY_DECIDED | Approval already approved/rejected |
| WORKFLOW_TIMEOUT | Workflow exceeded max duration |
| COMPENSATION_FAILED | Rollback could not complete |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-SER-001 | Tool validation | Invalid input | Validation error | Mock tool | - |
| UT-SER-002 | Approval required check | Sensitive action | Approval requested | Policy config | - |
| UT-SER-003 | Dry run mode | Workflow + dry_run=true | No side effects | - | - |
| UT-SER-004 | Step retry logic | Transient failure | Retry succeeds | - | - |
| UT-SER-005 | Compensation trigger | Step failure | Rollback executed | Compensable steps | - |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-SER-001 | End-to-end workflow | Multi-step workflow | All steps complete | Temporal worker | - |
| IT-SER-002 | Approval flow | Sensitive action | Blocked until approved | Approval policy | - |
| IT-SER-003 | Worker restart recovery | Kill worker mid-flow | Workflow resumes | Temporal cluster | - |
| IT-SER-004 | Timeout handling | Long-running step | Workflow times out | Slow tool | - |

- min_line_coverage: 85
- min_branch_coverage: 75

## 8. Edge Cases

### Boundary Conditions

- Empty workflow (no steps)
- Workflow with single step
- Maximum steps reached
- Approval at workflow end vs middle

### Concurrency

- Same workflow triggered twice
- Approval while workflow progressing
- Tool execution timeout during approval

### Failure Modes

- Temporal server unavailable
- Tool execution timeout
- Approval service down
- Compensation action fails

## 9. Error Handling

### Error Types

| Type | Retryable | Handler |
|------|-----------|---------|
| ToolExecutionError | depends | Retry if transient, compensate if not |
| ApprovalTimeoutError | no | Cancel workflow, notify user |
| TemporalError | yes | Automatic retry by Temporal |
| ValidationError | no | Fail workflow immediately |
| CompensationError | no | Alert ops, manual intervention |

- max_retries: 3
- backoff_strategy: exponential
- compensation_timeout: 300

## 10. Performance

- p50: 100
- p95: 500
- p99: 2000
- target_rps: 100
- memory_limit: 512
- max_concurrent_workflows: 50
- step_timeout: 60

## 11. Security

- requires_auth: true
- auth_method: JWT
- handles_pii: true
- encryption_at_rest: true
- encryption_in_transit: true

### Roles

| Role | Permissions |
|------|-------------|
| admin | Manage tools, view all workflows |
| operator | Execute workflows, approve actions |
| approver | Approve/reject only |
| viewer | Read-only workflow status |

### Security Controls

- Tool inputs sanitized against injection
- Sensitive outputs redacted in logs
- Approval actions require re-authentication
- All executions fully audited
- Prompt injection detection for AI inputs

## 12. Implementation

### Algorithms

- **Workflow Execution**: Temporal activity-based with checkpointing
- **Approval Routing**: Rule-based assignment with escalation
- **Compensation**: Reverse-order step rollback

### Patterns

- **Saga Pattern**: Distributed transactions with compensation
- **State Machine**: Workflow status transitions
- **Strategy Pattern**: Tool execution strategies

### Constraints

- Tools must be registered before use
- Sensitive tools require approval policy
- Compensation must be defined for reversible actions
- Workflow state is immutable (append-only)

## 13. Acceptance

### Criteria

- [ ] Workflows execute durably (survive worker restart)
- [ ] Tools validate inputs against schema
- [ ] Sensitive actions blocked until human approval
- [ ] Failed steps trigger compensation
- [ ] Audit trail captures all actions
- [ ] Dry-run mode produces no side effects

### Definition of Done

- [ ] Temporal workflows implemented
- [ ] Tool registry with 10+ tools
- [ ] Approval flow with notifications
- [ ] Compensation logic tested
- [ ] Unit tests >85% coverage
- [ ] Integration tests with Temporal
- [ ] Security review passed

# Block Specification: {{NAME}}

## 0. Block Configuration

### 0.1: Hierarchy

- block_type: {{BLOCK_TYPE}}
- parent: {{PARENT_PATH}}

### 0.2: Sub-Blocks

<!-- List sub-blocks if this is a component or module -->
<!-- Format: - sub-block-name - Description of the sub-block -->

### 0.3: Scoped Rules

<!-- Define rules that apply to this block and its descendants -->
<!-- These rules inherit from parent blocks and add additional constraints -->

| ID | Name | Category | Severity | Sections | Validator | Description |
|----|------|----------|----------|----------|-----------|-------------|
| | | | | | | |

### 0.4: Same-As References

<!-- Reference sections from other blocks to avoid duplication -->
<!-- Modes: replace (overwrite), extend (append lists), merge (deep merge) -->

| Target | Source | Source Section | Mode |
|--------|--------|----------------|------|
| | | | |

---

## 1. Metadata

- spec_id: {{SPEC_ID}}
- version: 1.0.0
- status: draft
- tech_stack:
- author:
- created:
- updated:

## 2. Overview

### Summary

[Brief description of this block's purpose and responsibilities]

### Goals

- [Goal 1]
- [Goal 2]

### Non-Goals

- [Non-goal 1]

### Background

[Background context and motivation for this block]

## 3. Inputs

### User Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| | | | | |

### System Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| | | | | |

### Environment Variables

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| | | | | |

## 4. Outputs

### Return Values

- [Return value 1]

### Side Effects

- [Side effect 1]

### Events

- [Event 1]

## 5. Dependencies

### Internal

- [Internal dependency 1]

### External

- [External dependency 1]

### Services

- [Service dependency 1]

## 6. API Contract

### Endpoints

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| | | | | |

### Error Codes

| Code | Description |
|------|-------------|
| | |

## 7. Test Cases

### Unit Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| UT-001 | | | | | |

### Integration Tests

| ID | Description | Input | Expected | Setup | Teardown |
|----|-------------|-------|----------|-------|----------|
| IT-001 | | | | | |

- min_line_coverage: 80
- min_branch_coverage: 70

## 8. Edge Cases

### Boundary Conditions

- [Boundary condition 1]

### Concurrency

- [Concurrency concern 1]

### Failure Modes

- [Failure mode 1]

## 9. Error Handling

### Error Types

- [Error type 1]

- max_retries: 3
- backoff_strategy: exponential

## 10. Performance

- p50: 100
- p95: 500
- p99: 1000
- target_rps: 100
- memory_limit: 512

## 11. Security

- requires_auth: false
- auth_method:
- handles_pii: false
- encryption_at_rest: false
- encryption_in_transit: true

### Roles

- [Role 1]

## 12. Implementation

### Algorithms

- [Algorithm 1]

### Patterns

- [Pattern 1]

### Constraints

- [Constraint 1]

## 13. Acceptance

### Criteria

- [ ] [Criterion 1]
- [ ] [Criterion 2]

### Definition of Done

- [ ] Code complete
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Code reviewed

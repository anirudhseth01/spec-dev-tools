"""Built-in validation functions for rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.spec.block import BlockSpec


def check_auth_required(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that API endpoints require authentication.

    Args:
        block: The block being validated.
        section: The section content (security section).
        **kwargs: Additional validation arguments.

    Returns:
        Error message if validation fails, None if passes.
    """
    security = block.spec.security
    api = block.spec.api_contract

    # If there are API endpoints, auth should be required
    if api.endpoints and not security.requires_auth:
        return "API endpoints defined but authentication is not required"

    return None


def check_min_tests(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate minimum number of test cases.

    Args:
        block: The block being validated.
        section: The section content (test_cases section).
        **kwargs: Additional validation arguments.
            - min_unit_tests: Minimum number of unit tests required.
            - min_integration_tests: Minimum number of integration tests required.

    Returns:
        Error message if validation fails, None if passes.
    """
    min_unit = kwargs.get("min_unit_tests", 1)
    min_integration = kwargs.get("min_integration_tests", 0)

    test_cases = block.spec.test_cases
    unit_count = len(test_cases.unit_tests)
    integration_count = len(test_cases.integration_tests)

    errors = []

    if unit_count < min_unit:
        errors.append(f"Expected at least {min_unit} unit tests, found {unit_count}")

    if integration_count < min_integration:
        errors.append(
            f"Expected at least {min_integration} integration tests, found {integration_count}"
        )

    return "; ".join(errors) if errors else None


def check_https_required(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that all API endpoints use HTTPS.

    Args:
        block: The block being validated.
        section: The section content (api_contract section).
        **kwargs: Additional validation arguments.

    Returns:
        Error message if validation fails, None if passes.
    """
    api = block.spec.api_contract

    for endpoint in api.endpoints:
        # Check if path contains http:// (should be https://)
        if "http://" in endpoint.path.lower():
            return f"Endpoint {endpoint.path} uses HTTP instead of HTTPS"

    # Also check security settings
    if api.endpoints and not block.spec.security.encryption_in_transit:
        return "API endpoints defined but encryption in transit is not enabled"

    return None


def check_health_checks(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that health check endpoints are defined.

    Args:
        block: The block being validated.
        section: The section content (api_contract section).
        **kwargs: Additional validation arguments.
            - required_endpoints: List of required health endpoint paths.

    Returns:
        Error message if validation fails, None if passes.
    """
    required = kwargs.get("required_endpoints", ["/health", "/ready"])
    api = block.spec.api_contract

    if not api.endpoints:
        return None  # No API, no health checks needed

    endpoint_paths = [e.path.lower() for e in api.endpoints]

    missing = []
    for required_path in required:
        if not any(required_path.lower() in path for path in endpoint_paths):
            missing.append(required_path)

    if missing:
        return f"Missing health check endpoints: {', '.join(missing)}"

    return None


def check_error_handling(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that error handling is properly defined.

    Args:
        block: The block being validated.
        section: The section content (error_handling section).
        **kwargs: Additional validation arguments.
            - min_error_types: Minimum number of error types to define.

    Returns:
        Error message if validation fails, None if passes.
    """
    min_types = kwargs.get("min_error_types", 1)
    error_handling = block.spec.error_handling

    if len(error_handling.error_types) < min_types:
        return f"Expected at least {min_types} error types, found {len(error_handling.error_types)}"

    return None


def check_performance_targets(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that performance targets are reasonable.

    Args:
        block: The block being validated.
        section: The section content (performance section).
        **kwargs: Additional validation arguments.
            - max_p99_ms: Maximum allowed P99 latency.
            - min_rps: Minimum required RPS target.

    Returns:
        Error message if validation fails, None if passes.
    """
    max_p99 = kwargs.get("max_p99_ms", 5000)
    min_rps = kwargs.get("min_rps", 10)

    perf = block.spec.performance
    errors = []

    if perf.p99_ms > max_p99:
        errors.append(f"P99 latency ({perf.p99_ms}ms) exceeds maximum ({max_p99}ms)")

    if perf.target_rps < min_rps:
        errors.append(f"Target RPS ({perf.target_rps}) is below minimum ({min_rps})")

    # Validate latency ordering
    if not (perf.p50_ms <= perf.p95_ms <= perf.p99_ms):
        errors.append("Latency percentiles are not in order (p50 <= p95 <= p99)")

    return "; ".join(errors) if errors else None


def check_pii_encryption(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate that PII data has proper encryption.

    Args:
        block: The block being validated.
        section: The section content (security section).
        **kwargs: Additional validation arguments.

    Returns:
        Error message if validation fails, None if passes.
    """
    security = block.spec.security

    if security.handles_pii:
        errors = []

        if not security.encryption_at_rest:
            errors.append("PII handling requires encryption at rest")

        if not security.encryption_in_transit:
            errors.append("PII handling requires encryption in transit")

        if not security.requires_auth:
            errors.append("PII handling requires authentication")

        return "; ".join(errors) if errors else None

    return None


def check_coverage_targets(block: BlockSpec, section: Any, **kwargs: Any) -> str | None:
    """Validate test coverage targets.

    Args:
        block: The block being validated.
        section: The section content (test_cases section).
        **kwargs: Additional validation arguments.
            - min_line_coverage: Minimum line coverage percentage.
            - min_branch_coverage: Minimum branch coverage percentage.

    Returns:
        Error message if validation fails, None if passes.
    """
    min_line = kwargs.get("min_line_coverage", 80)
    min_branch = kwargs.get("min_branch_coverage", 70)

    test_cases = block.spec.test_cases
    errors = []

    if test_cases.min_line_coverage < min_line:
        errors.append(
            f"Line coverage target ({test_cases.min_line_coverage}%) "
            f"is below minimum ({min_line}%)"
        )

    if test_cases.min_branch_coverage < min_branch:
        errors.append(
            f"Branch coverage target ({test_cases.min_branch_coverage}%) "
            f"is below minimum ({min_branch}%)"
        )

    return "; ".join(errors) if errors else None


# Registry of built-in validators
VALIDATORS: dict[str, Any] = {
    "check_auth_required": check_auth_required,
    "check_min_tests": check_min_tests,
    "check_https_required": check_https_required,
    "check_health_checks": check_health_checks,
    "check_error_handling": check_error_handling,
    "check_performance_targets": check_performance_targets,
    "check_pii_encryption": check_pii_encryption,
    "check_coverage_targets": check_coverage_targets,
}


def get_validator(name: str) -> Any | None:
    """Get a validator function by name.

    Args:
        name: Name of the validator function.

    Returns:
        Validator function or None if not found.
    """
    return VALIDATORS.get(name)

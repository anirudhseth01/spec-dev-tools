"""Tests for RulesEngine."""

from pathlib import Path

import pytest

from src.rules.engine import RulesEngine, load_rules_from_yaml, save_rules_to_yaml
from src.rules.schemas import Rule, RuleCategory, RuleLevel, RuleSeverity, MergeMode, SameAsReference
from src.spec.block import BlockSpec, BlockType
from src.spec.schemas import (
    Spec,
    Metadata,
    Overview,
    SecurityRequirements,
    TestCases,
    TestCase,
    APIContract,
    Endpoint,
    SpecStatus,
)


class TestRulesEngineLoading:
    """Tests for loading rules from configuration."""

    def test_load_global_rules(self, sample_global_rules: list[Rule], project_dir: Path) -> None:
        """Test loading global rules from yaml."""
        engine = RulesEngine(project_dir)

        assert len(engine.global_rules) == 2
        rule_ids = {r.id for r in engine.global_rules}
        assert "TEST-001" in rule_ids
        assert "SEC-001" in rule_ids

    def test_load_global_rules_no_file(self, temp_dir: Path) -> None:
        """Test loading when no rules file exists."""
        engine = RulesEngine(temp_dir)
        assert engine.global_rules == []

    def test_load_rules_from_yaml(self, sample_global_rules: list[Rule], project_dir: Path) -> None:
        """Test load_rules_from_yaml helper."""
        rules_file = project_dir / ".spec-dev" / "global-rules.yaml"
        rules = load_rules_from_yaml(rules_file)

        assert len(rules) == 2
        assert rules[0].id == "TEST-001"

    def test_save_rules_to_yaml(self, temp_dir: Path) -> None:
        """Test save_rules_to_yaml helper."""
        rules = [
            Rule(
                id="NEW-001",
                name="New Rule",
                level=RuleLevel.GLOBAL,
                category=RuleCategory.TESTING,
                severity=RuleSeverity.INFO,
            ),
        ]

        rules_file = temp_dir / "rules.yaml"
        save_rules_to_yaml(rules, rules_file)

        # Reload and verify
        loaded = load_rules_from_yaml(rules_file)
        assert len(loaded) == 1
        assert loaded[0].id == "NEW-001"


class TestRulesEngineEffectiveRules:
    """Tests for calculating effective rules."""

    def test_get_effective_rules_global_only(
        self, sample_global_rules: list[Rule], project_dir: Path, sample_block_spec: BlockSpec
    ) -> None:
        """Test effective rules with global rules only."""
        engine = RulesEngine(project_dir)
        effective = engine.get_effective_rules(sample_block_spec)

        assert len(effective) == 2

    def test_get_effective_rules_with_scoped(
        self, sample_global_rules: list[Rule], project_dir: Path, sample_block_spec: BlockSpec
    ) -> None:
        """Test effective rules including scoped rules."""
        # Add scoped rule to block
        scoped_rule = Rule(
            id="SCOPED-001",
            name="Scoped Rule",
            level=RuleLevel.SCOPED,
            category=RuleCategory.SECURITY,
            severity=RuleSeverity.WARNING,
        )
        sample_block_spec.scoped_rules = [scoped_rule]

        engine = RulesEngine(project_dir)
        effective = engine.get_effective_rules(sample_block_spec)

        assert len(effective) == 3
        rule_ids = {r.id for r in effective}
        assert "SCOPED-001" in rule_ids

    def test_get_effective_rules_inherits_from_ancestors(
        self, sample_global_rules: list[Rule], project_dir: Path, temp_dir: Path
    ) -> None:
        """Test that scoped rules are inherited from ancestors."""
        # Create parent with scoped rule
        parent_spec = Spec(name="Parent", metadata=Metadata(spec_id="parent"))
        parent = BlockSpec(
            path="parent",
            name="Parent",
            directory=temp_dir / "specs" / "parent",
            spec=parent_spec,
            block_type=BlockType.ROOT,
        )
        parent.scoped_rules = [
            Rule(
                id="PARENT-001",
                name="Parent Rule",
                level=RuleLevel.SCOPED,
                category=RuleCategory.TESTING,
                severity=RuleSeverity.WARNING,
            )
        ]

        # Create child
        child_spec = Spec(name="Child", metadata=Metadata(spec_id="child"))
        child = BlockSpec(
            path="parent/child",
            name="Child",
            directory=temp_dir / "specs" / "parent" / "child",
            spec=child_spec,
            block_type=BlockType.LEAF,
            parent=parent,
        )

        engine = RulesEngine(project_dir)
        effective = engine.get_effective_rules(child)

        # Should have global + parent scoped rules
        rule_ids = {r.id for r in effective}
        assert "TEST-001" in rule_ids
        assert "SEC-001" in rule_ids
        assert "PARENT-001" in rule_ids


class TestRulesEngineSameAs:
    """Tests for same-as reference resolution."""

    def test_resolve_same_as_replace(self, temp_dir: Path) -> None:
        """Test same-as with replace mode."""
        # Create source block with security settings
        source_spec = Spec(
            name="Source",
            metadata=Metadata(spec_id="source"),
            security=SecurityRequirements(
                requires_auth=True,
                auth_method="JWT",
                roles=["admin", "user"],
            ),
        )
        source = BlockSpec(
            path="source",
            name="Source",
            directory=temp_dir / "source",
            spec=source_spec,
            block_type=BlockType.COMPONENT,
        )

        # Create target block with same-as reference
        target_spec = Spec(
            name="Target",
            metadata=Metadata(spec_id="target"),
            security=SecurityRequirements(
                requires_auth=False,
            ),
        )
        target = BlockSpec(
            path="target",
            name="Target",
            directory=temp_dir / "target",
            spec=target_spec,
            block_type=BlockType.COMPONENT,
            same_as_refs=[
                SameAsReference(
                    target_section="security",
                    source_block="source",
                    merge_mode=MergeMode.REPLACE,
                )
            ],
        )

        engine = RulesEngine(temp_dir)
        all_blocks = {"source": source, "target": target}
        resolved = engine.resolve_same_as(target, all_blocks)

        # Security should be copied from source
        assert resolved.spec.security.requires_auth is True
        assert resolved.spec.security.auth_method == "JWT"
        assert resolved.spec.security.roles == ["admin", "user"]

    def test_resolve_same_as_extend(self, temp_dir: Path) -> None:
        """Test same-as with extend mode."""
        source_spec = Spec(
            name="Source",
            metadata=Metadata(spec_id="source"),
            security=SecurityRequirements(
                roles=["admin", "user"],
            ),
        )
        source = BlockSpec(
            path="source",
            name="Source",
            directory=temp_dir / "source",
            spec=source_spec,
            block_type=BlockType.COMPONENT,
        )

        target_spec = Spec(
            name="Target",
            metadata=Metadata(spec_id="target"),
            security=SecurityRequirements(
                roles=["guest"],
            ),
        )
        target = BlockSpec(
            path="target",
            name="Target",
            directory=temp_dir / "target",
            spec=target_spec,
            block_type=BlockType.COMPONENT,
            same_as_refs=[
                SameAsReference(
                    target_section="security",
                    source_block="source",
                    merge_mode=MergeMode.EXTEND,
                )
            ],
        )

        engine = RulesEngine(temp_dir)
        all_blocks = {"source": source, "target": target}
        resolved = engine.resolve_same_as(target, all_blocks)

        # Roles should be extended
        assert "guest" in resolved.spec.security.roles
        assert "admin" in resolved.spec.security.roles
        assert "user" in resolved.spec.security.roles

    def test_resolve_same_as_merge(self, temp_dir: Path) -> None:
        """Test same-as with merge mode."""
        source_spec = Spec(
            name="Source",
            metadata=Metadata(spec_id="source"),
            security=SecurityRequirements(
                requires_auth=True,
                roles=["admin"],
            ),
        )
        source = BlockSpec(
            path="source",
            name="Source",
            directory=temp_dir / "source",
            spec=source_spec,
            block_type=BlockType.COMPONENT,
        )

        target_spec = Spec(
            name="Target",
            metadata=Metadata(spec_id="target"),
            security=SecurityRequirements(
                roles=["user"],
                auth_method="OAuth",
            ),
        )
        target = BlockSpec(
            path="target",
            name="Target",
            directory=temp_dir / "target",
            spec=target_spec,
            block_type=BlockType.COMPONENT,
            same_as_refs=[
                SameAsReference(
                    target_section="security",
                    source_block="source",
                    merge_mode=MergeMode.MERGE,
                )
            ],
        )

        engine = RulesEngine(temp_dir)
        all_blocks = {"source": source, "target": target}
        resolved = engine.resolve_same_as(target, all_blocks)

        # Should merge: roles combined, auth_method kept from target
        assert "user" in resolved.spec.security.roles
        assert "admin" in resolved.spec.security.roles
        assert resolved.spec.security.auth_method == "OAuth"


class TestRulesEngineValidation:
    """Tests for rule validation."""

    def test_validate_passes(self, project_dir: Path, sample_spec: Spec, temp_dir: Path) -> None:
        """Test validation with no violations."""
        block = BlockSpec(
            path="test",
            name="Test",
            directory=temp_dir / "test",
            spec=sample_spec,
            block_type=BlockType.COMPONENT,
        )

        engine = RulesEngine(project_dir)
        violations = engine.validate(block)

        # sample_spec has auth required and enough tests
        assert len(violations) == 0

    def test_validate_fails_auth(self, sample_global_rules: list[Rule], project_dir: Path, temp_dir: Path) -> None:
        """Test validation catches missing auth."""
        spec = Spec(
            name="No Auth",
            metadata=Metadata(spec_id="no-auth"),
            security=SecurityRequirements(requires_auth=False),
            api_contract=APIContract(
                endpoints=[
                    Endpoint(method="GET", path="/api/test", description="Test endpoint")
                ]
            ),
        )
        block = BlockSpec(
            path="no-auth",
            name="No Auth",
            directory=temp_dir / "no-auth",
            spec=spec,
            block_type=BlockType.COMPONENT,
        )

        engine = RulesEngine(project_dir)
        violations = engine.validate(block)

        # Should have auth violation
        auth_violations = [v for v in violations if v.rule.id == "SEC-001"]
        assert len(auth_violations) > 0

    def test_validate_fails_min_tests(
        self, sample_global_rules: list[Rule], project_dir: Path, temp_dir: Path
    ) -> None:
        """Test validation catches insufficient tests."""
        spec = Spec(
            name="Few Tests",
            metadata=Metadata(spec_id="few-tests"),
            test_cases=TestCases(
                unit_tests=[
                    TestCase(test_id="UT-001", description="Only one test")
                ],
            ),
        )
        block = BlockSpec(
            path="few-tests",
            name="Few Tests",
            directory=temp_dir / "few-tests",
            spec=spec,
            block_type=BlockType.COMPONENT,
        )

        engine = RulesEngine(project_dir)
        violations = engine.validate(block)

        # Should have test count violation (requires 2, has 1)
        test_violations = [v for v in violations if v.rule.id == "TEST-001"]
        assert len(test_violations) > 0

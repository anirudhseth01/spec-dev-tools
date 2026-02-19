"""Rules engine for validating specifications."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from src.rules.schemas import MergeMode, Rule, RuleLevel, RuleViolation, SameAsReference
from src.rules.validators import get_validator
from src.spec.block import BlockSpec


class RulesEngine:
    """Engine for loading, managing, and validating rules against specifications.

    The rules engine supports three levels of rules:
    - Global: Apply to all blocks in the project
    - Scoped: Apply to a block and all its descendants
    - Local: Apply only to a specific block

    Rules are combined with proper precedence (local > scoped > global).
    """

    def __init__(self, project_root: Path | str) -> None:
        """Initialize the rules engine.

        Args:
            project_root: Root directory of the project.
        """
        self.project_root = Path(project_root)
        self.global_rules: list[Rule] = []
        self._load_global_rules()

    def _load_global_rules(self) -> None:
        """Load global rules from .spec-dev/global-rules.yaml."""
        rules_path = self.project_root / ".spec-dev" / "global-rules.yaml"

        if not rules_path.exists():
            return

        try:
            content = rules_path.read_text()
            data = yaml.safe_load(content) or {}
            rules_data = data.get("rules", [])

            for rule_dict in rules_data:
                rule = Rule.from_dict(rule_dict)
                if rule.enabled:
                    self.global_rules.append(rule)

        except (yaml.YAMLError, OSError) as e:
            # Log error but don't fail - rules are optional
            print(f"Warning: Could not load global rules: {e}")

    def get_effective_rules(self, block: BlockSpec) -> list[Rule]:
        """Get all rules that apply to a block.

        Combines global rules, ancestor scoped rules, and block's own scoped rules.
        Rules are returned in order of precedence (global first, then ancestors,
        then local).

        Args:
            block: The block to get rules for.

        Returns:
            List of applicable rules.
        """
        rules: list[Rule] = []

        # Add global rules
        rules.extend(self.global_rules)

        # Add scoped rules from ancestors (root to parent)
        ancestors = block.get_ancestors()
        for ancestor in ancestors:
            rules.extend(ancestor.scoped_rules)

        # Add block's own scoped rules
        rules.extend(block.scoped_rules)

        return rules

    def resolve_same_as(
        self, block: BlockSpec, all_blocks: dict[str, BlockSpec]
    ) -> BlockSpec:
        """Apply same-as references to copy sections from source blocks.

        Creates a copy of the block with sections populated from source blocks
        according to the same-as references defined in the block.

        Args:
            block: The block to resolve references for.
            all_blocks: Dictionary mapping block paths to BlockSpec objects.

        Returns:
            New BlockSpec with resolved same-as references.
        """
        if not block.same_as_refs:
            return block

        # Create a deep copy of the block to avoid modifying original
        resolved_block = copy.deepcopy(block)

        for ref in block.same_as_refs:
            source_block = self._find_source_block(block, ref.source_block, all_blocks)
            if source_block is None:
                continue

            source_section = ref.source_section or ref.target_section
            self._apply_same_as(resolved_block, ref.target_section, source_block, source_section, ref.merge_mode)

        return resolved_block

    def _find_source_block(
        self, current_block: BlockSpec, source_path: str, all_blocks: dict[str, BlockSpec]
    ) -> BlockSpec | None:
        """Find a source block by path.

        Supports both absolute paths (e.g., "auth-service") and relative
        paths (e.g., "../common").

        Args:
            current_block: The current block (for resolving relative paths).
            source_path: Path to the source block.
            all_blocks: Dictionary of all blocks.

        Returns:
            Source BlockSpec or None if not found.
        """
        # Handle relative paths
        if source_path.startswith("../"):
            parts = current_block.path.split("/")
            rel_parts = source_path.split("/")

            # Go up for each ../
            up_count = 0
            remaining = []
            for part in rel_parts:
                if part == "..":
                    up_count += 1
                else:
                    remaining.append(part)

            if up_count >= len(parts):
                # Can't go up past root
                base_parts = []
            else:
                base_parts = parts[:-up_count] if up_count > 0 else parts

            resolved_path = "/".join(base_parts + remaining)
            return all_blocks.get(resolved_path)

        # Handle absolute paths
        return all_blocks.get(source_path)

    def _apply_same_as(
        self,
        target_block: BlockSpec,
        target_section: str,
        source_block: BlockSpec,
        source_section: str,
        merge_mode: MergeMode,
    ) -> None:
        """Apply a same-as reference to copy/merge a section.

        Args:
            target_block: Block to modify.
            target_section: Section name in target block.
            source_block: Block to copy from.
            source_section: Section name in source block.
            merge_mode: How to merge the sections.
        """
        spec = target_block.spec
        source_spec = source_block.spec

        # Map section names to spec attributes
        section_map = {
            "security": ("security", "security"),
            "performance": ("performance", "performance"),
            "error_handling": ("error_handling", "error_handling"),
            "test_cases": ("test_cases", "test_cases"),
            "api_contract": ("api_contract", "api_contract"),
            "dependencies": ("dependencies", "dependencies"),
            "edge_cases": ("edge_cases", "edge_cases"),
            "implementation": ("implementation", "implementation"),
            "acceptance": ("acceptance", "acceptance"),
        }

        if target_section not in section_map or source_section not in section_map:
            return

        target_attr = section_map[target_section][0]
        source_attr = section_map[source_section][0]

        source_value = getattr(source_spec, source_attr)
        target_value = getattr(spec, target_attr)

        if merge_mode == MergeMode.REPLACE:
            setattr(spec, target_attr, copy.deepcopy(source_value))
        elif merge_mode == MergeMode.EXTEND:
            self._extend_section(target_value, source_value)
        elif merge_mode == MergeMode.MERGE:
            self._merge_section(target_value, source_value)

    def _extend_section(self, target: Any, source: Any) -> None:
        """Extend target section with source items (lists only).

        Args:
            target: Target section object.
            source: Source section object.
        """
        # Get list attributes and extend them
        for attr in dir(source):
            if attr.startswith("_"):
                continue
            source_val = getattr(source, attr, None)
            target_val = getattr(target, attr, None)
            if isinstance(source_val, list) and isinstance(target_val, list):
                target_val.extend(source_val)

    def _merge_section(self, target: Any, source: Any) -> None:
        """Deep merge target section with source.

        Args:
            target: Target section object.
            source: Source section object.
        """
        for attr in dir(source):
            if attr.startswith("_"):
                continue
            source_val = getattr(source, attr, None)
            target_val = getattr(target, attr, None)

            if source_val is None:
                continue

            if isinstance(source_val, list) and isinstance(target_val, list):
                # Merge lists, avoiding duplicates for simple types
                for item in source_val:
                    if item not in target_val:
                        target_val.append(item)
            elif isinstance(source_val, dict) and isinstance(target_val, dict):
                # Merge dicts
                target_val.update(source_val)
            elif target_val is None or target_val == "" or target_val == 0:
                # Only set if target is empty/default
                setattr(target, attr, source_val)

    def validate(self, block: BlockSpec) -> list[RuleViolation]:
        """Validate a block against all applicable rules.

        Args:
            block: The block to validate.

        Returns:
            List of rule violations found.
        """
        violations: list[RuleViolation] = []
        rules = self.get_effective_rules(block)

        for rule in rules:
            if not rule.enabled:
                continue

            # Run validator for each applicable section
            sections = rule.applies_to_sections or ["all"]

            for section in sections:
                violation = self._run_validator(rule, block, section)
                if violation:
                    violations.append(violation)

        return violations

    def _run_validator(
        self, rule: Rule, block: BlockSpec, section_name: str
    ) -> RuleViolation | None:
        """Execute a single validation function.

        Args:
            rule: The rule to validate.
            block: The block to validate against.
            section_name: Name of the section being validated.

        Returns:
            RuleViolation if validation fails, None otherwise.
        """
        validator_fn = get_validator(rule.validation_fn)
        if validator_fn is None:
            return None

        # Get section content
        section_content = self._get_section_content(block, section_name)

        try:
            error_message = validator_fn(block, section_content, **rule.validation_args)
            if error_message:
                return RuleViolation(
                    rule=rule,
                    block_path=block.path,
                    section=section_name,
                    message=error_message,
                )
        except Exception as e:
            return RuleViolation(
                rule=rule,
                block_path=block.path,
                section=section_name,
                message=f"Validator error: {str(e)}",
            )

        return None

    def _get_section_content(self, block: BlockSpec, section_name: str) -> Any:
        """Get section content from a block.

        Args:
            block: The block to get section from.
            section_name: Name of the section.

        Returns:
            Section content or None.
        """
        section_map = {
            "metadata": block.spec.metadata,
            "overview": block.spec.overview,
            "inputs": block.spec.inputs,
            "outputs": block.spec.outputs,
            "dependencies": block.spec.dependencies,
            "api_contract": block.spec.api_contract,
            "api": block.spec.api_contract,
            "test_cases": block.spec.test_cases,
            "tests": block.spec.test_cases,
            "edge_cases": block.spec.edge_cases,
            "error_handling": block.spec.error_handling,
            "errors": block.spec.error_handling,
            "performance": block.spec.performance,
            "security": block.spec.security,
            "implementation": block.spec.implementation,
            "acceptance": block.spec.acceptance,
            "all": block.spec,
        }

        return section_map.get(section_name.lower())


def load_rules_from_yaml(yaml_path: Path | str) -> list[Rule]:
    """Load rules from a YAML file.

    Args:
        yaml_path: Path to the YAML file.

    Returns:
        List of Rule objects.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        return []

    try:
        content = yaml_path.read_text()
        data = yaml.safe_load(content) or {}
        rules_data = data.get("rules", [])
        return [Rule.from_dict(r) for r in rules_data]
    except (yaml.YAMLError, OSError):
        return []


def save_rules_to_yaml(rules: list[Rule], yaml_path: Path | str) -> None:
    """Save rules to a YAML file.

    Args:
        rules: List of rules to save.
        yaml_path: Path to the YAML file.
    """
    yaml_path = Path(yaml_path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"rules": [rule.to_dict() for rule in rules]}

    yaml_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

"""Manages rules context to prevent context window overflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.rules.schemas import Rule, RuleCategory, RuleSeverity, RuleLevel


@dataclass
class ContextBudget:
    """Token budget for rules context."""

    max_tokens: int = 4000          # Max tokens for rules
    reserved_for_errors: int = 500  # Reserve space for error rules
    reserved_for_security: int = 500 # Reserve space for security rules
    current_usage: int = 0

    @property
    def remaining(self) -> int:
        return self.max_tokens - self.current_usage

    def can_fit(self, tokens: int) -> bool:
        return self.current_usage + tokens <= self.max_tokens

    def consume(self, tokens: int) -> bool:
        if self.can_fit(tokens):
            self.current_usage += tokens
            return True
        return False


@dataclass
class PrioritizedRule:
    """A rule with computed priority score."""

    rule: Rule
    priority_score: float
    token_estimate: int
    included: bool = False
    reason: str = ""


@dataclass
class RulesContextPack:
    """A packaged set of rules that fits within context budget."""

    included_rules: list[Rule]
    excluded_rules: list[Rule]
    total_tokens: int
    budget: ContextBudget
    summary: str  # Human-readable summary of what was included/excluded

    def to_prompt(self) -> str:
        """Convert to prompt-ready format."""
        lines = ["# Active Rules\n"]

        # Group by category
        by_category: dict[str, list[Rule]] = {}
        for rule in self.included_rules:
            cat = rule.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rule)

        for category, rules in by_category.items():
            lines.append(f"## {category.title()}")
            for rule in rules:
                severity_marker = {
                    "error": "🔴",
                    "warning": "🟡",
                    "info": "🔵",
                }.get(rule.severity.value, "⚪")

                lines.append(f"- {severity_marker} **{rule.id}**: {rule.name}")
                if rule.description:
                    lines.append(f"  - {rule.description}")
            lines.append("")

        if self.excluded_rules:
            lines.append(f"\n*Note: {len(self.excluded_rules)} lower-priority rules omitted to fit context.*")

        return "\n".join(lines)


class RulesContextManager:
    """Manages rules to fit within LLM context windows.

    Strategies:
    1. Priority-based selection (errors > warnings > info)
    2. Relevance filtering (only rules for target sections)
    3. Deduplication (remove redundant rules)
    4. Summarization (condense similar rules)
    5. Chunking (split across multiple calls if needed)
    """

    def __init__(self, max_tokens: int = 4000):
        """Initialize context manager.

        Args:
            max_tokens: Maximum tokens to allocate for rules.
        """
        self.max_tokens = max_tokens

        # Priority weights
        self.severity_weights = {
            RuleSeverity.ERROR: 100,
            RuleSeverity.WARNING: 50,
            RuleSeverity.INFO: 10,
        }

        self.category_weights = {
            RuleCategory.SECURITY: 80,
            RuleCategory.TESTING: 60,
            RuleCategory.API: 50,
            RuleCategory.PERFORMANCE: 40,
            RuleCategory.CODE_QUALITY: 30,
            RuleCategory.DOCUMENTATION: 20,
        }

        self.level_weights = {
            RuleLevel.LOCAL: 100,   # Most specific = highest priority
            RuleLevel.SCOPED: 70,
            RuleLevel.GLOBAL: 40,
        }

    def pack_rules(
        self,
        rules: list[Rule],
        target_sections: list[str] | None = None,
        agent_name: str | None = None,
    ) -> RulesContextPack:
        """Pack rules into a context-fitting bundle.

        Args:
            rules: All applicable rules.
            target_sections: Only include rules for these sections.
            agent_name: Agent that will use these rules (for relevance).

        Returns:
            RulesContextPack with prioritized, fitting rules.
        """
        budget = ContextBudget(max_tokens=self.max_tokens)

        # Step 1: Filter by relevance
        relevant_rules = self._filter_relevant(rules, target_sections, agent_name)

        # Step 2: Prioritize
        prioritized = self._prioritize_rules(relevant_rules, target_sections)

        # Step 3: Pack into budget
        included, excluded = self._pack_to_budget(prioritized, budget)

        # Step 4: Generate summary
        summary = self._generate_summary(included, excluded)

        return RulesContextPack(
            included_rules=[p.rule for p in included],
            excluded_rules=[p.rule for p in excluded],
            total_tokens=budget.current_usage,
            budget=budget,
            summary=summary,
        )

    def _filter_relevant(
        self,
        rules: list[Rule],
        target_sections: list[str] | None,
        agent_name: str | None,
    ) -> list[Rule]:
        """Filter rules to only relevant ones."""
        if not target_sections:
            return rules

        relevant = []
        for rule in rules:
            # Include if rule applies to any target section
            if not rule.applies_to_sections:
                relevant.append(rule)  # Applies to all
            elif any(s in rule.applies_to_sections for s in target_sections):
                relevant.append(rule)
            elif "all" in rule.applies_to_sections:
                relevant.append(rule)

        return relevant

    def _prioritize_rules(
        self,
        rules: list[Rule],
        target_sections: list[str] | None,
    ) -> list[PrioritizedRule]:
        """Calculate priority scores and sort rules."""
        prioritized = []

        for rule in rules:
            score = self._calculate_priority(rule, target_sections)
            tokens = self._estimate_tokens(rule)

            prioritized.append(PrioritizedRule(
                rule=rule,
                priority_score=score,
                token_estimate=tokens,
            ))

        # Sort by priority (highest first)
        prioritized.sort(key=lambda p: p.priority_score, reverse=True)

        return prioritized

    def _calculate_priority(
        self,
        rule: Rule,
        target_sections: list[str] | None,
    ) -> float:
        """Calculate priority score for a rule."""
        score = 0.0

        # Base scores from weights
        score += self.severity_weights.get(rule.severity, 0)
        score += self.category_weights.get(rule.category, 0)
        score += self.level_weights.get(rule.level, 0)

        # Boost for exact section match
        if target_sections and rule.applies_to_sections:
            matches = sum(1 for s in target_sections if s in rule.applies_to_sections)
            score += matches * 20

        # Penalty for disabled rules (shouldn't happen, but safety)
        if not rule.enabled:
            score = 0

        return score

    def _estimate_tokens(self, rule: Rule) -> int:
        """Estimate token count for a rule."""
        # Rough estimate: ID + name + description + metadata
        text = f"{rule.id} {rule.name} {rule.description}"
        text += " ".join(rule.applies_to_sections)
        return len(text) // 4 + 20  # +20 for formatting

    def _pack_to_budget(
        self,
        prioritized: list[PrioritizedRule],
        budget: ContextBudget,
    ) -> tuple[list[PrioritizedRule], list[PrioritizedRule]]:
        """Pack rules into budget, respecting reservations."""
        included = []
        excluded = []

        # First pass: Must-include (errors and security)
        for pr in prioritized:
            if pr.rule.severity == RuleSeverity.ERROR:
                if budget.consume(pr.token_estimate):
                    pr.included = True
                    pr.reason = "error severity (mandatory)"
                    included.append(pr)

        # Second pass: High-priority security rules
        for pr in prioritized:
            if pr.included:
                continue
            if pr.rule.category == RuleCategory.SECURITY:
                if budget.consume(pr.token_estimate):
                    pr.included = True
                    pr.reason = "security category (high priority)"
                    included.append(pr)

        # Third pass: Everything else by priority
        for pr in prioritized:
            if pr.included:
                continue
            if budget.can_fit(pr.token_estimate):
                budget.consume(pr.token_estimate)
                pr.included = True
                pr.reason = "fits in budget"
                included.append(pr)
            else:
                pr.reason = "exceeded budget"
                excluded.append(pr)

        return included, excluded

    def _generate_summary(
        self,
        included: list[PrioritizedRule],
        excluded: list[PrioritizedRule],
    ) -> str:
        """Generate human-readable summary."""
        lines = []

        # Count by severity
        error_count = sum(1 for p in included if p.rule.severity == RuleSeverity.ERROR)
        warn_count = sum(1 for p in included if p.rule.severity == RuleSeverity.WARNING)
        info_count = sum(1 for p in included if p.rule.severity == RuleSeverity.INFO)

        lines.append(f"Included {len(included)} rules: {error_count} errors, {warn_count} warnings, {info_count} info")

        if excluded:
            lines.append(f"Excluded {len(excluded)} rules due to context limits")
            # List excluded error rules (should be rare)
            excluded_errors = [p for p in excluded if p.rule.severity == RuleSeverity.ERROR]
            if excluded_errors:
                lines.append(f"  WARNING: {len(excluded_errors)} error rules excluded!")
                for p in excluded_errors[:3]:
                    lines.append(f"    - {p.rule.id}: {p.rule.name}")

        return "\n".join(lines)

    def chunk_rules(
        self,
        rules: list[Rule],
        chunk_size: int = 2000,
    ) -> list[list[Rule]]:
        """Split rules into chunks for multi-turn processing.

        Args:
            rules: All rules to chunk.
            chunk_size: Max tokens per chunk.

        Returns:
            List of rule chunks.
        """
        chunks: list[list[Rule]] = []
        current_chunk: list[Rule] = []
        current_tokens = 0

        for rule in rules:
            tokens = self._estimate_tokens(rule)
            if current_tokens + tokens > chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [rule]
                current_tokens = tokens
            else:
                current_chunk.append(rule)
                current_tokens += tokens

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def create_rules_summary(self, rules: list[Rule]) -> str:
        """Create a condensed summary of many rules.

        Use when rules are too numerous to include individually.
        """
        lines = ["# Rules Summary\n"]

        # Group by category
        by_category: dict[str, list[Rule]] = {}
        for rule in rules:
            cat = rule.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(rule)

        for category, cat_rules in sorted(by_category.items()):
            error_count = sum(1 for r in cat_rules if r.severity == RuleSeverity.ERROR)
            warn_count = sum(1 for r in cat_rules if r.severity == RuleSeverity.WARNING)

            lines.append(f"## {category.title()} ({len(cat_rules)} rules)")
            lines.append(f"   - {error_count} blocking errors, {warn_count} warnings")

            # Just list IDs
            ids = [r.id for r in cat_rules[:5]]
            lines.append(f"   - Rules: {', '.join(ids)}" + ("..." if len(cat_rules) > 5 else ""))
            lines.append("")

        return "\n".join(lines)

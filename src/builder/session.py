"""Core session data structures for Spec Builder Mode."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SessionPhase(Enum):
    """Phase of the builder session."""

    DISCUSSION = "discussion"
    DESIGN = "design"
    REVIEW = "review"
    EXECUTION = "execution"
    COMPLETED = "completed"
    PAUSED = "paused"


class ResearchDepth(Enum):
    """Depth of research to perform for technology choices."""

    LIGHT = "light"  # Quick validation only
    MEDIUM = "medium"  # Fetch key documentation
    DEEP = "deep"  # Comprehensive research


# Discussion topics covered in order during the discussion phase
DISCUSSION_TOPICS = [
    {
        "id": "problem_scope",
        "name": "Problem & Scope",
        "questions": ["What problem?", "Users?", "Scale?"],
        "research_enabled": False,
    },
    {
        "id": "architecture",
        "name": "Architecture",
        "questions": ["Monolith vs microservices?", "Components?"],
        "research_enabled": False,
    },
    {
        "id": "tech_stack",
        "name": "Tech Stack",
        "questions": ["Language?", "Framework?", "Database?"],
        "research_enabled": True,
    },
    {
        "id": "api_design",
        "name": "API Design",
        "questions": ["REST/GraphQL/gRPC?", "Auth?", "Versioning?"],
        "research_enabled": False,
    },
    {
        "id": "data_model",
        "name": "Data Model",
        "questions": ["Entities?", "Relationships?", "Consistency?"],
        "research_enabled": False,
    },
    {
        "id": "security",
        "name": "Security",
        "questions": ["PII?", "Compliance?", "Encryption?"],
        "research_enabled": False,
    },
    {
        "id": "performance",
        "name": "Performance",
        "questions": ["Latency targets?", "Throughput?", "Caching?"],
        "research_enabled": False,
    },
    {
        "id": "integrations",
        "name": "Integrations",
        "questions": ["Third-party services?", "Internal systems?"],
        "research_enabled": True,
    },
    {
        "id": "deployment",
        "name": "Deployment",
        "questions": ["Environment?", "CI/CD?", "Monitoring?"],
        "research_enabled": False,
    },
]


@dataclass
class Option:
    """An option presented to the user during discussion."""

    id: str
    label: str
    description: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    recommendation_score: float = 0.5  # 0-1, higher = more recommended

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "pros": self.pros,
            "cons": self.cons,
            "recommendation_score": self.recommendation_score,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Option":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            label=data["label"],
            description=data["description"],
            pros=data.get("pros", []),
            cons=data.get("cons", []),
            recommendation_score=data.get("recommendation_score", 0.5),
        )


@dataclass
class Decision:
    """A decision made during the discussion phase."""

    id: str
    topic: str
    question: str
    options: list[Option] = field(default_factory=list)
    selected_option_id: str | None = None
    user_notes: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_decided(self) -> bool:
        """Check if a selection has been made."""
        return self.selected_option_id is not None

    @property
    def selected_option(self) -> Option | None:
        """Get the selected option."""
        if not self.selected_option_id:
            return None
        for opt in self.options:
            if opt.id == self.selected_option_id:
                return opt
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "topic": self.topic,
            "question": self.question,
            "options": [opt.to_dict() for opt in self.options],
            "selected_option_id": self.selected_option_id,
            "user_notes": self.user_notes,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Decision":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            topic=data["topic"],
            question=data["question"],
            options=[Option.from_dict(opt) for opt in data.get("options", [])],
            selected_option_id=data.get("selected_option_id"),
            user_notes=data.get("user_notes", ""),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if "timestamp" in data
            else datetime.now(),
        )


@dataclass
class BlockDesign:
    """Design for a single block in the hierarchy."""

    path: str  # e.g., "payment-system/gateway"
    name: str
    block_type: str  # "root", "component", "module", "leaf"
    description: str
    parent_path: str | None = None
    tech_stack: str = ""
    dependencies: list[str] = field(default_factory=list)
    api_endpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "name": self.name,
            "block_type": self.block_type,
            "description": self.description,
            "parent_path": self.parent_path,
            "tech_stack": self.tech_stack,
            "dependencies": self.dependencies,
            "api_endpoints": self.api_endpoints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BlockDesign":
        """Create from dictionary."""
        return cls(
            path=data["path"],
            name=data["name"],
            block_type=data["block_type"],
            description=data["description"],
            parent_path=data.get("parent_path"),
            tech_stack=data.get("tech_stack", ""),
            dependencies=data.get("dependencies", []),
            api_endpoints=data.get("api_endpoints", []),
        )


@dataclass
class HierarchyDesign:
    """Complete hierarchy design for the system."""

    root_name: str
    blocks: list[BlockDesign] = field(default_factory=list)
    cross_block_rules: list[dict[str, Any]] = field(default_factory=list)

    @property
    def root_block(self) -> BlockDesign | None:
        """Get the root block."""
        for block in self.blocks:
            if block.block_type == "root":
                return block
        return None

    def get_block(self, path: str) -> BlockDesign | None:
        """Get a block by path."""
        for block in self.blocks:
            if block.path == path:
                return block
        return None

    def get_children(self, parent_path: str) -> list[BlockDesign]:
        """Get child blocks of a parent."""
        return [b for b in self.blocks if b.parent_path == parent_path]

    def get_leaves(self) -> list[BlockDesign]:
        """Get all leaf blocks."""
        return [b for b in self.blocks if b.block_type == "leaf"]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "root_name": self.root_name,
            "blocks": [b.to_dict() for b in self.blocks],
            "cross_block_rules": self.cross_block_rules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HierarchyDesign":
        """Create from dictionary."""
        return cls(
            root_name=data["root_name"],
            blocks=[BlockDesign.from_dict(b) for b in data.get("blocks", [])],
            cross_block_rules=data.get("cross_block_rules", []),
        )


@dataclass
class ExecutionProgress:
    """Progress tracking for execution phase."""

    total_blocks: int = 0
    completed_blocks: int = 0
    current_block: str = ""
    block_statuses: dict[str, str] = field(
        default_factory=dict
    )  # path -> status (pending/running/completed/failed)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Check if all blocks are complete."""
        return self.completed_blocks >= self.total_blocks and self.total_blocks > 0

    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_blocks == 0:
            return 0.0
        return (self.completed_blocks / self.total_blocks) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_blocks": self.total_blocks,
            "completed_blocks": self.completed_blocks,
            "current_block": self.current_block,
            "block_statuses": self.block_statuses,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionProgress":
        """Create from dictionary."""
        return cls(
            total_blocks=data.get("total_blocks", 0),
            completed_blocks=data.get("completed_blocks", 0),
            current_block=data.get("current_block", ""),
            block_statuses=data.get("block_statuses", {}),
            errors=data.get("errors", []),
        )


@dataclass
class BuilderSession:
    """Complete builder session state.

    Tracks all information across the three phases:
    1. Discussion - Q&A decisions
    2. Design - Block hierarchy
    3. Execution - Implementation progress
    """

    id: str = field(default_factory=lambda: f"bs-{uuid.uuid4().hex[:8]}")
    name: str = ""
    phase: SessionPhase = SessionPhase.DISCUSSION
    research_depth: ResearchDepth = ResearchDepth.MEDIUM
    initial_description: str = ""

    # Discussion phase
    decisions: list[Decision] = field(default_factory=list)
    current_topic_index: int = 0

    # Reference repositories for pattern reuse
    reference_repos: list[dict] = field(default_factory=list)  # List of RepoAnalysis dicts

    # Design phase
    hierarchy_design: HierarchyDesign | None = None

    # Execution phase
    execution_progress: ExecutionProgress = field(default_factory=ExecutionProgress)
    deployment_scope: str = "configs"  # "configs" | "local" | "cloud"

    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    project_root: str = "."
    specs_dir: str = "specs"

    def __post_init__(self) -> None:
        """Initialize derived fields."""
        if isinstance(self.phase, str):
            self.phase = SessionPhase(self.phase)
        if isinstance(self.research_depth, str):
            self.research_depth = ResearchDepth(self.research_depth)

    @property
    def current_topic(self) -> dict[str, Any] | None:
        """Get the current discussion topic."""
        if 0 <= self.current_topic_index < len(DISCUSSION_TOPICS):
            return DISCUSSION_TOPICS[self.current_topic_index]
        return None

    @property
    def is_discussion_complete(self) -> bool:
        """Check if all discussion topics have been covered."""
        return self.current_topic_index >= len(DISCUSSION_TOPICS)

    def add_decision(self, decision: Decision) -> None:
        """Add a decision and update timestamp."""
        self.decisions.append(decision)
        self.updated_at = datetime.now()

    def get_decision(self, topic: str) -> Decision | None:
        """Get decision for a specific topic."""
        for decision in self.decisions:
            if decision.topic == topic:
                return decision
        return None

    def advance_topic(self) -> None:
        """Move to the next discussion topic."""
        self.current_topic_index += 1
        self.updated_at = datetime.now()

    def transition_to(self, phase: SessionPhase) -> None:
        """Transition to a new phase."""
        self.phase = phase
        self.updated_at = datetime.now()

    def add_reference_repo(self, repo_analysis: dict) -> None:
        """Add a reference repository analysis.

        Args:
            repo_analysis: RepoAnalysis as dict (use .to_dict()).
        """
        self.reference_repos.append(repo_analysis)
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "phase": self.phase.value,
            "research_depth": self.research_depth.value,
            "initial_description": self.initial_description,
            "decisions": [d.to_dict() for d in self.decisions],
            "current_topic_index": self.current_topic_index,
            "reference_repos": self.reference_repos,
            "hierarchy_design": self.hierarchy_design.to_dict()
            if self.hierarchy_design
            else None,
            "execution_progress": self.execution_progress.to_dict(),
            "deployment_scope": self.deployment_scope,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "project_root": self.project_root,
            "specs_dir": self.specs_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BuilderSession":
        """Create session from dictionary."""
        session = cls(
            id=data["id"],
            name=data["name"],
            phase=SessionPhase(data["phase"]),
            research_depth=ResearchDepth(data["research_depth"]),
            initial_description=data.get("initial_description", ""),
            decisions=[Decision.from_dict(d) for d in data.get("decisions", [])],
            current_topic_index=data.get("current_topic_index", 0),
            reference_repos=data.get("reference_repos", []),
            hierarchy_design=HierarchyDesign.from_dict(data["hierarchy_design"])
            if data.get("hierarchy_design")
            else None,
            execution_progress=ExecutionProgress.from_dict(
                data.get("execution_progress", {})
            ),
            deployment_scope=data.get("deployment_scope", "configs"),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(),
            project_root=data.get("project_root", "."),
            specs_dir=data.get("specs_dir", "specs"),
        )
        return session

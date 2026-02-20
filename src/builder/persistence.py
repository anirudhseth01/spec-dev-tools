"""Session persistence for Spec Builder Mode.

Handles saving and loading builder sessions to/from JSON files
in the .spec-dev/builder-sessions/ directory.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.builder.session import BuilderSession


class SessionPersistence:
    """Manages persistence of builder sessions to disk.

    Sessions are stored as JSON files in .spec-dev/builder-sessions/{session_id}.json
    """

    def __init__(self, project_dir: Path | str):
        """Initialize persistence manager.

        Args:
            project_dir: Project root directory.
        """
        self.project_dir = Path(project_dir)
        self.sessions_dir = self.project_dir / ".spec-dev" / "builder-sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.sessions_dir / f"{session_id}.json"

    def save(self, session: BuilderSession) -> None:
        """Save a session to disk.

        Args:
            session: The session to save.
        """
        session_file = self._session_path(session.id)

        # Convert datetime objects to ISO format strings for JSON
        session_dict = session.to_dict()

        with open(session_file, "w") as f:
            json.dump(session_dict, f, indent=2, default=self._json_serializer)

    def load(self, session_id: str) -> BuilderSession | None:
        """Load a session from disk.

        Args:
            session_id: The session ID to load.

        Returns:
            BuilderSession or None if not found.
        """
        session_file = self._session_path(session_id)
        if not session_file.exists():
            return None

        with open(session_file) as f:
            data = json.load(f)

        return BuilderSession.from_dict(data)

    def delete(self, session_id: str) -> bool:
        """Delete a session from disk.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        session_file = self._session_path(session_id)
        if session_file.exists():
            session_file.unlink()
            return True
        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions.

        Returns:
            List of session summary dicts with id, name, phase, updated_at.
        """
        sessions = []
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file) as f:
                    data = json.load(f)
                sessions.append(
                    {
                        "id": data.get("id", session_file.stem),
                        "name": data.get("name", ""),
                        "phase": data.get("phase", "unknown"),
                        "updated_at": data.get("updated_at", ""),
                        "created_at": data.get("created_at", ""),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                # Skip invalid session files
                continue

        # Sort by updated_at descending (most recent first)
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    def exists(self, session_id: str) -> bool:
        """Check if a session exists.

        Args:
            session_id: The session ID to check.

        Returns:
            True if session exists.
        """
        return self._session_path(session_id).exists()

    def get_latest_session(self) -> BuilderSession | None:
        """Get the most recently updated session.

        Returns:
            BuilderSession or None if no sessions exist.
        """
        sessions = self.list_sessions()
        if not sessions:
            return None
        return self.load(sessions[0]["id"])

    @staticmethod
    def _json_serializer(obj: Any) -> str:
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

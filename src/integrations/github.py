"""GitHub integration for creating PRs from generated code."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class PRInfo:
    """Information about a pull request."""

    number: int
    url: str
    title: str
    body: str
    branch: str
    base_branch: str
    state: str = "open"
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "number": self.number,
            "url": self.url,
            "title": self.title,
            "body": self.body,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "state": self.state,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class GitHubResult:
    """Result of a GitHub operation."""

    success: bool
    message: str
    pr_info: PRInfo | None = None
    errors: list[str] = field(default_factory=list)


class GitHubIntegration:
    """Integration with GitHub via gh CLI."""

    def __init__(self, repo_dir: Path):
        """Initialize GitHub integration.

        Args:
            repo_dir: Git repository directory.
        """
        self.repo_dir = repo_dir

    def _run_gh(self, args: list[str], capture_output: bool = True) -> tuple[int, str, str]:
        """Run gh CLI command.

        Args:
            args: Command arguments.
            capture_output: Whether to capture output.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        try:
            result = subprocess.run(
                ["gh"] + args,
                cwd=self.repo_dir,
                capture_output=capture_output,
                text=True,
                timeout=60,
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, "", "gh CLI not found. Install: https://cli.github.com/"
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def _run_git(self, args: list[str]) -> tuple[int, str, str]:
        """Run git command.

        Args:
            args: Command arguments.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return 1, "", "git not found"
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"

    def check_gh_auth(self) -> bool:
        """Check if gh CLI is authenticated.

        Returns:
            True if authenticated.
        """
        code, _, _ = self._run_gh(["auth", "status"])
        return code == 0

    def get_current_branch(self) -> str | None:
        """Get current git branch.

        Returns:
            Branch name or None.
        """
        code, stdout, _ = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        if code == 0:
            return stdout.strip()
        return None

    def get_default_branch(self) -> str:
        """Get default branch name.

        Returns:
            Default branch name (main or master).
        """
        code, stdout, _ = self._run_git(["symbolic-ref", "refs/remotes/origin/HEAD"])
        if code == 0:
            return stdout.strip().split("/")[-1]
        return "main"

    def create_branch(self, branch_name: str) -> bool:
        """Create and checkout a new branch.

        Args:
            branch_name: Name of the branch.

        Returns:
            True if successful.
        """
        code, _, _ = self._run_git(["checkout", "-b", branch_name])
        return code == 0

    def stage_files(self, files: list[str]) -> bool:
        """Stage files for commit.

        Args:
            files: List of file paths to stage.

        Returns:
            True if successful.
        """
        code, _, _ = self._run_git(["add"] + files)
        return code == 0

    def commit(self, message: str) -> bool:
        """Create a commit.

        Args:
            message: Commit message.

        Returns:
            True if successful.
        """
        code, _, _ = self._run_git(["commit", "-m", message])
        return code == 0

    def push(self, branch: str, set_upstream: bool = True) -> bool:
        """Push branch to remote.

        Args:
            branch: Branch name.
            set_upstream: Whether to set upstream.

        Returns:
            True if successful.
        """
        args = ["push"]
        if set_upstream:
            args.extend(["-u", "origin", branch])
        else:
            args.append(branch)

        code, _, _ = self._run_git(args)
        return code == 0

    def create_pr(
        self,
        title: str,
        body: str,
        base_branch: str | None = None,
        draft: bool = False,
    ) -> GitHubResult:
        """Create a pull request.

        Args:
            title: PR title.
            body: PR body/description.
            base_branch: Base branch (defaults to default branch).
            draft: Whether to create as draft.

        Returns:
            GitHubResult with PR info.
        """
        if not self.check_gh_auth():
            return GitHubResult(
                success=False,
                message="GitHub CLI not authenticated. Run: gh auth login",
                errors=["Not authenticated"],
            )

        args = ["pr", "create", "--title", title, "--body", body]

        if base_branch:
            args.extend(["--base", base_branch])

        if draft:
            args.append("--draft")

        code, stdout, stderr = self._run_gh(args)

        if code != 0:
            return GitHubResult(
                success=False,
                message=f"Failed to create PR: {stderr}",
                errors=[stderr],
            )

        # Parse PR URL from output
        pr_url = stdout.strip()

        # Get PR details
        pr_info = self._get_pr_info(pr_url)

        return GitHubResult(
            success=True,
            message=f"Created PR: {pr_url}",
            pr_info=pr_info,
        )

    def _get_pr_info(self, pr_url: str) -> PRInfo | None:
        """Get PR information from URL.

        Args:
            pr_url: PR URL.

        Returns:
            PRInfo or None.
        """
        # Extract PR number from URL
        parts = pr_url.rstrip("/").split("/")
        if len(parts) < 1:
            return None

        pr_number = parts[-1]

        code, stdout, _ = self._run_gh([
            "pr", "view", pr_number, "--json",
            "number,url,title,body,headRefName,baseRefName,state,createdAt"
        ])

        if code != 0:
            return None

        try:
            data = json.loads(stdout)
            return PRInfo(
                number=data["number"],
                url=data["url"],
                title=data["title"],
                body=data["body"],
                branch=data["headRefName"],
                base_branch=data["baseRefName"],
                state=data["state"],
                created_at=datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00")),
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def create_implementation_pr(
        self,
        spec_name: str,
        generated_files: list[str],
        spec_summary: str = "",
        dry_run: bool = False,
    ) -> GitHubResult:
        """Create a PR for spec implementation.

        Args:
            spec_name: Name of the spec.
            generated_files: List of generated file paths.
            spec_summary: Summary from spec overview.
            dry_run: If True, don't actually create PR.

        Returns:
            GitHubResult with operation result.
        """
        # Generate branch name
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"spec-impl/{spec_name}-{timestamp}"

        # Generate PR title and body
        title = f"feat: Implement {spec_name} from spec"

        body_lines = [
            "## Summary",
            "",
            spec_summary or f"Implementation of the {spec_name} specification.",
            "",
            "## Generated Files",
            "",
        ]

        for file in generated_files:
            body_lines.append(f"- `{file}`")

        body_lines.extend([
            "",
            "## Checklist",
            "",
            "- [ ] Code review completed",
            "- [ ] Tests passing",
            "- [ ] Documentation updated",
            "",
            "---",
            "*Generated by spec-dev-tools*",
        ])

        body = "\n".join(body_lines)

        if dry_run:
            return GitHubResult(
                success=True,
                message="Dry run - would create PR",
                pr_info=PRInfo(
                    number=0,
                    url="(dry-run)",
                    title=title,
                    body=body,
                    branch=branch_name,
                    base_branch=self.get_default_branch(),
                ),
            )

        # Create branch
        current_branch = self.get_current_branch()
        if not self.create_branch(branch_name):
            return GitHubResult(
                success=False,
                message=f"Failed to create branch: {branch_name}",
                errors=["Branch creation failed"],
            )

        # Stage files
        if not self.stage_files(generated_files):
            self._run_git(["checkout", current_branch or "main"])
            return GitHubResult(
                success=False,
                message="Failed to stage files",
                errors=["Staging failed"],
            )

        # Commit
        commit_msg = f"feat: Implement {spec_name}\n\nGenerated from spec: {spec_name}"
        if not self.commit(commit_msg):
            self._run_git(["checkout", current_branch or "main"])
            return GitHubResult(
                success=False,
                message="Failed to commit",
                errors=["Commit failed"],
            )

        # Push
        if not self.push(branch_name):
            self._run_git(["checkout", current_branch or "main"])
            return GitHubResult(
                success=False,
                message="Failed to push branch",
                errors=["Push failed"],
            )

        # Create PR
        result = self.create_pr(title, body)

        # Switch back to original branch
        if current_branch:
            self._run_git(["checkout", current_branch])

        return result


def create_pr_from_implementation(
    repo_dir: Path,
    spec_name: str,
    generated_files: list[str],
    spec_summary: str = "",
    dry_run: bool = False,
) -> GitHubResult:
    """Convenience function to create PR from implementation.

    Args:
        repo_dir: Repository directory.
        spec_name: Name of the spec.
        generated_files: List of generated files.
        spec_summary: Spec summary.
        dry_run: Whether to do a dry run.

    Returns:
        GitHubResult.
    """
    github = GitHubIntegration(repo_dir)
    return github.create_implementation_pr(
        spec_name=spec_name,
        generated_files=generated_files,
        spec_summary=spec_summary,
        dry_run=dry_run,
    )

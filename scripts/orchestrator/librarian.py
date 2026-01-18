"""Librarian check for AGENTS.md cognitive feedback enforcement."""

import logging
import subprocess
from pathlib import Path
from typing import List

from .config import ConfigManager
from .state import StateManager
from .utils import tc

logger = logging.getLogger(__name__)


class LibrarianCheck:
    """
    Ensures AGENTS.md is updated when patterns emerge.

    Tracks iterations with code changes but no AGENTS.md updates,
    and issues warnings when threshold exceeded. This enforces
    the cognitive feedback loop that makes Ralph Zero learn.
    """

    def __init__(self, config: ConfigManager, state: StateManager) -> None:
        """
        Initialize LibrarianCheck.

        Args:
            config: Configuration manager
            state: State manager
        """
        self.config = config
        self.state = state
        self.project_root = Path(".")

        # Track iterations without AGENTS.md updates
        self.iterations_without_update = 0
        self.warning_threshold = config.librarian.warning_after_iterations

    def check_and_warn(self, iteration: int) -> bool:
        """
        Check if AGENTS.md should be updated and warn if necessary.

        Args:
            iteration: Current iteration number

        Returns:
            True if warning issued, False otherwise
        """
        if not self.config.librarian.check_enabled:
            logger.debug("Librarian check disabled in config")
            return False

        # Check if code files changed in last commit
        code_changed = self._detect_code_changes()

        # Check if AGENTS.md changed in last commit
        agents_changed = self._detect_agents_md_change()

        if code_changed and not agents_changed:
            self.iterations_without_update += 1
            logger.info(
                f"Code changed but AGENTS.md not updated "
                f"({self.iterations_without_update} consecutive iterations)"
            )
        elif agents_changed:
            # Reset counter if AGENTS.md was updated
            if self.iterations_without_update > 0:
                logger.info(
                    f"AGENTS.md updated! Resetting counter "
                    f"(was {self.iterations_without_update})"
                )
            self.iterations_without_update = 0

        # Issue warning if threshold exceeded
        if self.iterations_without_update >= self.warning_threshold:
            self._issue_warning(iteration)
            return True

        return False

    def _detect_code_changes(self) -> bool:
        """
        Detect if code files were modified in last commit.

        Returns:
            True if code files changed, False otherwise
        """
        try:
            # Get list of changed files in last commit
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.debug("No git commits yet or git error")
                return False

            changed_files = result.stdout.strip().split("\n")

            # Check for code files (common extensions)
            code_extensions = {
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                ".py",
                ".go",
                ".rs",
                ".java",
                ".cpp",
                ".c",
                ".rb",
                ".php",
            }

            for file in changed_files:
                if any(file.endswith(ext) for ext in code_extensions):
                    logger.debug(f"Code file changed: {file}")
                    return True

            return False

        except subprocess.TimeoutExpired:
            logger.warning("Git command timed out")
            return False
        except Exception as e:
            logger.error(f"Error detecting code changes: {e}")
            return False

    def _detect_agents_md_change(self) -> bool:
        """
        Detect if AGENTS.md was modified in last commit.

        Returns:
            True if AGENTS.md changed, False otherwise
        """
        try:
            agents_file = self.config.files.patterns

            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return False

            changed_files = result.stdout.strip().split("\n")

            if agents_file in changed_files:
                logger.debug("AGENTS.md was updated in last commit")
                return True

            return False

        except subprocess.TimeoutExpired:
            logger.warning("Git command timed out")
            return False
        except Exception as e:
            logger.error(f"Error detecting AGENTS.md changes: {e}")
            return False

    def _issue_warning(self, iteration: int) -> None:
        """
        Issue warning about missing AGENTS.md updates.

        Args:
            iteration: Current iteration number
        """
        warning = f"""
{tc.YELLOW}{'=' * 80}
⚠️  LIBRARIAN WARNING (Iteration {iteration})
{'=' * 80}
Code has been modified for {self.iterations_without_update} consecutive iterations
without updating {self.config.files.patterns}.

Have you discovered any new patterns, conventions, or gotchas?
If so, please add them to {self.config.files.patterns} so future iterations can learn.

Good AGENTS.md entries include:
- ## Pattern: [Name]
  - Clear description
  - Example usage
  - When to apply

- ## Gotcha: [Description]
  - What to avoid
  - How to prevent

This helps compound knowledge across iterations!
{'=' * 80}{tc.NC}
"""

        print(warning)
        logger.warning(
            f"Librarian warning issued at iteration {iteration} "
            f"({self.iterations_without_update} iterations without AGENTS.md update)"
        )

        # Don't reset counter - warning will repeat until addressed
        # This is intentional to encourage action

    def get_update_stats(self) -> dict:
        """
        Get statistics about AGENTS.md updates.

        Returns:
            Dict with iteration counts and status
        """
        return {
            "iterations_without_update": self.iterations_without_update,
            "warning_threshold": self.warning_threshold,
            "warning_active": self.iterations_without_update >= self.warning_threshold,
            "check_enabled": self.config.librarian.check_enabled,
        }

    def force_reset(self) -> None:
        """Force reset the iteration counter (for testing or manual override)."""
        logger.info(
            f"Librarian counter manually reset (was {self.iterations_without_update})"
        )
        self.iterations_without_update = 0

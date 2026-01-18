"""Context synthesis for agent memory injection."""

import logging
from pathlib import Path
from typing import Dict, Optional

from .config import ConfigManager
from .state import StateManager
from .utils import estimate_token_count

logger = logging.getLogger(__name__)


class ContextSynthesizer:
    """
    Synthesizes context from persistent state for agent "memory".

    Combines:
    - AGENTS.md (learned patterns and conventions)
    - progress.txt (recent iteration history)
    - Current story (objective)

    Into a structured context block that simulates auto-handoff
    for agents that don't natively support it.
    """

    def __init__(self, config: ConfigManager, state: StateManager) -> None:
        """
        Initialize ContextSynthesizer.

        Args:
            config: Configuration manager
            state: State manager
        """
        self.config = config
        self.state = state
        self.project_root = Path(".")

    def synthesize(self, iteration: int, story: Dict) -> Dict[str, str]:
        """
        Synthesize context for an iteration.

        Args:
            iteration: Current iteration number
            story: Story dict from prd.json

        Returns:
            Dict with keys:
                - 'agents_md': AGENTS.md content
                - 'progress': Recent progress.txt content
                - 'summary': Brief context summary
                - 'token_count': Estimated token count
        """
        logger.info(f"Synthesizing context for iteration {iteration}")

        # Load AGENTS.md
        agents_md = self._load_agents_md()

        # Load recent progress
        progress = self._load_recent_progress()

        # Estimate token count
        total_tokens = estimate_token_count(agents_md + progress)
        token_budget = self.config.context_config.token_budget

        # Trim if necessary
        if total_tokens > token_budget:
            logger.warning(
                f"Context exceeds budget ({total_tokens}/{token_budget} tokens), trimming"
            )
            # Calculate how much progress we can afford
            agents_md_tokens = estimate_token_count(agents_md)
            remaining_budget = token_budget - agents_md_tokens

            if remaining_budget < 0:
                logger.error(
                    "AGENTS.md alone exceeds token budget! Consider summarizing."
                )
                # Emergency: trim agents_md if it's too large
                if not self.config.context_config.include_full_agents_md:
                    agents_md = self._summarize_agents_md(agents_md, token_budget // 2)
                    remaining_budget = token_budget - estimate_token_count(agents_md)

            progress = self._trim_progress(progress, remaining_budget)
            total_tokens = estimate_token_count(agents_md + progress)

        summary = (
            f"Iteration {iteration}, Story {story['id']}, "
            f"Context: ~{total_tokens} tokens"
        )

        logger.info(summary)

        return {
            "agents_md": agents_md,
            "progress": progress,
            "summary": summary,
            "token_count": str(total_tokens),
        }

    def _load_agents_md(self) -> str:
        """
        Load AGENTS.md content.

        Returns:
            AGENTS.md content or default message
        """
        agents_path = self.project_root / self.config.files.patterns

        if not agents_path.exists():
            logger.info("AGENTS.md not found, using empty context")
            return (
                "No patterns documented yet. You're the first iteration!\n\n"
                "When you discover coding patterns, conventions, or gotchas:\n"
                "- Add them to AGENTS.md\n"
                "- Use clear headings (## Pattern: [Name])\n"
                "- Include examples\n"
            )

        try:
            content = agents_path.read_text(encoding="utf-8")
            token_count = estimate_token_count(content)
            logger.info(f"Loaded AGENTS.md ({len(content)} chars, ~{token_count} tokens)")
            return content
        except Exception as e:
            logger.error(f"Error loading AGENTS.md: {e}")
            return "Error loading AGENTS.md"

    def _load_recent_progress(self) -> str:
        """
        Load recent lines from progress.txt.

        Returns:
            Recent progress content
        """
        progress_path = self.project_root / self.config.files.progress

        if not progress_path.exists():
            logger.info("progress.txt not found")
            return "No previous iterations yet. This is the first one!"

        try:
            all_lines = progress_path.read_text(encoding="utf-8").split("\n")
            max_lines = self.config.context_config.max_progress_lines

            # Take last N lines
            recent_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines
            content = "\n".join(recent_lines)

            logger.info(
                f"Loaded {len(recent_lines)} lines from progress.txt "
                f"(~{estimate_token_count(content)} tokens)"
            )
            return content

        except Exception as e:
            logger.error(f"Error loading progress.txt: {e}")
            return "Error loading progress.txt"

    def _trim_progress(self, progress: str, token_budget: int) -> str:
        """
        Trim progress to fit token budget.

        Args:
            progress: Full progress content
            token_budget: Max tokens allowed

        Returns:
            Trimmed progress content
        """
        if token_budget <= 0:
            logger.warning("No token budget for progress context!")
            return "(...progress trimmed due to context limits)"

        char_budget = token_budget * 4  # Rough estimate: 4 chars/token

        if len(progress) <= char_budget:
            return progress

        logger.info(f"Trimming progress from {len(progress)} to {char_budget} chars")

        # Take last N chars
        trimmed = progress[-char_budget:]

        # Find first complete line to avoid cutting mid-line
        first_newline = trimmed.find("\n")
        if first_newline != -1:
            trimmed = trimmed[first_newline + 1 :]

        return f"...(earlier progress trimmed for context budget)\n\n{trimmed}"

    def _summarize_agents_md(self, agents_md: str, token_budget: int) -> str:
        """
        Summarize AGENTS.md if it exceeds budget.

        This is an emergency fallback. Ideally AGENTS.md should be kept concise.

        Args:
            agents_md: Full AGENTS.md content
            token_budget: Max tokens allowed

        Returns:
            Summarized content
        """
        logger.warning("AGENTS.md exceeds budget, summarizing (emergency fallback)")

        char_budget = token_budget * 4

        # Extract section headings for summary
        lines = agents_md.split("\n")
        summary_lines = [
            "## Key Patterns Summary (AGENTS.md truncated)",
            "",
        ]

        for line in lines:
            # Keep all headings
            if line.startswith("#"):
                summary_lines.append(line)

        summary = "\n".join(summary_lines)

        # If still too long, just take first N chars
        if len(summary) > char_budget:
            summary = summary[:char_budget]

        summary += "\n\n(Full AGENTS.md truncated. Please keep AGENTS.md concise!)"

        return summary

    def estimate_total_context_size(self) -> Dict[str, int]:
        """
        Estimate sizes of all context components.

        Returns:
            Dict with token estimates for each component
        """
        agents_md = self._load_agents_md()
        progress = self._load_recent_progress()

        return {
            "agents_md_tokens": estimate_token_count(agents_md),
            "progress_tokens": estimate_token_count(progress),
            "total_tokens": estimate_token_count(agents_md + progress),
            "budget": self.config.context_config.token_budget,
        }

"""Core RalphZero orchestrator logic."""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .agent import AgentInvoker
from .config import ConfigManager
from .context import ContextSynthesizer
from .librarian import LibrarianCheck
from .quality import QualityGates
from .state import StateManager
from .utils import print_section_header, tc

logger = logging.getLogger(__name__)


class RalphZero:
    """
    Main orchestrator for Ralph Zero autonomous development loop.

    Coordinates:
    - Story selection from prd.json
    - Context synthesis (AGENTS.md + progress.txt)
    - Agent invocation with enriched prompts
    - Quality gate execution
    - Git commits
    - State updates
    - Cognitive feedback enforcement
    """

    def __init__(
        self,
        config: ConfigManager,
        state: StateManager,
        max_iterations: Optional[int] = None,
    ) -> None:
        """
        Initialize RalphZero orchestrator.

        Args:
            config: Configuration manager
            state: State manager
            max_iterations: Override max iterations from config
        """
        self.config = config
        self.state = state
        self.max_iterations = max_iterations or config.max_iterations

        # Initialize components
        self.context_synth = ContextSynthesizer(config, state)
        self.agent_invoker = AgentInvoker(config)
        self.quality_gates = QualityGates(config)
        self.librarian = LibrarianCheck(config, state)

        logger.info(
            f"RalphZero initialized (max_iterations={self.max_iterations}, "
            f"agent={self.agent_invoker.agent_command})"
        )

    def run(self) -> int:
        """
        Execute the main autonomous development loop.

        Returns:
            Exit code:
                0 - All stories complete
                1 - Max iterations reached
                2 - Fatal error
        """
        self._print_header()

        # Validate prerequisites
        if not self._validate_prerequisites():
            return 2

        # Setup git branch
        if not self._setup_branch():
            return 2

        # Main loop
        iteration = 0
        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"=== Starting iteration {iteration}/{self.max_iterations} ===")
            self._print_iteration_header(iteration)

            # Find next story
            story = self.state.find_next_story()
            if story is None:
                self._print_all_complete()
                return 0

            # Execute iteration
            success = self._run_iteration(iteration, story)

            # Librarian check (every 3 iterations)
            if success and iteration % 3 == 0:
                self.librarian.check_and_warn(iteration)

            if not success:
                logger.warning(f"Iteration {iteration} failed for story {story['id']}")
                # Continue to next iteration (don't abort on single failure)

        # Reached max iterations
        self._print_max_iterations_reached()
        logger.warning(f"Max iterations ({self.max_iterations}) reached")
        return 1

    def _run_iteration(self, iteration: int, story: Dict) -> bool:
        """
        Execute a single iteration.

        Args:
            iteration: Current iteration number
            story: Story dict from prd.json

        Returns:
            True if story completed successfully, False otherwise
        """
        story_id = story["id"]
        story_title = story["title"]

        logger.info(f"ITERATION {iteration}: Working on {story_id} - {story_title}")
        print(f"\n{tc.BOLD}Story:{tc.NC} {story_id} - {story_title}")

        # Synthesize context
        context = self.context_synth.synthesize(iteration, story)

        # Build prompt
        prompt = self._build_prompt(iteration, story, context)

        # Save prompt for debugging (optional)
        if logger.isEnabledFor(logging.DEBUG):
            prompt_debug_path = Path(f".ralph_prompt_debug_{iteration}.md")
            prompt_debug_path.write_text(prompt, encoding="utf-8")
            logger.debug(f"Saved prompt to {prompt_debug_path}")

        # Invoke agent
        agent_output = self.agent_invoker.invoke(prompt, iteration)

        # Check completion signal
        is_complete, failure_reason = self.agent_invoker.check_completion_signal(
            agent_output
        )

        if not is_complete:
            reason = failure_reason or "Unknown"
            logger.error(f"Agent did not complete: {reason}")
            print(f"{tc.RED}❌ Agent reported failure: {reason}{tc.NC}")
            self._revert_and_log(iteration, story_id, f"AGENT_FAILED_{reason}")
            return False

        # Extract learnings from output
        learnings = self._extract_learnings(agent_output)

        # Run quality gates
        print(f"\n{tc.BOLD}Running quality gates...{tc.NC}")
        if not self.quality_gates.run_all():
            logger.error(f"Quality gates failed for {story_id}")
            self._revert_and_log(iteration, story_id, "QUALITY_GATES_FAILED")
            return False

        # Commit changes
        if not self._commit_changes(story_id, story_title):
            logger.error(f"Failed to commit changes for {story_id}")
            self._revert_and_log(iteration, story_id, "COMMIT_FAILED")
            return False

        # Update state
        self.state.update_story_status(story_id, passes=True)
        self.state.append_progress(
            iteration=iteration,
            story_id=story_id,
            status="PASSED",
            changes=self._get_changed_files(),
            learnings=learnings,
        )

        logger.info(f"✅ Successfully completed {story_id}")
        print(f"\n{tc.GREEN}✅ Story {story_id} completed successfully{tc.NC}")
        return True

    def _build_prompt(self, iteration: int, story: Dict, context: Dict) -> str:
        """
        Build agent prompt from template.

        Args:
            iteration: Iteration number
            story: Story dict
            context: Context dict from synthesizer

        Returns:
            Formatted prompt string
        """
        template_path = (
            Path(__file__).parent.parent.parent
            / "assets"
            / "templates"
            / "prompt_template.md"
        )

        if not template_path.exists():
            logger.error(f"Prompt template not found: {template_path}")
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        template = template_path.read_text(encoding="utf-8")

        # Format acceptance criteria as numbered list
        criteria_list = "\n".join(
            [f"{i+1}. {c}" for i, c in enumerate(story["acceptanceCriteria"])]
        )

        # Format quality gates
        gates_list = []
        for name, gate in self.config.quality_gates.items():
            blocking_str = "**BLOCKING**" if gate.blocking else "non-blocking"
            gates_list.append(f"- **{name}** ({blocking_str}): `{gate.cmd}`")

        gates_formatted = "\n".join(gates_list) if gates_list else "- No quality gates configured"

        # Fill template
        prompt = template.format(
            iteration_number=iteration,
            story_id=story["id"],
            story_title=story["title"],
            story_description=story["description"],
            acceptance_criteria_list=criteria_list,
            agents_md_content=context["agents_md"],
            progress_context=context["progress"],
            quality_gates_list=gates_formatted,
        )

        logger.debug(f"Built prompt ({len(prompt)} chars)")
        return prompt

    def _extract_learnings(self, agent_output: str) -> List[str]:
        """
        Extract learnings from agent output.

        Looks for sections like:
        - ### Patterns Discovered
        - ### Gotchas Encountered

        Args:
            agent_output: Full agent output

        Returns:
            List of learning strings
        """
        learnings = []

        # Simple extraction - look for markdown sections
        if "### Patterns Discovered" in agent_output:
            start = agent_output.find("### Patterns Discovered")
            end = agent_output.find("###", start + 1)
            section = agent_output[start:end] if end != -1 else agent_output[start:]

            # Extract bullet points
            for line in section.split("\n"):
                if line.strip().startswith("-"):
                    learnings.append(line.strip()[1:].strip())

        if "### Gotchas Encountered" in agent_output:
            start = agent_output.find("### Gotchas Encountered")
            end = agent_output.find("###", start + 1)
            section = agent_output[start:end] if end != -1 else agent_output[start:]

            for line in section.split("\n"):
                if line.strip().startswith("-"):
                    learnings.append(line.strip()[1:].strip())

        if learnings:
            logger.info(f"Extracted {len(learnings)} learnings from agent output")

        return learnings

    def _commit_changes(self, story_id: str, story_title: str) -> bool:
        """
        Commit changes with formatted message.

        Args:
            story_id: Story ID
            story_title: Story title

        Returns:
            True if successful, False otherwise
        """
        try:
            # Stage all changes
            subprocess.run(["git", "add", "-A"], check=True)

            # Check if there are changes to commit
            result = subprocess.run(
                ["git", "diff", "--staged", "--quiet"], capture_output=True
            )

            if result.returncode == 0:
                # No changes staged
                logger.warning("No changes to commit (git diff --staged is empty)")
                print(f"{tc.YELLOW}⚠️  No changes to commit{tc.NC}")
                return True  # Not an error - story might not have required changes

            # Commit with formatted message
            prefix = self.config.git.commit_prefix
            commit_msg = f"{prefix} {story_id} - {story_title}"

            subprocess.run(["git", "commit", "-m", commit_msg], check=True)

            logger.info(f"Committed: {commit_msg}")
            print(f"{tc.GREEN}✅ Committed: {commit_msg}{tc.NC}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Git commit failed: {e}")
            return False

    def _revert_and_log(self, iteration: int, story_id: str, reason: str) -> None:
        """
        Revert uncommitted changes and log failure.

        Args:
            iteration: Iteration number
            story_id: Story ID
            reason: Failure reason
        """
        try:
            # Revert changes
            subprocess.run(["git", "reset", "--hard", "HEAD"], check=True)
            subprocess.run(["git", "clean", "-fd"], check=True)

            logger.info(f"Reverted changes for {story_id}")
            print(f"{tc.YELLOW}↩️  Reverted changes{tc.NC}")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to revert changes: {e}")

        # Log failure
        self.state.append_progress(
            iteration=iteration,
            story_id=story_id,
            status=f"FAILED_{reason}",
            changes=[],
            learnings=[],
            gotchas=[f"Failed: {reason}"],
        )

    def _get_changed_files(self) -> List[str]:
        """
        Get list of changed files in last commit.

        Returns:
            List of changed file paths
        """
        try:
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            files = result.stdout.strip().split("\n")
            return [f for f in files if f]  # Filter empty

        except subprocess.CalledProcessError:
            logger.warning("Could not get changed files")
            return []

    def _validate_prerequisites(self) -> bool:
        """Validate required tools and files exist."""
        print(f"\n{tc.BOLD}Validating prerequisites...{tc.NC}")

        # Check prd.json
        if not self.state.prd_path.exists():
            logger.error("prd.json not found")
            print(f"{tc.RED}❌ prd.json not found{tc.NC}")
            print(f"   Run: Load ralph-convert skill to create prd.json")
            return False

        # Validate prd.json
        is_valid, errors = self.state.validate_prd()
        if not is_valid:
            logger.error(f"prd.json validation failed: {errors}")
            print(f"{tc.RED}❌ prd.json validation failed:{tc.NC}")
            for error in errors:
                print(f"   - {error}")
            return False

        # Check git
        result = subprocess.run(["git", "status"], capture_output=True)
        if result.returncode != 0:
            logger.error("Not a git repository")
            print(f"{tc.RED}❌ Not a git repository{tc.NC}")
            return False

        print(f"{tc.GREEN}✅ Prerequisites validated{tc.NC}")
        return True

    def _setup_branch(self) -> bool:
        """Setup git branch from PRD."""
        try:
            # Load PRD to get branch name
            with open(self.state.prd_path, "r", encoding="utf-8") as f:
                import json

                prd = json.load(f)

            branch_name = prd["branchName"]

            # Check if branch exists
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch_name],
                capture_output=True,
            )

            if result.returncode == 0:
                # Branch exists, check it out
                subprocess.run(["git", "checkout", branch_name], check=True)
                logger.info(f"Checked out existing branch: {branch_name}")
                print(f"{tc.GREEN}✅ Checked out branch: {branch_name}{tc.NC}")
            else:
                # Branch doesn't exist
                if self.config.git.auto_create_branch:
                    subprocess.run(["git", "checkout", "-b", branch_name], check=True)
                    logger.info(f"Created new branch: {branch_name}")
                    print(f"{tc.GREEN}✅ Created branch: {branch_name}{tc.NC}")
                else:
                    logger.error(f"Branch {branch_name} does not exist")
                    print(f"{tc.RED}❌ Branch {branch_name} does not exist{tc.NC}")
                    return False

            # Initialize progress.txt if needed
            if not self.state.progress_path.exists():
                project_name = prd["project"]
                self.state.initialize_progress(project_name, branch_name)

            return True

        except Exception as e:
            logger.error(f"Failed to setup branch: {e}", exc_info=True)
            print(f"{tc.RED}❌ Failed to setup branch: {e}{tc.NC}")
            return False

    def _print_header(self) -> None:
        """Print Ralph Zero startup header."""
        print(f"\n{tc.BOLD}{'='*80}{tc.NC}")
        print(f"{tc.BOLD}{tc.CYAN}RALPH ZERO - Autonomous Development Orchestrator{tc.NC}")
        print(f"{tc.BOLD}{'='*80}{tc.NC}")
        print(f"Agent: {self.agent_invoker.agent_command}")
        print(f"Max Iterations: {self.max_iterations}")
        print(f"Quality Gates: {len(self.config.quality_gates)}")
        print(f"{tc.BOLD}{'='*80}{tc.NC}\n")

    def _print_iteration_header(self, iteration: int) -> None:
        """Print iteration header."""
        print(f"\n{tc.BLUE}{'='*80}{tc.NC}")
        print(f"{tc.BLUE}{tc.BOLD}Iteration {iteration}/{self.max_iterations}{tc.NC}")
        print(f"{tc.BLUE}{'='*80}{tc.NC}")

    def _print_all_complete(self) -> None:
        """Print all stories complete message."""
        print(f"\n{tc.GREEN}{'='*80}{tc.NC}")
        print(f"{tc.GREEN}{tc.BOLD}🎉 ALL STORIES COMPLETE! 🎉{tc.NC}")
        print(f"{tc.GREEN}{'='*80}{tc.NC}")
        print(f"\n{tc.GREEN}All user stories have been successfully implemented.{tc.NC}")
        print(f"{tc.GREEN}Review the changes and merge when ready.{tc.NC}\n")

    def _print_max_iterations_reached(self) -> None:
        """Print max iterations reached message."""
        print(f"\n{tc.YELLOW}{'='*80}{tc.NC}")
        print(f"{tc.YELLOW}{tc.BOLD}⚠️  MAX ITERATIONS REACHED{tc.NC}")
        print(f"{tc.YELLOW}{'='*80}{tc.NC}")
        print(f"\n{tc.YELLOW}Work is incomplete. Stories remaining:{tc.NC}")

        # Show remaining stories
        stories = self.state.get_all_stories()
        incomplete = [s for s in stories if not s.get("passes", False)]

        for story in incomplete[:5]:  # Show first 5
            print(f"  - {story['id']}: {story['title']}")

        if len(incomplete) > 5:
            print(f"  ... and {len(incomplete) - 5} more")

        print(f"\n{tc.YELLOW}Run ralph-zero again to continue.{tc.NC}\n")

    def print_status(self, verbose: bool = False) -> None:
        """
        Print current status.

        Args:
            verbose: If True, show detailed story list
        """
        stories = self.state.get_all_stories()
        total = len(stories)
        passed = sum(1 for s in stories if s.get("passes", False))

        print(f"\n{tc.BOLD}Ralph Zero Status{tc.NC}")
        print(f"{'='*40}")
        print(f"Total Stories: {total}")
        print(f"Completed: {tc.GREEN}{passed}{tc.NC} ({passed/total*100:.1f}%)")
        print(f"Remaining: {tc.YELLOW}{total - passed}{tc.NC}")
        print()

        if verbose:
            print(f"{tc.BOLD}Story Details:{tc.NC}")
            for story in stories:
                status = f"{tc.GREEN}✅{tc.NC}" if story.get("passes") else f"{tc.YELLOW}⬜{tc.NC}"
                print(f"{status} {story['id']}: {story['title']}")
            print()

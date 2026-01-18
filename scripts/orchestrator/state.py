"""State management for Ralph Zero with atomic operations and validation."""

import fcntl
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import jsonschema

logger = logging.getLogger(__name__)


class StateManager:
    """
    Manages Ralph Zero persistent state with atomic operations.

    Provides:
    - Atomic updates to prd.json with file locking
    - Append-only progress.txt logging
    - JSON schema validation
    - Archive management for feature switches
    - Transaction logging for debugging
    """

    def __init__(self, project_root: str = ".") -> None:
        """
        Initialize StateManager.

        Args:
            project_root: Project root directory path
        """
        self.project_root = Path(project_root)
        self.prd_path = self.project_root / "prd.json"
        self.progress_path = self.project_root / "progress.txt"

        # Load JSON schema for validation
        self._prd_schema: Optional[Dict[str, Any]] = None
        self._load_prd_schema()

    def _load_prd_schema(self) -> None:
        """Load PRD JSON schema for validation."""
        schema_path = Path(__file__).parent.parent / "schemas" / "prd.schema.json"

        if not schema_path.exists():
            logger.warning(f"PRD schema not found at {schema_path}, validation disabled")
            return

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                self._prd_schema = json.load(f)
            logger.debug("PRD schema loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load PRD schema: {e}")
            self._prd_schema = None

    def update_story_status(
        self, story_id: str, passes: bool, notes: str = ""
    ) -> bool:
        """
        Atomically update story status in prd.json.

        Args:
            story_id: Story ID (e.g., "US-001")
            passes: Whether the story passed quality gates
            notes: Optional implementation notes

        Returns:
            True if successful, False otherwise
        """
        try:
            # Read with exclusive lock
            with open(self.prd_path, "r+", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                try:
                    prd = json.load(f)

                    # Validate schema if available
                    if self._prd_schema:
                        try:
                            jsonschema.validate(instance=prd, schema=self._prd_schema)
                        except jsonschema.ValidationError as e:
                            logger.error(f"PRD validation failed: {e.message}")
                            return False

                    # Find and update story
                    story_found = False
                    for story in prd["userStories"]:
                        if story["id"] == story_id:
                            old_status = story.get("passes", False)
                            story["passes"] = passes
                            if notes:
                                story["notes"] = notes

                            # Log transaction
                            logger.info(
                                f"Updated {story_id}: passes={old_status}->{passes}"
                            )
                            story_found = True
                            break

                    if not story_found:
                        logger.error(f"Story {story_id} not found in prd.json")
                        return False

                    # Write atomically
                    f.seek(0)
                    f.truncate()
                    json.dump(prd, f, indent=2, ensure_ascii=False)
                    f.write("\n")  # Trailing newline

                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            return True

        except FileNotFoundError:
            logger.error(f"prd.json not found at {self.prd_path}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in prd.json: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating story status: {e}", exc_info=True)
            return False

    def append_progress(
        self,
        iteration: int,
        story_id: str,
        status: str,
        changes: Optional[List[str]] = None,
        learnings: Optional[List[str]] = None,
        gotchas: Optional[List[str]] = None,
    ) -> bool:
        """
        Append iteration results to progress.txt.

        Args:
            iteration: Iteration number
            story_id: Story ID
            status: Status string (PASSED, FAILED_*, etc.)
            changes: List of files/changes made
            learnings: List of key learnings
            gotchas: List of gotchas/warnings

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Format status with icon
            if status == "PASSED":
                status_icon = "✅ PASSED"
            elif status.startswith("FAILED"):
                status_icon = f"❌ {status}"
            else:
                status_icon = status

            # Build entry
            entry_lines = [
                "",
                "=" * 80,
                f"[{timestamp}] ITERATION {iteration} - {story_id}",
                "=" * 80,
                f"STATUS: {status_icon}",
                "",
            ]

            if changes:
                entry_lines.append("Changes Made:")
                for change in changes:
                    entry_lines.append(f"  - {change}")
                entry_lines.append("")

            if learnings:
                entry_lines.append("Learnings:")
                for learning in learnings:
                    entry_lines.append(f"  - {learning}")
                entry_lines.append("")

            if gotchas:
                entry_lines.append("Gotchas:")
                for gotcha in gotchas:
                    entry_lines.append(f"  - {gotcha}")
            else:
                entry_lines.append("Gotchas:")
                entry_lines.append("  - None")

            entry_lines.append("")

            entry = "\n".join(entry_lines)

            # Append with lock
            with open(self.progress_path, "a", encoding="utf-8") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    f.write(entry)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            logger.debug(f"Appended progress for iteration {iteration}")
            return True

        except Exception as e:
            logger.error(f"Error appending progress: {e}", exc_info=True)
            return False

    def archive_previous_run(self, new_branch: str) -> bool:
        """
        Archive prd.json and progress.txt if switching features.

        Args:
            new_branch: New branch name from PRD

        Returns:
            True if successful or no archive needed, False on error
        """
        try:
            # Check if prd.json exists
            if not self.prd_path.exists():
                logger.debug("No prd.json to archive")
                return True

            # Read current branch name
            with open(self.prd_path, "r", encoding="utf-8") as f:
                current_prd = json.load(f)

            current_branch = current_prd.get("branchName", "")

            # Same feature? No archive needed
            if current_branch == new_branch:
                logger.debug(f"Same branch ({new_branch}), no archive needed")
                return True

            # Check if progress.txt has meaningful content
            if self.progress_path.exists():
                with open(self.progress_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Only archive if there's actual progress (more than just header)
                    if len(content.strip().split("\n")) <= 6:
                        logger.debug("No meaningful progress, skipping archive")
                        return True

            # Create archive directory
            date_str = datetime.now().strftime("%Y-%m-%d")
            old_feature = current_branch.replace("ralph/", "")
            archive_dir = self.project_root / "archive" / f"{date_str}-{old_feature}"
            archive_dir.mkdir(parents=True, exist_ok=True)

            # Copy files
            shutil.copy(self.prd_path, archive_dir / "prd.json")
            if self.progress_path.exists():
                shutil.copy(self.progress_path, archive_dir / "progress.txt")

            logger.info(f"Archived previous run to {archive_dir}")
            print(f"📦 Archived previous run to {archive_dir}")
            return True

        except Exception as e:
            logger.error(f"Error archiving previous run: {e}", exc_info=True)
            return False

    def validate_prd(self) -> Tuple[bool, List[str]]:
        """
        Validate prd.json structure and business rules.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors: List[str] = []

        try:
            if not self.prd_path.exists():
                return (False, ["prd.json not found"])

            with open(self.prd_path, "r", encoding="utf-8") as f:
                prd = json.load(f)

            # JSON Schema validation (if available)
            if self._prd_schema:
                try:
                    jsonschema.validate(instance=prd, schema=self._prd_schema)
                except jsonschema.ValidationError as e:
                    errors.append(f"Schema validation: {e.message}")

            # Additional business rule validation

            # Check required fields
            required_fields = ["project", "branchName", "description", "userStories"]
            for field in required_fields:
                if field not in prd:
                    errors.append(f"Missing required field: {field}")

            # Validate branch name format
            if "branchName" in prd:
                branch = prd["branchName"]
                if not branch.startswith("ralph/"):
                    errors.append("branchName must start with 'ralph/'")

            # Validate stories
            if "userStories" in prd:
                stories = prd["userStories"]

                if not stories:
                    errors.append("userStories array is empty")

                story_ids = set()
                priorities = set()

                for i, story in enumerate(stories):
                    # Check required story fields
                    required_story_fields = [
                        "id",
                        "title",
                        "description",
                        "acceptanceCriteria",
                        "priority",
                        "passes",
                    ]
                    for field in required_story_fields:
                        if field not in story:
                            errors.append(f"Story {i}: Missing field '{field}'")

                    # Check ID format
                    if "id" in story:
                        story_id = story["id"]
                        if not story_id.startswith("US-"):
                            errors.append(f"Story {i}: ID must start with 'US-'")

                        if story_id in story_ids:
                            errors.append(f"Duplicate story ID: {story_id}")
                        story_ids.add(story_id)

                    # Check priority uniqueness
                    if "priority" in story:
                        priority = story["priority"]
                        if priority in priorities:
                            errors.append(
                                f"Story {story.get('id', i)}: Duplicate priority {priority}"
                            )
                        priorities.add(priority)

                    # Check acceptance criteria
                    if "acceptanceCriteria" in story:
                        criteria = story["acceptanceCriteria"]
                        if not isinstance(criteria, list) or not criteria:
                            errors.append(
                                f"Story {story.get('id', i)}: acceptanceCriteria must be non-empty array"
                            )
                        elif "Typecheck passes" not in criteria:
                            errors.append(
                                f"Story {story.get('id', i)}: Missing required 'Typecheck passes' criterion"
                            )

            is_valid = len(errors) == 0
            return (is_valid, errors)

        except FileNotFoundError:
            return (False, ["prd.json not found"])
        except json.JSONDecodeError as e:
            return (False, [f"Invalid JSON: {e}"])
        except Exception as e:
            logger.error(f"Error validating PRD: {e}", exc_info=True)
            return (False, [f"Validation error: {str(e)}"])

    def find_next_story(self) -> Optional[Dict[str, Any]]:
        """
        Find the next incomplete story by priority.

        Returns:
            Story dict or None if all complete
        """
        try:
            if not self.prd_path.exists():
                logger.error("prd.json not found")
                return None

            with open(self.prd_path, "r", encoding="utf-8") as f:
                prd = json.load(f)

            stories = prd.get("userStories", [])

            # Find incomplete stories
            incomplete = [s for s in stories if not s.get("passes", False)]

            if not incomplete:
                logger.info("All stories complete!")
                return None

            # Sort by priority and return first
            incomplete.sort(key=lambda s: s.get("priority", 999))
            next_story = incomplete[0]

            logger.info(f"Next story: {next_story['id']} - {next_story['title']}")
            return next_story

        except Exception as e:
            logger.error(f"Error finding next story: {e}", exc_info=True)
            return None

    def get_all_stories(self) -> List[Dict[str, Any]]:
        """
        Get all stories from prd.json.

        Returns:
            List of story dicts
        """
        try:
            if not self.prd_path.exists():
                return []

            with open(self.prd_path, "r", encoding="utf-8") as f:
                prd = json.load(f)

            return prd.get("userStories", [])

        except Exception as e:
            logger.error(f"Error getting stories: {e}")
            return []

    def initialize_progress(self, project_name: str, branch_name: str) -> bool:
        """
        Initialize progress.txt with header.

        Args:
            project_name: Project name from PRD
            branch_name: Branch name from PRD

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            header = [
                "=" * 80,
                "RALPH ZERO PROGRESS LOG",
                "=" * 80,
                f"Project: {project_name}",
                f"Branch: {branch_name}",
                f"Started: {timestamp}",
                "",
                "=" * 80,
                "",
            ]

            with open(self.progress_path, "w", encoding="utf-8") as f:
                f.write("\n".join(header))

            logger.info(f"Initialized progress.txt for {project_name}")
            return True

        except Exception as e:
            logger.error(f"Error initializing progress: {e}", exc_info=True)
            return False

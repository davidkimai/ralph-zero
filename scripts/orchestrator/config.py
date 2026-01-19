"""Configuration management for Ralph Zero."""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import jsonschema

logger = logging.getLogger(__name__)


@dataclass
class ContextConfig:
    """Configuration for context synthesis."""

    max_progress_lines: int = 100
    include_full_agents_md: bool = True
    token_budget: int = 8000


@dataclass
class FilesConfig:
    """Configuration for file paths."""

    prd: str = "prd.json"
    progress: str = "progress.txt"
    patterns: str = "AGENTS.md"
    orchestrator_log: str = "orchestrator.log"


@dataclass
class GitConfig:
    """Configuration for git operations."""

    commit_prefix: str = "[Ralph]"
    auto_create_branch: bool = True
    require_clean_tree: bool = False


@dataclass
class LibrarianConfig:
    """Configuration for librarian checks."""

    check_enabled: bool = True
    warning_after_iterations: int = 3


@dataclass
class QualityGate:
    """Configuration for a single quality gate."""

    cmd: str
    blocking: bool
    timeout: int = 60
    working_dir: Optional[str] = None
    env: Optional[Dict[str, str]] = None


@dataclass
class ConfigManager:
    """
    Manages Ralph Zero configuration.

    Loads configuration from ralph.json with schema validation,
    provides defaults, and offers type-safe access to config values.
    """

    agent_command: str = "auto"
    agent_mode: str = "cli"  # "cli" or "api"
    model: str = "claude-3-7-sonnet-20250219"
    max_iterations: int = 50
    context_window_strategy: str = "synthesized"
    context_config: ContextConfig = field(default_factory=ContextConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    quality_gates: Dict[str, QualityGate] = field(default_factory=dict)
    git: GitConfig = field(default_factory=GitConfig)
    librarian: LibrarianConfig = field(default_factory=LibrarianConfig)

    _config_path: Optional[Path] = None
    _raw_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "ConfigManager":
        """
        Load configuration from file.

        Args:
            config_path: Path to ralph.json. If None, uses default 'ralph.json'

        Returns:
            ConfigManager instance with loaded configuration

        Raises:
            FileNotFoundError: If config file specified but not found
            jsonschema.ValidationError: If config fails schema validation
        """
        path = Path(config_path) if config_path else Path("ralph.json")

        # If file doesn't exist and path is default, use defaults
        if not path.exists() and config_path is None:
            logger.info("No ralph.json found, using default configuration")
            return cls()

        # File explicitly specified but doesn't exist
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        # Load and validate
        logger.info(f"Loading configuration from {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        # Validate against schema
        cls._validate_config(raw_config, path)

        # Create instance from config
        instance = cls._from_dict(raw_config)
        instance._config_path = path
        instance._raw_config = raw_config

        logger.info(f"Configuration loaded successfully (max_iterations={instance.max_iterations})")
        return instance

    @staticmethod
    def _validate_config(config: Dict[str, Any], path: Path) -> None:
        """
        Validate configuration against JSON schema.

        Args:
            config: Configuration dictionary
            path: Path to config file (for error messages)

        Raises:
            jsonschema.ValidationError: If validation fails
        """
        schema_path = Path(__file__).parent.parent / "schemas" / "ralph_config.schema.json"

        if not schema_path.exists():
            logger.warning(f"Schema file not found: {schema_path}, skipping validation")
            return

        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)

        try:
            jsonschema.validate(instance=config, schema=schema)
            logger.debug("Configuration validation passed")
        except jsonschema.ValidationError as e:
            logger.error(f"Configuration validation failed: {e.message}")
            raise

    @classmethod
    def _from_dict(cls, config: Dict[str, Any]) -> "ConfigManager":
        """
        Create ConfigManager from configuration dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            ConfigManager instance
        """
        # Parse context config
        context_config_dict = config.get("context_config", {})
        context_config = ContextConfig(
            max_progress_lines=context_config_dict.get("max_progress_lines", 100),
            include_full_agents_md=context_config_dict.get("include_full_agents_md", True),
            token_budget=context_config_dict.get("token_budget", 8000),
        )

        # Parse files config
        files_dict = config.get("files", {})
        files = FilesConfig(
            prd=files_dict.get("prd", "prd.json"),
            progress=files_dict.get("progress", "progress.txt"),
            patterns=files_dict.get("patterns", "AGENTS.md"),
            orchestrator_log=files_dict.get("orchestrator_log", "orchestrator.log"),
        )

        # Parse quality gates
        quality_gates_dict = config.get("quality_gates", {})
        quality_gates = {
            name: QualityGate(
                cmd=gate["cmd"],
                blocking=gate["blocking"],
                timeout=gate.get("timeout", 60),
                working_dir=gate.get("working_dir"),
                env=gate.get("env"),
            )
            for name, gate in quality_gates_dict.items()
        }

        # Parse git config
        git_dict = config.get("git", {})
        git = GitConfig(
            commit_prefix=git_dict.get("commit_prefix", "[Ralph]"),
            auto_create_branch=git_dict.get("auto_create_branch", True),
            require_clean_tree=git_dict.get("require_clean_tree", False),
        )

        # Parse librarian config
        librarian_dict = config.get("librarian", {})
        librarian = LibrarianConfig(
            check_enabled=librarian_dict.get("check_enabled", True),
            warning_after_iterations=librarian_dict.get("warning_after_iterations", 3),
        )

        return cls(
            agent_command=config.get("agent_command", "auto"),
            agent_mode=config.get("agent_mode", "cli"),
            model=config.get("model", "claude-3-7-sonnet-20250219"),
            max_iterations=config.get("max_iterations", 50),
            context_window_strategy=config.get("context_window_strategy", "synthesized"),
            context_config=context_config,
            files=files,
            quality_gates=quality_gates,
            git=git,
            librarian=librarian,
        )

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save current configuration to file.

        Args:
            path: Path to save to. If None, uses original config path.

        Raises:
            ValueError: If no path specified and no original path exists
        """
        save_path = path or self._config_path
        if save_path is None:
            raise ValueError("No path specified and no original config path exists")

        # Convert to dictionary
        config_dict = self._to_dict()

        # Write to file
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)

        logger.info(f"Configuration saved to {save_path}")

    def _to_dict(self) -> Dict[str, Any]:
        """
        Convert ConfigManager to dictionary.

        Returns:
            Configuration dictionary
        """
        return {
            "agent_command": self.agent_command,
            "agent_mode": self.agent_mode,
            "model": self.model,
            "max_iterations": self.max_iterations,
            "context_window_strategy": self.context_window_strategy,
            "context_config": {
                "max_progress_lines": self.context_config.max_progress_lines,
                "include_full_agents_md": self.context_config.include_full_agents_md,
                "token_budget": self.context_config.token_budget,
            },
            "files": {
                "prd": self.files.prd,
                "progress": self.files.progress,
                "patterns": self.files.patterns,
                "orchestrator_log": self.files.orchestrator_log,
            },
            "quality_gates": {
                name: {
                    "cmd": gate.cmd,
                    "blocking": gate.blocking,
                    "timeout": gate.timeout,
                    **({"working_dir": gate.working_dir} if gate.working_dir else {}),
                    **({"env": gate.env} if gate.env else {}),
                }
                for name, gate in self.quality_gates.items()
            },
            "git": {
                "commit_prefix": self.git.commit_prefix,
                "auto_create_branch": self.git.auto_create_branch,
                "require_clean_tree": self.git.require_clean_tree,
            },
            "librarian": {
                "check_enabled": self.librarian.check_enabled,
                "warning_after_iterations": self.librarian.warning_after_iterations,
            },
        }

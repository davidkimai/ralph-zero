"""Utility functions for Ralph Zero orchestrator."""

import logging
import sys
from pathlib import Path
from typing import Optional


class TerminalColors:
    """ANSI color codes for terminal output."""

    BOLD = "\033[1m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    NC = "\033[0m"  # No Color / Reset


# Convenient alias
tc = TerminalColors


def setup_logging(
    log_file: Optional[str] = None, level: int = logging.INFO, verbose: bool = False
) -> logging.Logger:
    """
    Setup logging configuration for Ralph Zero.

    Args:
        log_file: Path to log file (optional). If None, logs to console only.
        level: Logging level (default: INFO)
        verbose: If True, set DEBUG level

    Returns:
        Configured root logger
    """
    if verbose:
        level = logging.DEBUG

    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # Always DEBUG for file
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def print_section_header(title: str, width: int = 80, color: str = tc.BLUE) -> None:
    """
    Print a formatted section header.

    Args:
        title: Header title
        width: Total width of header
        color: ANSI color code
    """
    print()
    print(f"{color}{'=' * width}{tc.NC}")
    print(f"{color}{title}{tc.NC}")
    print(f"{color}{'=' * width}{tc.NC}")
    print()


def print_status(icon: str, message: str, color: str = tc.NC) -> None:
    """
    Print a status message with icon.

    Args:
        icon: Icon/emoji to display
        message: Status message
        color: ANSI color code
    """
    print(f"{color}{icon} {message}{tc.NC}")


def ensure_directory_exists(path: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path
    """
    path.mkdir(parents=True, exist_ok=True)


def load_file_content(path: Path, default: str = "") -> str:
    """
    Load file content, returning default if file doesn't exist.

    Args:
        path: File path
        default: Default content if file doesn't exist

    Returns:
        File content or default
    """
    if path.exists():
        return path.read_text(encoding="utf-8")
    return default


def estimate_token_count(text: str) -> int:
    """
    Estimate token count for text.

    This uses a simple heuristic: ~4 characters per token.
    For production, use tiktoken for accurate counting.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return len(text) // 4


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "2m 30s")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

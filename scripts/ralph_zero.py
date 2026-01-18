#!/usr/bin/env python3
"""
Ralph Zero - Agent Development Orchestrator

Usage:
    ralph-zero run [--max-iterations N] [--config PATH] [--verbose]
    ralph-zero validate [--config PATH]
    ralph-zero status [--verbose]
    ralph-zero archive <branch_name>
    ralph-zero --version
    ralph-zero --help

Commands:
    run          Execute autonomous development loop
    validate     Validate prd.json and configuration
    status       Show current progress status
    archive      Manually archive current run

Options:
    -h --help                Show this help message
    -v --version             Show version
    --max-iterations N       Override max iterations [default: from config]
    --config PATH            Path to ralph.json [default: ralph.json]
    --verbose                Verbose output (DEBUG logging)

Examples:
    ralph-zero run
    ralph-zero run --max-iterations 100
    ralph-zero validate
    ralph-zero status --verbose
    ralph-zero archive ralph/old-feature
"""

import logging
import sys
from pathlib import Path

try:
    from docopt import docopt
except ImportError:
    print("Error: docopt not installed. Run: pip install docopt")
    sys.exit(2)

from scripts.orchestrator.config import ConfigManager
from scripts.orchestrator.core import RalphZero
from scripts.orchestrator.state import StateManager
from scripts.orchestrator.utils import setup_logging, tc

__version__ = "0.1.0"


def main() -> None:
    """Main entry point for Ralph Zero CLI."""
    args = docopt(__doc__, version=f"Ralph Zero {__version__}")

    # Setup logging
    verbose = args.get("--verbose", False)
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logging("orchestrator.log", level=log_level, verbose=verbose)

    logger = logging.getLogger(__name__)
    logger.info(f"Ralph Zero {__version__} started")

    try:
        # Route to command
        if args["run"]:
            exit_code = cmd_run(args)
            sys.exit(exit_code)

        elif args["validate"]:
            exit_code = cmd_validate(args)
            sys.exit(exit_code)

        elif args["status"]:
            exit_code = cmd_status(args)
            sys.exit(exit_code)

        elif args["archive"]:
            exit_code = cmd_archive(args)
            sys.exit(exit_code)

    except KeyboardInterrupt:
        print(f"\n\n{tc.YELLOW}Interrupted by user{tc.NC}")
        logger.info("Interrupted by user (Ctrl+C)")
        sys.exit(130)

    except Exception as e:
        print(f"\n{tc.RED}❌ Fatal error: {e}{tc.NC}")
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)


def cmd_run(args: dict) -> int:
    """
    Execute autonomous development loop.

    Args:
        args: Parsed command arguments

    Returns:
        Exit code
    """
    logger = logging.getLogger(__name__)

    # Load configuration
    config_path = args.get("--config")
    try:
        config = ConfigManager.load(config_path)
    except FileNotFoundError as e:
        print(f"{tc.RED}❌ {e}{tc.NC}")
        logger.error(str(e))
        return 2
    except Exception as e:
        print(f"{tc.RED}❌ Configuration error: {e}{tc.NC}")
        logger.error(f"Configuration error: {e}", exc_info=True)
        return 2

    # Initialize state manager
    state = StateManager()

    # Get max iterations (from args or config)
    max_iters_str = args.get("--max-iterations")
    if max_iters_str:
        try:
            max_iterations = int(max_iters_str)
        except ValueError:
            print(f"{tc.RED}❌ Invalid --max-iterations: must be integer{tc.NC}")
            return 2
    else:
        max_iterations = config.max_iterations

    # Create orchestrator
    try:
        orchestrator = RalphZero(config, state, max_iterations=max_iterations)
    except Exception as e:
        print(f"{tc.RED}❌ Failed to initialize orchestrator: {e}{tc.NC}")
        logger.error(f"Orchestrator initialization failed: {e}", exc_info=True)
        return 2

    # Run!
    logger.info("Starting autonomous development loop")
    exit_code = orchestrator.run()

    if exit_code == 0:
        logger.info("All stories completed successfully")
    elif exit_code == 1:
        logger.warning("Max iterations reached, work incomplete")
    else:
        logger.error("Fatal error during execution")

    return exit_code


def cmd_validate(args: dict) -> int:
    """
    Validate prd.json and configuration.

    Args:
        args: Parsed command arguments

    Returns:
        Exit code (0=valid, 1=invalid, 2=error)
    """
    logger = logging.getLogger(__name__)

    print(f"\n{tc.BOLD}Validating Ralph Zero configuration...{tc.NC}\n")

    # Validate configuration
    print(f"{tc.BOLD}1. Configuration (ralph.json){tc.NC}")
    config_path = args.get("--config")

    try:
        config = ConfigManager.load(config_path)
        print(f"{tc.GREEN}✅ Configuration valid{tc.NC}")
        print(f"   Agent: {config.agent_command}")
        print(f"   Max iterations: {config.max_iterations}")
        print(f"   Quality gates: {len(config.quality_gates)}")
    except FileNotFoundError:
        print(f"{tc.YELLOW}⚠️  No ralph.json found, will use defaults{tc.NC}")
        config = ConfigManager()
    except Exception as e:
        print(f"{tc.RED}❌ Configuration invalid: {e}{tc.NC}")
        logger.error(f"Configuration validation failed: {e}")
        return 1

    # Validate PRD
    print(f"\n{tc.BOLD}2. PRD (prd.json){tc.NC}")
    state = StateManager()

    if not state.prd_path.exists():
        print(f"{tc.RED}❌ prd.json not found{tc.NC}")
        print(f"   Run: Load ralph-convert skill to create prd.json")
        return 1

    is_valid, errors = state.validate_prd()

    if is_valid:
        print(f"{tc.GREEN}✅ prd.json valid{tc.NC}")

        # Show summary
        stories = state.get_all_stories()
        passed = sum(1 for s in stories if s.get("passes", False))
        print(f"   Total stories: {len(stories)}")
        print(f"   Completed: {passed}")
        print(f"   Remaining: {len(stories) - passed}")
    else:
        print(f"{tc.RED}❌ prd.json invalid:{tc.NC}")
        for error in errors:
            print(f"   - {error}")
        return 1

    print(f"\n{tc.GREEN}{tc.BOLD}✅ All validations passed{tc.NC}\n")
    return 0


def cmd_status(args: dict) -> int:
    """
    Show current progress status.

    Args:
        args: Parsed command arguments

    Returns:
        Exit code (always 0)
    """
    state = StateManager()
    verbose = args.get("--verbose", False)

    # Create minimal config for orchestrator
    config = ConfigManager()

    # Create orchestrator just for status display
    orchestrator = RalphZero(config, state)
    orchestrator.print_status(verbose=verbose)

    return 0


def cmd_archive(args: dict) -> int:
    """
    Manually archive current run.

    Args:
        args: Parsed command arguments

    Returns:
        Exit code (0=success, 1=failure)
    """
    logger = logging.getLogger(__name__)
    branch_name = args["<branch_name>"]

    print(f"\n{tc.BOLD}Archiving current run for: {branch_name}{tc.NC}\n")

    state = StateManager()

    if state.archive_previous_run(branch_name):
        print(f"{tc.GREEN}✅ Archive complete{tc.NC}\n")
        return 0
    else:
        print(f"{tc.RED}❌ Archive failed{tc.NC}\n")
        logger.error("Archive failed")
        return 1


if __name__ == "__main__":
    main()

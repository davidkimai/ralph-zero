"""Quality gate execution and validation."""

import logging
import subprocess
from typing import Dict, List, Tuple

from .config import ConfigManager, QualityGate
from .utils import format_duration, tc

logger = logging.getLogger(__name__)


class QualityGates:
    """
    Execute configured quality gates.

    Supports:
    - Blocking vs non-blocking gates
    - Timeout enforcement
    - Parallel execution (future enhancement)
    - Detailed logging and user feedback
    """

    def __init__(self, config: ConfigManager) -> None:
        """
        Initialize QualityGates.

        Args:
            config: Configuration manager
        """
        self.config = config
        self.gates = config.quality_gates

    def run_all(self) -> bool:
        """
        Run all configured quality gates.

        Returns:
            True if all blocking gates pass, False otherwise
        """
        if not self.gates:
            logger.info("No quality gates configured, skipping")
            print(f"{tc.YELLOW}⚠️  No quality gates configured{tc.NC}")
            return True

        logger.info(f"Running {len(self.gates)} quality gates")
        print(f"\n{tc.BOLD}Running quality gates...{tc.NC}")

        results: Dict[str, Tuple[bool, float]] = {}

        for name, gate_config in self.gates.items():
            success, duration = self._run_gate(name, gate_config)
            results[name] = (success, duration)

        # Analyze results
        all_passed = all(success for success, _ in results.values())
        blocking_failed = [
            name
            for name, (success, _) in results.items()
            if not success and self.gates[name].blocking
        ]
        non_blocking_failed = [
            name
            for name, (success, _) in results.items()
            if not success and not self.gates[name].blocking
        ]

        # Report summary
        print()
        if all_passed:
            print(f"{tc.GREEN}✅ All quality gates passed{tc.NC}")
            logger.info("All quality gates passed")
            return True
        elif blocking_failed:
            print(f"{tc.RED}❌ Blocking gates failed: {', '.join(blocking_failed)}{tc.NC}")
            logger.error(f"Blocking gates failed: {blocking_failed}")
            return False
        elif non_blocking_failed:
            print(
                f"{tc.YELLOW}⚠️  Non-blocking gates failed: {', '.join(non_blocking_failed)}{tc.NC}"
            )
            print(f"{tc.GREEN}✅ Proceeding anyway (failures were non-blocking){tc.NC}")
            logger.warning(f"Non-blocking gates failed: {non_blocking_failed}")
            return True

        return True

    def _run_gate(self, name: str, gate_config: QualityGate) -> Tuple[bool, float]:
        """
        Run a single quality gate.

        Args:
            name: Gate name
            gate_config: Gate configuration

        Returns:
            Tuple of (success, duration_seconds)
        """
        cmd = gate_config.cmd
        timeout = gate_config.timeout
        working_dir = gate_config.working_dir or "."
        blocking = gate_config.blocking

        blocking_label = "BLOCKING" if blocking else "non-blocking"
        logger.info(f"Running gate '{name}' ({blocking_label}): {cmd}")
        print(f"  {name} ({blocking_label})...", end="", flush=True)

        import time

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=working_dir,
                timeout=timeout,
                capture_output=True,
                text=True,
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                print(f" {tc.GREEN}✅{tc.NC} ({format_duration(duration)})")
                logger.info(f"Gate '{name}' passed in {format_duration(duration)}")
                return (True, duration)
            else:
                print(f" {tc.RED}❌{tc.NC} (exit code {result.returncode})")
                logger.error(
                    f"Gate '{name}' failed with exit code {result.returncode}:\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

                # Show first few lines of error
                if result.stderr:
                    error_lines = result.stderr.strip().split("\n")[:3]
                    for line in error_lines:
                        print(f"    {tc.RED}{line}{tc.NC}")

                return (False, duration)

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            print(f" {tc.YELLOW}⏱️  TIMEOUT{tc.NC} (>{timeout}s)")
            logger.error(f"Gate '{name}' timed out after {timeout}s")
            return (False, duration)

        except Exception as e:
            duration = time.time() - start_time
            print(f" {tc.RED}❌ ERROR{tc.NC}")
            logger.error(f"Gate '{name}' raised exception: {e}", exc_info=True)
            return (False, duration)

    def get_gate_summary(self) -> str:
        """
        Get human-readable summary of configured gates.

        Returns:
            Formatted string describing gates
        """
        if not self.gates:
            return "No quality gates configured"

        lines = ["Configured quality gates:"]
        for name, gate in self.gates.items():
            blocking = "BLOCKING" if gate.blocking else "non-blocking"
            lines.append(f"  - {name}: {gate.cmd} ({blocking}, {gate.timeout}s timeout)")

        return "\n".join(lines)

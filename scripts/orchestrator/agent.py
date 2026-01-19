"""Agent invocation and output handling."""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .config import ConfigManager
from .utils import tc

logger = logging.getLogger(__name__)


class AgentInvoker:
    """
    Invokes AI agents with prompts and captures output.

    Automatically detects and uses appropriate invocation method:
    - Agent SDK: When agent_mode='sdk' or ANTHROPIC_API_KEY is available
    - CLI: When using command-line agent invocation

    Provides:
    - Universal agent command interface
    - Auto-detection of available agents  
    - Output capture and parsing
    - Completion signal detection
    """

    def __init__(self, config: ConfigManager) -> None:
        """
        Initialize AgentInvoker.

        Args:
            config: Configuration manager
        """
        self.config = config
        self.agent_command = config.agent_command
        
        # Detect agent mode
        self.use_sdk = self._should_use_sdk()
        
        if self.use_sdk:
            logger.info("Using Agent SDK mode")
            try:
                from .agent_sdk import AgentSDKInvoker
                self.sdk_invoker = AgentSDKInvoker(model=config.model)
                logger.info(f"AgentSDKInvoker initialized (model={config.model})")
            except Exception as e:
                logger.error(f"Failed to initialize SDK: {e}")
                logger.info("Falling back to CLI mode")
                self.use_sdk = False
                self.agent_command = self._auto_detect_agent()
        else:
            logger.info("Using CLI mode")
            # Auto-detect if needed
            if self.agent_command == "auto":
                self.agent_command = self._auto_detect_agent()
            logger.info(f"AgentInvoker initialized with command: {self.agent_command}")

    def invoke(self, prompt: str, iteration: int, timeout: int = 3600) -> str:
        """
        Invoke agent with prompt and capture output.

        Args:
            prompt: The prompt to send to agent
            iteration: Current iteration number (for temp files)
            timeout: Timeout in seconds (default: 1 hour)

        Returns:
            Agent output as string
        """
        # Route to SDK or CLI depending on mode
        if self.use_sdk:
            return self._invoke_sdk(prompt, iteration, timeout)
        else:
            return self._invoke_cli(prompt, iteration, timeout)
    
    def _invoke_sdk(self, prompt: str, iteration: int, timeout: int) -> str:
        """
        Invoke agent via SDK.
        
        Args:
            prompt: The prompt to send
            iteration: Current iteration
            timeout: Timeout in seconds
            
        Returns:
            Agent output
        """
        logger.info(f"Invoking agent via SDK for iteration {iteration}")
        print(f"\n{tc.BLUE}Invoking agent (SDK mode)...{tc.NC}")
        
        working_dir = Path(".")
        result = self.sdk_invoker.invoke(
            prompt=prompt,
            working_dir=working_dir,
            iteration=iteration,
            timeout=timeout
        )
        
        # Return output (SDK invoker handles completion signals internally)
        return result.output
    
    def _invoke_cli(self, prompt: str, iteration: int, timeout: int) -> str:
        """
        Invoke agent via CLI command.
        
        Args:
            prompt: The prompt to send
            iteration: Current iteration
            timeout: Timeout in seconds
            
        Returns:
            Agent output
        """
        logger.info(f"Invoking agent for iteration {iteration}")
        print(f"\n{tc.BLUE}Invoking agent...{tc.NC}")

        # Write prompt to temporary file
        prompt_file = Path(f".ralph_prompt_{iteration}.md")
        try:
            prompt_file.write_text(prompt, encoding="utf-8")
            logger.debug(f"Wrote prompt to {prompt_file} ({len(prompt)} chars)")

            # Build command with prompt file path replacement
            if "{prompt_file}" in self.agent_command:
                # Command expects prompt file path (e.g., "cat {prompt_file} | claude -p")
                cmd = self.agent_command.replace("{prompt_file}", str(prompt_file))
            else:
                # Legacy: command doesn't use placeholder, assume stdin
                cmd = f"cat {prompt_file} | {self.agent_command}"

            logger.debug(f"Executing: {cmd}")

            # Execute agent
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout

            if result.returncode != 0:
                logger.warning(
                    f"Agent exited with code {result.returncode}\n"
                    f"stderr: {result.stderr}"
                )
                # Include stderr in output for debugging
                output += f"\n\n--- Agent stderr ---\n{result.stderr}"

            logger.info(f"Agent completed ({len(output)} chars output)")
            print(f"{tc.GREEN}✅ Agent execution complete{tc.NC}")

            return output

        except subprocess.TimeoutExpired:
            logger.error(f"Agent timed out after {timeout}s")
            print(f"{tc.RED}❌ Agent timed out after {timeout}s{tc.NC}")
            return f"<promise>FAILED: TIMEOUT after {timeout}s</promise>"

        except Exception as e:
            logger.error(f"Error invoking agent: {e}", exc_info=True)
            print(f"{tc.RED}❌ Error invoking agent: {e}{tc.NC}")
            return f"<promise>FAILED: {str(e)}</promise>"

        finally:
            # Clean up prompt file
            if prompt_file.exists():
                prompt_file.unlink()
                logger.debug(f"Cleaned up {prompt_file}")

    def check_completion_signal(self, output: str) -> Tuple[bool, Optional[str]]:
        """
        Check if agent reported completion.

        Looks for:
        - <promise>COMPLETE</promise>
        - <promise>FAILED: reason</promise>

        Args:
            output: Agent output

        Returns:
            Tuple of (is_complete, failure_reason)
            - (True, None) if complete
            - (False, reason) if failed with reason
            - (False, "NO_SIGNAL") if no signal found
        """
        if "<promise>COMPLETE</promise>" in output:
            logger.info("Agent reported completion")
            return (True, None)

        if "<promise>FAILED:" in output:
            # Extract reason
            start = output.find("<promise>FAILED:")
            end = output.find("</promise>", start)
            if end != -1:
                reason = output[start + len("<promise>FAILED:") : end].strip()
                logger.warning(f"Agent reported failure: {reason}")
                return (False, reason)
            else:
                logger.warning("Agent reported failure but malformed signal")
                return (False, "MALFORMED_FAILURE_SIGNAL")

        logger.warning("Agent did not report completion or failure")
        return (False, "NO_COMPLETION_SIGNAL")

    def _should_use_sdk(self) -> bool:
        """
        Determine if SDK mode should be used.
        
        Returns:
            True if SDK should be used, False for CLI mode
        """
        # Check explicit config
        if self.config.agent_mode == "sdk":
            logger.info("SDK mode explicitly configured")
            return True
        
        # Check if API key is available (auto-enable SDK)
        if os.getenv("ANTHROPIC_API_KEY"):
            logger.info("ANTHROPIC_API_KEY found, enabling SDK mode")
            return True
        
        # Default to CLI
        return False
    
    def _auto_detect_agent(self) -> str:
        """
        Auto-detect available agent command.

        Returns:
            Detected agent command or error message
        """
        logger.info("Auto-detecting available agent...")

        # Try common agent commands in order of preference
        candidates = [
            ("claude", "claude -p"),
            ("amp", "amp"),
            ("cursor", "cursor-agent -p"),
            ("copilot", "copilot-agent"),
        ]

        for binary, command in candidates:
            if self._check_command_exists(binary):
                logger.info(f"Auto-detected agent: {command}")
                print(f"{tc.GREEN}✅ Auto-detected agent: {command}{tc.NC}")
                return command

        # No agent found
        error_msg = (
            "No compatible agent found. Please install one of:\n"
            "  - Claude CLI (claude)\n"
            "  - Amp (amp)\n"
            "  - Cursor Agent (cursor-agent)\n"
            "  - GitHub Copilot Agent (copilot-agent)\n"
            "Or specify agent_command in ralph.json"
        )
        logger.error(error_msg)
        print(f"{tc.RED}❌ {error_msg}{tc.NC}")
        raise RuntimeError("No agent found")

    def _check_command_exists(self, command: str) -> bool:
        """
        Check if command exists in PATH.

        Args:
            command: Command name to check

        Returns:
            True if command exists, False otherwise
        """
        result = subprocess.run(
            ["which", command],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def get_agent_info(self) -> dict:
        """
        Get information about configured agent.

        Returns:
            Dict with agent details
        """
        return {
            "command": self.agent_command,
            "auto_detected": self.config.agent_command == "auto",
        }
